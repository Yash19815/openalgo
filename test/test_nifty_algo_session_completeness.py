"""Live/replay opening and historical tail regressions, synthetic histories."""

from copy import deepcopy
from datetime import datetime, timedelta

from services.nifty_algo.config import StrategyConfig
from services.nifty_algo.execution_replay import MarketFrame, decision_at
from test.test_nifty_algo_execution_completion import NOW, warmed_frame


def test_replay_refuses_missing_opening_bucket_even_with_opening_minute():
    payload = warmed_frame()["payload"]
    opening = NOW.replace(hour=3, minute=46)
    payload["minute_bars"] = [
        b for b in payload["minute_bars"] if datetime.fromisoformat(b["start"]) != opening
    ]
    frame = MarketFrame.model_validate(payload)
    result = decision_at(frame, NOW, StrategyConfig())
    assert "SESSION_VWAP_INCOMPLETE" in result["reasons"]
    assert not result["eligible"]


def test_missing_previous_tail_is_discarded_from_warmup():
    payload = warmed_frame()["payload"]
    previous = NOW.date() - timedelta(days=1)
    tail = NOW.replace(
        year=previous.year, month=previous.month, day=previous.day, hour=9, minute=59
    )
    missing = deepcopy(payload)
    missing["minute_bars"] = [
        b for b in missing["minute_bars"] if datetime.fromisoformat(b["start"]) != tail
    ]
    assert len(missing["minute_bars"]) == len(payload["minute_bars"]) - 1
    result = decision_at(MarketFrame.model_validate(missing), NOW, StrategyConfig())
    assert result["higher"]["supertrend"] is None  # Only five 15-minute bars remain.
    assert not result["eligible"]


def test_whole_missing_session_and_missing_calendar_row_cannot_bridge_warmup():
    payload = warmed_frame()["payload"]
    previous = NOW.date() - timedelta(days=1)
    payload["minute_bars"] = [
        b for b in payload["minute_bars"] if datetime.fromisoformat(b["start"]).date() != previous
    ]
    result = decision_at(MarketFrame.model_validate(payload), NOW, StrategyConfig())
    assert previous.isoformat() in result["discarded_incomplete_sessions"]
    assert result["higher"]["supertrend"] is None
    payload["sessions"] = [s for s in payload["sessions"] if s["date"] != previous.isoformat()]
    missing_calendar = decision_at(MarketFrame.model_validate(payload), NOW, StrategyConfig())
    assert previous.isoformat() in missing_calendar["discarded_incomplete_sessions"]
    assert not missing_calendar["eligible"]
