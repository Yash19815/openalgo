"""Recorded simulated fill quality, never inferred broker execution quality."""

from datetime import UTC
from decimal import Decimal

from .config import StrategyConfig
from .models import Instrument, Quote


def fill_quality(order):
    try:
        quote = Quote.model_validate(order.payload["fill_observation"])
        item = Instrument.model_validate(order.payload["instrument"])
        config = StrategyConfig.model_validate(order.payload["configuration"])
        resolved = (
            order.resolved_at.replace(tzinfo=UTC)
            if order.resolved_at.tzinfo is None
            else order.resolved_at
        )
        if (
            quote.token != item.token
            or quote.bid is None
            or quote.ask is None
            or not quote.source_time <= quote.received_time <= resolved
            or (resolved - quote.source_time).total_seconds() > config.quote_max_age
            or quote.bid % item.tick_size
            or quote.ask % item.tick_size
        ):
            raise ValueError
        spread = quote.ask - quote.bid
        slippage = order.price - quote.ask if order.side == "BUY" else quote.bid - order.price
        expected = item.tick_size * config.slippage_ticks
        return {
            "basis": "RECORDED_PAPER_FILL_NOT_BROKER_EXECUTION",
            "spread_points": str(spread),
            "spread_bps": str(spread / ((quote.ask + quote.bid) / 2) * 10000),
            "adverse_slippage_points": str(slippage),
            "modeled_slippage_points": str(expected),
            "slippage_model_difference": str(slippage - expected),
            "source_time": quote.source_time.isoformat(),
            "received_time": quote.received_time.isoformat(),
            "quantity": order.quantity,
        }
    except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError):
        return {"basis": "UNAVAILABLE", "reason": "NO_VALIDATED_RECORDED_QUOTE_AND_FILL"}


def summarize_quality(entries, exits, protections):
    def aggregate(rows):
        available = [r for r in rows if r["basis"] != "UNAVAILABLE"]
        quantity = sum(r["quantity"] for r in available)
        return {
            "available": len(available),
            "total": len(rows),
            "quantity_weighted_adverse_slippage": str(
                sum(Decimal(r["adverse_slippage_points"]) * r["quantity"] for r in available)
                / quantity
            )
            if quantity
            else None,
            "quantity_weighted_spread": str(
                sum(Decimal(r["spread_points"]) * r["quantity"] for r in available) / quantity
            )
            if quantity
            else None,
        }

    missing = sum(not p.get("observation_count") for p in protections)
    locks = sum(bool(p.get("profit_lock_active")) for p in protections)
    gap_evidence = [
        p
        for p in protections
        if p.get("observation_count", 0) >= 2 and p.get("max_observation_gap_seconds") is not None
    ]
    gaps = sum(
        Decimal(str(p["max_observation_gap_seconds"]))
        > Decimal(str((p.get("configuration") or {}).get("quote_max_age", 5)))
        for p in gap_evidence
    )
    suggestions = []
    for code, count, message in (
        (
            "OBSERVATION_COVERAGE",
            missing,
            "Inspect missing sampled exposure observations before interpreting exit effectiveness.",
        ),
        (
            "FEED_GAPS",
            gaps,
            "Inspect recorded quote gaps before trusting continuous protection assumptions.",
        ),
        (
            "SLIPPAGE_MODEL",
            sum(
                Decimal(r["slippage_model_difference"]) > 0
                for r in [*entries, *exits]
                if r["basis"] != "UNAVAILABLE"
            ),
            "Review adverse slippage against the recorded model using genuine execution evidence.",
        ),
    ):
        if count:
            suggestions.append(
                {
                    "code": code,
                    "evidence_count": count,
                    "message": message,
                    "requires_explicit_approval": True,
                    "active_settings_changed": False,
                }
            )
    return {
        "entry": aggregate(entries),
        "exit": aggregate(exits),
        "protection": {
            "trades": len(protections),
            "recorded_profit_locks": locks,
            "missing_observation_series": missing,
            "gapped_series": gaps,
            "unavailable_gap_series": len(protections) - len(gap_evidence),
            "extrema_basis": "SAMPLED_NOT_CONTINUOUS",
        },
        "suggestions": suggestions,
        "active_settings_changed": False,
    }
