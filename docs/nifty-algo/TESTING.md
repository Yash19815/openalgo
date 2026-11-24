# NIFTY verification record

All strategy market inputs used in this session are explicitly deterministic
offline fixtures. No real historical or live-market evidence is claimed.

## Post-audit remediation verification - 21 November 2026

These results cover the uncommitted risk-bound, fill-revalidation and native
spot-reader remediation, not the earlier Phase 7 revision:

- Windows Python 3.12.11: **317 passed** in 733.24 s, exit 0:
  `.venv/Scripts/python.exe -m pytest test/test_nifty_algo_*.py -o addopts="" -q --basetemp=tmp/nifty-full-spot-03 -p no:cacheprovider`.
  Output: `tmp/nifty-full-spot-03.txt`.
- After adding malformed-LTP coverage and making the imported store fixture an
  explicit re-export, **88 passed** in 315.46 s, exit 0:
  `.venv/Scripts/python.exe -m pytest test/test_nifty_algo_gap_p1.py test/test_nifty_algo_phase5.py test/test_email_functionality_pytest.py test/test_smtp_error_messages.py test/test_smtp_certificate_verification.py test/test_gthread_messaging_email.py -o addopts="" -q --basetemp=tmp/nifty-final-focused-04 -p no:cacheprovider`.
  This includes the transport-trap self-test and PAPER/forced-LIVE full-cycle
  canaries. Output: `tmp/nifty-final-focused-04.txt`. The full matrix was not
  rerun after this test-only addition.
- After a whitespace-only `ruff format` pass on `test_nifty_algo_gap_p1.py`,
  the file was rerun standalone: **35 passed** in 141.37 s, exit 0
  (`--basetemp=tmp/nifty-gap-final`). `ruff format --check` and `ruff check`
  pass on all files changed in this diff.
- The three Analyzer-state pipeline cases passed independently in 28.17 s,
  exit 0, before the full matrix. A positive but insufficient bid triggers
  TARGET without filling; a zero-sized bid cannot be treated as executable.
- Ruff passed for `services/nifty_algo/`, `database/nifty_algo_db.py`,
  `blueprints/nifty_algo.py` and `test/test_nifty_algo_*.py`; whitespace checks
  passed. An order-API text scan of `services/nifty_algo/` found no matches.
- Resource review was **static**, limited to the changed paths: fill checks
  remain within the existing transaction/session context; engines still use
  `create_db_engine`/NullPool; fixture teardown disposes its engine. The spot
  reader borrows the shared market-data service and retains no quote history.
  No new client, socket, subscription, thread, executor or module-level cache
  was introduced. No measured descriptor/memory soak is claimed.

Native spot regressions cover source modes 1/2/3, missing timestamps,
stale/future/reversed timestamps, NaN/infinity/nonpositive prices, malformed
records and LTP, and display-only data. Invalid data leaves BUY pending without
creating a position; TTL expiry still removes the pending intent. Fixtures use
valid persisted configurations and premiums near 165, without relaxing the
400 planned-loss ceiling or 350 net-reward floor.

**Linux gate blocked; no commit or push.** `docker info --format '{{.OSType}}'`
cannot connect to `npipe:////./pipe/dockerDesktopLinuxEngine` (pipe not found).
`wsl --list --quiet` lists only `docker-desktop`, not a usable independent Linux
test distribution. The current diff has not passed the required Linux
eventlet/gthread checks. Run the repository's Linux commands, including
`test/test_gthread_*.py` with `--timeout=120 -rfs`, from a Linux-filesystem copy
before committing/pushing. Prior Linux results below do not cover this diff.

The existing Python-host closed-stream logging error still prints at interpreter
shutdown after passing pytest results. Real broker/feed startup, forward paper
observation, actual mailbox delivery, historical replay and a production-worker
rehearsal remain unverified. Live stays hard-blocked.

## Phase 7 verification — 21 November 2026

Final hardening checks against `4ff43de2c` plus the Phase 7 working diff:

- Linux Python 3.12.12: **311 passed** in 72.06 s: all 283 NIFTY
  tests plus 28 neighboring email/SMTP tests. Command:
  `.venv/bin/python -m pytest test/test_nifty_algo_*.py test/test_email_functionality_pytest.py test/test_smtp_error_messages.py test/test_smtp_certificate_verification.py test/test_gthread_messaging_email.py -o addopts="" --timeout=120 -rfs`.
- Full Linux runtime gate: **1,456 passed, 3 skipped** in 805.23 s.
  Command: `.venv/bin/python -m pytest test/test_gthread_*.py -o addopts="" --timeout=120 -rfs`.
  All three skips are documentation checks reporting no threading note about
  greenlets. The checkout and virtual environment reside in `/work` on the
  container filesystem; the container runs with `--init` to reap orphaned
  children. The direct-install eventlet test explicitly isolates Docker
  detection; the proxy orphan assertion remains unchanged. The eight NIFTY
  check-then-act sites were reviewed for transaction locking/object ownership.
  Normalized hashes of the changed Python files, reviewed-site file and Groww
  data module match the Windows checkout.
- Windows Python 3.12.11: **310 passed, 1 failed** in 1,199.13 s.
  The sole failure is the unchanged email diagnostic's
  `test_cli_help_does_not_require_pytest`: its subprocess exceeded 10 seconds.
  That same test passed in the Linux run above. Pytest cache permission
  warnings and the existing strategy-host atexit closed-stream logging error
  also occurred; the logging error recurred after successful Linux tests.
  A later isolated Windows diagnostic run using a writable `--basetemp` and
  `-p no:cacheprovider` passed in 5.00 s without changing the subprocess timeout.
  This does not replace the earlier full-run result.
- Windows Node 26.2.0: **26 NIFTY workspace tests passed** in 66.97 s with
  `node --no-experimental-webstorage node_modules/vitest/vitest.mjs run src/features/nifty-algo --pool=threads --maxWorkers=1`.
  Fork-pool runs could not start workers within their timeout. An attempted
  `npx --package=node@24.22.1` still resolved Node 26.2.0 and is not evidence
  of supported-Node validation.
- `node node_modules/typescript/bin/tsc -b` passed; production Vite build
  passed in 1m47s (8,346 modules) with output in `tmp/nifty-phase7-build`.
  Existing unresolved-runtime asset, plugin timing and large-chunk warnings
  remain. Tracked `frontend/dist` files were not rewritten.
- Ruff passed for all NIFTY services, database, blueprint, tests, the SMTP
  helper and the changed eventlet test; `git diff --check` passed.

Delivery audit regressions reproduce missing events for both expired claims and
`SKIPPED_NO_SMTP`, and the ability to clear an expired claim through the skip
method. Recovery and skip now record their outcome in the same transaction;
repeated calls create no duplicate event. Skipping requires no claim token or
lease, preserving the unknown-outcome hold until explicit recovery.

The resource review was static: report DB operations use session contexts,
PDF writes close descriptors and unlink temporary files on failure, SMTP closes
in `finally` after success or failure, and native settings/user sessions are
removed at the report scheduler boundary. The report service and its calendar
cache are recreated per tick; no new persistent thread, executor or registry was
introduced. This is not a measured long-running resource soak.

The broader frontend suite is **not green** under this installed Node version,
which is outside `package.json`'s supported range. Earlier full runs recorded
3,112 passes/588 failures; disabling experimental web storage improved this
to 3,683 passes, six timeouts and 11 skips, with seven failing files:
`openscriptStudiesChart.test.ts`, `openscriptHighlight.test.ts`,
`ChartDataDialog.test.tsx`, `PriceScaleMenu.test.tsx`, `AgentChat.retry.test.tsx`,
`Message.viz.test.tsx`, and `VizBlock.test.tsx`. Shared implementation and
assertions were not changed to mask those failures. No full-repository backend
or supported-Node full-frontend pass is claimed.

These are offline runtime and fixture checks. Genuine broker/feed startup,
extended forward paper observation and real SMTP deliverability remain
operator acceptance work.

### Earlier pre-hardening run

Run on the `feat/nifty-paper-trading-system` branch at `4ff43de2c` (Windows
checkout, `uv run pytest`, Node 26.2.0, npm + `package-lock.json`).

- **Feature suite: 280 passed** across all 15 `test/test_nifty_algo_*.py` files
  (55.88 s): v2 47, phase6 25, phase5 25, phase4 28, phase1 20, phase2 14,
  phase3b 12, calendar 12, pipeline 15, core 18, foundation 11, native_data 19,
  paper_executor 15, assessment 12, research 7.
- **Neighboring suites: 43 passed** — `test_nifty_algo_pipeline.py`,
  `test_email_functionality_pytest.py`, `test_smtp_error_messages.py`,
  `test_smtp_certificate_verification.py`,
  `test_gthread_messaging_email.py`. `test_email_functionality.py` is a manual
  diagnostic script with no collectable tests.
- **Ruff clean**: `services/nifty_algo/`, `database/nifty_algo_db.py`,
  `blueprints/nifty_algo.py`, `utils/email_utils.py`, `test_nifty_algo_*.py`.
- **Frontend: 26 vitest tests passed** (`Workspace.test.tsx` 7,
  `Panels.test.tsx` 19). `npm run build` (`tsc -b && vite build`) passed in
  2m39s, 8,346 modules; same existing unresolved-runtime asset and large-chunk
  warnings as before. Generated `frontend/dist` changes were restored, as
  before.
- **Environment caveat:** the shared `%TEMP%\pytest-of-hp` directory was owned
  by another context (WinError 5), causing 156 setup `PermissionError`s on the
  first run. All suites were run with `--basetemp` pointed at a writable
  directory; this is a machine issue, not a code issue.
- `git status` clean and `git diff --check` clean before and after.
- Safety invariants confirmed by grep (no order API anywhere in
  `services/nifty_algo/`; `LiveAdapterStub` submit always refuses;
  `live_readiness` always appends `LIVE_NOT_READY`). Evidence is listed in
  `PAPER_SYSTEM_DESIGN.md` §5.
- Unchanged since earlier runs: no Linux eventlet/gthread rehearsal, no real
  broker session, no historical replay. The pre-existing Python-host atexit
  logging error (`I/O operation on closed file` from
  `blueprints/python_strategy.py` cleanup) still prints after the suite exits;
  it does not affect the result.

## Measured checks on 19–20 November 2026

- Baseline: 78 existing NIFTY tests passed on clean `main` at `d25122f2f`.
- Updated feature suite: 142 tests passed, covering existing modules plus `test_nifty_algo_v2.py` and `test_nifty_algo_pipeline.py`.
- Existing workspace tests: all seven passed, including readiness-gated Start and strength contributions.
- `npm run build --prefix frontend` passed TypeScript project checks and the Vite production build. Vite reported existing unresolved-runtime asset and large-chunk warnings. Generated distribution changes were restored so the patch remains focused on source.
- Ruff checks and formatting apply to modified feature Python modules and tests.

Run the feature suite with the existing environment:

```powershell
.venv/Scripts/python.exe -m pytest test/test_nifty_algo_core.py test/test_nifty_algo_foundation.py test/test_nifty_algo_native_data.py test/test_nifty_algo_assessment.py test/test_nifty_algo_paper_executor.py test/test_nifty_algo_research.py test/test_nifty_algo_v2.py test/test_nifty_algo_pipeline.py -q --tb=short
npm run test:run --prefix frontend -- src/features/nifty-algo
npm run build --prefix frontend
```

The full simulator uses real feature calculations over synthetic minute history,
a complete artificial expiry master and timestamped CE/PE observations. It
checks five-gate qualification, strength/target selection, paper entry,
protection, kill-state exits, journal net P&L and zero generic order calls for
Analyzer enabled, disabled and changed during exposure. The artificial calendar
includes explicitly labeled synthetic sessions; it is not exchange history.

Other regressions cover independent indicator references, no look-ahead,
missing session-open VWAP data, incomplete/stale PCR, invalid master rows,
source-time preservation, missing OI, subscription acknowledgments, duplicate
signals, concurrent distinct admission, a control change at the database write,
quantity override rejection, tick rounding, insufficient depth, fill-time risk,
partial-exit fees, expired exit retry, restart peaks, immutable entry settings,
legacy migration/emergency protection, user isolation, CSRF and session cleanup.

## Upstream regression observations

A combined run of Angel quote tests, Python strategy host tests, strategy
recovery and risk tests produced 108 passes and 59 failures. The recovery
failures reported `sqlite3.OperationalError: no such table: sm_strategy`.
`test_python_strategy_edge_cases.py` assigns `DATABASE_URL=sqlite:///:memory:`
at import; the recovery store uses NullPool, so that combined collection loses
its tables across connections. Recovery/risk then passed all 98 tests in a separate process, avoiding this pre-existing harness interaction.
No shared strategy engine or test isolation rule was changed to hide failures.

The existing Python-host atexit logger also reports `ValueError: I/O operation
on closed file` after pytest capture shuts down. This occurred at baseline and
does not change pytest's passing exit result.

Windows runs do not verify the Linux eventlet/gthread production matrix.
A full locked-dependency application boot, real native authentication,
exchange-time stream verification, production-worker rehearsal and extended
forward paper observation remain pending. Historical option-depth replay is
not implemented without a real validated dataset; the existing research
boundary still refuses invented option-premium history.

## Resource review

Database work uses short-lived sessions and the existing engine factory.
No feature thread, executor, scheduler, HTTP pool or broker login was added.
Native scheduler jobs are named/coalesced and bounded to one instance each.
Callback replacement and shutdown remove registered callbacks; runner ownership
is durable. Futures history is bounded to nine days/10,000 minute rows. Durable
events, decisions and depth-use proofs need an archival policy for long runs.

The broader frontend suite was also invoked directly through Vitest with two
workers. Installed Node is 26.2.0, outside package.json's supported ranges
(^22.23.4, ^24.22.1, or >=26.12.1). Unchanged chart/auth tests report
`TypeError: Cannot read properties of undefined (reading 'clear')` and a native
localStorage warning. A process-only storage flag check is recorded separately;
no shared frontend implementation or assertions were changed to hide failures.
The unmodified-runtime run finished with 3,112 passes and 588 failures across
274 files. With `NODE_OPTIONS=--no-experimental-webstorage`, a focused storage
check passed all 32 tests. The full run with that flag and four workers finished
with 3,683 passes, six test timeouts and 11 skipped tests; 267 files passed and
seven files failed. Two additional suite hooks timed out at 30 seconds.
The six tests timed out at five seconds. Affected files were
`openscriptStudiesChart.test.ts`, `openscriptHighlight.test.ts`,
`ChartDataDialog.test.tsx`, `PriceScaleMenu.test.tsx`, `AgentChat.retry.test.tsx`,
`Message.viz.test.tsx` and `VizBlock.test.tsx`. None of those files was changed.
The broader frontend run is not green. These failures are retained as measured
limitations; no assertions or shared chart/agent implementation were weakened.
A supported Node installation and production-worker validation remain separate
acceptance work.

Shared-file Ruff inspection reports existing import-order/deprecated-typing
issues in app.py, market_data_service.py and angel_adapter.py. Focused NIFTY
module/test checks pass. Fees use the ledger's four-decimal precision and
remaining entry fees are conserved across uneven partial exits. Performance
aggregates the entire durable journal rather than its 200-row display page.
Equity is explicitly labeled book cost, not mark-to-market.


## Final recovery and event checks

Recovery now compares book cash with held cost, validates entry/exit fill
references, reconciles entry quantities against open positions and closed
trades, and checks entry/exit reservations. SQL aggregates avoid loading full
history into the application worker. Inconsistent durable state blocks entries;
sell coverage is also checked against confirmed fills at admission and fill.
Tests inject cash, quantity and entry-status inconsistencies. Legacy recorded
peaks cannot restart at a looser initial stop; uncertain profitable legacy
exposure requests an observed-depth closure without inventing confidence.

A delayed heartbeat cannot shorten the owner lease. An invalid current config
cannot suppress read-only feed recovery for held exposure. A closed runner
cannot recreate its lease. Signed Socket.IO subscriptions ignore caller-supplied
users, rejoin after reconnect and remove listeners on unmount. Admission events
retain atomic risk approval separately from immutable pre-admission assessments.


Final source validation also passed the Vite production build using
`vite build --outDir ../tmp/nifty-production-validated` and TypeScript `tsc -b`.
The temporary output keeps tracked distribution assets intact. Focused Biome
checks pass after using semantic status outputs in the existing workspace.
Native client replacement removes adopted NIFTY callbacks before registration,
and resets subscription ownership so borrowed replacement-client subscriptions
are not removed as though NIFTY owned them. The final focused lifecycle rerun
covers this reconnect case without creating another broker session.
