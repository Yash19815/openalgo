"""Phase 5: Paper/Live trading mode, Live readiness and masked broker status."""

import ast
import importlib.abc
import inspect
import json
import logging
import re
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask, jsonify, session
from flask_wtf.csrf import CSRFProtect, generate_csrf
from sqlalchemy import inspect as schema

from blueprints.nifty_algo import initialize_nifty, nifty_algo_bp
from database.engine_factory import create_db_engine
from database.nifty_algo_db import NiftyMode, NiftyStore, StateConflict
from services.nifty_algo import calendar as session_calendar
from services.nifty_algo import trading_mode
from services.nifty_algo.config import StrategyConfig
from services.nifty_algo.paper_executor import OrderRefused
from services.nifty_algo.runner import NiftyRunner
from services.nifty_algo.trading_mode import (
    LIVE_ADAPTER,
    LiveAdapterStub,
    broker_status,
    live_readiness,
    request_mode,
)
from test.test_nifty_algo_paper_executor import (
    NOW,
    USER,
    FakeMarket,
    buy_intent,
    executor,
    running,
)
from test.test_nifty_algo_phase1 import Phase1MarketCalendar
from utils.broker_keys import BrokerKeys

SECRET_TOKEN = "SECRET-TOKEN-1234567890"
SECRET_FEED = "SECRET-FEED-0987654321"
SECRET_KEY = "SECRET-APIKEY-5566778899"
SECRET_API_SECRET = "SECRET-APISECRET-1122334455"
SECRETS = (SECRET_TOKEN, SECRET_FEED, SECRET_KEY, SECRET_API_SECRET)
UNVERIFIED = [
    "BROKER_UNREACHABLE",
    "LIVE_NOT_READY",
    "MARKET_DATA_UNVERIFIED",
    "PROTECTIVE_ORDERS_UNVERIFIED",
    "FILL_RECONCILIATION_UNVERIFIED",
    "STATIC_IP_UNVERIFIED",
]


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(session_calendar, "_legacy_calendar", lambda: Phase1MarketCalendar())
    engine = create_db_engine(f"sqlite:///{tmp_path / 'phase5.db'}")
    value = NiftyStore(engine, calendar_blob_dir=tmp_path / "calendar_blobs")
    value.initialize()
    value.ensure_user(USER)
    yield value
    engine.dispose()


def keys():
    return BrokerKeys(
        broker="zerodha",
        source="saved",
        api_key=SECRET_KEY,
        api_secret=SECRET_API_SECRET,
        api_key_market="",
        api_secret_market="",
        redirect_url="http://127.0.0.1:5000/zerodha/callback",
    )


def ready_facts(user_id=USER):
    return {
        "broker": "zerodha",
        "broker_name": "Zerodha",
        "auth": SECRET_TOKEN,
        "feed_token": SECRET_FEED,
        "revoked": False,
        "session_current": True,
        "keys": keys(),
        "openalgo_api_key": True,
    }


def seed_auth_sources(monkeypatch, *, revoked=False, current=True):
    """Stand-ins for OpenAlgo's auth and broker-key stores, holding real-looking secrets."""
    import database.auth_db
    import utils.broker_keys

    row = SimpleNamespace(
        name=USER, auth=SECRET_TOKEN, feed_token=SECRET_FEED, broker="zerodha", is_revoked=revoked
    )
    monkeypatch.setattr(trading_mode, "_auth_row", lambda user_id: row)
    monkeypatch.setattr(utils.broker_keys, "resolve", lambda broker: keys())
    monkeypatch.setattr(
        utils.broker_keys, "live_broker", lambda: "zerodha" if current else None
    )
    monkeypatch.setattr(database.auth_db, "get_api_key", lambda user_id: True)


def force_mode(store, mode):
    store.trading_mode(USER)
    with store.sessions.begin() as db:
        db.get(NiftyMode, USER).mode = mode


def assert_no_secret(text, tails=False):
    for secret in SECRETS:
        assert secret not in text
        assert not tails or secret[-4:] not in text


def open_position(store, market=None):
    running(store)
    market = market or FakeMarket()
    exe = executor(store, market=market, config=StrategyConfig(latency_ms=1))
    exe.admit(buy_intent())
    assert exe.process(NOW + timedelta(seconds=1))[0]["status"] == "FILLED"
    return exe, market


# Mode table ------------------------------------------------------------------


def test_mode_table_is_additive_and_new_users_default_to_paper(store):
    assert {"nifty_algo_mode", "nifty_algo_state", "nifty_algo_account"} <= set(
        schema(store.engine).get_table_names()
    )
    with store.sessions() as db:
        row = db.get(NiftyMode, USER)
        assert row.mode == "PAPER" and row.revision == 1 and row.history == []
    store.ensure_user("second")
    assert store.trading_mode("second")["mode"] == "PAPER"


def test_existing_users_without_a_mode_row_default_to_paper(store):
    NiftyMode.__table__.drop(store.engine)
    assert "nifty_algo_mode" not in schema(store.engine).get_table_names()
    store.initialize()  # Startup create_all adds the table; nothing else changes.
    mode = store.trading_mode(USER)
    assert mode["mode"] == "PAPER" and mode["revision"] == 1 and mode["history"] == []
    assert store.trading_mode(USER)["revision"] == 1


# Readiness -------------------------------------------------------------------


def test_live_is_refused_even_when_every_broker_fact_is_ready(store):
    mode, codes, changed = request_mode(
        store, USER, 1, "LIVE", acknowledged=True, actor=USER, reader=ready_facts
    )
    assert codes == UNVERIFIED and not changed
    assert mode["mode"] == "PAPER" and mode["revision"] == 1
    assert store.trading_mode(USER)["mode"] == "PAPER"
    refused = [e for e in store.events(USER) if e["kind"] == "mode_change_refused"]
    assert len(refused) == 1
    payload = refused[0]["payload"]
    assert payload["previous"] == "PAPER" and payload["requested"] == "LIVE"
    assert payload["actor"] == USER and payload["codes"] == UNVERIFIED
    assert payload["readiness"]["broker"]["auth_token_present"] is True
    assert_no_secret(json.dumps(store.events(USER)))


def test_live_not_ready_cannot_be_bypassed(store, monkeypatch):
    # A future adapter reporting ready still cannot activate Live in this release.
    monkeypatch.setattr(LIVE_ADAPTER, "readiness", lambda: [])
    monkeypatch.setattr(LIVE_ADAPTER, "reachable", lambda: True)
    status = broker_status(USER, ready_facts)
    assert live_readiness(status, {"positions": 0, "pending_orders": 0}, True) == [
        "LIVE_NOT_READY"
    ]
    _, codes, changed = store.change_mode(
        USER, 1, "LIVE", actor=USER, evaluate=lambda exposure, current: [], snapshot={}
    )
    assert codes == ["LIVE_NOT_READY"] and not changed
    assert store.trading_mode(USER)["mode"] == "PAPER"
    with pytest.raises(OrderRefused) as refused:
        LiveAdapterStub().submit({"side": "BUY"})
    assert refused.value.reasons == ["LIVE_NOT_READY"]


def test_ack_required_without_explicit_true_acknowledgement(store):
    for acknowledged in (False, None, "true", 1):
        _, codes, _ = request_mode(
            store, USER, 1, "LIVE", acknowledged=acknowledged, actor=USER, reader=ready_facts
        )
        assert codes[-1] == "ACK_REQUIRED" and "LIVE_NOT_READY" in codes
    _, codes, _ = request_mode(
        store, USER, 1, "LIVE", acknowledged=True, actor=USER, reader=ready_facts
    )
    assert "ACK_REQUIRED" not in codes


def test_broker_readiness_codes(store):
    exposure = {"positions": 0, "pending_orders": 0}
    missing = broker_status(USER, lambda user_id: {**ready_facts(), "keys": None})
    assert "API_MISSING" in live_readiness(missing, exposure, True)
    no_api_key = broker_status(USER, lambda user_id: {**ready_facts(), "openalgo_api_key": False})
    assert "API_MISSING" in live_readiness(no_api_key, exposure, True)
    for override in ({"auth": None}, {"revoked": True}, {"session_current": False}):
        expired = broker_status(USER, lambda user_id, o=override: {**ready_facts(), **o})
        assert "AUTH_EXPIRED" in live_readiness(expired, exposure, True)
    ready = broker_status(USER, ready_facts)
    assert live_readiness(ready, exposure, True) == UNVERIFIED


def test_open_exposure_blocks_switching(store):
    exe, market = open_position(store)
    _, codes, _ = request_mode(
        store, USER, 1, "LIVE", acknowledged=True, actor=USER, reader=ready_facts
    )
    assert "OPEN_EXPOSURE" in codes
    force_mode(store, "LIVE")
    mode, codes, changed = request_mode(
        store, USER, 1, "PAPER", acknowledged=False, actor=USER, reader=ready_facts
    )
    assert codes == ["OPEN_EXPOSURE"] and not changed and mode["mode"] == "LIVE"
    # A pending exit intent is exposure as well.
    exe.admit(buy_intent(intent_id="close", side="SELL"))
    at = NOW + timedelta(seconds=1)
    assert store.open_exposure(USER, at) == {"positions": 1, "pending_orders": 1}
    assert request_mode(
        store, USER, 1, "PAPER", acknowledged=False, actor=USER, reader=ready_facts, now=at
    )[1] == ["OPEN_EXPOSURE"]
    # An intent past its expiry can no longer fill, so it is not exposure.
    assert store.open_exposure(USER, NOW + timedelta(hours=1))["pending_orders"] == 0
    assert exe.process(NOW + timedelta(seconds=2))[0]["status"] == "FILLED"
    assert store.open_exposure(USER, at) == {"positions": 0, "pending_orders": 0}
    mode, codes, changed = request_mode(
        store, USER, 1, "PAPER", acknowledged=False, actor=USER, reader=ready_facts
    )
    assert codes == [] and changed and mode["mode"] == "PAPER" and mode["revision"] == 2


def test_paper_request_is_idempotent_and_changes_are_audited(store):
    for _ in range(2):
        mode, codes, changed = request_mode(
            store, USER, 1, "PAPER", acknowledged=False, actor=USER, reader=ready_facts
        )
        assert codes == [] and not changed and mode["revision"] == 1
    assert not [e for e in store.events(USER) if e["kind"].startswith("mode_")]

    force_mode(store, "LIVE")
    mode, codes, changed = request_mode(
        store, USER, 1, "PAPER", acknowledged=False, actor="operator", reader=ready_facts
    )
    assert changed and mode["mode"] == "PAPER" and mode["revision"] == 2
    entry = mode["history"][-1]
    assert entry["previous"] == "LIVE" and entry["new"] == "PAPER"
    assert entry["actor"] == "operator" and entry["revision"] == 2 and entry["at"]
    event = next(e for e in store.events(USER) if e["kind"] == "mode_changed")["payload"]
    assert event["previous"] == "LIVE" and event["new"] == "PAPER" and event["actor"] == "operator"
    assert event["exposure"] == {"positions": 0, "pending_orders": 0}
    assert event["readiness"]["adapter"] == "LIVE_ADAPTER_STUB"
    assert event["readiness"]["broker"]["api_key_configured"] is True
    assert_no_secret(json.dumps(store.events(USER)))


def test_stale_revision_is_refused(store):
    force_mode(store, "LIVE")
    request_mode(store, USER, 1, "PAPER", acknowledged=False, actor=USER, reader=ready_facts)
    with pytest.raises(StateConflict):
        request_mode(store, USER, 1, "PAPER", acknowledged=False, actor=USER, reader=ready_facts)
    with pytest.raises(StateConflict):
        request_mode(store, USER, 1, "LIVE", acknowledged=True, actor=USER, reader=ready_facts)
    assert store.trading_mode(USER)["revision"] == 2


# Broker status ---------------------------------------------------------------


def test_broker_status_is_masked(store, caplog):
    with caplog.at_level(logging.DEBUG):
        status = broker_status(USER, ready_facts)
    assert status == {
        "available": True,
        "code": None,
        "broker": "zerodha",
        "broker_name": "Zerodha",
        "auth_token_present": True,
        "feed_token_present": True,
        "revoked": False,
        "session_current": True,
        "api_key_configured": True,
        "api_secret_configured": True,
        "key_source": "saved",
        "openalgo_api_key_configured": True,
    }
    assert_no_secret(json.dumps(status), tails=True)
    assert_no_secret(caplog.text)


def test_default_reader_uses_openalgo_stores_without_decrypting(store, monkeypatch):
    import database.auth_db

    seed_auth_sources(monkeypatch)
    decrypt = Mock(side_effect=AssertionError("token decrypted"))
    monkeypatch.setattr(database.auth_db, "decrypt_token", decrypt)
    status = broker_status(USER)
    assert status["available"] and status["auth_token_present"] and status["session_current"]
    assert status["api_key_configured"] and status["key_source"] == "saved"
    seed_auth_sources(monkeypatch, revoked=True)
    assert broker_status(USER)["revoked"] and not broker_status(USER)["session_current"]
    seed_auth_sources(monkeypatch, current=False)
    assert not broker_status(USER)["session_current"]
    decrypt.assert_not_called()


def test_default_reader_against_the_auth_database(store):
    from database import auth_db

    auth_db.init_db()
    status = broker_status("nifty-phase5-no-such-user")
    assert status["available"] is True and status["broker"] is None
    assert not status["auth_token_present"] and not status["api_key_configured"]
    codes = live_readiness(status, {"positions": 0, "pending_orders": 0}, True)
    assert {"API_MISSING", "AUTH_EXPIRED", "LIVE_NOT_READY"} <= set(codes)


def test_broker_status_failure_is_generic_and_logs_type_only(store, caplog):
    def failing(user_id):
        raise RuntimeError(f"connect failed token={SECRET_TOKEN} key={SECRET_KEY}")

    with caplog.at_level(logging.DEBUG):
        status = broker_status(USER, failing)
    assert status["available"] is False and status["code"] == "BROKER_STATUS_UNAVAILABLE"
    assert not any(value is True for value in status.values())
    assert "RuntimeError" in caplog.text
    assert_no_secret(caplog.text)
    codes = live_readiness(status, {"positions": 0, "pending_orders": 0}, True)
    assert codes[:2] == ["BROKER_STATUS_UNAVAILABLE", "BROKER_UNREACHABLE"]
    assert "LIVE_NOT_READY" in codes
    _, codes, changed = request_mode(
        store, USER, 1, "LIVE", acknowledged=True, actor=USER, reader=failing
    )
    assert "BROKER_STATUS_UNAVAILABLE" in codes and not changed
    assert_no_secret(caplog.text + json.dumps(store.events(USER)))


# Executor guard --------------------------------------------------------------


def test_forced_live_mode_refuses_entries_without_transport(store):
    running(store)
    force_mode(store, "LIVE")
    exe = executor(store, config=StrategyConfig(latency_ms=1))
    with pytest.raises(OrderRefused) as refused:
        exe.admit(buy_intent())
    assert refused.value.reasons == ["LIVE_NOT_READY"]
    assert store.orders(USER, now=NOW) == []
    assert exe.entry_lock_reasons(NOW, exe.config)[0] == "LIVE_NOT_READY"


def test_mode_flip_at_the_admission_write_is_refused_under_the_lock(store, monkeypatch):
    running(store)
    exe = executor(store, config=StrategyConfig(latency_ms=1))
    original = NiftyStore.admit_order

    def flip_then_admit(self, user_id, order, **kwargs):
        force_mode(self, "LIVE")
        return original(self, user_id, order, **kwargs)

    monkeypatch.setattr(NiftyStore, "admit_order", flip_then_admit)
    with pytest.raises(OrderRefused) as refused:
        exe.admit(buy_intent())
    assert "LIVE_NOT_READY" in refused.value.reasons
    assert store.orders(USER, now=NOW) == []


def test_mode_flip_before_fill_rejects_the_paper_entry(store):
    running(store)
    exe = executor(store, config=StrategyConfig(latency_ms=1))
    exe.admit(buy_intent())
    force_mode(store, "LIVE")
    filled = exe.process(NOW + timedelta(seconds=1))[0]
    assert filled["status"] == "REJECTED" and filled["reason"] == "LIVE_NOT_READY"
    assert store.positions(USER) == []


def test_forced_live_mode_keeps_paper_exits_simulated(store):
    exe, market = open_position(store)
    force_mode(store, "LIVE")
    exe.admit(buy_intent(intent_id="close", side="SELL"))
    assert exe.process(NOW + timedelta(seconds=2))[0]["status"] == "FILLED"
    assert store.positions(USER) == [] and len(store.trades(USER)) == 1


# No order transmission -------------------------------------------------------

ORDER_MODULES = (
    "services.place_order_service",
    "services.place_smart_order_service",
    "services.place_options_order_service",
    "services.options_multiorder_service",
    "services.basket_order_service",
    "services.split_order_service",
    "services.modify_order_service",
    "services.cancel_order_service",
    "services.cancel_all_order_service",
    "services.close_position_service",
    "services.order_router_service",
    "services.pending_order_execution_service",
    "services.place_gtt_order_service",
    "services.modify_gtt_order_service",
    "services.cancel_gtt_order_service",
    "services.sandbox_service",
)
BROKER_ORDER_API = re.compile(r"^broker\.[^.]+\.api\.order_api$")
ORDER_CALLS = {
    "place_order",
    "place_smart_order",
    "place_order_with_auth",
    "place_order_api",
    "place_smartorder_api",
    "modify_order",
    "cancel_order",
    "cancel_all_orders",
    "close_all_positions",
    "basket_order",
    "split_order",
    "sandbox_place_order",
    "import_module",
    "__import__",
}
SCANNED = (
    "services/nifty_algo/paper_executor.py",
    "services/nifty_algo/runner.py",
    "services/nifty_algo/trading_mode.py",
    "services/nifty_algo/shadow.py",
    "services/nifty_algo/research.py",
    "services/nifty_algo/protection.py",
    "services/nifty_algo/risk_manager.py",
    "database/nifty_algo_db.py",
    "blueprints/nifty_algo.py",
)


def _forbidden_module(name):
    return (
        name in ORDER_MODULES
        or name == "sandbox"
        or name.startswith("sandbox.")
        or bool(BROKER_ORDER_API.match(name))
    )


def _order_violations(tree):
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "broker" or module.startswith(("broker.", "sandbox")) or any(
                _forbidden_module(f"{module}.{alias.name}") for alias in node.names
            ):
                found.append(module)
            if _forbidden_module(module):
                found.append(module)
        elif isinstance(node, ast.Import):
            found.extend(
                alias.name
                for alias in node.names
                if alias.name.startswith(("broker", "sandbox")) or _forbidden_module(alias.name)
            )
        elif isinstance(node, ast.Attribute) and node.attr in ORDER_CALLS:
            found.append(node.attr)
        elif isinstance(node, ast.Name) and node.id in ORDER_CALLS:
            found.append(node.id)
    return found


def test_order_paths_cannot_import_or_call_broker_order_apis():
    for path in SCANNED:
        tree = ast.parse(Path(path).read_text(encoding="utf-8"))
        assert _order_violations(tree) == [], path
    stub = ast.parse(inspect.getsource(LiveAdapterStub))
    imports = [
        node.module
        for node in ast.walk(stub)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    assert imports == ["paper_executor"]
    # Control: the scan does see each forbidden shape.
    for snippet in (
        "from services.place_order_service import place_order",
        "from services import place_order_service",
        "import broker.zerodha.api.order_api",
        "from broker.zerodha.api.order_api import place_order_api",
        "from sandbox.order_manager import OrderManager",
        "service.place_order_with_auth(x)",
        "importlib.import_module(name)",
    ):
        assert _order_violations(ast.parse(snippet)), snippet


class _OrderImportTrap(importlib.abc.MetaPathFinder):
    def __init__(self, spy):
        self.spy = spy

    def find_spec(self, name, path=None, target=None):
        if _forbidden_module(name):
            self.spy(name)
            raise ImportError(f"order module import blocked: {name}")
        return None


def _forbid_order_transport(monkeypatch):
    spy = Mock()
    monkeypatch.setattr(sys, "meta_path", [_OrderImportTrap(spy), *sys.meta_path])
    for name, module in list(sys.modules.items()):
        if module is None or not _forbidden_module(name):
            continue
        for attribute, value in list(vars(module).items()):
            if callable(value) and getattr(value, "__module__", None) == name:
                monkeypatch.setattr(module, attribute, spy)
    import httpx
    import requests

    monkeypatch.setattr(httpx.Client, "send", spy)
    monkeypatch.setattr(httpx.AsyncClient, "send", spy)
    monkeypatch.setattr(requests.Session, "send", spy)
    return spy


def test_order_transport_trap_detects_imports_and_calls(monkeypatch):
    import importlib

    import httpx

    spy = _forbid_order_transport(monkeypatch)
    module = sys.modules.get("services.place_order_service")
    if module is None:
        with pytest.raises(ImportError):
            importlib.import_module("services.place_order_service")
    else:
        patched = [value for value in vars(module).values() if value is spy]
        assert patched
        patched[0]()
    with pytest.raises(ImportError):
        sys.meta_path[0].find_spec("broker.zerodha.api.order_api")
    with httpx.Client() as http:
        http.send(None)
    assert spy.call_count == 3


def _protect(store, exe, market, at):
    market.stamp = at
    runner = NiftyRunner(store, USER, native=Mock(), executor=exe, clock=lambda: at)
    runner.protect(at)
    return runner


@pytest.mark.parametrize("forced", ["PAPER", "LIVE"])
def test_full_cycle_never_transmits_an_order(store, monkeypatch, forced):
    before = set(sys.modules)
    spy = _forbid_order_transport(monkeypatch)
    exe, market = open_position(store)
    assert store.trading_mode(USER)["mode"] == "PAPER"
    if forced == "LIVE":
        force_mode(store, "LIVE")
        with pytest.raises(OrderRefused) as refused:
            exe.admit(buy_intent(intent_id="i-2"))
        assert refused.value.reasons == ["LIVE_NOT_READY"]
    # The initial stop latches an exit through the runner, and the next tick fills it.
    market.bid, market.ask = "90", "90.5"
    runner = _protect(store, exe, market, NOW + timedelta(seconds=2))
    assert store.pending_orders(USER)[0]["side"] == "SELL"
    market.stamp = NOW + timedelta(seconds=3)
    runner.clock = lambda: market.stamp
    runner.protect(market.stamp)
    assert store.positions(USER) == []
    assert store.trades(USER)[0]["reason"] == "INITIAL_STOP"
    assert store.trading_mode(USER)["mode"] == forced
    spy.assert_not_called()
    assert not [name for name in set(sys.modules) - before if _forbidden_module(name)]


# API -------------------------------------------------------------------------


@pytest.fixture
def client(store, monkeypatch):
    import utils.session

    monkeypatch.setattr(utils.session, "is_session_valid", lambda: bool(session.get("user")))
    app = Flask(__name__)
    app.secret_key = "test-only-nifty-fixture-key"
    app.config["TESTING"] = True
    CSRFProtect(app)
    app.register_blueprint(nifty_algo_bp)
    initialize_nifty(app, store.engine)

    @app.get("/fixture-csrf")
    def csrf():
        return jsonify(token=generate_csrf())

    return app.test_client()


def _login(client):
    with client.session_transaction() as browser:
        browser["user"] = USER
    return {"X-CSRFToken": client.get("/fixture-csrf").json["token"]}


def test_mode_api_requires_a_session_and_csrf(client):
    headers = {"Accept": "application/json"}
    assert client.get("/api/nifty-algo/mode", headers=headers).status_code == 401
    headers["X-CSRFToken"] = client.get("/fixture-csrf").json["token"]
    body = {"mode": "PAPER", "revision": 1}
    assert client.post("/api/nifty-algo/mode", json=body, headers=headers).status_code == 401
    _login(client)
    response = client.post("/api/nifty-algo/mode", json=body)
    assert response.status_code == 400  # CSRF token missing.
    assert "data" not in (response.get_json(silent=True) or {})


def test_mode_api_get_reports_masked_status(client, monkeypatch, caplog):
    seed_auth_sources(monkeypatch)
    _login(client)
    with caplog.at_level(logging.DEBUG):
        response = client.get("/api/nifty-algo/mode")
        risk = client.get("/api/nifty-algo/risk")
    assert response.status_code == 200
    data = response.json["data"]
    assert data["mode"] == "PAPER" and data["revision"] == 1 and data["live_available"] is False
    assert data["readiness"] == [*UNVERIFIED, "ACK_REQUIRED"]
    assert data["broker"]["auth_token_present"] is True
    assert data["broker"]["api_key_configured"] is True
    assert data["exposure"] == {"positions": 0, "pending_orders": 0}
    risk_data = risk.json["data"]
    assert risk_data["mode"] == "PAPER_ONLY"
    assert {item["code"] for item in risk_data["readiness"]} >= {"STRICT_FILL_PROFILE"}
    assert risk_data["trading_mode"] == {
        "mode": "PAPER",
        "revision": 1,
        "live_available": False,
        "live_readiness": data["readiness"],
    }
    assert_no_secret(response.get_data(as_text=True))
    assert_no_secret(risk.get_data(as_text=True))
    assert_no_secret(caplog.text)


def test_mode_api_post(client, store, monkeypatch, caplog):
    seed_auth_sources(monkeypatch)
    headers = _login(client)
    post = lambda body: client.post("/api/nifty-algo/mode", json=body, headers=headers)  # noqa: E731
    for body in (
        {},
        {"mode": "LIVE"},
        {"mode": "DEMO", "revision": 1},
        {"mode": "PAPER", "revision": "1"},
        {"mode": "PAPER", "revision": 0},
        {"mode": "LIVE", "revision": 1, "acknowledged": "yes"},
        {"mode": "PAPER", "revision": 1, "extra": True},
    ):
        response = post(body)
        assert response.status_code == 400 and response.json["code"] == "MODE_REQUEST_INVALID"

    with caplog.at_level(logging.DEBUG):
        live = post({"mode": "LIVE", "revision": 1, "acknowledged": True})
        unacknowledged = post({"mode": "LIVE", "revision": 1})
    assert live.status_code == 409 and live.json["code"] == "MODE_CHANGE_REFUSED"
    assert live.json["reasons"] == UNVERIFIED and live.json["data"]["mode"] == "PAPER"
    assert unacknowledged.json["reasons"][-1] == "ACK_REQUIRED"
    assert_no_secret(live.get_data(as_text=True) + caplog.text + json.dumps(store.events(USER)))

    paper = post({"mode": "PAPER", "revision": 1})
    assert paper.status_code == 200
    assert paper.json["data"]["changed"] is False and paper.json["data"]["revision"] == 1

    force_mode(store, "LIVE")
    switched = post({"mode": "PAPER", "revision": 1})
    assert switched.json["data"]["changed"] is True and switched.json["data"]["revision"] == 2
    stale = post({"mode": "PAPER", "revision": 1})
    assert stale.status_code == 409 and stale.json["code"] == "REVISION_CONFLICT"
    assert client.get("/api/nifty-algo/mode").json["data"]["mode"] == "PAPER"


def test_risk_api_reports_calendar_approval_read_only(client, store, monkeypatch):
    from datetime import datetime

    from test.nifty_calendar_helpers import seed_approved_nfo_calendar

    seed_auth_sources(monkeypatch)
    _login(client)
    year = datetime.now(session_calendar.IST).year
    blocked = client.get("/api/nifty-algo/risk").json["data"]["calendar"]
    assert blocked == {"year": year, "status": "CALENDAR_UNAPPROVED", "approved_version_id": None}
    assert store.calendar_versions(USER) == []
    version = seed_approved_nfo_calendar(store, USER, year)
    approved = client.get("/api/nifty-algo/risk").json["data"]["calendar"]
    assert approved == {"year": year, "status": "APPROVED", "approved_version_id": version["id"]}
