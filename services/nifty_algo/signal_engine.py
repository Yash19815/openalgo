from hashlib import sha256
from math import isfinite
from zoneinfo import ZoneInfo

from .indicators import adx, macd, supertrend, vwap


def completed_series(bars, now, token, timeframe):
    """Reject ambiguous series instead of sorting or silently repairing input."""
    known = [bar for bar in bars if bar.end <= now and bar.complete]
    if any(
        not all(isfinite(value) and value > 0 for value in (bar.open, bar.high, bar.low, bar.close))
        for bar in known
    ):
        return []
    if any(bar.token != token or bar.timeframe != timeframe for bar in known):
        return []
    if any(left.end > right.start for left, right in zip(known, known[1:], strict=False)):
        return []
    local = ZoneInfo("Asia/Kolkata")
    if any(
        left.end != right.start
        and left.start.astimezone(local).date() == right.start.astimezone(local).date()
        for left, right in zip(known, known[1:], strict=False)
    ):
        return []
    return known


def snapshot(bars, config):
    if not bars:
        return {}
    return {
        "supertrend": supertrend(bars, config.atr_period, config.atr_multiplier)[-1],
        "macd": macd(bars, config.macd_fast, config.macd_slow, config.macd_signal)[-1],
        "adx": adx(bars, config.adx_period)[-1],
        "vwap": vwap(bars, config.vwap_basis)[-1],
        "price": bars[-1].close,
        "end": bars[-1].end.isoformat(),
    }


class Rules:
    def evaluate(self, bars, higher, pcr, now, config, config_id, token):
        bars = completed_series(bars, now, token, 5)
        higher = completed_series(higher, now, token, 15)
        snap = snapshot(bars, config)
        h = snapshot(higher, config)
        checks = []

        def gate(rule, passed, detail, available=True):
            checks.append(
                {
                    "rule": rule,
                    "state": "UNAVAILABLE" if not available else "PASS" if passed else "FAIL",
                    "detail": detail,
                }
            )

        st, momentum, strength = snap.get("supertrend"), snap.get("macd"), snap.get("adx")
        direction = st["direction"] if st else 0
        gate(
            "R-WARMUP",
            len(higher) >= 80 and len(bars) >= 80,
            "80 completed higher and entry bars required",
        )
        gate(
            "R-FRESH",
            bool(bars) and 0 <= (now - bars[-1].end).total_seconds() <= 30,
            "Completed entry candle age ≤30s",
        )
        gate(
            "R-ST",
            bool(st) and (snap["price"] - st["value"]) * direction > 0,
            "Established SuperTrend and completed close",
            bool(st),
        )
        gate(
            "R-MTF",
            bool(h.get("supertrend"))
            and direction == h["supertrend"]["direction"]
            and (now - higher[-1].end).total_seconds() < 15 * 60 + 30,
            "Latest completed 15-minute SuperTrend agrees",
            bool(h.get("supertrend")),
        )
        macd_ok = (
            bool(momentum)
            and momentum["cross_direction"] == direction
            and momentum["cross_age"] is not None
            and momentum["cross_age"] <= config.crossover_freshness
            and momentum["histogram"] * direction > 0
        )
        if config.macd_zero_required:
            macd_ok = macd_ok and momentum["line"] * direction > 0
        gate("R-MACD", macd_ok, "Recent crossover, current momentum alignment", bool(momentum))
        strong = bool(strength) and strength["adx"] >= config.adx_min
        if config.di_confirmation and strength:
            strong = strong and (strength["plus_di"] - strength["minus_di"]) * direction > 0
        gate("R-ADX", strong, "Trend strength and optional DI", bool(strength))
        vw = snap.get("vwap")
        distance = (snap["price"] - vw) / vw * 10000 if vw else None
        gate(
            "R-VWAP",
            distance is not None
            and distance * direction >= 0
            and abs(distance) <= config.vwap_max_bps,
            "Same NIFTY future price/VWAP within extension limit",
            vw is not None,
        )
        valid_pcr = (
            pcr is not None
            and pcr.kind == config.pcr_kind
            and pcr.coverage == 1
            and pcr.verified
            and 0 <= (now - pcr.source_time).total_seconds() <= config.pcr_max_age
        )
        pcr_ok = valid_pcr and (
            pcr.value >= config.pcr_bull if direction == 1 else pcr.value < config.pcr_bear
        )
        gate(
            "R-PCR",
            pcr_ok,
            "Verified complete scoped PCR, matching definition and timestamp",
            valid_pcr,
        )
        if config.previous_candle_break:
            passed = len(bars) > 1 and (
                bars[-1].close > bars[-2].high if direction == 1 else bars[-1].close < bars[-2].low
            )
            gate("R-CANDLE", passed, "Previous completed candle high/low break")
        eligible = bool(direction) and all(c["state"] == "PASS" for c in checks)
        bias = ("BULLISH" if direction == 1 else "BEARISH") if direction else "NO_TRADE"
        if eligible:
            bias = "STRONG_" + bias
        elif direction and not strong:
            bias = "NEUTRAL"
        if any(check["state"] == "UNAVAILABLE" for check in checks):
            bias = "DATA_UNAVAILABLE"
        stamp = bars[-1].end.isoformat() if bars else now.isoformat()
        return {
            "decision_id": sha256(f"{token}:{stamp}:{config_id}".encode()).hexdigest(),
            "timestamp": now.isoformat(),
            "underlying": "NIFTY",
            "analysis_token": token,
            "timeframe": 5,
            "config_id": config_id,
            "snapshot": snap,
            "higher": h,
            "pcr": pcr.model_dump(mode="json") if pcr else None,
            "vwap_distance_bps": distance,
            "bias": bias,
            "side": "CE" if direction == 1 else "PE" if direction else None,
            "eligible": eligible,
            "checks": checks,
            "reasons": [c["rule"] + ": " + c["detail"] for c in checks if c["state"] != "PASS"],
            "contract": None,
            "risk": None,
            "final_action": "CANDIDATE" if eligible else "NO_TRADE",
            "rule_provenance": "RESEARCH_ASSUMPTION",
        }
