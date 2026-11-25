"""Inactive policy comparison. Production signal_strength remains unchanged."""

from copy import deepcopy

from .confidence import signal_strength, target_fraction

POLICIES = (
    "fixed-v1",
    "configured-st-v2-proposal",
    "version-pinned-v2-proposal",
    "historical-macd-v2-proposal",
)


def compare_strength(snapshot, higher, pcr, direction, config, policy):
    if policy not in POLICIES:
        raise ValueError("Unknown offline confidence proposal")
    result = deepcopy(signal_strength(snapshot, higher, pcr, direction, config))
    st, momentum = snapshot["supertrend"], snapshot["macd"]

    def unit(value):
        return max(0, min(1, value))

    length, factor = (
        (config.atr_period, config.atr_multiplier) if policy == POLICIES[1] else (10, 3)
    )
    denominator = (
        4
        if policy == POLICIES[3]
        else 3
        if policy == POLICIES[2]
        else config.crossover_freshness + 1
    )
    points = {
        "supertrend": unit(st["duration"] / length) * 10
        + unit(abs(st["distance"]) / st["atr"] / factor) * 10,
        "macd": unit(1 - momentum["cross_age"] / denominator) * 10
        + unit(direction * momentum["histogram"] / st["atr"]) * 10,
    }
    for key, value in points.items():
        result["contributions"][key]["points"] = round(value, 8)
        result["contributions"][key]["normalized"] = round(value / 20, 8)
    result["score"] = round(sum(row["points"] for row in result["contributions"].values()), 6)
    result["target_fraction"] = str(target_fraction(result["score"], config))
    result.update(policy=policy, active=False, production_method=config.confidence_method)
    return result
