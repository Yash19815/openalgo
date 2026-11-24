"""Metrics derived only from simulated fills and persisted equity observations."""

from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def _timestamp(value):
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        raise ValueError("Analytics timestamp requires timezone")
    return stamp.astimezone(UTC).isoformat()


def _amount(value):
    amount = Decimal(str(value))
    if not amount.is_finite():
        raise ValueError("Non-finite analytics amount")
    return amount


def performance(journal, initial, equity_points=()):
    """Adapted from trader-bot cf7acb4, validated and normalized before grouping."""
    initial = _amount(initial)
    if initial <= 0:
        raise ValueError("Positive starting capital required")
    validated = []
    fill_ids = set()
    for source in journal:
        row = dict(source)
        if row.get("fill_id") is not None:
            if row["fill_id"] in fill_ids:
                raise ValueError("Duplicate fill in analytics input")
            fill_ids.add(row["fill_id"])
        row["opened"], row["closed"] = _timestamp(row["opened"]), _timestamp(row["closed"])
        if (
            row["opened"] > row["closed"]
            or type(row["quantity"]) is not int
            or row["quantity"] <= 0
        ):
            raise ValueError("Invalid closed trade interval or quantity")
        for field in ("net", "gross", "charges"):
            row[field] = _amount(row.get(field, 0))
        risk = row.get("planned_risk")
        row["planned_risk"] = _amount(risk) if risk is not None else None
        if (
            row["charges"] < 0
            or (row["planned_risk"] is not None and row["planned_risk"] < 0)
            or row["gross"] - row["charges"] != row["net"]
        ):
            raise ValueError("Trade costs do not reconcile")
        if row["instrument"]["kind"] not in ("CE", "PE"):
            raise ValueError("NIFTY option journal required")
        validated.append(row)
    equity_points = [
        dict(point, timestamp=_timestamp(point["timestamp"]), equity=_amount(point["equity"]))
        for point in equity_points
    ]
    # Partial exits aggregate to one trade for win-rate statistics.
    trades = {}
    for row in validated:
        key = row["trade_id"]
        if key not in trades:
            trades[key] = {
                **row,
                "net": Decimal(0),
                "gross": Decimal(0),
                "charges": Decimal(0),
                "quantity": 0,
            }
        entry = trades[key]
        if any(
            entry.get(field) != row.get(field) for field in ("instrument", "opened", "planned_risk")
        ):
            raise ValueError("Conflicting partial-exit entry identity")
        for field in ("net", "gross", "charges"):
            trades[key][field] += Decimal(row[field])
        trades[key]["quantity"] += row["quantity"]
        trades[key]["opened"] = min(trades[key]["opened"], row["opened"])
        trades[key]["closed"] = max(trades[key]["closed"], row["closed"])
    ordered = sorted(trades.values(), key=lambda r: (r["closed"], str(r["trade_id"])))
    values = [r["net"] for r in ordered]
    winners, losers = [v for v in values if v > 0], [v for v in values if v < 0]

    def average(v):
        return sum(v) / len(v) if v else None

    current = Decimal(initial)
    high = current
    max_drawdown = Decimal(0)
    curve, drawdowns = [], []
    # A partial exit realizes money immediately, not at the final exit of its trade.
    fills = sorted(
        validated,
        key=lambda r: (r["closed"], str(r["trade_id"]), str(r.get("fill_id", ""))),
    )
    for row in fills:
        current += row["net"]
        high = max(high, current)
        max_drawdown = max(max_drawdown, high - current)
        curve.append({"timestamp": row["closed"], "equity": str(current)})
        drawdowns.append({"timestamp": row["closed"], "drawdown": str(high - current)})
    observed_high = Decimal(initial)
    observed_drawdown = Decimal(0)
    for point in sorted(equity_points, key=lambda p: p["timestamp"]):
        equity = Decimal(point["equity"])
        observed_high = max(observed_high, equity)
        observed_drawdown = max(observed_drawdown, observed_high - equity)
    groups = {
        k: defaultdict(lambda: {"net": Decimal(0), "trade_ids": set()})
        for k in (
            "daily",
            "weekly",
            "monthly",
            "entry_hour",
            "option_type",
            "expiry_days",
            "moneyness",
            "confidence",
            "selector_score",
            "weekday",
            "exit_reason",
            "duration",
        )
    }
    consecutive_wins = consecutive_losses = max_wins = max_losses = 0
    ratios = []
    for row in fills:
        closed = datetime.fromisoformat(row["closed"]).astimezone(IST)
        opened = datetime.fromisoformat(row["opened"]).astimezone(IST)
        keys = {
            "daily": closed.date().isoformat(),
            "weekly": closed.strftime("%G-W%V"),
            "monthly": closed.strftime("%Y-%m"),
            "entry_hour": opened.strftime("%H:00"),
            "option_type": row["instrument"]["kind"],
            "expiry_days": str(
                (datetime.fromisoformat(row["instrument"]["expiry"]).date() - opened.date()).days
            ),
            "moneyness": row.get("moneyness") or "UNAVAILABLE",
            "confidence": str(row["confidence"])
            if row.get("confidence") is not None
            else "UNAVAILABLE",
            "selector_score": str(row["selector_score"])
            if row.get("selector_score") is not None
            else "UNAVAILABLE",
            "weekday": opened.strftime("%A"),
            "exit_reason": row.get("exit_reason") or "UNAVAILABLE",
            "duration": str(int((closed - opened).total_seconds() // 300) * 5) + "_MINUTE_BUCKET",
        }
        for group, key in keys.items():
            groups[group][key]["net"] += row["net"]
            groups[group][key]["trade_ids"].add(row["trade_id"])
    for row in ordered:
        row["duration_seconds"] = (
            datetime.fromisoformat(row["closed"]) - datetime.fromisoformat(row["opened"])
        ).total_seconds()
        consecutive_wins = consecutive_wins + 1 if row["net"] > 0 else 0
        consecutive_losses = consecutive_losses + 1 if row["net"] < 0 else 0
        max_wins, max_losses = max(max_wins, consecutive_wins), max(max_losses, consecutive_losses)
        risk = row["planned_risk"]
        if risk:
            ratios.append(row["net"] / risk)
    return {
        "trades": len(ordered),
        "fills": len(fills),
        "wins": len(winners),
        "losses": len(losers),
        "breakeven": sum(value == 0 for value in values),
        "total_gross": str(sum((row["gross"] for row in ordered), Decimal(0))),
        "best": str(max(values)) if values else None,
        "worst": str(min(values)) if values else None,
        "total_net": str(sum(values, Decimal(0))),
        "win_rate": len(winners) / len(values) if values else None,
        "average_winner": str(average(winners)) if winners else None,
        "average_loser": str(average(losers)) if losers else None,
        "profit_factor": float(sum(winners) / abs(sum(losers))) if losers else None,
        "expectancy": str(average(values)) if values else None,
        "maximum_drawdown": str(max_drawdown),
        "observed_maximum_drawdown": str(observed_drawdown) if equity_points else None,
        "average_duration_seconds": average([r["duration_seconds"] for r in ordered]),
        "average_realized_r": str(average(ratios)) if ratios else None,
        "risk_coverage": {
            "available": len(ratios),
            "total": len(ordered),
            "reason": "PLANNED_RISK_MISSING" if len(ratios) < len(ordered) else None,
        },
        "consecutive_wins": max_wins,
        "consecutive_losses": max_losses,
        "costs": str(sum((r["charges"] for r in ordered), Decimal(0))),
        "groups": {
            kind: {
                key: {"net": str(value["net"]), "trades": len(value["trade_ids"])}
                for key, value in group.items()
            }
            for kind, group in groups.items()
        },
        "equity_curve": curve,
        "drawdown_curve": drawdowns,
        "basis": "PAPER_FILLS_REALIZED",
    }
