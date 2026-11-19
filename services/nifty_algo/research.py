"""Causal candle studies using native history inputs and the production decision rules."""

from datetime import timedelta
from zoneinfo import ZoneInfo

from .market_data import aggregate
from .signal_engine import Rules

IST = ZoneInfo("Asia/Kolkata")


def signal_study(bars, config, start, end, *, session_opens):
    """Session anchors are dated native calendar observations keyed by local date.

    The interval is [start, end). Without historical chain observations PCR is
    unavailable, so strict entry eligibility stays false in this candle study.
    """
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError("Ordered timezone-aware study interval required")
    ordered = sorted(bars, key=lambda bar: bar.start)
    if len({bar.token for bar in ordered}) > 1:
        raise ValueError("One futures instrument per study required")
    if any(left.end > right.start for left, right in zip(ordered, ordered[1:], strict=False)):
        raise ValueError("Overlapping or duplicate candle history")
    by_day = {}
    for bar in ordered:
        by_day.setdefault(bar.start.astimezone(IST).date(), []).append(bar)
    entries, higher = [], []
    for day, daily in sorted(by_day.items()):
        anchor = session_opens.get(day)
        if anchor is None:
            raise ValueError("Effective session opening missing for history date")
        entries.extend(aggregate(daily, 5, end, session_open=anchor))
        higher.extend(aggregate(daily, 15, end, session_open=anchor))
    decisions = []
    for bar in entries:
        if start <= bar.end < end:
            decisions.append(
                Rules().evaluate(
                    [known for known in entries if known.end <= bar.end],
                    [known for known in higher if known.end <= bar.end],
                    None,
                    bar.end,
                    config,
                    config.version_id,
                    bar.token,
                )
            )
    return {
        "mode": "SIGNAL_ONLY",
        "decisions": decisions,
        "trades": [],
        "performance": None,
        "limitations": [
            "Candle study has no historical option premiums or execution fills.",
            "Historical PCR is unavailable. Strict entry eligibility remains blocked.",
        ],
    }


def options_replay(*args, **kwargs):
    """Refuse a premium simulation until a validated historical quote model exists."""
    raise ValueError(
        "OPTION_REPLAY_UNAVAILABLE: timestamped option depth and verified metadata required"
    )


def walk_forward_windows(start, end, train_days=20, test_days=5):
    """Half-open slices share a boundary, with no observation in both slices."""
    if start >= end or train_days <= 0 or test_days <= 0:
        raise ValueError("Positive ordered walk-forward ranges required")
    windows = []
    cursor = start + timedelta(days=train_days)
    while cursor + timedelta(days=test_days) <= end:
        windows.append(
            {
                "train_start": cursor - timedelta(days=train_days),
                "train_end": cursor,
                "test_start": cursor,
                "test_end": cursor + timedelta(days=test_days),
                "interval_convention": "[start, end)",
            }
        )
        cursor += timedelta(days=test_days)
    return windows
