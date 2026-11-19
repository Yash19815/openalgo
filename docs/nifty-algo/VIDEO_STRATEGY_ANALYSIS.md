# Video strategy evidence

Reviewed on 19 November 2026. The original watch page and Hindi timed-text endpoint could not be retrieved. The secondary summary was readable, but its transcript tab failed. Primary footage, subtitles and exact teaching remain unverified. No entry below has `VERIFIED_FROM_VIDEO` status. [Original video](https://www.youtube.com/watch?v=94Vph1miSYg), [Hindi timed-text attempt](https://www.youtube.com/api/timedtext?v=94Vph1miSYg&lang=hi), [Secondary summary](https://videohighlight.com/v/94Vph1miSYg)

## Secondary evidence

The following brief paraphrases summarize the secondary source. Timestamps identify claims requiring original-footage review.

| Concept | Unverified timestamps | Secondary interpretation | Remaining uncertainty |
| --- | --- | --- | --- |
| SuperTrend | 00:43, 01:28, 02:12, 02:34, 02:58 | Follow trend and confirm candles. | ATR settings and exact candle/volume rule. |
| MACD | 05:35, 06:06, 06:27, 07:36, 08:43 | Directional crossover, zero line, 12/26/9 settings. | Original parameter instruction and crossover persistence. |
| VWAP | 08:19, 09:04, 11:41, 13:06 | Consider distance from VWAP. | Source instrument and extension threshold. |
| ADX | 13:55, 14:15, 15:02 | Strength around 25 and 50. | Period and exact confirmation rule. |
| PCR | 16:33, 19:39, 20:01, 20:25 | Values above 1.5 and below 1 inform selling views. | OI versus volume, expiry scope and meaning of selling. |
| Timeframes | 03:20, 04:25, 06:50 | Discusses 5m and 15m charts. | Exact multi-timeframe gate. |

The summary associates MACD histogram with volume. The implementation must calculate histogram as MACD line minus signal line. All combined automation conditions retain `RESEARCH_ASSUMPTION` status. [Secondary summary](https://videohighlight.com/v/94Vph1miSYg)

## Calculation and automation contracts

| Rule | Inputs and outputs | Candidate confirmation | Exit use | Classification |
| --- | --- | --- | --- | --- |
| R-ST | Completed futures OHLC, ATR period and multiplier. Output line, direction, ATR and confirmed flip. | CE requires bullish close/line relation. PE requires bearish relation. Optional completed 15m agreement. | Configurable confirmed reversal. | Formula/API `VERIFIED_FROM_DOCUMENTATION` after native parity tests. Parameters and gate `RESEARCH_ASSUMPTION`. |
| R-MACD | Futures closes. Output fast-minus-slow EMA, signal EMA, difference and crossover age. | Directional crossover within configured age and aligned histogram. Optional zero-line gate. | Optional momentum invalidation only when configured. | Formula/API `VERIFIED_FROM_DOCUMENTATION`. Default 12/26/9 and gate `RESEARCH_ASSUMPTION`. |
| R-VWAP | Matching futures OHLCV and effective session. Output cumulative weighted price, distance and instrument identity. | Trend-side price within configured extension. | No standalone reversal assumption. | Formula `VERIFIED_FROM_DOCUMENTATION`. Instrument choice and distance gate `RESEARCH_ASSUMPTION`. |
| R-ADX | Futures high/low/close and Wilder period. Output ADX, +DI and -DI. | Configured strength, optional DI agreement. | Never substitutes for protective risk exit. | Formula/API `VERIFIED_FROM_DOCUMENTATION`. Threshold/gate `RESEARCH_ASSUMPTION`. |
| R-PCR | Complete dated CE/PE universe for one expiry and observed OI or volume. Output put sum divided by call sum, oldest source time and coverage. | Explicit selected definition and configurable sentiment gate. | No standalone exit. | Ratio definition `VERIFIED_FROM_DOCUMENTATION`. Sentiment hypothesis `RESEARCH_ASSUMPTION`. |

The documentation references are the local OpenAlgo indicator files under `docs/prompt/indicators/`, particularly trend, momentum, hybrid and volume references. PCR implementation behavior is audited against `services/oi_tracker_service.py`. Native output conventions require tests before reuse. User edits produce immutable configuration versions classified `USER_CONFIGURATION`, preserving the original assumption’s provenance.

## Verification work still open

- Review original footage or authorized subtitles and record exact wording, parameter screens and source timestamps.
- Resolve the spot/futures/chart instrument used in each original example.
- Resolve PCR universe, definition and interpretation without inferring a long-option trade from discussion of selling.
- Verify entry, confirmation and exit logic independently. A five-indicator conjunction, risk budget, execution latency and options selection are automation design choices.
- Preserve existing evidence status when rules change. A passing calculation test establishes calculation behavior, while source attribution requires source review.
