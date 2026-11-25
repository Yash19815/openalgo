"""Native normalization, safe diagnostics and cache ordering; no broker client."""

from copy import deepcopy
from threading import Lock
from unittest.mock import Mock

from services.nifty_algo.feed_diagnostics import snapshot_evidence
from test.test_nifty_algo_native_capture import NOW, instrument, source


def test_angel_normalization_preserves_each_timestamp_and_sequence():
    from websocket_proxy import AngelWebSocketAdapter

    adapter = object.__new__(AngelWebSocketAdapter)
    adapter.logger = Mock()
    adapter.lock, adapter.subscriptions = Lock(), {}
    adapter._reconnect_timer = adapter.ws_client = adapter._connect_thread = None
    message = {
        "exchange_timestamp": int(NOW.timestamp() * 1000),
        "last_traded_timestamp": int(NOW.timestamp()) - 3600,
        "sequence_number": 456,
        "last_traded_price": 10000,
        "open_interest": 0,
        "best_5_buy_data": [],
        "best_5_sell_data": [],
    }
    raw = adapter._normalize_market_data(message, 3, "NFO")
    assert raw["quote_time"] == message["exchange_timestamp"]
    assert raw["last_trade_time"] == message["last_traded_timestamp"]
    assert raw["ltt"] == raw["quote_time"]  # Compatibility alias, explicitly not trade time.
    assert raw["sequence_number"] == 456 and raw["source_oi"] == 0
    assert raw["broker_time"] is None


def test_diagnostics_are_allowlisted_and_missing_oi_stays_missing():
    raw = source(api_key="DO-NOT-EXPORT", password="DO-NOT-EXPORT", oi=0)
    result = snapshot_evidence(instrument(), raw, NOW)
    assert "DO-NOT-EXPORT" not in str(result)
    assert result["oi"] == 0
    assert snapshot_evidence(instrument(), source(), NOW)["oi"] is None
    assert result["timestamps"]["last_trade_time"] is None
    assert result["timestamps"]["broker_time"] is None


def test_source_cache_rejects_duplicate_and_out_of_order_packets():
    from services.market_data_service import MarketDataService, MarketDataValidator

    service = object.__new__(MarketDataService)
    service.data_lock, service.validator = Lock(), MarketDataValidator()
    service.health_monitor, service.market_data_cache = Mock(), {}
    service.metrics = {"validation_errors": 0, "total_updates": 0}
    service._broadcast_update_priority = Mock()
    service._broadcast_update = Mock()
    packet = {
        "symbol": instrument().symbol,
        "exchange": "NFO",
        "mode": 3,
        "data": {
            **source(),
            "quote_time": int(NOW.timestamp() * 1000),
            "ltp": 100.075,
            "ltt": int(NOW.timestamp() * 1000),
            "sequence_number": 10,
        },
    }
    packet["data"]["depth"] = {
        "buy": [{"price": 100.05, "quantity": 65}],
        "sell": [{"price": 100.10, "quantity": 130}],
    }
    assert service.process_market_data(packet)
    first = deepcopy(service.get_all_data(instrument().symbol, "NFO")["source_observations"]["3"])
    for sequence, offset in ((9, 0), (10, 0), (11, -1)):
        changed = deepcopy(packet)
        changed["data"].update(
            sequence_number=sequence, quote_time=packet["data"]["quote_time"] + offset, oi=999
        )
        assert service.process_market_data(changed)
        assert service.get_all_data(instrument().symbol, "NFO")["source_observations"]["3"] == first
    packet["data"]["sequence_number"] = 11
    packet["data"]["oi"] = 0
    assert service.process_market_data(packet)
    assert service.get_all_data(instrument().symbol, "NFO")["source_observations"]["3"]["oi"] == 0
