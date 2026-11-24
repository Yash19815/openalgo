"""Pure time boundaries shared by PAPER admission, fills and replay."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
SESSION_EXIT_BUFFER = timedelta(minutes=5)


def entry_cutoff(now, config, session_close=None):
    day = now.astimezone(IST).date()
    cutoff = datetime.combine(day, min(time(14, 45), config.entry_before), IST)
    return min(cutoff, session_close - SESSION_EXIT_BUFFER) if session_close else cutoff


def pending_entry_expiry(now, config, session_close=None):
    return min(
        now + timedelta(seconds=config.order_ttl_seconds), entry_cutoff(now, config, session_close)
    )
