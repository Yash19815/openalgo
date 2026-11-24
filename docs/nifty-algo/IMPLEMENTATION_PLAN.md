# NIFTY ALGO implementation tracker

> The paper-trading system's phase ledger (Phases 0–7 with commits and test
> counts) now lives in [PAPER_SYSTEM_DESIGN.md](PAPER_SYSTEM_DESIGN.md) §5.
> This file tracks the earlier v2 hardening work (phases A–F).

## Audit baseline and updated requirements

On 19 November 2026, work began on clean `main` at `d25122f2f`.
The existing 78 NIFTY tests passed. Code inspection found unsafe receipt-time
fallback, ignored displayed depth, hardcoded ticks, non-atomic distinct intent
admission, no persisted protection, and no runner. The previous Phase 6 DONE
claim was not supported by those safety cases.

The effective v2 rules are a maximum 8% initial filled-premium stop, a minimum
of [1.5, 2.0] option-premium points for the trailing distance, activation after
entry +1.5 premium points, and a deterministic confidence-sensitive 10–15%
profit target. Risk remains 0.5% of equity by default, including configured costs.

## Measured phase status

| Phase | Implementation | Evidence and remaining gate |
| --- | --- | --- |
| A Audit | Implemented | Branch/status checked; baseline 78 offline tests |
| B Risk and strength | Implemented; offline tested | Revisioned migration, deterministic contributions, tick-safe targets and durable protection |
| C Data and PCR | Connected in code; offline tested | Native history and source cache, current master, full expiry scope, OI/volume separation; real broker coverage remains unverified |
| D Automation | Implemented on native scheduler; offline tested | Separate named protection and entry jobs, durable lease/reservation, retries, recovery and isolated fills; production worker rehearsal remains pending |
| E Existing workspace | Implemented | Backend readiness controls Start; indicator contributions, protection, journal and rejection state are exposed |
| F Validation | In progress | See TESTING.md for measured commands and failures; no real historical or live-market evidence |

No phase label means profitable, calibrated, or ready for unattended deployment.
No live-order capability was added. The existing OpenAlgo application, routing,
login, broker setup, navigation, charts and option-chain tools remain in use.

## Remaining acceptance work

- Verify authenticated Angel source packets, complete expiry coverage and subscription capacity in a real NFO session.
- Rehearse application startup/shutdown under Linux eventlet and gthread, including a process restart with exposure.
- Resolve or separately isolate upstream test harness failures recorded in TESTING.md.
- Choose database archival/retention before prolonged forward operation.
- Record genuine historical observations and live-market paper evidence separately from deterministic fixtures.

## Changed files in this implementation

- [README.md](../../README.md)
- [app.py](../../app.py)
- [blueprints/nifty_algo.py](../../blueprints/nifty_algo.py)
- [broker/angel/streaming/angel_adapter.py](../../broker/angel/streaming/angel_adapter.py)
- [database/nifty_algo_db.py](../../database/nifty_algo_db.py)
- [docs/nifty-algo/ARCHITECTURE.md](../../docs/nifty-algo/ARCHITECTURE.md)
- [docs/nifty-algo/CHANGELOG.md](../../docs/nifty-algo/CHANGELOG.md)
- [docs/nifty-algo/IMPLEMENTATION_PLAN.md](../../docs/nifty-algo/IMPLEMENTATION_PLAN.md)
- [docs/nifty-algo/MASTER_DESIGN.md](../../docs/nifty-algo/MASTER_DESIGN.md)
- [docs/nifty-algo/MIGRATION_ANALYSIS.md](../../docs/nifty-algo/MIGRATION_ANALYSIS.md)
- [docs/nifty-algo/OPENALGO_REUSE_AUDIT.md](../../docs/nifty-algo/OPENALGO_REUSE_AUDIT.md)
- [docs/nifty-algo/READINESS_REPORT.md](../../docs/nifty-algo/READINESS_REPORT.md)
- [docs/nifty-algo/SAFETY_MODEL.md](../../docs/nifty-algo/SAFETY_MODEL.md)
- [docs/nifty-algo/SETUP.md](../../docs/nifty-algo/SETUP.md)
- [docs/nifty-algo/STRATEGY_ASSUMPTIONS.md](../../docs/nifty-algo/STRATEGY_ASSUMPTIONS.md)
- [docs/nifty-algo/TESTING.md](../../docs/nifty-algo/TESTING.md)
- [frontend/src/features/nifty-algo/Workspace.test.tsx](../../frontend/src/features/nifty-algo/Workspace.test.tsx)
- [frontend/src/features/nifty-algo/Workspace.tsx](../../frontend/src/features/nifty-algo/Workspace.tsx)
- [frontend/src/features/nifty-algo/api.ts](../../frontend/src/features/nifty-algo/api.ts)
- [services/market_data_service.py](../../services/market_data_service.py)
- [services/nifty_algo/assessment.py](../../services/nifty_algo/assessment.py)
- [services/nifty_algo/confidence.py](../../services/nifty_algo/confidence.py)
- [services/nifty_algo/config.py](../../services/nifty_algo/config.py)
- [services/nifty_algo/indicators.py](../../services/nifty_algo/indicators.py)
- [services/nifty_algo/market_data.py](../../services/nifty_algo/market_data.py)
- [services/nifty_algo/models.py](../../services/nifty_algo/models.py)
- [services/nifty_algo/native_data.py](../../services/nifty_algo/native_data.py)
- [services/nifty_algo/paper_executor.py](../../services/nifty_algo/paper_executor.py)
- [services/nifty_algo/protection.py](../../services/nifty_algo/protection.py)
- [services/nifty_algo/risk_manager.py](../../services/nifty_algo/risk_manager.py)
- [services/nifty_algo/runner.py](../../services/nifty_algo/runner.py)
- [services/nifty_algo/signal_engine.py](../../services/nifty_algo/signal_engine.py)
- [test/test_nifty_algo_core.py](../../test/test_nifty_algo_core.py)
- [test/test_nifty_algo_foundation.py](../../test/test_nifty_algo_foundation.py)
- [test/test_nifty_algo_paper_executor.py](../../test/test_nifty_algo_paper_executor.py)
- [test/test_nifty_algo_pipeline.py](../../test/test_nifty_algo_pipeline.py)
- [test/test_nifty_algo_v2.py](../../test/test_nifty_algo_v2.py)
