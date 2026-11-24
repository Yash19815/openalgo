"""Synthetic research fixtures, isolated from any account or market connection."""

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from services.nifty_algo.analytics import performance
from services.nifty_algo.config import StrategyConfig
from services.nifty_algo.models import Candle
from services.nifty_algo.research import (
    expire_opportunity,
    observe_opportunity,
    opportunity_from_decision,
    options_replay,
    signal_study,
    walk_forward_windows,
)

START = datetime(2026, 11, 19, 4, 0, tzinfo=UTC)


def bars(count):
    return [
        Candle(
            token="fixture_future",
            start=START + timedelta(minutes=i),
            end=START + timedelta(minutes=i + 1),
            timeframe=1,
            open=100 + i,
            high=101 + i,
            low=99 + i,
            close=100 + i,
            volume=10,
            provenance="TEST_FIXTURE",
        )
        for i in range(count)
    ]


def trade(identifier, gross, charges, opened, closed, **changes):
    return dict(
        trade_id=identifier,
        gross=str(gross),
        charges=str(charges),
        net=str(gross - charges),
        quantity=25,
        opened=opened.isoformat(),
        closed=closed.isoformat(),
        instrument={"kind": "CE", "expiry": "2026-11-24"},
        **changes,
    )


def test_signal_study_future_input_cannot_change_prior_decision():
    config = StrategyConfig()
    end = START + timedelta(minutes=31)
    kwargs = {"session_opens": {date(2026, 11, 19): START}}
    first = signal_study(bars(30), config, START, end, **kwargs)
    longer = signal_study(bars(60), config, START, end + timedelta(minutes=30), **kwargs)
    assert first["decisions"] == longer["decisions"][: len(first["decisions"])]
    assert first["performance"] is None
    assert first["trades"] == []
    assert all(not decision["eligible"] for decision in first["decisions"])
    with pytest.raises(ValueError, match="Effective session"):
        signal_study(bars(30), config, START, end, session_opens={})


def test_option_replay_refuses_candle_substitution():
    with pytest.raises(ValueError, match="OPTION_REPLAY_UNAVAILABLE"):
        options_replay(bars(30))


def test_metrics_hand_calculation_and_partial_exit_consolidation():
    journal = [
        trade("one", 60, 10, START, START + timedelta(minutes=10)),
        trade("one", 60, 10, START, START + timedelta(minutes=20)),
        trade("two", -40, 10, START, START + timedelta(minutes=30)),
    ]
    result = performance(journal, "1000")
    assert result["trades"] == 2
    assert result["total_net"] == "50"
    assert result["costs"] == "30"
    assert result["win_rate"] == 0.5
    assert result["profit_factor"] == 2
    assert result["maximum_drawdown"] == "50"
    assert result["average_duration_seconds"] == 1500


def test_analytics_rejects_nonfinite_and_unreconciled_costs():
    with pytest.raises(ValueError):
        performance([], "NaN")
    row = trade("one", 60, 10, START, START + timedelta(minutes=10))
    with pytest.raises(ValueError, match="reconcile"):
        performance([row | {"net": "100"}], "1000")
    with pytest.raises(ValueError, match="Duplicate fill"):
        performance([row | {"fill_id": "same"}] * 2, "1000")


def test_walk_forward_windows_half_open_nonoverlapping():
    windows = walk_forward_windows(START, START + timedelta(days=40))
    assert len(windows) == 4
    assert all(window["train_end"] == window["test_start"] for window in windows)
    assert all(
        left["test_end"] == right["test_start"]
        for left, right in zip(windows, windows[1:], strict=False)
    )
    assert all(window["interval_convention"] == "[start, end)" for window in windows)
    with pytest.raises(ValueError):
        walk_forward_windows(START, START + timedelta(days=40), test_days=0)


def opportunity(end=START + timedelta(minutes=30), side="CE"):
    config = StrategyConfig()
    return opportunity_from_decision(
        {
            "decision_id": "d",
            "eligible": True,
            "side": side,
            "config_id": config.version_id,
            "analysis_token": "fixture_future",
            "snapshot": {"end": end.isoformat(), "price": 100.0, "supertrend": {"atr": 2.0}},
        },
        config,
    )


def step(at, price, token="fixture_future"):
    return {"token": token, "price": price, "at": at.isoformat()}


def test_opportunity_observation_is_causal_and_ordered():
    row = opportunity()
    end = datetime.fromisoformat(row["candle_end"])
    assert row["status"] == "OBSERVING" and row["research_only"] is True
    assert datetime.fromisoformat(row["deadline"]) == end + timedelta(minutes=45)
    # The signal candle itself, a reordered candle and another future are ignored.
    assert observe_opportunity(row, step(end, 150)) == row
    assert observe_opportunity(row, step(end + timedelta(minutes=5), 150, "other")) == row
    later = observe_opportunity(row, step(end + timedelta(minutes=10), 101))
    assert observe_opportunity(later, step(end + timedelta(minutes=5), 150)) == later
    assert later["max_favorable"] == "1.0" and len(later["steps"]) == 1
    # A candle beyond the deadline stops the row without being applied.
    late = observe_opportunity(later, step(end + timedelta(minutes=50), 150))
    assert late["outcome"] == "WINDOW_45M" and len(late["steps"]) == 1
    assert observe_opportunity(late, step(end + timedelta(minutes=55), 150)) == late
    assert expire_opportunity(row, end + timedelta(minutes=44))["status"] == "OBSERVING"
    assert expire_opportunity(row, end + timedelta(minutes=45))["outcome"] == "WINDOW_45M"


def test_adverse_threshold_stops_and_unobservable_signals_are_skipped():
    row = opportunity(side="PE")
    end = datetime.fromisoformat(row["candle_end"])
    stopped = observe_opportunity(row, step(end + timedelta(minutes=5), 102))
    assert stopped["outcome"] == "THRESHOLD_ADVERSE" and stopped["max_adverse"] == "2.0"
    config = StrategyConfig()
    base = {"eligible": True, "side": "CE", "config_id": config.version_id}
    for snapshot in (
        {"end": end.isoformat(), "price": 100.0},
        {"end": end.isoformat(), "price": 100.0, "supertrend": {"atr": 0}},
        {"end": end.replace(tzinfo=None).isoformat(), "price": 100.0, "supertrend": {"atr": 1}},
    ):
        assert opportunity_from_decision({**base, "snapshot": snapshot}, config) is None
