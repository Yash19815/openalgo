"""Calendar disagreement locks entries without disabling protective PAPER sells."""

from datetime import date, timedelta

import pytest

from services.nifty_algo import calendar
from test.test_nifty_algo_calendar import FakeMarketCalendar, approved
from test.test_nifty_algo_calendar import store as calendar_feature_store
from test.test_nifty_algo_paper_executor import (
    NOW,
    USER,
    buy_intent,
    executor,
    market_calendar,
    running,
)
from test.test_nifty_algo_paper_executor import store as feature_store


@pytest.fixture
def store(request):
    return request.getfixturevalue("feature_store")


@pytest.fixture
def calendar_store(request):
    return request.getfixturevalue("calendar_feature_store")


def test_native_holiday_cannot_be_reopened_by_timing_fallback(calendar_store, monkeypatch):
    monkeypatch.setattr(calendar, "_legacy_calendar", lambda: FakeMarketCalendar())
    approved(calendar_store)
    result = calendar.nifty_session("alice", date(2026, 1, 12), store=calendar_store)
    assert result["status"] == "CALENDAR_DISAGREEMENT"
    assert result["window"] is None


def test_calendar_loss_does_not_block_fresh_protective_sell(store):
    running(store)
    exe = executor(store)
    exe.admit(buy_intent())
    assert exe.process(NOW + timedelta(seconds=1))[0]["status"] == "FILLED"
    exe.session_reader = lambda day, exchange: None
    exe.admit(buy_intent(intent_id="protective-close", side="SELL"), NOW + timedelta(seconds=2))
    result = exe.process(NOW + timedelta(seconds=3))
    assert result and result[0]["status"] == "FILLED"
    assert store.positions(USER) == []
