"""Safety incidents extend existing admission locks without replacing protection."""

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from flask import Flask, jsonify, session
from flask_wtf.csrf import CSRFProtect, generate_csrf
from sqlalchemy import event, update

from blueprints.nifty_algo import nifty_algo_bp
from database.engine_factory import create_db_engine
from database.nifty_algo_db import NiftyAccount, NiftyState, NiftyStore, StateConflict
from services.nifty_algo.paper_executor import OrderRefused
from services.nifty_algo.runner import NiftyRunner
from test.test_nifty_algo_paper_executor import (
    NOW,
    USER,
    buy_intent,
    executor,
    running,
)


@pytest.fixture
def store(tmp_path):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'safety.db'}")
    value = NiftyStore(engine)
    value.initialize()
    value.ensure_user(USER)
    yield value
    engine.dispose()


def incident(store, *, mode="PAPER", key="lost-feed"):
    return store.raise_safety_incident(
        USER, key, mode=mode, code="STALE_DATA", severity="CRITICAL", now=NOW
    )


def test_incident_is_durable_idempotent_and_acknowledgement_does_not_clear(store):
    first = incident(store)
    assert incident(store)["id"] == first["id"]
    assert store.read(USER)["state"] == "PAUSED"
    acknowledged = store.acknowledge_safety_incident(
        USER, first["id"], first["revision"], actor=USER, now=NOW
    )
    assert acknowledged["status"] == "ACKNOWLEDGED"
    assert acknowledged["revision"] == first["revision"] + 1
    store.mark_reconciled(USER, NOW + timedelta(seconds=1))
    reopened = NiftyStore(store.engine)
    assert reopened.safety_status(USER)["entry_blocked"]
    with pytest.raises(StateConflict):
        reopened.acknowledge_safety_incident(
            USER, first["id"], first["revision"], actor=USER, now=NOW
        )


def test_incident_blocks_admission_even_if_running_state_is_changed(store):
    paper = executor(store)
    running(store)
    incident(store)
    # Simulates an old process restoring RUNNING without understanding new tables.
    running(store)
    with pytest.raises(OrderRefused) as refused:
        paper.admit(buy_intent(), NOW)
    assert "SAFETY_INTERLOCK" in refused.value.reasons
    assert store.pending_orders(USER) == []


def test_shadow_incident_does_not_block_primary_or_cross_owner(store):
    incident(store, mode="SHADOW")
    assert not store.safety_status(USER)["entry_blocked"]
    assert not store.safety_status("another-user")["incidents"]
    assert not store.safety_status("another-user")["entry_blocked"]


def test_incident_acknowledgement_requires_owning_actor(store):
    first = incident(store)
    with pytest.raises(ValueError):
        store.acknowledge_safety_incident(
            USER, first["id"], first["revision"], actor="another-user", now=NOW
        )
    assert store.safety_status(USER)["incidents"][0]["status"] == "OPEN"


def test_incident_at_fill_write_cannot_fill_pending_buy(store, monkeypatch):
    paper = executor(store)
    running(store)
    order, _ = paper.admit(buy_intent(), NOW)
    original = store.fill

    def competing_incident(*args, **kwargs):
        incident(store)
        # The incident gate, not only PAUSED, must protect a pending reservation.
        running(store)
        return original(*args, **kwargs)

    monkeypatch.setattr(store, "fill", competing_incident)
    paper.market_data.stamp = NOW + timedelta(seconds=1)
    paper.process(NOW + timedelta(seconds=1))
    assert store.order_by_intent(USER, order["intent_id"])["status"] != "FILLED"
    assert not store.positions(USER)


@pytest.fixture
def client(store, monkeypatch):
    import utils.session

    monkeypatch.setattr(utils.session, "is_session_valid", lambda: bool(session.get("user")))
    app = Flask(__name__)
    app.secret_key = "test-only-nifty-safety-key"
    app.config["TESTING"] = True
    app.extensions["nifty_algo_store"] = store
    CSRFProtect(app)
    app.register_blueprint(nifty_algo_bp)

    @app.get("/fixture-csrf")
    def csrf():
        return jsonify(token=generate_csrf())

    return app.test_client()


def login(client, user=USER):
    with client.session_transaction() as browser:
        browser["user"] = user
    return {"X-CSRFToken": client.get("/fixture-csrf").json["token"]}


def test_safety_api_requires_owner_session_and_csrf(client, store):
    first = incident(store)
    url = f"/api/nifty-algo/safety/incidents/{first['id']}/acknowledge"
    assert client.get("/api/nifty-algo/safety", headers={"Accept": "application/json"}).status_code == 401
    token = client.get("/fixture-csrf").json["token"]
    assert client.post(
        url, json={"revision": 1}, headers={"X-CSRFToken": token, "Accept": "application/json"}
    ).status_code == 401
    headers = login(client)
    assert client.post(url, json={"revision": 1}).status_code == 400
    assert client.post(url, json={"revision": 1}, headers=headers).status_code == 200
    status = client.get("/api/nifty-algo/safety").json["data"]
    assert status["entry_blocked"]
    assert status["incidents"][0]["status"] == "ACKNOWLEDGED"
    assert client.post(url, json={"revision": 1}, headers=headers).status_code == 409
    other = login(client, "another-user")
    assert client.get("/api/nifty-algo/safety").json["data"]["incidents"] == []
    assert client.post(url, json={"revision": 2}, headers=other).status_code == 404


@pytest.mark.parametrize("body", [None, [], {"revision": True}, {"revision": 0}, {"revision": 1, "actor": USER}])
def test_safety_acknowledgement_rejects_invalid_body(client, store, body):
    first = incident(store)
    headers = login(client)
    response = client.post(
        f"/api/nifty-algo/safety/incidents/{first['id']}/acknowledge",
        json=body,
        headers=headers,
    )
    assert response.status_code == 400
    assert store.safety_status(USER)["incidents"][0]["status"] == "OPEN"


def test_status_readiness_includes_safety_interlock(client, store):
    state = store.read(USER)
    store.claim_runner(
        USER, "ready-fixture", NOW, seconds=10**9,
        payload={"entries_ready": True, "configuration_id": state["configuration_id"]},
    )
    incident(store)
    login(client)
    response = client.get("/api/nifty-algo/status")
    assert response.status_code == 200
    assert response.json["data"]["ready"] is False


def resolution_ready(store, *, mode="PAPER", code="STALE_DATA"):
    first = store.raise_safety_incident(
        USER, "resolve-fixture", mode=mode, code=code, severity="CRITICAL", now=NOW
    )
    acknowledged = store.acknowledge_safety_incident(
        USER, first["id"], first["revision"], actor=USER, now=NOW
    )
    state = store.read(USER)
    store.mark_reconciled(USER, NOW + timedelta(seconds=1))
    store.claim_runner(
        USER, "resolution-fixture", NOW + timedelta(seconds=1),
        payload={
            "entries_ready": True,
            "configuration_id": state["configuration_id"],
            "assessed_at": (NOW + timedelta(seconds=1)).isoformat(),
        },
    )
    return acknowledged, state


def resolve(store, row, state, **overrides):
    return store.resolve_safety_incident(
        USER, row["id"], row["revision"], state["revision"],
        actor=overrides.get("actor", USER),
        now=overrides.get("now", NOW + timedelta(seconds=2)),
    )


def test_resolution_rechecks_paper_ledger_and_records_actor_without_resuming(store):
    row, state = resolution_ready(store)
    result = resolve(store, row, state)
    assert result["status"] == "RESOLVED"
    assert result["resolved_by"] == USER
    assert result["resolved_at"] == (NOW + timedelta(seconds=2)).isoformat()
    assert result["evidence"]["scope"] == "ISOLATED_PAPER_LEDGER"
    restored = NiftyStore(store.engine).safety_status(USER)["incidents"][0]
    assert restored["resolved_by"] == result["resolved_by"]
    assert restored["resolved_at"] == result["resolved_at"]
    assert restored["evidence"] == result["evidence"]
    assert result["revision"] == row["revision"] + 1
    assert store.read(USER)["state"] == "PAUSED"
    assert store.read(USER)["revision"] == state["revision"] + 1
    assert not store.safety_status(USER)["entry_blocked"]
    evidence = store.events(USER, kind="safety_resolved")[0]["payload"]
    assert evidence["resolved_by"] == USER
    assert evidence["evidence"]["scope"] == "ISOLATED_PAPER_LEDGER"
    assert evidence["evidence"]["checked_at"] == (NOW + timedelta(seconds=2)).isoformat()
    with pytest.raises(StateConflict):
        resolve(store, row, state)
    assert len(store.events(USER, kind="safety_resolved")) == 1


def test_resolution_evidence_survives_busy_history_and_stays_owner_scoped(store):
    row, state = resolution_ready(store)
    result = resolve(store, row, state)
    for index in range(101):
        store.record_event(USER, "heartbeat", {"index": index}, NOW)
    store.record_event(
        "another-user", "safety_resolved",
        {**result, "resolved_by": "another-user", "evidence": {"scope": "WRONG_OWNER"}},
        NOW,
    )
    restored = NiftyStore(store.engine).safety_status(USER)["incidents"][0]
    assert restored["resolved_by"] == USER
    assert restored["evidence"] == result["evidence"]
    assert NiftyStore(store.engine).safety_status("another-user")["incidents"] == []


@pytest.mark.parametrize("mode,code", [
    ("LIVE", "STALE_DATA"), ("SHADOW", "STALE_DATA"),
    ("PAPER", "BROKER_AMBIGUITY"), ("PAPER", "UNKNOWN_SAFETY_CONDITION"),
])
def test_resolution_refuses_unverified_modes_and_conditions(store, mode, code):
    row, state = resolution_ready(store, mode=mode, code=code)
    with pytest.raises(StateConflict):
        resolve(store, row, state)
    assert not store.events(USER, kind="safety_resolved")


@pytest.mark.parametrize("delay", [-1, 32])
def test_resolution_refuses_future_or_stale_assessment(store, delay):
    row, state = resolution_ready(store)
    with pytest.raises(StateConflict):
        resolve(store, row, state, now=NOW + timedelta(seconds=delay))


def test_resolution_cannot_use_reconciled_flag_to_hide_current_ledger_mismatch(store):
    row, state = resolution_ready(store)
    with store.sessions.begin() as db:
        db.execute(update(NiftyAccount).where(NiftyAccount.user_id == USER).values(available=1))
    with pytest.raises(StateConflict):
        resolve(store, row, state)
    assert store.safety_status(USER)["entry_blocked"]


def test_resolution_cannot_clear_kill_or_ignore_competing_control(store):
    row, state = resolution_ready(store)
    store.change(USER, state["revision"], action="kill-switch")
    with pytest.raises(StateConflict):
        resolve(store, row, state)
    current = store.read(USER)
    with pytest.raises(StateConflict):
        resolve(store, row, current)
    assert store.read(USER)["killed"]


def test_resolution_requires_owner_and_acknowledged_revision(store):
    row, state = resolution_ready(store)
    with pytest.raises(ValueError):
        resolve(store, row, state, actor="other")
    with store.sessions.begin() as db:
        db.execute(update(NiftyState).where(NiftyState.user_id == USER).values(state="RUNNING"))
    with pytest.raises(StateConflict):
        resolve(store, row, store.read(USER))


def test_runner_lease_carries_assessment_time_not_heartbeat_time(store):
    runner = NiftyRunner(
        store, USER, native=Mock(), executor=executor(store), clock=lambda: NOW
    )
    assert runner._lease(NOW)
    assert store.runner_status(USER, NOW).get("assessed_at") is None
    runner.last_assessed_at = NOW
    assert runner._lease(NOW + timedelta(seconds=5))
    assert store.runner_status(USER, NOW)["assessed_at"] == NOW.isoformat()


def test_resolution_api_requires_owner_csrf_confirmation_and_both_revisions(
    client, store, monkeypatch
):
    row, state = resolution_ready(store)
    monkeypatch.setattr(
        "blueprints.nifty_algo.datetime",
        Mock(now=lambda *_: NOW + timedelta(seconds=2)),
    )
    url = f"/api/nifty-algo/safety/incidents/{row['id']}/resolve"
    body = {
        "revision": row["revision"], "state_revision": state["revision"],
        "confirm": "RESOLVE_ONLY",
    }
    headers = login(client)
    assert client.post(url, json=body).status_code == 400
    for invalid in (
        {**body, "confirm": False}, {**body, "revision": True},
        {**body, "state_revision": 0}, {**body, "actor": USER},
    ):
        assert client.post(url, json=invalid, headers=headers).status_code == 400
    assert client.post(
        url, json={**body, "state_revision": state["revision"] - 1}, headers=headers
    ).status_code == 409
    other = login(client, "another-user")
    assert client.post(url, json=body, headers=other).status_code == 404
    headers = login(client)
    response = client.post(url, json=body, headers=headers)
    assert response.status_code == 200
    assert response.json["data"]["status"] == "RESOLVED"
    assert response.json["data"]["resolved_by"] == USER
    assert response.json["data"]["evidence"]["checked_at"] == (
        NOW + timedelta(seconds=2)
    ).isoformat()
    assert store.read(USER)["state"] == "PAUSED"
    assert client.post(url, json=body, headers=headers).status_code == 409
    status = client.get("/api/nifty-algo/safety").json["data"]
    assert status["state_revision"] == state["revision"] + 1
    assert status["recovery_available"]


@pytest.mark.parametrize("age", [None, 31, -5])
def test_start_refuses_renewed_heartbeat_without_fresh_assessment(store, age):
    now = datetime.now(UTC)
    store.mark_reconciled(USER, now)
    state = store.read(USER)
    payload = {"entries_ready": True, "configuration_id": state["configuration_id"]}
    if age is not None:
        payload["assessed_at"] = (now - timedelta(seconds=age)).isoformat()
    store.claim_runner(USER, "start-fixture", now, payload=payload)
    with pytest.raises(StateConflict):
        store.change(USER, state["revision"], action="start")
    assert store.read(USER)["state"] != "RUNNING"


def test_start_rechecks_ledger_at_write_despite_reconciled_flag(store, monkeypatch):
    now = datetime.now(UTC)
    store.mark_reconciled(USER, now)
    state = store.read(USER)
    store.claim_runner(
        USER, "start-fixture", now,
        payload={
            "entries_ready": True, "configuration_id": state["configuration_id"],
            "assessed_at": now.isoformat(),
        },
    )
    original = store._lock

    def competing_ledger_write(db, user_id):
        with store.sessions.begin() as writer:
            writer.execute(update(NiftyAccount).where(
                NiftyAccount.user_id == user_id
            ).values(available=1))
        monkeypatch.setattr(store, "_lock", original)
        return original(db, user_id)

    monkeypatch.setattr(store, "_lock", competing_ledger_write)
    with pytest.raises(StateConflict):
        store.change(USER, state["revision"], action="start")
    assert store.read(USER)["state"] != "RUNNING"


def test_resolving_one_incident_preserves_other_hold_and_kill_safety(store):
    row, _ = resolution_ready(store)
    incident(store, key="second-hold")
    resolve(store, row, store.read(USER))
    assert store.safety_status(USER)["entry_blocked"]
    assert store.read(USER)["state"] == "PAUSED"
    assert store.safety_status(USER)["incidents"][0]["status"] == "OPEN"


def test_resolved_incident_needs_separate_start_with_current_revision(store):
    row, state = resolution_ready(store)
    resolve(store, row, state)
    paused = store.read(USER)
    assert paused["state"] == "PAUSED"
    now = datetime.now(UTC)
    store.claim_runner(
        USER, "resolution-fixture", now,
        payload={
            "entries_ready": True, "configuration_id": paused["configuration_id"],
            "assessed_at": now.isoformat(),
        },
    )
    with pytest.raises(StateConflict):
        store.change(USER, state["revision"], action="start")
    assert store.read(USER)["state"] == "PAUSED"
    started = store.change(USER, paused["revision"], action="start")
    assert started["state"] == "RUNNING"
    assert len(store.events(USER, kind="start")) == 1


def test_resolution_failures_release_all_connections_and_rollback(store):
    row, state = resolution_ready(store)
    acquired, released = [], []

    def opened(connection, record):
        acquired.append(id(connection))

    def closed(connection, record):
        released.append(id(connection))

    def failed_commit(session):
        raise RuntimeError("Simulated audit commit failure")

    event.listen(store.engine, "connect", opened)
    event.listen(store.engine, "close", closed)
    event.listen(store.sessions.class_, "before_commit", failed_commit)
    try:
        for _ in range(100):
            with pytest.raises(RuntimeError, match="Simulated audit commit failure"):
                resolve(store, row, state)
            assert len(acquired) == len(released)
    finally:
        event.remove(store.engine, "connect", opened)
        event.remove(store.engine, "close", closed)
        event.remove(store.sessions.class_, "before_commit", failed_commit)
    assert len(acquired) == 100
    assert store.safety_status(USER)["incidents"][0]["status"] == "ACKNOWLEDGED"
    assert store.read(USER)["revision"] == state["revision"]
    assert not store.events(USER, kind="safety_resolved")
