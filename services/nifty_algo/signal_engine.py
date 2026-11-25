from hashlib import sha256
from math import isfinite
from zoneinfo import ZoneInfo

from .confidence import signal_strength
from .fees import estimate_metadata
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
    # A missing broker candle is never repaired. A gap inside the session being
    # evaluated leaves its candles and session VWAP incomplete, so that series
    # is refused outright. A gap in an earlier session discards everything up
    # to it: only the verified continuous suffix after the latest gap is used,
    # and the R-WARMUP gate decides whether that suffix is long enough.
    gaps = [
        index + 1
        for index, (left, right) in enumerate(zip(known, known[1:], strict=False))
        if left.end != right.start
        and left.start.astimezone(local).date() == right.start.astimezone(local).date()
    ]
    if not gaps:
        return known
    suffix = known[gaps[-1] :]
    if suffix[0].start.astimezone(local).date() == known[-1].start.astimezone(local).date():
        return []
    return suffix


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
        # Age 0 is the latest completed entry candle. From strategy 3.2.0 the
        # configuration caps freshness at 2, so only the latest three completed
        # candles qualify; a stored 3.1.0 record replays with its own value.
        cross_age = momentum.get("cross_age") if momentum else None
        macd_ok = (
            bool(momentum)
            and momentum["cross_direction"] == direction
            and type(cross_age) is int
            and 0 <= cross_age <= config.crossover_freshness
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
        confidence = None
        if eligible:
            try:
                confidence = signal_strength(snap, h, pcr, direction, config)
            except (ValueError, TypeError, KeyError, ZeroDivisionError):
                gate("R-CONFIDENCE", False, "Confidence calculation unavailable or invalid", False)
                eligible = False
        bias = ("BULLISH" if direction == 1 else "BEARISH") if direction else "NO_TRADE"
        if eligible:
            bias = "STRONG_" + bias
        elif direction and not strong:
            bias = "NEUTRAL"
        if any(check["state"] == "UNAVAILABLE" for check in checks):
            bias = "DATA_UNAVAILABLE"
        stamp = bars[-1].end.isoformat() if bars else now.isoformat()
        indicator_states = {}
        for name, rule, value, signal_direction in (
            ("supertrend", "R-ST", st, direction),
            ("macd", "R-MACD", momentum, momentum.get("cross_direction") if momentum else None),
            ("vwap", "R-VWAP", vw, (1 if distance >= 0 else -1) if distance is not None else None),
            ("adx", "R-ADX", strength, direction if strong else 0),
            (
                "pcr",
                "R-PCR",
                pcr.value if valid_pcr else None,
                (1 if pcr.value >= config.pcr_bull else -1 if pcr.value < config.pcr_bear else 0)
                if valid_pcr
                else None,
            ),
        ):
            check = next(c for c in checks if c["rule"] == rule)
            indicator_states[name] = {
                "value": value,
                "timestamp": pcr.source_time.isoformat()
                if name == "pcr" and valid_pcr
                else snap.get("end"),
                "valid": check["state"] != "UNAVAILABLE",
                "gate": check["state"],
                "direction": signal_direction,
                "reason": None if check["state"] == "PASS" else check["detail"],
            }
        return {
            "decision_id": sha256(f"{token}:{stamp}:{config_id}".encode()).hexdigest(),
            "timestamp": now.isoformat(),
            "underlying": "NIFTY",
            "analysis_token": token,
            "timeframe": 5,
            "config_id": config_id,
            "effective_configuration": config.model_dump(mode="json"),
            "charge_model": estimate_metadata(config),
            "snapshot": snap,
            "higher": h,
            "pcr": pcr.model_dump(mode="json") if pcr else None,
            "vwap_distance_bps": distance,
            "bias": bias,
            "side": "CE" if direction == 1 else "PE" if direction else None,
            "eligible": eligible,
            "confidence": confidence,
            "confidence_score": confidence["score"] if confidence else None,
            "target_fraction": confidence["target_fraction"] if confidence else None,
            "indicator_states": indicator_states,
            "point_unit": config.point_unit,
            "checks": checks,
            "reasons": [c["rule"] + ": " + c["detail"] for c in checks if c["state"] != "PASS"],
            "contract": None,
            "risk": None,
            "final_action": "CANDIDATE" if eligible else "NO_TRADE",
            "rule_provenance": "RESEARCH_ASSUMPTION",
        }
