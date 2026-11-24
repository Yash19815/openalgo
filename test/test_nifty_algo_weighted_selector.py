"""Weighted proposals must preserve frozen financial and market-data gates."""

from datetime import timedelta
from decimal import Decimal as D
from hashlib import sha256

import pytest

from services.nifty_algo.config import StrategyConfig
from services.nifty_algo.risk_manager import plan_entry
from test.test_nifty_algo_phase1 import NOW, account, candidate, no_charges


def test_default_weights_preserve_legacy_configuration_identity():
    config = StrategyConfig()
    assert (
        config.version_id
        == sha256(config.model_dump_json(exclude={"selector_weights"}).encode()).hexdigest()
    )
    changed = StrategyConfig(selector_weights=(25, 30, 15, 20, 10))
    assert changed.version_id != config.version_id


@pytest.mark.parametrize("weights", [(30, 25, 15, 20, 11), (-1, 26, 25, 25, 25), (0, 0, 0, 0, 0)])
def test_weights_reject_invalid_total_or_range(weights):
    with pytest.raises(ValueError):
        StrategyConfig(selector_weights=weights)


def test_all_eligible_quantities_ranked_with_bounded_scores_and_exact_risk():
    item, quote = candidate(lot_size=25)
    plan = plan_entry(account(), [(item, quote)], StrategyConfig(), 100, no_charges, now=NOW)
    assert plan.instrument is not None
    assert plan.planned_loss <= 400 and plan.projected_net_reward >= 350
    assert plan.ranking and plan.ranking[0]["quantity"] == plan.quantity
    for row in plan.ranking:
        assert D(0) <= D(row["total"]) <= D(100)
        assert all(D(0) <= D(value) <= D(1) for value in row["scores"].values())
        assert sum(D(v) for v in row["weights"].values()) == 100


def test_tie_breaking_is_independent_of_input_order():
    a, aq = candidate("a")
    z, zq = candidate("z")
    args = (StrategyConfig(), 100, no_charges)
    left = plan_entry(account(), [(z, zq), (a, aq)], *args, now=NOW)
    right = plan_entry(account(), [(a, aq), (z, zq)], *args, now=NOW)
    assert left.ranking == right.ranking
    assert left.instrument.token == right.instrument.token == "a"


def test_missing_delta_never_receives_redistributed_weight():
    missing, quote = candidate()
    fresh = missing.model_copy(update={"delta": 0.5, "delta_time": NOW})
    config = StrategyConfig()
    no_delta = plan_entry(account(), [(missing, quote)], config, 100, no_charges, now=NOW)
    with_delta = plan_entry(account(), [(fresh, quote)], config, 100, no_charges, now=NOW)
    assert no_delta.instrument is not None
    assert not no_delta.ranking[0]["coverage"]["delta"]
    assert D(with_delta.ranking[0]["total"]) - D(no_delta.ranking[0]["total"]) == 15
    stale = fresh.model_copy(update={"delta_time": NOW - timedelta(seconds=6)})
    old = plan_entry(account(), [(stale, quote)], config, 100, no_charges, now=NOW)
    assert old.ranking == no_delta.ranking


def test_explicit_clock_rejects_stale_missing_bid_and_insufficient_exit_depth():
    item, quote = candidate()
    config = StrategyConfig()
    for bad in (
        quote.model_copy(update={"source_time": NOW - timedelta(seconds=6)}),
        quote.model_copy(update={"bid": None}),
        quote.model_copy(update={"bid_size": 0}),
    ):
        plan = plan_entry(account(), [(item, bad)], config, 100, no_charges, now=NOW)
        assert plan.quantity == 0 and not plan.ranking


def test_better_liquidity_can_outrank_first_listed_contract():
    a, aq = candidate("a")
    b, bq = candidate("b")
    aq = aq.model_copy(update={"bid_size": 25, "ask_size": 25})
    config = StrategyConfig()
    plan = plan_entry(account(), [(a, aq), (b, bq)], config, 100, no_charges, now=NOW)
    assert plan.instrument.token == "b"
    assert any(
        reason == "INSUFFICIENT_DEPTH" for token, _, reason in plan.rejections if token == "a"
    )
    assert D(next(row["total"] for row in plan.ranking if row["token"] == "a")) < D(
        plan.ranking[0]["total"]
    )
