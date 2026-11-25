"""Quantify unchanged ST initialization against the actual installed SDK."""

import json
from pathlib import Path

from openalgo import ta
from openalgo.indicators import _backend

from services.nifty_algo.indicators import supertrend
from test.test_nifty_algo_sdk_241_parity import PATTERNS, arrays, fixture_bars


def main():
    rows = []
    for period, factor in ((10, 3), (20, 2)):
        for pattern in PATTERNS:
            bars = fixture_bars(pattern)
            ours = supertrend(bars, period, factor)
            values, directions = ta.supertrend(*arrays(bars)[:3], period, factor)
            first_flip = next((i for i, row in enumerate(ours) if row and row["flip"]), None)
            different = [i for i in range(79, len(bars)) if ours[i]["direction"] != -directions[i]]
            rows.append(
                {
                    "period": period,
                    "factor": factor,
                    "pattern": pattern,
                    "first_reversal_index": first_flip,
                    "disagreement_after_80": len(different),
                    "disagreement_indices": different,
                    "last_band_difference": abs(ours[-1]["value"] - float(values[-1])),
                }
            )
    root = Path(__file__).resolve().parents[1] / "docs/nifty-algo/evidence"
    root.mkdir(parents=True, exist_ok=True)
    (root / "initialization.json").write_text(
        json.dumps(
            {
                "provenance": "SYNTHETIC_SDK241_FIXTURES",
                "compiled_sdk_rust": _backend.HAVE_RUST,
                "bars_each": 525,
                "results": rows,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    lines = [
        "# SuperTrend initialization evidence",
        "",
        "Current close-versus-hl2 initialization is unchanged. SDK/TradingView-style bearish initialization is a comparison, not an activated policy.",
        "The 80-bar warmup does not guarantee initialization convergence. A ranging path can retain opposite directions indefinitely before a reversal.",
        "",
        "| Period/factor | Synthetic pattern | First reversal index | Disagreements at indices 79–524 | Final band difference |",
        "|---|---|---|---|---|",
    ]
    lines.extend(
        f"| {r['period']}/{r['factor']} | {r['pattern']} | {r['first_reversal_index']} | {r['disagreement_after_80']} | {r['last_band_difference']:.9f} |"
        for r in rows
    )
    (root / "initialization.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} initialization comparisons; SDK Rust={_backend.HAVE_RUST}")


if __name__ == "__main__":
    main()
