# Strategy assumptions and rule provenance

Version 2.0.0, 19 November 2026. The strategy is a research hypothesis, not a
calibrated probability model or a claim of historical profitability.

## Explicit user requirements

- Maximum initial stop distance: 8% of the confirmed simulated option fill; tighter is allowed.
- Trailing candidates: [1.5, 2.0]; effective distance: minimum, 1.5 option-premium price units.
- Profit target: a deterministic strength-sensitive percentage between 10% and 15% of entry premium.
- Five mandatory gates, completed 5-minute entries and 15-minute confirmation, independent risk approval, long NIFTY CE/PE only, isolated paper execution.

## Research defaults retained or introduced

Analysis uses the nearest eligible NIFTY future's actual OHLCV. Spot is a
separate strike reference. SuperTrend uses ATR 10 and multiplier 3; MACD uses
12/26/9 and a crossover within three completed entry bars; ADX uses Wilder 14
and minimum 25. Zero-line and DI confirmation remain configurable. Session
VWAP uses the same future's completed entry-candle typical price and volume;
missing session opening data or volume blocks execution. Maximum VWAP
extension is 80 basis points. At least 80 entry and higher-timeframe bars are
required. Histories never combine futures identities across rollover.

PCR defaults to OI, with volume explicitly selectable. Scope is one dated
expiry's full native master strike universe, not the 47-strike tracker window.
An optional `pcr_expiry` preserves a selected expiry; otherwise the nearest
eligible expiry is chosen. CE and PE must cover identical strikes. Maximum
source age is 90 seconds and maximum cross-leg skew is five seconds. Bullish
support starts at 1.5; bearish support is below 1.0. The midpoint does not pass.
The exact complete-market coverage and subscription entitlement require real
broker verification. Unknown master freshness or missing source fields block.

Default risk is 0.5% of equity including entry/exit costs and adverse ticks.
One position, one lot, three daily entries, 1.5% daily loss threshold and a
45-minute holding limit remain. Default entry window is 09:30–14:45 IST, with
exit requests from 15:10 or five minutes before an earlier native NFO close.
Special sessions and holidays come from OpenAlgo's calendar.

## Strength method: five-indicator-v1

Scoring runs only after every mandatory gate passes. Each component is clipped
to [0,1], receives weight 0.2 and contributes at most 20 points:

| Component | Normalized strength |
| --- | --- |
| SuperTrend | Half confirmed duration / 10, half absolute trend distance / (3 ATR) |
| MACD | Half crossover recency `1 - age/(freshness+1)`, half directional histogram / ATR |
| VWAP | `1 - abs(extension_bps)/configured_limit`; passing directional alignment is mandatory |
| ADX | `(ADX - minimum)/max(1,100-minimum)` |
| PCR | Directional margin beyond the qualifying threshold divided by that threshold |

Contributions retain normalized values, weights, points and explanations.
The sum, rounded to six decimals, is a strength score from 0 to 100.
Nominal target fraction is `target_min + (target_max-target_min)*score/100`.
Higher strength cannot increase size or relax risk. Invalid scoring rejects
entry. Tick rounding preserves target bounds; if no valid tick exists inside
them, entry is rejected. Both nominal and tick-adjusted target fractions are
retained with the trade.

Trailing activation at entry +1.5 premium points is an implementation
assumption, independently configurable. Entry 100 produces initial stop 92;
bid 101.50 arms the trail; eligible peak 106 gives stop 104.50; peak 110 gives
108.50. A falling bid never lowers protection. Thresholds round upward to
valid contract ticks. Gaps, latency, stale data and insufficient depth can
produce worse realized results or leave an exit unfilled.

Configured fees are deterministic research estimates, not a statement of
current statutory rates. Brokerage and transaction, GST, STT, stamp and SEBI
rates are versioned. Verify their applicable effective rates before forwarding
a real-market paper study. Costs are included in sizing, final admission and
journal P&L. No historical accuracy is inferred from synthetic fixtures.
