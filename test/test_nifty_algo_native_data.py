"""Offline fixtures for native cache provenance and instrument restrictions."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from services.nifty_algo.native_data import NativeDataAdapter

NOW = datetime(2026, 11, 19, 5, 0, tzinfo=UTC)


def row(**changes):
    return {
        "symbol": "NIFTY24NOV2624000CE",
        "token": "123",
        "name": "NIFTY",
        "exchange": "NFO",
        "instrumenttype": "CE",
        "expiry": "24-NOV-26",
        "strike": 24000,
        "lotsize": 65,
        "tick_size": 0.05,
        **changes,
    }


class Cache:
    def __init__(self, observation):
        self.observation = observation
        self.reads = []

    def get_all_data(self, symbol, exchange):
        self.reads.append((symbol, exchange))
        return self.observation


def adapter(rows, cached=None):
    return NativeDataAdapter(lambda: rows, Cache(cached or {}), lambda: NOW)


@pytest.mark.parametrize(
    "changes",
    [
        {"name": "BANKNIFTY"},
        {"name": "NIFTYBEES"},
        {"exchange": "NSE"},
        {"instrumenttype": "OPTSTK"},
        {"expiry": "18-NOV-26"},
        {"expiry": "invalid"},
        {"lotsize": 0},
        {"lotsize": 1.5},
        {"tick_size": float("nan")},
        {"strike": 0},
        {"token": ""},
    ],
)
def test_contracts_reject_invalid_structured_metadata(changes):
    assert adapter([row(**changes)]).get_contracts() == []


def test_contracts_use_current_metadata_and_do_not_construct_symbols():
    actual = row(symbol="listed-broker-independent-symbol", lotsize=35, tick_size=0.1)
    contract = adapter([actual]).get_contracts()[0]
    assert contract["symbol"] == actual["symbol"]
    assert contract["lot_size"] == 35
    assert contract["tick_size"] == 0.1
    assert contract["kind"] == "CE"
    assert contract["master_freshness"] == "UNVERIFIED"


def test_market_preserves_exchange_transport_and_receipt_times():
    source = NOW - timedelta(seconds=2)
    transport = NOW - timedelta(seconds=1)
    cached = {
        "last_update": NOW.timestamp(),
        "quote": {
            "ltp": 24000,
            "volume": 200,
            "ltt": source.timestamp() * 1000,
            "timestamp": transport.timestamp() * 1000,
        },
    }
    rows = [row(instrumenttype="FUTIDX", symbol="listed-future", strike=0)]
    native = adapter(rows, cached)
    market = native.get_market()
    assert market["future"]["source_time"] == source.isoformat()
    assert market["future"]["transport_time"] == transport.isoformat()
    assert market["future"]["received_time"] == NOW.isoformat()
    assert market["future"]["feed_latency_ms"] == 2000
    assert market["future"]["status"] == "AVAILABLE"
    assert native.market_data.reads == [("listed-future", "NFO")]


def test_native_cache_without_ltt_fails_closed_despite_recent_timestamp():
    cached = {"last_update": NOW.timestamp(), "quote": {"ltp": 24000, "timestamp": NOW.timestamp()}}
    future = adapter([row(instrumenttype="FUTIDX")], cached).get_market()["future"]
    assert future["ltp"] == 24000
    assert future["source_time"] is None
    assert future["status"] == "DATA_UNAVAILABLE"
    assert "SOURCE_TIMESTAMP_UNAVAILABLE" in future["reasons"]


@pytest.mark.parametrize(
    "offset,reason",
    [
        (-10, "SOURCE_QUOTE_STALE"),
        (2, "TIMESTAMP_ORDER_INVALID"),
        (-86400, "PREVIOUS_SESSION_QUOTE"),
    ],
)
def test_source_freshness_and_session_fail_closed(offset, reason):
    cached = {
        "last_update": NOW.timestamp(),
        "quote": {
            "ltp": 24000,
            "ltt": (NOW + timedelta(seconds=offset)).timestamp(),
        },
    }
    observation = adapter([row(instrumenttype="FUT")], cached).get_market()["future"]
    assert observation["status"] == "DATA_UNAVAILABLE"
    assert reason in observation["reasons"]


def test_spot_has_no_manufactured_volume_and_future_selection_uses_expiry():
    cached = {
        "last_update": NOW.timestamp(),
        "ltp": {
            "value": 24000,
            "volume": 999,
            "ltt": NOW.timestamp(),
        },
    }
    rows = [
        row(instrumenttype="FUTIDX", symbol="later", expiry="29-DEC-26"),
        row(instrumenttype="FUTIDX", symbol="nearer"),
        row(instrumenttype="AMXIDX", exchange="NSE_INDEX", symbol="NIFTY", name="Nifty 50"),
    ]
    market = adapter(rows, cached).get_market()
    assert market["spot"]["volume"] is None
    assert market["future"]["instrument"]["symbol"] == "nearer"


def test_empty_cache_is_explicitly_unavailable():
    observation = adapter([row(instrumenttype="FUTIDX")]).get_market()["future"]
    assert observation["status"] == "DATA_UNAVAILABLE"
    assert observation["ltp"] is None
    assert observation["received_time"] is None
