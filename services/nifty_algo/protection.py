"""Decimal option-premium protection. A trigger is not a guaranteed fill."""

from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from .confidence import target_fraction

D = Decimal


def ceiling_tick(price, tick):
    price, tick = D(str(price)), D(str(tick))
    if not price.is_finite() or not tick.is_finite() or price <= 0 or tick <= 0:
        raise ValueError("Positive finite prices and ticks required")
    return (price / tick).to_integral_value(rounding=ROUND_CEILING) * tick


def initial_protection(entry, tick, config, confidence):
    entry = D(str(entry))
    fraction = target_fraction(confidence["score"], config)
    if confidence.get("method") != config.confidence_method:
        raise ValueError("Confidence method mismatch")
    stop = ceiling_tick(entry * (1 - config.premium_stop), tick)
    tick = D(str(tick))
    upper = (entry * (1 + config.target_max) / tick).to_integral_value(rounding=ROUND_FLOOR) * tick
    target = min(ceiling_tick(entry * (1 + fraction), tick), upper)
    if target < entry * (1 + config.target_min):
        raise ValueError("No valid target tick within configured bounds")
    return {
        "configuration": config.model_dump(mode="json"),
        "configuration_id": config.version_id,
        "confidence": confidence,
        "confidence_target_fraction": str(fraction),
        "target_fraction": str(target / entry - 1),
        "target_price": str(target),
        "initial_stop": str(stop),
        "stop_price": str(stop),
        "highest_bid": None,
        "trailing_active": False,
        "last_source_time": None,
        "exit_reason": None,
        "point_unit": "OPTION_PREMIUM",
        "trailing_distance_points": str(config.trailing_distance_points),
    }


def observe_bid(protection, entry, bid, tick, config):
    """Caller validates freshness and serializes persistence before calling."""
    entry, bid = D(str(entry)), D(str(bid))
    if not bid.is_finite() or bid <= 0:
        raise ValueError("Executable positive bid required")
    result = dict(protection)
    high = max(D(protection["highest_bid"]) if protection["highest_bid"] else bid, bid)
    active = protection["trailing_active"] or high >= entry + config.trailing_activation_points
    stop = max(D(protection["initial_stop"]), D(protection["stop_price"]))
    if active and high > config.trailing_distance_points:
        stop = max(stop, ceiling_tick(high - config.trailing_distance_points, tick))
    result.update(highest_bid=str(high), trailing_active=active, stop_price=str(stop))
    reason = None
    if bid <= stop:
        reason = "TRAILING_STOP" if stop > D(protection["initial_stop"]) else "INITIAL_STOP"
    elif protection.get("target_price") is not None and bid >= D(protection["target_price"]):
        reason = "TARGET"
    result["exit_reason"] = protection.get("exit_reason") or reason
    return result
