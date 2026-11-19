# Strategy assumptions and rule provenance

Version 0.1.0, reviewed 19 November 2026. This register defines the initial research hypothesis. Runtime implementation and active settings are recorded in `IMPLEMENTATION_PLAN.md`. A value in this document does not claim a completed capability or measured profitability.

## Classification

`VERIFIED_FROM_VIDEO` requires direct footage or subtitle evidence. None is currently available. `VERIFIED_FROM_DOCUMENTATION` identifies a formula or service behavior established by the installed OpenAlgo documentation and code. `RESEARCH_ASSUMPTION` identifies an automation policy chosen for testing. `USER_CONFIGURATION` identifies an explicit saved override. Preserve source classification, configuration version and strategy version in each decision snapshot.

## Initial hypothesis

| Rule | Initial research setting | Classification |
| --- | --- | --- |
| Analysis identity | Nearest eligible NIFTY future supplies all price indicators and genuine traded volume. NIFTY spot remains separately labeled and supplies strike-selection reference. Reset warm-up on a futures roll. | RESEARCH_ASSUMPTION |
| R-ST | ATR 10 and multiplier 3. Completed close agrees with established SuperTrend direction. | RESEARCH_ASSUMPTION |
| R-MACD | EMA 12/26/9, recent directional crossover within three completed entry bars, aligned histogram. Zero-line and DI gates are optional. | RESEARCH_ASSUMPTION |
| R-ADX | Wilder period 14, minimum strength 25. Direction comes from other rules. | RESEARCH_ASSUMPTION |
| R-VWAP | Session typical-price VWAP of the same future. Maximum absolute extension 80 basis points. Missing genuine volume invalidates the session reading. | RESEARCH_ASSUMPTION |
| R-PCR | OI default, with separately selectable volume definition. Complete CE/PE coverage for an explicitly identified expiry. Bullish-supportive at or above 1.5, bearish-supportive below 1.0. Middle range blocks strict confluence. Maximum observation age 90 seconds. | RESEARCH_ASSUMPTION |
| R-MTF | Completed 5m entry and 15m trend confirmation. At least 80 completed bars in both series, with indicator seed checks. | RESEARCH_ASSUMPTION |
| R-FRESH | Entry evaluation within 30 seconds after bar close. Selected option quote age at most five seconds, measured from source time. | RESEARCH_ASSUMPTION |
| R-CONTRACT | Earliest eligible listed expiry, ATM default. Optional one listed strike ITM/OTM. Delta mode requires reliable synchronized Greeks. Avoid expiry-day entries initially. | RESEARCH_ASSUMPTION |
| R-LIQUIDITY | Positive uncrossed bid/ask, current contract metadata, size sufficient for permitted fill, configured volume and spread bounds. Initial max spread 150 basis points and minimum volume 1,000 units subject to verified feed units. | RESEARCH_ASSUMPTION |
| R-RISK | Virtual capital ₹1,00,000, per-trade planned risk 0.5% of equity, daily loss 1.5% of starting-day equity, one position, one lot per entry, three entries per session. Include conservative costs in sizing. Skip if one lot exceeds capital or budget. | RESEARCH_ASSUMPTION |
| R-EXIT | Premium stop 15%, target 30%, trail 10%, maximum holding 45 minutes. Optional confirmed SuperTrend reversal and underlying ATR invalidation at two entry ATRs. | RESEARCH_ASSUMPTION |
| R-TIME | New entries 09:30–14:45 IST. Exit requests from 15:10 IST, always bounded by effective NFO contract sessions and holidays. | RESEARCH_ASSUMPTION |
| R-EXECUTION | Ask-side buys, bid-side exits, configurable adverse ticks, latency, fees and pending expiry. Native Sandbox fill behavior must meet the documented execution contract before readiness. | RESEARCH_ASSUMPTION |

## Required invariants

PAPER_ONLY execution, NFO NIFTY CE/PE validation, long-only exposure, no averaging, no martingale, causal inputs, independent risk approval and confirmed-fill position state are user requirements. Configurations cannot enable live routing, uncovered sales or a bypass around these requirements.

Missing PCR scope, missing quote source time, stale data or unavailable indicators produce explicit unavailable checks. Do not substitute response creation time for exchange observation time or missing volume for zero. No signal-strength label authorizes an order by itself.

Use native `services/risk/` for shared price stop, target and trail evaluation. Underlying invalidation uses the underlying’s own points and ATR. Option stops use premium prices. A stop request cannot guarantee a fill during gaps or outages.

Research must label directional candle studies, option-premium replay and observed forward paper trading separately. Option-premium replay requires dated contracts and causal quotes or trades with explicit fill assumptions. Costs are effective-dated estimates. Record both realized and marked equity definitions. Completed test fixtures provide local verification only.

Restart recovery retains kill and daily lockout state, reconciles pending orders and confirmed Sandbox positions, and pauses entries until recovery succeeds. Changed configuration versions pause new entries and retain the entry configuration for existing exposure. Exits remain visibly pending until confirmed simulated fills reduce quantity to zero.
