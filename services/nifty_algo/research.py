"""Causal candle studies using native history inputs and the production decision rules.

Research only: nothing here admits, fills or transmits an order.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from zoneinfo import ZoneInfo

from .market_data import aggregate
from .signal_engine import Rules

IST = ZoneInfo("Asia/Kolkata")
OBSERVATION_WINDOW = timedelta(minutes=45)
# Testable hypotheses: terminal moves of the analysis future, in entry-candle ATRs.
FAVORABLE_ATR_MULTIPLE = Decimal("1")
ADVERSE_ATR_MULTIPLE = Decimal("1")


def opportunity_id(candle_end, direction, configuration_id):
    """Stable identity of one completed signal candle, side and configuration."""
    if isinstance(candle_end, str):
        candle_end = datetime.fromisoformat(candle_end)
    if candle_end.tzinfo is None:
        raise ValueError("Timezone-aware candle end required")
    if direction not in ("CE", "PE") or not configuration_id:
        raise ValueError("CE/PE direction and configuration id required")
    stamp = candle_end.astimezone(UTC).isoformat()
    return sha256(f"{stamp}:{direction}:{configuration_id}".encode()).hexdigest()


def opportunity_from_decision(decision, config):
    """Observation record for a qualifying signal, or None. Never an order intent."""
    snapshot = decision.get("snapshot") or {}
    side = decision.get("side")
    if not decision.get("eligible") or side not in ("CE", "PE") or not decision.get("config_id"):
        return None
    try:
        end = datetime.fromisoformat(snapshot["end"])
        price = Decimal(str(snapshot["price"]))
        atr = Decimal(str((snapshot.get("supertrend") or {}).get("atr")))
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return None
    if end.tzinfo is None or not price.is_finite() or price <= 0:
        return None
    if not atr.is_finite() or atr <= 0:
        return None
    cutoff = datetime.combine(end.astimezone(IST).date(), config.exit_by, tzinfo=IST)
    if end >= cutoff:
        return None
    window_end = end + OBSERVATION_WINDOW
    deadline, deadline_reason = (
        (window_end, "WINDOW_45M") if window_end <= cutoff else (cutoff, "SESSION_CUTOFF")
    )
    return {
        "opportunity_id": opportunity_id(end, side, decision["config_id"]),
        "candle_end": end.astimezone(UTC).isoformat(),
        "direction": side,
        "configuration_id": decision["config_id"],
        "decision_id": decision.get("decision_id"),
        "analysis_token": decision.get("analysis_token"),
        "reference_price": str(price),
        "atr": str(atr),
        "favorable_threshold": str(atr * FAVORABLE_ATR_MULTIPLE),
        "adverse_threshold": str(atr * ADVERSE_ATR_MULTIPLE),
        "deadline": deadline.astimezone(UTC).isoformat(),
        "deadline_reason": deadline_reason,
        "status": "OBSERVING",
        "outcome": None,
        "steps": [],
        "max_favorable": "0",
        "max_adverse": "0",
        "last_observed_at": None,
        "closed_at": None,
        "research_only": True,
    }


def _stopped(opportunity, outcome, at):
    return {
        **opportunity,
        "status": "CLOSED",
        "outcome": outcome,
        "closed_at": at.astimezone(UTC).isoformat(),
    }


def observe_opportunity(opportunity, observation):
    """One causal step from a completed candle of the same analysis future.

    Stops at the first terminal threshold (adverse checked first), at the
    45-minute window, or at the session cutoff, whichever comes first.
    """
    if opportunity["status"] != "OBSERVING":
        return opportunity
    try:
        at = datetime.fromisoformat(observation["at"])
        price = Decimal(str(observation["price"]))
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return opportunity
    if (
        at.tzinfo is None
        or not price.is_finite()
        or price <= 0
        or observation.get("token") != opportunity["analysis_token"]
    ):
        return opportunity
    last = datetime.fromisoformat(opportunity["last_observed_at"] or opportunity["candle_end"])
    if at <= last:
        return opportunity
    deadline = datetime.fromisoformat(opportunity["deadline"])
    if at > deadline:
        return _stopped(opportunity, opportunity["deadline_reason"], deadline)
    direction = Decimal(1 if opportunity["direction"] == "CE" else -1)
    move = (price - Decimal(opportunity["reference_price"])) * direction
    result = {
        **opportunity,
        "steps": [
            *opportunity["steps"],
            {"at": at.astimezone(UTC).isoformat(), "price": str(price), "move": str(move)},
        ],
        "max_favorable": str(max(Decimal(opportunity["max_favorable"]), move)),
        "max_adverse": str(max(Decimal(opportunity["max_adverse"]), -move)),
        "last_observed_at": at.astimezone(UTC).isoformat(),
    }
    if -move >= Decimal(opportunity["adverse_threshold"]):
        return _stopped(result, "THRESHOLD_ADVERSE", at)
    if move >= Decimal(opportunity["favorable_threshold"]):
        return _stopped(result, "THRESHOLD_FAVORABLE", at)
    if at >= deadline:
        return _stopped(result, opportunity["deadline_reason"], deadline)
    return result


def expire_opportunity(opportunity, now):
    if opportunity["status"] != "OBSERVING":
        return opportunity
    deadline = datetime.fromisoformat(opportunity["deadline"])
    if now >= deadline:
        return _stopped(opportunity, opportunity["deadline_reason"], deadline)
    return opportunity


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
