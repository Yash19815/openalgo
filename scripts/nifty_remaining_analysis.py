"""Reproduce offline policy and feasibility tables; no broker, DB or notification I/O.

Run: .venv/Scripts/python.exe -m scripts.nifty_remaining_analysis
Every premium is synthetic. The candidate tariff is inactive and unverified for
contract-note rounding. Current and historical estimates remain separately labelled.
"""

import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace

from services.nifty_algo.confidence import target_fraction
from services.nifty_algo.confidence_comparison import POLICIES, compare_strength
from services.nifty_algo.config import StrategyConfig
from services.nifty_algo.fees import candidate_breakdown, configured_legacy_total, configured_total
from services.nifty_algo.models import Instrument, Quote
from services.nifty_algo.protection import initial_protection
from services.nifty_algo.risk_manager import AccountRisk, plan_entry

NOW = datetime(2026, 11, 25, 5, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[1] / "docs" / "nifty-algo" / "evidence"


def charges_candidate(side, price, quantity, config):
    return candidate_breakdown(side, price, quantity, NOW.date())["total"]


def proposal(score, lots, premium, spread, ticks, charges=configured_total):
    config = StrategyConfig(max_lots=lots, slippage_ticks=ticks)
    item = Instrument(
        token="SYNTHETIC-65",
        symbol="SYNTHETIC-OPTION",
        exchange="NFO",
        kind="CE",
        expiry=NOW.date() + timedelta(days=6),
        strike=D(25000),
        lot_size=65,
        tick_size=D("0.05"),
        master_date=NOW.date(),
    )
    quote = Quote(
        token=item.token,
        source_time=NOW,
        received_time=NOW,
        ltp=premium,
        bid=premium - spread,
        ask=premium,
        bid_size=10000,
        ask_size=10000,
        volume=10000,
        oi=10000,
        provider="SYNTHETIC_ANALYSIS",
    )
    account = AccountRisk(D(20000), D(20000), D(20000), reconciled=True, entries_enabled=True)
    return plan_entry(account, [(item, quote)], config, score, charges, now=NOW)


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    config = StrategyConfig()
    comparisons = []
    st = {"atr": 10.0, "duration": 10, "distance": 20.0, "direction": 1}
    for age in (0, 1, 2):
        snap = {
            "supertrend": st,
            "macd": {"cross_age": age, "histogram": 1.0},
            "adx": {"adx": 40.0},
            "price": 100.0,
            "vwap": 100.0,
        }
        for policy in POLICIES:
            result = compare_strength(
                snap, {"supertrend": st}, SimpleNamespace(value=2.0), 1, config, policy
            )
            comparisons.append(
                {
                    "age": age,
                    "policy": policy,
                    "score": result["score"],
                    "st_points": result["contributions"]["supertrend"]["points"],
                    "macd_points": result["contributions"]["macd"]["points"],
                    "permitted_lots": sum(
                        t <= D(str(result["score"])) for t in config.lot_score_thresholds
                    ),
                    "target_fraction": result["target_fraction"],
                }
            )
    boundaries = []
    for value in ("39.999999", "40", "40.000001", "69.999999", "70", "70.000001"):
        score = D(value)
        entry = D("30.05")
        protection = initial_protection(
            entry, D("0.05"), config, {"score": score, "method": config.confidence_method}
        )
        for age in (0, 1, 2):
            adjusted = score + D(10) * D(age) / 12  # historical denominator 4 versus 3
            boundaries.append(
                {
                    "score": value,
                    "age": age,
                    "permitted_lots": sum(t <= score for t in config.lot_score_thresholds),
                    "target_fraction": str(target_fraction(score, config)),
                    "target_price_at_30_05": protection["target_price"],
                    "historical_denominator_score": str(adjusted),
                    "historical_denominator_lots": sum(
                        t <= adjusted for t in config.lot_score_thresholds
                    ),
                }
            )
    feasible, rejected_examples = [], []

    def historical_fees(side, price, quantity, config):
        return configured_legacy_total(
            side, price, quantity, StrategyConfig(strategy_version="3.2.0")
        )

    for schedule, charges in (
        ("ACTIVE_CONFIGURED_2026_ESTIMATE", configured_total),
        ("HISTORICAL_3_2_COST_COMPARATOR", historical_fees),
        ("INACTIVE_ANGEL_2026_CANDIDATE", charges_candidate),
    ):
        for score in (D("39.999999"), D(40), D("69.999999"), D(70), D(100)):
            for lots in (1, 2, 3):
                for spread in (D("0.05"), D("0.50"), D("1.00")):
                    for ticks in (0, 1, 2):
                        premiums, failures = [], Counter()
                        for step in range(4, 401):
                            premium = D(step) / 2
                            plan = proposal(score, lots, premium, spread, ticks, charges)
                            matching = next((r for r in plan.ranking if r["lots"] == lots), None)
                            if matching:
                                premiums.append(premium)
                            else:
                                reasons = [r for _, size, r in plan.rejections if size in (0, lots)]
                                failures.update(reasons or ["SCORE_LOT_LIMIT"])
                            if (
                                schedule.startswith("INACTIVE")
                                and score == 70
                                and spread == D("0.50")
                                and ticks == 1
                                and premium in (D(15), D(20), D(30), D(60), D(100))
                            ):
                                rejected_examples.append(
                                    {
                                        "lots": lots,
                                        "premium": str(premium),
                                        "selected_lots": plan.lots,
                                        "ranking": plan.ranking,
                                        "rejections": plan.rejections,
                                    }
                                )
                        feasible.append(
                            {
                                "schedule": schedule,
                                "score": str(score),
                                "lots": lots,
                                "spread": str(spread),
                                "slippage_ticks_each_side": ticks,
                                "grid_step": "0.50",
                                "minimum_ask": str(min(premiums)) if premiums else None,
                                "maximum_ask": str(max(premiums)) if premiums else None,
                                "feasible_grid_points": len(premiums),
                                "failure_counts": dict(failures),
                            }
                        )
    evidence = {
        "provenance": "DETERMINISTIC_SYNTHETIC_NOT_MARKET_OBSERVATIONS",
        "as_of": NOW.isoformat(),
        "lot_size": 65,
        "tick_size": "0.05",
        "configuration": config.model_dump(mode="json"),
        "confidence": comparisons,
        "boundaries": boundaries,
        "feasibility": feasible,
        "examples": rejected_examples,
    }
    (ROOT / "remaining-analysis.json").write_text(
        json.dumps(evidence, indent=2, default=str) + "\n", encoding="utf-8"
    )
    lines = [
        "# Deterministic policy and feasibility evidence",
        "",
        "Synthetic premiums only. No observed market availability or profitability claim.",
        "Lot size 65 and tick 0.05 are an explicit exchange-document scenario; runtime still requires dated master metadata.",
        "Current 3.3.0 estimates, historical cost comparisons and the inactive tariff candidate are separately labelled.",
        "",
        "## Confidence comparison (version-pinned option approved for 3.3.0)",
        "",
        "| Age | Policy | Score | ST points | MACD points | Lot permission | Target fraction |",
        "|---|---|---|---|---|---|---|",
    ]
    lines.extend(
        f"| {r['age']} | {r['policy']} | {r['score']} | {r['st_points']} | {r['macd_points']} | {r['permitted_lots']} | {r['target_fraction']} |"
        for r in comparisons
    )
    lines += [
        "",
        "## Lot boundaries",
        "",
        "| Score | Lots | Nominal target | Tick target at entry 30.05 |",
        "|---|---|---|---|",
    ]
    lines.extend(
        f"| {r['score']} | {r['permitted_lots']} | {r['target_fraction']} | {r['target_price_at_30_05']} |"
        for r in boundaries
        if r["age"] == 0
    )
    lines += [
        "",
        "## Feasible ask ranges on a 0.50 grid",
        "",
        "Spread 0.05 and one adverse tick per entry/exit. Other spreads and slippage are in the JSON.",
        "",
        "| Charge model | Score | Lots | Min ask | Max ask | Feasible points |",
        "|---|---|---|---|---|---|",
    ]
    lines.extend(
        f"| {r['schedule']} | {r['score']} | {r['lots']} | {r['minimum_ask']} | {r['maximum_ask']} | {r['feasible_grid_points']} |"
        for r in feasible
        if r["spread"] == "0.05" and r["slippage_ticks_each_side"] == 1
    )
    lines += [
        "",
        "The full JSON retains rejected candidate reasons and admitted risk/fee/protection values.",
        "Range endpoints are grid results, not proofs that every tick between them passes. Tick-rounded targets can create holes.",
        "Admission additionally requires calendar, signal, PCR, metadata, capital, ledger, entry-count and safety gates.",
        "No representative authorized market recording was supplied to this analysis.",
    ]
    (ROOT / "remaining-analysis.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        f"Wrote {len(comparisons)} confidence comparisons, {len(boundaries)} boundary cases and {len(feasible)} feasibility scenarios"
    )


if __name__ == "__main__":
    main()
