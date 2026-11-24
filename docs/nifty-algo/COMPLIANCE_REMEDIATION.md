# NIFTY compliance remediation — 24 November 2026

## Revision and verification boundary

The first pass started at `1a0be77917cc66841926cf63c9adf6062b881803`, the
reference audit commit. The completion pass started at local and remote branch
HEAD `69862862b35e31637239498b4531d76ce48f77b8`, branch
`feat/nifty-paper-trading-system`, which adds only
`NIFTY_INDICATOR_PARITY_AUDIT.md` on top of the audit commit. No reset, commit,
push, merge or PR creation.

The latest CI run for that HEAD,
[45340678640](https://github.com/Yash19815/openalgo/actions/runs/45340678640),
failed only in `gthread-migration`: 1,281 items collected, 27 collection errors,
the first `KeyError: 'openalgo.test.test_gthread_review_messaging'` and the rest
`ModuleNotFoundError: No module named 'openalgo.test'`. Every other job,
including backend tests on Python 3.12, 3.13 and 3.14, passed. That is the
failure the import correction below addresses.

The audit, CLAUDE.md, service/RMS prompt references, NIFTY architecture, design,
reuse audit, readiness and testing documents were reviewed against current
source. Findings below are independently demonstrated by source or controlled
regressions, rather than accepted from historical line numbers.

Latest inspected [CI run 45336311245](https://github.com/Yash19815/openalgo/actions/runs/45336311245)
finished with failure. Its `gthread-migration` job, ID `138249228615`, collected
1,281 items with 27 collection errors. The log records Python 3.12.16 and a PR
merge checkout `d0418d29397652a7ffe8b4a438e9633ce3f8baa8`. Backend jobs on
Python 3.12, 3.13 and 3.14 passed in that historical run. Those results do not
verify this unpushed working tree. All new Linux and cross-platform results are
**PENDING GITHUB CI**.

## Import failure root cause

Default pytest `prepend` collection follows package markers upward. The empty
application-root `__init__.py`, together with `test/__init__.py`, named modules
`openalgo.test.*` in the checkout named `openalgo`. The installed OpenAlgo SDK
also owns `openalgo` and has no `test` subpackage. Existing test setup imports
the SDK, and the legacy MCP helper can remove an incorrectly bound application
package from `sys.modules`. Removing that package while
`openalgo.test.test_gthread_review_messaging` is still importing explains its
observed `KeyError`; later imports fail on the SDK's missing `openalgo.test`.

Earlier missing `test.test_nifty_algo_paper_executor` and bare
`test_gthread_sandbox_support` errors arose from the two existing helper import
styles and package/path changes. Keeping `test/__init__.py` and
`pythonpath = [".", "test"]` supports both styles. Removing only the empty
application-root marker makes collection stop at the actual `test` package.
It also agrees with setuptools' existing `packages = []` declaration: this
application is not the SDK package. No global module alias, new module eviction,
import-order workaround, assertion change, test skip or matrix removal is used.

Synthetic Windows subprocess tests exercise both collection orders in a folder
named `openalgo`, including a parent package marker and real installed SDK
imports. Actual Linux gthread execution is left to CI. Pytest's
[import-mode reference](https://docs.pytest.org/en/stable/explanation/pythonpath.html)
documents package naming and the additional helper-import constraints of
`importlib`; changing import mode alone was not needed.

## Finding disposition and exact corrections

| Finding | Independent evidence and correction |
| --- | --- |
| F-11 | Confirmed: the report queue overrides the connection's C timeout to 500 ms. Remove it; retain 100 ms C waits and cooperative retries. Add a context-local one-second deadline for interaction DB work and report enqueueing, without changing ordinary 15-second retries. Set the short C timeout before WAL connection setup. Owner locking, commit and composite-key deduplication remain atomic; no transport runs in this transaction. |
| F-05 | Confirmed: Python initialization and NIFTY restore share a try block; one owner exception aborts the loop. Separate startup boundaries, require the existing running scheduler, isolate owners, expose failed restoration as unready, and retain all ledger exposure. Partial job registration closes the runner and attempts every job removal. Retries reuse deterministic jobs and existing runners; attachment starts unready. |
| F-07 | Confirmed for both token columns. Settings use string `user_id`; private report requests use `(user_id, interaction_id)` and nullable String(2048). Add both to salt sampling/migration and pepper rotation with exact keys. Unknown NIFTY ciphertext aborts and rolls back; known new-key ciphertext is not double-encrypted. Caught salt failures restore the previous settings file, and startup then continues on the legacy salt the restored file and the rolled-back database agree on, retrying next start; startup stops only when the restore itself fails. (The first pass raised and stopped startup on every caught failure. That would have kept every install with one unreadable NIFTY token, or one transient DB error, from starting at all, so the completion pass changed it.) Crash-atomicity between DB and filesystem remains unsupported; matched backups are required. |
| F-13 | Git exclusions were missing. Add both private roots. Docker inclusion was not reproduced: `.dockerignore` already excludes all `db/`; clarify its persistence implications. `git ls-files` found no tracked artifact in either root, without reading file contents. No runtime file or record was deleted. |
| F-02 | Confirmed: no Flask page route. Register `/nifty-algo` with optional trailing slash, serving the existing shell. React authentication and API session/CSRF checks remain unchanged. |
| F-01/F-06 | Confirmed fixed-print/silent catches in workers, Discord, socket-session validation and feed bootstrap. Use the existing logger with a sanitized exception value and original traceback locations/type. Arbitrary exception messages, chains and provider bodies are withheld. Ambiguous deliveries remain ambiguous. |
| F-08 | Confirmed: a feed-bootstrap exception class was appended to `DATA_PIPELINE_UNAVAILABLE`. Keep the stable code, protect diagnostics in logs and add actionable labels. Replace the audited revision/history/recording/replay messages with trader instructions. Other controlled domain codes remain available for support. |
| F-09 | Confirmed: no inbound limiter. Apply 20/second and 120/minute before DB/signature work using one deployment-wide key, keeping limiter key space bounded. Ed25519 remains mandatory for PING and commands; no rate-limit exception bypasses signatures. |
| F-12 | Confirmed: `_spot` initializes its cache outside its exception guard. Include initialization in that guard so a BUY lacking spot evidence is skipped while later protective SELLs continue. |
| F-14 | Apply Ruff to changed NIFTY/new files and only changed ranges of shared files. The completion pass also formatted the three NIFTY sources the audit named (`analytics_report.py`, `calendar.py`, `calendar_import.py`; layout only). Shared platform files that were already unformatted at HEAD (`app.py`, `utils/env_check.py`, `upgrade/rotate_pepper.py`, `blueprints/react_app.py`) and the twelve older NIFTY test files are left alone to keep the review diff focused. |
| F-15 | Add deterministic Windows lock/deadline, restart/partial-failure and private-command regressions. Add real report-lock/hub-liveness cases to the existing eventlet subprocess file already run by CI. No local eventlet/gthread runtime or Linux environment was used. |
| F-18 | Confirmed personalized outbound URL. Use the upstream URL, platform `utils.version.VERSION` and Discord's documented `DiscordBot (url, version)` identification format. |
| F-16 | Add an unreleased platform entry and group feature corrections under existing unreleased 0.6.0. No release or version bump is claimed. |

F-03/F-04 intentionally retain PAPER terminology: this feature's isolated
Decimal ledger, approved starting capital and fill model are distinct from the
shared Sandbox account. Renaming it Sandbox would misrepresent ownership and
routing. Historical design mockups are not a new shipped integration. F-10 and
F-17 are informational. F-19 remains a bounded, explicit setup operation;
its provider validation calls were not redesigned.

## F-20 database placement recommendation — deferred

The feature currently uses the main engine, `NullPool`, WAL and short-lived
transactions. Owner `_lock` uses UPDATE before mutable reads; on SQLite that is
a database writer lock, not an independent per-owner writer. Protection renews
a durable 30-second lease each second; entry work and capture add writes every
five seconds, while reports/notification/research processes share that file.
Native data acquisition, provider sends and report rendering remain outside
financial-state transaction locks. The authoritative Decimal ledger, fill
deduplication, depth consumption, monthly/cooldown state and protection history
depend on those transaction boundaries.

A controlled second-connection test independently demonstrates contention and
deadline refusal. It does not measure this operator's workload, storage latency,
WAL growth or production lock-wait rate. No production database was inspected
or benchmarked. Finite cooperative retries can still fail under sustained
contention; WAL is not a no-failure guarantee.

Recommendation: retain the current placement for this correction. Measure lock
wait percentiles/timeouts, protection scheduling delay, file/WAL/checkpoint
growth, and research write volume on the target deployment. If contention is
material, prepare a separately approved migration of the complete NIFTY table
set, not selected ledger tables. Quiesce every writer, preserve owner/intent
identities and live leases or fence old owners, copy all state and immutable
evidence, reconcile exact Decimal cash/fills/positions, and prove restart and
rollback before switching engines. Update workers, migration/key-rotation
registries and coordinated backups for both databases and private blobs.
An isolated DB removes competition with unrelated main-DB writers but adds
cross-database auth/config/calendar consistency, migration and operational
backup costs. No database split or shared-risk redesign was implemented.

## Changed files

- Import layout/CI: deleted root `__init__.py`; `pyproject.toml`,
  `test/conftest.py`, `.github/workflows/ci.yml`,
  `test/test_pytest_import_resolution.py`.
- Locking: `database/__init__.py`, `database/nifty_notification_ops.py`,
  `test/test_sqlite_lock_cooperative.py`.
- Startup/exits: `app.py`, `services/nifty_algo/runner.py`,
  `services/nifty_algo/paper_executor.py`.
- Secrets: `utils/env_check.py`, `upgrade/rotate_pepper.py`,
  `test/test_nifty_algo_secret_rotation.py`.
- Formatting only (F-14): `services/nifty_algo/analytics_report.py`,
  `services/nifty_algo/calendar.py`, `services/nifty_algo/calendar_import.py`.
- Routes/logging/messages: `blueprints/nifty_algo.py`,
  `blueprints/nifty_discord.py`, `blueprints/react_app.py`,
  `services/nifty_algo/safe_logging.py`, `services/nifty_algo/discord_bot.py`,
  `services/nifty_algo/notification_worker.py`,
  `services/nifty_algo/replay_worker.py`,
  `frontend/src/features/nifty-algo/labels.ts`,
  `test/test_nifty_algo_compliance.py`.
- Storage/docs: `.gitignore`, `.dockerignore`, `README.md`,
  `docs/CHANGELOG.md`, `docs/nifty-algo/CHANGELOG.md`,
  `docs/nifty-algo/DISCORD_INTEGRATION.md`, `docs/nifty-algo/SETUP.md`, this record.

No new dependency, environment variable, broker execution transport or database
schema is introduced. The existing schema definitions remain unchanged.

## Verification

Executed in the existing Windows environment through `uv run --no-sync`:

- Initial isolated import checks: **2 passed**.
- First compliance iteration: **9 passed, 1 failed** because the new test called
  a nonexistent helper. Corrected the test to use actual `monitor_exits`.
- Focused compliance/import/secret-rotation and neighboring rotation warnings:
  **29 passed in 58.20 s**. This includes rollback of synthetic .env/database
  failures and composite-key ownership; no operator credential was rotated.
- TypeScript: `node node_modules/typescript/bin/tsc -p tsconfig.app.json --noEmit --incremental false`
  from `frontend/`: **passed**.
- `git diff --check`: **passed**. Git ignore checks match both private roots;
  tracked-artifact checks return no names.

Completion pass, same environment (Windows, Python 3.12, `uv run --no-sync`):

- Every file the CI "offline NIFTY and notification regressions" step lists
  (`test/test_nifty_algo_*.py`, import resolution, both salt/pepper files, SMTP,
  requirements parity): **875 passed in 305.54 s**. Run before the F-14
  formatting; the calendar, analytics, rotation and lock files were re-run after
  it: **75 passed, 1 skipped** (the eventlet file, skipped because eventlet is
  not installed locally).
- `pytest test/test_gthread_*.py --collect-only`: **1,430 collected, 0
  errors**, against CI's 1,281 with 27 errors. This checks imports only; no
  gthread test ran.
- `test_mcp_integrity.py`, `test_alerts_flow_mcp.py`,
  `test_strategy_residual_safety.py` (the bare and `from test import` helpers):
  **125 passed**.
- The two new eventlet cases in `test_sqlite_lock_cooperative.py` ran against a
  thread-backed stand-in for `eventlet`. That checks their inputs and
  assertions only: **2 passed**. Hub liveness under real eventlet is **PENDING
  GITHUB CI** (`eventlet-fallback` job).
- `ruff check`: no finding that HEAD did not already have in the changed shared
  files; NIFTY sources clean. Biome on `labels.ts`: clean. `git diff --check`:
  clean. `.gitignore` matches both private roots; no tracked file in either.
- Not caused by this change: `test_alerts_api.py` followed by
  `test_broker_keys.py` in one process fails 67 broker-keys cases. HEAD fails
  the same 67 in a clean worktree, each file passes alone (177 passed for
  broker keys), and CI never runs the two together.

Earlier audit/readiness counts are historical, not newly executed.

## Safety and remaining acceptance

All approved trading rules remain unchanged: isolated ₹20,000 seed; at most one
filled primary entry per eligible day; long NIFTY ATM/ITM CE/PE only; eligible
1–3 lots; mandatory SuperTrend/MACD/VWAP/ADX/verified PCR; completed 5m entry and
15m confirmation; entry 10:30 to before 14:45 IST; 45-minute maximum hold;
15:10/effective-session exits; maximum 8% initial stop; 1.5-point trail;
₹400 modeled planned-loss ceiling and ₹350 minimum modeled reward; approved
profit/floor/early exits; next-eligible-session loss cooldown; ₹2,000 monthly
realized net-loss lock; independent Shadow and non-additive mirrors; strict
source/depth/fee/expiry/master/lot validation; atomic Decimal ledger/recovery.
`LiveAdapterStub` and permanent `LIVE_NOT_READY` remain intact. No indicator,
threshold or selector-weight change and no broker order path was introduced.

Real Angel One feed/PCR/depth/expired-option history, Discord three-second
acknowledgements and permission/delivery behavior, SMTP delivery/ambiguity,
DigitalOcean mounts/backups/resource supervision and forward PAPER recovery
remain external acceptance requirements. A caught-error rollback does not
guarantee recovery from power loss across filesystem/database commits.

Verdict: **PARTIAL**, pending GitHub CI and external acceptance. No local Linux,
WSL, Docker, VM, Gunicorn/eventlet/gthread runtime, real order or real message.

## Security and strategy-integration corrections — 24 November 2026 (second pass)

Starting HEAD `36baadbfae4704f04e90fe387ef63d6cfdd5f46c` (local equals
`origin/feat/nifty-paper-trading-system`). The first pass above is pushed and
was not repeated. No commit, push, merge or PR.

| Finding | Evidence | Correction |
| --- | --- | --- |
| S-01 (platform) | `blueprints/apikey.py` took the target of `POST /apikey` and `POST /apikey/mode` from the body's `user_id`, unchanged from upstream `main`. | Both writes act on `session["user"]`. An explicit other `user_id` (another account or one that does not exist) gets 403 and writes nothing; the owner's own `user_id`, or none, works as before. A non-object body cannot name a target. CSRF is untouched and still required. |
| N-02 | Reproduced on HEAD: a mode-3 source with `oi=5000` gave a PAPER quote with `oi=None`, while the research reader copied it. | `depth_quote.open_interest` is the one parser for both paths: only the contract's own identified source record, a non-negative non-bool `int`, missing stays `None`. PAPER drops a malformed value and keeps the quote (it also prices exits); strict research reads refuse it as before. `recording_quote` no longer overrides OI. |
| N-03 | Demonstrated from HEAD source: the runner sent `atm_strike: None`, admission classified against selection-time spot, and the locked write, fill and replay used spot-only `moneyness`, so the nearest strike on the far side of spot was refused. | `contract_resolver.current_moneyness`: nearest listed strike of the same side and expiry on today's verified master, lower at the midpoint, recomputed from fresh spot at admission, at the locked write, at fill and in replay; the selector uses the same `nearest_listed_strike`. The ladder is read before the ledger lock. The ATM label applies only while listed strikes bracket spot, so a sparse ladder cannot widen eligibility (found by an existing 21900 test once a one-strike fixture ladder was added). No master or a contract it does not list identically refuses. The check runs after the cooldown, monthly-lock and restriction checks, so their reasons still come first. |
| N-04 | Reproduced on HEAD: dropping one minute of the oldest session made the end-to-end fixture ineligible. | `completed_series` keeps the continuous suffix after the latest same-day gap when that gap is in an earlier session, refuses when it is in the session being evaluated, and repairs nothing. Whole-series value, identity (rollover) and overlap refusals are unchanged; R-WARMUP decides suffix length. |
| N-04, related | Reproduced on HEAD: with today's minute 1 missing (opening 5-minute bucket dropped), the fixture was **eligible** and no `SESSION_VWAP_INCOMPLETE` was recorded. | `assess_current` also requires today's first completed entry candle to start at the open. |

Priority 5 checks, verified by reading and by the suites below:

- Discord interaction limiter is still applied before the owner lookup;
  `test_public_interaction_limits_run_before_owner_lookup` and
  `test_rate_limited_surface_still_verifies_signed_ping` pass.
- `db/nifty_reports/` and `db/nifty_calendar/` match `.gitignore`; no file in
  either is tracked.
- Single-user administration: S-01 changes only who a write targets; the
  `GET /apikey` view, session checks and the one-account model are unchanged.
- Selector weights: five values, each 0 to 100, summing to 100; NaN, infinity
  and wrong arity are refused; a change makes a new configuration identity, so
  a decision made under other weights cannot be admitted. Key Settings still
  lets the trader set other weights deliberately; pinning them to 30/25/15/20/10
  is an owner decision and was not made here.
- No Live order route: nothing under `services/nifty_algo/`, the NIFTY
  blueprints or `database/nifty_*.py` imports a broker order function;
  `LiveAdapterStub.submit` always raises `LIVE_NOT_READY`.
- Other blueprints reading a user id from the request: only the broker
  sign-in forms in `blueprints/brlogin.py`, which carry the broker client ID
  under the broker-login invariant, not an OpenAlgo account target.

Not changed, for the owner: the Angel adapter defaults a missing `open_interest`
to `0` in its normalized `oi` field, but the source observation NIFTY reads
uses `source_oi`, which stays `None`. A genuine OI of zero and a missing OI
score the same (the capped volume is zero either way), so ranking is
unaffected. N-05 (crossover-age wording) and N-01 (`openalgo.ta` parity tests)
are not addressed in this pass.

Verification of the second pass (Windows, Python 3.12, `uv run --no-sync`):

- Every file in CI's offline NIFTY step, plus `test_apikey_session_owner.py`,
  `test_logout_csrf.py` and `test_auth_logout.py`: **932 passed in 318.29 s**,
  after all Python changes.
- New `test_apikey_session_owner.py`: 14 cases. New
  `test_nifty_algo_strategy_integration.py`: 32 cases.
- Against HEAD in a temporary worktree: the oldest-session gap was ineligible,
  the dropped opening bucket was eligible, and PAPER OI was `None`. The new
  tests assert the corrected behaviour for each.
- An intermediate run with the master check in place but no fixture master
  failed 124 tests; with the shared fixture listing its contract, the
  remaining failures exposed the sparse-ladder broadening and the reason-order
  change described above, both fixed rather than worked around.
- `ruff check` clean on every changed Python file. Two older test files were
  already unformatted at HEAD and are left as they were. Biome and
  `tsc --noEmit` clean for the frontend label change. `git diff --check` clean.
- **PENDING GITHUB CI**: the full matrix (Python 3.12/3.13/3.14, gthread,
  eventlet, platforms) and the frontend jobs.

Verdict for this pass: **PARTIAL**, pending GitHub CI and real-feed validation
of OI availability, minute-history completeness and the listed ladder.
