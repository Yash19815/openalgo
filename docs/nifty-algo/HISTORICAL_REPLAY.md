# Historical Replay Lab

The lab consumes sealed recordings and immutable experiment definitions in
the existing Research workspace. It never calls broker order methods or writes
active strategy settings. Financial replay remains unavailable for incomplete
data; options OHLC is not a substitute for observed executable depth.

## Available controls

Define an owned experiment with pinned source count/hash and half-open UTC
TRAIN/VALIDATION/TEST splits. Select it in Historical Replay Lab. Save an
evidence-only inspection, set a UTC replay clock and step through pages.
Source time and receipt availability appear separately. A late quote is never
visible at its earlier source timestamp.

| API | Contract |
| --- | --- |
| GET `/api/nifty-algo/research/experiments/<id>/inspection` | Owned, hash-verified immutable result, or null |
| POST same path | CSRF plus `{"confirm":"INSPECT_EVIDENCE_ONLY"}`; no market input accepted |
| GET `/api/nifty-algo/research/experiments/<id>/replay` | `as_of` aware ISO timestamp and bounded integer `after`; at most 100 records |

Each request re-verifies sealed content against the experiment. No global
cursor registry, open DB connection or executable trading state is retained.
Results carry engine, definition, dataset and configuration identities. Changed
results cannot overwrite the immutable row. Corruption fails closed.

## Fidelity gates

The current native recorder contains option quote evidence. Inspection reports
actual samples, per-token gaps, executable bid/ask coverage and split counts.
It labels results QUOTE_EVIDENCE_ONLY and refuses financial returns for all
three variants: A without profit lock, B with current protection, and C with
research-only settings. Their definitions do not imply simulated performance.

Full execution requires synchronized futures, historical PCR, point-in-time
metadata and candidate universe, bid/ask/depth, fee/fill assumptions and adequate
protection price coverage. Those inputs are not established by current datasets.
The three-way execution simulator is therefore not implemented or certified.

The pure `signal_study` function reuses completed-candle production rules and
optional dated PCR observations with explicit availability. Warm-up bars can
precede the study interval. Out-of-order candles/PCR and missing availability
evidence are rejected. Missing, stale or incomplete PCR yields partial indicator
research, not a five-indicator backtest. A historical PCR importer and an
integrated saved signal-execution workflow remain unfinished.

## Recording and storage

Existing native capture is opt-in, cache-only, lease-fenced and bounded by
record count, encoded bytes, metadata scope and per-cycle time. Recorder failure
does not authorize trading or weaken protection. Experiments remain limited to
50 per owner, 1 MiB per definition and 1 MiB per inspection result. Source
recordings retain their existing 10,000-observation/16 MiB ceiling.

Automated archival/retention and full futures/PCR/decision recording remain
unfinished. Do not silently delete source evidence, unresolved incidents or
active-risk records. Back up feature data before deployment or archival work.
