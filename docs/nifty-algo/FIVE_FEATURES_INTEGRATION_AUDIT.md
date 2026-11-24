# Five Features Integration Audit

> 24 November 2026 completion supersedes the software-gap descriptions below:
> typed evidence and isolated A/B/C replay, verified archive/restore, comparative
> ledger analytics, notification operations/private reports and the approved OI
> cap are implemented. See [current readiness](ADVANCED_FEATURES_READINESS.md)
> and [current test evidence](ADVANCED_FEATURES_TESTING.md). Linux verification
> is delegated to GitHub CI; earlier Linux and browser results are historical.

> Current continuation status (23 November 2026): weighted quantity proposals,
> trade inspection/exit sampling, causal evidence playback and a dedicated
> Discord REST bot are now integrated. Final NIFTY gates pass 744 tests on each
> OS; four subsequently added Discord cases pass in the focused 37-test suite
> on both OSes. Full requested acceptance remains incomplete. See
> [ADVANCED_FEATURES_READINESS.md](ADVANCED_FEATURES_READINESS.md) and the
> continuation evidence below. Earlier checkpoint statements remain historical.

## Baseline And Scope

The inspected baseline is commit `84b899ab9d91eaba4a12decff2c1474a29bb5d99`
on `feat/nifty-paper-trading-system`. The fetched origin branch matched that
commit. The user confirms that baseline development is complete. This work
extends the baseline; it does not replace the strategy or its accounting.

This is a source compatibility audit, not a certification of broker readiness.
No real orders, broker recovery exercise, Discord messages, or deployment have
been performed. Live must remain blocked by `trading_mode.LiveAdapterStub`.

Canonical baseline context remains in [ARCHITECTURE.md](ARCHITECTURE.md),
[SAFETY_MODEL.md](SAFETY_MODEL.md), [SETUP.md](SETUP.md) and
[READINESS_REPORT.md](READINESS_REPORT.md).

## Existing Capabilities And Extension Points

### Contract Selector

- `services/nifty_algo/contract_resolver.py` already derives the nearest valid
  expiry and listed ATM strike from current NIFTY metadata. It supports ATM,
  adjacent ITM, and trusted synchronized delta selection, never primary OTM.
- `liquid()` rejects token mismatches, stale quotes, invalid observation order,
  insufficient one-lot bid/ask depth, low volume and excessive spread.
- `runner.NiftyRunner._entry_candidates()` obtains native spot, instrument and
  quote observations. It passes candidate identity and moneyness evidence into
  `NiftyPaperExecutor.admit()`.
- `risk_manager.plan_entry()` selects a candidate and lot count within existing
  frozen risk, fee, capital and net-reward constraints. It remains the authority;
  ranking must never increase permitted size or relax any threshold.
- `paper_executor.process()` rereads depth and spot. `NiftyStore.fill()` validates
  the frozen token, tick, source timestamp, displayed size, costs, depth-use
  identity, current mode and risk under the user transaction lock.

Extend the resolver with explainable deterministic ranking and rejection
details, persist a bounded decision record, expose it through the existing
authenticated blueprint, and add a workspace panel. Preserve the configured
ATM/ITM preference. Do not derive strike spacing from a hardcoded interval or
invent Greeks. Admission and fill must revalidate the exact selected identity,
not reselect an unrelated token after approval.

### Execution Safety Center

- `database/nifty_algo_db.py` owns durable strategy revisions, killed/paused
  state, account reconciliation, order intents, fills, positions, protection,
  cooldowns, monthly locks, runner leases and events.
- `NiftyStore.change()` uses compare-and-set revisions. `admit_order()` checks
  mode, calendar approval, configuration identity, reservation limits and risk
  under `_lock()`. Idempotent intent lookup precedes new reservation.
- `services/nifty_algo/protection.py` is the deliberately isolated, pure Decimal
  NIFTY protection evaluator. It must not be copied into a new safety engine.
- `NiftyPaperExecutor.reconcile()` checks the isolated paper ledger. It does not
  establish live Angel One reconciliation or protective-order coverage.
- The existing risk panel and strategy controls remain reusable.

Add incident lifecycle, durable entry interlock and operator action evidence.
Acknowledgement must not resolve an incident or resume trading. Recovery must
require fresh reconciliation evidence and explicit operator confirmation. Check
the interlock under the same locks as admission and fill; a check only in the
browser or runner is insufficient. Entry blocking must never disable exits or
discard exposure. Live partial fills, broker ambiguity and session loss remain
hard blockers until the live adapter is implemented and independently verified.

### Advanced Analytics

- `NiftyStore.performance()` already aggregates the entire primary realized
  ledger rather than the journal page. Its equity basis is book cost, not MTM.
- `NiftyStore.trades()` returns a bounded journal with entry and exit contexts.
- `services/nifty_algo/analytics.py` validates financial reconciliation and
  aggregates partial exits by trade ID, equity curves, drawdown and groups.
- Durable shadow positions/ledger and research opportunities already exist.
- `services/nifty_algo/reports.py` and the reports panel already support durable
  daily/monthly PDF generation, bounded scanning and audited email delivery.

Extend queries and adapters rather than create a second ledger. Use full
selected-period trade data for aggregates; paginate detail independently.
Expose costs, expectancy, holding time, moneyness, strength/contributions,
slippage and fill quality only where durable evidence exists. Missing evidence
must be null with a reason, not zero. Keep realized, marked unrealized,
hypothetical shadow, actual-trade mirror and research series separate. Use
Decimal for financial calculations and strings at JSON/export boundaries.

### Replay And Backtesting

- `services/nifty_algo/research.py` already supplies signal studies, walk-forward
  windows and observed native-history validation. It bounds minute rows at
  10,000, validates chronological UTC minute timestamps, rejects duplicates and
  future rows, and checks native session windows.
- `options_replay()` currently refuses unsupported options execution replay.
  This refusal is intentional: OHLC alone cannot establish observed depth,
  point-in-time option identity, PCR, or executable fills.
- Native data and assessment services reuse OpenAlgo's broker/history sources.
  Historify remains a historical storage source, not proof of option execution.

Add bounded point-in-time observation recording and immutable experiment,
dataset manifest, replay cursor and result records. Reuse the same indicator,
selector, protection and cost functions causally, with only observations
available at each simulated instant. Keep replay isolated from primary stores,
active settings and broker submission. Store configuration and source hashes,
coverage gaps and experiment splits. Missing execution evidence must block
execution-grade results; signal-only studies must remain clearly labelled.

### Discord Monitoring

- `services/alerts/channels/discord.py` provides a validated webhook channel
  with destination host/path restrictions, escaped structured alerts and
  disabled mentions. Reuse its formatting/security behavior where applicable.
- The shared alert router is not a NIFTY durable ten-destination delivery
  outbox or a read-only monitoring bot.
- Existing NIFTY report delivery persists retry/claim state and treats an
  ambiguous SMTP outcome conservatively. Reuse its lifecycle conventions and
  existing SMTP configuration, not its report rows for unrelated alert events.

Add a dedicated notification projection over committed NIFTY events, durable
outbox, bounded delivery attempts, rate-limit state and dead-letter status.
Run HTTP/bot work outside protection jobs. Keep secrets server-side and return
only masked readiness to the browser. Restrict bot commands by guild, channel
and authorized user IDs; command allowlist is read-only. Never expose trading,
resume, stop modification or configuration commands. Critical alerts require
durable escalation and independently tracked Gmail/SMTP fallback. Do not claim
exactly-once remote delivery when transport acknowledgement is ambiguous.

## Database And Migration Plan

The baseline uses SQLAlchemy `Base.metadata.create_all()` in
`NiftyStore.initialize()` for additive tables. Existing state/config migrations
are handled by `ensure_user()` and `migrate_configuration()`. All engines must
continue to come from `database.engine_factory.create_db_engine()` with
`NullPool` on SQLite. Sessions remain short-lived context managers.

Planned additive durable structures:

1. Safety incidents and operator actions, with an indexed owner/mode/status
   lookup and a versioned entry interlock. Reuse existing killed/paused flags
   rather than introduce a competing kill switch.
2. Selector decisions keyed by owner, mode and decision identity, including
   ranked candidate/rejection evidence and configuration version.
3. Replay dataset manifests, bounded observation batches, immutable experiments,
   resumable cursors and research-only results.
4. Discord nonsecret routing/settings, event cursor, idempotent delivery outbox,
   claims, attempts, rate-limit deadlines and dead-letter/fallback state.

Analytics should query existing trades/fills and need no duplicate account
table. Do not add columns to existing tables without an explicit migration:
`create_all()` does not alter existing tables. Initialize twice in migration
tests and prove existing balances, reservations, fills and locks are unchanged.

Rollback means stopping new workers and reverting application code while
retaining additive evidence tables. Do not automatically drop tables or clear
an unresolved safety interlock. A rollback must preserve paused/killed state;
an old binary cannot interpret a new-only gate unless the existing paused state
also blocks entries. Back up the configured databases before deployment.

## Conflicts And Required Safeguards

- Ranking may change which otherwise valid contract wins. Preserve strategy
  preference and publish policy/version and candidate reasons.
- New safety state can race with an admitted pending BUY. Enforce it again at
  fill and retain normal SELL/protection processing.
- A generic reconciliation success must not clear an operator safety hold.
- Mode labels in the UI do not constitute execution isolation. Keep Live stub
  refusal and existing transactional mode gates.
- Shared scheduler/executor capacity can delay protection. Do not add network
  calls or replay loops to `protect()` or `evaluate()`.
- `runner.attach_runner()` currently installs independent protection, entry and
  report jobs with single-instance/coalescing limits. Preserve shutdown and job
  removal paths when extending worker ownership.
- Bound request payloads, list pages, recorder batches, retained data, retries,
  caches and registries. Retention must not delete open incident, pending order
  or unsent critical delivery evidence.

## Mode Support

| Feature | Paper | Live | Shadow | Research |
| --- | --- | --- | --- | --- |
| Selector | Extend existing execution path | Preview only; submission blocked | Reuse eligibility without primary accounting | Point-in-time metadata/quotes required |
| Safety | Durable interlock and recovery | Monitoring only; live recovery unverified | Separate hypothetical incidents | No primary controls from replay |
| Analytics | Authoritative simulated-fill ledger | No live ledger evidence yet | Hypothetical and mirrors separate | Separate experiment results |
| Replay | Never changes paper balances | No broker access | Explicit hypothetical outputs | Primary supported domain |
| Discord | Explicit PAPER labels | Readiness/incident monitoring, no orders | Explicit SHADOW labels | Explicit RESEARCH labels |

## Strategy Compatibility And Deviations

The baseline implements the five mandatory indicators, CE/bullish and
PE/bearish mapping, ATM/ITM restrictions, configuration-versioned confidence,
Decimal protection and native calendar checks. Preserve these representations.

Older design documents mention a 09:30 entry start and three daily entries.
The approved follow-up contract instead specifies observation from 09:15 to
10:30 IST and a 10:30 to 14:45 entry window. `StrategyConfig` version 3.1.0
already sets `entry_after` to 10:30 and migrates older configurations accordingly.
The store enforces one primary entry per session. This is documentation drift,
not an entry-window defect to rewrite in feature code. Verify the saved
configuration before operational acceptance.

Other unchanged requirements include maximum 45-minute holding, exit requests
by 15:10 IST (or the native earlier-close rule), risk/capital bounds, net
profit-lock/trailing floors, dynamic lot/tick/expiry metadata and observed data.
Requesting an exit is not evidence of a completed live square-off. Existing
paper estimates are not current statutory charge verification.

Angel One plugin availability does not make NIFTY live execution complete.
The baseline intentionally has no verified NIFTY live executor, protective-order
adapter, live partial-fill reconciliation or static-IP readiness evidence.
These are readiness gaps, not permission to bypass the existing stub.

## Security And Operational Risks

- Use the existing signed-session owner and global CSRF protection for every
  browser mutation. Never trust a supplied owner/mode to grant control.
- Reject unknown fields, invalid mode/status transitions, stale revisions and
  unbounded reason strings. Do not log arbitrary API bodies or broker errors.
- Discord content is untrusted. Escape data, bound content and disable mentions
  except an explicitly configured critical role. Never log webhook/token URLs.
- Restrict external destinations and redirects to avoid SSRF. Credentials
  belong in existing encrypted storage or environment, never event payloads.
- Discord interaction authorization must not reuse browser session assumptions.
- All DB, file, HTTP, thread and socket acquisitions need success/error/retry/
  shutdown release review. No new per-request thread pools or unbounded caches.
- Windows test success does not establish eventlet/gthread production behavior.
  Run the repository's Linux gthread suite before a commit or PR.

## Verification Evidence And Acceptance Gates

Initial unmodified-baseline command:

```text
".venv/Scripts/python.exe" -m pytest test/test_nifty_algo*.py -o addopts="" -q --tb=short
```

Result: **133 passed, 191 setup errors, 2 warnings in 119.76 seconds**.
The shown setup failure is `PermissionError: [WinError 5] Access is denied`
while pytest scans `C:\Users\hp\AppData\Local\Temp\pytest-of-hp`, before the
database fixtures run. This is not a passing regression run.

The isolated retry uses:

```text
".venv/Scripts/python.exe" -m pytest test/test_nifty_algo*.py -o addopts="" -q --tb=short --basetemp="C:/Users/hp/AppData/Local/Temp/nifty-feature-baseline-20261122-a"
```

Result: **324 passed, 1 warning in 149.41 seconds**. The remaining warning is
pytest cache creation denied at `.pytest_cache/v/cache`; it is not a test failure.
This establishes the feature's backend regression baseline before code changes.
Subsequent runs should use fresh isolated temporary directories and disable
pytest's cache provider rather than change production code for local ACLs.

All existing `test/test_nifty_algo*.py` tests remain regression requirements,
including paper accounting, partial exits, idempotency, protection, admission/
fill races, calendar, mode, shadow/research, native provenance and report retry
tests. Preserve `Workspace.test.tsx` and `Panels.test.tsx`.

New coverage must exercise migration preservation, interlock races at the write,
owner/CSRF checks, acknowledgement versus recovery, ranking determinism and
submission identity, authoritative analytics pagination and Decimal truth,
causal replay/future-data rejection, Discord authorization/retries/rate limits/
ambiguity/fallback, and resource release under repeated failures. Prove critical
tests fail when the relevant guard is disabled where practical.

Feature completion requires fresh backend/frontend results, resource audit,
updated architecture diagrams and a handover with actual blockers. External
broker, real-market, historical-depth, Discord and Gmail validation remains
unverified until performed with authorized infrastructure. Live stays blocked.

## Implemented Safety Recovery Slice

The Risk workspace now supports durable incident acknowledgement and explicit
paper-only resolution, followed by a separate Start action. The recovery
contract and supported incident codes are documented in
[SAFETY_MODEL.md](SAFETY_MODEL.md). The architecture diagram includes selector
evidence, entry interlocks and the recovery path.

The latest full backend run, including the status-evidence hydration fix, passed
**405 tests in 161.13 seconds**. Ruff passed. The feature frontend suite passed
**41 tests across four files**; Biome checked 17 files and TypeScript build-mode
compilation exited successfully. These are offline results, not Linux worker,
broker, market-session or external-delivery acceptance.

A follow-up regression reproduces resolution evidence disappearing from
`GET /safety` after store recreation, despite its committed audit event.
The status reader now hydrates actor, resolution time and evidence from
matching owner-scoped events without adding columns or a second audit store.
Focused safety/outbox validation passed **45 tests in 14.00 seconds**, with
Ruff clean. The final 405-test regression also includes the additional
busy-history/owner-isolation test.

Resource review: new database paths use context-managed sessions and existing
engine ownership; no new threads, sockets, file handles, network clients or
module-level caches are introduced. The failure-path test injects 100 failed
resolution commits, checks rollback, and measures equal NullPool connection
acquisitions and releases. Status hydration returns at most the incident page
size and does not scan event history into Python. Linux gthread/eventlet
rehearsal, browser visual checks, analytics, causal replay and Discord integration
remain outstanding. Live stays blocked.

## Implemented Selector Slice

The current extension adds deterministic `listed-preference-v1` assessment,
configuration identity, ranked tokens, available quote/depth provenance and raw
rejection reasons. Candidate evidence is capped at 100 rows; omitted rows are
counted. Selection preference and existing risk sizing remain separate.

Runner assessment records use owner-scoped `contract_selector:PAPER` and
`contract_selector:SHADOW` events. Authenticated
`GET /api/nifty-algo/selector?mode=PAPER|SHADOW` returns the newest matching
record or null. Live is rejected. Event filtering occurs before the bounded SQL
limit. Signal Monitor presents the evidence without order controls.

Admission rejects conflicting full contract identities, including conflicting
metadata for a repeated fallback token. A cache-only validation callback runs
under the existing ledger admission lock after account, mode, calendar and
safety checks. It compares the selected identity and rereads current spot
before insertion. It creates no broker request or subscription.

Normalized candidate metadata is retained with the order for audit. Historical
ATM classification never exempts a currently OTM contract from execution gates.
The observational selector can rank a nearest listed ATM that is slightly OTM
against exact spot; admission and fill conservatively refuse that execution.
This preserves the pre-existing strict fill boundary rather than manufacturing
a strike interval or loosening protection.

Fill checks frozen token and symbol against order columns, requires NFO CE/PE
identity and finite positive current spot for BUY, and applies current moneyness
inside the accounting transaction. Invalid proof rolls back without moving
money. SELL/protection processing does not require entry spot proof.

Verification at this checkpoint: 385 offline NIFTY backend tests pass; the
selector/workspace/safety frontend slice has 37 passing tests, Biome and
TypeScript checks. Ruff passes for NIFTY services, database, blueprint and tests.
Resource review for this slice follows `.claude/skills/fd-audit/SKILL.md` and is static: existing
transaction contexts close or roll back on each validation exit; no new engine,
client, thread, socket or retained registry is introduced. This is not a new
measured descriptor/RSS audit or Linux worker verification.

Failures before ranking now produce a durable `UNAVAILABLE` assessment. Missing
spot, current master, synchronized Greeks or listed ITM metadata retain stable
reason codes without inventing candidate rows or ATM/expiry values. Unexpected
validation errors retain only `CONTRACT_EVIDENCE_UNAVAILABLE`; provider exception
text is not persisted. Persistence errors propagate and cannot authorize orders.
The UI accepts older records without status/reasons, displays top-level refusals,
and labels absent values `Unavailable`.

When ranking is available, bounded candidate evidence also retains stale master,
expired, non-tradable, avoided expiry-day and later-expiry exclusions. These rows
have null rank/quote and `NOT_ASSESSED` moneyness; they cannot become executable
choices. Deterministic ordering and the 100-row cap preserve every ranked choice;
omitted counts include excluded metadata. No valid assessment still produces
only the durable refusal envelope, not invented candidates.

Still pending: remaining feature phases, corresponding diagrams in the separate
`openalgo-docs` checkout, and final
worker/operational acceptance. That checkout was not present beside this repository.
No deployment or external notification has been performed.

## Implemented Analytics And PDF Slice

The owner-scoped, authenticated `GET /api/nifty-algo/analytics` and
`GET /api/nifty-algo/analytics.pdf` share a bounded read-only ledger snapshot.
ISO date parameters represent IST midnights; responses record UTC instants.
The interval is `[start, end)`, at most 366 days and 5,000 exit fills.
`limit=1..100` and `offset=0..5000` affect details only, not full-period metrics.
A committed trade watermark fences concurrently appended fills. Missing,
conflicting or unreconciled fill evidence fails closed rather than returning
zero or truncated performance.

Trade-level statistics consolidate partial exits by immutable entry order.
Fill counts, realized equity, drawdown and daily groups follow exit timestamps.
Opening equity includes prior realized net. No mark series exists, so marked
unrealized P&L and observed mark-to-market drawdown remain explicitly unavailable.
The UI presents realized equity/drawdown step charts, IST daily groups, period
controls and independent fill pagination. PDF export uses the applied evidence
period rather than draft inputs; failures leave loaded metrics visible.
The PDF identifies its watermark, full-period totals, limitations and selected
fill-page appendix. A fresh export can contain fills committed after UI load.

Verification on the current analytics/PDF changes:

- Windows offline NIFTY regression: **444 passed in 180.99 seconds**.
- Feature frontend suite: **49 passed across five files**. The analytics file
  contributes eight cases, including empty curves, period/pagination separation,
  export failures and browser-download cleanup on both success and exception.
- Biome checks all 20 feature files; TypeScript build-mode checks pass.
- Ruff checks the analytics services, ledger, blueprint and analytics tests.
- Resource measurement covers 100 successful and 100 failed analytics reads,
  with no outstanding NullPool connections after each request. Browser tests
  verify object URL revocation and temporary anchor removal on both exit paths.
  PDF rendering is bounded and in-memory; no network client, thread or persistent
  cache is introduced. No process-level RSS/descriptor soak is claimed.

Linux Docker became available during this checkpoint. A fresh source copy is
on its Linux filesystem. The first worker suite reported 1,455 passed,
three skips and one failed check-then-act review gate. Its three findings
are revision increments in incident acknowledgement/resolution; all hold the
existing owner transaction lock through commit. Their exact locking reasons
are now recorded in `scripts/gthread_check_then_act_reviewed.txt`, and all ten
deploy-gate tests pass after that metadata-only change. The fresh full Linux
run then passes: **444 NIFTY tests in 128.50 seconds** and **1,456 worker tests
in 642.05 seconds**, exit 0. Three documentation tests skip with
"no threading note about greenlets"; no behavioral tests skip in that suite.
Production-worker/browser visual acceptance, exit research,
causal replay and Discord integration remain outstanding. Live stays blocked.

## Recorder Foundation (Not Forward-Capture Acceptance)

Exit research needs durable post-exit option observations before it can compare
exits without fabricating a quote path. `research.recording_batch()` now validates
quote evidence and separate source/receipt/availability timestamps. It accepts
only known envelope and quote fields, rejects future or reversed availability,
and preserves delayed observations in arrival order. Decimal prices serialize
as strings. Normalized SHA-256 values detect exact duplicate observations;
neither hashes nor caller-supplied provenance authenticate a provider.

`NiftyStore` now creates, appends, seals and pages owner-scoped research recordings
using two additive tables. No existing table or active strategy setting changes.
Each recording snapshots the current configuration, has a maximum 24-hour window,
10,000 observations and 16 MiB of serialized evidence. Batches contain 1-100 rows,
at most 256 KiB input. Each owner may retain 20 recordings; reaching quota refuses
creation and never deletes evidence automatically. A future retention/archive
workflow must be explicit. These are storage bounds, not strategy thresholds.

Appends check the expected count and all evidence bounds under the existing
owner transaction lock. Observations and hash-chain metadata commit together.
Sealing is idempotent at the same count and blocks further appends. Pages use
`sequence <= manifest.count` so a concurrent append cannot mix new evidence with
an older manifest; as-of filters use availability. The application marks every
recording `mode=RESEARCH`, `execution_eligible=false`, with quote-only and
unauthenticated-provenance limitations. No replay can infer missing instrument,
PCR, depth consumption, or execution evidence from these records.

Verification at this checkpoint: 35 recording tests pass, including duplicate
rejection, restart durability, ownership, causal pagination, creation quotas,
time windows, stale writers and competing appends. A regression test stages a
competing append immediately before the observation SELECT and caught the
manifest/page race before its fix. An injected insert failure repeated 100 times
leaves both observations and manifest unchanged; all NullPool connections close
after each failed append and successful read. The additive migration test
excludes both new recording tables before initialization and verifies existing
locks, reservations, balances and configuration survive repeated initialization.
Ruff and the strict full check-then-act static scan pass. After formatting,
the recording/outbox slice passes 49 tests. The latest Linux NIFTY regression
passes 479 tests in 134.90 seconds; the Linux worker suite passes 1,456 tests
in 633.47 seconds, with three documentation-only skips for missing greenlet
notes. No behavior tests skip in that worker run. A Windows full regression
before the final duplicate/boundary tests passes 465 tests.

This is a storage/control foundation, not an enabled forward recorder. Feed capture,
capture UI, exit-study metrics, immutable experiments, replay
cursors/results, causal strategy replay and Discord remain incomplete.

### Authenticated Recording Controls

The existing signed-session NIFTY blueprint exposes four owner-scoped operations
under `/api/nifty-algo/research/recordings`:

- `GET /`: list at most 20 owned manifests; no query parameters.
- `POST /`: create an empty recording using exactly `duration_minutes` (1-1440),
  `max_observations` (1-10000) and `confirm=RESEARCH_ONLY`; returns 201.
- `GET /<id>`: bounded page with `after` (0-10000), `limit` (1-100) and optional
  timezone-aware ISO `as_of`; rejects unknown/repeated query parameters.
- `POST /<id>/seal`: exactly `expected_count` (0-10000) and `confirm=SEAL_ONLY`;
  stale counts return 409, repeated same-count seals are idempotent.

All reads require session authentication. Both mutations require the existing
CSRF protection. Another owner's identifier returns 404, and every recording
response uses `Cache-Control: private, no-store`. Control bodies are limited to
2048 bytes before JSON decoding, including WSGI streams without Content-Length.
Malformed JSON, invalid Unicode and excessive nesting fail safely. UTC conversion
overflow is rejected before opening a database session.

There is deliberately no HTTP append/import endpoint. No request can submit
quote evidence, select provenance, resume trading or change active strategy
settings. Creation only reserves an empty research recording; the list explicitly
reports `capture_status=NOT_CONNECTED` in that original control slice.

### Native capture checkpoint - 23 November 2026

The optional strict JSON boolean `native_capture` now requests the existing
native-capture sidecar, default false for backward compatibility. Requests
still accept no evidence or instrument scope and never initialize feed/cache,
attach a monitor or change trading state. Listing returns
`NATIVE_CAPTURE_REQUESTED` when an owned manifest has opted in; this describes
request presence, not feed health or coverage. Existing legacy manifests stay
unadopted.

The runner has a separate five-second capture job with single-instance,
coalesced scheduling, application context, registration rollback and shutdown
removal. It uses verified existing feed state, a frozen master scope and
owner/count-fenced durable appends, with no readiness renewal or order path.
Master-identity races, socket/reconnect changes during sampling, seal races,
100-sample bounds, rotation and loop-budget exhaustion have focused coverage.
One hundred duplicate capture calls close every opened database connection.

Windows NIFTY regression before the HTTP opt-in extension: 620 passed
in 260.48 seconds. After opt-in, the API/capture slice passes 86 tests in
29.93 seconds, with Ruff clean. These are intermediate results; the recording
workspace checkpoint below supersedes their capture/UI and verification status.

### Historical authenticated-control verification

Focused verification: 44 API tests plus 35 recorder tests pass (79 total).
Tests cover session/CSRF, ownership, frozen configuration, invalid controls,
quotas without evidence deletion, stale cursors, bounded parsing and availability
filtering. A 100-iteration list/page/not-found read loop observes no SQL writes
and no checked-out connections after each request. This is connection-lifecycle
measurement, not a production descriptor/RSS soak.

Fresh full verification of this control slice: Windows NIFTY 523 passed in
288.43 seconds; Linux NIFTY 523 passed in 222.62 seconds; Linux worker suite
1,456 passed in 663.23 seconds, with three documentation-only skips for missing
greenlet notes. All runs exit 0 with zero failures. Frontend NIFTY tests pass
49 tests across five files; Biome checks 20 files and TypeScript passes.
Ruff, the strict full check-then-act scan and `git diff --check` pass.

Resource review finds no new files, sockets, threads, executors, subscriptions
or module-level registries in these API controls. Read sessions close through
existing contexts; create/seal transactions retain the owner lock through
commit and roll back on exceptions. Input parsing and response queries have
explicit bounds. Production-worker/browser acceptance and forward-capture
resource measurements remain outstanding.

### Recording Workspace Checkpoint - 23 November 2026

The Research tab now lazy-loads recording controls through Suspense. Creation
requires research-only consent, validates integer bounds and defaults native
capture to false. Manifests distinguish native requests from feed health and
show frozen scope, saved count, capture-window conditions and content hashes.
No control connects a feed or changes trading state.

Seal review freezes the expected observation count and disables confirmation
when the current count/status changes or a read fails. Cancellation restores
focus to the review button; successful sealing focuses the introduction.
Creation and sealing explicitly disable mutation retries. An ambiguous create
blocks another creation until a successful explicit refresh. API helpers use
the existing signed-session/CSRF client and whitelist request fields.

Latest recorded backend evidence: Windows full NIFTY suite 631 passed; Linux
full NIFTY suite 629 passed before the final HTTP/cache integration additions.
That final capture-runner slice passes 35 tests on each operating system.
These counts describe distinct source checkpoints, not identical full runs.
The latest Linux worker gate is NOT green: 1,455 passed, three documentation
skips, one 25-second eventlet child timeout in
`test_gthread_historify_lifecycle.py::test_connection_retry_allows_green_and_native_writers_without_stopping_hub`.
A diagnostic run did not reproduce it; that does not resolve the failure.
No Historify, eventlet or threading runtime fix is claimed.

Frontend feature tests: 62 passed, including recording API and panel coverage.
Biome, TypeScript build-mode noEmit and the production Vite build pass; the
build reports chunk-size warnings. Generated `frontend/dist/` remains unstaged.

Visible Edge browser verification uses an isolated Vite component harness,
fresh browser context and mocked HTTP only. At 1440px and 375px it verifies
consent/defaults, exact CSRF and mutation payloads, count-fenced sealing,
keyboard focus/trapping/Escape, ambiguous-create blocking, explicit refresh
recovery, dialog bounds and no horizontal overflow. All eight API requests are
mocked: two creates (one deliberate 503), one seal and five reads. No page
errors occur; the intentional 503 produces the expected console resource error.
Three axe scans of settled desktop, dialog and mobile states report zero WCAG
2/2.1 A/AA violations. Screenshots were visually reviewed at both widths.
This does not establish signed-in full-application/backend/broker acceptance,
real-device behavior, screen-reader usability or full WCAG conformance.

The initial harness import failure was fixed outside production source by
using Vite's normal bare-import/CJS interop through a virtual entry. Browser
audits await actual animation completion rather than reading transitional
disabled opacity. No production style or accessibility threshold was relaxed.
The temporary QA server is closed after verification.

Causal option replay, immutable experiments, evidence-backed exit studies and
Discord monitoring remain incomplete. Final worker/resource/runtime gates
remain outstanding. No commit, push, deployment, external message, broker
access, real order or PR-lifecycle claim accompanies this checkpoint.

### Sealed Quote Cursor Core - 23 November 2026

An internal read-only `recording_cursor()` now validates sealed owner-scoped
datasets against a pinned count and SHA-256 before returning any observations.
It verifies normalized quote hashes, context and native-scope chain, sequential
pages, window/availability order and stored byte counts. The detached cursor
has a monotonic timezone-aware clock and returns at most 100 observations per
step; delayed quotes appear at availability time, never retroactively.
No account, runner, order, feed, API, UI or experiment-persistence path is added.
The full manifest is retrospective audit metadata, not causal strategy input.
Options execution replay remains explicitly unavailable.

Test-first coverage exposed an omitted native-scope hash-chain step in the new
loader. The loader now reproduces the existing freeze chain; storage/capture
behavior does not change. Windows focused replay/research/recording tests pass
87 cases in 19.66 seconds; the same slice on Linux passes 87 in 14.58 seconds.
Ruff and `git diff --check` pass. A repeated-load test observes every opened
NullPool connection close after each of 100 successes and 100 corrupt-content
failures. Static resource review finds no retained connections, sockets,
threads, files or global cursor registry. Retained evidence is bounded by
10,000 observations and the recording's 16 MiB encoded quota; that is not a
Python heap/RSS cap. Final process FD/RSS soak remains outstanding.

Further cursor adversarial coverage, immutable experiment storage/execution,
strategy-input causality and exit studies remain unfinished. This focused
proof does not supersede the unresolved Historify worker timeout or establish
full regression/runtime acceptance.

### Immutable Experiment Definitions - 23 November 2026

An additive research table now stores write-once definitions after sealed
owner-scoped cursor verification. Each definition freezes dataset manifest,
validated strategy configuration and its identity, engine version, half-open
UTC TRAIN/VALIDATION/TEST boundaries and canonical content hash. Creation
rechecks the source under the existing owner lock. Active settings and trading
tables are unchanged. Limits: 50 definitions per owner, 64 KiB configuration,
1 MiB snapshot. There is no mutation/deletion method or implicit pruning.

Definitions remain `DEFINED`, execution-ineligible and without performance.
Split bounds end at the earlier seal/window end; boundaries do not prove
coverage. No execution, result persistence, API or UI integration is claimed.
Options simulation remains unavailable.

Test-first missing-method failure precedes implementation. A later corruption
test exposes unchecked stored snapshots; reads now verify canonical SHA-256.
The research slice passes 223 cases on each OS. Tests cover a competing writer
at INSERT with 49 definitions already stored, source replacement at the owner
lock, deterministic identities, invalid settings, detached reads and 100
injected failures after actual SQL INSERTs. Every connection closes, failed
rows roll back and the next insert succeeds. The post-import-cleanup Windows
experiment/outbox slice passes 28 cases, including additive migration preserving
existing locks, balances and reservations. Ruff/format and diff checks pass.

An isolated Linux soak holds 50 definitions and repeats cursor loading, listing
and quota refusal for 100 measured iterations after warm-up. FD samples remain
5 throughout. RSS moves from 69,312,512 bytes to 71,364,608 bytes, with identical
final two samples; traced live allocations increase by 39,695 bytes. This is
a small-dataset lifecycle check, not a maximum-recording or production soak.
No new engine, thread, file, socket or global registry is acquired by definition
storage; existing session contexts release on success and exceptions.
Fresh full NIFTY gates after import cleanup pass 660 tests on Windows
(271.08 seconds) and Linux (191.10 seconds).
The unresolved Historify worker timeout still blocks final runtime acceptance.

### Experiment Controls - 23 November 2026

Signed-session GET/POST experiment controls now freeze definitions using owned
sealed evidence, pinned count/hash and validated research settings overrides.
Overrides merge into the recording configuration, not active settings. POST
requires CSRF and `DEFINE_ONLY`, rejects unknown controls, and reads at most
2 KiB even without Content-Length. Lists select at most 50 identities without
loading dataset snapshots. Owner-scoped detail verifies the snapshot digest.
All responses are private/no-store. No edit, delete or run route exists.

Test-first missing-route failure precedes implementation. The experiment API,
persistence and recording API slice passes 98 cases on Windows (27.62 seconds)
and Linux (20.57 seconds). Coverage includes session/CSRF, ownership, immutable
settings isolation, bounded bodies, invalid controls/settings/splits, pinned
identity, SELECT-only reads and sanitized corrupt-detail refusal. Ruff and diff
checks pass. Fresh post-API full NIFTY gates pass 691 tests on Windows
(319.07 seconds) and Linux (220.70 seconds). An isolated 100-cycle API soak
closes all 806 opened connections across reads, verification refusals and
post-SQL INSERT failures; the next insert succeeds. Six samples hold at five
FDs. RSS grows from 197,193,728 to 197,439,488 bytes with tapering increments;
this small-fixture measurement is not worst-case or production memory proof.
The Historify worker timeout remains unresolved. UI and study execution/results
are not wired. Options execution replay and Live remain unavailable.

### Experiment Definitions Workspace - 23 November 2026

This checkpoint supersedes the earlier experiment-UI gap, not the replay,
study-results or worker-runtime limitations. Research now lazy-loads an
experiment panel alongside recording controls. Operators explicitly select
nonempty sealed evidence, pin its reviewed count/hash, enter half-open UTC
split boundaries and optionally override ADX minimum or ATR period. All other
settings come from the recording, never current active settings. Definitions
remain immutable, research-only and execution-ineligible, with no performance.

Changed source identities and failed source/list reads block creation even
when cached data exists. Detail refresh failures hide the previous snapshot.
The shared recording query key deduplicates reads across both panels.
Definition writes disable retries even if the QueryClient enables them;
uncertain writes require successful manual refresh and operator inspection.
The API helper whitelists payload fields and fixes confirmation to
`DEFINE_ONLY` through the existing signed-session/CSRF web client.

The NIFTY frontend suite passes 72 tests across nine files in 16.23 seconds.
Six changed experiment/workspace files pass Biome, TypeScript noEmit passes,
and the production build (including `tsc -b`) completes in 1 minute 25 seconds.
Output uses a temporary directory, not tracked `frontend/dist/`. The build
retains existing whole-application asset/deprecation/plugin-timing warnings.
Backend source has not changed since the recorded 691-per-OS/API-soak gates.

Visible Chrome checks pass at 1440px and 375px with Asia/Kolkata browser
timezone, using an isolated Vite component harness and fully mocked HTTP.
Checks cover keyboard consent and submission, exact UTC/count/hash/override
POST payloads, persisted inspection after reload, hidden stale detail after
verification failure, list failure/recovery and uncertain-write lockout without
automatic retry. Each viewport sends exactly two mock definition writes:
one success and one deliberate 503. No page exceptions or unexpected API
requests occur. Two settled axe scans report zero WCAG 2/2.1 A/AA violations
inside the panel. Expanded snapshots do not cause horizontal page overflow;
screenshots are visually reviewed at both widths.

The first harness run could not find its expected bundled browser; it uses
installed Chrome instead. A second harness failure came from Playwright
comparing a datetime-local input against an unnormalized zero-seconds value.
A browser probe confirms native normalization from `04:10:00` to `04:10`.
The harness now fills the canonical minute value; production code is unchanged.
UTC conversion is asserted at the HTTP boundary, not inferred from display.

This proves the isolated component flow, not signed-in full-application,
production-worker, real-device or screen-reader acceptance, nor full WCAG
conformance. The unresolved Historify eventlet child timeout still blocks final
runtime acceptance. Causal option execution replay, evidence-backed exit
studies and Discord monitoring remain incomplete. No live orders, external
messages, deployment, commit, push or PR lifecycle change is performed.

### Weighted Selector, Exit Research, Replay and Discord Continuation — 23 November 2026

The remote baseline was fetched again successfully and still matches
`84b899ab9d91eaba4a12decff2c1474a29bb5d99`. Existing local feature work was
preserved. Fresh pre-edit Windows regression passed 691 cases in 328.22 seconds.

A source audit found that the previous selector checkpoint ranked listed
preference rather than the requested weighted contract/lot pairs. The existing
risk planner now evaluates every permitted eligible pair with Decimal
30/25/15/20/10 weights. Normalization, missing-Delta fixed-weight handling, raw
inputs, score bounds and deterministic tie breaking are documented in
[SMART_CONTRACT_SELECTOR.md](SMART_CONTRACT_SELECTOR.md). Existing risk,
reservation and final-fill checks remain authoritative. Default weight identities
preserve existing v3.1 configurations and open-position protection; edited
weights change the configuration identity. DELTA-mode's existing strict Greeks
requirement and the inherited five-second quote threshold remain explicit
compatibility differences, not silently weakened gates.

Analytics now exposes reconciled owner-scoped trade details, additional
breakdowns, sampled MFE/MAE/profit capture, bounded stop history and a sampled
post-exit study through the approved effective close. Missing observations stay
unavailable; sampled extrema are not continuous market extrema. Report PDFs
reuse the original renderer/archive/Gmail workflow and add safety/protection
interval evidence. There is no new account or P&L ledger.

Immutable experiments now support hash-verified coverage inspection and
availability-time quote playback. Inspection results are write-once and
configuration/dataset/version identified. Full execution and all three financial
variant results remain refused because the recorder does not establish futures,
historical PCR or continuous protection evidence. The pure signal-study function
accepts explicitly dated historical PCR with receipt availability, but a saved,
integrated signal execution workflow and full recorder/retention remain unfinished.

Discord adds a dedicated API-v10 REST bot, encrypted settings and validated ten
channel ID routing, Ed25519-signed authorized ephemeral monitoring commands,
idempotent incident acknowledgement, critical role allowlisting, durable attempts,
rate-limit retry state, restart-safe reminders, independent Gmail fallback,
verified report attachments and an integrated management panel. A standalone
notification process isolates delivery from the protection scheduler. Shadow
activity uses a separate checkpoint and a bounded 60-second digest. Critical
incident generation is never disabled by routine preferences.

Regression testing first exposed primary-event writes from Shadow paths:
738 tests passed and two failed. A follow-up static check also caught a direct
primary event call in the runner's Shadow method. All such calls were removed;
Shadow freezes scoring in its own protection and projects its own journal.
Existing order-boundary/isolation tests were not weakened. The unchanged Phase 4
slice then passed 28 cases. The fresh final full NIFTY gates pass **744 cases on
Windows in 458.83 seconds and Linux in 249.02 seconds**. Four newer Discord tests
then pass in the focused **37-test suite on both OSes** (22.10 seconds Windows;
7.20 seconds Linux). A separate reports/Discord/analytics slice passes 95 cases.

The combined frontend suite passes **79 tests across 11 files**. TypeScript
noEmit and the production tsc-build/Vite build pass; build output is outside
tracked frontend/dist. Warnings concern existing whole-application asset,
deprecation, plugin timing and chunk size. An npm wrapper rejected an outDir flag;
direct installed tsc.cmd and vite.cmd complete the intended build. Ruff and
reviewed check-then-act/sleep gates pass. The sleep review covers only the
standalone notification CLI loop, which holds no transaction while polling.

Visible installed Chrome passes isolated mock HTTP checks at 1440px and 375px,
with Asia/Kolkata timezone. The checks cover ten ID inputs, credential clearing,
revision-pinned saves, failed-write lockout without retries, manual refresh,
immutable coverage and exact UTC replay/step controls. Each viewport performs
four mock POSTs and two playback reads. No page errors or unexpected transport
occur. Both scoped WCAG 2/2.1 A/AA axe scans have zero violations and both full
screenshots were visually inspected; no horizontal page overflow occurs. The
skill wrapper could not create its scratch file in the protected skill folder,
so the same test script ran directly from the permitted Temp directory.
This is component proof, not a signed-in full-application or assistive-device audit.

Resource review found standalone SMTP lookup sessions lacked Flask teardown.
The worker now uses the existing session_cleanup context before SMTP, including
exception paths. Repeated configuration/conflict reads close all 300 connections.
A 120-cycle isolated Linux mocked dispatcher soak closes all 1,080 connections
and samples five FDs throughout. Its mock retained call history, so a second
220-cycle run removes that instrumentation retention: all **1,980 connections
close**, FD samples stay **5**, and RSS samples after warm-up move from
198,979,584 to 199,032,832 bytes. Small RSS growth remains; this is not a
worst-case or production memory proof. No real provider, broker or feed is used.

The earlier unresolved Historify eventlet child timeout remains a release
blocker. A bounded stack-capture diagnostic did not reproduce it; that is not a
root-cause fix or a passing full worker gate. Live adapter transport is still
absent. The extension does not certify broker-hosted protection or emergency
flattening. Remaining local software and external validation gaps are listed
explicitly in ADVANCED_FEATURES_READINESS.md. No commit, push, deployment, real
order or external message was performed.
