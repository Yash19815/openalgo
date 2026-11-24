"""Gap-remediation regression tests: hard strategy limits and fill revalidation."""

from datetime import time, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from services.nifty_algo.config import StrategyConfig
from services.nifty_algo.models import Quote
from services.nifty_algo.paper_executor import _charges
from services.nifty_algo.risk_manager import AccountRisk, plan_entry
from test.nifty_calendar_helpers import seed_market_timing
from test.test_nifty_algo_paper_executor import (
    NOW,
    USER,
    FakeMarket,
    buy_intent,
    executor,
    instrument,
    running,
)
from test.test_nifty_algo_paper_executor import store as store


def _bad(**kwargs):
    with pytest.raises(ValidationError):
        StrategyConfig.model_validate(kwargs)


def test_max_planned_loss_cannot_exceed_400():
    _bad(max_planned_loss=Decimal("400.01"))
    StrategyConfig.model_validate({"max_planned_loss": Decimal("400")})
    StrategyConfig.model_validate({"max_planned_loss": Decimal("300")})  # safer OK


def test_min_projected_net_reward_cannot_drop_below_350():
    _bad(min_projected_net_reward=Decimal("349.99"))
    StrategyConfig.model_validate({"min_projected_net_reward": Decimal("350")})


def test_max_hold_minutes_capped_at_45():
    _bad(max_hold_minutes=46)
    StrategyConfig.model_validate({"max_hold_minutes": 45})
    StrategyConfig.model_validate({"max_hold_minutes": 30})


def test_monthly_loss_limit_capped_at_2000():
    _bad(monthly_loss_limit=Decimal("2000.01"))
    StrategyConfig.model_validate({"monthly_loss_limit": Decimal("1000")})


def test_virtual_capital_fixed_at_20000():
    _bad(virtual_capital=Decimal("20001"))
    _bad(virtual_capital=Decimal("19999"))
    assert StrategyConfig().virtual_capital == Decimal("20000")


def test_trading_windows_cannot_widen():
    _bad(entry_after=time(10, 29))
    _bad(entry_before=time(14, 46))
    _bad(exit_by=time(15, 11))
    _bad(shadow_entry_after=time(9, 14))
    # tighter (safer) windows allowed
    StrategyConfig.model_validate(
        {
            "entry_after": time(10, 45),
            "entry_before": time(14, 30),
            "exit_by": time(15, 0),
            "shadow_entry_after": time(9, 20),
        }
    )


def test_trailing_distance_fixed_at_1_5():
    _bad(trailing_distance_points=Decimal("2.0"))
    _bad(trailing_candidates=(Decimal("1.0"), Decimal("1.5")))
    StrategyConfig.model_validate({"trailing_candidates": (Decimal("1.5"), Decimal("2.0"))})


def test_profit_lock_bounds():
    _bad(profit_lock_activation_net=Decimal("400.01"))
    _bad(profit_lock_floor_net=Decimal("-0.01"))
    _bad(
        profit_lock_floor_net=Decimal("400"),
        profit_lock_activation_net=Decimal("400"),
    )
    _bad(profit_lock_floor_net=Decimal("349.99"))
    StrategyConfig.model_validate({"profit_lock_floor_net": Decimal("350")})
    StrategyConfig.model_validate({"profit_lock_floor_net": Decimal("360")})
    _bad(profit_lock_activation_net=Decimal("399.99"))
    _bad(early_booking_min_net=Decimal("299.99"))


def test_premium_stop_capped_at_8pct():
    _bad(premium_stop=Decimal("0.0801"))
    StrategyConfig.model_validate({"premium_stop": Decimal("0.05")})


@pytest.fixture(autouse=True)
def _gap_market_calendar():
    seed_market_timing()


def _filled(store, market, config=None):
    running(store)
    exe = executor(store, market=market, config=config or StrategyConfig(latency_ms=1))
    exe.admit(buy_intent())
    return exe.process(now=NOW + timedelta(seconds=1))


def test_fill_revalidates_reward_at_actual_fill_price(store):
    """P1-02: quote deteriorates between admission and fill -> reject."""
    market = FakeMarket()
    running(store)
    exe = executor(store, market=market, config=StrategyConfig(latency_ms=1))
    exe.admit(buy_intent())
    # Ask falls ~24%: planned loss is fine but modeled reward drops below 350.
    market.bid, market.ask = "124", "125"
    fills = exe.process(now=NOW + timedelta(seconds=1))
    assert [row["status"] for row in fills] == ["REJECTED"]
    assert fills[0]["reason"] == "NET_REWARD_BELOW_MINIMUM"
    assert store.pending_orders(USER) == []
    assert store.orders(USER)[0]["reason"] == "NET_REWARD_BELOW_MINIMUM"


def test_fill_accepts_when_reward_still_above_floor(store):
    """P1-02: same config, healthy market -> the order still fills."""
    fills = _filled(store, FakeMarket())
    assert [row["status"] for row in fills] == ["FILLED"]


@pytest.mark.parametrize(
    "bid,ask",
    [("165", "165"), ("140", "165"), (None, "165")],
    ids=["crossed", "wide_spread", "missing_bid"],
)
def test_fill_rejects_deteriorated_liquidity(store, bid, ask):
    """P1-03: crossed, widened, or missing bid side at fill -> reject."""
    market = FakeMarket()
    running(store)
    exe = executor(store, market=market, config=StrategyConfig(latency_ms=1))
    exe.admit(buy_intent())
    market.bid, market.ask = bid, ask
    fills = exe.process(now=NOW + timedelta(seconds=1))
    assert [row["status"] for row in fills] == ["REJECTED"]
    assert fills[0]["reason"] == "LIQUIDITY_LOST"


def test_fill_rejects_collapsed_volume(store):
    """P1-03: option volume below minimum at fill -> reject."""
    market = FakeMarket()
    running(store)
    exe = executor(store, market=market, config=StrategyConfig(latency_ms=1))
    exe.admit(buy_intent())
    market.volume = 500
    fills = exe.process(now=NOW + timedelta(seconds=1))
    assert [row["status"] for row in fills] == ["REJECTED"]
    assert fills[0]["reason"] == "LIQUIDITY_LOST"


def test_fill_rejects_contract_turned_otm(store):
    """P1-03: spot moves so the admitted contract is OTM at fill -> reject."""
    market = FakeMarket()
    running(store)
    exe = executor(store, market=market, config=StrategyConfig(latency_ms=1))
    exe.admit(buy_intent())
    # CE 22000 was ATM at admission; spot at 21900 makes it OTM.
    market.index_ltp = "21900"
    fills = exe.process(now=NOW + timedelta(seconds=1))
    assert [row["status"] for row in fills] == ["REJECTED"]
    assert fills[0]["reason"] == "OTM_PROHIBITED"


def test_fill_waits_when_spot_unavailable(store):
    """P1-03: no current index quote -> order stays pending (fail closed)."""

    class NoSpot(FakeMarket):
        def get_all_data(self, symbol, exchange):
            if symbol == "NIFTY":
                return {}
            return super().get_all_data(symbol, exchange)

    running(store)
    exe = executor(store, market=FakeMarket(), config=StrategyConfig(latency_ms=1))
    exe.admit(buy_intent())
    exe.market_data = NoSpot()
    assert exe.process(now=NOW + timedelta(seconds=1)) == []
    assert [row["status"] for row in store.pending_orders(USER)] == ["PENDING"]


@pytest.mark.parametrize("mode", ["1", "2", "3"])
def test_fill_reads_native_spot_observation(store, mode):
    class SourceSpot(FakeMarket):
        def get_all_data(self, symbol, exchange):
            if symbol == "NIFTY":
                return {
                    "source_observations": {
                        mode: {
                            "ltp": 22000,
                            "ltt": NOW.timestamp() * 1000,
                            "received_time": NOW.timestamp(),
                        }
                    }
                }
            return super().get_all_data(symbol, exchange)

    running(store)
    exe = executor(store, market=SourceSpot(), config=StrategyConfig(latency_ms=1))
    exe.admit(buy_intent())
    assert [row["status"] for row in exe.process(NOW + timedelta(seconds=1))] == ["FILLED"]


@pytest.mark.parametrize(
    "fault",
    [
        "missing_source",
        "missing_receipt",
        "stale",
        "future_source",
        "future_receipt",
        "receipt_before_source",
        "nan",
        "infinite",
        "zero",
        "negative",
        "malformed",
        "malformed_ltp",
        "display_only",
    ],
)
def test_fill_waits_for_valid_source_spot_not_display_fallback(store, fault):
    class InvalidSpot(FakeMarket):
        def get_all_data(self, symbol, exchange):
            if symbol != "NIFTY":
                return super().get_all_data(symbol, exchange)
            raw = {
                "ltp": 22000,
                "ltt": NOW.timestamp() * 1000,
                "received_time": NOW.timestamp(),
            }
            if fault == "missing_source":
                raw.pop("ltt")
            elif fault == "missing_receipt":
                raw.pop("received_time")
            elif fault == "stale":
                raw["ltt"] = (NOW - timedelta(seconds=6)).timestamp() * 1000
            elif fault == "future_source":
                raw["ltt"] = (NOW + timedelta(seconds=2)).timestamp() * 1000
            elif fault == "future_receipt":
                raw["received_time"] = (NOW + timedelta(seconds=2)).timestamp()
            elif fault == "receipt_before_source":
                raw["received_time"] = (NOW - timedelta(seconds=1)).timestamp()
            elif fault in ("nan", "infinite", "zero", "negative"):
                raw["ltp"] = {"nan": "NaN", "infinite": "Infinity", "zero": 0, "negative": -1}[
                    fault
                ]
            elif fault == "malformed":
                raw = "invalid"
            elif fault == "malformed_ltp":
                raw["ltp"] = "not-a-price"
            # Display fields cannot rescue an invalid or absent source observation.
            return {
                "source_observations": {} if fault == "display_only" else {"2": raw},
                "ltp": {"value": 22000, "timestamp": NOW.timestamp()},
                "last_update": NOW.timestamp(),
            }

    running(store)
    exe = executor(store, market=FakeMarket(), config=StrategyConfig(latency_ms=1))
    exe.admit(buy_intent())
    exe.market_data = InvalidSpot()
    assert exe.process(NOW + timedelta(seconds=1)) == []
    assert store.positions(USER) == []
    assert len(store.pending_orders(USER)) == 1
    exe.process(NOW + timedelta(seconds=11))
    assert store.pending_orders(USER) == []
    assert store.orders(USER)[0]["status"] == "EXPIRED"


def test_fill_rejects_degenerate_price(store):
    """P1-05: sub-tick fill price -> protection model refuses, never persists."""
    market = FakeMarket()
    running(store)
    exe = executor(store, market=market, config=StrategyConfig(latency_ms=1))
    exe.admit(buy_intent())
    # A ~0.15 entry cannot fit a tick-aligned 8% stop: ceiling_tick(0.138)
    # rounds up to the entry itself, and the stop-exit subtraction would
    # underflow, which the protection layer rejects first
    # (STOP_PRICE_INVALID remains as defense-in-depth behind it).
    # Quote must stay coherent (bid < ltp < ask, strictly positive) and
    # bid/ask tick-aligned: _depth drops any level off the 0.05 grid.
    market.bid, market.ltp, market.ask = "0.05", "0.075", "0.10"
    fills = exe.process(now=NOW + timedelta(seconds=1))
    assert [row["status"] for row in fills] == ["REJECTED"]
    assert fills[0]["reason"] == "PROTECTION_TICK_INVALID"
    assert store.pending_orders(USER) == []


def test_admission_rejects_degenerate_price(store):
    """P1-05: a low-premium candidate is refused at admission, deterministically.

    On the 0.05 tick grid every coherent quote cheap enough to break the
    protection math (entry ~0.15) carries a ~5000 bps spread, so admit()
    refuses it at LIQUIDITY_UNAVAILABLE before planning ever runs. Behind
    that gate, plan_entry -- the admission-time protection guard -- refuses
    the same candidate with PROTECTION_TICK_INVALID.
    """
    market = FakeMarket(bid="0.05", ltp="0.075", ask="0.10")
    running(store)
    exe = executor(store, market=market)
    with pytest.raises(Exception, match="LIQUIDITY_UNAVAILABLE"):
        exe.admit(buy_intent())

    contract = instrument()
    quote = Quote(
        token=contract.token,
        source_time=NOW,
        received_time=NOW,
        ltp=Decimal("0.075"),
        bid=Decimal("0.05"),
        ask=Decimal("0.10"),
        bid_size=100,
        ask_size=100,
        volume=10000,
        provider="test",
    )
    plan = plan_entry(
        AccountRisk(
            equity=Decimal("20000"),
            available=Decimal("20000"),
            starting_day_equity=Decimal("20000"),
        ),
        [(contract, quote)],
        StrategyConfig(),
        100,
        _charges,
    )
    assert plan.instrument is None
    assert "PROTECTION_TICK_INVALID" in {reason for _, _, reason in plan.rejections}
