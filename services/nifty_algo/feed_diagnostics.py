"""Bounded allowlisted feed evidence, safe to embed in offline analysis frames."""

from .depth_quote import epoch


def snapshot_evidence(instrument, raw, now):
    """Do not log/return raw packets, credentials, exception strings or headers."""
    raw = raw if isinstance(raw, dict) else {}
    times = {
        key: epoch(raw.get(key))
        for key in ("quote_time", "last_trade_time", "broker_time", "received_time", "ltt")
    }
    quote, received = times["quote_time"], times["received_time"]
    oi = raw.get("oi")
    sequence = raw.get("sequence_number")
    return {
        "schema": "nifty-feed-provenance-v1",
        "token": instrument.token,
        "symbol": instrument.symbol,
        "expiry": instrument.expiry.isoformat(),
        "strike": str(instrument.strike),
        "lot_size": instrument.lot_size,
        "tick_size": str(instrument.tick_size),
        "master_date": instrument.master_date.isoformat(),
        "identity_matches": raw.get("symbol") == instrument.symbol
        and raw.get("exchange") == instrument.exchange,
        "timestamp_kind": "EXCHANGE_PACKET"
        if raw.get("timestamp_kind") == "EXCHANGE_PACKET"
        else "UNVERIFIED",
        "timestamps": {key: value.isoformat() if value else None for key, value in times.items()},
        "quote_age_seconds": (now - quote).total_seconds() if quote else None,
        "causal_quote": bool(quote and received and quote <= received <= now),
        "oi": oi if type(oi) is int and oi >= 0 else None,
        "sequence": sequence if type(sequence) is int and sequence >= 0 else None,
        "has_book": isinstance(raw.get("depth"), dict),
    }
