"""Deterministic, evidence-gated options research. No store or order transport.

Frames freeze the information available to an assessment. Quote events advance
the execution clock. Recorded decisions are explanations, never signal authority.
Financial output is withheld for any unobserved protection interval or unresolved
operation. All three variants consume identical availability-ordered evidence.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from json import dumps
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, model_validator

from .analytics import performance
from .config import StrategyConfig
from .contract_resolver import Resolver, current_moneyness
from .market_data import aggregate
from .models import PCR, Candle, Instrument, Model, Quote
from .paper_executor import _charges
from .protection import (
    early_booking_exit,
    initial_protection,
    mandatory_exit_reason,
    momentum_weakening,
    observe_bid,
)
from .risk_manager import AccountRisk, entry_reasons, plan_entry
from .signal_engine import Rules

IST = ZoneInfo("Asia/Kolkata")
ENGINE = "causal-options-execution-v1"
D = Decimal
RESEARCH_FIELDS = {
    "adx_min",
    "adx_period",
    "atr_period",
    "atr_multiplier",
    "macd_fast",
    "macd_slow",
    "macd_signal",
    "crossover_freshness",
    "macd_zero_required",
    "di_confirmation",
    "vwap_basis",
    "vwap_max_bps",
    "pcr_bull",
    "pcr_bear",
    "previous_candle_break",
}


def research_configuration(baseline, experimental):
    baseline = StrategyConfig.model_validate(baseline)
    experimental = StrategyConfig.model_validate(experimental)
    if any(
        getattr(baseline, field) != getattr(experimental, field)
        for field in type(baseline).model_fields
        if field not in RESEARCH_FIELDS
    ):
        raise ValueError("Research overrides cannot change risk, cost or execution policy")
    return experimental


class RecordedExecution(Model):
    mode: Literal["PAPER"]
    event: Literal["ENTRY_FILL", "EXIT_FILL", "PROTECTION"]
    token: str = Field(min_length=1)
    entry_order_id: str = Field(min_length=1)
    order_id: str | None = Field(default=None, min_length=1, max_length=64)
    quantity: int = Field(gt=0)
    configuration_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    price: Decimal | None = Field(default=None, gt=0)
    fees: Decimal | None = Field(default=None, ge=0)
    stop_price: Decimal | None = Field(default=None, gt=0)
    profit_floor_stop: Decimal | None = Field(default=None, gt=0)
    profit_lock_active: bool | None = None
    reason: str | None = Field(default=None, max_length=64)
    selector_policy: str | None = Field(default=None, max_length=100)
    quote: Quote | None = None

    @model_validator(mode="after")
    def complete(self):
        if self.event.endswith("FILL") and (self.price is None or self.fees is None):
            raise ValueError("Actual recorded fill and fees required")
        if self.event == "PROTECTION" and self.stop_price is None:
            raise ValueError("Recorded protective stop required")
        if self.quote is not None and self.quote.token != self.token:
            raise ValueError("Execution quote must identify the recorded contract")
        return self


def instant(value):
    at = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(at, datetime) or at.utcoffset() is None:
        raise ValueError("Aware evidence timestamp required")
    return at.astimezone(UTC)


def identity(value):
    return sha256(
        dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def event_identity(events):
    """Length-framed hashes avoid materializing a multi-recording JSON string."""
    digest = sha256()
    for event in events:
        encoded = dumps(event, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


class MarketFrame(Model):
    analysis_instrument: Instrument
    minute_bars: list[Candle] = Field(max_length=10000)
    pcr: PCR | None
    pcr_available_at: datetime | None
    spot: Quote | None
    spot_instrument: dict | None
    instruments: list[Instrument] = Field(max_length=1000)
    quotes: list[Quote] = Field(max_length=1000)
    sessions: list[dict] = Field(max_length=370)
    calendars: list[dict] = Field(max_length=3)
    decision: dict
    configuration_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    selector_policy: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def valid(self):
        if self.analysis_instrument.kind != "FUT":
            raise ValueError("Recorded analysis must identify a NIFTY future")
        if self.spot is not None and (
            not self.spot_instrument
            or self.spot.token != self.spot_instrument.get("token")
            or self.spot_instrument.get("symbol") != "NIFTY"
            or self.spot_instrument.get("exchange") != "NSE_INDEX"
        ):
            raise ValueError("Identified native NIFTY spot required")
        if any(
            b.token != self.analysis_instrument.token or b.timeframe != 1 or not b.complete
            for b in self.minute_bars
        ):
            raise ValueError("Completed same-future minute history required")
        if any(
            a.end > b.start for a, b in zip(self.minute_bars, self.minute_bars[1:], strict=False)
        ):
            raise ValueError("Recorded candles overlap or are out of order")
        if (
            len({i.token for i in self.instruments}) != len(self.instruments)
            or len({q.token for q in self.quotes}) != len(self.quotes)
            or any(i.kind not in ("CE", "PE") for i in self.instruments)
            or not {q.token for q in self.quotes} <= {i.token for i in self.instruments}
        ):
            raise ValueError("Ambiguous recorded candidate universe")
        if self.pcr_available_at is not None:
            object.__setattr__(self, "pcr_available_at", instant(self.pcr_available_at))
        return self


def validate_frame(payload, available):
    frame = MarketFrame.model_validate(payload)
    available = instant(available)

    def check_private(value, depth=0):
        if depth > 20:
            raise ValueError("Research evidence nesting exceeds bounds")
        if isinstance(value, dict):
            if {str(k).lower() for k in value} & {
                "api_key",
                "access_token",
                "auth_token",
                "bot_token",
                "password",
                "secret",
                "authorization",
            }:
                raise ValueError("Credentials are not research evidence")
            for child in value.values():
                check_private(child, depth + 1)
        elif isinstance(value, list):
            for child in value:
                check_private(child, depth + 1)

    check_private(payload)
    from re import fullmatch

    for calendar in frame.calendars:
        if (
            calendar.get("status") != "APPROVED"
            or calendar.get("segment") != "NFO"
            or type(calendar.get("year")) is not int
            or fullmatch(r"[a-f0-9]{64}", calendar.get("sha256", "")) is None
            or not calendar.get("approved_at")
            or instant(calendar["approved_at"]) > available
        ):
            raise ValueError("Point-in-time approved NFO calendar required")
        entries = calendar.get("entries")
        if not isinstance(entries, list) or any(
            not isinstance(e, dict)
            or not isinstance(e.get("date"), str)
            or date.fromisoformat(e["date"]).year != calendar["year"]
            for e in entries
        ):
            raise ValueError("Dated approved calendar entries required")
    day = available.astimezone(IST).date()
    if any(
        i.master_date != day
        or not i.tradable
        or i.expiry < day
        or (i.delta_time is not None and i.delta_time > available)
        for i in frame.instruments
    ):
        raise ValueError("Stale, expired or future candidate metadata")
    if any(b.end > available for b in frame.minute_bars):
        raise ValueError("Future candle in assessment frame")
    for quote in [*frame.quotes, *([frame.spot] if frame.spot else [])]:
        if not quote.source_time <= quote.received_time <= available:
            raise ValueError("Quote not available at assessment time")
    if frame.pcr is not None and (
        frame.pcr_available_at is None
        or not frame.pcr.source_time <= frame.pcr_available_at <= available
    ):
        raise ValueError("PCR availability evidence required")
    if (
        frame.analysis_instrument.master_date != day
        or not frame.analysis_instrument.tradable
        or frame.analysis_instrument.expiry < day
    ):
        raise ValueError("Future master must be point-in-time")
    for session in frame.sessions:
        if set(session) != {"date", "status", "start", "end", "calendar_sha256"}:
            raise ValueError("Invalid session evidence")
        if session["status"] == "TRADING":
            start, end = instant(session["start"]), instant(session["end"])
            if (
                start >= end
                or start.astimezone(IST).date().isoformat() != session["date"]
                or end.astimezone(IST).date().isoformat() != session["date"]
            ):
                raise ValueError("Invalid recorded session window")
    if len({s["date"] for s in frame.sessions}) != len(frame.sessions):
        raise ValueError("Duplicate session evidence")
    return frame.model_dump(mode="json")


def session_window(frame, day):
    row = next((s for s in frame.sessions if s["date"] == day.isoformat()), None)
    calendar = next(
        (
            c
            for c in frame.calendars
            if c.get("year") == day.year
            and c.get("status") == "APPROVED"
            and c.get("segment") == "NFO"
        ),
        None,
    )
    if not row or not calendar or row["calendar_sha256"] != calendar.get("sha256"):
        return None
    if (
        row["status"] != "TRADING"
        or day.weekday() >= 5
        or day.isoformat() in {e["date"] for e in calendar.get("entries", [])}
    ):
        return None
    return instant(row["start"]), instant(row["end"])


def decision_at(frame, now, config):
    entries, higher = [], []
    for day in sorted({b.start.astimezone(IST).date() for b in frame.minute_bars}):
        window = session_window(frame, day)
        if window:
            bars = [b for b in frame.minute_bars if b.start.astimezone(IST).date() == day]
            entries.extend(aggregate(bars, 5, now, window[0]))
            higher.extend(aggregate(bars, 15, now, window[0]))
    pcr = frame.pcr if frame.pcr_available_at and frame.pcr_available_at <= now else None
    decision = Rules().evaluate(
        entries, higher, pcr, now, config, config.version_id, frame.analysis_instrument.token
    )
    today = [
        b for b in frame.minute_bars if b.start.astimezone(IST).date() == now.astimezone(IST).date()
    ]
    window = session_window(frame, now.astimezone(IST).date())
    if not window or not today or today[0].start != window[0]:
        decision["eligible"] = False
        decision["reasons"].append("SESSION_VWAP_INCOMPLETE")
    return decision


def _run(events, config, profit_lock, start, end):
    equity = config.virtual_capital
    day_equity, daily_entries, day = equity, 0, None
    month, month_net, month_locked = None, D(0), False
    cooldown_after = None
    frame = None
    frame_received_at = None
    quotes, journal, refusals, coverage = {}, [], [], set()
    held = pending = None
    last_observed = None
    decisions = 0
    seen_decisions = set()
    consumed = set()

    def reject(code, at):
        if len(refusals) < 1000:
            refusals.append({"at": at.isoformat(), "code": code})

    for item in events:
        now = instant(item["available_at"])
        if now >= end:
            break
        if item["kind"] == "QUOTE":
            quote = Quote.model_validate(item["payload"])
            previous = quotes.get(quote.token)
            if previous is None or quote.source_time > previous.source_time:
                quotes[quote.token] = quote
        elif item["kind"] == "FRAME":
            frame = MarketFrame.model_validate(validate_frame(item["payload"], now))
            frame_received_at = now
            for quote in frame.quotes:
                previous = quotes.get(quote.token)
                if previous is None or quote.source_time > previous.source_time:
                    quotes[quote.token] = quote
        else:
            continue
        if now < start:
            continue
        if frame is None:
            coverage.add("FUTURES_PCR_SPOT_UNIVERSE_FRAME_MISSING")
            continue
        current_day = now.astimezone(IST).date()
        if current_day != day:
            day, daily_entries, day_equity = current_day, 0, equity
        key = day.strftime("%Y-%m")
        if key != month:
            month, month_net, month_locked = key, D(0), False
        window = session_window(frame, day)
        if window is None:
            coverage.add("APPROVED_SESSION_EVIDENCE_MISSING")
            continue
        if held:
            boundary = now.replace(minute=(now.minute // 5) * 5, second=0, microsecond=0)
            if (
                boundary > held["opened"]
                and now > boundary + timedelta(seconds=30)
                and frame_received_at < boundary
            ):
                coverage.add("FUTURES_PROTECTION_FRAME_MISSING")
            quote = quotes.get(held["instrument"].token)
            if (
                quote is None
                or not quote.bid
                or quote.bid_size <= 0
                or not quote.source_time <= quote.received_time <= now
                or not 0 <= (now - quote.source_time).total_seconds() <= config.quote_max_age
            ):
                coverage.add("PROTECTION_QUOTE_GAP")
                continue
            if quote.bid % held["instrument"].tick_size:
                coverage.add("INVALID_PROTECTION_TICK")
                continue
            if last_observed and (now - last_observed).total_seconds() > config.quote_max_age:
                coverage.add("PROTECTION_QUOTE_GAP")
            if quote.source_time >= held["opened"] and (
                last_observed is None or quote.source_time > last_observed
            ):
                last_observed = quote.source_time
                held["protection"] = observe_bid(
                    held["protection"],
                    held["price"],
                    quote.bid,
                    held["instrument"].tick_size,
                    config,
                    quantity=held["quantity"] if profit_lock else None,
                    entry_fees=held["fees"],
                    charges=_charges,
                    bid_size=quote.bid_size,
                    source_time=quote.source_time,
                )
            technical = False
            discretionary = None
            if item["kind"] == "FRAME":
                decision = decision_at(frame, now, config)
                snapshot = decision.get("snapshot") or {}
                direction = 1 if held["instrument"].kind == "CE" else -1
                st = snapshot.get("supertrend") or {}
                fresh = any(
                    c["rule"] == "R-FRESH" and c["state"] == "PASS" for c in decision["checks"]
                )
                if not fresh or not st:
                    coverage.add("FUTURES_PROTECTION_FRAME_MISSING")
                same = frame.analysis_instrument.token == held["analysis_token"]
                if not same:
                    coverage.add("FUTURES_PROTECTION_INSTRUMENT_CHANGED")
                entry_st = held["snapshot"].get("supertrend") or {}
                technical = bool(
                    fresh
                    and same
                    and (
                        st.get("direction") not in (None, direction)
                        or (
                            entry_st.get("atr")
                            and (
                                held["snapshot"]["price"]
                                - snapshot.get("price", held["snapshot"]["price"])
                            )
                            * direction
                            >= entry_st["atr"] * config.atr_exit_multiple
                        )
                    )
                )
                if fresh and same and held.get("last_snapshot"):
                    discretionary = early_booking_exit(
                        held["protection"],
                        held["price"],
                        quote.bid,
                        held["instrument"].tick_size,
                        config,
                        quantity=held["quantity"],
                        entry_fees=held["fees"],
                        charges=_charges,
                        momentum_weak=momentum_weakening(
                            held["last_snapshot"], snapshot, direction
                        ),
                    )
                held["last_snapshot"] = snapshot
            reason = held["protection"].get("exit_reason") or mandatory_exit_reason(
                held["opened"],
                now,
                config,
                window,
                technical=technical,
                discretionary=discretionary,
            )
            if reason and not held.get("exit_at"):
                held["exit_at"] = now + timedelta(milliseconds=config.latency_ms)
                held["reason"] = reason
            depth_key = (quote.token, quote.source_time, "SELL")
            if (
                held.get("exit_at")
                and now >= held["exit_at"]
                and quote.bid_size >= held["quantity"]
                and depth_key not in consumed
            ):
                price = quote.bid - held["instrument"].tick_size * config.slippage_ticks
                if price <= 0 or not window[0] <= now < window[1]:
                    coverage.add("EXIT_EXECUTION_UNAVAILABLE")
                    continue
                consumed.add(depth_key)
                fees = _charges("SELL", price, held["quantity"], config)
                gross = (price - held["price"]) * held["quantity"]
                net = gross - fees - held["fees"]
                equity += net
                month_net += net
                month_locked = (
                    month_locked
                    or month_net <= -config.monthly_loss_limit
                    or (
                        config.monthly_profit_target is not None
                        and month_net >= config.monthly_profit_target
                    )
                )
                if net < 0:
                    following = sorted(
                        s["date"]
                        for s in frame.sessions
                        if s["date"] > day.isoformat()
                        and session_window(frame, datetime.fromisoformat(s["date"]).date())
                    )
                    cooldown_after = following[0] if following else "UNRESOLVED"
                journal.append(
                    {
                        "trade_id": str(len(journal) + 1),
                        "fill_id": str(len(journal) + 1),
                        "instrument": held["instrument"].model_dump(mode="json"),
                        "quantity": held["quantity"],
                        "opened": held["opened"].isoformat(),
                        "closed": now.isoformat(),
                        "gross": str(gross),
                        "charges": str(fees + held["fees"]),
                        "net": str(net),
                        "planned_risk": str(held["risk"]),
                        "exit_reason": held["reason"],
                        "entry_price": str(held["price"]),
                        "exit_price": str(price),
                        "protection": held["protection"],
                        "mode": "RESEARCH",
                    }
                )
                held, last_observed = None, None
            continue
        if pending:
            if now >= pending["expires"]:
                reject("ENTRY_EXPIRED", now)
                pending = None
                continue
            if now < pending["eligible"]:
                continue
            instrument = pending["plan"].instrument
            current_instrument = next(
                (i for i in frame.instruments if i.token == instrument.token), None
            )
            if current_instrument != instrument:
                reject("FILL_METADATA_CHANGED", now)
                pending = None
                continue
            if not window[0] <= now < window[1] or instrument.master_date != day:
                reject("SESSION_OR_MASTER_CHANGED", now)
                pending = None
                continue
            quote = quotes.get(instrument.token)
            if quote is not None and (
                (quote.ask is not None and quote.ask % instrument.tick_size)
                or (quote.bid is not None and quote.bid % instrument.tick_size)
            ):
                coverage.add("INVALID_EXECUTION_TICK")
                pending = None
                continue
            spot = frame.spot
            if (
                spot is None
                or spot.ltp is None
                or not 0 <= (now - spot.source_time).total_seconds() <= config.quote_max_age
                # The same listed-ATM rule PAPER applies at fill, against the
                # recorded master of this frame.
                or current_moneyness(instrument, spot.ltp, frame.instruments)[0] in (None, "OTM")
            ):
                reject("CURRENT_SPOT_UNAVAILABLE_OR_OTM", now)
                pending = None
                continue
            current = plan_entry(
                AccountRisk(equity, equity, day_equity),
                [(instrument, quote)],
                config,
                pending["decision"]["confidence"]["score"],
                _charges,
                now=now,
            )
            plan = pending["plan"]
            if (
                current.instrument is None
                or current.quantity != plan.quantity
                or current.planned_loss > plan.planned_loss
                or current.cash_required > plan.cash_required
            ):
                reject("FILL_REVALIDATION_REFUSED", now)
                pending = None
                continue
            depth_key = (instrument.token, quote.source_time, "BUY")
            if depth_key in consumed:
                continue
            consumed.add(depth_key)
            held = {
                "instrument": instrument,
                "quantity": current.quantity,
                "price": current.entry_price,
                "fees": _charges("BUY", current.entry_price, current.quantity, config),
                "opened": now,
                "risk": current.planned_loss,
                "protection": initial_protection(
                    current.entry_price,
                    instrument.tick_size,
                    config,
                    pending["decision"]["confidence"],
                ),
                "analysis_token": frame.analysis_instrument.token,
                "snapshot": pending["decision"]["snapshot"],
            }
            pending = None
            daily_entries += 1
            last_observed = now
            continue
        if item["kind"] != "FRAME":
            continue
        decision = decision_at(frame, now, config)
        from .selection_scoring import POLICY

        if frame.selector_policy != POLICY:
            coverage.add("SELECTOR_POLICY_UNSUPPORTED")
        if any(
            c["state"] == "UNAVAILABLE"
            or (c["rule"] in ("R-WARMUP", "R-FRESH") and c["state"] != "PASS")
            for c in decision["checks"]
        ):
            coverage.add("INCOMPLETE_SIGNAL_INPUTS")
        if decision["decision_id"] in seen_decisions:
            continue
        seen_decisions.add(decision["decision_id"])
        decisions += 1
        if frame.pcr is None:
            coverage.add("HISTORICAL_PCR_MISSING")
        if not decision["eligible"]:
            for code in decision["reasons"]:
                reject(code, now)
            continue
        if cooldown_after and (cooldown_after == "UNRESOLVED" or day.isoformat() <= cooldown_after):
            reject("COOLDOWN_ACTIVE", now)
            continue
        if month_locked:
            reject("MONTHLY_RISK_LOCK", now)
            continue
        if equity <= 0 or day_equity <= 0:
            reject("CAPITAL_DEPLETED", now)
            continue
        spot = frame.spot
        if (
            spot is None
            or spot.ltp is None
            or not 0 <= (now - spot.source_time).total_seconds() <= config.quote_max_age
        ):
            coverage.add("SPOT_MISSING_OR_STALE")
            continue
        try:
            candidates = Resolver().candidates(
                frame.instruments, quotes, spot.ltp, decision["side"], now, config
            )
        except ValueError:
            coverage.add("OPTION_UNIVERSE_OR_DEPTH_UNAVAILABLE")
            continue
        account = AccountRisk(
            equity,
            equity,
            day_equity,
            daily_entries=daily_entries,
            reconciled=True,
            entries_enabled=True,
        )
        blocks = entry_reasons(
            account,
            candidates[0],
            quotes.get(candidates[0].token),
            now,
            config,
            session_open=window[0] <= now < window[1],
            data_healthy=True,
        )
        if blocks:
            for code in blocks:
                reject(code, now)
            continue
        plan = plan_entry(
            account,
            [(i, quotes.get(i.token)) for i in candidates],
            config,
            decision["confidence"]["score"],
            _charges,
            now=now,
        )
        if plan.instrument is None:
            for _, _, code in plan.rejections:
                reject(code, now)
            continue
        pending = {
            "plan": plan,
            "decision": decision,
            "eligible": now + timedelta(milliseconds=config.latency_ms),
            "expires": min(
                now + timedelta(seconds=config.order_ttl_seconds),
                datetime.combine(day, config.entry_before, IST),
            ),
        }
    if held or pending:
        coverage.add("UNRESOLVED_OPERATION_AT_SPLIT_END")
    if decisions == 0:
        coverage.add("NO_SIGNAL_FRAMES_IN_SPLIT")
    return {
        "status": "REFUSED_MISSING_EVIDENCE" if coverage else "MODELED_EXECUTION",
        "performance": None if coverage else performance(journal, config.virtual_capital),
        "trades": [] if coverage else journal,
        "signal_decisions": decisions,
        "missing": sorted(coverage),
        "rejections": refusals,
    }


def compare(events, baseline, experimental, splits):
    """No optimization or active-setting writes. Every split starts at the same seed."""
    if len(events) > 200000 or [s["kind"] for s in splits] != ["TRAIN", "VALIDATION", "TEST"]:
        raise ValueError("Bounded three-way evidence required")
    baseline = StrategyConfig.model_validate(baseline)
    experimental = research_configuration(baseline, experimental)
    known = []
    previous = None
    for row in events:
        now = instant(row["available_at"])
        if previous and now < previous:
            raise ValueError("Out-of-order replay availability")
        if instant(row["source_time"]) > now:
            raise ValueError("Future source observation")
        if row["kind"] == "FRAME":
            frame = validate_frame(row["payload"], now)
            if frame["configuration_id"] != baseline.version_id:
                raise ValueError("FRAME_CONFIGURATION_ID_MISMATCH")
        elif row["kind"] == "QUOTE":
            quote = Quote.model_validate(row["payload"])
            if not quote.source_time <= quote.received_time <= now:
                raise ValueError("Unavailable replay quote")
        elif row["kind"] == "LEDGER":
            execution = RecordedExecution.model_validate(row["payload"])
            if execution.quote is not None and not (
                execution.quote.source_time
                <= execution.quote.received_time
                <= instant(row["source_time"])
            ):
                raise ValueError("Future execution quote")
        else:
            raise ValueError("Unsupported execution evidence")
        known.append(row)  # Validated immutable input is only read by the replay.
        previous = now
    boundaries = [(instant(s["start"]), instant(s["end"])) for s in splits]
    if any(a >= b for a, b in boundaries) or any(
        a[1] != b[0] for a, b in zip(boundaries, boundaries[1:], strict=False)
    ):
        raise ValueError("Ordered disjoint TRAIN/VALIDATION/TEST splits required")
    if any(
        baseline.entry_after < end.astimezone(IST).time() < baseline.exit_by
        for _, end in boundaries[:-1]
    ):
        raise ValueError("Split boundaries cannot divide an eligible trading session")
    variants = []
    for name, config, lock in (
        ("A_BASELINE", baseline, False),
        ("B_CURRENT", baseline, True),
        ("C_EXPERIMENTAL", experimental, True),
    ):
        results = [
            {"kind": split["kind"], **_run(known, config, lock, start, end)}
            for split, (start, end) in zip(splits, boundaries, strict=True)
        ]
        variants.append(
            {
                "name": name,
                "configuration_id": config.version_id,
                "profit_lock": lock,
                "splits": results,
                "status": "MODELED_EXECUTION"
                if all(r["performance"] is not None for r in results)
                else "REFUSED_MISSING_EVIDENCE",
            }
        )
    result = {
        "engine_version": ENGINE,
        "mode": "RESEARCH",
        "dataset_sha256": event_identity(known),
        "dataset_hash_policy": "length-framed-record-sha256-v1",
        "variants": variants,
        "active_settings_changed": False,
        "assumptions": [
            "Full-quantity displayed-depth fills after configured latency; no partial fills.",
            "Quote freshness gaps while exposed invalidate financial results.",
            "Each split resets capital; preceding evidence supplies warm-up only.",
            "Modeled fills are not certified achievable historical executions.",
        ],
    }
    return {**result, "sha256": identity(result)}
