"""Deterministic research strength, never a calibrated win probability."""

from decimal import Decimal
from math import isfinite


def _unit(value):
    if not isfinite(value):
        raise ValueError("Nonfinite confidence input")
    return max(0.0, min(1.0, value))


def target_fraction(score, config):
    value = Decimal(str(score))
    if not value.is_finite() or not 0 <= value <= 100:
        raise ValueError("Confidence must be finite and between 0 and 100")
    return config.target_min + (config.target_max - config.target_min) * value / 100


def signal_strength(snapshot, higher, pcr, direction, config):
    """Call only after every mandatory gate passes. Normalize before weighting.

    Equal weights are initial research assumptions. ATR normalizes momentum
    and trend distance; VWAP uses its configured extension bound; PCR uses a
    relative distance from the directional sentiment threshold.
    """
    if direction not in (-1, 1) or pcr is None:
        raise ValueError("Qualifying direction and verified PCR required")
    st, macd, adx = (snapshot[key] for key in ("supertrend", "macd", "adx"))
    atr = st["atr"]
    if not isfinite(atr) or atr <= 0 or higher["supertrend"]["direction"] != direction:
        raise ValueError("Valid ATR and confirmed direction required")
    distance = abs(snapshot["price"] - snapshot["vwap"]) / snapshot["vwap"] * 10000
    threshold = config.pcr_bull if direction == 1 else config.pcr_bear
    sentiment = (pcr.value - threshold) if direction == 1 else (threshold - pcr.value)
    measurements = {
        "supertrend": (
            _unit(st["duration"] / 10) * 0.5 + _unit(abs(st["distance"]) / atr / 3) * 0.5,
            "Confirmed trend duration / 10 and ATR-normalized distance / 3",
        ),
        "macd": (
            _unit(
                1
                - macd["cross_age"]
                / (
                    3
                    if config.confidence_method == "five-indicator-v2-pinned"
                    else config.crossover_freshness + 1
                )
            )
            * 0.5
            + _unit(direction * macd["histogram"] / atr) * 0.5,
            "Crossover recency and direction-aligned histogram / ATR",
        ),
        "vwap": (
            _unit(1 - distance / config.vwap_max_bps),
            "Directional gate passed; smaller extension receives greater strength",
        ),
        "adx": (
            _unit((adx["adx"] - config.adx_min) / max(1, 100 - config.adx_min)),
            "Trend strength above configured ADX threshold, normalized to 100",
        ),
        "pcr": (
            _unit(sentiment / threshold),
            "Verified sentiment margin / directional PCR threshold",
        ),
    }
    contributions = {
        key: {
            "normalized": round(value, 8),
            "weight": 0.2,
            "points": round(value * 20, 8),
            "explanation": explanation,
        }
        for key, (value, explanation) in measurements.items()
    }
    score = round(sum(row["points"] for row in contributions.values()), 6)
    return {
        "method": config.confidence_method,
        "normalization": {
            "supertrend_duration_bars": 10,
            "supertrend_distance_atr": 3,
            "macd_recency_denominator": 3
            if config.confidence_method == "five-indicator-v2-pinned"
            else config.crossover_freshness + 1,
        },
        "score": score,
        "contributions": contributions,
        "calibrated_probability": False,
        "target_fraction": str(target_fraction(score, config)),
    }
