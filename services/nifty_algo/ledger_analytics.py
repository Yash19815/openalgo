"""Normalize closed ledger rows against their immutable paper fill evidence."""

from datetime import UTC
from decimal import Decimal

from .models import Instrument


class AnalyticsDataError(ValueError):
    """Persisted evidence cannot support an authoritative analytics result."""


IDENTITY_FIELDS = (
    "token",
    "symbol",
    "exchange",
    "underlying",
    "kind",
    "expiry",
    "strike",
    "lot_size",
    "tick_size",
)


def _instant(value):
    # SQLite stores these ledger timestamps as naive UTC.
    return value.replace(tzinfo=UTC).isoformat() if value.tzinfo is None else value.isoformat()


def fill_facts(trade, entry, exit_order):
    """Return a validated journal event and an allowlisted, secret-free detail."""
    try:
        if entry is None or exit_order is None:
            raise ValueError("Missing fill")
        instrument = Instrument.model_validate(entry.payload["instrument"])
        exit_instrument = Instrument.model_validate(exit_order.payload["instrument"])
        if (
            entry.status != "FILLED"
            or exit_order.status != "FILLED"
            or entry.side != "BUY"
            or exit_order.side != "SELL"
            or instrument.kind not in ("CE", "PE")
            or any(
                getattr(instrument, field) != getattr(exit_instrument, field)
                for field in IDENTITY_FIELDS
            )
            or entry.token != instrument.token
            or exit_order.token != instrument.token
            or entry.symbol != trade.symbol
            or exit_order.symbol != trade.symbol
            or instrument.symbol != trade.symbol
            or exit_order.payload.get("entry_order_id") != entry.order_id
            or type(trade.quantity) is not int
            or not 0 < trade.quantity <= entry.quantity
            or trade.quantity != exit_order.quantity
            or trade.entry_price != entry.price
            or trade.exit_price != exit_order.price
            or _instant(trade.opened_at) != _instant(entry.resolved_at)
            or _instant(trade.closed_at) != _instant(exit_order.resolved_at)
        ):
            raise ValueError("Conflicting fill")
        for amount in (
            trade.entry_price,
            trade.exit_price,
            trade.gross,
            trade.fees,
            trade.net,
            entry.fees,
            exit_order.fees,
        ):
            if amount is None or not Decimal(amount).is_finite():
                raise ValueError("Invalid fill amount")
        if (
            trade.entry_price <= 0
            or trade.exit_price <= 0
            or entry.fees < 0
            or exit_order.fees < 0
            or not exit_order.fees <= trade.fees <= exit_order.fees + entry.fees
            or trade.gross != (trade.exit_price - trade.entry_price) * trade.quantity
            or trade.net != trade.gross - trade.fees
        ):
            raise ValueError("Unreconciled fill")
        risk = (entry.payload.get("risk_approval") or {}).get("planned_risk")
        metadata = next(
            (
                r
                for r in (entry.payload.get("candidate_metadata") or [])
                if r.get("token") == instrument.token
            ),
            {},
        )
        sizing = entry.payload.get("sizing_plan") or {}
        selected = next(
            (
                r
                for r in sizing.get("ranking", [])
                if r.get("token") == instrument.token and r.get("quantity") == entry.quantity
            ),
            {},
        )
        journal = {
            "trade_id": entry.order_id,
            "fill_id": exit_order.order_id,
            "instrument": {
                field: instrument.model_dump(mode="json")[field] for field in IDENTITY_FIELDS
            },
            "quantity": trade.quantity,
            "opened": _instant(trade.opened_at),
            "closed": _instant(trade.closed_at),
            "gross": str(trade.gross),
            "charges": str(trade.fees),
            "net": str(trade.net),
            "planned_risk": risk,
            "moneyness": metadata.get("moneyness", "UNAVAILABLE"),
            "confidence": (entry.payload.get("confidence") or {}).get("score"),
            "selector_score": selected.get("total"),
            "exit_reason": trade.reason,
        }
        detail = {
            "id": trade.id,
            "trade_id": entry.order_id,
            "fill_id": exit_order.order_id,
            "symbol": trade.symbol,
            "quantity": trade.quantity,
            "entry_price": str(trade.entry_price),
            "exit_price": str(trade.exit_price),
            "gross": str(trade.gross),
            "fees": str(trade.fees),
            "net": str(trade.net),
            "reason": trade.reason,
            "opened_at": journal["opened"],
            "closed_at": journal["closed"],
            "instrument": journal["instrument"],
            "planned_risk": risk,
            "configuration_id": entry.payload.get("configuration_id"),
            "decision_id": entry.payload.get("decision_id"),
        }
        return journal, detail
    except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError):
        raise AnalyticsDataError("Persisted paper fill evidence is inconsistent") from None
