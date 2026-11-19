"""Feature-scoped strict paper execution.

Fills resolve only from observed bid/ask depth inside this feature's isolated
ledger — never from LTP, and never through the shared Sandbox, broker modules,
or generic order services. The generic ``submit`` boundary stays permanently
closed: orders enter only through ``admit`` after risk-manager checks and
resolve only through ``process`` against fresh market depth.
"""

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

from services.nifty_algo.models import Instrument, Quote

IST = ZoneInfo("Asia/Kolkata")

TICK = Decimal("0.05")
BROKERAGE = Decimal("20")


class PaperExecutionUnavailable(ValueError):
    pass


class OrderRefused(ValueError):
    """Risk or ledger checks rejected the intent before admission."""

    def __init__(self, reasons):
        self.reasons = list(reasons)
        super().__init__(", ".join(self.reasons))


def _epoch(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        stamp = datetime.fromtimestamp(value / 1000 if value > 10**12 else value, UTC)
        return stamp
    try:
        stamp = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)


def _best_level(entries, high=True):
    """(price, quantity) at the best level of a depth side."""
    best = None
    for entry in entries or []:
        try:
            if isinstance(entry, dict):
                price = Decimal(str(entry["price"]))
                size = int(entry.get("quantity") or entry.get("orders") or 0)
            else:
                price = Decimal(str(entry[0]))
                size = int(entry[1])
        except (KeyError, IndexError, TypeError, ArithmeticError):
            continue
        if best is None or (price > best[0] if high else price < best[0]):
            best = (price, size)
    return best


def _charges(side, price, quantity):
    """Deterministic Indian-options charge schedule for the paper ledger."""
    turnover = price * quantity
    txn = turnover * Decimal("0.0005")
    gst = (BROKERAGE + txn) * Decimal("0.18")
    stt = turnover * Decimal("0.000625") if side == "SELL" else Decimal("0")
    stamp = turnover * Decimal("0.00003") if side == "BUY" else Decimal("0")
    sebi = turnover * Decimal("0.000001")
    return BROKERAGE + txn + gst + stt + stamp + sebi


class NiftyPaperExecutor:
    mode = "PAPER_ONLY"

    def __init__(self, store=None, user_id=None, config=None, market_data=None, clock=None):
        self.store = store
        self.user_id = user_id
        self.config = config
        self.market_data = market_data
        self.clock = clock or (lambda: datetime.now(UTC))

    def _bound(self):
        return self.store is not None and self.user_id is not None

    def readiness(self):
        """Structural gates only; live depth is probed per fill, not here."""
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
                "ready": False,
                "detail": "Background strategy runner is not wired yet; orders can "
                "only be admitted and processed through the scoped executor API.",
            },
        ]

    def submit(self, *args, **kwargs):
        raise PaperExecutionUnavailable("Paper execution prerequisites are incomplete.")

    # Admission ------------------------------------------------------------

    def admit(self, intent, now=None):
        """Validate an intent through the risk manager, then persist it once."""
        from services.nifty_algo.config import StrategyConfig
        from services.nifty_algo.risk_manager import AccountRisk, entry_reasons, size_quantity

        now = now or self.clock()
        existing = self.store.order_by_intent(self.user_id, intent["intent_id"])
        if existing is not None:
            return existing, False
        state = self.store.read(self.user_id)
        config = self.config or StrategyConfig.model_validate(state["configuration"])
        row = self.store.account(self.user_id, now)
        positions = self.store.positions(self.user_id)
        pending = self.store.pending_orders(self.user_id)
        side = intent["side"]
        try:
            instrument = Instrument.model_validate(intent["instrument"])
        except (ValueError, TypeError, KeyError):
            raise OrderRefused(["METADATA_INVALID"])
        held = next((row for row in positions if row["token"] == intent["token"]), None)
        if side == "SELL":
            if held is None:
                raise OrderRefused(["UNCOVERED_SELL"])
            quantity = intent.get("quantity") or held["quantity"]
            if quantity > held["quantity"]:
                raise OrderRefused(["UNCOVERED_SELL"])
        else:
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
            quote = self._depth(instrument, now)
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
            quantity = intent.get("quantity") or size_quantity(
                risk,
                instrument,
                quote,
                config,
                round_trip_cost_per_lot=(
                    _charges("BUY", quote.ask, instrument.lot_size)
                    + _charges("SELL", quote.ask, instrument.lot_size)
                ),
            )
            if quantity < 1:
                raise OrderRefused(["POSITION_SIZE_ZERO"])
        order = {
            "order_id": uuid4().hex[:20],
            "intent_id": intent["intent_id"],
            "side": side,
            "symbol": intent["symbol"],
            "token": intent["token"],
            "quantity": quantity,
            "payload": {
                "instrument": instrument.model_dump(mode="json"),
                "decision_id": intent.get("decision_id"),
                "exit_reason": intent.get("exit_reason", "SIGNAL_EXIT"),
            },
            "eligible_at": now + timedelta(milliseconds=config.latency_ms),
            "expires_at": now + timedelta(seconds=config.order_ttl_seconds),
            "created_at": now,
        }
        return self.store.admit_order(self.user_id, order)

    # Fills ----------------------------------------------------------------

    @staticmethod
    def _session_open(now):
        return time(9, 15) <= now.astimezone(IST).time() <= time(15, 30)

    def _slippage(self):
        config = self.config
        ticks = getattr(config, "slippage_ticks", 0) if config else 0
        return TICK * ticks

    def _depth(self, instrument, now):
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
        depth = cached.get("depth") or {}
        bid = _best_level(depth.get("buy") or depth.get("bids"))
        ask = _best_level(depth.get("sell") or depth.get("asks"), high=False)
        stamp = _epoch(
            depth.get("ltt") or depth.get("timestamp") or cached.get("last_update")
        )
        ltp = cached.get("ltp")
        config = self.config
        max_age = getattr(config, "quote_max_age", 5) if config else 5
        if (
            stamp is None
            or ltp is None
            or stamp > now
            or (now - stamp).total_seconds() > max_age
        ):
            return None
        received = _epoch(cached.get("last_update"))
        if received is None or received < stamp or received > now:
            received = now
        try:
            return Quote(
                token=instrument.token,
                source_time=stamp,
                received_time=received,
                ltp=Decimal(str(ltp)),
                bid=None if bid is None else bid[0],
                ask=None if ask is None else ask[0],
                bid_size=0 if bid is None else bid[1],
                ask_size=0 if ask is None else ask[1],
                volume=cached.get("volume"),
                provider="native_depth",
            )
        except (ValueError, TypeError, ArithmeticError):
            return None

    def process(self, now=None):
        """Expire stale intents, then fill eligible pending orders on depth."""
        now = now or self.clock()
        self.store.expire_pending(self.user_id, now)
        resolved = []
        for order in self.store.pending_orders(self.user_id):
            eligible = _epoch(order["eligible_at"])
            if eligible is None or eligible > now:
                continue
            quote = self._depth(order["payload"]["instrument"], now)
            if quote is None:
                continue
            if order["side"] == "BUY":
                if quote.ask is None:
                    continue
                price = quote.ask + self._slippage()
            else:
                if quote.bid is None:
                    continue
                price = quote.bid - self._slippage()
            fees = _charges(order["side"], price, order["quantity"])
            resolved.append(self.store.fill(self.user_id, order["order_id"], price, fees, now))
        return resolved

    def reconcile(self, now=None):
        """Restart recovery: expire dead intents and report the durable state."""
        now = now or self.clock()
        self.store.expire_pending(self.user_id, now)
        self.store.mark_reconciled(self.user_id, now)
        return {
            "account": self.store.account(self.user_id, now),
            "pending": self.store.pending_orders(self.user_id),
            "positions": self.store.positions(self.user_id),
        }
