"""Phase 4: hypothetical shadow positions, primary mirrors and research observations."""

import ast
import inspect
import sys
import textwrap
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask, session
from sqlalchemy import func, select
from sqlalchemy import inspect as schema
from sqlalchemy.exc import IntegrityError

from blueprints.nifty_algo import initialize_nifty, nifty_algo_bp
from database.engine_factory import create_db_engine
from database.nifty_algo_db import (
    NiftyAccount,
    NiftyCooldown,
    NiftyMonth,
    NiftyOpportunity,
    NiftyShadowPosition,
    NiftyStore,
)
from services.nifty_algo import calendar as session_calendar
from services.nifty_algo.config import StrategyConfig
from services.nifty_algo.paper_executor import NiftyPaperExecutor, _charges
from services.nifty_algo.protection import modeled_exit_net
from services.nifty_algo.research import opportunity_from_decision, opportunity_id
from services.nifty_algo.runner import NiftyRunner
from services.nifty_algo.shadow import ShadowBook
from test.nifty_calendar_helpers import seed_approved_nfo_calendar
from test.test_nifty_algo_paper_executor import (
    NOW,
    USER,
    FakeMarket,
    _paper_test_config,
    buy_intent,
    executor,
    instrument,
    running,
)
from test.test_nifty_algo_phase1 import Phase1MarketCalendar

D = Decimal
CONFIG = _paper_test_config(
    StrategyConfig(latency_ms=1, profit_lock_floor_net=D("380"))
)


def ist(hour, minute, day=19):
    """2026-11 IST wall time as a UTC instant. NOW is Thursday 19th, 10:30 IST."""
    return datetime(2026, 11, day, hour, minute, tzinfo=session_calendar.IST).astimezone(UTC)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(session_calendar, "_legacy_calendar", lambda: Phase1MarketCalendar())
    engine = create_db_engine(f"sqlite:///{tmp_path / 'phase4.db'}")
    value = NiftyStore(engine, calendar_blob_dir=tmp_path / "calendar_blobs")
    value.initialize()
    value.ensure_user(USER)
    yield value
    engine.dispose()


def prepare(store, holidays=()):
    if holidays:
        seed_approved_nfo_calendar(store, USER, 2026, entries=holidays)
    executor(store, config=StrategyConfig(latency_ms=1))


def signal(at, decision_id="s-1", side="CE"):
    return {
        "decision_id": decision_id,
        "eligible": True,
        "side": side,
        "config_id": CONFIG.version_id,
        "timestamp": at.isoformat(),
        "analysis_token": "future",
        "confidence": {"method": CONFIG.confidence_method, "score": 50},
        "snapshot": {"end": at.isoformat(), "price": 24000.0, "supertrend": {"atr": 10.0}},
    }


def book(store, market):
    quotes = NiftyPaperExecutor(store, USER, CONFIG, market_data=market)
    return ShadowBook(store, USER, quote=quotes._depth)


def quote(market, at, bid):
    market.bid, market.ask, market.stamp = str(bid), str(D(str(bid)) + D("0.5")), at


def open_shadow(store, at, decision_id="s-1", market=None):
    market = market or FakeMarket(stamp=at)
    shadows = book(store, market)
    row, reasons = shadows.open_independent(signal(at, decision_id), at, CONFIG, [instrument()])
    return shadows, market, row, reasons


def active_rows(store):
    with store.sessions() as db:
        return db.scalar(
            select(func.count())
            .select_from(NiftyShadowPosition)
            .where(NiftyShadowPosition.active_slot.is_not(None))
        )


def test_tables_are_additive(store):
    tables = set(schema(store.engine).get_table_names())
    assert {
        "nifty_algo_shadow_position",
        "nifty_algo_shadow_event",
        "nifty_algo_opportunity",
        "nifty_algo_account",
    } <= tables


@pytest.mark.parametrize("at", [ist(9, 15), ist(9, 20), ist(14, 44)])
def test_independent_shadow_opens_inside_its_own_window(store, at):
    prepare(store)
    store.account(USER, at)
    account = store.account(USER, at)
    _, _, row, reasons = open_shadow(store, at)
    assert reasons == [] and row["kind"] == "INDEPENDENT" and row["active"]
    assert row["additive"] is True and row["status"] == "ACTIVE"
    assert row["quantity"] == 25 and D(row["entry_price"]) == D("165.05")
    assert D(row["entry_fees"]) == _charges("BUY", D("165.05"), 25, CONFIG)
    # The hypothetical ledger never touches the primary account, orders or months.
    assert store.account(USER, at) == account
    assert store.orders(USER, now=at) == []
    with store.sessions() as db:
        assert db.scalar(select(func.count()).select_from(NiftyMonth)) == 0
    assert store.shadow_ledger(USER)["equity"] == "20000"


@pytest.mark.parametrize(
    ("at", "expected"),
    [
        (ist(9, 10), {"SESSION_CLOSED", "SHADOW_ENTRY_WINDOW"}),
        (ist(14, 45), {"SHADOW_ENTRY_WINDOW"}),
        (ist(15, 0), {"SHADOW_ENTRY_WINDOW"}),
        (ist(10, 0, day=21), {"WEEKEND"}),
    ],
)
def test_independent_shadow_refused_outside_window(store, at, expected):
    prepare(store)
    _, _, row, reasons = open_shadow(store, at)
    assert row is None and set(reasons) == expected
    assert active_rows(store) == 0


def test_independent_shadow_refused_on_holiday(store):
    prepare(store, holidays=[{"date": "2026-11-20", "weekday": "Friday", "name": "Fixture"}])
    _, _, row, reasons = open_shadow(store, ist(9, 30, day=20))
    assert row is None and reasons == ["HOLIDAY"]


def test_independent_shadow_refused_during_cooldown_but_not_monthly_lock(store):
    prepare(store)
    with store.sessions.begin() as db:
        db.add(
            NiftyCooldown(
                user_id=USER,
                loss_session="2026-11-18",
                cooldown_session="2026-11-19",
                loss_event_id=0,
                entry_order_id="offline-entry",
                realized_net=D("-1"),
                created_at=NOW,
                updated_at=NOW,
            )
        )
    _, _, row, reasons = open_shadow(store, ist(9, 20))
    assert row is None and reasons == ["COOLDOWN_ACTIVE"]
    # The store refuses authoritatively under the user lock as well.
    record = {
        "decision_id": "direct",
        "token": "token-ce",
        "symbol": "TEST_CONTRACT",
        "instrument": instrument().model_dump(mode="json"),
        "quantity": 25,
        "entry_price": "100",
        "entry_fees": "1",
        "protection": {},
        "opened_at": ist(9, 20),
    }
    assert store.open_shadow(USER, record, CONFIG) == (None, ["COOLDOWN_ACTIVE"])
    assert store.open_shadow(USER, {**record, "opened_at": ist(14, 45)}, CONFIG)[1] == [
        "SHADOW_ENTRY_WINDOW",
        "COOLDOWN_ACTIVE",
    ]
    with store.sessions.begin() as db:
        db.query(NiftyCooldown).delete()
        db.add(
            NiftyMonth(
                user_id=USER,
                month="2026-11",
                realized_net=D("-5000"),
                loss_locked_at=NOW,
                lock_detail={},
                milestone_report_ids=[],
                created_at=NOW,
                updated_at=NOW,
            )
        )
    assert "MONTHLY_LOSS_LOCK" in store.entry_locks(USER, ist(9, 20), CONFIG)
    _, _, row, reasons = open_shadow(store, ist(9, 20))
    assert reasons == [] and row["active"]


def test_single_active_shadow_row_is_enforced(store):
    prepare(store)
    _, _, first, _ = open_shadow(store, ist(9, 20))
    again = open_shadow(store, ist(9, 20))[2]
    assert again["id"] == first["id"]
    _, _, row, reasons = open_shadow(store, ist(9, 25), "s-2")
    assert row is None and reasons == ["SHADOW_ACTIVE"]
    assert active_rows(store) == 1
    # The database itself rejects a second active row, mirrors included.
    with pytest.raises(IntegrityError):
        with store.sessions.begin() as db:
            db.add(
                NiftyShadowPosition(
                    user_id=USER,
                    shadow_key="mirror:forged",
                    kind="MIRROR",
                    status="ACTIVE",
                    active_slot=1,
                    additive=0,
                    token="token-ce",
                    symbol="TEST_CONTRACT",
                    instrument={},
                    quantity=25,
                    entry_price=D("100"),
                    entry_fees=D("0"),
                    protection={},
                    session="2026-11-19",
                    opened_at=NOW,
                    updated_at=NOW,
                )
            )
    assert active_rows(store) == 1


def test_primary_fill_preempts_and_mirror_follows_primary(store):
    prepare(store)
    shadows, market, independent, _ = open_shadow(store, ist(9, 20))
    quote(market, ist(9, 21), "166")
    shadows.monitor(ist(9, 21))
    running(store)
    primary_market = FakeMarket()
    exe = executor(store, market=primary_market, config=StrategyConfig(latency_ms=1))
    entry, _ = exe.admit(buy_intent())
    assert exe.process(NOW + timedelta(seconds=1))[0]["status"] == "FILLED"
    held = store.positions(USER)[0]

    mirror = shadows.sync_mirrors(NOW + timedelta(seconds=2))
    assert mirror["kind"] == "MIRROR" and mirror["active"] and mirror["additive"] is False
    assert mirror["primary_entry_order_id"] == entry["order_id"]
    assert mirror["entry_price"] == held["entry_price"] and mirror["quantity"] == 25
    preempted = next(row for row in store.shadow_status(USER)["positions"] if row["id"] == independent["id"])
    assert preempted["status"] == "PREEMPTED_BY_ACTUAL_MIRROR" and not preempted["active"]
    assert preempted["exit_reason"] == "PREEMPTED_BY_ACTUAL_MIRROR"
    assert preempted["primary_entry_order_id"] == entry["order_id"]
    assert preempted["valuation"] == "LAST_BID"
    assert D(preempted["net"]) == modeled_exit_net(
        D("165.05"), 25, D("166"), D(preempted["entry_fees"]), D("0.05"), CONFIG, _charges
    )
    assert active_rows(store) == 1
    # Repeat ticks and a restarted store never duplicate the mirror.
    assert shadows.sync_mirrors(NOW + timedelta(seconds=3)) is None
    restarted = NiftyStore(create_db_engine(str(store.engine.url)))
    try:
        assert restarted.sync_shadow_mirrors(USER, NOW + timedelta(seconds=3)) is None
        assert restarted.active_shadow(USER)["id"] == mirror["id"]
    finally:
        restarted.engine.dispose()
    assert shadows.open_independent(
        signal(NOW + timedelta(seconds=3), "s-3"), NOW + timedelta(seconds=3), CONFIG, [instrument()]
    ) == (None, ["SHADOW_ACTIVE"])
    assert shadows.monitor(NOW + timedelta(seconds=3))["status"] == "ACTIVE"

    primary_market.bid, primary_market.ask = "110", "110.5"
    exe.admit(buy_intent(intent_id="close", side="SELL"))
    assert exe.process(NOW + timedelta(seconds=4))[0]["status"] == "FILLED"
    assert shadows.sync_mirrors(NOW + timedelta(seconds=5)) is None
    trade = store.trades(USER)[0]
    closed = next(row for row in store.shadow_status(USER)["positions"] if row["id"] == mirror["id"])
    assert closed["status"] == "CLOSED" and not closed["active"]
    assert closed["valuation"] == "PRIMARY_JOURNAL" and closed["exit_reason"] == trade["reason"]
    assert D(closed["net"]) == D(trade["net"]) and closed["exit_price"] == trade["exit_price"]
    assert active_rows(store) == 0
    # Mirror P&L is reported but never added to the hypothetical ledger.
    ledger = store.shadow_ledger(USER)
    assert ledger["mirror_additive"] is False
    assert D(ledger["mirror_realized_net"]) == D(trade["net"])
    assert D(ledger["realized_net"]) == D(preempted["net"])
    assert D(ledger["equity"]) == D("20000") + D(preempted["net"])


def test_shadow_initial_stop_exit(store):
    prepare(store)
    shadows, market, row, _ = open_shadow(store, ist(9, 20))
    quote(market, ist(9, 21), "92")
    closed = shadows.monitor(ist(9, 21))
    assert closed["status"] == "CLOSED" and closed["exit_reason"] == "INITIAL_STOP"
    assert closed["valuation"] == "DEPTH_MODEL" and D(closed["exit_price"]) == D("91.95")
    assert D(closed["net"]) == modeled_exit_net(
        D("165.05"), 25, D("92"), D(row["entry_fees"]), D("0.05"), CONFIG, _charges
    )
    assert D(store.shadow_ledger(USER)["realized_net"]) == D(closed["net"]) < 0


def test_shadow_trailing_stop_exit_is_monotone(store):
    prepare(store)
    shadows, market, _, _ = open_shadow(store, ist(9, 20))
    quote(market, ist(9, 21), "172")
    trailing = shadows.monitor(ist(9, 21))
    assert trailing["protection"]["trailing_active"] is True
    assert D(trailing["protection"]["stop_price"]) == D("170.5")
    quote(market, ist(9, 22), "171")
    assert D(shadows.monitor(ist(9, 22))["protection"]["stop_price"]) == D("170.5")
    quote(market, ist(9, 23), "170.5")
    closed = shadows.monitor(ist(9, 23))
    assert closed["exit_reason"] == "TRAILING_STOP" and D(closed["exit_price"]) == D("170.45")


def test_shadow_profit_lock_floor_exit(store):
    prepare(store)
    shadows, market, _, _ = open_shadow(store, ist(9, 20))
    quote(market, ist(9, 21), "183.5")
    locked = shadows.monitor(ist(9, 21))["protection"]
    assert locked["profit_lock_active"] is True
    assert locked["stop_price"] == locked["profit_floor_stop"]
    assert D(locked["profit_floor_stop"]) > D(locked["trailing_stop"])
    quote(market, ist(9, 22), "183")
    assert shadows.monitor(ist(9, 22))["protection"]["stop_price"] == locked["stop_price"]
    quote(market, ist(9, 23), str(D(locked["profit_floor_stop"]) - D("0.05")))
    closed = shadows.monitor(ist(9, 23))
    assert closed["exit_reason"] == "PROFIT_LOCK_STOP" and closed["status"] == "CLOSED"
    kinds = [event["kind"] for event in store.shadow_status(USER)["events"]]
    assert kinds.count("PROFIT_LOCK_ACTIVATED") == 1
    # Shadow protection events never enter the primary activity log.
    assert "PROFIT_LOCK_ACTIVATED" not in [event["kind"] for event in store.events(USER)]


def test_shadow_mandatory_exits(store):
    prepare(store)
    shadows, market, _, _ = open_shadow(store, ist(9, 20))
    quote(market, ist(10, 5), "166")
    assert shadows.monitor(ist(10, 5))["exit_reason"] == "MAX_HOLD"

    shadows, market, _, _ = open_shadow(store, ist(14, 40), "late")
    quote(market, ist(15, 10), "166")
    closed = shadows.monitor(ist(15, 10))
    assert closed["exit_reason"] == "SESSION_EXIT" and closed["valuation"] == "DEPTH_MODEL"


def test_shadow_without_fillable_bid_ends_at_last_bid_after_close(store):
    prepare(store)
    shadows, market, _, _ = open_shadow(store, ist(14, 40))
    quote(market, ist(14, 41), "166")
    shadows.monitor(ist(14, 41))
    market.size = 10  # Displayed bid cannot absorb the hypothetical quantity.
    quote(market, ist(15, 10), "167")
    latched = shadows.monitor(ist(15, 10))
    assert latched["active"] and latched["protection"]["exit_reason"] == "SESSION_EXIT"
    closed = shadows.monitor(ist(15, 31))
    assert not closed["active"] and closed["valuation"] == "LAST_BID"
    assert D(closed["exit_price"]) == D("166.95")


def test_shadow_state_recovers_after_restart(store):
    prepare(store)
    shadows, market, row, _ = open_shadow(store, ist(9, 20))
    quote(market, ist(9, 21), "172")
    shadows.monitor(ist(9, 21))
    engine = create_db_engine(str(store.engine.url))
    try:
        restored = NiftyStore(engine)
        active = restored.active_shadow(USER)
        assert active["id"] == row["id"] and D(active["protection"]["stop_price"]) == D("170.5")
        recovered = book(restored, market)
        assert recovered.open_independent(signal(ist(9, 20)), ist(9, 20), CONFIG, [instrument()])[
            0
        ]["id"] == row["id"]
        assert recovered.open_independent(
            signal(ist(9, 25), "s-2"), ist(9, 25), CONFIG, [instrument()]
        ) == (None, ["SHADOW_ACTIVE"])
        quote(market, ist(9, 22), "171")
        assert D(recovered.monitor(ist(9, 22))["protection"]["stop_price"]) == D("170.5")
        quote(market, ist(9, 23), "170.4")
        assert recovered.monitor(ist(9, 23))["exit_reason"] == "TRAILING_STOP"
        assert active_rows(restored) == 0
    finally:
        engine.dispose()


# Research observations ------------------------------------------------------


def observe(store, at, price, token="future", now=None):
    return store.observe_opportunities(
        USER, {"token": token, "price": price, "at": at.isoformat()}, now or at
    )


def record(store, at, side="CE", price=24000.0):
    opportunity = opportunity_from_decision({**signal(at, side=side), "snapshot": {
        "end": at.isoformat(), "price": price, "supertrend": {"atr": 10.0}
    }}, CONFIG)
    return store.record_opportunity(USER, opportunity, at)


def only(store):
    rows = store.opportunities(USER)
    assert len(rows) == 1
    return rows[0]


def test_opportunity_id_is_stable_and_scoped():
    end = ist(10, 0)
    same = end.astimezone(session_calendar.IST).isoformat()
    assert opportunity_id(end, "CE", "config") == opportunity_id(same, "CE", "config")
    assert opportunity_id(end, "CE", "config") != opportunity_id(end, "PE", "config")
    assert opportunity_id(end, "CE", "config") != opportunity_id(end, "CE", "other")
    assert opportunity_id(end, "CE", "config") != opportunity_id(
        end + timedelta(minutes=5), "CE", "config"
    )
    with pytest.raises(ValueError):
        opportunity_id(end.replace(tzinfo=None), "CE", "config")
    assert opportunity_from_decision({**signal(end), "eligible": False}, CONFIG) is None


def test_opportunity_upsert_is_idempotent(store):
    first, created = record(store, ist(10, 0))
    observe(store, ist(10, 5), 24004)
    again, created_again = record(store, ist(10, 0))
    assert created is True and created_again is False
    assert again["opportunity_id"] == first["opportunity_id"]
    assert len(again["steps"]) == 1  # The later upsert never resets observation.
    with store.sessions() as db:
        assert db.scalar(select(func.count()).select_from(NiftyOpportunity)) == 1


@pytest.mark.parametrize(
    ("side", "price", "outcome"),
    [("CE", 24010, "THRESHOLD_FAVORABLE"), ("PE", 24010, "THRESHOLD_ADVERSE")],
)
def test_observation_stops_at_first_terminal_threshold(store, side, price, outcome):
    record(store, ist(10, 0), side)
    observe(store, ist(10, 5), 24004)
    assert only(store)["status"] == "OBSERVING"
    observe(store, ist(10, 10), price)
    observe(store, ist(10, 15), 23900)
    row = only(store)
    assert row["status"] == "CLOSED" and row["outcome"] == outcome
    assert len(row["steps"]) == 2 and row["closed_at"] == ist(10, 10).isoformat()
    observe(store, ist(10, 5), 24004, token="other-future")
    assert only(store) == row


def test_observation_stops_at_45_minutes(store):
    record(store, ist(10, 0))
    for minute in range(5, 50, 5):
        observe(store, ist(10, 0) + timedelta(minutes=minute), 24001)
    row = only(store)
    assert row["outcome"] == "WINDOW_45M" and len(row["steps"]) == 9
    assert row["closed_at"] == ist(10, 45).isoformat()

    # Without a further candle the scheduler tick stops it at the deadline.
    record(store, ist(11, 0))
    assert store.expire_opportunities(USER, ist(11, 44)) == []
    stopped = store.expire_opportunities(USER, ist(11, 45) + timedelta(seconds=1))
    assert [item["outcome"] for item in stopped] == ["WINDOW_45M"]
    assert stopped[0]["closed_at"] == ist(11, 45).isoformat()


def test_observation_stops_at_1510(store):
    record(store, ist(14, 40))
    row = only(store)
    assert row["deadline"] == ist(15, 10).isoformat() and row["deadline_reason"] == "SESSION_CUTOFF"
    observe(store, ist(14, 45), 24002)
    assert store.expire_opportunities(USER, ist(15, 9)) == []
    assert store.expire_opportunities(USER, ist(15, 10))[0]["outcome"] == "SESSION_CUTOFF"
    observe(store, ist(15, 15), 24050)
    row = only(store)
    assert row["outcome"] == "SESSION_CUTOFF" and len(row["steps"]) == 1
    assert opportunity_from_decision(signal(ist(15, 10)), CONFIG) is None


def test_runner_tick_runs_research_without_admitting_orders(store, monkeypatch):
    prepare(store)
    started = ist(9, 59)
    native = Mock()
    native.get_market.return_value = {"spot": None}

    def decision(at, price, eligible):
        return {
            **signal(at, decision_id=f"d-{at.isoformat()}"),
            "eligible": eligible,
            "checks": [
                {"rule": "R-WARMUP", "state": "PASS"},
                {"rule": "R-FRESH", "state": "PASS"},
            ],
            "reasons": [],
            "snapshot": {"end": at.isoformat(), "price": price, "supertrend": {"atr": 10.0}},
        }

    decisions = {ist(10, 0): decision(ist(10, 0), 24000, True)}
    decisions[ist(10, 5)] = decision(ist(10, 5), 24011, False)
    admit = Mock(side_effect=AssertionError("research must never admit"))
    runner = NiftyRunner(
        store,
        USER,
        native=native,
        executor=executor(store, config=StrategyConfig(latency_ms=1)),
        assessment=lambda config, now: decisions[now],
        clock=lambda: started,
    )
    monkeypatch.setattr(runner.executor, "admit", admit)
    runner.protect(started)
    assert runner.evaluate(ist(10, 0))["eligible"]
    assert only(store)["status"] == "OBSERVING"
    runner.evaluate(ist(10, 5))
    assert only(store)["outcome"] == "THRESHOLD_FAVORABLE"
    # A failed hypothetical contract lookup never disturbs the primary path.
    assert store.active_shadow(USER) is None
    admit.assert_not_called()
    assert store.orders(USER, now=ist(10, 5)) == []


# Safety --------------------------------------------------------------------

FORBIDDEN_MODULES = (
    "broker",
    "sandbox",
    "services.place_order",
    "services.place_smart_order",
    "services.sandbox",
    "services.order",
)
FORBIDDEN_CALLS = {
    "admit",
    "admit_order",
    "fill",
    "submit",
    "process",
    "place_order",
    "place_smart_order",
    "monitor_exits",
    "_record_month_net",
    "_schedule_cooldown",
    "mark_reconciled",
    "block_reconciliation",
    "record_event",
}
PRIMARY_TABLES = {
    "NiftyOrder",
    "NiftyTrade",
    "NiftyAccount",
    "NiftyMonth",
    "NiftyPosition",
    "NiftyCooldown",
    "NiftyProtection",
    "NiftyEvent",
}


def _violations(tree):
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = {alias.name for alias in node.names}
            if module.startswith(FORBIDDEN_MODULES):
                found.append(module)
            if module.endswith("paper_executor") and names - {"_charges"}:
                found.append(f"{module}:{sorted(names)}")
        elif isinstance(node, ast.Import):
            found.extend(a.name for a in node.names if a.name.startswith(FORBIDDEN_MODULES))
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_CALLS:
            found.append(node.attr)
        elif isinstance(node, ast.Attribute) and node.attr == "delete":
            found.append("delete")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in PRIMARY_TABLES
        ):
            found.append(node.func.id)
    return found


def test_shadow_and_research_code_cannot_reach_order_apis():
    for path in ("services/nifty_algo/shadow.py", "services/nifty_algo/research.py"):
        tree = ast.parse(Path(path).read_text(encoding="utf-8"))
        assert _violations(tree) == [], path
    methods = [
        NiftyStore.cooldown_reasons,
        NiftyStore.open_shadow,
        NiftyStore._close_shadow,
        NiftyStore.observe_shadow,
        NiftyStore.sync_shadow_mirrors,
        NiftyStore._close_mirror,
        NiftyStore.shadow_ledger,
        NiftyStore.shadow_status,
        NiftyStore.record_opportunity,
        NiftyStore.observe_opportunities,
        NiftyStore.expire_opportunities,
        NiftyStore.opportunities,
        NiftyRunner._research,
        NiftyRunner._shadow_entry,
        NiftyRunner._shadow_upkeep,
    ]
    for method in methods:
        tree = ast.parse(textwrap.dedent(inspect.getsource(method)))
        assert _violations(tree) == [], method.__qualname__


def test_shadow_and_research_runtime_never_call_order_services(store, monkeypatch):
    prepare(store)
    spy = Mock(side_effect=AssertionError("order boundary reached"))
    for module, name in (
        ("services.place_order_service", "place_order"),
        ("services.place_smart_order_service", "place_smart_order"),
        ("services.sandbox_service", "sandbox_place_order"),
    ):
        monkeypatch.setitem(sys.modules, module, SimpleNamespace(**{name: spy}))
    for owner, name in (
        (NiftyPaperExecutor, "admit"),
        (NiftyPaperExecutor, "process"),
        (NiftyStore, "admit_order"),
        (NiftyStore, "fill"),
    ):
        monkeypatch.setattr(owner, name, spy)
    accounts_before = _primary_counts(store)
    shadows, market, _, _ = open_shadow(store, ist(9, 20))
    quote(market, ist(9, 21), "172")
    shadows.monitor(ist(9, 21))
    quote(market, ist(9, 22), "170.5")
    shadows.monitor(ist(9, 22))
    shadows.sync_mirrors(ist(9, 22))
    record(store, ist(10, 0))
    observe(store, ist(10, 5), 24011)
    store.expire_opportunities(USER, ist(11, 0))
    spy.assert_not_called()
    assert _primary_counts(store) == accounts_before


def _primary_counts(store):
    from database.nifty_algo_db import NiftyEvent, NiftyOrder, NiftyTrade

    with store.sessions() as db:
        account = db.get(NiftyAccount, USER)
        return (
            None if account is None else (str(account.equity), str(account.available)),
            *(
                db.scalar(select(func.count()).select_from(table))
                for table in (NiftyOrder, NiftyTrade, NiftyMonth, NiftyEvent)
            ),
        )


# Read-only API ---------------------------------------------------------------


@pytest.fixture
def client(store, monkeypatch):
    import utils.session

    monkeypatch.setattr(utils.session, "is_session_valid", lambda: bool(session.get("user")))
    app = Flask(__name__)
    app.secret_key = "test-only-nifty-fixture-key"
    app.config["TESTING"] = True
    app.register_blueprint(nifty_algo_bp)
    initialize_nifty(app, store.engine)
    return app.test_client()


def test_shadow_and_research_endpoints_are_authenticated_and_read_only(store, client):
    headers = {"Accept": "application/json"}
    assert client.get("/api/nifty-algo/shadow", headers=headers).status_code == 401
    assert client.get("/api/nifty-algo/research/opportunities", headers=headers).status_code == 401
    prepare(store)
    open_shadow(store, ist(9, 20))
    record(store, ist(10, 0))
    with client.session_transaction() as browser:
        browser["user"] = USER
    shadow = client.get("/api/nifty-algo/shadow").json["data"]
    assert shadow["mode"] == "HYPOTHETICAL" and shadow["active"]["kind"] == "INDEPENDENT"
    assert shadow["ledger"]["mirror_additive"] is False
    research = client.get("/api/nifty-algo/research/opportunities").json["data"]
    assert research[0]["research_only"] is True and research[0]["status"] == "OBSERVING"
    assert client.post("/api/nifty-algo/shadow").status_code == 405
