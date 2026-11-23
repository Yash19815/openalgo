"""Native research reads cannot promote display fallbacks into feed evidence."""

from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from services.nifty_algo.models import Instrument
from services.nifty_algo.native_data import NativeDataAdapter
from services.nifty_algo.paper_executor import NiftyPaperExecutor
from test.test_nifty_algo_native_data import Cache

NOW = datetime(2026, 11, 19, 5, 0, tzinfo=UTC)


def instrument():
    return Instrument(
        token="native-option",
        symbol="NIFTY24NOV2624000CE",
        exchange="NFO",
        kind="CE",
        expiry=date(2026, 11, 24),
        strike="24000",
        lot_size=65,
        tick_size="0.05",
        master_date=NOW.date(),
    )


def source(**changes):
    return {
        "symbol": instrument().symbol,
        "exchange": "NFO",
        "ltt": NOW - timedelta(seconds=2),
        "received_time": NOW - timedelta(seconds=1),
        "depth": {
            "buy": [{"price": "100.05", "quantity": 65}],
            "sell": [{"price": "100.10", "quantity": 130}],
        },
        "ltp": "100.075",
        "volume": 500,
        **changes,
    }


def native(cached):
    return NativeDataAdapter(lambda: [], Cache(cached), lambda: NOW)


def test_recording_quote_reuses_fill_validation_without_executor_or_cache_mutation():
    cached = {"source_observations": {"3": source()}}
    before = deepcopy(cached)
    adapter = native(cached)
    observed = adapter.recording_quote(instrument(), NOW)
    assert observed == NiftyPaperExecutor(market_data=adapter.market_data)._depth(instrument(), NOW)
    assert observed.bid == Decimal("100.05")
    assert observed.ask == Decimal("100.10")
    assert observed.bid_size == 65
    assert observed.ask_size == 130
    assert observed.source_time == source()["ltt"]
    assert observed.received_time == source()["received_time"]
    assert observed.provider == "native_depth"
    assert cached == before
    assert adapter.recording_quote(instrument(), NOW) == observed


@pytest.mark.parametrize(
    "cached",
    [
        None,
        [],
        {},
        {"source_observations": []},
        {"source_observations": {"3": []}},
        {"source_observations": {"3": "invalid"}},
        {"source_observations": {"2": source()}},
        {
            "depth": source()["depth"],
            "last_update": NOW,
            "ltp": "100",
        },
    ],
)
def test_recording_quote_never_uses_display_or_other_modes(cached):
    assert native(cached).recording_quote(instrument(), NOW) is None


@pytest.mark.parametrize(
    "changes",
    [
        {"symbol": "BANKNIFTY"},
        {"symbol": None},
        {"exchange": "NSE"},
        {"received_time": None},
        {"received_time": NOW + timedelta(seconds=1)},
        {"received_time": NOW - timedelta(seconds=3)},
        {"ltt": None},
        {"ltt": NOW + timedelta(seconds=1)},
        {"ltt": NOW - timedelta(seconds=6)},
        {"ltt": NOW.replace(tzinfo=None)},
        {"depth": []},
        {"depth": "invalid"},
        {"depth": {"buy": "invalid"}},
        {"depth": {"buy": [{"price": "100.01", "quantity": 65}]}},
        {
            "depth": {
                "buy": [{"price": "101", "quantity": 65}],
                "sell": [{"price": "100", "quantity": 65}],
            }
        },
    ],
)
def test_recording_quote_rejects_missing_mismatched_or_unusable_source(changes):
    cached = {"source_observations": {"3": source(**changes)}}
    assert native(cached).recording_quote(instrument(), NOW) is None


def test_recording_quote_failure_does_not_reconnect_subscribe_or_create_a_client():
    class MissingCache:
        def get_all_data(self, symbol, exchange):
            raise RuntimeError("cache unavailable")

    adapter = NativeDataAdapter(lambda: [], MissingCache(), lambda: NOW)
    assert adapter.recording_quote(instrument(), NOW) is None


def test_recording_quote_has_no_ltp_fabricated_depth():
    cached = {"source_observations": {"3": source(depth={}, ltp="100")}}
    assert native(cached).recording_quote(instrument(), NOW) is None


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_recording_quote_rejects_missing_or_oversized_depth_side(side):
    raw = source()
    raw["depth"][side] = []
    assert native({"source_observations": {"3": raw}}).recording_quote(instrument(), NOW) is None
    raw["depth"][side] = [{"price": "100.05", "quantity": 65}] * 21
    assert native({"source_observations": {"3": raw}}).recording_quote(instrument(), NOW) is None


def test_recording_quote_preserves_native_oi_and_packet_sequence():
    cached = {"source_observations": {"3": source(oi=1200, sequence_number=789)}}
    observed = native(cached).recording_quote(instrument(), NOW)
    assert observed.oi == 1200
    assert observed.sequence == 789


@pytest.mark.parametrize(
    "entry",
    [
        "invalid",
        {"price": "bad", "quantity": 65},
        {"price": "100.05"},
        {"price": "100.05", "quantity": True},
        {"price": "100.05", "quantity": 65.5},
    ],
)
def test_recording_quote_rejects_malformed_levels_even_with_a_usable_best(entry):
    raw = source()
    raw["depth"]["buy"].append(entry)
    assert native({"source_observations": {"3": raw}}).recording_quote(instrument(), NOW) is None
