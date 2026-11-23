"""Versioned Decimal scoring over risk-approved contract/quantity proposals.

All factors lie in [0, 1]. Missing delta earns zero under its unchanged weight;
weights are never redistributed across candidates with different data coverage.
"""

from decimal import Decimal

D = Decimal
FACTORS = ("liquidity", "spread", "delta", "reward_risk", "capital_efficiency")
POLICY = "risk-approved-weighted-v1"


def clamp(value):
    return max(D(0), min(D(1), value))


def score_plan(plan, quote, config, now):
    item = plan.instrument
    spread_bps = (quote.ask - quote.bid) / ((quote.ask + quote.bid) / 2) * 10000
    depth_ratio = D(min(quote.ask_size, quote.bid_size)) / plan.quantity
    delta_available = (
        item.delta is not None
        and item.delta_time is not None
        and now is not None
        and 0 <= (now - item.delta_time).total_seconds() <= config.quote_max_age
        and (item.delta >= 0 if item.kind == "CE" else item.delta <= 0)
    )
    target = D(str(config.delta_target))
    factors = {
        "liquidity": D("0.75") * clamp(depth_ratio / 3)
        + D("0.25") * clamp(D(quote.volume or 0) / (config.min_volume * 3)),
        "spread": clamp(1 - spread_bps / D(str(config.max_spread_bps))),
        "delta": clamp(1 - abs(abs(D(str(item.delta))) - target) / max(target, 1 - target))
        if delta_available
        else D(0),
        "reward_risk": clamp(plan.projected_net_reward / plan.planned_loss / 2)
        if plan.planned_loss > 0
        else D(1),
        "capital_efficiency": clamp(
            plan.projected_net_reward / plan.cash_required / config.target_max
        ),
    }
    weights = dict(zip(FACTORS, config.selector_weights, strict=True))
    total = sum(factors[name] * weights[name] for name in FACTORS)
    return {
        "policy": POLICY,
        "token": item.token,
        "lots": plan.lots,
        "quantity": plan.quantity,
        "entry_price": str(plan.entry_price),
        "stop_price": str(plan.stop_price),
        "target_price": str(plan.target_price),
        "capital_required": str(plan.cash_required),
        "planned_loss": str(plan.planned_loss),
        "projected_net_reward": str(plan.projected_net_reward),
        "inputs": {
            "bid": str(quote.bid),
            "ask": str(quote.ask),
            "spread_bps": str(spread_bps),
            "ask_size": quote.ask_size,
            "bid_size": quote.bid_size,
            "volume": quote.volume,
            "delta": str(item.delta) if delta_available else None,
            "quote_source_time": quote.source_time.isoformat(),
        },
        "coverage": {"delta": bool(delta_available), "policy": "FIXED_WEIGHT_MISSING_DELTA_ZERO"},
        "scores": {name: str(value) for name, value in factors.items()},
        "weights": {name: str(value) for name, value in weights.items()},
        "total": str(total),
    }
