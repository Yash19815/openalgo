"""Research calculations ported from the user-owned trader-bot, commit cf7acb4."""

from zoneinfo import ZoneInfo

from .models import PCR


def smooth(values, period, alpha):
    output = [None] * len(values)
    seed = []
    previous = None
    for i, value in enumerate(values):
        if value is None:
            seed = []
            previous = None
            continue
        if previous is None:
            seed.append(value)
            if len(seed) == period:
                previous = sum(seed) / period
        else:
            previous += alpha * (value - previous)
        output[i] = previous
    return output


def ema(values, period):
    return smooth(values, period, 2 / (period + 1))


def wilder(values, period):
    return smooth(values, period, 1 / period)


def ranges(bars):
    return [
        max(b.high - b.low, abs(b.high - bars[i - 1].close), abs(b.low - bars[i - 1].close))
        if i
        else b.high - b.low
        for i, b in enumerate(bars)
    ]


def supertrend(bars, period=10, multiplier=3):
    """Recursive final bands; flips only use completed input candles."""
    atr = wilder(ranges(bars), period)
    result = [None] * len(bars)
    upper = lower = direction = None
    duration = 0
    for i, bar in enumerate(bars):
        if atr[i] is None or not bar.complete:
            continue
        mid = (bar.high + bar.low) / 2
        basic_upper, basic_lower = mid + multiplier * atr[i], mid - multiplier * atr[i]
        old_direction = direction
        if upper is None:
            upper, lower = basic_upper, basic_lower
            direction = 1 if bar.close >= mid else -1
        else:
            upper = basic_upper if basic_upper < upper or bars[i - 1].close > upper else upper
            lower = basic_lower if basic_lower > lower or bars[i - 1].close < lower else lower
            if direction == -1 and bar.close > upper:
                direction = 1
            elif direction == 1 and bar.close < lower:
                direction = -1
        flip = old_direction is not None and direction != old_direction
        duration = 1 if flip or duration == 0 else duration + 1
        value = lower if direction == 1 else upper
        result[i] = {
            "direction": direction,
            "value": value,
            "atr": atr[i],
            "flip": flip,
            "distance": bar.close - value,
            "duration": duration,
        }
    return result


def macd(bars, fast=12, slow=26, signal=9):
    closes = [b.close for b in bars]
    f, s = ema(closes, fast), ema(closes, slow)
    line = [None if a is None or b is None else a - b for a, b in zip(f, s, strict=True)]
    sig = ema(line, signal)
    result = []
    last_cross = None
    previous = None
    for i, (value, average) in enumerate(zip(line, sig, strict=True)):
        if value is None or average is None:
            result.append(None)
            continue
        hist = value - average
        cross = 0
        if previous is not None:
            if previous <= 0 < hist:
                cross = 1
            elif previous >= 0 > hist:
                cross = -1
        if cross:
            last_cross = (i, cross)
        result.append(
            {
                "line": value,
                "signal": average,
                "histogram": hist,
                "zero": 1 if value > 0 else -1 if value < 0 else 0,
                "zero_cross": 0
                if i == 0 or line[i - 1] is None
                else (1 if line[i - 1] <= 0 < value else -1 if line[i - 1] >= 0 > value else 0),
                "cross": cross,
                "cross_direction": last_cross[1] if last_cross else 0,
                "cross_age": i - last_cross[0] if last_cross else None,
                "acceleration": hist - previous if previous is not None else 0,
            }
        )
        previous = hist
    return result


def adx(bars, period=14):
    plus, minus = [None], [None]
    if not bars:
        return []
    for prev, bar in zip(bars, bars[1:], strict=False):
        up, down = bar.high - prev.high, prev.low - bar.low
        plus.append(up if up > down and up > 0 else 0)
        minus.append(down if down > up and down > 0 else 0)
    # Wilder DM and TR start at the first price transition, not the first candle.
    tr = ranges(bars)
    tr[0] = None
    smoothed_tr, p, m = wilder(tr, period), wilder(plus, period), wilder(minus, period)
    di_plus, di_minus, dx = [], [], []
    for t, up, down in zip(smoothed_tr, p, m, strict=True):
        if t is None:
            di_plus.append(None)
            di_minus.append(None)
            dx.append(None)
            continue
        a, b = (100 * up / t, 100 * down / t) if t else (0, 0)
        di_plus.append(a)
        di_minus.append(b)
        dx.append(100 * abs(a - b) / (a + b) if a + b else 0)
    values = wilder(dx, period)
    return [
        None
        if value is None
        else {
            "adx": value,
            "plus_di": di_plus[i],
            "minus_di": di_minus[i],
            "slope": value - values[i - 1] if i and values[i - 1] is not None else 0,
            "strength": "VERY_STRONG" if value >= 50 else "STRONG" if value >= 25 else "WEAK",
        }
        for i, value in enumerate(values)
    ]


def vwap(bars, basis="typical", instrument_kind="FUT"):
    """Same-series session VWAP. Missing volume invalidates the remaining session."""
    result = []
    day = None
    pv = volume = 0
    valid = instrument_kind == "FUT"
    if len({bar.token for bar in bars}) > 1:
        return [None] * len(bars)
    for bar in bars:
        current = bar.start.astimezone(ZoneInfo("Asia/Kolkata")).date()
        if current != day:
            day, pv, volume, valid = current, 0, 0, instrument_kind == "FUT"
        if bar.volume is None:
            valid = False
        if valid:
            price = (bar.high + bar.low + bar.close) / 3 if basis == "typical" else bar.close
            pv += price * bar.volume
            volume += bar.volume
        result.append(pv / volume if valid and volume > 0 else None)
    return result


def pcr(contracts, quotes, kind, scope, now, max_age=90, verified=False):
    """No missing-strike renormalization; OI and volume are never substituted."""
    if kind not in ("OI", "VOLUME") or {i.kind for i in contracts} != {"CE", "PE"}:
        return None
    identities = {(i.exchange, i.underlying, i.expiry) for i in contracts}
    if len(identities) != 1 or not scope or not verified:
        return None
    if len({i.token for i in contracts}) != len(contracts):
        return None
    strikes = {i.strike for i in contracts}
    if any({i.kind for i in contracts if i.strike == strike} != {"CE", "PE"} for strike in strikes):
        return None
    puts = calls = 0
    timestamps = []
    for instrument in contracts:
        quote = quotes.get(instrument.token)
        if quote is None or quote.token != instrument.token:
            return None
        if not 0 <= (now - quote.source_time).total_seconds() <= max_age:
            return None
        if not quote.source_time <= quote.received_time <= now:
            return None
        value = quote.oi if kind == "OI" else quote.volume
        if value is None:
            return None
        if instrument.kind == "CE":
            calls += value
        elif instrument.kind == "PE":
            puts += value
        else:
            return None
        timestamps.append(quote.source_time)
    if calls <= 0:
        return None
    return PCR(
        value=puts / calls,
        kind=kind,
        scope=scope,
        source_time=min(timestamps),
        coverage=1,
        verified=verified,
    )
