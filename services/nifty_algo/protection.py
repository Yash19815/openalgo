"""Decimal option-premium protection. A trigger is not a guaranteed fill."""

from datetime import timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from zoneinfo import ZoneInfo

from .confidence import target_fraction
from .session_policy import SESSION_EXIT_BUFFER

D = Decimal
IST = ZoneInfo("Asia/Kolkata")


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
        "lowest_bid": None,
        "observation_count": 0,
        "max_observation_gap_seconds": 0,
        "trailing_active": False,
        "trailing_stop": None,
        "profit_lock_active": False,
        "profit_floor_stop": None,
        "profit_lock_activation": None,
        "estimated_net": None,
        "last_source_time": None,
        "exit_reason": None,
        "point_unit": "OPTION_PREMIUM",
        "trailing_distance_points": str(config.trailing_distance_points),
    }


def modeled_exit_net(entry_price, quantity, price, entry_fees, tick, config, charges):
    entry_price, price, entry_fees, tick = (
        D(str(entry_price)),
        D(str(price)),
        D(str(entry_fees)),
        D(str(tick)),
    )
    if (
        not all(value.is_finite() for value in (entry_price, price, entry_fees, tick))
        or entry_price <= 0
        or price <= 0
        or entry_fees < 0
        or tick <= 0
        or not isinstance(quantity, int)
        or quantity <= 0
    ):
        raise ValueError("Finite positive prices, tick, and quantity required")
    exit_fill = price - D(config.slippage_ticks) * tick
    return (
        (exit_fill - entry_price) * quantity
        - entry_fees
        - D(str(charges("SELL", exit_fill, quantity, config)))
    )


def profit_floor_stop(entry_price, quantity, entry_fees, floor_net, tick, config, charges):
    entry_price, entry_fees, floor_net, tick = (
        D(str(entry_price)),
        D(str(entry_fees)),
        D(str(floor_net)),
        D(str(tick)),
    )
    if (
        not all(value.is_finite() for value in (entry_price, entry_fees, floor_net, tick))
        or entry_price <= 0
        or entry_fees < 0
        or floor_net < 0
        or tick <= 0
        or not isinstance(quantity, int)
        or quantity <= 0
    ):
        raise ValueError("Finite prices, non-negative fees/floor, and positive quantity required")
    estimate = entry_price + (floor_net + entry_fees) / quantity
    estimate += D(config.slippage_ticks) * tick
    candidate = ceiling_tick(estimate, tick)
    for _ in range(1000):
        if (
            modeled_exit_net(entry_price, quantity, candidate, entry_fees, tick, config, charges)
            < floor_net
        ):
            candidate += tick
            continue
        previous = candidate - tick
        if (
            previous > 0
            and modeled_exit_net(entry_price, quantity, previous, entry_fees, tick, config, charges)
            >= floor_net
        ):
            candidate = previous
            continue
        return candidate
    raise ValueError("Profit floor cannot be represented within 1000 ticks")


def _cost_model(config):
    fields = (
        "brokerage",
        "transaction_rate",
        "gst_rate",
        "stt_sell_rate",
        "stamp_buy_rate",
        "sebi_rate",
    )
    return {name: str(getattr(config, name)) for name in fields}


def _source_time_text(source_time):
    if source_time is None:
        return None
    return source_time.isoformat() if hasattr(source_time, "isoformat") else str(source_time)


def observe_bid(
    protection,
    entry,
    bid,
    tick,
    config,
    *,
    quantity=None,
    entry_fees=None,
    charges=None,
    bid_size=None,
    source_time=None,
):
    """Caller validates freshness and serializes persistence before calling."""
    entry, bid = D(str(entry)), D(str(bid))
    if not bid.is_finite() or bid <= 0:
        raise ValueError("Executable positive bid required")
    result = dict(protection)
    result.setdefault("trailing_stop", None)
    result.setdefault("profit_lock_active", False)
    result.setdefault("profit_floor_stop", None)
    result.setdefault("profit_lock_activation", None)
    result.setdefault("estimated_net", None)
    result["new_events"] = []
    result["lowest_bid"] = str(
        min(D(protection["lowest_bid"]) if protection.get("lowest_bid") else bid, bid)
    )
    if source_time is not None:
        from datetime import datetime

        observed_time = (
            datetime.fromisoformat(source_time) if isinstance(source_time, str) else source_time
        )
        previous = protection.get("last_source_time")
        gap = (observed_time - datetime.fromisoformat(previous)).total_seconds() if previous else 0
        result["max_observation_gap_seconds"] = max(
            protection.get("max_observation_gap_seconds", 0), gap
        )
        result["observation_count"] = protection.get("observation_count", 0) + 1
        result.setdefault("first_observed_at", observed_time.isoformat())
    high = max(D(protection["highest_bid"]) if protection.get("highest_bid") else bid, bid)
    active = protection.get("trailing_active", False) or high >= (
        entry + config.trailing_activation_points
    )
    initial_stop = D(protection["initial_stop"])
    previous_stop = D(protection.get("stop_price", protection["initial_stop"]))
    trailing_stop = (
        D(protection["trailing_stop"]) if protection.get("trailing_stop") is not None else None
    )
    if active and high > config.trailing_distance_points:
        trailing_stop = ceiling_tick(high - config.trailing_distance_points, tick)
    result.update(
        highest_bid=str(high),
        trailing_active=active,
        trailing_stop=str(trailing_stop) if trailing_stop is not None else None,
    )
    floor_stop = (
        D(protection["profit_floor_stop"])
        if protection.get("profit_floor_stop") is not None
        else None
    )
    if quantity is not None:
        if entry_fees is None or charges is None:
            raise ValueError("Entry fees and charges are required for profit-lock observation")
        estimated_net = modeled_exit_net(entry, quantity, bid, entry_fees, tick, config, charges)
        result["estimated_net"] = str(estimated_net)
        if not result["profit_lock_active"] and not protection.get("exit_reason"):
            if estimated_net >= config.profit_lock_activation_net:
                floor_stop = profit_floor_stop(
                    entry,
                    quantity,
                    entry_fees,
                    config.profit_lock_floor_net,
                    tick,
                    config,
                    charges,
                )
                stop_before = max(
                    initial_stop,
                    previous_stop,
                    trailing_stop if trailing_stop is not None else initial_stop,
                )
                event = {
                    "stop_before": str(stop_before),
                    "stop_after": str(max(stop_before, floor_stop)),
                    "bid": str(bid),
                    "bid_size": bid_size,
                    "estimated_net": str(estimated_net),
                    "floor_net": str(config.profit_lock_floor_net),
                    "activation_net": str(config.profit_lock_activation_net),
                    "slippage_ticks": config.slippage_ticks,
                    "cost_model": _cost_model(config),
                    "source_time": _source_time_text(source_time),
                }
                if floor_stop >= bid:
                    result["exit_reason"] = "PROFIT_FLOOR_UNREPRESENTABLE"
                    result["new_events"] = [{"kind": "PROFIT_FLOOR_UNREPRESENTABLE", **event}]
                    floor_stop = None
                else:
                    result["profit_lock_active"] = True
                    result["profit_floor_stop"] = str(floor_stop)
                    result["profit_lock_activation"] = event
                    result["new_events"] = [{"kind": "PROFIT_LOCK_ACTIVATED", **event}]
    stop = max(
        initial_stop,
        previous_stop,
        trailing_stop if trailing_stop is not None else initial_stop,
        floor_stop if floor_stop is not None else initial_stop,
    )
    result["stop_price"] = str(stop)
    if source_time is not None and stop != previous_stop:
        history = [
            *protection.get("stop_history", []),
            {
                "source_time": observed_time.isoformat(),
                "stop_price": str(stop),
                "trailing_stop": result.get("trailing_stop"),
                "profit_floor_stop": result.get("profit_floor_stop"),
            },
        ]
        result["stop_history_omitted"] = protection.get("stop_history_omitted", 0) + max(
            0, len(history) - 256
        )
        result["stop_history"] = history[-256:]
    reason = None
    if bid <= stop:
        if (
            floor_stop is not None
            and stop == floor_stop
            and floor_stop
            >= max(
                initial_stop,
                previous_stop,
                trailing_stop if trailing_stop is not None else initial_stop,
            )
        ):
            reason = "PROFIT_LOCK_STOP"
        else:
            reason = "TRAILING_STOP" if stop > initial_stop else "INITIAL_STOP"
    elif protection.get("target_price") is not None and bid >= D(protection["target_price"]):
        reason = "TARGET"
    result["exit_reason"] = result.get("exit_reason") or protection.get("exit_reason") or reason
    return result


def mandatory_exit_reason(
    opened_at, now, config, window, *, technical=False, operator=False, discretionary=None
):
    """Forced-exit precedence shared by primary and hypothetical shadow monitoring."""
    local = now.astimezone(IST)
    if (now - opened_at).total_seconds() >= config.max_hold_minutes * 60:
        return "MAX_HOLD"
    if config.technical_exit and technical:
        return "TECHNICAL_INVALIDATION"
    if (
        local.time().replace(tzinfo=None) >= config.exit_by
        or (window and now >= window[1] - SESSION_EXIT_BUFFER)
        or not window
    ):
        return "SESSION_EXIT"
    if operator:
        return "OPERATOR_CLOSE"
    return discretionary


def momentum_weakening(previous_snapshot, snapshot, direction):
    if direction not in (-1, 1):
        return False
    try:
        if (
            not previous_snapshot.get("end")
            or not snapshot.get("end")
            or snapshot["end"] <= previous_snapshot["end"]
        ):
            return False
        previous_macd, current_macd = previous_snapshot.get("macd"), snapshot.get("macd")
        previous_price, current_price = (
            D(str(previous_snapshot["price"])),
            D(str(snapshot["price"])),
        )
        if not isinstance(previous_macd, dict) or not isinstance(current_macd, dict):
            return False
        previous_histogram = previous_macd.get("histogram")
        current_histogram = current_macd.get("histogram")
        if previous_histogram is None:
            previous_histogram = D(str(previous_macd["line"])) - D(str(previous_macd["signal"]))
        else:
            previous_histogram = D(str(previous_histogram))
        if current_histogram is None:
            current_histogram = D(str(current_macd["line"])) - D(str(current_macd["signal"]))
        else:
            current_histogram = D(str(current_histogram))
        if not all(
            value.is_finite()
            for value in (previous_price, current_price, previous_histogram, current_histogram)
        ):
            return False
        return (
            D(direction) * (current_histogram - previous_histogram) < 0
            and D(direction) * (current_price - previous_price) < 0
        )
    except (ArithmeticError, KeyError, TypeError, ValueError):
        return False


def early_booking_exit(
    protection,
    entry,
    bid,
    tick,
    config,
    *,
    quantity,
    entry_fees,
    charges,
    momentum_weak,
):
    if protection.get("profit_lock_active") or not momentum_weak:
        return None
    highest_bid = protection.get("highest_bid")
    if highest_bid is None:
        return None
    highest_bid = D(str(highest_bid))
    entry, bid = D(str(entry)), D(str(bid))
    if highest_bid <= entry:
        return None
    if modeled_exit_net(entry, quantity, bid, entry_fees, tick, config, charges) < (
        config.early_booking_min_net
    ):
        return None
    if highest_bid - bid < config.early_booking_retrace_fraction * (highest_bid - entry):
        return None
    return "EARLY_PROFIT_BOOKING"


# Live stop modification is gated to Phase 5 and must reconcile acknowledgements.
