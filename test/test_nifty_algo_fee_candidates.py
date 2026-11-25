"""Independent hand-calculated tariff vectors, never contract-note claims."""

from datetime import date
from decimal import Decimal as D

import pytest

from services.nifty_algo.config import StrategyConfig
from services.nifty_algo.fees import (
    candidate_angel_schedule,
    candidate_breakdown,
    configured_legacy_total,
    configured_total,
    round_daily_stt,
)


@pytest.mark.parametrize("side,expected", (("BUY", "26.5279"), ("SELL", "36.0829")))
def test_2026_candidate_golden_6500_turnover(side, expected):
    result = candidate_breakdown(side, D("100"), 65, date(2026, 11, 25))
    assert result["components"]["exchange"] == D("2.3094435")
    assert result["components"]["ipft"] == D("0.0000065")
    assert result["components"]["sebi"] == D("0.0065")
    assert result["components"]["gst"] == D("4.016871")
    assert result["total"] == D(expected)
    assert result["active"] is False and result["actual_contract_note"] is False


def test_legacy_charge_vectors_remain_exact():
    config = StrategyConfig(strategy_version="3.2.0")
    assert configured_legacy_total("BUY", D(100), 65, config) == D("27.6365")
    assert configured_legacy_total("SELL", D(100), 65, config) == D("31.5040")
    assert configured_total("BUY", D(100), 65, StrategyConfig()) == D("26.5279")
    assert configured_total("SELL", D(100), 65, StrategyConfig()) == D("36.0829")


def test_effective_date_boundaries_and_daily_rounding():
    assert candidate_angel_schedule(date(2026, 2, 28))["transaction_rate"] == D("0.0003503")
    assert candidate_angel_schedule(date(2026, 3, 1))["transaction_rate"] == D("0.000355299")
    assert candidate_angel_schedule(date(2026, 3, 31))["stt_sell_rate"] == D("0.001")
    assert candidate_angel_schedule(date(2026, 4, 1))["stt_sell_rate"] == D("0.0015")
    assert round_daily_stt(["0.49", "0.49"]) == D(1)
    assert round_daily_stt(["0.49"]) == D(0)
    assert round_daily_stt(["0.50"]) == D(1)
    with pytest.raises(ValueError):
        candidate_angel_schedule(date(2024, 9, 30))
