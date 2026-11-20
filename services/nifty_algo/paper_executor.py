"""Feature-scoped strict paper execution.

Fills resolve only from observed bid/ask depth inside this feature's isolated
ledger — never from LTP, and never through the shared Sandbox, broker modules,
or generic order services. The generic ``submit`` boundary stays permanently
closed: orders enter only through ``admit`` after risk-manager checks and
resolve only through ``process`` against fresh market depth.
"""

from datetime import UTC, datetime, time, timedelta
from decimal import ROUND_CEILING, Decimal
from math import isfinite
from uuid import uuid4
from zoneinfo import ZoneInfo

from services.nifty_algo.models import Instrument, Quote

IST = ZoneInfo("Asia/Kolkata")


class PaperExecutionUnavailable(ValueError):
    pass


class OrderRefused(ValueError):
    """Risk or ledger checks rejected the intent before admission."""

    def __init__(self, reasons):
        self.reasons = list(reasons)
        super().__init__(", ".join(self.reasons))


def _epoch(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else None
    if isinstance(value, (int, float)):
        try:
            return (
                datetime.fromtimestamp(value / 1000 if value > 10**12 else value, UTC)
                if isfinite(value)
                else None
            )
        except (ValueError, OverflowError, OSError):
            return None
    try:
        stamp = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return stamp if stamp.tzinfo else None


def _best_level(entries, high=True):
    """(price, quantity) at the best level of a depth side."""
    best = None
    for entry in entries or []:
        try:
            if isinstance(entry, dict):
                price = Decimal(str(entry["price"]))
                size = int(entry.get("quantity", 0))
            else:
                price = Decimal(str(entry[0]))
                size = int(entry[1])
        except (KeyError, IndexError, TypeError, ValueError, ArithmeticError):
            continue
        if not price.is_finite() or price <= 0 or size <= 0:
            continue
        if best is None or (price > best[0] if high else price < best[0]):
            best = (price, size)
    return best


def _charges(side, price, quantity, config=None):
    """Configured research cost schedule; not an assertion of current tax rates."""
    from .config import StrategyConfig

    config = config or StrategyConfig()
    turnover = price * quantity
    txn = turnover * config.transaction_rate
    gst = (config.brokerage + txn) * config.gst_rate
    stt = turnover * config.stt_sell_rate if side == "SELL" else Decimal("0")
    stamp = turnover * config.stamp_buy_rate if side == "BUY" else Decimal("0")
    sebi = turnover * config.sebi_rate
    return (config.brokerage + txn + gst + stt + stamp + sebi).quantize(
        Decimal("0.0001"), rounding=ROUND_CEILING
    )


class NiftyPaperExecutor:
    mode = "PAPER_ONLY"

    def __init__(
        self,
        store=None,
        user_id=None,
        config=None,
        market_data=None,
        clock=None,
        session_reader=None,
    ):
        self.store = store
        self.user_id = user_id
        self.config = config
        self.market_data = market_data
        self.clock = clock or (lambda: datetime.now(UTC))
        self.session_reader = session_reader

    def _bound(self):
        return self.store is not None and self.user_id is not None

    def readiness(self):
        """Structural and cached runner gates; live depth is validated per fill."""
        account_ok = False
        if self._bound():
            try:
                account_ok = bool(self.store.account(self.user_id))
            except Exception:
                account_ok = False
        return [
            {
                "code": "STRICT_FILL_PROFILE",
                "ready": True,
                "detail": "Fills resolve only from observed bid/ask depth in the "
                "feature ledger. LTP fallback does not exist in this path.",
            },
            {
                "code": "ISOLATED_PAPER_ACCOUNT",
                "ready": account_ok,
                "detail": "NIFTY virtual capital isolated from shared Sandbox funds.",
            },
            {
                "code": "AUTOMATION_LOOP",
                "ready": bool(
                    self._bound() and self.store.runner_status(self.user_id).get("operational")
                ),
                "detail": "A leased native scheduler must attach and report verified data readiness.",
            },
            {
                "code": "DATA_PIPELINE",
                "ready": bool(
                    self._bound() and self.store.runner_status(self.user_id).get("entries_ready")
                ),
                "detail": (
                    self.store.runner_status(self.user_id).get("reason")
                    or "Verified five-indicator data required"
                )
                if self._bound()
                else "Runner not attached",
            },
        ]

    def submit(self, *args, **kwargs):
        raise PaperExecutionUnavailable("Paper execution prerequisites are incomplete.")

    # Admission ------------------------------------------------------------

    def admit(self, intent, now=None):
        """Validate an intent through the risk manager, then persist it once."""
        from services.nifty_algo.config import StrategyConfig
        from services.nifty_algo.risk_manager import AccountRisk, entry_reasons, plan_entry

        now = now or self.clock()
        existing = self.store.order_by_intent(self.user_id, intent["intent_id"])
        if existing is not None:
            return existing, False
        state = self.store.read(self.user_id)
        try:
            config = self.config or StrategyConfig.model_validate(state["configuration"])
        except ValueError:
            if intent.get("side") != "SELL":
                raise OrderRefused(["CONFIGURATION_INCOMPATIBLE"]) from None
            config = StrategyConfig()  # Existing protection overrides this below.
        row = self.store.account(self.user_id, now)
        positions = self.store.positions(self.user_id)
        pending = self.store.pending_orders(self.user_id)
        side = intent["side"]
        if side not in ("BUY", "SELL"):
            raise OrderRefused(["SIDE_RESTRICTED"])
        try:
            raw_candidates = intent.get("candidates") if side == "BUY" else None
            candidate_instruments = [
                Instrument.model_validate(value)
                for value in (raw_candidates or [intent["instrument"]])
            ]
            instrument = candidate_instruments[0]
        except (ValueError, TypeError, KeyError):
            raise OrderRefused(["METADATA_INVALID"]) from None
        if (
            intent["token"] != instrument.token
            or intent["symbol"] != instrument.symbol
            or instrument.kind not in ("CE", "PE")
            or instrument.exchange != "NFO"
        ):
            raise OrderRefused(["INSTRUMENT_RESTRICTED"])
        confidence = None
        held = next((row for row in positions if row["token"] == intent["token"]), None)
        if side == "SELL":
            if held is None:
                raise OrderRefused(["UNCOVERED_SELL"])
            quantity = intent.get("quantity") or held["quantity"]
            if type(quantity) is not int or quantity <= 0 or quantity > held["quantity"]:
                raise OrderRefused(["UNCOVERED_SELL"])
            if held["instrument"] != instrument.model_dump(mode="json"):
                raise OrderRefused(["POSITION_IDENTITY_MISMATCH"])
            if held.get("protection"):
                config = StrategyConfig.model_validate(held["protection"]["configuration"])
        else:
            decisions = (
                self.store.decisions(self.user_id, intent.get("decision_id"))
                if intent.get("decision_id")
                else []
            )
            decision = decisions[0] if decisions else {}
            confidence = decision.get("confidence")
            if (
                not decision.get("eligible")
                or decision.get("config_id") != config.version_id
                or decision.get("side") != instrument.kind
                or not confidence
                or confidence.get("method") != config.confidence_method
            ):
                raise OrderRefused(["QUALIFYING_CONFIDENCE_REQUIRED"])
            from .confidence import target_fraction

            try:
                target_fraction(confidence["score"], config)
                decided = _epoch(decision["timestamp"])
                if decided is None or not 0 <= (now - decided).total_seconds() <= 30:
                    raise ValueError("Decision expired")
            except (ValueError, TypeError, KeyError):
                raise OrderRefused(["CONFIDENCE_OR_DECISION_INVALID"]) from None
            risk = AccountRisk(
                equity=Decimal(row["equity"]),
                available=Decimal(row["available"]),
                starting_day_equity=Decimal(row["starting_day_equity"]),
                open_positions=len(positions),
                pending_entries=sum(1 for order in pending if order["side"] == "BUY"),
                daily_entries=row["daily_entries"],
                killed=state["killed"],
                daily_locked=state["daily_locked"],
                reconciled=row["reconciled"],
                entries_enabled=state["state"] == "RUNNING",
            )
            candidate_quotes = [
                (candidate, self._depth(candidate, now)) for candidate in candidate_instruments
            ]
            quote = candidate_quotes[0][1]
            reasons = entry_reasons(
                risk,
                instrument,
                quote,
                now,
                config,
                session_open=self._session_open(now),
                data_healthy=quote is not None,
            )
            if reasons:
                raise OrderRefused(reasons)
            sizing = plan_entry(
                risk,
                candidate_quotes,
                config,
                confidence["score"],
                _charges,
            )
            if sizing.instrument is None:
                reasons = list(dict.fromkeys(reason for _, _, reason in sizing.rejections))
                if not reasons:
                    reasons = ["POSITION_SIZE_ZERO"]
                raise OrderRefused(reasons)
            if intent.get("quantity") is not None and intent["quantity"] != sizing.quantity:
                raise OrderRefused(["POSITION_SIZE_ZERO"])
            instrument = sizing.instrument
            quote = next(
                candidate_quote
                for candidate, candidate_quote in candidate_quotes
                if candidate.token == instrument.token
            )
            quantity = sizing.quantity
        reservation = {}
        sizing_plan = None
        if side == "BUY":
            reservation = {
                "reserved_capital": str(sizing.cash_required),
                "reserved_risk": str(sizing.planned_loss),
            }
            sizing_plan = {
                "instrument": instrument.token,
                "quantity": sizing.quantity,
                "lots": sizing.lots,
                "entry_price": str(sizing.entry_price),
                "stop_price": str(sizing.stop_price),
                "stop_exit_price": str(sizing.stop_exit_price),
                "target_price": str(sizing.target_price),
                "planned_loss": str(sizing.planned_loss),
                "projected_net_reward": str(sizing.projected_net_reward),
                "cash_required": str(sizing.cash_required),
                "rejections": [
                    {"token": token, "lots": lots, "reason": reason}
                    for token, lots, reason in sizing.rejections
                ],
                "rejection_details": {
                    "PLANNED_LOSS_LIMIT": str(config.max_planned_loss),
                    "NET_REWARD_BELOW_MINIMUM": str(config.min_projected_net_reward),
                },
            }
        expires_at = now + timedelta(seconds=config.order_ttl_seconds)
        if side == "BUY":
            cutoff = datetime.combine(now.astimezone(IST).date(), time(14, 45), tzinfo=IST)
            expires_at = min(expires_at, cutoff)
        order = {
            "order_id": uuid4().hex[:20],
            "intent_id": intent["intent_id"],
            "side": side,
            "symbol": instrument.symbol,
            "token": instrument.token,
            "quantity": quantity,
            "payload": {
                "instrument": instrument.model_dump(mode="json"),
                "decision_id": intent.get("decision_id"),
                "exit_reason": intent.get("exit_reason", "SIGNAL_EXIT"),
                "configuration": config.model_dump(mode="json"),
                "configuration_id": config.version_id,
                "confidence": confidence,
                "runner_owner": intent.get("runner_owner"),
                "protection": held.get("protection") if side == "SELL" else None,
                "signal_context": decision if side == "BUY" else None,
                "sizing_plan": sizing_plan,
                "entry_order_id": held["entry_order_id"] if side == "SELL" else None,
                "risk_approval": {
                    "approved": True,
                    "mode": "PAPER_ONLY",
                    "quantity": quantity,
                    "planned_risk": reservation.get("reserved_risk"),
                    "capital_reservation": reservation.get("reserved_capital"),
                },
                **reservation,
            },
            "eligible_at": now + timedelta(milliseconds=config.latency_ms),
            "expires_at": expires_at,
            "created_at": now,
        }
        return self.store.admit_order(self.user_id, order)

    # Fills ----------------------------------------------------------------

    def _session_open(self, now):
        from .assessment import _session, _window

        try:
            window = _window(now.astimezone(IST).date(), self.session_reader or _session)
        except Exception:
            return False
        return bool(window and window[0] <= now < window[1])

    def _slippage(self, instrument):
        config = self.config
        ticks = getattr(config, "slippage_ticks", 0) if config else 0
        tick = (
            instrument.tick_size
            if isinstance(instrument, Instrument)
            else Decimal(str(instrument["tick_size"]))
        )
        return tick * ticks

    def _depth(self, instrument, now, config=None):
        """Best bid/ask as a Quote from the native cache, or None when unusable."""
        try:
            if not isinstance(instrument, Instrument):
                instrument = Instrument.model_validate(instrument)
        except (ValueError, TypeError):
            return None
        if self.market_data is None:
            try:
                from services.market_data_service import get_market_data_service

                self.market_data = get_market_data_service()
            except Exception:
                return None
        try:
            cached = self.market_data.get_all_data(instrument.symbol, instrument.exchange)
        except Exception:
            return None
        source = cached.get("source_observations", {}).get("3")
        depth = (source.get("depth") or source) if source else (cached.get("depth") or {})
        bid = _best_level(depth.get("buy") or depth.get("bids"))
        ask = _best_level(depth.get("sell") or depth.get("asks"), high=False)
        stamp = _epoch(
            source.get("ltt") if source else (depth.get("source_time") or depth.get("ltt"))
        )
        ltp = source.get("ltp") if source else cached.get("ltp")
        if isinstance(ltp, dict):
            ltp = ltp.get("value")
        config = config or self.config
        max_age = getattr(config, "quote_max_age", 5) if config else 5
        if stamp is None or stamp > now or (now - stamp).total_seconds() > max_age:
            return None
        received = _epoch(source.get("received_time") if source else cached.get("last_update"))
        if received is None or received < stamp or received > now:
            return None
        if any(level and level[0] % instrument.tick_size != 0 for level in (bid, ask)):
            return None
        try:
            return Quote(
                token=instrument.token,
                source_time=stamp,
                received_time=received,
                ltp=Decimal(str(ltp)) if ltp is not None and Decimal(str(ltp)) > 0 else None,
                bid=None if bid is None else bid[0],
                ask=None if ask is None else ask[0],
                bid_size=0 if bid is None else bid[1],
                ask_size=0 if ask is None else ask[1],
                volume=source.get("volume") if source else cached.get("volume"),
                provider="native_depth",
            )
        except (ValueError, TypeError, ArithmeticError):
            return None

    def process(self, now=None):
        """Expire stale intents, then fill eligible pending orders on depth."""
        now = now or self.clock()
        self.store.recover_legacy(self.user_id, now)
        self.store.expire_pending(self.user_id, now)
        resolved = []
        for order in self.store.pending_orders(self.user_id):
            eligible = _epoch(order["eligible_at"])
            if eligible is None or eligible > now:
                continue
            from .config import StrategyConfig

            config = StrategyConfig.model_validate(order["payload"]["configuration"])
            quote = self._depth(order["payload"]["instrument"], now, config)
            if quote is None:
                continue
            if not self._session_open(now):
                continue
            tick = Decimal(str(order["payload"]["instrument"]["tick_size"]))
            if order["side"] == "BUY":
                instrument = Instrument.model_validate(order["payload"]["instrument"])
                if (
                    quote.ask is None
                    or quote.ask_size < order["quantity"]
                    or instrument.master_date != now.astimezone(IST).date()
                    or instrument.expiry < now.astimezone(IST).date()
                ):
                    continue
                price = quote.ask + tick * config.slippage_ticks
                size = quote.ask_size
            else:
                if quote.bid is None or quote.bid_size < order["quantity"]:
                    continue
                price = quote.bid - tick * config.slippage_ticks
                size = quote.bid_size
            if price <= 0:
                continue
            fees = _charges(order["side"], price, order["quantity"], config)
            from hashlib import sha256

            snapshot_id = sha256(
                f"{quote.token}:{quote.source_time.isoformat()}:{order['side']}".encode()
            ).hexdigest()
            resolved.append(
                self.store.fill(
                    self.user_id,
                    order["order_id"],
                    price,
                    fees,
                    now,
                    snapshot_id=snapshot_id,
                    displayed_size=size,
                    observation=quote.model_dump(mode="json"),
                )
            )
        return resolved

    def monitor_exits(
        self,
        now=None,
        technical_invalidations=None,
        operator_close=False,
        discretionary_exits=None,
    ):
        """Protect exposure independently of entry controls. Failed exits stay latched."""
        from .assessment import _session, _window
        from .config import StrategyConfig

        now = now or self.clock()
        intents = []
        self.store.expire_pending(self.user_id, now)
        for held in self.store.positions(self.user_id):
            protection = held.get("protection")
            if not protection:
                continue  # Reconciliation reports legacy exposure as blocked.
            config = StrategyConfig.model_validate(protection["configuration"])
            quote = self._depth(held["instrument"], now, config)
            forced = None
            local = now.astimezone(IST)
            try:
                window = _window(local.date(), self.session_reader or _session)
            except Exception:
                window = None
            if (now - _epoch(held["opened_at"])).total_seconds() >= config.max_hold_minutes * 60:
                forced = "MAX_HOLD"
            elif (
                config.technical_exit
                and technical_invalidations
                and held["token"] in technical_invalidations
            ):
                forced = "TECHNICAL_INVALIDATION"
            elif (
                local.time().replace(tzinfo=None) >= config.exit_by
                or (window and now >= window[1] - timedelta(minutes=5))
                or not window
            ):
                forced = "SESSION_EXIT"
            elif operator_close:
                forced = "OPERATOR_CLOSE"
            elif discretionary_exits and held["token"] in discretionary_exits:
                forced = discretionary_exits[held["token"]]
            protection = self.store.observe_position(
                self.user_id, held["token"], quote, now, forced
            )
            if not protection or not protection.get("exit_reason"):
                continue
            pending = [
                o
                for o in self.store.pending_orders(self.user_id)
                if o["side"] == "SELL" and o["token"] == held["token"]
            ]
            if pending:
                continue
            # Resolved failed attempts receive a new deterministic attempt identity.
            attempts = self.store.exit_attempt_count(self.user_id, held["entry_order_id"])
            try:
                intents.append(
                    self.admit(
                        {
                            "intent_id": f"exit:{held['entry_order_id']}:{attempts}",
                            "side": "SELL",
                            "symbol": held["symbol"],
                            "token": held["token"],
                            "instrument": held["instrument"],
                            "quantity": held["quantity"],
                            "exit_reason": protection["exit_reason"],
                        },
                        now,
                    )
                )
            except OrderRefused:
                # A competing monitor may already own the reserved exit quantity.
                continue
        return intents

    def reconcile(self, now=None):
        """Restart recovery: expire dead intents and report the durable state."""
        now = now or self.clock()
        self.store.recover_legacy(self.user_id, now)
        self.store.expire_pending(self.user_id, now)
        positions = self.store.positions(self.user_id)
        missing = [
            p["token"]
            for p in positions
            if not p.get("protection") or p["protection"].get("legacy")
        ]
        reasons = self.store.reconciliation_issues(self.user_id)
        if missing:
            reasons.append("LEGACY_PROTECTION_REQUIRES_REVIEW")
        if reasons:
            self.store.block_reconciliation(self.user_id, now, "; ".join(reasons))
        else:
            self.store.mark_reconciled(self.user_id, now)
        return {
            "account": self.store.account(self.user_id, now),
            "pending": self.store.pending_orders(self.user_id),
            "positions": positions,
            "reasons": reasons,
        }
