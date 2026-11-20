from datetime import timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from database.engine_factory import create_db_engine
from database.nifty_algo_db import NiftyEvent, NiftyStore
from services.nifty_algo.config import StrategyConfig
from services.nifty_algo.models import Quote
from services.nifty_algo.protection import (
    early_booking_exit,
    initial_protection,
    modeled_exit_net,
    momentum_weakening,
    observe_bid,
    profit_floor_stop,
)
from test.nifty_calendar_helpers import seed_nifty_calendar_dependencies
from test.test_nifty_algo_paper_executor import (
    IST,
    NOW,
    USER,
    FakeMarket,
    buy_intent,
    running,
)
from test.test_nifty_algo_paper_executor import (
    executor as make_executor,
)

D = Decimal


def no_charges(side, price, quantity, config):
    return D("0")


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "phase2.db"
    engine = create_db_engine(f"sqlite:///{path}")
    value = NiftyStore(engine)
    value.initialize()
    value.ensure_user(USER)
    seed_nifty_calendar_dependencies(value, USER, NOW.astimezone(IST).year)
    yield value
    engine.dispose()


def test_profit_floor_is_exact_at_tick_boundary_for_one_to_three_lots():
    config = StrategyConfig(slippage_ticks=2)
    for lots in (1, 2, 3):
        quantity = lots * 25
        stop = profit_floor_stop(
            D("100"), quantity, D("3"), D("350"), D("0.05"), config, no_charges
        )

        assert stop % D("0.05") == 0
        assert (
            modeled_exit_net(
                D("100"), quantity, stop, D("3"), D("0.05"), config, no_charges
            )
            >= D("350")
        )
        assert (
            modeled_exit_net(
                D("100"), quantity, stop - D("0.05"), D("3"), D("0.05"), config, no_charges
            )
            < D("350")
        )


def test_profit_floor_accounts_for_slippage():
    config = StrategyConfig(slippage_ticks=2)
    slipped = profit_floor_stop(
        D("100"), 25, D("0"), D("350"), D("0.05"), config, no_charges
    )
    config_without_slippage = config.model_copy(update={"slippage_ticks": 0})
    plain = profit_floor_stop(
        D("100"), 25, D("0"), D("350"), D("0.05"), config_without_slippage, no_charges
    )
    assert slipped == plain + D("0.10")


@pytest.mark.parametrize("fraction", [D("0"), D("-0.01"), D("1.01")])
def test_early_booking_retrace_fraction_has_testable_bounds(fraction):
    with pytest.raises(ValidationError):
        StrategyConfig(early_booking_retrace_fraction=fraction)


def _protection():
    return {
        "initial_stop": "90",
        "stop_price": "90",
        "highest_bid": None,
        "trailing_active": False,
        "trailing_stop": None,
        "profit_lock_active": False,
        "profit_floor_stop": None,
        "profit_lock_activation": None,
        "estimated_net": None,
        "target_price": "200",
        "exit_reason": None,
    }


def test_profit_lock_activates_on_exact_threshold_once_and_floor_binds_then_trail_overtakes():
    config = StrategyConfig(
        profit_lock_floor_net=D("375"),
        slippage_ticks=0,
        trailing_distance_points=D("1.5"),
    )
    locked = observe_bid(
        _protection(),
        D("100"),
        D("116"),
        D("0.05"),
        config,
        quantity=25,
        entry_fees=D("0"),
        charges=no_charges,
        bid_size=50,
        source_time="2026-01-01T10:30:00+05:30",
    )
    assert D(locked["estimated_net"]) == D("400")
    assert locked["profit_lock_active"] is True
    assert D(locked["profit_floor_stop"]) == D("115")
    assert D(locked["trailing_stop"]) == D("114.5")
    assert D(locked["stop_price"]) == D("115")
    assert locked["new_events"][0]["kind"] == "PROFIT_LOCK_ACTIVATED"

    repeated = observe_bid(
        locked,
        D("100"),
        D("118"),
        D("0.05"),
        config,
        quantity=25,
        entry_fees=D("0"),
        charges=no_charges,
        bid_size=50,
        source_time="2026-01-01T10:30:01+05:30",
    )
    assert D(repeated["profit_floor_stop"]) == D("115")
    assert D(repeated["trailing_stop"]) == D("116.5")
    assert D(repeated["stop_price"]) == D("116.5")
    assert repeated["new_events"] == []


def test_profit_lock_does_not_activate_below_exact_threshold_and_unrepresentable_floor_is_reported():
    config = StrategyConfig(slippage_ticks=0)
    below = observe_bid(
        _protection(),
        D("100"),
        D("115.9996"),
        D("0.05"),
        config,
        quantity=25,
        entry_fees=D("0"),
        charges=no_charges,
    )
    assert D(below["estimated_net"]) == D("399.99")
    assert below["profit_lock_active"] is False
    assert below["new_events"] == []

    narrow_config = StrategyConfig(
        profit_lock_floor_net=D("399.999"),
        slippage_ticks=0,
    )
    unrepresentable = observe_bid(
        _protection(),
        D("100"),
        D("500"),
        D("0.05"),
        narrow_config,
        quantity=1,
        entry_fees=D("0"),
        charges=no_charges,
    )
    assert unrepresentable["profit_lock_active"] is False
    assert unrepresentable["exit_reason"] == "PROFIT_FLOOR_UNREPRESENTABLE"
    assert unrepresentable["new_events"][0]["kind"] == "PROFIT_FLOOR_UNREPRESENTABLE"


def test_floor_exit_reason_is_binding_and_stop_never_decreases():
    config = StrategyConfig(
        profit_lock_floor_net=D("375"),
        slippage_ticks=0,
    )
    locked = observe_bid(
        _protection(), D("100"), D("116"), D("0.05"), config,
        quantity=25, entry_fees=D("0"), charges=no_charges,
    )
    dropped = observe_bid(
        locked, D("100"), D("114.9"), D("0.05"), config,
        quantity=25, entry_fees=D("0"), charges=no_charges,
    )
    assert D(dropped["stop_price"]) == D("115")
    assert dropped["exit_reason"] == "PROFIT_LOCK_STOP"

    lower_bid = observe_bid(
        dropped, D("100"), D("105"), D("0.05"), config,
        quantity=25, entry_fees=D("0"), charges=no_charges,
    )
    assert D(lower_bid["stop_price"]) == D("115")
    assert lower_bid["exit_reason"] == "PROFIT_LOCK_STOP"


def test_partial_exit_keeps_a_persisted_floor_stop_monotonic():
    config = StrategyConfig(
        profit_lock_floor_net=D("375"),
        slippage_ticks=0,
    )
    locked = observe_bid(
        _protection(), D("100"), D("116"), D("0.05"), config,
        quantity=25, entry_fees=D("0"), charges=no_charges,
    )
    partial_exit = observe_bid(
        locked, D("100"), D("115.5"), D("0.05"), config,
        quantity=10, entry_fees=D("0"), charges=no_charges,
    )
    assert D(partial_exit["stop_price"]) == D("115")
    assert D(partial_exit["profit_floor_stop"]) == D("115")


def test_early_booking_requires_net_retrace_momentum_and_no_active_lock():
    config = StrategyConfig(
        early_booking_retrace_fraction=D("0.30"),
        slippage_ticks=0,
    )
    protection = {**_protection(), "highest_bid": "120"}
    kwargs = {
        "quantity": 25,
        "entry_fees": D("0"),
        "charges": no_charges,
        "momentum_weak": True,
    }
    assert (
        early_booking_exit(protection, D("100"), D("113"), D("0.05"), config, **kwargs)
        == "EARLY_PROFIT_BOOKING"
    )
    assert (
        early_booking_exit(protection, D("100"), D("111.9996"), D("0.05"), config, **kwargs)
        is None
    )
    assert (
        early_booking_exit(
            protection, D("100"), D("113"), D("0.05"), config,
            **{**kwargs, "momentum_weak": False},
        )
        is None
    )
    assert (
        early_booking_exit(
            {**protection, "profit_lock_active": True},
            D("100"),
            D("113"),
            D("0.05"),
            config,
            **kwargs,
        )
        is None
    )


def test_momentum_weakening_requires_completed_directional_momentum_and_price_change():
    previous = {"end": "2026-01-01T10:00:00+05:30", "price": 100, "macd": {"histogram": 2}}
    weaker = {"end": "2026-01-01T10:05:00+05:30", "price": 99, "macd": {"histogram": 1}}
    assert momentum_weakening(previous, weaker, 1) is True
    assert momentum_weakening(previous, weaker, -1) is False
    assert momentum_weakening(previous, {**weaker, "price": 101}, 1) is False
    assert momentum_weakening(previous, {**weaker, "end": None}, 1) is False
    assert momentum_weakening(previous, {}, 1) is False
    line_signal = {"end": weaker["end"], "price": 99, "macd": {"line": 1, "signal": 0}}
    prior_line_signal = {"end": previous["end"], "price": 100, "macd": {"line": 2, "signal": 0}}
    assert momentum_weakening(prior_line_signal, line_signal, 1) is True


def test_old_positional_observe_bid_calls_keep_trailing_behavior():
    config = StrategyConfig()
    protection = initial_protection(
        D("100"), D("0.05"), config, {"score": 50, "method": config.confidence_method}
    )
    observed = observe_bid(protection, D("100"), D("101.5"), D("0.05"), config)
    assert observed["trailing_active"] is True
    assert D(observed["trailing_stop"]) == D("100")
    assert D(observed["stop_price"]) == D("100")
    assert observed["profit_lock_active"] is False
    assert observed["new_events"] == []
    with pytest.raises(ValueError):
        observe_bid(protection, D("100"), D("0"), D("0.05"), config)


def test_mandatory_stop_is_not_gated_by_discretionary_booking():
    config = StrategyConfig(slippage_ticks=0)
    protection = {**_protection(), "highest_bid": "100"}
    stopped = observe_bid(
        protection, D("100"), D("89"), D("0.05"), config,
        quantity=25, entry_fees=D("0"), charges=no_charges,
    )
    assert stopped["exit_reason"] == "INITIAL_STOP"
    assert early_booking_exit(
        protection,
        D("100"),
        D("89"),
        D("0.05"),
        config,
        quantity=25,
        entry_fees=D("0"),
        charges=no_charges,
        momentum_weak=True,
    ) is None


def test_restarted_store_recovers_lock_emits_once_and_reports_realized_gap(store):
    config = StrategyConfig(
        slippage_ticks=0,
        profit_lock_floor_net=D("35"),
        profit_lock_activation_net=D("50"),
    )
    running(store)
    market = FakeMarket()
    exe = make_executor(store, market=market, config=config)
    exe.admit(buy_intent())
    exe.process(now=NOW + timedelta(seconds=1))
    first_time = NOW + timedelta(seconds=2)

    def quote(at, bid):
        return Quote(
            token="token-ce",
            source_time=at,
            received_time=at,
            ltp=bid,
            bid=bid,
            ask=bid + D("0.05"),
            bid_size=100,
            ask_size=100,
            provider="PHASE2_TEST",
        )

    activated = store.observe_position(
        USER, "token-ce", quote(first_time, D("105")), first_time
    )
    assert activated["profit_lock_active"] is True
    floor = D(activated["profit_floor_stop"])
    repeated_time = first_time + timedelta(seconds=1)
    store.observe_position(USER, "token-ce", quote(repeated_time, D("105")), repeated_time)
    with store.sessions() as db:
        events = db.scalars(
            select(NiftyEvent).where(
                NiftyEvent.user_id == USER,
                NiftyEvent.kind == "PROFIT_LOCK_ACTIVATED",
            )
        ).all()
    assert len(events) == 1
    stale_time = repeated_time + timedelta(seconds=1)
    ignored = store.observe_position(
        USER,
        "token-ce",
        quote(repeated_time, D("119")),
        stale_time + timedelta(seconds=10),
    )
    assert ignored["last_source_time"] == repeated_time.isoformat()

    restarted = NiftyStore(store.engine)
    restarted.initialize()
    recovered = restarted.positions(USER)[0]["protection"]
    assert recovered["profit_lock_active"] is True
    assert D(recovered["profit_floor_stop"]) == floor

    gap_time = repeated_time + timedelta(seconds=2)
    gap_bid = floor - D("1")
    observed = restarted.observe_position(USER, "token-ce", quote(gap_time, gap_bid), gap_time)
    assert observed["stop_price"] == recovered["stop_price"]
    assert observed["exit_reason"] == "TRAILING_STOP"

    market.bid = str(gap_bid)
    market.ask = str(gap_bid + D("0.05"))
    market.stamp = gap_time
    gap_executor = make_executor(restarted, market=market, config=config)
    exit_order, _ = gap_executor.admit(
        buy_intent(
            intent_id="phase2-gap-exit",
            side="SELL",
            quantity=25,
            exit_reason=observed["exit_reason"],
        ),
        now=gap_time,
    )
    fills = gap_executor.process(now=gap_time + timedelta(seconds=1))
    assert fills and fills[0]["status"] == "FILLED"
    trades = restarted.trades(USER)
    assert trades[-1]["reason"] == "PROFIT_FLOOR_GAP"
    assert D(trades[-1]["net"]) < D(
        activated["profit_lock_activation"]["floor_net"]
    )
    with restarted.sessions() as db:
        gap_events = db.scalars(
            select(NiftyEvent).where(
                NiftyEvent.user_id == USER,
                NiftyEvent.kind == "PROFIT_FLOOR_GAP",
            )
        ).all()
    assert len(gap_events) == 1
    assert D(gap_events[0].payload["expected_floor_net"]) == D(
        activated["profit_lock_activation"]["floor_net"]
    )
    assert D(gap_events[0].payload["realized_net"]) == D(trades[-1]["net"])
    assert exit_order["side"] == "SELL" and fills[0]["order_id"] == exit_order["order_id"]
