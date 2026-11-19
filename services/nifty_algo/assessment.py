"""Observed futures-history assessments through native read-only services."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from .config import StrategyConfig
from .market_data import aggregate
from .models import Candle
from .native_data import NativeDataAdapter, _timestamp
from .signal_engine import Rules

IST = ZoneInfo("Asia/Kolkata")
MAX_HISTORY_ROWS = 10000


def _history(**kwargs):
    from services.history_service import get_history

    return get_history(**kwargs)


def _session(day, exchange):
    from database.market_calendar_db import db_session, get_effective_session_window

    try:
        return get_effective_session_window(day, exchange)
    finally:
        db_session.remove()


def _window(day, session_reader):
    result = session_reader(day, "NFO")
    if result is None:
        return None
    start = _timestamp(result.get("start_ms"))
    end = _timestamp(result.get("end_ms"))
    if start is None or end is None or start >= end:
        raise ValueError("Invalid native session window")
    if start.astimezone(IST).date() != day or end.astimezone(IST).date() != day:
        raise ValueError("Native session date mismatch")
    return start, end


def _candles(rows, token, now, first_day, session_reader):
    if not isinstance(rows, list) or len(rows) > MAX_HISTORY_ROWS:
        raise ValueError("History must contain at most 10000 minute rows")
    bars = []
    windows = {}
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("History row requires named candle fields")
        start = _timestamp(row.get("timestamp"))
        if start is None or start.second or start.microsecond:
            raise ValueError("History requires aligned UTC epoch minute timestamps")
        end = start + timedelta(minutes=1)
        day = start.astimezone(IST).date()
        if end > now or day < first_day:
            continue
        if any(
            isinstance(row.get(field), bool) for field in ("open", "high", "low", "close", "volume")
        ):
            raise ValueError("History OHLCV values must be numeric")
        if start in seen:
            raise ValueError("Duplicate historical candle timestamp")
        seen.add(start)
        bar = Candle(
            token=token,
            start=start,
            end=end,
            timeframe=1,
            open=row.get("open"),
            high=row.get("high"),
            low=row.get("low"),
            close=row.get("close"),
            volume=row.get("volume"),
            complete=True,
            provenance="OBSERVED_BROKER_HISTORY",
        )
        if day not in windows:
            windows[day] = _window(day, session_reader)
        window = windows[day]
        if window and window[0] <= start and end <= window[1]:
            bars.append(bar)
    return sorted(bars, key=lambda bar: bar.start), windows


def assess_current(
    api_key,
    config,
    now=None,
    *,
    history_reader=None,
    instrument_loader=None,
    session_reader=None,
):
    """Compute an explainable observation without creating an order intent.

    Dependencies are injectable for offline fixtures. PCR remains unavailable
    because native chain responses do not establish per-leg causal freshness.
    """
    if not api_key:
        raise ValueError("Authenticated OpenAlgo API key required")
    config = config if isinstance(config, StrategyConfig) else StrategyConfig.model_validate(config)
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("Assessment timestamp requires timezone")
    now = now.astimezone(UTC)
    today = now.astimezone(IST).date()
    first_day = today - timedelta(days=9)
    session_reader = session_reader or _session
    native = NativeDataAdapter(instrument_loader=instrument_loader, clock=lambda: now)
    futures = sorted(
        (row for row in native._instruments(now) if row["kind"] == "FUT"),
        key=lambda row: (row["expiry"], row["symbol"]),
    )
    instrument = futures[0] if futures else None
    bars, windows = [], {}
    issue = None
    if instrument:
        ok, response, _status = (history_reader or _history)(
            symbol=instrument["symbol"],
            exchange="NFO",
            interval="1m",
            start_date=first_day.isoformat(),
            end_date=today.isoformat(),
            api_key=api_key,
        )
        if ok and isinstance(response, dict) and response.get("status") == "success":
            bars, windows = _candles(
                response.get("data"),
                instrument["token"],
                now,
                first_day,
                session_reader,
            )
        else:
            issue = "HISTORY_UNAVAILABLE"
    else:
        issue = "CURRENT_NIFTY_FUTURE_UNAVAILABLE"
    entry, higher = [], []
    for day, window in sorted(windows.items()):
        if window:
            session_bars = [bar for bar in bars if bar.start.astimezone(IST).date() == day]
            entry.extend(aggregate(session_bars, 5, now, session_open=window[0]))
            higher.extend(aggregate(session_bars, 15, now, session_open=window[0]))
    decision = Rules().evaluate(
        entry,
        higher,
        None,
        now,
        config,
        config.version_id,
        instrument["token"] if instrument else "NIFTY_FUTURE_UNAVAILABLE",
    )
    if issue:
        decision["checks"].append({"rule": "R-HISTORY", "state": "UNAVAILABLE", "detail": issue})
        decision["reasons"].append("R-HISTORY: " + issue)
    decision.update(
        {
            "eligible": False,
            "final_action": "NO_ORDER",
            "risk": {
                "approved": False,
                "reasons": ["OBSERVATION_ONLY", "VERIFIED_PCR_UNAVAILABLE"],
            },
            "source": "OBSERVED_BROKER_HISTORY",
            "analysis_instrument": instrument,
            "history": {
                "start_date": first_day.isoformat(),
                "end_date": today.isoformat(),
                "minute_bars": len(bars),
                "entry_bars": len(entry),
                "confirmation_bars": len(higher),
            },
        }
    )
    return decision
