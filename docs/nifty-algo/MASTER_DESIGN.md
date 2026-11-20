# NIFTY ALGO technical design

Audit baseline is local branch `main`, commit `de8456ab38d722fd1fd3b83b8c97ed6895684945`, inspected 19 November 2026. The local checkout is the implementation authority. The earlier [migration inventory](MIGRATION_ANALYSIS.md) covers all 98 tracked legacy files.

## Scope and ownership

This document preserves the original design proposal. Its shared-Sandbox execution plan is superseded by the isolated feature ledger described in [ARCHITECTURE.md](ARCHITECTURE.md) and [SAFETY_MODEL.md](SAFETY_MODEL.md). Current rules and implementation evidence are in [STRATEGY_ASSUMPTIONS.md](STRATEGY_ASSUMPTIONS.md) and [TESTING.md](TESTING.md).

The feature extends the existing Flask application, React 19 client and native Python strategy scheduler. `services/nifty_algo/` owns pure rules and feature orchestration. `database/nifty_algo_db.py` owns feature state and the isolated paper ledger within the existing main database. `blueprints/nifty_algo.py` provides authenticated, CSRF-protected browser endpoints. The frontend remains in `frontend/src/features/nifty-algo/`.

Orders require a server-side validated NIFTY NFO option, current risk approval, reconciliation and an execution profile that satisfies the requested simulation rules. All account-changing calls must use native Sandbox capabilities. The feature must fail closed while strict fills and isolated account accounting remain unavailable.

The default research capital is INR 100000. This value must not reset the shared native Sandbox balance. Account isolation must preserve unrelated strategies. Position and cash state must come from confirmed Sandbox fills. Configuration, daily locks, decision IDs and run identity must survive process restarts.

## Input and rule contracts

Analyze NIFTY spot separately from a dated NIFTY future. Use that future’s OHLCV for directional indicators and session VWAP. Aggregate complete constituent minutes for 5m entries and 15m confirmation. Preserve source and receipt clocks. Bind PCR to a complete explicitly named expiry universe with verified timestamps and separate OI and volume variants. Missing data blocks entries.

All combined strategy parameters are research assumptions until independently verified. Rules are deterministic and versioned. Every assessment records pass, fail and unavailable checks, candidate, risk result and final action. Persist rejected and unavailable assessments too. Research consumes the same pure rules and never changes the operational paper account.

## Integration gates

1. Validate and test pure rules and contract restrictions.
2. Persist authenticated feature state and configuration safely.
3. Adapt real native market data with trustworthy provenance and complete universe coverage.
4. Extend native Sandbox only where necessary for strict bid/ask fills, independent accounting, fees, latency, order expiry and supported partial quantities.
5. Add atomic intent claims, reconcile ambiguous submissions and persist protective exit state.
6. Register the runner through `/python`, using NFO effective sessions and native scheduling.
7. Bind the Stitch-derived workspace to backend observations and expose readiness failures.

See [safety model](SAFETY_MODEL.md), [reuse audit](OPENALGO_REUSE_AUDIT.md), [architecture](ARCHITECTURE.md) and [phase tracker](IMPLEMENTATION_PLAN.md).
