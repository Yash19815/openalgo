"""Deterministic test fixtures, never market observations or broker requests."""

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from services.nifty_algo.config import StrategyConfig
from services.nifty_algo.contract_resolver import Resolver
from services.nifty_algo.indicators import adx, ema, macd, pcr, supertrend, vwap, wilder
from services.nifty_algo.market_data import aggregate
from services.nifty_algo.models import Candle, Instrument, Quote
from services.nifty_algo.risk_manager import (
    AccountRisk,
    entry_reasons,
    evaluate_premium_exit,
    size_quantity,
)
from services.nifty_algo.signal_engine import Rules

NOW = datetime(2026, 11, 19, 4, 30, tzinfo=UTC)


def candle(index, close=100, volume=10, timeframe=1):
    start = NOW + timedelta(minutes=index * timeframe)
    return Candle(
        token="future",
        start=start,
        end=start + timedelta(minutes=timeframe),
        timeframe=timeframe,
        open=close,
        close=close,
        high=close + 1,
        low=close - 1,
        volume=volume,
        provenance="TEST_FIXTURE",
    )


def instrument(kind="CE", strike=22000, token="call", **changes):
    return Instrument(
        token=token,
        symbol="TEST_CONTRACT",
        exchange="NFO",
        kind=kind,
        expiry=date(2026, 11, 24),
        strike=strike,
        lot_size=25,
        tick_size=Decimal("0.05"),
        master_date=NOW.date(),
        **changes,
    )


def quote(token="call", **changes):
    data = {
        "token": token,
        "source_time": NOW,
        "received_time": NOW,
        "ltp": 100,
        "bid": 99,
        "ask": 100,
        "bid_size": 100,
        "ask_size": 100,
        "volume": 2000,
        "oi": 100,
        "provider": "TEST_FIXTURE",
    }
    return Quote(**(data | changes))


def test_seeded_smoothing_hand_reference():
    assert ema([1, 2, 3, 4], 3) == [None, None, 2, 3]
    assert wilder([1, 2, 3, 5], 3)[-1] == 3


def test_macd_linear_series_hand_reference_and_prefix_causality():
    bars = [candle(i, 100 + i) for i in range(50)]
    result = macd(bars, 3, 5, 2)
    assert result[-1]["line"] == pytest.approx(1)
    assert result[-1]["signal"] == pytest.approx(1)
    assert result[-1]["histogram"] == pytest.approx(0)
    assert result[:30] == macd(bars[:30], 3, 5, 2)


def test_adx_and_supertrend_independent_monotone_reference():
    bars = [candle(i, 100 + i) for i in range(50)]
    assert adx(bars, 3)[-1]["adx"] == pytest.approx(100)
    assert adx(bars, 3)[-1]["minus_di"] == 0
    trend = supertrend(bars, 3, 2)
    assert trend[-1]["direction"] == 1
    assert trend[-1]["value"] == pytest.approx(bars[-1].close - 4)
    assert trend[:30] == supertrend(bars[:30], 3, 2)


def test_vwap_weighted_reference_and_missing_volume():
    bars = [candle(0, 100, 10), candle(1, 110, 30), candle(2, 120, None), candle(3, 130)]
    assert vwap(bars) == [100, 107.5, None, None]
    assert vwap(bars, instrument_kind="SPOT") == [None] * 4


def test_pcr_scope_complete_legs_and_causal_times():
    contracts = [instrument(), instrument("PE", token="put")]
    quotes = {"call": quote(), "put": quote("put", oi=150)}
    assert pcr(contracts, quotes, "OI", "TEST_EXPIRY_ALL_STRIKES", NOW, verified=True).value == 1.5
    assert pcr(contracts, {"call": quote()}, "OI", "scope", NOW, verified=True) is None
    assert pcr(contracts, quotes, "OI", "scope", NOW, verified=False) is None
    assert pcr(contracts, quotes | {"call": quote(oi=0)}, "OI", "scope", NOW, verified=True) is None
    assert (
        pcr(
            contracts,
            quotes | {"call": quote(source_time=NOW + timedelta(seconds=1))},
            "OI",
            "scope",
            NOW,
            verified=True,
        )
        is None
    )
    assert (
        pcr(
            contracts + [instrument(strike=22100, token="unpaired")],
            quotes,
            "OI",
            "scope",
            NOW,
            verified=True,
        )
        is None
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"underlying": "BANKNIFTY"},
        {"exchange": "NSE"},
        {"tick_size": float("nan")},
        {"lot_size": 0},
    ],
)
def test_invalid_metadata_rejected(changes):
    data = instrument().model_dump() | changes
    with pytest.raises(ValidationError):
        Instrument(**data)


def test_contract_resolver_uses_listed_strikes_and_requires_fresh_depth():
    contracts = [instrument(strike=22000), instrument(strike=22080, token="higher")]
    quotes = {"call": quote(), "higher": quote("higher")}
    config = StrategyConfig()
    assert Resolver().resolve(contracts, quotes, 22040, "CE", NOW, config).token == "call"
    assert (
        Resolver()
        .resolve(contracts, quotes, 22040, "CE", NOW, StrategyConfig(selection="OTM"))
        .token
        == "higher"
    )
    with pytest.raises(ValueError):
        Resolver().resolve(contracts, quotes, 22040, "FUT", NOW, config)
    with pytest.raises(ValueError):
        Resolver().resolve(
            contracts, quotes | {"call": quote(bid_size=0)}, 22040, "CE", NOW, config
        )


def test_aggregation_requires_effective_session_and_all_constituents():
    bars = [candle(i) for i in range(5)]
    end = NOW + timedelta(minutes=5)
    assert len(aggregate(bars, 5, end, session_open=NOW)) == 1
    assert aggregate(bars[:-1], 5, end, session_open=NOW) == []
    assert aggregate(bars, 5, end - timedelta(seconds=1), session_open=NOW) == []
    with pytest.raises(ValueError):
        aggregate(bars, 5, end)


def test_signal_determinism_unavailable_and_forming_candle_exclusion():
    config = StrategyConfig()
    result = Rules().evaluate([], [], None, NOW, config, config.version_id, "future")
    assert result["bias"] == "DATA_UNAVAILABLE"
    assert not result["eligible"]
    assert result == Rules().evaluate(
        [candle(0, timeframe=5)], [], None, NOW, config, config.version_id, "future"
    )
    assert config.version_id != StrategyConfig(adx_min=30).version_id


def test_risk_whole_lot_budget_includes_costs_and_blocks_pending():
    account = AccountRisk(
        Decimal("100000"),
        Decimal("100000"),
        Decimal("100000"),
        reconciled=True,
        entries_enabled=True,
    )
    config = StrategyConfig()
    assert size_quantity(account, instrument(), quote(), config, Decimal("100")) == 25
    assert size_quantity(account, instrument(), quote(), config, Decimal("200")) == 0
    pending = AccountRisk(
        Decimal("100000"),
        Decimal("100000"),
        Decimal("100000"),
        pending_entries=1,
        reconciled=True,
        entries_enabled=True,
    )
    assert "PENDING_ENTRY" in entry_reasons(
        pending, instrument(), quote(), NOW, config, session_open=True, data_healthy=True
    )


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1"])
def test_invalid_account_values_fail_closed(value):
    with pytest.raises(ValueError):
        AccountRisk(Decimal(value), Decimal("100000"), Decimal("100000"))


def test_nan_bypassed_candle_model_cannot_enter():
    invalid = candle(-1, timeframe=5).model_copy(update={"close": float("nan")})
    config = StrategyConfig()
    decision = Rules().evaluate([invalid], [], None, NOW, config, config.version_id, "future")
    assert not decision["eligible"]
    assert decision["bias"] == "DATA_UNAVAILABLE"


def test_shared_rms_stop_target_and_trailing():
    config = StrategyConfig()
    assert not evaluate_premium_exit(100, 25, 89, config).breached
    assert evaluate_premium_exit(100, 25, 84, config).breached
    assert evaluate_premium_exit(100, 25, 131, config).breached
    trailing = evaluate_premium_exit(100, 25, 105, config, highest_price=120)
    assert trailing.breached
    assert trailing.stop_price == pytest.approx(108)
