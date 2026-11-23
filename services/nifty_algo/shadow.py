"""Hypothetical shadow positions with their own ledger.

Research only: nothing here admits, fills or transmits an order. Sizing and
exits reuse the pure risk and protection functions; the store persists the
hypothetical state under the per-user lock.
"""

from datetime import datetime
from decimal import Decimal

from .calendar import IST, nifty_session
from .config import StrategyConfig
from .models import Instrument
from .paper_executor import _charges
from .protection import initial_protection, mandatory_exit_reason
from .risk_manager import AccountRisk, plan_entry


class ShadowBook:
    def __init__(self, store, user_id, quote=None):
        self.store, self.user_id = store, user_id
        self.quote = quote

    def _depth(self, instrument, now, config):
        return self.quote(instrument, now, config) if self.quote else None

    def _window(self, now):
        session = nifty_session(self.user_id, now.astimezone(IST).date(), store=self.store)
        return session, session["window"] if session["status"] == "TRADING" else None

    def entry_blocks(self, now, config):
        """Independent entries: an open eligible session, 09:15 to before 14:45, no cooldown.

        Monthly locks guard primary capital only and do not block shadows.
        """
        session, window = self._window(now)
        reasons = []
        if session["status"] != "TRADING":
            reasons.append(session["status"])
        elif not window or not window[0] <= now < window[1]:
            reasons.append("SESSION_CLOSED")
        local = now.astimezone(IST).time().replace(tzinfo=None)
        if not config.shadow_entry_after <= local < config.entry_before:
            reasons.append("SHADOW_ENTRY_WINDOW")
        self.store.resolve_cooldowns(self.user_id, now)
        reasons.extend(self.store.cooldown_reasons(self.user_id, now))
        return reasons

    def open_independent(self, decision, now, config, candidates):
        """Open a hypothetical entry for a qualifying signal; returns (row, reasons)."""
        confidence = decision.get("confidence") or {}
        if (
            not decision.get("eligible")
            or decision.get("side") not in ("CE", "PE")
            or decision.get("config_id") != config.version_id
            or confidence.get("method") != config.confidence_method
        ):
            return None, ["QUALIFYING_SIGNAL_REQUIRED"]
        try:
            decided = datetime.fromisoformat(decision["timestamp"])
            if decided.tzinfo is None or not 0 <= (now - decided).total_seconds() <= 30:
                return None, ["SIGNAL_EXPIRED"]
        except (KeyError, TypeError, ValueError):
            return None, ["SIGNAL_EXPIRED"]
        reasons = self.entry_blocks(now, config)
        if reasons:
            return None, reasons
        active = self.store.active_shadow(self.user_id)
        if active is not None:
            if active["shadow_key"] == "independent:" + decision["decision_id"]:
                return active, []
            return None, ["SHADOW_ACTIVE"]
        equity = Decimal(self.store.shadow_ledger(self.user_id)["equity"])
        if equity <= 0:
            return None, ["SHADOW_LEDGER_DEPLETED"]
        options = candidates() if callable(candidates) else candidates
        quotes = [(candidate, self._depth(candidate, now, config)) for candidate in options]
        sizing = plan_entry(
            AccountRisk(equity=equity, available=equity, starting_day_equity=equity),
            quotes,
            config,
            confidence["score"],
            _charges,
            now=now,
        )
        if sizing.instrument is None:
            reasons = list(dict.fromkeys(reason for _, _, reason in sizing.rejections))
            return None, reasons or ["POSITION_SIZE_ZERO"]
        instrument = sizing.instrument
        try:
            protection = initial_protection(
                sizing.entry_price, instrument.tick_size, config, confidence
            )
        except ValueError:
            return None, ["PROTECTION_TICK_INVALID"]
        fees = _charges("BUY", sizing.entry_price, sizing.quantity, config)
        protection["entry_fees_remaining"] = str(fees)
        protection["signal_context"] = {
            "decision_id": decision.get("decision_id"),
            "snapshot": decision.get("snapshot"),
        }
        protection["sizing_plan"] = {
            "ranking": list(sizing.ranking),
            "rejections": [
                {"token": token, "lots": lots, "reason": reason}
                for token, lots, reason in sizing.rejections
            ],
            "lots": sizing.lots,
            "planned_loss": str(sizing.planned_loss),
            "projected_net_reward": str(sizing.projected_net_reward),
            "cash_required": str(sizing.cash_required),
        }
        return self.store.open_shadow(
            self.user_id,
            {
                "decision_id": decision["decision_id"],
                "token": instrument.token,
                "symbol": instrument.symbol,
                "instrument": instrument.model_dump(mode="json"),
                "quantity": sizing.quantity,
                "entry_price": sizing.entry_price,
                "entry_fees": fees,
                "protection": protection,
                "opened_at": now,
            },
            config,
        )

    def sync_mirrors(self, now):
        return self.store.sync_shadow_mirrors(self.user_id, now)

    def monitor(self, now):
        """Hypothetical stop, profit lock, trail, target and mandatory exits."""
        row = self.store.active_shadow(self.user_id)
        if row is None or row["kind"] != "INDEPENDENT":
            return row
        config = StrategyConfig.model_validate(row["protection"]["configuration"])
        quote = self._depth(Instrument.model_validate(row["instrument"]), now, config)
        _, window = self._window(now)
        forced = mandatory_exit_reason(
            datetime.fromisoformat(row["opened_at"]), now, config, window
        )
        return self.store.observe_shadow(
            self.user_id,
            row["id"],
            quote,
            now,
            forced,
            market_closed=window is None or now >= window[1],
        )
