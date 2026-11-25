"""Research models may vary inputs; new PAPER entries keep approved floors."""

import pytest
from pydantic import ValidationError

from services.nifty_algo.config import StrategyConfig, active_configuration


@pytest.mark.parametrize(
    "field,value",
    (
        ("daily_loss_fraction", "0.02"),
        ("adx_period", 13),
        ("adx_min", 24.99),
        ("macd_fast", 11),
        ("macd_slow", 25),
        ("macd_signal", 8),
        ("vwap_basis", "close"),
        ("vwap_max_bps", 81),
        ("pcr_max_age", 91),
        ("pcr_max_skew_seconds", 6),
        ("pcr_bull", 1.4),
        ("pcr_bear", 1.1),
        ("trailing_activation_points", "2"),
        ("stt_sell_rate", "0.000625"),
        ("transaction_rate", "0.0003"),
        ("gst_rate", "0.17"),
        ("brokerage", "0"),
        ("lot_score_thresholds", ("0", "39", "70")),
    ),
)
def test_active_configuration_refuses_weakening(field, value):
    values = StrategyConfig().model_dump(mode="json") | {field: value}
    # Historic/research deserialization is independent of entry authorization.
    StrategyConfig.model_validate(values)
    with pytest.raises(ValidationError) as refused:
        active_configuration(values)
    assert any(error["loc"] == (field,) for error in refused.value.errors())


def test_stricter_values_and_pinned_historical_configuration_remain_representable():
    config = StrategyConfig(
        adx_min=30,
        pcr_max_age=60,
        pcr_max_skew_seconds=2,
        vwap_max_bps=60,
        daily_loss_fraction="0.01",
        lot_score_thresholds=("0", "50", "80"),
    )
    assert active_configuration(config) is config
    old = StrategyConfig(strategy_version="3.2.0", daily_loss_fraction="0.02")
    assert old.daily_loss_fraction > config.daily_loss_fraction
