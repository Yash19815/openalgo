# Native capability reuse audit

Baseline `de8456ab38d722fd1fd3b83b8c97ed6895684945`. Detailed legacy disposition lives in [MIGRATION_ANALYSIS.md](MIGRATION_ANALYSIS.md).

The table below records the original capability audit, not the active execution
design. The implemented NIFTY path uses `NiftyPaperExecutor` and feature-owned
accounts, orders, positions, protection and journals in the existing main
database. It does not dispatch through shared Sandbox order/fund managers.
Native broker data, calendar, authentication, scheduler, event transport,
engine factory and frontend components are reused. Shared consumers continue
to use `services/risk/`; NIFTY paper protection is an intentional exception
implemented only by the isolated, pure Decimal evaluator in
`services/nifty_algo/protection.py`. Its formulas must not be copied elsewhere.
See [ARCHITECTURE.md](ARCHITECTURE.md) and [TESTING.md](TESTING.md) for the
current implementation and evidence.

| Feature | Existing file or service | Reuse | Required change | Risk | Test plan |
| --- | --- | --- | --- | --- | --- |
| Flask API registration | `app.py`, `blueprints/` | Yes | Register scoped blueprint | Route regressions | Authenticated API and import tests |
| Session and CSRF | `utils/session.py`, Flask-WTF setup in `app.py` | Yes | Existing decorators and CSRF-aware web client | Unauthorized mutation | Signed-out and missing-CSRF rejection |
| REST data | `services/quotes_service.py`, `depth_service.py`, `history_service.py` | Yes | Normalize source identity and timestamps | Stale/future data | Boundary fixtures |
| Streaming and reconnect | `websocket_proxy/`, `services/market_data_service.py` | Yes | Scoped subscriptions and bounded windows | Resource retention | Disconnect and teardown tests |
| Angel connection | `broker/angel/` | Yes | Read-only adapter consumption | Feed token expiry | Normalized observations and pending real session test |
| Calendar | `database/market_calendar_db.py` | Yes | Query effective NFO session | Holiday/effective date | Session boundary fixtures |
| Symbol master | `database/symbol.py`, `services/option_symbol_service.py` | Yes | Strict NIFTY structured selection | Wrong underlying or expiry | CE/PE and metadata rejection tests |
| Option chain | `services/option_chain_service.py` | Yes | Verify complete scoped observations | Missing fields become zero | Missing-leg and timestamp tests |
| OI and volume PCR | `services/oi_tracker_service.py` | Partial | Its 47-strike window and zero-denominator result cannot satisfy full-universe strategy PCR | False availability | Independent full-scope ratio fixtures |
| Indicators | `openalgo.ta`, `services/risk/` | Yes where equivalent | Validate seeds, SuperTrend sign and session resets | Changed signals | Independent hand references and parity |
| Strategy host | `blueprints/python_strategy.py`, `strategies/` | Yes | Single version-controlled runner | Restart duplicates | Actual host validation and rehearsal |
| Scheduling | Native Python scheduler | Yes | NFO schedule and cooperative stop | Abandoned exposure | Session and stop tests |
| Orders | `services/sandbox_service.py` | Partial | Dedicated strict profile and risk approval boundary | LTP fallback | Native Sandbox integration and broker spies |
| Positions and P&L | `sandbox/position_manager.py`, `database/sandbox_db.py` | Yes | Strategy/account ownership and reconciliation | Shared exposure | Fill and cash invariants |
| Paper funds | `sandbox/fund_manager.py` | Partial | Isolate NIFTY capital without resetting another account | Cross-strategy balance | Isolation tests |
| Fees and fills | `sandbox/execution_engine.py`, `order_manager.py` | Partial | Effective fees, bid/ask-only, latency, expiry, supported partials | Misleading results | Hand accounting and quote-event replay |
| Risk and protection | `services/risk/`, `services/nifty_algo/protection.py` | Shared consumers use the common core; NIFTY paper protection remains isolated | Pure Decimal floor, trail and discretionary-booking evaluator; DB and runner persist/translate results | Formula drift or cross-domain duplication | Decimal boundaries, monotonic stops, restart recovery and event tests |
| Persistence | `database/engine_factory.py` | Yes | Add feature tables within main DB | Leaks and lost updates | Repeated operations and CAS tests |
| Events and logs | `events/`, `extensions.py`, `utils/logging.py` | Yes | Publish feature decisions and fills | Secrets and subscriptions | Redaction and cleanup tests |
| React shell | `frontend/src/App.tsx`, `components/layout/` | Yes | Authenticated NIFTY workspace | Navigation regressions | Routes and empty/error states |
| UI and charts | `components/ui/`, `openalgo-charts` | Yes | Stitch screen mapping and real data binding | Source confusion | Build and UI contracts |
| Historical research | `services/historify_service.py`, `database/historify_db.py` | Yes | Causal signal study and dataset coverage | Fake option premiums | Signal-only and option-data gating |

Installed dependency baseline is declared in `pyproject.toml`, `uv.lock` and `frontend/package-lock.json`. A clean target environment was absent during the audit. Local tests use a scoped environment and are reported separately from full locked-dependency and Linux worker validation.
