"""Hand-calculated paper analytics fixtures; no market or broker connection."""

from datetime import timedelta
from decimal import Decimal

import pytest

from services.nifty_algo.analytics import performance
from test.test_nifty_algo_research import START, trade


def exit_row(identifier, net, minute, **changes):
    return trade(
        identifier, net + 10, 10, START, START + timedelta(minutes=minute),
        fill_id=f"{identifier}-{minute}", **changes,
    )


def test_partial_exits_keep_fill_chronology_for_equity_and_drawdown():
    rows = [
        exit_row("one", 100, 10, planned_risk="400"),
        exit_row("one", -300, 20, planned_risk="400"),
        exit_row("one", 400, 30, planned_risk="400"),
    ]
    result = performance(rows, "1000")
    assert result["trades"] == 1
    assert result["win_rate"] == 1
    assert Decimal(result["total_net"]) == 200
    assert [Decimal(point["equity"]) for point in result["equity_curve"]] == [1100, 800, 1200]
    assert Decimal(result["maximum_drawdown"]) == 300
    assert Decimal(result["average_realized_r"]) == Decimal("0.5")


def test_missing_planned_risk_is_unavailable_not_zero():
    result = performance([exit_row("one", 100, 10)], "1000")
    assert result["average_realized_r"] is None
    assert result["risk_coverage"] == {"available": 0, "total": 1, "reason": "PLANNED_RISK_MISSING"}
    assert performance([], "1000")["expectancy"] is None


def test_period_summary_counts_partial_exits_once_and_reconciles_gross_costs():
    result = performance([
        exit_row("one", 100, 10),
        exit_row("one", -300, 20),
        exit_row("two", 400, 30),
        exit_row("three", 0, 40),
    ], "1000")
    assert result["trades"] == 3
    assert result["fills"] == 4
    assert result["wins"] == result["losses"] == result["breakeven"] == 1
    assert Decimal(result["total_gross"]) == 240
    assert Decimal(result["costs"]) == 40
    assert Decimal(result["total_net"]) == 200
    assert Decimal(result["best"]) == 400
    assert Decimal(result["worst"]) == -200
    empty = performance([], "1000")
    assert empty["best"] is empty["worst"] is None


@pytest.mark.parametrize("quantity", [True, 1.5, "25", 0, -1])
def test_invalid_journal_quantity_is_rejected(quantity):
    row = exit_row("one", 100, 10) | {"quantity": quantity}
    with pytest.raises(ValueError, match="quantity"):
        performance([row], "1000")


@pytest.mark.parametrize(
    "change",
    [
        {"instrument": {"kind": "PE", "expiry": "2026-11-24"}},
        {"instrument": {"kind": "CE", "expiry": "2026-12-01"}},
        {"planned_risk": "300"},
        {"opened": (START + timedelta(minutes=1)).isoformat()},
    ],
)
def test_partial_exits_cannot_merge_conflicting_entry_identity(change):
    first = exit_row("one", 100, 10, planned_risk="400")
    second = exit_row("one", -50, 20, planned_risk="400") | change
    with pytest.raises(ValueError, match="Conflicting"):
        performance([first, second], "1000")


def test_equal_timestamp_results_have_stable_fill_order():
    rows = [exit_row("alpha", 100, 10), exit_row("beta", -100, 10)]
    assert performance(rows, "1000") == performance(list(reversed(rows)), "1000")


def test_observed_equity_drawdown_never_relabels_realized_drawdown():
    result = performance(
        [exit_row("one", 100, 10)], "1000",
        [
            {"timestamp": START.isoformat(), "equity": "1100"},
            {"timestamp": (START + timedelta(minutes=1)).isoformat(), "equity": "700"},
        ],
    )
    assert Decimal(result["maximum_drawdown"]) == 0
    assert Decimal(result["observed_maximum_drawdown"]) == 400
    assert result["basis"] == "PAPER_FILLS_REALIZED"
    assert performance([], "1000")["observed_maximum_drawdown"] is None


def test_daily_groups_recognize_partial_exit_on_its_own_session():
    rows = [exit_row("one", 100, 10), exit_row("one", -50, 24 * 60 + 10)]
    result = performance(rows, "1000")
    daily = result["groups"]["daily"]
    assert Decimal(daily["2026-11-19"]["net"]) == 100
    assert Decimal(daily["2026-11-20"]["net"]) == -50
    assert daily["2026-11-19"]["trades"] == daily["2026-11-20"]["trades"] == 1
