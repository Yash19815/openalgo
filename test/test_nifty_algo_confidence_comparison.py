"""Inactive confidence proposals cannot change active lot/target semantics."""

from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from services.nifty_algo.confidence import signal_strength
from services.nifty_algo.confidence_comparison import POLICIES, compare_strength
from services.nifty_algo.config import StrategyConfig


@pytest.mark.parametrize("age", (0, 1, 2))
def test_recency_alternatives_are_explicit_and_inactive(age):
    config = StrategyConfig()
    st = {"atr": 10.0, "duration": 10, "distance": 20.0, "direction": 1}
    snap = {
        "supertrend": st,
        "macd": {"cross_age": age, "histogram": 1.0},
        "adx": {"adx": 40.0},
        "price": 100.0,
        "vwap": 100.0,
    }
    args = snap, {"supertrend": st}, SimpleNamespace(value=2.0), 1, config
    original = signal_strength(*args)
    results = {p: compare_strength(*args, p) for p in POLICIES}
    assert results[POLICIES[0]]["score"] == original["score"]
    assert results[POLICIES[2]]["score"] == original["score"]
    assert results[POLICIES[3]]["score"] - original["score"] == pytest.approx(
        10 * age / 12, abs=1e-6
    )
    assert results[POLICIES[1]]["contributions"]["supertrend"]["points"] == 15
    assert all(r["active"] is False for r in results.values())
    assert signal_strength(*args) == original
    with pytest.raises(ValidationError):
        StrategyConfig(confidence_method=POLICIES[3])


@pytest.mark.parametrize(
    "score,lots",
    (("39.999999", 1), ("40", 2), ("40.000001", 2), ("69.999999", 2), ("70", 3), ("70.000001", 3)),
)
def test_real_risk_engine_at_lot_boundaries(score, lots):
    from scripts.nifty_remaining_analysis import proposal

    # A 20 premium cannot finance the reward floor for one lot, but can for
    # higher lot permissions. Count all actual proposals rather than infer fills.
    plan = proposal(D(score), 3, D(20), D("0.05"), 1)
    assert sum(t <= D(score) for t in StrategyConfig().lot_score_thresholds) == lots
    assert all(r["lots"] <= lots for r in plan.ranking)
    assert all(
        D(r["planned_loss"]) <= 400 and D(r["projected_net_reward"]) >= 350 for r in plan.ranking
    )
