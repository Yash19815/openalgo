# Confidence policy decision for strategy 3.3.0

Status: APPROVED by the owner on 2026-11-25 in this remediation session:
"Approve version-pinned ST /10, /3 and MACD /3 (recommended)."
Strategy 3.3.0 uses `five-indicator-v2-pinned`. Historical configurations retain
`five-indicator-v1` and their original inputs. Final test evidence is tracked in
the remediation register.

## Recommendation and mathematics

The owner approved a separately named, version-pinned method with SuperTrend duration /10,
ATR distance /3, and MACD recency denominator 3 for new configurations. Keep
the existing 3.1.0 and 3.2.0 methods unchanged. This preserves current default
3.2.0 arithmetic for identical indicator inputs, without making confidence
depend on a future tightening of crossover eligibility. The recorded approval
also covers new configurations with freshness 0 or 1, whose scores can change.

The ATR period is a smoothing horizon, not a mathematical definition of trend
duration strength. Replacing duration /10 with /20 doubles the saturation time
from 50 to 100 minutes on five-minute candles. Replacing ATR-distance /3 with
/2 changes the meaning of the distance contribution. Neither follows as a
mathematical necessity from adopting SuperTrend 20/2.

The proposed fixed denominators make their units explicit: ten completed entry
candles and three current Wilder ATRs. They do not make confidence a calibrated
probability. The indicator change itself can change ATR, direction, duration,
distance, eligibility, score and target. No promise of unchanged trade outcomes
is possible merely by retaining the confidence formula.

## Compared alternatives

1. `fixed-v1`: existing production arithmetic, ST /10 and /3, MACD
   `1-age/(crossover_freshness+1)`. Historical versions retain this method.
2. `configured-st-v2-proposal`: ST duration /configured ATR period and distance
   /configured multiplier; MACD remains relative to eligibility. Different
   mathematical meanings can offset each other or move lot/target boundaries.
3. `version-pinned-v2-proposal`: ST /10 and /3, MACD /3. Recommended for explicit
   approval, now recorded above. It equals historical 3.2.0 default arithmetic at freshness 2.
4. `historical-macd-v2-proposal`: ST /10 and /3, MACD /4. Restores the scores of
   historically eligible ages 0–2 from strategy 3.1.0, while age 3 still refuses.

The offline comparison cannot activate a proposal. The configuration validator
requires `five-indicator-v2-pinned` for 3.3.0 and v1 for historical versions.

## MACD age effects

The recency half contributes `10*(1-age/denominator)` points. The other half
(histogram / ATR, clipped) is unchanged for identical inputs.

| Age | Denominator 3 | Denominator 4 | Restore-/4 score change |
|---|---|---|---|
| 0 | 10 | 10 | 0 |
| 1 | 6.66666667 | 7.5 | +0.83333333 |
| 2 | 3.33333333 | 5 | +1.66666667 |

A former score of 40.5 at age 2 became 38.833333 under the 3.2.0 denominator,
crossing the two-lot permission boundary. A former 70.5 became 68.833333,
crossing the three-lot boundary. Restoring /4 reverses those movements for
identical component inputs. Age 3 remains ineligible in new configurations.

Lot permissions change inclusively at 40 and 70. The nominal target is
`0.10 + 0.0005*score`; a +1.66666667 score movement changes the fraction by
0.000833333335. Tick rounding can hide or amplify a small nominal movement.
Actual lots remain subject to every risk, cash, liquidity and execution gate.

## Reproducible evidence

Run `.venv/Scripts/python.exe -m scripts.nifty_remaining_analysis` from the root.
[Numerical tables](evidence/remaining-analysis.md) and
[full deterministic inputs/results](evidence/remaining-analysis.json) contain
ages 0–2, all four proposals, scores immediately below/at/above 40 and 70,
tick-rounded targets and actual `plan_entry` feasibility results. The fixtures
are synthetic, use explicit 65-unit lots and 0.05 ticks, and claim no observed
market availability. Candidate fees remain inactive and distinctly labelled.

Tests: `test_nifty_algo_confidence_comparison.py`,
`test_nifty_algo_macd_window.py`, and the historical SDK parity suite. Recorded
charges, balances, decisions, recordings and experiments are never recomputed
in place. Comparisons produce new artifacts, not replacements for evidence.

## Decision recorded

The owner chose the recommended version-pinned method for new configurations.
Historical /4 recency and configuration-dependent SuperTrend alternatives remain
inactive. No further confidence-policy decision is pending for this change.
