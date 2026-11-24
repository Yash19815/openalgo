"""Exit studies consume validated samples without changing exits or P&L."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from services.nifty_algo.config import StrategyConfig
from services.nifty_algo.models import Quote
from services.nifty_algo.protection import initial_protection, observe_bid
from test.test_nifty_algo_analytics_integration import round_trip
from test.test_nifty_algo_paper_executor import NOW, USER
from test.test_nifty_algo_paper_executor import market_calendar as market_calendar
from test.test_nifty_algo_safety_center import client as client
from test.test_nifty_algo_safety_center import login
from test.test_nifty_algo_safety_center import store as store


def closed_trade(store):
    round_trip(store)
    return store.analytics_snapshot(USER, NOW, NOW + timedelta(days=1))["details"]["items"][0]


def test_trade_detail_reconciles_fills_without_claiming_unobserved_extremes(store):
    trade = closed_trade(store)
    detail = store.trade_detail(USER, trade["id"])
    assert detail["net"] == trade["net"] and detail["mode"] == "PAPER"
    assert detail["exit_effectiveness"]["mae_gross"] is None
    assert detail["post_exit"]["status"] == "UNAVAILABLE"
    assert store.trade_detail("other", trade["id"]) is None


def test_observed_mae_mfe_and_stop_history_never_change_protection_result():
    config = StrategyConfig()
    state = initial_protection(
        100, Decimal(".05"), config, {"score": 80, "method": config.confidence_method}
    )
    result = observe_bid(state, 100, 102, Decimal(".05"), config, source_time=NOW)
    assert result["highest_bid"] == result["lowest_bid"] == "102"
    assert result["observation_count"] == 1
    assert result["stop_history"][0]["stop_price"] == result["stop_price"]
    result["last_source_time"] = NOW.isoformat()
    second = observe_bid(
        result, 100, 101, Decimal(".05"), config, source_time=NOW + timedelta(seconds=2)
    )
    assert second["lowest_bid"] == "101" and second["highest_bid"] == "102"
    assert second["stop_price"] == result["stop_price"]
    assert second["max_observation_gap_seconds"] == 2


def test_post_exit_samples_continue_past_45_minutes_to_effective_close(store):
    trade = closed_trade(store)
    detail = store.trade_detail(USER, trade["id"])
    closed = datetime.fromisoformat(detail["closed_at"])
    close = NOW.replace(hour=10, minute=0, second=0, microsecond=0)
    before = store.analytics_snapshot(USER, NOW, NOW + timedelta(days=1))
    for minutes in (5, 15, 30, 46, 60):
        stamp = closed + timedelta(minutes=minutes)
        quote = Quote(
            token=detail["instrument"]["token"],
            source_time=stamp,
            received_time=stamp,
            bid=Decimal(165 + minutes),
            ask=Decimal(166 + minutes),
            bid_size=100,
            ask_size=100,
            provider="TEST_FIXTURE",
        )
        assert store.observe_exit_study(USER, trade["id"], quote, stamp, close, 1)
        assert not store.observe_exit_study(USER, trade["id"], quote, stamp, close, 1)
    result = store.trade_detail(USER, trade["id"])["post_exit"]
    assert result["samples"] == 5 and set(result["checkpoints"]) == {"300", "900", "1800"}
    assert datetime.fromisoformat(result["session_close"]) == close
    assert store.analytics_snapshot(USER, NOW, NOW + timedelta(days=1)) == before
    late = quote.model_copy(
        update={
            "source_time": close + timedelta(seconds=1),
            "received_time": close + timedelta(seconds=1),
        }
    )
    assert not store.observe_exit_study(
        USER, trade["id"], late, close + timedelta(seconds=1), close, 1
    )


def test_post_exit_refuses_stale_wrong_token_and_changed_calendar(store):
    trade = closed_trade(store)
    detail = store.trade_detail(USER, trade["id"])
    stamp = NOW + timedelta(minutes=6)
    close = NOW + timedelta(hours=4)
    quote = Quote(
        token=detail["instrument"]["token"],
        source_time=stamp,
        received_time=stamp,
        bid=170,
        ask=171,
        bid_size=100,
        ask_size=100,
        provider="TEST_FIXTURE",
    )
    assert not store.observe_exit_study(
        USER, trade["id"], quote.model_copy(update={"token": "wrong"}), stamp, close, 1
    )
    assert not store.observe_exit_study(
        USER, trade["id"], quote, stamp + timedelta(seconds=3), close, 1
    )
    assert store.observe_exit_study(USER, trade["id"], quote, stamp, close, 1)
    next_quote = quote.model_copy(
        update={
            "source_time": stamp + timedelta(seconds=1),
            "received_time": stamp + timedelta(seconds=1),
        }
    )
    assert not store.observe_exit_study(
        USER, trade["id"], next_quote, stamp + timedelta(seconds=1), close, 2
    )


def test_trade_detail_api_uses_owner_session_and_no_store(client, store):
    trade = closed_trade(store)
    headers = login(client)
    result = client.get(f"/api/nifty-algo/analytics/trades/{trade['id']}", headers=headers)
    assert result.status_code == 200 and result.json["data"]["mode"] == "PAPER"
    login(client, "other")
    assert client.get(f"/api/nifty-algo/analytics/trades/{trade['id']}").status_code == 404
