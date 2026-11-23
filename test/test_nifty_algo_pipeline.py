"""Explicit deterministic market simulator. No historical or live data claims."""

import ast
import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from services.nifty_algo.assessment import assess_current
from services.nifty_algo.config import StrategyConfig
from services.nifty_algo.native_data import NativeDataAdapter
from services.nifty_algo.paper_executor import NiftyPaperExecutor
from services.nifty_algo.runner import NiftyRunner, attach_runner
from test.nifty_calendar_helpers import seed_nifty_calendar_dependencies
from test.test_nifty_algo_paper_executor import IST, NOW, USER, running
from test.test_nifty_algo_paper_executor import store as feature_store


@pytest.fixture
def store(request):
    value = request.getfixturevalue("feature_store")
    seed_nifty_calendar_dependencies(value, USER, NOW.astimezone(IST).year)
    return value


def session(day, exchange):
    """Artificial sessions, including weekends, solely for causal replay tests."""
    assert exchange == "NFO"
    opening = NOW.replace(year=day.year, month=day.month, day=day.day, hour=3, minute=45)
    return {
        "start_ms": opening.timestamp() * 1000,
        "end_ms": (opening + timedelta(minutes=375)).timestamp() * 1000,
    }


def minute_rows():
    rows = []
    for day in range(9):
        opening = NOW.replace(hour=3, minute=45) - timedelta(days=8 - day)
        for minute in range(375 if day < 8 else 75):
            price = 24000 + day * 100 + minute * 0.2
            if day == 8 and minute >= 15:
                price -= min(minute - 15, 24)
            if day == 8 and minute >= 39:
                price += (minute - 39) * 8
            rows.append(
                {
                    "timestamp": (opening + timedelta(minutes=minute)).timestamp(),
                    "open": price,
                    "high": price + 1,
                    "low": price - 1,
                    "close": price,
                    "volume": 100,
                }
            )
    return rows


def master_rows():
    common = {
        "name": "NIFTY",
        "exchange": "NFO",
        "expiry": "24-NOV-26",
        "lotsize": 25,
        "tick_size": 0.05,
    }
    return [
        {
            **common,
            "symbol": "OFFLINE_FUTURE",
            "token": "15",
            "instrumenttype": "FUTIDX",
            "strike": 0,
        },
        {
            **common,
            "symbol": "OFFLINE_CE",
            "token": "ce",
            "instrumenttype": "OPTIDX",
            "strike": 25000,
        },
        {
            **common,
            "symbol": "OFFLINE_PE",
            "token": "pe",
            "instrumenttype": "OPTIDX",
            "strike": 25000,
        },
        {
            "name": "NIFTY",
            "exchange": "NSE_INDEX",
            "symbol": "NIFTY",
            "token": "spot",
            "instrumenttype": "AMXIDX",
        },
    ]


class DeterministicMarket:
    def __init__(self):
        self.stamp, self.bid, self.ask = NOW, 99, 100
        self.bid_size = self.ask_size = 100
        self.missing_oi, self.missing_time, self.stale_put = False, False, False

    def get_all_data(self, symbol, exchange):
        source = (
            self.stamp - timedelta(seconds=100)
            if symbol.endswith("PE") and self.stale_put
            else self.stamp
        )
        raw = {
            "ltt": source.timestamp() * 1000,
            "received_time": self.stamp.timestamp(),
            "ltp": 25000 if symbol == "NIFTY" else getattr(self, "ltp", 100),
            "volume": 5000,
            "oi": (200 if symbol.endswith("PE") else 100),
            "depth": {
                "buy": [{"price": self.bid, "quantity": self.bid_size}],
                "sell": [{"price": self.ask, "quantity": self.ask_size}],
            },
        }
        if self.missing_oi:
            raw["oi"] = None
        if self.missing_time:
            raw.pop("ltt")
        return {"source_observations": {"3" if exchange == "NFO" else "2": raw}}


def pipeline(market=None, master=None):
    market = market or DeterministicMarket()
    return NativeDataAdapter(
        instrument_loader=master_rows,
        market_data=market,
        master_reader=(
            master or (lambda: {"is_ready": True, "download_date": "2026-11-19", "broker": "angel"})
        ),
        clock=lambda: market.stamp,
    )


def assess(native, now=NOW, rows=None, config=None):
    return assess_current(
        "offline-only",
        config or StrategyConfig(),
        now,
        native=native,
        history_reader=lambda **kwargs: (
            True,
            {"status": "success", "data": rows or minute_rows()},
            200,
        ),
        session_reader=session,
        observation_only=False,
    )


def test_real_calculations_connect_complete_pcr_to_eligible_confidence():
    now = NOW - timedelta(minutes=30)
    market = DeterministicMarket()
    market.stamp = now
    decision = assess(pipeline(market), now=now)
    assert decision["eligible"]
    assert all(c["state"] == "PASS" for c in decision["checks"])
    assert decision["pcr"]["value"] == 2 and "2026-11-24" in decision["pcr"]["scope"]
    assert decision["pcr_readiness"]["expected_contracts"] == 2
    assert len(decision["confidence"]["contributions"]) == 5
    assert decision["confidence"]["score"] == pytest.approx(61.970368)
    assert Decimal(".10") <= Decimal(decision["confidence"]["target_fraction"]) <= Decimal(".15")


@pytest.mark.parametrize("fault", ["missing_oi", "missing_time", "stale_put"])
def test_incomplete_or_stale_pcr_cannot_become_executable(fault):
    market = DeterministicMarket()
    setattr(market, fault, True)
    decision = assess(pipeline(market))
    assert not decision["eligible"] and decision["confidence"] is None
    assert decision["pcr"] is None
    assert decision["pcr_readiness"]["reason"] == "COMPLETE_TIMESTAMPED_CHAIN_UNAVAILABLE"


def test_definition_is_preserved_and_master_date_is_required():
    native = pipeline()
    result = native.get_pcr(StrategyConfig(pcr_kind="VOLUME"), NOW)
    assert result["pcr"].kind == "VOLUME" and result["pcr"].value == 1
    old = pipeline(master=lambda: {"is_ready": True, "download_date": "2026-11-18"})
    decision = assess(old)
    assert not decision["eligible"] and decision["pcr"] is None
    assert decision["pcr_readiness"]["reason"] == "MASTER_FRESHNESS_UNVERIFIED"


def test_ordered_causal_history_and_missing_session_open():
    rows = minute_rows()
    rows[-1], rows[-2] = rows[-2], rows[-1]
    with pytest.raises(ValueError, match="Out-of-order"):
        assess(pipeline(), rows=rows)
    missing = [
        r for r in minute_rows() if r["timestamp"] != NOW.replace(hour=3, minute=45).timestamp()
    ]
    result = assess(pipeline(), rows=missing)
    assert not result["eligible"] and "SESSION_VWAP_INCOMPLETE" in result["reasons"]
    baseline = assess(pipeline())
    future = {**minute_rows()[-1], "timestamp": NOW.timestamp(), "close": 90000, "high": 90001}
    assert assess(pipeline(), rows=minute_rows() + [future]) == baseline


@pytest.mark.parametrize("analyzer", [True, False, "changed-mid-session"])
def test_offline_end_to_end_runner_never_calls_order_services(store, monkeypatch, analyzer):
    # A transport spy, plus import-graph assertions below, checks isolation.
    spy = Mock(side_effect=AssertionError("Live/generic order boundary reached"))
    monkeypatch.setitem(
        sys.modules, "services.place_order_service", SimpleNamespace(place_order=spy)
    )
    monkeypatch.setitem(
        sys.modules, "services.place_smart_order_service", SimpleNamespace(place_smart_order=spy)
    )
    import database.settings_db as settings

    mode = {"enabled": analyzer is True}
    monkeypatch.setattr(settings, "get_analyze_mode", lambda: mode["enabled"])
    running(store)
    config = StrategyConfig(slippage_ticks=0)
    with store.sessions.begin() as db:
        from database.nifty_algo_db import NiftyState

        row = db.get(NiftyState, USER)
        row.configuration, row.configuration_id = config.model_dump(mode="json"), config.version_id
    market = DeterministicMarket()
    market.bid, market.ask, market.ltp = 164, 165, 164.5
    native = pipeline(market)
    rows = minute_rows()
    history = rows[:-75]
    for minute, row in enumerate(rows[-75:]):
        price = 24800 + minute * 0.2
        if minute >= 15:
            price -= min(minute - 15, 24)
        if minute >= 46:
            price += (minute - 46) * 0.5
        history.append(
            row
            | {
                "open": price,
                "high": price + 1,
                "low": price - 1,
                "close": price,
            }
        )
    exe = NiftyPaperExecutor(
        store, USER, config, market, clock=lambda: market.stamp, session_reader=session
    )
    reads = Mock(side_effect=lambda config, now: assess(native, now, history, config))
    runner = NiftyRunner(
        store,
        USER,
        native=native,
        executor=exe,
        assessment=reads,
        clock=lambda: NOW - timedelta(seconds=1),
    )
    runner.protect(NOW - timedelta(seconds=1))
    decision = runner.evaluate(NOW)
    assert decision is not None, runner.last_issue
    assert decision["eligible"] and len(store.pending_orders(USER)) == 1
    assert runner.evaluate(NOW + timedelta(seconds=1)) is None and reads.call_count == 1
    market.stamp = NOW + timedelta(seconds=1)
    runner.protect(market.stamp)
    assert len(store.positions(USER)) == 1
    if analyzer == "changed-mid-session":
        mode["enabled"] = True
    market.bid, market.ask, market.stamp = 172, 172.5, NOW + timedelta(seconds=2)
    runner.protect(market.stamp)
    assert Decimal(store.positions(USER)[0]["protection"]["stop_price"]) == Decimal("170.5")
    state = store.read(USER)
    store.change(USER, state["revision"], action="kill-switch")
    market.bid, market.ask, market.bid_size, market.stamp = (
        250,
        250.5,
        1,
        NOW + timedelta(seconds=3),
    )
    # A positive but insufficient bid can trigger TARGET, never fill the exit.
    runner.protect(market.stamp)
    assert store.positions(USER) and store.pending_orders(USER)[0]["side"] == "SELL"
    market.bid_size = 100
    market.stamp = NOW + timedelta(seconds=4)
    runner.protect(market.stamp)
    assert store.positions(USER) == []
    journal = store.trades(USER)[0]
    assert journal["reason"] == "TARGET"
    assert journal["entry_context"]["confidence"]["contributions"]
    assert Decimal(journal["net"]) == Decimal(journal["gross"]) - Decimal(journal["fees"])
    assert not spy.called


def test_feature_has_no_order_placement_imports():
    for path in Path("services/nifty_algo").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules = (
                [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else [n.name for n in node.names]
                if isinstance(node, ast.Import)
                else []
            )
            assert not any(
                name.startswith(
                    ("broker.", "sandbox.", "services.place_order", "services.place_smart_order")
                )
                for name in modules
            )


def test_scheduler_attaches_once_with_independent_exit_job(store):
    from flask import Flask

    app = Flask(__name__)
    app.extensions["nifty_algo_store"] = store
    scheduler = Mock()
    runner = attach_runner(app, scheduler, USER)
    assert attach_runner(app, scheduler, USER) is runner
    assert scheduler.add_job.call_count == 4
    calls = scheduler.add_job.call_args_list
    assert calls[0].kwargs["seconds"] == 1 and calls[1].kwargs["seconds"] == 5
    assert calls[2].kwargs["id"].endswith(":reports") and calls[2].kwargs["seconds"] == 60
    assert calls[3].kwargs["id"].endswith(":capture") and calls[3].kwargs["seconds"] == 5
    assert all(c.kwargs["max_instances"] == 1 and c.kwargs["coalesce"] for c in calls)


def test_malformed_master_cannot_silently_shrink_pcr_universe():
    native = pipeline()
    native.instrument_loader = lambda: (
        master_rows()
        + [{**master_rows()[1], "token": "broken", "symbol": "OTHER_CE", "lotsize": None}]
    )
    result = native.get_pcr(StrategyConfig(), NOW)
    assert result["pcr"] is None and result["reason"] == "MASTER_UNIVERSE_INVALID"


def test_native_subscriptions_reuse_client_and_do_not_duplicate(store, monkeypatch):
    import database.auth_db as auth
    import services.market_data_service as cache
    import services.nifty_algo.runner as module
    import services.websocket_service as sockets

    monkeypatch.setattr(auth, "get_api_key_for_tradingview", lambda _: "offline-key")
    monkeypatch.setattr(auth, "get_broker_name", lambda _: "angel")
    active = [{"exchange": "NSE_INDEX", "symbol": "NIFTY", "mode": "Quote"}]
    client = Mock(connected=True, authenticated=True)
    client.get_subscriptions.side_effect = lambda: {"subscriptions": list(active)}

    def subscribe(symbols, mode):
        entries = [{**row, "mode": mode, "status": "success"} for row in symbols]
        active.extend(entries)
        return {"status": "success", "subscriptions": entries}

    client.subscribe.side_effect = subscribe
    monkeypatch.setattr(sockets, "get_websocket_connection", lambda _: (True, client, None))
    service = Mock()
    service.health_monitor.get_health.return_value = {"reconnect_count": 0}
    monkeypatch.setattr(cache, "get_market_data_service", lambda: service)
    monkeypatch.setattr(module, "assess_current", lambda *args, **kwargs: {"offline": True})
    runner = NiftyRunner(store, USER, native=pipeline(), clock=lambda: NOW)
    assert runner._native_assessment(StrategyConfig(), NOW) == {"offline": True}
    calls = client.subscribe.call_count
    assert calls == 2  # Future Quote and full option Depth; spot is borrowed.
    runner._native_assessment(StrategyConfig(), NOW)
    assert client.subscribe.call_count == calls and client.register_callback.call_count == 1
    old_client, old_callback = client, runner.cache_callback
    client = Mock(connected=True, authenticated=True)
    client.callbacks = {"market_data": [old_callback]}
    client.get_subscriptions.side_effect = lambda: {"subscriptions": list(active)}
    client.register_callback.side_effect = lambda event, callback: client.callbacks[event].append(
        callback
    )

    def remove_callback(event, callback):
        if callback in client.callbacks[event]:
            client.callbacks[event].remove(callback)

    client.unregister_callback.side_effect = remove_callback
    monkeypatch.setattr(sockets, "get_websocket_connection", lambda _: (True, client, None))
    runner._native_assessment(StrategyConfig(), NOW)
    old_client.unregister_callback.assert_called_once_with("market_data", old_callback)
    assert client.callbacks["market_data"] == [runner.cache_callback]
    assert not runner.owned_subscriptions  # Replacement-client subscriptions were borrowed.
    client.subscribe.return_value = {"status": "error"}
    client.subscribe.side_effect = None
    active.clear()
    from services.nifty_algo.paper_executor import OrderRefused

    with pytest.raises(OrderRefused, match="NATIVE_SUBSCRIPTION_ACK_FAILED"):
        runner._native_assessment(StrategyConfig(), NOW)
    runner.close()
    assert client.unregister_callback.call_count == 2
    assert not client.callbacks["market_data"]


def test_native_cache_preserves_source_time_and_missing_values_without_workers():
    from threading import Lock

    from services.market_data_service import MarketDataService, MarketDataValidator

    service = object.__new__(MarketDataService)
    service.data_lock, service.validator = Lock(), MarketDataValidator()
    service.health_monitor, service.market_data_cache = Mock(), {}
    service.metrics = {"validation_errors": 0, "total_updates": 0}
    service._broadcast_update_priority = Mock()
    service._broadcast_update = Mock()
    raw = {
        "symbol": "OFFLINE_CE",
        "exchange": "NFO",
        "mode": 3,
        "data": {
            "ltp": 100,
            "ltt": NOW.timestamp() * 1000,
            "volume": 0,
            "oi": 0,
            "source_volume": None,
            "source_oi": None,
            "depth": {
                "buy": [{"price": 99, "quantity": 25}],
                "sell": [{"price": 100, "quantity": 25}],
            },
        },
    }
    assert service.process_market_data(raw)
    source = service.get_all_data("OFFLINE_CE", "NFO")["source_observations"]["3"]
    assert (
        source["ltt"] == NOW.timestamp() * 1000
        and source["volume"] is None
        and source["oi"] is None
    )
    raw["data"] = {**raw["data"], "ltt": (NOW - timedelta(seconds=1)).timestamp() * 1000}
    assert service.process_market_data(raw)
    assert (
        service.get_all_data("OFFLINE_CE", "NFO")["source_observations"]["3"]["ltt"]
        == source["ltt"]
    )


def test_pcr_accepts_observed_oi_without_requiring_an_ltp():
    market = DeterministicMarket()
    original = market.get_all_data

    def without_ltp(symbol, exchange):
        data = original(symbol, exchange)
        for raw in data["source_observations"].values():
            raw.pop("ltp")
        return data

    market.get_all_data = without_ltp
    result = pipeline(market).get_pcr(StrategyConfig(), NOW)
    assert result["pcr"].value == 2 and result["pcr"].verified
