"""Approved 20/2 defaults and immutable historical configurations; synthetic only."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from services.nifty_algo.config import StrategyConfig, migrate_configuration
from services.nifty_algo.indicators import supertrend
from services.nifty_algo.signal_engine import Rules
from test.test_nifty_algo_sdk_241_parity import (
    PATTERNS,
    arrays,
    assert_numeric,
    field,
    fixture_bars,
    reference_bands,
    reference_smoothing,
)


@pytest.mark.parametrize("pattern", PATTERNS)
def test_actual_sdk_20_2_and_compiled_backend_parity(monkeypatch, pattern):
    from openalgo import ta
    from openalgo.indicators import _backend

    bars = fixture_bars(pattern)
    high, low, close, _ = arrays(bars)
    reference_atr, _, _, direction, values = reference_bands(
        bars, sdk_initial=True, period=20, multiplier=2
    )
    native_atr = ta.atr(high, low, close, 20)
    native_value, native_direction = ta.supertrend(high, low, close, 20, 2)
    assert_numeric(native_atr, reference_atr)
    assert_numeric(native_value, values)
    assert_numeric(-native_direction, direction)
    assert _backend.HAVE_RUST, "Compiled SDK parity requires the installed Rust extension"
    monkeypatch.setattr(_backend, "HAVE_RUST", False)
    assert_numeric(ta.atr(high, low, close, 20), native_atr)
    fallback_value, fallback_direction = ta.supertrend(high, low, close, 20, 2)
    assert_numeric(fallback_value, native_value)
    assert_numeric(fallback_direction, native_direction)


@pytest.mark.parametrize("bullish", (True, False))
def test_20_2_exact_band_crossing(bullish):
    bars = fixture_bars(n=22)
    for i in range(20):
        bars[i] = bars[i].model_copy(
            update={"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0 if bullish else 99.5}
        )
    boundary, beyond = (96.0, 95.95) if bullish else (104.0, 104.05)
    for i, close in ((20, boundary), (21, beyond)):
        bars[i] = bars[i].model_copy(
            update={
                "open": 100.0,
                "high": 101.0 if bullish else 105.0,
                "low": 95.0 if bullish else 99.0,
                "close": close,
            }
        )
    result = supertrend(bars)
    assert result[20]["direction"] == (1 if bullish else -1)
    assert result[21]["direction"] == (-1 if bullish else 1)
    assert result[20]["flip"] is False and result[21]["flip"] is True


def test_approved_defaults_and_function_defaults():
    config = StrategyConfig()
    assert config.strategy_version == "3.3.0"
    assert (config.atr_period, config.atr_multiplier) == (20, 2)
    bars = fixture_bars()
    assert supertrend(bars) == supertrend(bars, 20, 2)


@pytest.mark.parametrize("version", ("3.1.0", "3.2.0"))
def test_sparse_historical_records_keep_legacy_indicator_defaults(version):
    config = StrategyConfig(strategy_version=version)
    assert (config.atr_period, config.atr_multiplier) == (10, 3)
    assert StrategyConfig.model_validate(config.model_dump()).version_id == config.version_id


@pytest.mark.parametrize(
    "version,age,identity",
    (
        ("3.1.0", 3, "3bb641c8f7c4c20e82185ae09cefdbcfce5414e16198c785183bca4c12d170df"),
        ("3.2.0", 2, "e7b3243447672bc3be091b1966ef5896a7d6e37840837ca39a3dd1cd94c706db"),
    ),
)
def test_historical_configuration_identity_from_batch_a(version, age, identity):
    assert StrategyConfig(strategy_version=version, crossover_freshness=age).version_id == identity


def test_ambiguous_explicit_legacy_defaults_require_approval():
    values = StrategyConfig(strategy_version="3.2.0").model_dump(mode="json")
    original = deepcopy(values)
    with pytest.raises(ValueError, match="SUPERTrend_MIGRATION_APPROVAL_REQUIRED"):
        migrate_configuration(values)
    migrated = migrate_configuration(values, approve_supertrend=True, approve_fees=True)
    assert (migrated.atr_period, migrated.atr_multiplier) == (20, 2)
    assert migrated.strategy_version == "3.3.0"
    assert values == original
    assert migrate_configuration(migrated.model_dump()) == migrated


def test_implicit_defaults_and_explicit_custom_settings():
    implicit = migrate_configuration({"strategy_version": "3.2.0"})
    assert (implicit.atr_period, implicit.atr_multiplier) == (20, 2)
    custom = migrate_configuration(
        {"strategy_version": "3.2.0", "atr_period": 17, "atr_multiplier": 2.5}
    )
    assert (custom.atr_period, custom.atr_multiplier) == (17, 2.5)


@pytest.mark.parametrize("value", (0, 1, 101, float("nan")))
def test_invalid_length(value):
    with pytest.raises(ValidationError):
        StrategyConfig(atr_period=value)


@pytest.mark.parametrize("value", (0, -1, 10.1, float("inf")))
def test_invalid_factor(value):
    with pytest.raises(ValidationError):
        StrategyConfig(atr_multiplier=value)


@pytest.mark.parametrize("pattern", PATTERNS)
@pytest.mark.parametrize("timeframe", (5, 15))
def test_20_2_independent_recursion_and_both_timeframes(pattern, timeframe):
    """Independent array recurrence; do not replace the historical 10/3 tests."""
    import numpy as np

    bars = [b.model_copy(update={"timeframe": timeframe}) for b in fixture_bars(pattern)]
    high, low, close, _ = arrays(bars)
    tr = high - low
    tr[1:] = np.maximum.reduce((tr[1:], abs(high[1:] - close[:-1]), abs(low[1:] - close[:-1])))
    atr = reference_smoothing(tr, 20, 1 / 20)
    actual = supertrend(bars, 20, 2)
    assert actual[:19] == [None] * 19
    upper = lower = previous_close = direction = None
    duration = 0
    for i in range(19, len(bars)):
        mid = (high[i] + low[i]) / 2
        basic_upper, basic_lower = mid + 2 * atr[i], mid - 2 * atr[i]
        old_direction = direction
        if direction is None:
            direction = 1 if close[i] >= mid else -1
            upper, lower = basic_upper, basic_lower
        else:
            if basic_upper < upper or previous_close > upper:
                upper = basic_upper
            if basic_lower > lower or previous_close < lower:
                lower = basic_lower
            if direction < 0 and close[i] > upper:
                direction = 1
            elif direction > 0 and close[i] < lower:
                direction = -1
        duration = 1 if old_direction != direction else duration + 1
        assert actual[i]["value"] == pytest.approx(lower if direction == 1 else upper)
        assert actual[i]["direction"] == direction
        assert actual[i]["duration"] == duration
        previous_close = close[i]
    assert_numeric(field(actual, "atr"), atr)


@pytest.mark.parametrize("length", (0, 19, 20, 79, 80, 81))
def test_approved_warmup_and_diagnostics(length):
    bars = fixture_bars()[:length]
    all_bars = fixture_bars()
    now = bars[-1].end if bars else all_bars[0].start
    config = StrategyConfig()
    result = Rules().evaluate(bars, [], None, now, config, config.version_id, "SDK241-FUT")
    assert result["effective_configuration"]["strategy_version"] == "3.3.0"
    assert result["effective_configuration"]["atr_period"] == 20
    assert result["effective_configuration"]["atr_multiplier"] == 2
    assert not result["eligible"]  # Higher timeframe and PCR remain mandatory.


@pytest.mark.parametrize("exposure", ("NONE", "PENDING", "POSITION"))
def test_migration_defers_while_exposure_is_pinned(tmp_path, exposure):
    from datetime import UTC, datetime, timedelta

    from database.engine_factory import create_db_engine
    from database.nifty_algo_db import NiftyOrder, NiftyPosition, NiftyState, NiftyStore

    engine = create_db_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    store = NiftyStore(engine)
    now = datetime(2026, 11, 25, 5, tzinfo=UTC)
    # Explicit approved parameters make this migration unambiguous.
    old = StrategyConfig(
        strategy_version="3.2.0",
        atr_period=20,
        atr_multiplier=2,
        transaction_rate="0.000355299",
        stt_sell_rate="0.0015",
    )
    try:
        store.initialize()
        store.ensure_user("owner")
        with store.sessions.begin() as db:
            state = db.get(NiftyState, "owner")
            state.configuration = old.model_dump(mode="json")
            state.configuration_id = old.version_id
            state.state = "RUNNING"
            if exposure == "PENDING":
                db.add(
                    NiftyOrder(
                        user_id="owner",
                        order_id="pinned",
                        intent_id="pinned",
                        side="BUY",
                        symbol="SYNTHETIC",
                        token="fixture",
                        quantity=65,
                        status="PENDING",
                        payload={"configuration": old.model_dump(mode="json")},
                        eligible_at=now,
                        expires_at=now + timedelta(seconds=10),
                        created_at=now,
                    )
                )
            elif exposure == "POSITION":
                db.add(
                    NiftyPosition(
                        user_id="owner",
                        token="fixture",
                        symbol="SYNTHETIC",
                        instrument={},
                        quantity=65,
                        entry_price=60,
                        entry_order_id="pinned",
                        highest=60,
                        opened_at=now,
                    )
                )
        result = store.read("owner")
        assert result["state"] == "PAUSED"
        assert result["configuration"]["strategy_version"] == (
            "3.3.0" if exposure == "NONE" else "3.2.0"
        )
        revision = result["revision"]
        assert store.read("owner")["revision"] == revision
        if exposure != "NONE":
            assert result["configuration_id"] == old.version_id
            from database.nifty_algo_db import StateConflict

            with pytest.raises(StateConflict, match="pending order or open position"):
                store.change("owner", revision, configuration=StrategyConfig())
    finally:
        engine.dispose()
