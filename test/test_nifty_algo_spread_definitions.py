"""Preserve executable ask-cost gating and symmetric midpoint ranking."""

from decimal import Decimal as D

from scripts.nifty_remaining_analysis import proposal


def test_ask_gate_boundary_and_midpoint_ranking_are_distinct_and_pinned():
    accepted = proposal(D(70), 2, D(30), D("0.45"), 1)
    assert accepted.instrument is not None
    assert (D("0.45") / D(30) * 10000) == 150
    assert all(D(row["inputs"]["spread_bps"]) > 150 for row in accepted.ranking)
    assert all(D(row["scores"]["spread"]) == 0 for row in accepted.ranking)
    rejected = proposal(D(70), 2, D(30), D("0.50"), 1)
    assert rejected.instrument is None
    assert ("SYNTHETIC-65", 0, "LIQUIDITY_UNAVAILABLE") in rejected.rejections


def test_rank_spread_term_uses_actual_midpoint_without_changing_admission():
    accepted = proposal(D(70), 2, D(30), D("0.40"), 1)
    row = accepted.ranking[0]
    midpoint_bps = D("0.40") / D("29.80") * 10000
    ask_bps = D("0.40") / D(30) * 10000
    assert D(row["inputs"]["spread_bps"]) == midpoint_bps
    assert D(row["scores"]["spread"]) == 1 - midpoint_bps / 150
    assert midpoint_bps > ask_bps
