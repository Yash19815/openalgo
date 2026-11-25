# Deterministic policy and feasibility evidence

Synthetic premiums only. No observed market availability or profitability claim.
Lot size 65 and tick 0.05 are an explicit exchange-document scenario; runtime still requires dated master metadata.
The candidate tariff remains inactive. Both charge models include brokerage and estimated costs.

## Confidence proposals (inactive)

| Age | Policy | Score | ST points | MACD points | Lot permission | Target fraction |
|---|---|---|---|---|---|---|
| 0 | fixed-v1 | 58.333333 | 16.66666667 | 11.0 | 2 | 0.1291666665 |
| 0 | configured-st-v2-proposal | 56.666667 | 15.0 | 11.0 | 2 | 0.1283333335 |
| 0 | version-pinned-v2-proposal | 58.333333 | 16.66666667 | 11.0 | 2 | 0.1291666665 |
| 0 | historical-macd-v2-proposal | 58.333333 | 16.66666667 | 11.0 | 2 | 0.1291666665 |
| 1 | fixed-v1 | 55.0 | 16.66666667 | 7.66666667 | 2 | 0.1275 |
| 1 | configured-st-v2-proposal | 53.333333 | 15.0 | 7.66666667 | 2 | 0.1266666665 |
| 1 | version-pinned-v2-proposal | 55.0 | 16.66666667 | 7.66666667 | 2 | 0.1275 |
| 1 | historical-macd-v2-proposal | 55.833333 | 16.66666667 | 8.5 | 2 | 0.1279166665 |
| 2 | fixed-v1 | 51.666667 | 16.66666667 | 4.33333333 | 2 | 0.1258333335 |
| 2 | configured-st-v2-proposal | 50.0 | 15.0 | 4.33333333 | 2 | 0.125 |
| 2 | version-pinned-v2-proposal | 51.666667 | 16.66666667 | 4.33333333 | 2 | 0.1258333335 |
| 2 | historical-macd-v2-proposal | 53.333333 | 16.66666667 | 6.0 | 2 | 0.1266666665 |

## Lot boundaries

| Score | Lots | Nominal target | Tick target at entry 30.05 |
|---|---|---|---|
| 39.999999 | 1 | 0.1199999995 | 33.70 |
| 40 | 2 | 0.12 | 33.70 |
| 40.000001 | 2 | 0.1200000005 | 33.70 |
| 69.999999 | 2 | 0.1349999995 | 34.15 |
| 70 | 3 | 0.135 | 34.15 |
| 70.000001 | 3 | 0.1350000005 | 34.15 |

## Feasible ask ranges on a 0.50 grid

Spread 0.05 and one adverse tick per entry/exit. Other spreads and slippage are in the JSON.

| Charge model | Score | Lots | Min ask | Max ask | Feasible points |
|---|---|---|---|---|---|
| ACTIVE_CONFIGURED_2026_ESTIMATE | 39.999999 | 1 | 52 | 63.5 | 24 |
| ACTIVE_CONFIGURED_2026_ESTIMATE | 39.999999 | 2 | None | None | 0 |
| ACTIVE_CONFIGURED_2026_ESTIMATE | 39.999999 | 3 | None | None | 0 |
| ACTIVE_CONFIGURED_2026_ESTIMATE | 40 | 1 | 52 | 63.5 | 24 |
| ACTIVE_CONFIGURED_2026_ESTIMATE | 40 | 2 | 26 | 31.5 | 12 |
| ACTIVE_CONFIGURED_2026_ESTIMATE | 40 | 3 | None | None | 0 |
| ACTIVE_CONFIGURED_2026_ESTIMATE | 69.999999 | 1 | 46 | 63.5 | 36 |
| ACTIVE_CONFIGURED_2026_ESTIMATE | 69.999999 | 2 | 23 | 31.5 | 18 |
| ACTIVE_CONFIGURED_2026_ESTIMATE | 69.999999 | 3 | None | None | 0 |
| ACTIVE_CONFIGURED_2026_ESTIMATE | 70 | 1 | 46 | 63.5 | 36 |
| ACTIVE_CONFIGURED_2026_ESTIMATE | 70 | 2 | 23 | 31.5 | 18 |
| ACTIVE_CONFIGURED_2026_ESTIMATE | 70 | 3 | 15.5 | 21 | 12 |
| ACTIVE_CONFIGURED_2026_ESTIMATE | 100 | 1 | 42 | 63.5 | 44 |
| ACTIVE_CONFIGURED_2026_ESTIMATE | 100 | 2 | 21 | 31.5 | 22 |
| ACTIVE_CONFIGURED_2026_ESTIMATE | 100 | 3 | 14 | 21 | 15 |
| HISTORICAL_3_2_COST_COMPARATOR | 39.999999 | 1 | 52 | 64 | 25 |
| HISTORICAL_3_2_COST_COMPARATOR | 39.999999 | 2 | None | None | 0 |
| HISTORICAL_3_2_COST_COMPARATOR | 39.999999 | 3 | None | None | 0 |
| HISTORICAL_3_2_COST_COMPARATOR | 40 | 1 | 52 | 64 | 25 |
| HISTORICAL_3_2_COST_COMPARATOR | 40 | 2 | 26 | 31.5 | 12 |
| HISTORICAL_3_2_COST_COMPARATOR | 40 | 3 | None | None | 0 |
| HISTORICAL_3_2_COST_COMPARATOR | 69.999999 | 1 | 46 | 64 | 37 |
| HISTORICAL_3_2_COST_COMPARATOR | 69.999999 | 2 | 23 | 31.5 | 18 |
| HISTORICAL_3_2_COST_COMPARATOR | 69.999999 | 3 | None | None | 0 |
| HISTORICAL_3_2_COST_COMPARATOR | 70 | 1 | 46 | 64 | 37 |
| HISTORICAL_3_2_COST_COMPARATOR | 70 | 2 | 23 | 31.5 | 18 |
| HISTORICAL_3_2_COST_COMPARATOR | 70 | 3 | 15.5 | 21 | 12 |
| HISTORICAL_3_2_COST_COMPARATOR | 100 | 1 | 41.5 | 64 | 46 |
| HISTORICAL_3_2_COST_COMPARATOR | 100 | 2 | 21 | 31.5 | 22 |
| HISTORICAL_3_2_COST_COMPARATOR | 100 | 3 | 14 | 21 | 15 |
| INACTIVE_ANGEL_2026_CANDIDATE | 39.999999 | 1 | 52 | 63.5 | 24 |
| INACTIVE_ANGEL_2026_CANDIDATE | 39.999999 | 2 | None | None | 0 |
| INACTIVE_ANGEL_2026_CANDIDATE | 39.999999 | 3 | None | None | 0 |
| INACTIVE_ANGEL_2026_CANDIDATE | 40 | 1 | 52 | 63.5 | 24 |
| INACTIVE_ANGEL_2026_CANDIDATE | 40 | 2 | 26 | 31.5 | 12 |
| INACTIVE_ANGEL_2026_CANDIDATE | 40 | 3 | None | None | 0 |
| INACTIVE_ANGEL_2026_CANDIDATE | 69.999999 | 1 | 46 | 63.5 | 36 |
| INACTIVE_ANGEL_2026_CANDIDATE | 69.999999 | 2 | 23 | 31.5 | 18 |
| INACTIVE_ANGEL_2026_CANDIDATE | 69.999999 | 3 | None | None | 0 |
| INACTIVE_ANGEL_2026_CANDIDATE | 70 | 1 | 46 | 63.5 | 36 |
| INACTIVE_ANGEL_2026_CANDIDATE | 70 | 2 | 23 | 31.5 | 18 |
| INACTIVE_ANGEL_2026_CANDIDATE | 70 | 3 | 15.5 | 21 | 12 |
| INACTIVE_ANGEL_2026_CANDIDATE | 100 | 1 | 42 | 63.5 | 44 |
| INACTIVE_ANGEL_2026_CANDIDATE | 100 | 2 | 21 | 31.5 | 22 |
| INACTIVE_ANGEL_2026_CANDIDATE | 100 | 3 | 14 | 21 | 15 |

The full JSON retains rejected candidate reasons and admitted risk/fee/protection values.
Range endpoints are grid results, not proofs that every tick between them passes. Tick-rounded targets can create holes.
Admission additionally requires calendar, signal, PCR, metadata, capital, ledger, entry-count and safety gates.
No representative authorized market recording was supplied to this analysis.
