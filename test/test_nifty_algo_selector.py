"""Offline selector evidence; these fixtures do not establish broker readiness."""

from datetime import timedelta
from itertools import permutations

import pytest

from services.nifty_algo.config import StrategyConfig
from services.nifty_algo.contract_resolver import Resolver
from test.test_nifty_algo_phase1 import NOW, candidate


def test_selector_assessment_explains_rejections_and_keeps_baseline_priority():
    pairs = [candidate("atm"), candidate("itm", strike=21950)]
    instruments = [item for item, _ in pairs]
    quotes = {item.token: quote for item, quote in pairs}
    quotes["atm"] = quotes["atm"].model_copy(update={"source_time": NOW - timedelta(seconds=6)})
    report = Resolver().assess(instruments, quotes, 22000, "CE", NOW, StrategyConfig())
    assert report["policy"] == "listed-preference-v1"
    assert report["configuration_id"] == StrategyConfig().version_id
    assert report["ranked_tokens"] == ["itm"]
    assert report["candidates"][0]["reasons"] == ["QUOTE_STALE"]
    assert report["candidates"][0]["moneyness"] == "ATM"
    assert report["candidates"][1]["rank"] == 1
    assert report["candidates"][1]["quote"]["provider"] == "PHASE1_TEST"
    assert report["atm_strike"] == "22000"


def test_selector_assessment_is_deterministic_for_equal_metadata_preferences():
    pairs = [candidate("b"), candidate("a"), candidate("itm", strike=21950)]
    quotes = {item.token: quote for item, quote in pairs}
    reports = [
        Resolver().assess(list(order), quotes, 22000, "CE", NOW, StrategyConfig())
        for order in permutations(item for item, _ in pairs)
    ]
    assert all(report == reports[0] for report in reports)
    assert reports[0]["ranked_tokens"] == ["a", "b", "itm"]


def test_selector_assessment_keeps_failed_candidates_visible_without_inventing_quotes():
    item, _ = candidate()
    report = Resolver().assess([item], {}, 22000, "CE", NOW, StrategyConfig())
    assert report["ranked_tokens"] == []
    assert report["candidates"][0]["quote"] is None
    assert report["candidates"][0]["reasons"] == ["QUOTE_UNAVAILABLE"]


def test_selector_evidence_includes_otm_and_window_exclusions():
    pairs = [candidate(), candidate("otm", strike=22050), candidate("itm", strike=21950)]
    report = Resolver().assess(
        [item for item, _ in pairs],
        {item.token: quote for item, quote in pairs},
        22000,
        "CE",
        NOW,
        StrategyConfig(candidate_strike_window=0),
    )
    rows = {row["instrument"]["token"]: row for row in report["candidates"]}
    assert rows["otm"]["reasons"] == ["OTM_PROHIBITED"]
    assert rows["itm"]["reasons"] == ["OUTSIDE_SELECTION_WINDOW"]
    assert report["ranked_tokens"] == ["candidate"]


def test_selector_rejects_conflicting_identity_for_same_token():
    item, quote = candidate()
    conflict = item.model_copy(update={"symbol": "DIFFERENT_CONTRACT"})
    with pytest.raises(ValueError, match="Conflicting option token metadata"):
        Resolver().assess([item, conflict], {item.token: quote}, 22000, "CE", NOW, StrategyConfig())


def test_selector_caps_rejection_evidence_without_dropping_ranked_candidates():
    pairs = [candidate()] + [
        candidate(f"otm-{index}", strike=22050 + index) for index in range(200)
    ]
    stale = [
        pairs[0][0].model_copy(
            update={"token": f"stale-{index}", "master_date": NOW.date() - timedelta(days=1)}
        )
        for index in range(200)
    ]
    report = Resolver().assess(
        [*[item for item, _ in pairs], *stale],
        {item.token: quote for item, quote in pairs},
        22000,
        "CE",
        NOW,
        StrategyConfig(),
    )
    assert len(report["candidates"]) == 100
    assert report["omitted_candidates"] == 301
    assert report["ranked_tokens"] == ["candidate"]


def test_selector_explains_excluded_metadata_without_changing_rank_or_inventing_quotes():
    item, quote = candidate()
    day = NOW.date()
    variants = [
        item.model_copy(update={"token": "stale", "master_date": day - timedelta(days=1)}),
        item.model_copy(update={"token": "expired", "expiry": day - timedelta(days=1)}),
        item.model_copy(update={"token": "disabled", "tradable": False}),
        item.model_copy(update={"token": "expiry-day", "expiry": day}),
        item.model_copy(update={"token": "later", "expiry": item.expiry + timedelta(days=7)}),
    ]
    report = Resolver().assess(
        [item, *variants], {item.token: quote}, 22000, "CE", NOW, StrategyConfig()
    )
    rows = {row["instrument"]["token"]: row for row in report["candidates"]}
    expected = {
        "stale": "MASTER_STALE",
        "expired": "CONTRACT_EXPIRED",
        "disabled": "CONTRACT_NOT_TRADABLE",
        "expiry-day": "EXPIRY_DAY_AVOIDED",
        "later": "OUTSIDE_SELECTED_EXPIRY",
    }
    assert report["ranked_tokens"] == [item.token]
    for token, reason in expected.items():
        assert rows[token]["reasons"] == [reason]
        assert rows[token]["rank"] is rows[token]["quote"] is None
        assert rows[token]["moneyness"] == "NOT_ASSESSED"
    reversed_report = Resolver().assess(
        list(reversed([item, *variants])), {item.token: quote}, 22000, "CE", NOW, StrategyConfig()
    )
    assert reversed_report == report
