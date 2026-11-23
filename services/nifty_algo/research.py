"""Causal candle studies using native history inputs and the production decision rules.

Research only: nothing here admits, fills or transmits an order.
"""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from json import dumps
from re import fullmatch
from zoneinfo import ZoneInfo

from .config import StrategyConfig
from .market_data import aggregate
from .models import PCR, Instrument, Quote
from .signal_engine import Rules

IST = ZoneInfo("Asia/Kolkata")
OBSERVATION_WINDOW = timedelta(minutes=45)
# Testable hypotheses: terminal moves of the analysis future, in entry-candle ATRs.
FAVORABLE_ATR_MULTIPLE = Decimal("1")
ADVERSE_ATR_MULTIPLE = Decimal("1")


def recording_scope(instruments, broker, now):
    """Canonical bounded metadata snapshot; callers must obtain native feed proof."""
    if (
        not isinstance(now, datetime)
        or now.tzinfo is None
        or not isinstance(broker, str)
        or fullmatch(r"[a-z0-9_]{1,32}", broker) is None
        or not isinstance(instruments, list)
        or not 1 <= len(instruments) <= 1000
    ):
        raise ValueError("Invalid native recording scope")
    today = now.astimezone(IST).date()
    rows, tokens, symbols = [], set(), set()
    for item in instruments:
        if not isinstance(item, Instrument):
            raise ValueError("Native recording requires validated instrument metadata")
        item = Instrument.model_validate(item.model_dump())
        if (
            item.kind not in ("CE", "PE")
            or not item.tradable
            or item.master_date != today
            or item.expiry < today
            or len(item.token) > 32
            or len(item.symbol) > 64
            or item.token in tokens
            or item.symbol in symbols
        ):
            raise ValueError("Invalid or ambiguous native recording identity")
        tokens.add(item.token)
        symbols.add(item.symbol)
        rows.append(item.model_dump(mode="json", exclude={"delta", "delta_time"}))
    scope = {
        "schema_version": 1,
        "broker": broker,
        "frozen_at": now.astimezone(UTC).isoformat(),
        "instruments": sorted(rows, key=lambda row: (row["exchange"], row["symbol"], row["token"])),
    }
    if len(dumps(scope, sort_keys=True, separators=(",", ":")).encode()) > 524288:
        raise ValueError("Native recording scope exceeds 512 KiB")
    return scope


def recording_batch(rows, now):
    """Validate bounded quote evidence in availability order, never source-time order.

    Provenance labels and hashes describe supplied evidence; neither authenticates
    a provider nor establishes historical execution eligibility.
    """
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("Timezone-aware recording time required")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
        raise ValueError("Recording batch requires 1 to 100 observations")
    try:
        encoded = dumps(rows, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()
    except (TypeError, ValueError, RecursionError):
        raise ValueError("Invalid recording batch") from None
    if len(encoded) > 262144:
        raise ValueError("Recording batch exceeds 256 KiB")
    fields = {"kind", "source_time", "available_at", "source", "payload"}
    result, previous, seen = [], None, set()
    for row in rows:
        try:
            if not isinstance(row, dict) or set(row) != fields:
                raise ValueError
            if row["kind"] != "QUOTE" or row["source"] not in ("NATIVE_FEED", "IMPORT"):
                raise ValueError
            source = datetime.fromisoformat(row["source_time"])
            available = datetime.fromisoformat(row["available_at"])
            quote = Quote.model_validate(row["payload"])
            if (
                source.tzinfo is None
                or available.tzinfo is None
                or source != quote.source_time
                or not source <= quote.received_time <= available <= now
                or (previous is not None and available < previous)
                or not quote.token
                or not quote.provider
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            # Do not echo validation errors containing untrusted payload values.
            raise ValueError("Invalid point-in-time quote evidence") from None
        normalized = {
            "kind": "QUOTE",
            "source_time": source.astimezone(UTC).isoformat(),
            "available_at": available.astimezone(UTC).isoformat(),
            "source": row["source"],
            "payload": quote.model_dump(mode="json"),
        }
        content = dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
        digest = sha256(content).hexdigest()
        if digest in seen:
            raise ValueError("Duplicate point-in-time quote evidence")
        seen.add(digest)
        result.append({**normalized, "sha256": digest})
        previous = available
    return result


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


def signal_study(bars, config, start, end, *, session_opens, pcr_observations=()):
    """Session anchors are dated native calendar observations keyed by local date.

    The interval is [start, end). Without historical chain observations PCR is
    unavailable, so strict entry eligibility stays false in this candle study.
    """
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError("Ordered timezone-aware study interval required")
    ordered = list(bars)
    if len(ordered) > 10000 or len(pcr_observations) > 10000:
        raise ValueError("Replay input exceeds 10000 observations")
    if any(left.start >= right.start for left, right in zip(ordered, ordered[1:], strict=False)):
        raise ValueError("Out-of-order or duplicate candle history")
    pcr_history, previous_available = [], None
    for item in pcr_observations:
        if not isinstance(item, dict) or set(item) != {"pcr", "available_at"}:
            raise ValueError("PCR observations require availability evidence")
        pcr = item["pcr"]
        available = item["available_at"]
        if (
            not isinstance(pcr, PCR)
            or not isinstance(available, datetime)
            or available.tzinfo is None
            or pcr.source_time > available
            or (previous_available is not None and available < previous_available)
        ):
            raise ValueError("Invalid chronological PCR evidence")
        pcr_history.append((available, pcr))
        previous_available = available
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
    decisions, pcr_covered = [], 0
    for bar in entries:
        if start <= bar.end < end:
            known_pcr = [
                pcr
                for available, pcr in pcr_history
                if available <= bar.end and pcr.source_time <= bar.end
            ]
            current_pcr = max(known_pcr, key=lambda pcr: pcr.source_time, default=None)
            valid_pcr = (
                current_pcr is not None
                and current_pcr.verified
                and current_pcr.coverage == 1
                and current_pcr.kind == config.pcr_kind
                and 0 <= (bar.end - current_pcr.source_time).total_seconds() <= config.pcr_max_age
            )
            pcr_covered += int(valid_pcr)
            decisions.append(
                Rules().evaluate(
                    [known for known in entries if known.end <= bar.end],
                    [known for known in higher if known.end <= bar.end],
                    current_pcr,
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
        "indicator_coverage": {
            "pcr_available": pcr_covered,
            "total_decisions": len(decisions),
            "complete_five_indicator_evidence": bool(decisions) and pcr_covered == len(decisions),
        },
        "limitations": [
            "Candle study has no historical option premiums or execution fills.",
            *(
                []
                if decisions and pcr_covered == len(decisions)
                else ["Historical PCR is missing or incomplete. Partial indicator research only."]
            ),
        ],
    }


def options_replay(*args, **kwargs):
    """Refuse a premium simulation until a validated historical quote model exists."""
    raise ValueError(
        "OPTION_REPLAY_UNAVAILABLE: timestamped option depth and verified metadata required"
    )


def experiment_snapshot(manifest, configuration, *, train_end, validation_end, now):
    """Freeze a research definition; no data coverage or execution claim follows."""
    if any(
        not isinstance(at, datetime) or at.tzinfo is None for at in (train_end, validation_end, now)
    ):
        raise ValueError("Timezone-aware experiment boundaries required")
    config = StrategyConfig.model_validate(configuration)
    if len(config.model_dump_json().encode()) > 65536:
        raise ValueError("Experiment configuration exceeds bounds")
    start = datetime.fromisoformat(manifest["starts_at"])
    sealed_at = datetime.fromisoformat(manifest["sealed_at"])
    end = min(datetime.fromisoformat(manifest["ends_at"]), sealed_at)
    if not start < train_end < validation_end < end or now < sealed_at:
        raise ValueError("Ordered experiment splits within sealed evidence required")
    boundaries = (start, train_end, validation_end, end)
    snapshot = {
        "schema_version": 1,
        "engine_version": "quote-evidence-cursor-v1",
        "dataset": deepcopy(manifest),
        "configuration": config.model_dump(mode="json"),
        "configuration_id": config.version_id,
        "interval": "[start,end)",
        "splits": [
            {
                "kind": kind,
                "start": left.astimezone(UTC).isoformat(),
                "end": right.astimezone(UTC).isoformat(),
            }
            for kind, left, right in zip(
                ("TRAIN", "VALIDATION", "TEST"), boundaries, boundaries[1:], strict=False
            )
        ],
    }
    if len(dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()) > 1048576:
        raise ValueError("Experiment snapshot exceeds bounds")
    return snapshot


class _RecordingCursor:
    """Detached, bounded evidence cursor, not an execution simulator."""

    def __init__(self, manifest, observations):
        self._manifest = deepcopy(manifest)
        self._observations = deepcopy(observations)
        self._index = 0
        self._clock = None

    @property
    def manifest(self):
        return deepcopy(self._manifest)

    def advance(self, as_of, *, limit=100):
        if (
            not isinstance(as_of, datetime)
            or as_of.tzinfo is None
            or type(limit) is not int
            or not 1 <= limit <= 100
        ):
            raise ValueError("Timezone-aware clock and bounded replay page required")
        as_of = as_of.astimezone(UTC)
        if self._clock is not None and as_of < self._clock:
            raise ValueError("Replay clock cannot move backward")
        end = self._index
        while end < min(len(self._observations), self._index + limit):
            if datetime.fromisoformat(self._observations[end]["available_at"]) > as_of:
                break
            end += 1
        items = deepcopy(self._observations[self._index : end])
        self._index, self._clock = end, as_of
        return {
            "mode": "QUOTE_EVIDENCE_ONLY",
            "execution_eligible": False,
            "as_of": as_of.isoformat(),
            "items": items,
            "next_after": end,
            "limitations": ["QUOTE_EVIDENCE_ONLY", "PROVENANCE_NOT_AUTHENTICATED"],
        }


def recording_cursor(store, user_id, recording_id, *, expected_count, expected_sha256):
    """Verify sealed owner-scoped evidence before exposing any replay step.

    The pinned digest detects changed content, not provider authenticity. No
    store or connection is retained by the returned cursor.
    """
    if (
        type(expected_count) is not int
        or not 0 <= expected_count <= 10000
        or not isinstance(expected_sha256, str)
        or fullmatch(r"[a-f0-9]{64}", expected_sha256) is None
    ):
        raise ValueError("Invalid replay identity")
    page = store.recording_page(user_id, recording_id, limit=100)
    if page is None:
        raise ValueError("Recording not found")
    manifest = deepcopy(page["manifest"])
    if manifest["status"] != "SEALED" or not manifest.get("sealed_at"):
        raise ValueError("Replay requires a sealed recording")
    if manifest["count"] != expected_count or manifest["content_sha256"] != expected_sha256:
        raise ValueError("Recording identity changed")
    configuration = StrategyConfig.model_validate(manifest["configuration"]).model_dump(mode="json")
    context = {
        "starts_at": manifest["starts_at"],
        "ends_at": manifest["ends_at"],
        "configuration": configuration,
        "schema_version": 1,
    }
    if manifest.get("capture") is not None:
        context["capture"] = "NATIVE_FEED"
    digest = sha256(dumps(context, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    capture = manifest.get("capture")
    if capture is not None and capture.get("scope") is not None:
        scope_digest = sha256(
            dumps(capture["scope"], sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if capture.get("scope_sha256") != scope_digest:
            raise ValueError("Recording scope integrity failed")
        digest = sha256((digest + scope_digest).encode("ascii")).hexdigest()
    sealed_at = datetime.fromisoformat(manifest["sealed_at"])
    start = datetime.fromisoformat(manifest["starts_at"])
    end = datetime.fromisoformat(manifest["ends_at"])
    observations, size, previous = [], 0, start
    fields = {"kind", "source_time", "available_at", "source", "payload"}
    while True:
        if (
            page is None
            or page["manifest"] != manifest
            or not isinstance(page["items"], list)
            or len(page["items"]) > 100
        ):
            raise ValueError("Recording changed during replay loading")
        for item in page["items"]:
            if (
                set(item) != fields | {"sequence", "sha256"}
                or type(item["sequence"]) is not int
                or item["sequence"] != len(observations) + 1
                or len(observations) >= expected_count
            ):
                raise ValueError("Invalid recording sequence")
            normalized = recording_batch([{key: item[key] for key in fields}], sealed_at)[0]
            available = datetime.fromisoformat(normalized["available_at"])
            if (
                normalized["sha256"] != item["sha256"]
                or not start <= datetime.fromisoformat(normalized["source_time"])
                or not previous <= available <= end
            ):
                raise ValueError("Recording evidence integrity failed")
            size += len(dumps(normalized, sort_keys=True, separators=(",", ":")).encode())
            if size > 16777216:
                raise ValueError("Replay evidence exceeds recording bounds")
            digest = sha256((digest + normalized["sha256"]).encode("ascii")).hexdigest()
            observations.append({"sequence": item["sequence"], **normalized})
            previous = available
        if len(observations) == expected_count:
            break
        if not page["items"] or page["next_after"] != len(observations):
            raise ValueError("Incomplete recording evidence")
        page = store.recording_page(user_id, recording_id, after=len(observations), limit=100)
    if digest != expected_sha256 or size != manifest["size_bytes"]:
        raise ValueError("Recording content integrity failed")
    return _RecordingCursor(manifest, observations)


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
