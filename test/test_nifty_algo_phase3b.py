"""Phase 3b: loss cooldown, monthly loss lock and monthly profit-target lock."""

import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import delete, inspect

from database.engine_factory import create_db_engine
from database.nifty_algo_db import NiftyAccount, NiftyCooldown, NiftyMonth, NiftyStore
from services.nifty_algo import calendar as session_calendar
from services.nifty_algo.config import StrategyConfig
from services.nifty_algo.paper_executor import OrderRefused
from test.nifty_calendar_helpers import seed_approved_nfo_calendar
from test.test_nifty_algo_paper_executor import (
    NOW,
    USER,
    FakeMarket,
    buy_intent,
    executor,
    running,
)
from test.test_nifty_algo_phase1 import Phase1MarketCalendar, admit_direct

D = Decimal
YEAR = 2026
# NOW is Thursday 2026-11-19 10:30 IST. Every probe below is 10:30 IST.
FRIDAY = datetime(2026, 11, 20, 5, 0, tzinfo=UTC)
MONDAY = datetime(2026, 11, 23, 5, 0, tzinfo=UTC)
TUESDAY = datetime(2026, 11, 24, 5, 0, tzinfo=UTC)
NEXT_MONTH = datetime(2026, 12, 1, 5, 0, tzinfo=UTC)
FRIDAY_HOLIDAY = [{"date": "2026-11-20", "weekday": "Friday", "name": "Fixture holiday"}]


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(session_calendar, "_legacy_calendar", lambda: Phase1MarketCalendar())
    engine = create_db_engine(f"sqlite:///{tmp_path / 'phase3b.db'}")
    value = NiftyStore(engine, calendar_blob_dir=tmp_path / "calendar_blobs")
    value.initialize()
    value.ensure_user(USER)
    yield value
    engine.dispose()


def round_trip(store, exit_bid, config=None, *, holidays=()):
    """One primary BUY and a full SELL on the Thursday session."""
    if holidays:
        seed_approved_nfo_calendar(store, USER, YEAR, entries=holidays)
    running(store)
    market = FakeMarket()
    exe = executor(store, market=market, config=config or StrategyConfig(latency_ms=1))
    exe.admit(buy_intent())
    assert exe.process(NOW + timedelta(seconds=1))[0]["status"] == "FILLED"
    market.bid, market.ask = exit_bid, str(D(exit_bid) + D("0.5"))
    exe.admit(buy_intent(intent_id="close", side="SELL"))
    assert exe.process(NOW + timedelta(seconds=2))[0]["status"] == "FILLED"
    assert not store.positions(USER)
    return exe


def state_config(store):
    return StrategyConfig.model_validate(store.read(USER)["configuration"])


def refused_on(store, day, intent_id, config=None):
    store.account(USER, day)  # IST day rollover of the daily counters.
    with pytest.raises(OrderRefused) as refused:
        admit_direct(store, config or state_config(store), intent_id, day)
    return refused.value.reasons


def admitted_on(store, day, intent_id, config=None):
    store.account(USER, day)
    order, created = admit_direct(store, config or state_config(store), intent_id, day)
    assert created and order["intent_id"] == intent_id
    return order


def kinds(store):
    return [event["kind"] for event in store.events(USER)]


def realized_net(store):
    return sum((D(trade["net"]) for trade in store.trades(USER)), D("0"))


def test_tables_are_additive(store):
    tables = set(inspect(store.engine).get_table_names())
    assert {"nifty_algo_cooldown", "nifty_algo_month", "nifty_algo_account"} <= tables


def test_loss_blocks_next_eligible_session_across_holiday(store, monkeypatch):
    spy = Mock(side_effect=AssertionError("paper orders must not be transmitted"))
    monkeypatch.setitem(
        sys.modules, "services.place_order_service", SimpleNamespace(place_order=spy)
    )
    monkeypatch.setitem(
        sys.modules,
        "services.place_smart_order_service",
        SimpleNamespace(place_smart_order=spy),
    )
    exe = round_trip(store, "160", holidays=FRIDAY_HOLIDAY)
    assert realized_net(store) < 0
    # Friday is an approved holiday and the weekend follows: Monday is the cooldown.
    locks = store.risk_locks(USER, NOW + timedelta(seconds=3))
    assert locks["cooldown"] == {
        "active": False,
        "loss_session": "2026-11-19",
        "cooldown_session": "2026-11-23",
    }
    assert {"SESSION_LOSS_COOLDOWN", "COOLDOWN_SCHEDULED"} <= set(kinds(store))

    assert "COOLDOWN_ACTIVE" in refused_on(store, FRIDAY, "holiday-buy")
    assert refused_on(store, MONDAY, "monday-buy") == ["COOLDOWN_ACTIVE"]

    # The executor refuses before sizing, so no intent is ever created.
    store.record_decision(
        USER,
        {
            "decision_id": "d-monday",
            "eligible": True,
            "side": "CE",
            "config_id": exe.config.version_id,
            "timestamp": MONDAY.isoformat(),
            "confidence": {"method": exe.config.confidence_method, "score": 50},
        },
    )
    with pytest.raises(OrderRefused) as refused:
        exe.admit(buy_intent(intent_id="monday-exe", decision_id="d-monday"), now=MONDAY)
    assert refused.value.reasons == ["COOLDOWN_ACTIVE"]
    assert store.order_by_intent(USER, "monday-exe") is None
    assert store.risk_locks(USER, MONDAY)["cooldown"]["active"] is True

    admitted_on(store, TUESDAY, "tuesday-buy")
    spy.assert_not_called()


def test_profit_session_schedules_no_cooldown(store):
    round_trip(store, "175")
    assert realized_net(store) > 0
    assert store.risk_locks(USER, FRIDAY)["cooldown"]["loss_session"] is None
    assert "SESSION_LOSS_COOLDOWN" not in kinds(store)
    admitted_on(store, FRIDAY, "friday-buy")


def test_cooldown_survives_restart(store):
    round_trip(store, "160", holidays=FRIDAY_HOLIDAY)
    engine = create_db_engine(str(store.engine.url))
    try:
        restored = NiftyStore(engine)
        assert refused_on(restored, MONDAY, "restart-monday") == ["COOLDOWN_ACTIVE"]
        admitted_on(restored, TUESDAY, "restart-tuesday")
    finally:
        engine.dispose()


def test_revised_calendar_recomputes_future_cooldown(store):
    round_trip(store, "160")
    assert store.risk_locks(USER, NOW)["cooldown"]["cooldown_session"] == "2026-11-20"
    data = b"date,name\n2026-11-20,Fixture holiday\n"
    draft = store.create_calendar_draft(
        USER,
        year=YEAR,
        segment="NFO",
        source_filename="revision.csv",
        sha256=sha256(data).hexdigest(),
        uploader=USER,
        entries=FRIDAY_HOLIDAY,
        issues=[],
        data=data,
        extension="csv",
    )
    store.approve_calendar(
        USER,
        draft["id"],
        confirmed_year=YEAR,
        confirmed_segment="NFO",
        actor=USER,
        now=NOW + timedelta(seconds=3),
    )
    assert store.risk_locks(USER, NOW)["cooldown"]["cooldown_session"] == "2026-11-23"
    assert "COOLDOWN_RECOMPUTED" in kinds(store)
    assert refused_on(store, MONDAY, "revised-monday") == ["COOLDOWN_ACTIVE"]


def test_unresolved_cooldown_fails_closed_until_calendar_resolves_it(store):
    running(store)
    executor(store)
    with store.sessions.begin() as db:
        db.add(
            NiftyCooldown(
                user_id=USER,
                loss_session="2026-11-18",
                cooldown_session=None,
                loss_event_id=0,
                entry_order_id="offline-entry",
                realized_net=D("-1"),
                created_at=NOW,
                updated_at=NOW,
            )
        )
    assert refused_on(store, NOW, "unresolved") == ["COOLDOWN_UNRESOLVED"]
    assert store.resolve_cooldowns(USER, NOW)[0]["cooldown_session"] == "2026-11-19"
    assert refused_on(store, NOW, "resolved") == ["COOLDOWN_ACTIVE"]


def test_monthly_loss_lock_blocks_until_next_month(store):
    round_trip(store, "160", StrategyConfig(latency_ms=1, monthly_loss_limit=D("50")))
    assert realized_net(store) <= D("-50")
    month = store.risk_locks(USER, NOW)["month"]
    assert month["month"] == "2026-11" and month["loss_locked_at"] is not None
    assert D(month["realized_net"]) == realized_net(store)
    assert "MONTHLY_LOSS_LOCKED" in kinds(store)
    # Tuesday is past the one-session cooldown; only the monthly lock remains.
    assert refused_on(store, TUESDAY, "same-month") == ["MONTHLY_LOSS_LOCK"]
    admitted_on(store, NEXT_MONTH, "next-month")


def test_monthly_loss_lock_not_reached_below_limit(store):
    round_trip(store, "160")  # Default 2000 rupee limit; a ~110 rupee loss.
    assert store.risk_locks(USER, NOW)["month"]["loss_locked_at"] is None
    admitted_on(store, TUESDAY, "below-limit")


def test_monthly_profit_lock_latches_through_target_edit(store):
    round_trip(store, "175", StrategyConfig(latency_ms=1, monthly_profit_target=D("100")))
    assert realized_net(store) >= D("100")
    assert store.risk_locks(USER, NOW)["month"]["profit_locked_at"] is not None
    assert "MONTHLY_PROFIT_LOCKED" in kinds(store)
    assert refused_on(store, FRIDAY, "goal-reached") == ["MONTHLY_PROFIT_LOCK"]

    previous = state_config(store)
    raised = StrategyConfig.model_validate(
        {**previous.model_dump(mode="json"), "monthly_profit_target": "100000"}
    )
    store.change(USER, store.read(USER)["revision"], configuration=raised)
    audit = next(
        event
        for event in store.events(USER)
        if event["kind"] == "monthly_profit_target_changed"
    )
    assert audit["payload"]["previous"] == "100"
    assert audit["payload"]["new"] == "100000"
    assert audit["payload"]["at"]
    running(store)
    # Raising the target never clears a latched lock.
    assert refused_on(store, FRIDAY, "after-edit", raised) == ["MONTHLY_PROFIT_LOCK"]
    admitted_on(store, NEXT_MONTH, "next-month-goal", raised)


def test_monthly_profit_lock_disabled_when_unset_and_latches_when_lowered(store):
    round_trip(store, "175")
    assert state_config(store).monthly_profit_target is None
    assert store.risk_locks(USER, NOW)["month"]["profit_locked_at"] is None
    admitted_on(store, FRIDAY, "goal-disabled")
    lowered = state_config(store).model_copy(update={"monthly_profit_target": D("100")})
    assert store.entry_locks(USER, FRIDAY, lowered) == ["MONTHLY_PROFIT_LOCK"]
    assert store.risk_locks(USER, FRIDAY)["month"]["profit_locked_at"] is not None


def test_month_rollover_resets_counters_and_keeps_equity(store):
    round_trip(store, "160", StrategyConfig(latency_ms=1, monthly_loss_limit=D("50")))
    equity = store.account(USER, NOW + timedelta(seconds=3))["equity"]
    november = store.risk_locks(USER, NOW)["month"]
    assert store.entry_locks(USER, NEXT_MONTH, state_config(store)) == []
    december = store.risk_locks(USER, NEXT_MONTH)["month"]
    assert december["month"] == "2026-12"
    assert D(december["realized_net"]) == 0
    assert december["loss_locked_at"] is None and december["profit_locked_at"] is None
    # The prior month keeps its history, and equity never resets on a new month.
    assert store.risk_locks(USER, NOW)["month"] == november
    assert D(store.account(USER, NEXT_MONTH)["equity"]) == D(equity) < D("20000")


def test_equity_reset_does_not_clear_monthly_tracking(store):
    round_trip(store, "160", StrategyConfig(latency_ms=1, monthly_loss_limit=D("50")))
    before = store.risk_locks(USER, NOW)["month"]
    with store.sessions.begin() as db:
        db.execute(delete(NiftyAccount).where(NiftyAccount.user_id == USER))
    assert D(store.account(USER, TUESDAY)["equity"]) == D("20000")
    with store.sessions() as db:
        row = db.get(NiftyMonth, (USER, "2026-11"))
        assert row is not None and row.loss_locked_at is not None
    assert store.risk_locks(USER, NOW)["month"] == before
    assert refused_on(store, TUESDAY, "after-equity-reset") == ["MONTHLY_LOSS_LOCK"]
