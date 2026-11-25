"""Exchange quote time and last-trade time are distinct synthetic evidence."""

from datetime import timedelta

from services.nifty_algo.depth_quote import depth_quote
from test.test_nifty_algo_native_capture import NOW, instrument, source


def test_fresh_trade_cannot_certify_stale_book():
    raw = source()
    raw.update(
        quote_time=NOW - timedelta(seconds=6), last_trade_time=NOW, ltt=NOW, received_time=NOW
    )
    assert depth_quote(instrument(), raw, NOW) is None


def test_fresh_book_does_not_require_recent_trade():
    raw = source()
    raw.update(
        quote_time=NOW - timedelta(seconds=1),
        last_trade_time=NOW - timedelta(hours=1),
        ltt=NOW - timedelta(hours=1),
    )
    quote = depth_quote(instrument(), raw, NOW)
    assert quote is not None
    assert quote.source_time == raw["quote_time"]


def test_untyped_ltt_or_receipt_time_cannot_certify_book():
    raw = source()
    raw.pop("quote_time", None)
    assert depth_quote(instrument(), raw, NOW) is None


def test_historical_timestamp_policy_remains_explicit():
    raw = source()
    raw.pop("quote_time", None)
    assert depth_quote(instrument(), raw, NOW, allow_legacy_timestamp=True) is not None
