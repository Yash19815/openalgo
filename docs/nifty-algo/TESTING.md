# NIFTY verification record

All strategy market inputs used in this session are explicitly deterministic
offline fixtures. No real historical or live-market evidence is claimed.

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
