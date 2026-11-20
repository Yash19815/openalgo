"""Causal candles: no interpolation, no synthetic volume, no incomplete aggregates."""

from datetime import timedelta
from zoneinfo import ZoneInfo

from .models import Candle

IST = ZoneInfo("Asia/Kolkata")


def aggregate(bars, minutes, now, session_open=None):
    if minutes not in (1, 5, 15):
        raise ValueError("Unsupported candle timeframe")
    if len({bar.token for bar in bars}) > 1 or any(bar.timeframe != 1 for bar in bars):
        raise ValueError("Aggregation requires one instrument's minute bars")
    if any(left.start >= right.start for left, right in zip(bars, bars[1:], strict=False)):
        raise ValueError("Duplicate or out-of-order minute bars")
    groups = {}
    for bar in bars:
        if not bar.complete or bar.end > now:
            continue
        anchor = session_open
        if anchor is None:
            raise ValueError("Effective session opening timestamp required")
        if anchor.tzinfo is None:
            raise ValueError("Session opening timestamp requires timezone")
        if bar.start.astimezone(IST).date() != anchor.astimezone(IST).date():
            continue
        offset = int((bar.start - anchor).total_seconds() // 60)
        if offset < 0:
            continue
        start = anchor + timedelta(minutes=offset // minutes * minutes)
        groups.setdefault(start, []).append(bar)
    result = []
    for start, group in sorted(groups.items()):
        group.sort(key=lambda b: b.start)
        end = start + timedelta(minutes=minutes)
        if (
            end > now
            or len(group) != minutes
            or any(b.start != start + timedelta(minutes=i) for i, b in enumerate(group))
        ):
            continue
        result.append(
            Candle(
                token=group[0].token,
                start=start,
                end=end,
                timeframe=minutes,
                open=group[0].open,
                high=max(b.high for b in group),
                low=min(b.low for b in group),
                close=group[-1].close,
                volume=sum(b.volume for b in group)
                if all(b.volume is not None for b in group)
                else None,
                provenance=group[-1].provenance,
            )
        )
    return result


class CandleBuilder:
    def __init__(self):
        self.current = {}
        self.previous = {}
        self.valid_start = {}

    def push(self, quote, instrument):
        if quote.ltp is None:
            return None
        old = self.previous.get(quote.token)
        if old and (
            quote.source_time < old.source_time
            or (quote.source_time == old.source_time and quote.sequence <= old.sequence)
        ):
            return None
        self.previous[quote.token] = quote
        start = quote.source_time.replace(second=0, microsecond=0)
        current = self.current.get(quote.token)
        emitted = None
        if current is None or start > current.start:
            if current is not None and self.valid_start.get(quote.token):
                emitted = current.model_copy(update={"complete": True})
            # First observed minute is partial. A consecutive minute boundary proves its next start.
            valid = current is not None and start == current.end
            self.valid_start[quote.token] = valid
            self.current[quote.token] = Candle(
                token=quote.token,
                start=start,
                end=start + timedelta(minutes=1),
                timeframe=1,
                open=float(quote.ltp),
                high=float(quote.ltp),
                low=float(quote.ltp),
                close=float(quote.ltp),
                volume=0
                if instrument.kind != "SPOT" and quote.volume is not None and old is not None
                else None,
                complete=False,
                provenance=quote.provider,
            )
            current = self.current[quote.token]
        current.high = max(current.high, float(quote.ltp))
        current.low = min(current.low, float(quote.ltp))
        current.close = float(quote.ltp)
        if current.volume is not None and old is not None:
            same_day = (
                old.source_time.astimezone(IST).date() == quote.source_time.astimezone(IST).date()
            )
            if (
                quote.volume is None
                or old.volume is None
                or quote.volume < old.volume
                or not same_day
            ):
                current.volume = None
            else:
                current.volume += quote.volume - old.volume
        return emitted
