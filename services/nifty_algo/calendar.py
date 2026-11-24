"""NIFTY paper-trading session authority over user-approved NFO calendars."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def approved_calendar(user_id, year, *, store):
    return store.approved_calendar_version(user_id, year)


def _legacy_calendar():
    from database import market_calendar_db

    return market_calendar_db


def legacy_nfo_holidays(year):
    market = _legacy_calendar()
    try:
        return sorted(
            item["date"]
            for item in market.get_holidays_by_year(year)
            if item.get("holiday_type") == "TRADING_HOLIDAY"
            and "NFO" in item.get("closed_exchanges", [])
        )
    finally:
        market.db_session.remove()


def preview_diff(entries, year):
    legacy = set(legacy_nfo_holidays(year))
    approved = {item["date"] for item in entries if item.get("date")}
    return {
        "legacy_only": sorted(legacy - approved),
        "calendar_only": sorted(approved - legacy),
    }


def nifty_session(user_id, day, *, store):
    if isinstance(day, datetime):
        day = day.astimezone(IST).date()
    if not isinstance(day, date):
        raise ValueError("Session lookup requires a date")
    calendar = approved_calendar(user_id, day.year, store=store)
    if calendar is None:
        return {"status": "CALENDAR_UNAPPROVED", "window": None}

    market = _legacy_calendar()
    try:
        if market.get_special_session(day, "NFO"):
            return {"status": "SPECIAL_SESSION_DISABLED", "window": None}
        if day.weekday() >= 5:
            return {"status": "WEEKEND", "window": None}
        if day.isoformat() in {item["date"] for item in calendar["entries"] if item.get("date")}:
            return {"status": "HOLIDAY", "window": None}

        timing = market.get_effective_session_window(day, "NFO")
        if timing is None:
            timing = market.get_market_timing("NFO")
            if timing is None:
                return {"status": "SESSION_WINDOW_UNAVAILABLE", "window": None}
            start_ms = int(timing["start_offset"])
            end_ms = int(timing["end_offset"])
            midnight = datetime.combine(day, datetime.min.time(), tzinfo=IST)
            start = datetime.fromtimestamp(midnight.timestamp() + start_ms / 1000, IST)
            end = datetime.fromtimestamp(midnight.timestamp() + end_ms / 1000, IST)
        else:
            start = datetime.fromtimestamp(timing["start_ms"] / 1000, IST)
            end = datetime.fromtimestamp(timing["end_ms"] / 1000, IST)
        return {"status": "TRADING", "window": (start, end)}
    finally:
        market.db_session.remove()


def next_eligible_session(user_id, day, *, store):
    if isinstance(day, datetime):
        day = day.astimezone(IST).date()
    candidate = day + timedelta(days=1)
    for _ in range(370):
        if approved_calendar(user_id, candidate.year, store=store) is None:
            raise ValueError("CALENDAR_UNAPPROVED")
        result = nifty_session(user_id, candidate, store=store)
        if result["status"] == "TRADING":
            return candidate
        if result["status"] == "CALENDAR_UNAPPROVED":
            raise ValueError("CALENDAR_UNAPPROVED")
        candidate += timedelta(days=1)
    raise ValueError("No eligible session found within one year")
