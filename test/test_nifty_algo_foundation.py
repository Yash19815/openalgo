"""Feature persistence, authenticated API and execution admission regressions."""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask, jsonify, session
from flask_wtf import CSRFProtect
from flask_wtf.csrf import generate_csrf
from sqlalchemy import event, inspect, select

from blueprints.nifty_algo import initialize_nifty, nifty_algo_bp
from database.engine_factory import create_db_engine
from database.nifty_algo_db import NiftyConfiguration, NiftyStore, StateConflict
from services.nifty_algo.config import StrategyConfig
from services.nifty_algo.paper_executor import NiftyPaperExecutor, PaperExecutionUnavailable


@pytest.fixture
def engine(tmp_path):
    database = create_db_engine(f"sqlite:///{tmp_path / 'feature.db'}")
    yield database
    database.dispose()


@pytest.fixture
def store(engine):
    result = NiftyStore(engine)
    result.initialize()
    return result


def test_additive_initialization_and_immutable_config(store, engine):
    store.initialize()
    assert "nifty_algo_state" in inspect(engine).get_table_names()
    original = store.read("alice")
    config = StrategyConfig(adx_min=30)
    updated = store.change("alice", original["revision"], configuration=config)
    assert updated["configuration_id"] != original["configuration_id"]
    with store.sessions() as db:
        revisions = list(
            db.scalars(select(NiftyConfiguration).order_by(NiftyConfiguration.revision))
        )
        assert len(revisions) == 2
        assert revisions[0].configuration["adx_min"] == 25
    with pytest.raises(StateConflict):
        store.change("alice", original["revision"], action="stop")


def test_kill_survives_store_recreation_and_configuration_change(store, engine):
    first = store.read("alice")
    killed = store.change("alice", first["revision"], action="kill-switch")
    restored = NiftyStore(engine)
    assert restored.read("alice")["killed"]
    changed = restored.change("alice", killed["revision"], configuration=StrategyConfig(adx_min=35))
    assert changed["state"] == "KILLED"
    assert restored.read("bob")["killed"] is False


def test_concurrent_control_has_one_winner(store):
    original = store.read("alice")

    def change(action):
        try:
            return store.change("alice", original["revision"], action=action)["revision"]
        except StateConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(change, ("stop", "kill-switch")))
    assert sorted(map(str, results)) == ["2", "conflict"]


def test_decision_deduplication_and_user_scope(store):
    decision = {"decision_id": "abc", "eligible": False, "bias": "NO_TRADE"}
    store.record_decision("alice", decision)
    assert store.record_decision("alice", {**decision, "eligible": True}) == decision
    assert store.decisions("bob") == []
    assert len(store.decisions("alice")) == 1


def test_sessions_release_connections_on_repeated_success_and_conflict(store, engine):
    connections = {"active": 0}

    def checkout(*args):
        connections["active"] += 1

    def checkin(*args):
        connections["active"] -= 1

    event.listen(engine, "checkout", checkout)
    event.listen(engine, "checkin", checkin)
    try:
        for _ in range(100):
            store.read("alice")
            with pytest.raises(StateConflict):
                store.change("alice", 0, action="pause")
            assert connections["active"] == 0
    finally:
        event.remove(engine, "checkout", checkout)
        event.remove(engine, "checkin", checkin)


@pytest.fixture
def client(engine, monkeypatch):
    import utils.session

    monkeypatch.setattr(utils.session, "is_session_valid", lambda: bool(session.get("user")))
    app = Flask(__name__)
    app.secret_key = "test-only-nifty-fixture-key"
    app.config["TESTING"] = True
    CSRFProtect(app)
    app.register_blueprint(nifty_algo_bp)
    initialize_nifty(app, engine)

    @app.get("/fixture-csrf")
    def csrf():
        return jsonify(token=generate_csrf())

    return app.test_client()


def test_api_auth_csrf_validation_and_readiness(client):
    assert (
        client.get("/api/nifty-algo/status", headers={"Accept": "application/json"}).status_code
        == 401
    )
    with client.session_transaction() as browser:
        browser["user"] = "alice"
    data = client.get("/api/nifty-algo/status").json["data"]
    assert data["mode"] == "PAPER_ONLY"
    assert data["ready"] is False
    assert (
        client.post("/api/nifty-algo/strategy/kill-switch", json={"revision": 1}).status_code == 400
    )
    token = client.get("/fixture-csrf").json["token"]
    headers = {"X-CSRFToken": token}
    assert (
        client.post("/api/nifty-algo/strategy/start", json={}, headers=headers).status_code == 409
    )
    assert client.post("/api/nifty-algo/strategy/live", json={}, headers=headers).status_code == 404
    assert (
        client.put(
            "/api/nifty-algo/configuration",
            json={"revision": 1, "configuration": {"execution_mode": "LIVE"}},
            headers=headers,
        ).status_code
        == 400
    )
    response = client.post(
        "/api/nifty-algo/strategy/kill-switch", json={"revision": 1}, headers=headers
    )
    assert response.json["data"]["killed"] is True
    assert client.get("/api/nifty-algo/positions").status_code == 200
    assert client.get("/api/nifty-algo/positions").json["data"] == []


def test_api_start_requires_current_lease_config_and_reconciliation(client):
    from datetime import UTC, datetime

    with client.session_transaction() as browser:
        browser["user"] = "alice"
    state = client.application.extensions["nifty_algo_store"]
    current = state.read("alice")
    state.account("alice")
    now = datetime.now(UTC)
    state.claim_runner(
        "alice",
        "offline-lease",
        now,
        payload={"entries_ready": True, "configuration_id": current["configuration_id"]},
    )
    token = client.get("/fixture-csrf").json["token"]
    response = client.post(
        "/api/nifty-algo/strategy/start",
        json={"revision": current["revision"]},
        headers={"X-CSRFToken": token},
    )
    assert response.status_code == 200 and response.json["data"]["state"] == "RUNNING"
    changed = state.change(
        "alice", response.json["data"]["revision"], configuration=StrategyConfig(adx_min=35)
    )
    assert not client.get("/api/nifty-algo/status").json["data"]["ready"]
    refused = client.post(
        "/api/nifty-algo/strategy/start",
        json={"revision": changed["revision"]},
        headers={"X-CSRFToken": token},
    )
    assert refused.status_code == 409


def test_socket_updates_use_valid_signed_session_ownership(client, monkeypatch):
    import blueprints.nifty_algo as feature
    import utils.session as sessions

    join, leave = Mock(), Mock()
    monkeypatch.setattr(feature, "join_room", join)
    monkeypatch.setattr(feature, "leave_room", leave)
    with client.application.test_request_context():
        session["user"] = "alice"
        monkeypatch.setattr(sessions, "is_session_valid", lambda: False)
        assert feature.subscribe_updates({"user": "bob"})["status"] == "error"
        join.assert_not_called()
        monkeypatch.setattr(sessions, "is_session_valid", lambda: True)
        assert feature.subscribe_updates({"user": "bob"})["status"] == "success"
        join.assert_called_once_with("nifty_algo:alice")
        assert feature.unsubscribe_updates()["status"] == "success"
        leave.assert_called_once_with("nifty_algo:alice")
        session.clear()
        assert feature.subscribe_updates()["status"] == "error"


def test_assessment_uses_server_key_and_persists_no_order_decision(client, monkeypatch):
    import sys

    import services.nifty_algo.assessment as assessment

    reader = Mock(
        return_value={
            "decision_id": "fixture-decision",
            "eligible": False,
            "final_action": "NO_ORDER",
            "source": "TEST_FIXTURE",
        }
    )
    monkeypatch.setattr(assessment, "assess_current", reader)
    lookup = Mock(return_value="test-only-server-key")
    monkeypatch.setitem(
        sys.modules, "database.auth_db", SimpleNamespace(get_api_key_for_tradingview=lookup)
    )
    with client.session_transaction() as browser:
        browser["user"] = "alice"
    token = client.get("/fixture-csrf").json["token"]
    response = client.post("/api/nifty-algo/assessment", json={}, headers={"X-CSRFToken": token})
    assert response.status_code == 200
    lookup.assert_called_once_with("alice")
    assert reader.call_args.args[0] == "test-only-server-key"
    assert "test-only-server-key" not in response.get_data(as_text=True)
    assert client.get("/api/nifty-algo/signals").json["data"][0]["final_action"] == "NO_ORDER"


@pytest.mark.parametrize("analyzer", [True, False])
def test_closed_execution_boundary_cannot_import_broker_or_generic_orders(monkeypatch, analyzer):
    import builtins

    original = builtins.__import__
    broker_boundary = Mock(side_effect=AssertionError("Real order dependency reached"))

    def guarded(name, *args, **kwargs):
        if name.startswith("broker.") or name in {
            "services.place_order_service",
            "services.place_smart_order_service",
            "services.cancel_order_service",
            "services.close_position_service",
        }:
            return broker_boundary(name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    executor = NiftyPaperExecutor()
    for mode in (analyzer, not analyzer):
        with pytest.raises(PaperExecutionUnavailable):
            executor.submit({"mode": mode, "symbol": "BANKNIFTY", "action": "SELL"})
    broker_boundary.assert_not_called()
