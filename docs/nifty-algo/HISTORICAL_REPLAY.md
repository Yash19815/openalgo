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

## Execution comparison and fidelity gates

Quote-only recordings retain evidence inspection. Inspection reports
actual samples, per-token gaps, executable bid/ask coverage and split counts.
It labels results QUOTE_EVIDENCE_ONLY and refuses financial returns for all
three variants: A without profit lock, B with current protection, and C with
research-only settings. Their definitions do not imply simulated performance.

Full execution requires synchronized futures, historical PCR, point-in-time
metadata and candidate universe, bid/ask/depth, fee/fill assumptions and adequate
protection price coverage. Those inputs are not established by current datasets.
The separate financial replay engine is implemented for complete typed evidence.
This does not establish that a genuine dataset currently satisfies those gates.

`FRAME` observations freeze completed, same-future one-minute OHLCV, dated PCR
and its availability, identified native spot, option universe and metadata,
cached quotes/depth/volume/OI, available Greeks, approved calendar/session
identities, configuration/selector identities and the recorded decision. Completed
5/15-minute candles are derived using the production aggregator. Recorded
decisions explain past behavior; production Rules recompute replay signals.
`QUOTE` observations advance the causal clock. `LEDGER` observations record
actual PAPER fills, fees and protection without making those outcomes replay
authority. Source times and receipt/availability times remain separate.

The engine reuses Rules, Resolver, entry risk, Decimal costs, sizing, protection,
mandatory exits and early-booking evidence. It enforces the pinned strategy's
₹20,000 seed, one primary fill per session, ATM/ITM, lot/capital constraints,
10:30–14:45 entry window, 45-minute hold, mandatory exit, planned ₹400 loss,
₹350 projected reward, monthly latches and next-eligible-session loss cooldown.
A disables only the additional profit lock. B uses current protection. C allows
only research indicator overrides; risk, costs and execution policy cannot vary.

All variants consume the identical availability-ordered, digest-verified tape.
Each chronological TRAIN/VALIDATION/TEST partition is an independent trial with
₹20,000; earlier evidence supplies warm-up only. Internal boundaries cannot divide
an eligible trading session. Partition returns are not one continuous account.
Full displayed depth is required for fills after configured latency and slippage;
partial fills are not modeled. A displayed depth observation is consumed once
per side/source timestamp. There is no claim of historical queue priority.

Future input, identity mismatch, stale prices, unsupported selector policy,
unobserved exposure gaps, missing completed-candle protection frames or an open
operation at a split end prevent financial output. Unsupported fields are null,
never zero performance. Rejection codes and missing evidence remain visible.
Recorded samples do not establish continuous market extrema or actual fillability.

The pure `signal_study` function reuses completed-candle production rules and
optional dated PCR observations with explicit availability. Warm-up bars can
precede the study interval. Out-of-order candles/PCR and missing availability
evidence are rejected. Missing, stale or incomplete PCR yields partial indicator
research, not a five-indicator backtest. Native capture, imported typed PCR and
the saved execution workflow use the same typed evidence gates. Arbitrary options OHLC
cannot satisfy them. Existing signal-only studies remain explicitly non-financial.

## Comparison workflow

POST `/api/nifty-algo/research/comparisons` pins one to twenty sealed owned
recordings with `{id,count,content_sha256}`, a configuration, aware `train_end`
and `validation_end`, and `confirm=DEFINE_RESEARCH_ONLY`. The source configurations
must match. It creates an immutable definition; it does not run a backtest in Flask.
POST `/research/experiments/<id>/execution` with `confirm=REPLAY_RESEARCH_ONLY`
queues the owned job. GET that path reads the hash-verified result/status.
All paths are under `/api/nifty-algo`; writes require session and CSRF.

Run the explicit, isolated worker with existing environment and dependencies:

```shell
uv run --no-sync python -m services.nifty_algo.replay_worker --user YOUR_USERNAME
```

`--once` processes at most one job. Expired calculation claims can be recomputed
deterministically after restart; stale workers cannot overwrite a newer result.
Neither the protection scheduler nor a request thread calculates financial replay.
Results include definition, dataset, source and configuration hashes. Hashes prove
identity and corruption detection, not provider authenticity. The existing Replay
Lab displays A/B/C side by side. Multi-session bundles use the isolated worker;
individual recordings retain raw evidence inspection and causal playback.

## Recording and storage

Existing native capture is opt-in, cache-only, lease-fenced and bounded by
record count, encoded bytes, metadata scope and per-cycle time. Recorder failure
does not authorize trading or weaken protection. Experiments remain limited to
50 per owner, 1 MiB per definition and 1 MiB per inspection result. Source
recordings retain their existing 10,000-observation/16 MiB ceiling.

Explicit owner-scoped archival writes a bounded, verified immutable JSON bundle
before retiring only that recording's observation/sample rows. It preserves its
manifest and every experiment identity. Reads and replay verify archived bytes;
restore verifies the full digest chain before one transaction restores rows.
Interrupted writes leave original DB evidence intact. An archive error never
silently discards evidence. At most twenty recordings remain active and 1,000
manifest identities remain catalogued; quota exhaustion blocks further capture.
Archives are at most 20 MiB and must be backed up with DB and encryption keys.

The existing Replay UI exposes explicit archive, download and restore. POST
`/research/recordings/<id>/archive` requires `ARCHIVE_SEALED_EVIDENCE`; POST
`.../restore` requires `RESTORE_ARCHIVED_EVIDENCE`. GET `.../archive` downloads
verified owned bytes and GET `/research/recordings/archives` lists archived
manifests. There is no age-based deletion of financial or safety evidence.

Native recording remains explicit and lease-fenced after restart. Cache gaps,
record/byte quotas and partial coverage are reported rather than replaced with
invented prices. Genuine Angel One coverage, expired-options evidence and
executable historical coverage still require external validation. No provider
capability is assumed from deterministic fixture tests.
