"""Observed-history assessment fixtures, isolated from credentials and networks."""

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

from services.nifty_algo.assessment import assess_current
from services.nifty_algo.config import StrategyConfig

IST = ZoneInfo("Asia/Kolkata")
OPEN = datetime(2026, 11, 19, 9, 15, tzinfo=IST)
NOW = OPEN + timedelta(minutes=16)
FUTURE = {
    "name": "NIFTY",
    "symbol": "actual-listed-future",
    "token": "15",
    "exchange": "NFO",
    "instrumenttype": "FUTIDX",
    "expiry": "24-NOV-26",
    "lotsize": 65,
    "tick_size": 0.1,
    "strike": 0,
}


def candles(count=18):
    return [
        {
            "timestamp": (OPEN + timedelta(minutes=i)).timestamp(),
            "open": 24000 + i,
            "high": 24002 + i,
            "low": 23999 + i,
            "close": 24001 + i,
            "volume": 100,
        }
        for i in range(count)
    ]


def session(day, exchange):
    assert exchange == "NFO"
    opening = OPEN.replace(year=day.year, month=day.month, day=day.day)
    return {
        "start_ms": opening.timestamp() * 1000,
        "end_ms": (opening + timedelta(hours=6)).timestamp() * 1000,
    }


def assess(rows=None, instruments=None, **kwargs):
    history = Mock(return_value=(True, {"status": "success", "data": rows or candles()}, 200))
    result = assess_current(
        "offline-test-key",
        StrategyConfig(),
        NOW,
        instrument_loader=lambda: instruments if instruments is not None else [FUTURE],
        history_reader=history,
        session_reader=kwargs.get("session_reader", session),
    )
    return result, history


def test_native_history_arguments_are_authenticated_bounded_and_read_only():
    decision, history = assess()
    history.assert_called_once_with(
        symbol=FUTURE["symbol"],
        exchange="NFO",
        interval="1m",
        start_date="2026-11-10",
        end_date="2026-11-19",
        api_key="offline-test-key",
    )
    assert decision["source"] == "OBSERVED_BROKER_HISTORY"
    assert decision["history"] == {
        "start_date": "2026-11-10",
        "end_date": "2026-11-19",
        "minute_bars": 16,
        "entry_bars": 3,
        "confirmation_bars": 1,
    }
    assert decision["snapshot"]["end"] == (OPEN + timedelta(minutes=15)).astimezone(UTC).isoformat()
    assert decision["eligible"] is False
    assert decision["final_action"] == "NO_ORDER"
    assert decision["risk"]["approved"] is False
    assert decision["pcr"] is None
    assert (
        next(check for check in decision["checks"] if check["rule"] == "R-PCR")["state"]
        == "UNAVAILABLE"
    )


def test_missing_or_non_nifty_future_never_fetches_history():
    decision, history = assess(instruments=[{**FUTURE, "name": "BANKNIFTY"}])
    history.assert_not_called()
    assert decision["analysis_instrument"] is None
    assert "R-HISTORY: CURRENT_NIFTY_FUTURE_UNAVAILABLE" in decision["reasons"]


def test_closed_native_session_excludes_all_candles():
    decision, _ = assess(session_reader=lambda *_: None)
    assert decision["history"]["minute_bars"] == 0
    assert decision["snapshot"] == {}


def test_causal_result_unchanged_by_unfinished_future_prices():
    original, _ = assess()
    rows = candles()
    rows[-1].update(open=100000, high=100001, low=99999, close=100000)
    changed, _ = assess(rows)
    assert changed == original


@pytest.mark.parametrize(
    "changes",
    [
        {"timestamp": "unparseable"},
        {"timestamp": OPEN.timestamp() + 1},
        {"close": float("nan")},
        {"volume": -1},
        {"volume": True},
        {"high": 100},
    ],
)
def test_malformed_completed_history_fails_closed(changes):
    rows = candles()
    rows[0].update(changes)
    with pytest.raises(ValueError):
        assess(rows)


def test_duplicate_candle_and_oversized_response_fail_closed():
    with pytest.raises(ValueError, match="Duplicate"):
        assess(candles() + [candles()[0]])
    with pytest.raises(ValueError, match="10000"):
        assess([candles()[0]] * 10001)


def test_history_failure_is_explainable_and_does_not_expose_broker_error():
    decision = assess_current(
        "offline-key",
        StrategyConfig(),
        NOW,
        instrument_loader=lambda: [FUTURE],
        history_reader=lambda **_: (False, {"message": "private upstream error"}, 403),
        session_reader=session,
    )
    assert decision["final_action"] == "NO_ORDER"
    assert "R-HISTORY: HISTORY_UNAVAILABLE" in decision["reasons"]
    assert "private upstream error" not in str(decision)
