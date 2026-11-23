"""Pure native-depth normalization shared by paper fills and research reads."""

from datetime import UTC, datetime
from decimal import Decimal
from math import isfinite

from .models import Quote


def epoch(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else None
    if isinstance(value, (int, float)):
        try:
            return (
                datetime.fromtimestamp(value / 1000 if value > 10**12 else value, UTC)
                if isfinite(value)
                else None
            )
        except (ValueError, OverflowError, OSError):
            return None
    try:
        stamp = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return stamp if stamp.tzinfo else None


def _best_level(entries, high=True, *, strict=False):
    """(price, quantity) at the best level of a depth side."""
    best = None
    for entry in entries or []:
        try:
            if isinstance(entry, dict):
                price = Decimal(str(entry["price"]))
                quantity = entry["quantity"] if strict else entry.get("quantity", 0)
            else:
                price = Decimal(str(entry[0]))
                quantity = entry[1]
            size = int(quantity)
            if strict and (isinstance(quantity, bool) or Decimal(str(quantity)) != size):
                return None
        except (KeyError, IndexError, TypeError, ValueError, ArithmeticError):
            if strict:
                return None
            continue
        if not price.is_finite() or price <= 0 or size <= 0:
            continue
        if best is None or (price > best[0] if high else price < best[0]):
            best = (price, size)
    return best


def depth_quote(instrument, raw, now, max_age=5, *, strict=False):
    """Normalize one source snapshot; absent depth stays absent, never LTP depth."""
    try:
        depth = raw.get("depth") or raw
        bid = _best_level(depth.get("buy") or depth.get("bids"), strict=strict)
        ask = _best_level(depth.get("sell") or depth.get("asks"), high=False, strict=strict)
        stamp, received = epoch(raw.get("ltt")), epoch(raw.get("received_time"))
        if stamp is None or stamp > now or (now - stamp).total_seconds() > max_age:
            return None
        if received is None or received < stamp or received > now:
            return None
        if any(level and level[0] % instrument.tick_size != 0 for level in (bid, ask)):
            return None
        ltp = raw.get("ltp")
        if isinstance(ltp, dict):
            ltp = ltp.get("value")
        return Quote(
            token=instrument.token,
            source_time=stamp,
            received_time=received,
            ltp=Decimal(str(ltp)) if ltp is not None and Decimal(str(ltp)) > 0 else None,
            bid=None if bid is None else bid[0],
            ask=None if ask is None else ask[0],
            bid_size=0 if bid is None else bid[1],
            ask_size=0 if ask is None else ask[1],
            volume=raw.get("volume"),
            provider="native_depth",
        )
    except (AttributeError, ValueError, TypeError, ArithmeticError):
        return None
