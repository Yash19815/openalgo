"""Offline deterministic regression evidence, not exchange-data verification."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal as D
from unittest.mock import Mock

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from database.nifty_algo_db import NiftyConfiguration, NiftyState, NiftyStore
from services.nifty_algo.confidence import signal_strength, target_fraction
from services.nifty_algo.config import StrategyConfig
from services.nifty_algo.models import PCR
from services.nifty_algo.paper_executor import NiftyPaperExecutor, OrderRefused
from services.nifty_algo.protection import initial_protection, observe_bid
from services.nifty_algo.runner import NiftyRunner
from test.nifty_calendar_helpers import seed_nifty_calendar_dependencies
from test.test_nifty_algo_paper_executor import (
    IST,
    NOW,
    USER,
    FakeMarket,
    buy_intent,
    executor,
    instrument,
    running,
)
from test.test_nifty_algo_paper_executor import (
    store as feature_store,
)


@pytest.fixture
def store(request):
    value = request.getfixturevalue("feature_store")
    seed_nifty_calendar_dependencies(value, USER, NOW.astimezone(IST).year)
    return value


def confidence(score=50):
    return {"method": "five-indicator-v1", "score": score}


@pytest.mark.parametrize(
    "changes",
    [
        {"premium_stop": ".080001"},
        {"premium_stop": ".15"},
        {"target": ".30"},
        {"trailing": ".10"},
        {"target_min": ".09"},
        {"target_max": ".16"},
        {"trailing_candidates": []},
        {"trailing_candidates": [0, 2]},
        {"trailing_distance_points": 2},
        {"point_unit": "INDEX"},
        {"trailing_activation_points": 0},
        {"target_min": ".15", "target_max": ".10"},
    ],
)
def test_unsafe_or_ambiguous_config_rejected(changes):
    with pytest.raises(ValidationError):
        StrategyConfig(**changes)


def test_legacy_migration_keeps_history_pauses_and_is_idempotent(store):
    state = store.read(USER)
    legacy = dict(state["configuration"])
    for field in (
        "confidence_method",
        "target_min",
        "target_max",
        "trailing_candidates",
        "trailing_distance_points",
        "trailing_activation_points",
        "point_unit",
        "pcr_expiry",
        "pcr_max_skew_seconds",
        "brokerage",
        "transaction_rate",
        "gst_rate",
        "stt_sell_rate",
        "stamp_buy_rate",
        "sebi_rate",
    ):
        legacy.pop(field, None)
    legacy.update(strategy_version="1.0.0", premium_stop="0.15", target="0.3", trailing="0.1")
    with store.sessions.begin() as db:
        row = db.get(NiftyState, USER)
        row.configuration, row.configuration_id, row.state = legacy, "legacy-identity", "RUNNING"
        db.get(NiftyConfiguration, (USER, 1)).configuration = legacy
    migrated = NiftyStore(store.engine).read(USER)
    assert migrated["state"] == "PAUSED"
    assert migrated["configuration"]["premium_stop"] == "0.08"
    assert migrated["configuration"]["trailing_distance_points"] == "1.5"
    assert migrated["revision"] == 2
    assert store.read(USER) == migrated
    with store.sessions() as db:
        revisions = list(
            db.scalars(
                select(NiftyConfiguration)
                .where(NiftyConfiguration.user_id == USER)
                .order_by(NiftyConfiguration.revision)
            )
        )
        assert len(revisions) == 2
        assert revisions[0].configuration["target"] == "0.3"
    assert store.events(USER)[0]["kind"] == "configuration_migration"


def test_confidence_hand_reference_and_normalized_contributions():
    config = StrategyConfig()
    snapshot = {
        "price": 100,
        "vwap": 100,
        "supertrend": {"atr": 2, "duration": 10, "distance": 6},
        "macd": {"cross_age": 0, "histogram": 2},
        "adx": {"adx": 100},
    }
    pcr = PCR(
        value=3, kind="OI", scope="OFFLINE_COMPLETE", source_time=NOW, coverage=1, verified=True
    )
    value = signal_strength(snapshot, {"supertrend": {"direction": 1}}, pcr, 1, config)
    assert value["score"] == 100
    assert value["calibrated_probability"] is False
    assert all(row["points"] == 20 for row in value["contributions"].values())
    assert value == signal_strength(snapshot, {"supertrend": {"direction": 1}}, pcr, 1, config)


def test_targets_monotonic_bounded_and_invalid_confidence_refused():
    config = StrategyConfig()
    targets = [target_fraction(D(n) / 10, config) for n in range(1001)]
    assert targets == sorted(targets)
    assert targets[0] == D(".10") and targets[500] == D(".125") and targets[-1] == D(".15")
    for invalid in (-1, 101, "NaN", "Infinity"):
        with pytest.raises(ValueError):
            target_fraction(invalid, config)


def test_decimal_stop_trail_activation_monotonic_and_tick_rounding():
    config = StrategyConfig()
    p = initial_protection(100, ".05", config, confidence())
    assert D(p["initial_stop"]) == 92
    assert D(p["target_price"]) == D("112.50")
    for bid in (99, 100, D("101.49")):
        p = observe_bid(p, 100, bid, ".05", config)
        assert not p["trailing_active"] and D(p["stop_price"]) == 92
    p = observe_bid(p, 100, D("101.5"), ".05", config)
    assert p["trailing_active"] and D(p["stop_price"]) == 100
    p = observe_bid(p, 100, 106, ".05", config)
    assert D(p["stop_price"]) == D("104.50")
    p = observe_bid(p, 100, 110, ".05", config)
    assert D(p["stop_price"]) == D("108.50")
    p = observe_bid(p, 100, 108, ".05", config)
    assert D(p["stop_price"]) == D("108.50") and p["exit_reason"] == "TRAILING_STOP"
    uneven = initial_protection(D("100.1"), ".2", config, confidence())
    assert D(uneven["initial_stop"]) == D("92.2")
    uneven = observe_bid(uneven, D("100.1"), D("106.2"), ".2", config)
    assert D(uneven["stop_price"]) == D("104.8")


def test_source_timestamp_and_displayed_quantity_are_mandatory(store):
    running(store)
    market = FakeMarket(size=1)
    exe = executor(store, market=market)
    with pytest.raises(OrderRefused, match="LIQUIDITY|DEPTH"):
        exe.admit(buy_intent())
    raw = FakeMarket().get_all_data("", "")
    raw["depth"].pop("ltt")
    raw["depth"]["timestamp"] = NOW.timestamp()
    exe.market_data = Mock(get_all_data=Mock(return_value=raw))
    assert exe._depth(instrument(), NOW) is None
    raw["depth"]["ltt"] = NOW.replace(tzinfo=None)
    assert exe._depth(instrument(), NOW) is None


def test_depth_disappearing_after_admission_cannot_invent_fill(store):
    running(store)
    market = FakeMarket()
    exe = executor(store, market=market)
    exe.admit(buy_intent())
    market.size = 1
    assert exe.process(NOW + timedelta(seconds=1)) == []
    assert store.positions(USER) == []
    assert store.pending_orders(USER)[0]["status"] == "PENDING"


def test_concurrent_distinct_intents_reserve_only_one_position(store):
    running(store)
    exe = executor(store)

    def admit(index):
        try:
            return exe.admit(buy_intent(f"distinct-{index}"))[1]
        except OrderRefused:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(admit, (1, 2)))
    assert results.count(True) == 1
    assert len(store.pending_orders(USER)) == 1


def test_quantity_override_cannot_bypass_risk(store):
    running(store)
    with pytest.raises(OrderRefused, match="POSITION_SIZE_ZERO"):
        executor(store).admit(buy_intent(quantity=10000))


def test_stop_from_fill_restart_pause_exit_gap_and_journal(store):
    running(store)
    config = StrategyConfig(slippage_ticks=0)
    market = FakeMarket()
    exe = executor(store, market=market, config=config)
    entry, _ = exe.admit(buy_intent())
    fills = exe.process(NOW + timedelta(seconds=1))
    assert fills[0]["status"] == "FILLED"
    held = store.positions(USER)[0]
    assert D(held["entry_price"]) == 165 and D(held["protection"]["initial_stop"]) == D("151.8")
    # Pause never disables protection, and active levels survive a new executor.
    state = store.read(USER)
    store.change(USER, state["revision"], action="pause")
    market.bid, market.ask, market.stamp = "172", "172.5", NOW + timedelta(seconds=2)
    exe.monitor_exits(market.stamp)
    assert D(store.positions(USER)[0]["protection"]["stop_price"]) == D("170.5")
    recovered = executor(store, market=market, config=config)
    recovered.reconcile(NOW + timedelta(seconds=3))
    # Stale data cannot move protection or trigger a price exit.
    market.bid, market.ask = "110", "110.5"
    recovered.monitor_exits(NOW + timedelta(seconds=10))
    assert D(store.positions(USER)[0]["protection"]["stop_price"]) == D("170.5")
    market.bid, market.ask, market.size, market.stamp = "80", "81", 1, NOW + timedelta(seconds=11)
    recovered.monitor_exits(market.stamp)
    assert len(store.pending_orders(USER)) == 1
    assert recovered.process(NOW + timedelta(seconds=12)) == []
    assert store.positions(USER)[0]["quantity"] == held["quantity"]
    market.size, market.stamp = 100, NOW + timedelta(seconds=13)
    closed = recovered.process(market.stamp)
    assert closed[0]["status"] == "FILLED" and D(closed[0]["price"]) == 80
    assert store.positions(USER) == []
    trade = store.trades(USER)[0]
    assert trade["reason"] == "TRAILING_STOP" and D(trade["net"]) < -D(held["quantity"]) * 8
    assert store.order_by_intent(USER, entry["intent_id"])["payload"]["confidence"]["score"] == 50


def test_pending_buy_canceled_by_kill_but_sell_remains_allowed(store):
    running(store)
    exe = executor(store)
    exe.admit(buy_intent())
    state = store.read(USER)
    store.change(USER, state["revision"], action="kill-switch")
    result = exe.process(NOW + timedelta(seconds=1))
    assert result[0]["status"] == "CANCELED"
    assert store.positions(USER) == []


def test_runner_lease_and_recovery_floor(store):
    running(store)
    exe = executor(store)
    runner = NiftyRunner(store, USER, executor=exe, clock=lambda: NOW)
    assert runner.protect(NOW) == []
    competitor = NiftyRunner(store, USER, executor=exe, clock=lambda: NOW)
    assert competitor.protect(NOW)["reason"] == "RUNNER_OWNED_ELSEWHERE"
    assert competitor.protect(NOW + timedelta(seconds=31)) == []
    assert runner.protect(NOW + timedelta(seconds=32))["reason"] == "RUNNER_OWNED_ELSEWHERE"


def test_entry_snapshot_does_not_follow_later_config(store):
    running(store)
    exe = executor(store, config=StrategyConfig(slippage_ticks=0))
    exe.admit(buy_intent())
    exe.process(NOW + timedelta(seconds=1))
    before = store.positions(USER)[0]["protection"]
    state = store.read(USER)
    store.change(
        USER,
        state["revision"],
        configuration=StrategyConfig(premium_stop=".04", target_min=".14", target_max=".15"),
    )
    restored = NiftyStore(store.engine).positions(USER)[0]["protection"]
    assert restored == before and D(restored["initial_stop"]) == D("151.8")


def test_partial_exit_allocates_entry_fees_and_preserves_trailing(store):
    running(store)
    market = FakeMarket()
    config = StrategyConfig(
        slippage_ticks=0, max_lots=1, lot_score_thresholds=(D("0"),)
    )
    exe = executor(store, config=config, market=market)
    exe.admit(buy_intent())
    exe.process(NOW + timedelta(seconds=1))
    market.bid, market.ask, market.stamp = "172", "172.5", NOW + timedelta(seconds=2)
    exe.monitor_exits(market.stamp)
    before = store.positions(USER)[0]["protection"]
    exe.admit(buy_intent("partial", side="SELL", quantity=10), now=market.stamp)
    exe.process(NOW + timedelta(seconds=3))
    after = store.positions(USER)[0]
    assert after["quantity"] == 15
    assert all(
        after["protection"][key] == before[key]
        for key in (
            "stop_price",
            "initial_stop",
            "highest_bid",
            "trailing_active",
            "configuration_id",
            "confidence",
        )
    )
    market.stamp = NOW + timedelta(seconds=4)  # A new observed depth snapshot.
    exe.admit(buy_intent("remainder", side="SELL"), now=market.stamp)
    exe.process(NOW + timedelta(seconds=5))
    assert not store.positions(USER)
    trades = store.trades(USER)
    net = sum((D(t["net"]) for t in trades), D(0))
    assert D(store.account(USER, NOW)["equity"]) - 20000 == net


def test_expired_exit_latch_retries_after_restart_and_retains_exposure(store):
    running(store)
    market = FakeMarket()
    config = StrategyConfig(slippage_ticks=0, order_ttl_seconds=2)
    exe = executor(store, config=config, market=market)
    exe.admit(buy_intent())
    exe.process(NOW + timedelta(seconds=1))
    market.bid, market.ask, market.stamp, market.size = "90", "91", NOW + timedelta(seconds=2), 1
    exe.monitor_exits(market.stamp)
    old_id = store.pending_orders(USER)[0]["order_id"]
    restored = executor(store, config=config, market=market)
    restored.reconcile(NOW + timedelta(seconds=5))
    market.stamp, market.size = NOW + timedelta(seconds=6), 100
    restored.monitor_exits(market.stamp)
    assert store.pending_orders(USER)[0]["order_id"] != old_id
    assert store.positions(USER)[0]["exit_state"] == "EXITING"
    restored.process(NOW + timedelta(seconds=7))
    assert not store.positions(USER) and store.trades(USER)[0]["reason"] == "INITIAL_STOP"


@pytest.mark.parametrize(("ask", "status"), [("160", "FILLED"), ("200", "REJECTED")])
def test_nondefault_tick_slippage_and_fill_risk_budget(store, ask, status):
    running(store)
    market = FakeMarket()
    exe = executor(store, market=market)
    contract = instrument().model_copy(update={"tick_size": D(".2")})
    exe.admit(buy_intent(instrument=contract))
    market.ask = ask
    market.bid = str(D(ask) - D("0.2"))
    market.ltp = str(D(ask) - D("0.1"))
    result = exe.process(NOW + timedelta(seconds=1))
    # A changed entry fill cannot exceed its reserved risk or capital.
    assert result[0]["status"] == status
    if status == "FILLED":
        assert D(result[0]["price"]) == D("160.2")
    else:
        assert not store.positions(USER)


def test_config_change_between_risk_check_and_write_is_refused(store, monkeypatch):
    running(store)
    exe = executor(store)
    original = store.admit_order

    def race(user_id, order):
        state = store.read(USER)
        store.change(USER, state["revision"], action="pause")
        return original(user_id, order)

    monkeypatch.setattr(store, "admit_order", race)
    with pytest.raises(OrderRefused, match="ENTRIES_DISABLED"):
        exe.admit(buy_intent())
    assert not store.pending_orders(USER)


def test_incompatible_saved_config_pauses_instead_of_using_legacy_values(store):
    running(store)
    with store.sessions.begin() as db:
        state = db.get(NiftyState, USER)
        state.configuration = {
            **state.configuration,
            "strategy_version": "unknown",
            "premium_stop": ".15",
        }
    state = store.read(USER)
    assert state["state"] == "PAUSED"
    assert state["configuration"]["strategy_version"] == "unknown"
    assert store.events(USER)[0]["kind"] == "configuration_incompatible"


def test_legacy_exposure_gets_emergency_protection_without_guessed_target(store):
    from database.nifty_algo_db import NiftyProtection

    running(store)
    exe = executor(store, config=StrategyConfig(slippage_ticks=0))
    exe.admit(buy_intent())
    exe.process(NOW + timedelta(seconds=1))
    with store.sessions.begin() as db:
        db.delete(db.get(NiftyProtection, (USER, instrument().token)))
    result = exe.reconcile(NOW + timedelta(seconds=2))
    assert result["reasons"] == ["LEGACY_PROTECTION_REQUIRES_REVIEW"]
    p = store.positions(USER)[0]["protection"]
    assert p["confidence"] is None and p["target_price"] is None
    assert D(p["initial_stop"]) == D("151.8") and not store.account(USER, NOW)["reconciled"]


def test_depth_only_observation_can_fill_without_using_ltp(store):
    running(store)
    raw = FakeMarket().get_all_data("", "")
    raw.pop("ltp")
    index = FakeMarket().get_all_data("NIFTY", "NSE_INDEX")
    exe = executor(
        store,
        market=Mock(
            get_all_data=Mock(
                side_effect=lambda symbol, exchange: index
                if exchange == "NSE_INDEX"
                else raw
            )
        ),
    )
    exe.admit(buy_intent())
    assert exe.process(NOW + timedelta(seconds=1))[0]["status"] == "FILLED"


def test_target_rounding_stays_inside_bounds_for_nondefault_ticks():
    config = StrategyConfig()
    for score in range(101):
        p = initial_protection("100.2", ".2", config, confidence(score))
        assert D(".10") <= D(p["target_fraction"]) <= D(".15")
        assert D(p["target_price"]) % D(".2") == 0


@pytest.mark.parametrize(
    ("trigger", "reason"),
    [
        ("hold", "MAX_HOLD"),
        ("technical", "TECHNICAL_INVALIDATION"),
        ("session", "SESSION_EXIT"),
        ("operator", "OPERATOR_CLOSE"),
    ],
)
def test_independent_nonprice_exit_triggers_remain_pending_until_filled(store, trigger, reason):
    running(store)
    market = FakeMarket()
    exe = executor(
        store, market=market, config=StrategyConfig(slippage_ticks=0, max_hold_minutes=1)
    )
    exe.admit(buy_intent())
    exe.process(NOW + timedelta(seconds=1))
    now = NOW + timedelta(seconds=62 if trigger == "hold" else 2)
    if trigger == "session":
        exe.session_reader = lambda *_: {
            "start_ms": (NOW - timedelta(hours=1)).timestamp() * 1000,
            "end_ms": (now + timedelta(minutes=1)).timestamp() * 1000,
        }
    exe.monitor_exits(
        now,
        technical_invalidations={instrument().token} if trigger == "technical" else None,
        operator_close=trigger == "operator",
    )
    assert store.positions(USER)[0]["exit_state"] == "EXITING"
    assert store.pending_orders(USER)[0]["payload"]["exit_reason"] == reason
    market.stamp = now + timedelta(seconds=1)
    assert exe.process(market.stamp)[0]["status"] == "FILLED"
    assert not store.positions(USER)


def test_realized_gap_loss_locks_day_and_survives_restart(store):
    running(store)
    market = FakeMarket()
    exe = executor(store, market=market, config=StrategyConfig(slippage_ticks=0))
    exe.admit(buy_intent())
    exe.process(NOW + timedelta(seconds=1))
    market.bid, market.ask, market.stamp = "20", "21", NOW + timedelta(seconds=2)
    exe.monitor_exits(market.stamp)
    exe.process(NOW + timedelta(seconds=3))
    restored = NiftyStore(store.engine)
    assert restored.read(USER)["daily_locked"]
    assert restored.read(USER)["state"] == "PAUSED"
    restored.account(USER, NOW + timedelta(days=1))
    assert not restored.read(USER)["daily_locked"]


def test_fee_allocation_conserves_money_across_uneven_partial_exits(store):
    running(store)
    market = FakeMarket()
    config = StrategyConfig(max_lots=1, lot_score_thresholds=(D("0"),))
    exe = executor(store, market=market, config=config)
    exe.admit(buy_intent())
    exe.process(NOW + timedelta(seconds=1))
    market.bid, market.ask = "101", "101.5"
    for step, quantity in enumerate((1, 1, 23)):
        market.stamp = NOW + timedelta(seconds=2 + step * 2)
        exe.admit(buy_intent(f"partial-{step}", side="SELL", quantity=quantity), now=market.stamp)
        assert exe.process(market.stamp + timedelta(seconds=1))[0]["status"] == "FILLED"
    assert not store.positions(USER)
    net = sum((D(t["net"]) for t in store.trades(USER)), D(0))
    assert D(store.account(USER, NOW)["equity"]) == 20000 + net


def test_performance_aggregates_entire_ledger_beyond_journal_page(store):
    from database.nifty_algo_db import NiftyTrade

    store.ensure_user(USER)
    with store.sessions.begin() as db:
        for index in range(205):
            db.add(
                NiftyTrade(
                    user_id=USER,
                    entry_order_id=f"e-{index}",
                    exit_order_id=f"x-{index}",
                    symbol="OFFLINE_CE",
                    quantity=1,
                    entry_price=100,
                    exit_price=101,
                    gross=1,
                    fees=D(".1"),
                    net=D(".9"),
                    reason="OFFLINE_FIXTURE",
                    opened_at=NOW,
                    closed_at=NOW,
                )
            )
    assert len(store.trades(USER)) == 200
    result = store.performance(USER)
    assert result["trades"] == 205 and result["wins"] == 205
    assert D(result["realized_total"]) == D("184.5")
    assert result["equity_basis"] == "BOOK_COST_NOT_MARK_TO_MARKET"


def test_late_heartbeat_cannot_shorten_runner_lease(store):
    assert store.claim_runner(USER, "owner", NOW)
    assert store.claim_runner(USER, "owner", NOW + timedelta(seconds=20))
    assert store.claim_runner(USER, "owner", NOW + timedelta(seconds=1))
    assert not store.claim_runner(USER, "competitor", NOW + timedelta(seconds=31))
    assert store.claim_runner(USER, "competitor", NOW + timedelta(seconds=51))


def test_incompatible_config_keeps_feed_recovery_available(store, monkeypatch):
    running(store)
    exe = executor(store)
    with store.sessions.begin() as db:
        state = db.get(NiftyState, USER)
        state.configuration = {**state.configuration, "strategy_version": "unknown"}
    runner = NiftyRunner(store, USER, executor=exe, clock=lambda: NOW)
    feed = Mock(return_value="offline-only")
    monkeypatch.setattr(runner, "_native_feed", feed)
    assert runner.evaluate(NOW) is None
    feed.assert_called_once()
    assert not runner.ready and runner.last_issue == "CONFIGURATION_INCOMPATIBLE"
    assert not store.pending_orders(USER)


def test_closed_runner_cannot_reclaim_a_lease(store):
    running(store)
    runner = NiftyRunner(store, USER, executor=executor(store), clock=lambda: NOW)
    runner.protect(NOW)
    runner.close()
    assert not runner._lease(NOW + timedelta(seconds=1))
    assert not store.runner_status(USER, NOW)["operational"]


def test_legacy_peak_cannot_restart_at_a_looser_stop(store):
    from database.nifty_algo_db import NiftyProtection

    running(store)
    exe = executor(store, config=StrategyConfig(slippage_ticks=0))
    exe.admit(buy_intent())
    exe.process(NOW + timedelta(seconds=1))
    store.mark_highest(USER, instrument().token, D("180"))
    with store.sessions.begin() as db:
        db.delete(db.get(NiftyProtection, (USER, instrument().token)))
    exe.reconcile(NOW + timedelta(seconds=2))
    protection = store.positions(USER)[0]["protection"]
    assert D(protection["initial_stop"]) == D("151.8")
    assert D(protection["stop_price"]) >= 110
    assert protection["highest_bid"] is None
    assert protection["exit_reason"] == "LEGACY_PROTECTION_REVIEW"


@pytest.mark.parametrize(
    ("fault", "reason"),
    [
        ("cash", "ACCOUNT_POSITION_BALANCE_MISMATCH"),
        ("quantity", "ENTRY_QUANTITY_NOT_RECONCILED"),
        ("entry", "POSITION_ENTRY_FILL_MISMATCH"),
    ],
)
def test_recovery_checks_cash_positions_and_confirmed_fills(store, fault, reason):
    from database.nifty_algo_db import NiftyAccount, NiftyOrder, NiftyPosition

    running(store)
    exe = executor(store, config=StrategyConfig(slippage_ticks=0))
    entry, _ = exe.admit(buy_intent())
    exe.process(NOW + timedelta(seconds=1))
    with store.sessions.begin() as db:
        if fault == "cash":
            db.get(NiftyAccount, USER).available += 1
        elif fault == "quantity":
            db.get(NiftyPosition, (USER, instrument().token)).quantity += 25
        else:
            db.get(NiftyOrder, (USER, entry["order_id"])).status = "REJECTED"
    report = exe.reconcile(NOW + timedelta(seconds=2))
    assert reason in report["reasons"] and not report["account"]["reconciled"]
    assert store.read(USER)["state"] == "PAUSED"
    if fault != "cash":
        with pytest.raises(OrderRefused, match="UNCOVERED"):
            exe.admit(buy_intent("unsafe-exit", side="SELL"), now=NOW + timedelta(seconds=3))
