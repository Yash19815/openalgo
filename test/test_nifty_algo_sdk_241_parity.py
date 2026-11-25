"""Offline SDK 2.4.1 parity evidence; see docs/nifty-algo/SDK_241_PARITY.md.

Synthetic prices are mathematical fixtures, not market observations. Expected
differences deliberately remain visible: these tests do not replace the strategy
with SDK indicators or change its crossover freshness rule.
"""

import inspect
from datetime import UTC, datetime, timedelta
from importlib.metadata import version
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest
from numpy.testing import assert_allclose
from openalgo import ta
from openalgo.indicators import _backend

from services.nifty_algo import indicators, signal_engine
from services.nifty_algo.config import StrategyConfig
from services.nifty_algo.market_data import aggregate
from services.nifty_algo.models import Candle

ATOL = 1e-9
RTOL = 1e-12
IST = ZoneInfo("Asia/Kolkata")


def legacy_31(**changes):
    """A stored strategy 3.1.0 record: crossover ages 0..3 were admitted.

    The census below was frozen under that rule. It is kept as historical
    evidence that the indicator mathematics did not change when 3.2.0 narrowed
    the window to ages 0..2 (approved 2026-11-24).
    """
    values = StrategyConfig(**({"atr_period": 10, "atr_multiplier": 3} | changes)).model_dump(
        mode="json"
    )
    values.update(
        strategy_version="3.1.0", confidence_method="five-indicator-v1", crossover_freshness=3
    )
    return StrategyConfig.model_validate(values)


PATTERNS = ("rising", "falling", "sideways", "volatile", "reversal", "low_volatility")
GATES = ("R-ST", "R-MACD", "R-ADX", "R-VWAP")


def fixture_bars(pattern="volatile", n=525, seed=241):
    """75 five-minute bars per weekday, 09:15 IST, one immutable FUT token.

    PCG64 draws steps first, then upper/lower wicks and integer volume. Explicit
    patterns replace steps but retain those draws, making each seed reproducible.
    """
    rng = np.random.default_rng(seed)
    steps = rng.normal(0, 8, n)
    x = np.arange(n)
    closes = 22000 + np.cumsum(steps)
    if pattern == "rising":
        closes = 22000 + 2 * x
    elif pattern == "falling":
        closes = 22000 - 2 * x
    elif pattern == "sideways":
        closes = 22000 + 0.1 * np.sin(x / 3)
    elif pattern == "reversal":
        closes = 22000 + np.where(x < 100, 3 * x, 300 - 5 * (x - 100))
    elif pattern == "low_volatility":
        closes = 22000 + np.cumsum(steps * 0.001)
    elif pattern != "volatile":
        raise ValueError(pattern)
    upper = rng.uniform(1, 12, n)
    lower = rng.uniform(1, 12, n)
    volumes = rng.integers(1, 1000, n)
    days = []
    day = datetime(2026, 11, 2, 9, 15, tzinfo=IST)
    while len(days) * 75 < n:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    bars = []
    for i, close in enumerate(closes):
        opening = closes[i - 1] if i else close
        high, low = max(opening, close) + upper[i], min(opening, close) - lower[i]
        if pattern == "sideways":
            high, low = close + 20, close - 20
        start = days[i // 75] + timedelta(minutes=5 * (i % 75))
        bars.append(
            Candle(
                token="SDK241-FUT",
                start=start,
                end=start + timedelta(minutes=5),
                timeframe=5,
                open=float(opening),
                high=float(high),
                low=float(low),
                close=float(close),
                volume=int(volumes[i]),
                provenance="DETERMINISTIC_SDK_241_FIXTURE",
            )
        )
    return bars


def arrays(bars):
    return tuple(
        np.array([getattr(b, name) for b in bars], dtype=float)
        for name in ("high", "low", "close", "volume")
    )


def numeric(values):
    return np.array([np.nan if v is None else v for v in values], dtype=float)


def field(rows, name):
    return numeric([row[name] if row is not None else None for row in rows])


def assert_numeric(actual, expected):
    assert_allclose(actual, expected, atol=ATOL, rtol=RTOL, equal_nan=True)


def first_finite(values):
    positions = np.flatnonzero(np.isfinite(values))
    return int(positions[0]) if len(positions) else None


def reference_smoothing(values, period, alpha, first_value=False):
    """Independent weighted recurrence; NaNs reset the seed window."""
    result = np.full(len(values), np.nan)
    window = []
    last = None
    for i, value in enumerate(values):
        if not np.isfinite(value):
            last, window = None, []
            continue
        if last is None:
            window.append(value)
            if first_value or len(window) == period:
                last = float(np.mean(window))
        else:
            last = (1 - alpha) * last + alpha * value
        if last is not None:
            result[i] = last
    return result


def reference_dm(bars, include_bar_zero=False):
    """TR/DM and Wilder DI/DX/ADX, independently built from OHLC arrays."""
    high, low, close, _ = arrays(bars)
    tr = high - low
    tr[1:] = np.maximum.reduce((tr[1:], abs(high[1:] - close[:-1]), abs(low[1:] - close[:-1])))
    up, down = np.diff(high), -np.diff(low)
    plus = np.r_[0.0, np.where((up > down) & (up > 0), up, 0)]
    minus = np.r_[0.0, np.where((down > up) & (down > 0), down, 0)]
    if not include_bar_zero:
        tr[0] = plus[0] = minus[0] = np.nan
    smoothed = [reference_smoothing(a, 14, 1 / 14) for a in (tr, plus, minus)]
    tr_mean, plus_mean, minus_mean = smoothed
    p = np.full(len(bars), np.nan)
    m = p.copy()
    valid = np.isfinite(tr_mean)
    nonzero = valid & (tr_mean > 0)
    p[nonzero] = 100 * plus_mean[nonzero] / tr_mean[nonzero]
    m[nonzero] = 100 * minus_mean[nonzero] / tr_mean[nonzero]
    if not include_bar_zero:
        p[valid & ~nonzero] = m[valid & ~nonzero] = 0
    dx = np.full(len(bars), np.nan)
    directional = np.isfinite(p) & ((p + m) > 0)
    dx[directional] = 100 * abs(p[directional] - m[directional]) / (p + m)[directional]
    if not include_bar_zero:
        dx[valid & ~directional] = 0
    return tr, plus, minus, p, m, dx, reference_smoothing(dx, 14, 1 / 14)


def reference_bands(bars, sdk_initial=False, period=10, multiplier=3):
    """Final-band recursion with both documented initial-direction choices."""
    high, low, close, _ = arrays(bars)
    tr = high - low
    tr[1:] = np.maximum.reduce((tr[1:], abs(high[1:] - close[:-1]), abs(low[1:] - close[:-1])))
    atr = reference_smoothing(tr, period, 1 / period)
    upper, lower, direction, values = (np.full(len(bars), np.nan) for _ in range(4))
    for i in range(period - 1, len(bars)):
        midpoint = (high[i] + low[i]) / 2
        upper[i], lower[i] = midpoint + multiplier * atr[i], midpoint - multiplier * atr[i]
        if i == period - 1:
            direction[i] = -1 if sdk_initial or close[i] < midpoint else 1
        else:
            if upper[i] >= upper[i - 1] and close[i - 1] <= upper[i - 1]:
                upper[i] = upper[i - 1]
            if lower[i] <= lower[i - 1] and close[i - 1] >= lower[i - 1]:
                lower[i] = lower[i - 1]
            direction[i] = direction[i - 1]
            if direction[i] == -1 and close[i] > upper[i]:
                direction[i] = 1
            elif direction[i] == 1 and close[i] < lower[i]:
                direction[i] = -1
        values[i] = lower[i] if direction[i] == 1 else upper[i]
    return atr, upper, lower, direction, values


def sdk_vwap(bars, basis="typical", **kwargs):
    high, low, close, volume = arrays(bars)
    return ta.vwap(
        high, low, close, volume, source="hlc3" if basis == "typical" else "close", **kwargs
    )


def session_markers(bars):
    days = [b.start.astimezone(IST).date() for b in bars]
    return np.array([i == 0 or d != days[i - 1] for i, d in enumerate(days)])


def momentum_rows(line, signal, histogram):
    """SDK has no crossover age output; derive it causally from its histogram."""
    rows = []
    last_cross = None
    previous = None
    for i, hist in enumerate(histogram):
        if not np.isfinite(hist):
            rows.append(None)
            continue
        cross = 0
        if previous is not None:
            cross = 1 if previous <= 0 < hist else -1 if previous >= 0 > hist else 0
        if cross:
            last_cross = (i, cross)
        rows.append(
            {
                "line": float(line[i]),
                "signal": float(signal[i]),
                "histogram": float(hist),
                "cross": cross,
                "cross_direction": last_cross[1] if last_cross else 0,
                "cross_age": i - last_cross[0] if last_cross else None,
            }
        )
        previous = hist
    return rows


def gate_values(price, st, momentum, strength, vw, config=None):
    """Gate projection checked against actual Rules.evaluate below."""
    config = config or StrategyConfig(atr_period=10, atr_multiplier=3)
    direction = st["direction"] if st else 0
    macd_ok = bool(momentum) and (
        momentum["cross_direction"] == direction
        and momentum["cross_age"] is not None
        and momentum["cross_age"] <= config.crossover_freshness
        and momentum["histogram"] * direction > 0
    )
    if config.macd_zero_required and momentum:
        macd_ok = macd_ok and momentum["line"] * direction > 0
    adx_ok = bool(strength) and strength["adx"] >= config.adx_min
    if config.di_confirmation and strength:
        adx_ok = adx_ok and (strength["plus_di"] - strength["minus_di"]) * direction > 0
    distance = (price - vw) / vw * 10000 if vw is not None and np.isfinite(vw) and vw else None
    return dict(
        zip(
            GATES,
            (
                bool(st) and (price - st["value"]) * direction > 0,
                bool(macd_ok),
                bool(adx_ok),
                distance is not None
                and distance * direction >= 0
                and abs(distance) <= config.vwap_max_bps,
            ),
            strict=True,
        )
    )


def comparison(bars):
    high, low, close, _ = arrays(bars)
    custom = (
        indicators.supertrend(bars, 10, 3),
        indicators.macd(bars),
        indicators.adx(bars),
        indicators.vwap(bars),
    )
    st_value, st_direction = ta.supertrend(high, low, close, period=10, multiplier=3)
    sdk_st = [
        None if not np.isfinite(value) else {"value": float(value), "direction": int(-direction)}
        for value, direction in zip(st_value, st_direction, strict=True)
    ]
    sdk_macd = momentum_rows(*ta.macd(close, fast_period=12, slow_period=26, signal_period=9))
    p, m, a = ta.adx(high, low, close, period=14)
    sdk_adx = [
        None
        if not np.isfinite(value)
        else {"adx": float(value), "plus_di": float(p[i]), "minus_di": float(m[i])}
        for i, value in enumerate(a)
    ]
    return custom, (sdk_st, sdk_macd, sdk_adx, sdk_vwap(bars, session_starts=session_markers(bars)))


def test_installed_sdk_version_signatures_and_output_order():
    assert version("openalgo") == "2.4.1", "Parity suite requires the repository's pinned SDK"
    expected = {
        "atr": ("high", "low", "close", "period"),
        "supertrend": ("high", "low", "close", "period", "multiplier"),
        "ema": ("data", "period"),
        "macd": ("data", "fast_period", "slow_period", "signal_period"),
        "adx": ("high", "low", "close", "period"),
    }
    for name, parameters in expected.items():
        assert tuple(inspect.signature(getattr(ta, name)).parameters) == parameters
    assert tuple(inspect.signature(ta.vwap).parameters) == (
        "high",
        "low",
        "close",
        "volume",
        "anchor",
        "source",
        "stdev_mult_1",
        "stdev_mult_2",
        "stdev_mult_3",
        "percent_mult_1",
        "percent_mult_2",
        "percent_mult_3",
        "timestamps",
        "session_starts",
    )
    high, low, close, _ = arrays(fixture_bars("rising", n=80))
    for result, size in (
        (ta.supertrend(high, low, close), 2),
        (ta.macd(close), 3),
        (ta.adx(high, low, close), 3),
    ):
        assert isinstance(result, tuple) and len(result) == size
        assert all(isinstance(a, np.ndarray) and a.shape == (80,) for a in result)
    p, m, a = ta.adx(high, low, close)
    assert p[-1] > m[-1]
    assert a[-1] == pytest.approx(72.10077804824489, abs=ATOL)


def test_old_audit_private_kernel_api_compatibility():
    assert tuple(inspect.signature(_backend.ema_sma).parameters) == ("data", "period")
    assert not hasattr(_backend, "adx_talib")
    assert tuple(inspect.signature(_backend.adx_wilder_sum).parameters) == (
        "high",
        "low",
        "close",
        "period",
    )


@pytest.mark.parametrize("pattern", PATTERNS)
def test_supertrend_atr_final_bands_reversals_and_seed_mapping(pattern):
    bars = fixture_bars(pattern)
    high, low, close, _ = arrays(bars)
    ours = indicators.supertrend(bars, 10, 3)
    atr, upper, lower, direction, values = reference_bands(bars)
    sdk_atr, _, _, sdk_direction, sdk_values = reference_bands(bars, sdk_initial=True)
    sdk_st, sdk_sign = ta.supertrend(high, low, close, period=10, multiplier=3)
    assert first_finite(atr) == first_finite(ta.atr(high, low, close, period=10)) == 9
    assert_numeric(field(ours, "atr"), atr)
    assert_numeric(ta.atr(high, low, close, period=10), sdk_atr)
    assert_numeric(field(ours, "direction"), direction)
    assert_numeric(field(ours, "value"), values)
    assert_numeric(-sdk_sign, sdk_direction)
    assert_numeric(sdk_st, sdk_values)
    for i in range(10, len(bars)):
        assert ours[i]["flip"] == (direction[i] != direction[i - 1])
        assert ours[i]["duration"] == (1 if ours[i]["flip"] else ours[i - 1]["duration"] + 1)
        if ours[i]["flip"]:
            assert close[i] > upper[i] if direction[i] == 1 else close[i] < lower[i]
    if pattern in ("rising", "falling", "volatile", "reversal"):
        assert_numeric(field(ours, "value")[79:], sdk_st[79:])
        assert_numeric(field(ours, "direction")[79:], -sdk_sign[79:])
    if pattern == "sideways":
        assert np.all(direction[9:] == 1) and np.all(sdk_direction[9:] == -1)
        assert_numeric(field(ours, "atr")[9:], np.full(len(bars) - 9, 40.0))
        assert abs(ours[-1]["value"] - sdk_st[-1]) > 119


@pytest.mark.parametrize("side", ("upper", "lower"))
def test_supertrend_does_not_reverse_at_band_equality(side):
    bars = fixture_bars("sideways", n=12)
    for i in range(10):
        bars[i] = bars[i].model_copy(
            update={"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0}
        )
    h, low, boundary, beyond = (
        (113.0, 99.0, 106.0, 106.01) if side == "upper" else (101.0, 87.0, 94.0, 93.99)
    )
    for i, close in ((10, boundary), (11, beyond)):
        bars[i] = bars[i].model_copy(update={"open": close, "high": h, "low": low, "close": close})
    ours = indicators.supertrend(bars, 10, 3)
    sdk_values, sdk_direction = ta.supertrend(*arrays(bars)[:3], period=10, multiplier=3)
    if side == "upper":
        assert sdk_direction[9:12].tolist() == [1, 1, -1]
        assert sdk_values[10] == pytest.approx(106, abs=ATOL)
    else:
        assert [row["direction"] for row in ours[9:12]] == [1, 1, -1]
        assert ours[10]["value"] == pytest.approx(94, abs=ATOL)


@pytest.mark.parametrize("period", (12, 26))
def test_macd_ema_seed_contract_and_independent_reference(period):
    bars = fixture_bars()
    close = arrays(bars)[2]
    custom = numeric(indicators.ema(close, period))
    sdk = ta.ema(close, period=period)
    assert first_finite(custom) == period - 1
    assert first_finite(sdk) == 0
    assert custom[period - 1] == pytest.approx(np.mean(close[:period]), abs=ATOL)
    assert sdk[0] == close[0]
    assert_numeric(custom, reference_smoothing(close, period, 2 / (period + 1)))
    assert_numeric(custom, _backend.ema_sma(close, period))
    assert_numeric(sdk, reference_smoothing(close, period, 2 / (period + 1), first_value=True))
    assert abs(custom[79] - sdk[79]) > 1e-6
    assert abs(custom[-1] - sdk[-1]) < ATOL


@pytest.mark.parametrize("n", (79, 80, 81, 150, 300, 525))
def test_macd_histogram_crossover_age_and_history_boundary(n):
    bars = fixture_bars(n=n)
    close = arrays(bars)[2]
    ours = indicators.macd(bars)
    fast, slow = (_backend.ema_sma(close, p) for p in (12, 26))
    line = fast - slow
    signal = _backend.ema_sma(line, 9)
    assert first_finite(field(ours, "line")) == 33
    assert_numeric(field(ours, "line")[33:], line[33:])
    assert_numeric(field(ours, "signal"), signal)
    assert_numeric(field(ours, "histogram"), line - signal)
    derived = momentum_rows(line, signal, line - signal)
    for actual, expected in zip(ours[33:], derived[33:], strict=True):
        for key in ("cross", "cross_direction", "cross_age"):
            assert actual[key] == expected[key]
    sdk_line, sdk_signal, sdk_hist = ta.macd(close, 12, 26, 9)
    f, s = (reference_smoothing(close, p, 2 / (p + 1), first_value=True) for p in (12, 26))
    assert_numeric(sdk_line, f - s)
    assert_numeric(sdk_signal, reference_smoothing(f - s, 9, 0.2, first_value=True))
    assert_numeric(sdk_hist, sdk_line - sdk_signal)
    assert first_finite(sdk_hist) == 0
    if n >= 300:
        assert abs(ours[-1]["histogram"] - sdk_hist[-1]) < 1e-7


@pytest.mark.parametrize("pattern", PATTERNS)
def test_adx_wilder_transition_seed_di_dx_and_slope(pattern):
    bars = fixture_bars(pattern)
    ours = indicators.adx(bars)
    tr, plus, minus, p, m, dx, a = reference_dm(bars)
    sdk_p, sdk_m, sdk_a = ta.adx(*arrays(bars)[:3], period=14)
    _, _, _, ref_p, ref_m, ref_dx, ref_a = reference_dm(bars, include_bar_zero=True)
    assert np.isnan(tr[0]) and np.isnan(plus[0]) and np.isnan(minus[0])
    assert first_finite(a) == first_finite(field(ours, "adx")) == 27
    assert first_finite(sdk_p) == first_finite(sdk_m) == 13
    assert first_finite(sdk_a) == 26
    assert_numeric(field(ours, "adx"), a)
    assert_numeric(field(ours, "plus_di")[27:], p[27:])
    assert_numeric(field(ours, "minus_di")[27:], m[27:])
    assert_numeric(field(ours, "slope")[28:], np.diff(a)[27:])
    assert ours[27]["slope"] == 0
    assert_numeric(sdk_p, ref_p)
    assert_numeric(sdk_m, ref_m)
    assert_numeric(sdk_a, ref_a)
    den = sdk_p + sdk_m
    actual_dx = np.divide(
        100 * abs(sdk_p - sdk_m), den, out=np.full(len(bars), np.nan), where=den > 0
    )
    assert_numeric(actual_dx, ref_dx)
    assert_numeric(a, reference_smoothing(dx, 14, 1 / 14))
    assert abs(ours[-1]["adx"] - sdk_a[-1]) < ATOL


def test_adx_true_range_dm_ties_and_zero_range_conventions():
    bars = fixture_bars(n=80)
    for i in range(80):
        bars[i] = bars[i].model_copy(
            update={"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0}
        )
    ours = indicators.adx(bars)
    assert all(
        row == {"adx": 0, "plus_di": 0, "minus_di": 0, "slope": 0, "strength": "WEAK"}
        for row in ours[27:]
    )
    assert all(np.isnan(a).all() for a in ta.adx(*arrays(bars)[:3], period=14))
    # Equal outside moves are neither +DM nor -DM; gaps use previous close.
    bars[1] = bars[1].model_copy(update={"high": 103.0, "low": 97.0})
    bars[2] = bars[2].model_copy(
        update={"open": 110.0, "close": 110.0, "high": 111.0, "low": 109.0}
    )
    tr, plus, minus, *_ = reference_dm(bars)
    assert (tr[1], plus[1], minus[1]) == (6, 0, 0)
    assert (tr[2], plus[2], minus[2]) == (11, 8, 0)
    assert_numeric(indicators.ranges(bars)[1:], tr[1:])
    assert_numeric(field(indicators.adx(bars), "adx"), reference_dm(bars)[-1])


@pytest.mark.parametrize("basis", ("typical", "close"))
def test_vwap_session_by_session_markers_and_ist_timestamps(basis):
    bars = fixture_bars(n=300)
    ours = indicators.vwap(bars, basis=basis)
    markers = session_markers(bars)
    sdk = sdk_vwap(bars, basis, session_starts=markers)
    assert_numeric(numeric(ours), sdk)
    times = pd.DatetimeIndex([b.start for b in bars]).tz_convert(IST)
    assert_numeric(sdk_vwap(bars, basis, timestamps=times), sdk)
    for start in range(0, 300, 75):
        window = bars[start : start + 75]
        h, low, c, volume = arrays(window)
        source = (h + low + c) / 3 if basis == "typical" else c
        expected = np.cumsum(source * volume) / np.cumsum(volume)
        assert_numeric(ours[start : start + 75], expected)
        assert_numeric(sdk_vwap(window, basis, anchor=None), expected)
    # A cumulative multi-day SDK call is deliberately not the parity oracle.
    assert abs(sdk_vwap(bars, basis, anchor=None)[75] - ours[75]) > 1


def test_vwap_hand_values_zero_and_missing_volume_changed_in_241():
    bars = fixture_bars(n=5)
    for i, (close, volume) in enumerate(((100, 0), (110, 10), (120, 0), (130, 30), (140, 10))):
        bars[i] = bars[i].model_copy(
            update={
                "open": close,
                "close": close,
                "high": close + 3,
                "low": close - 1,
                "volume": volume,
            }
        )
    assert_numeric(numeric(indicators.vwap(bars, basis="close")), [np.nan, 110, 110, 125, 128])
    assert_numeric(sdk_vwap(bars, "close", anchor=None), [np.nan, 110, 110, 125, 128])
    assert_numeric(
        numeric(indicators.vwap(bars)),
        numeric([None, 110 + 2 / 3, 110 + 2 / 3, 125 + 2 / 3, 128 + 2 / 3]),
    )
    zero = [b.model_copy(update={"volume": 0}) for b in bars]
    assert indicators.vwap(zero) == [None] * 5
    assert np.isnan(sdk_vwap(zero, anchor=None)).all()  # 2.0.5 raised RuntimeError.
    missing = bars[:2] + [bars[2].model_copy(update={"volume": None})] + bars[3:]
    assert indicators.vwap(missing, basis="close") == [None, 110, None, None, None]
    # 2.4.1 skips the missing observation, then resumes accumulated sums.
    assert_numeric(sdk_vwap(missing, "close", anchor=None), [np.nan, 110, np.nan, 125, 128])
    next_day = [
        b.model_copy(
            update={"start": b.start + timedelta(days=1), "end": b.end + timedelta(days=1)}
        )
        for b in bars[1:]
    ]
    assert indicators.vwap(missing + next_day, basis="close")[5] == 110
    assert indicators.vwap(bars, instrument_kind="SPOT") == [None] * 5
    mixed = bars[:3] + [b.model_copy(update={"token": "NEXT-FUT"}) for b in bars[3:]]
    assert indicators.vwap(mixed) == [None] * 5
    assert signal_engine.completed_series(mixed, mixed[-1].end, bars[0].token, 5) == []


def test_vwap_ist_date_reset_is_not_a_utc_date_reset():
    bars = fixture_bars(n=3)
    times = [
        datetime(2026, 11, 2, 23, 55, tzinfo=IST),
        datetime(2026, 11, 3, 0, 0, tzinfo=IST),
        datetime(2026, 11, 3, 0, 5, tzinfo=IST),
    ]
    # Calendar-only edge fixture, not an NSE trading-session claim.
    bars = [
        b.model_copy(
            update={"start": t.astimezone(UTC), "end": (t + timedelta(minutes=5)).astimezone(UTC)}
        )
        for b, t in zip(bars, times, strict=True)
    ]
    assert len({b.start.date() for b in bars}) == 1
    ours = indicators.vwap(bars)
    assert_numeric(numeric(ours), sdk_vwap(bars, session_starts=[True, True, False]))
    assert_numeric(numeric(ours), sdk_vwap(bars, timestamps=pd.DatetimeIndex(times)))
    assert ours[1] == pytest.approx((bars[1].high + bars[1].low + bars[1].close) / 3, abs=ATOL)


@pytest.mark.parametrize("cut", (9, 10, 27, 34, 79, 80, 81, 150))
def test_all_indicators_prefix_causality(cut):
    bars = fixture_bars(n=225)
    for calculate in (indicators.supertrend, indicators.macd, indicators.adx, indicators.vwap):
        assert calculate(bars)[:cut] == calculate(bars[:cut])
    high, low, close, _ = arrays(bars)
    for calculate, minimum in ((ta.supertrend, 10), (ta.adx, 14), (ta.atr, 14)):
        full = calculate(high, low, close)
        if cut < minimum:
            with pytest.raises(ValueError, match="cannot be greater than data length"):
                calculate(high[:cut], low[:cut], close[:cut])
            continue
        prefix = calculate(high[:cut], low[:cut], close[:cut])
        if isinstance(full, tuple):
            for a, b in zip(full, prefix, strict=True):
                assert_numeric(a[:cut], b)
        else:
            assert_numeric(full[:cut], prefix)
    for calculate, minimum in (
        (lambda c: ta.macd(c), 1),
        (lambda c: ta.ema(c, period=12), 12),
        (lambda c: ta.ema(c, period=26), 26),
    ):
        full = calculate(close)
        # Public MACD accepts short first-seeded input; EMA validates its period.
        if cut < minimum:
            with pytest.raises(ValueError, match="cannot be greater than data length"):
                calculate(close[:cut])
            continue
        prefix = calculate(close[:cut])
        if isinstance(full, tuple):
            for a, b in zip(full, prefix, strict=True):
                assert_numeric(a[:cut], b)
        else:
            assert_numeric(full[:cut], prefix)
    assert_numeric(
        sdk_vwap(bars, session_starts=session_markers(bars))[:cut],
        sdk_vwap(bars[:cut], session_starts=session_markers(bars[:cut])),
    )


def test_completed_candles_future_append_and_80_bar_rule():
    bars = fixture_bars(n=81)
    config = StrategyConfig(atr_period=10, atr_multiplier=3)
    now = bars[79].end
    expected = signal_engine.Rules().evaluate(
        bars[:80], [], None, now, config, config.version_id, bars[0].token
    )
    forming = bars[80].model_copy(update={"complete": False, "high": 99999.0, "close": 99999.0})
    for appended in (bars[80], forming):
        assert (
            signal_engine.Rules().evaluate(
                bars[:80] + [appended], [], None, now, config, config.version_id, bars[0].token
            )
            == expected
        )
    assert signal_engine.snapshot(bars[:80], config) == expected["snapshot"]
    assert (
        signal_engine.completed_series(bars[:80] + [forming], forming.end, bars[0].token, 5)
        == bars[:80]
    )
    higher = [
        b.model_copy(
            update={
                "timeframe": 15,
                "start": bars[0].start - timedelta(minutes=15 * (80 - i)),
                "end": bars[0].start - timedelta(minutes=15 * (79 - i)),
            }
        )
        for i, b in enumerate(bars[:80])
    ]
    for n, state in ((79, "FAIL"), (80, "PASS"), (81, "PASS")):
        result = signal_engine.Rules().evaluate(
            bars[:n], higher, None, bars[n - 1].end, config, config.version_id, bars[0].token
        )
        assert next(c["state"] for c in result["checks"] if c["rule"] == "R-WARMUP") == state


def test_missing_history_is_refused_or_trimmed_before_vwap():
    bars = fixture_bars(n=225)
    now = bars[-1].end
    # Current-session hole blocks the series; a historical hole retains only
    # its continuous suffix and reruns the unchanged 80-bar requirement.
    assert signal_engine.completed_series(bars[:200] + bars[201:], now, bars[0].token, 5) == []
    suffix = signal_engine.completed_series(bars[:20] + bars[21:], now, bars[0].token, 5)
    assert suffix == bars[21:]
    assert (
        signal_engine.snapshot(suffix, StrategyConfig(atr_period=10, atr_multiplier=3))["vwap"]
        == indicators.vwap(bars[150:])[-1]
    )
    # Pure VWAP cannot know the effective opening time; assessment owns that guard.
    partial = bars[151:]
    assert indicators.vwap(partial)[0] is not None
    minute = bars[150].model_copy(
        update={"timeframe": 1, "end": bars[150].start + timedelta(minutes=1)}
    )
    opening = [
        minute.model_copy(
            update={
                "start": minute.start + timedelta(minutes=i),
                "end": minute.end + timedelta(minutes=i),
            }
        )
        for i in range(1, 10)
    ]
    assert [b.start for b in aggregate(opening, 5, opening[-1].end, session_open=minute.start)] == [
        minute.start + timedelta(minutes=5)
    ]


@pytest.mark.parametrize(
    "legacy,age,passed",
    (
        (False, 0, True),
        (False, 1, True),
        (False, 2, True),
        (False, 3, False),
        (False, 4, False),
        # A stored 3.1.0 record replays with the rule it was decided under.
        (True, 3, True),
        (True, 4, False),
    ),
)
def test_actual_macd_freshness_boundary(monkeypatch, legacy, age, passed):
    bars = fixture_bars(n=80)
    snap = signal_engine.snapshot(bars, StrategyConfig(atr_period=10, atr_multiplier=3))
    direction = snap["supertrend"]["direction"]
    snap["macd"].update(cross_direction=direction, cross_age=age, histogram=float(direction))
    monkeypatch.setattr(signal_engine, "snapshot", lambda bars, config: snap if bars else {})
    config = legacy_31() if legacy else StrategyConfig(atr_period=10, atr_multiplier=3)
    assert config.crossover_freshness == (3 if legacy else 2)
    result = signal_engine.Rules().evaluate(
        bars, [], None, bars[-1].end, config, config.version_id, bars[0].token
    )
    assert result["indicator_states"]["macd"]["gate"] == ("PASS" if passed else "FAIL")


@pytest.mark.parametrize("value,passed", ((24.999999, False), (25.0, True), (25.000001, True)))
def test_actual_adx_inclusive_25_boundary(monkeypatch, value, passed):
    bars = fixture_bars(n=80)
    snap = signal_engine.snapshot(bars, StrategyConfig(atr_period=10, atr_multiplier=3))
    snap["adx"]["adx"] = value
    monkeypatch.setattr(signal_engine, "snapshot", lambda bars, config: snap if bars else {})
    config = StrategyConfig(atr_period=10, atr_multiplier=3)
    assert config.adx_min == 25
    result = signal_engine.Rules().evaluate(
        bars, [], None, bars[-1].end, config, config.version_id, bars[0].token
    )
    assert result["indicator_states"]["adx"]["gate"] == ("PASS" if passed else "FAIL")


def decision_disagreements(seed_count=64, isolate_direction=True, config=None):
    """Frozen census: 64 PCG64 paths, 525 bars, indices 79..524 inclusive.

    Hold custom ST direction fixed for MACD/ADX/VWAP to isolate each indicator.
    ST compares each implementation's own normalized direction and band.
    """
    disagreements = {gate: [] for gate in GATES}
    side_changes = []
    config = config or StrategyConfig(atr_period=10, atr_multiplier=3)
    for seed in range(seed_count):
        bars = fixture_bars(seed=seed)
        custom, sdk = comparison(bars)
        for i in range(79, len(bars)):
            st, momentum, strength, vw = [series[i] for series in custom]
            sdk_st, sdk_momentum, sdk_strength, sdk_vw = [series[i] for series in sdk]
            ours = gate_values(bars[i].close, st, momentum, strength, vw, config)
            theirs = gate_values(
                bars[i].close,
                st if isolate_direction else sdk_st,
                sdk_momentum,
                sdk_strength,
                sdk_vw,
                config,
            )
            theirs["R-ST"] = gate_values(
                bars[i].close, sdk_st, sdk_momentum, sdk_strength, sdk_vw, config
            )["R-ST"]
            if st["direction"] != sdk_st["direction"]:
                side_changes.append((seed, i))
            for gate in GATES:
                if ours[gate] != theirs[gate]:
                    disagreements[gate].append((seed, i))
    return disagreements, side_changes


@pytest.mark.parametrize("legacy", (True, False), ids=("v3.1.0-ages-0-3", "current-ages-0-2"))
@pytest.mark.parametrize("isolate_direction", (True, False))
def test_deterministic_decision_disagreement_census(isolate_direction, legacy):
    disagreements, side_changes = decision_disagreements(
        isolate_direction=isolate_direction,
        config=legacy_31() if legacy else StrategyConfig(atr_period=10, atr_multiplier=3),
    )
    if legacy:
        macd = ([] if isolate_direction else [(4, 79), (4, 80), (4, 81)]) + [
            (21, 80),
            (49, 88),
            (54, 124),
        ]
    else:
        macd = ([] if isolate_direction else [(4, 79), (4, 80)]) + [
            (21, 79),
            (49, 87),
            (54, 124),
        ]
    assert disagreements == {
        "R-ST": [],
        "R-MACD": macd,
        "R-ADX": [(1, 90), (20, 106), (45, 149), (57, 97)],
        "R-VWAP": [] if isolate_direction else [(4, i) for i in range(79, 90)],
    }
    assert side_changes == [(4, i) for i in range(79, 90)]


@pytest.mark.parametrize(
    "legacy,pattern,counts,side_changes",
    (
        (True, "rising", (0, 0, 0, 0), 0),
        (True, "falling", (0, 0, 0, 0), 0),
        (True, "sideways", (0, 189, 0, 444), 446),
        (True, "volatile", (0, 0, 0, 0), 0),
        (True, "reversal", (0, 0, 0, 0), 0),
        (True, "low_volatility", (0, 126, 0, 446), 446),
        (False, "rising", (0, 0, 0, 0), 0),
        (False, "falling", (0, 0, 0, 0), 0),
        (False, "sideways", (0, 141, 0, 444), 446),
        (False, "volatile", (0, 0, 0, 0), 0),
        (False, "reversal", (0, 0, 0, 0), 0),
        (False, "low_volatility", (0, 100, 0, 446), 446),
    ),
)
def test_named_fixture_native_direction_gate_disagreements(legacy, pattern, counts, side_changes):
    bars = fixture_bars(pattern)
    custom, sdk = comparison(bars)
    config = legacy_31() if legacy else StrategyConfig(atr_period=10, atr_multiplier=3)
    actual_counts = dict.fromkeys(GATES, 0)
    actual_sides = 0
    for i in range(79, 525):
        ours = gate_values(bars[i].close, *[r[i] for r in custom], config)
        theirs = gate_values(bars[i].close, *[r[i] for r in sdk], config)
        actual_sides += custom[0][i]["direction"] != sdk[0][i]["direction"]
        for gate in GATES:
            actual_counts[gate] += int(ours[gate] != theirs[gate])
    assert tuple(actual_counts.values()) == counts
    assert actual_sides == side_changes


@pytest.mark.parametrize(
    "legacy,seed,index,gate",
    (
        (True, 21, 80, "R-MACD"),
        (True, 49, 88, "R-MACD"),
        (True, 54, 124, "R-MACD"),
        (False, 21, 79, "R-MACD"),
        (False, 49, 87, "R-MACD"),
        (False, 54, 124, "R-MACD"),
        # The 3.1.0 counterexamples agree under the three-candle window.
        (False, 21, 80, None),
        (False, 49, 88, None),
        (False, 1, 90, "R-ADX"),
        (False, 20, 106, "R-ADX"),
        (False, 45, 149, "R-ADX"),
        (False, 57, 97, "R-ADX"),
        (False, 4, 79, None),
        (False, 241, 79, None),
    ),
)
@pytest.mark.parametrize("zero_required,di_confirmation", ((False, False), (True, True)))
def test_gate_projection_matches_actual_rules(
    monkeypatch, legacy, seed, index, gate, zero_required, di_confirmation
):
    bars = fixture_bars(seed=seed)
    custom, sdk = comparison(bars)
    settings = {"macd_zero_required": zero_required, "di_confirmation": di_confirmation}
    config = (
        legacy_31(**settings)
        if legacy
        else StrategyConfig(**({"atr_period": 10, "atr_multiplier": 3} | settings))
    )
    actual_states = []
    for series in (custom, sdk):
        st, momentum, strength, vw = [rows[index] for rows in series]
        snap = {
            "price": bars[index].close,
            "supertrend": st,
            "macd": momentum,
            "adx": strength,
            "vwap": vw,
            "end": bars[index].end.isoformat(),
        }
        monkeypatch.setattr(
            signal_engine, "snapshot", lambda bars, config, value=snap: value if bars else {}
        )
        result = signal_engine.Rules().evaluate(
            bars[: index + 1], [], None, bars[index].end, config, config.version_id, bars[0].token
        )
        actual = {c["rule"]: c["state"] == "PASS" for c in result["checks"] if c["rule"] in GATES}
        assert actual == gate_values(bars[index].close, st, momentum, strength, vw, config)
        actual_states.append(actual)
    if gate is not None and not zero_required:
        assert actual_states[0][gate] != actual_states[1][gate]
    if gate is None and (seed, index) in ((21, 80), (49, 88)):
        assert actual_states[0]["R-MACD"] is False
        assert actual_states[1]["R-MACD"] is False
        if (seed, index) == (54, 124):
            assert [all(state.values()) for state in actual_states] == [False, True]


def test_missing_volume_sdk_resumption_would_change_actual_vwap_gate(monkeypatch):
    bars = fixture_bars(seed=0, n=80)
    bars[77] = bars[77].model_copy(update={"volume": None})
    config = StrategyConfig(atr_period=10, atr_multiplier=3)
    snap = signal_engine.snapshot(bars, config)
    assert snap["vwap"] is None
    monkeypatch.setattr(signal_engine, "snapshot", lambda bars, config: snap if bars else {})
    args = (bars, [], None, bars[-1].end, config, config.version_id, bars[0].token)
    assert (
        signal_engine.Rules().evaluate(*args)["indicator_states"]["vwap"]["gate"] == "UNAVAILABLE"
    )
    snap["vwap"] = float(sdk_vwap(bars, session_starts=session_markers(bars))[-1])
    assert snap["vwap"] == pytest.approx(22062.28100736435, abs=ATOL)
    assert signal_engine.Rules().evaluate(*args)["indicator_states"]["vwap"]["gate"] == "PASS"


@pytest.mark.parametrize("direction", (1, -1))
@pytest.mark.parametrize("extension,passed", ((0, True), (80, True), (80.0001, False)))
def test_actual_vwap_alignment_and_inclusive_extension(monkeypatch, direction, extension, passed):
    bars = fixture_bars(n=80)
    config = StrategyConfig(atr_period=10, atr_multiplier=3)
    snap = signal_engine.snapshot(bars, config)
    snap["supertrend"]["direction"] = direction
    snap["vwap"], snap["price"] = 10000.0, 10000.0 + direction * extension
    monkeypatch.setattr(signal_engine, "snapshot", lambda bars, config: snap if bars else {})
    result = signal_engine.Rules().evaluate(
        bars, [], None, bars[-1].end, config, config.version_id, bars[0].token
    )
    assert result["indicator_states"]["vwap"]["gate"] == ("PASS" if passed else "FAIL")


@pytest.mark.parametrize("pattern", ("volatile", "sideways"))
def test_sdk_numpy_fallback_matches_installed_backend(monkeypatch, pattern):
    bars = fixture_bars(pattern, n=150)
    h, low, c, _ = arrays(bars)

    def outputs():
        return (
            ta.atr(h, low, c, period=10),
            *ta.supertrend(h, low, c, 10, 3),
            ta.ema(c, 12),
            ta.ema(c, 26),
            *ta.macd(c, 12, 26, 9),
            *ta.adx(h, low, c, 14),
            sdk_vwap(bars, session_starts=session_markers(bars)),
        )

    installed = outputs()
    monkeypatch.setattr(_backend, "HAVE_RUST", False)
    for actual, expected in zip(outputs(), installed, strict=True):
        assert_numeric(actual, expected)
