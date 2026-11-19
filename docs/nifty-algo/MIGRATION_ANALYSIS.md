# NIFTY ALGO migration analysis

Source is the sibling `../trader-bot/` checkout, version `0.1.0`, commit `cf7acb4`. Target is this OpenAlgo fork, inspected at `de8456ab3`. This is a static review of all 98 tracked source files. Paths in the inventory are relative to `trader-bot`. OpenAlgo paths are named explicitly. The legacy app, database, providers, tests and order paths were never run. Local databases, caches, virtual environments and installed dependencies were excluded.

The reusable core is the deterministic NIFTY decision evaluator, indicator reference behavior, strategy-specific entry and exit policy, research coverage rules, analytics and UI presentation. OpenAlgo already provides the broker plugin, instrument master, market-data transport, calendar, strategy lifecycle, shared risk evaluation, Sandbox order and trade records, authentication and frontend shell.

## OpenAlgo integration boundaries

| Concern | Existing OpenAlgo surface | Migration decision |
| --- | --- | --- |
| Strategy lifecycle | `blueprints/python_strategy.py` and `workspace/execution/` for single-file hosted scripts. `services/strategy_module/` for managed runs, signals, scheduling, reconciliation, risk and audit. | Use whichever host the implementation prompt specifies. Keep the decision evaluator callable from paper execution and research. The Python host copies one file into `strategies/scripts/` and runs it with OpenAlgo’s interpreter. It requires a Sandbox-only submission path before the strategy can send orders. |
| Paper execution | `services/sandbox_service.py` and `sandbox/`. `services/strategy_module/order_dispatch.py` demonstrates explicit per-run Sandbox dispatch for placement, cancellation and status. | Bind NIFTY order placement, exits, cancellation and order/position reads to Sandbox. Set the mode in server-side code or call the Sandbox service directly after validation and authentication. Reject any other mode and return Sandbox failures without retry through another route. Include read and recovery paths in the check. |
| Analyzer mode | `services/place_order_service.py` and `services/place_smart_order_service.py` route ordinary orders based on the mutable platform Analyzer flag. The strategy module supports a separate explicitly live branch. | A startup Analyzer check leaves a race when the global mode changes. Keep generic SDK order calls, actionable live-enable controls, `force_live` and broker order modules outside the NIFTY order path. Test with Analyzer off, a working Angel session, Sandbox failure and a mode change between entry and exit. |
| Read-only Angel One data | `broker/angel/api/data.py`, `broker/angel/streaming/angel_adapter.py`, `services/market_data_service.py`, `services/quotes_service.py`, `services/depth_service.py`, `services/history_service.py`. | Use the existing authenticated connections. Preserve exchange/source time and receipt time separately wherever the upstream path supplies them. The Angel adapter can emit a local transport timestamp, so that field alone cannot establish exchange freshness. Fail the relevant entry gate if required timestamps, depth or provenance are unavailable. |
| Instrument choice and sessions | `database/symbol.py`, `services/symbol_service.py`, `services/expiry_service.py`, `services/option_symbol_service.py`, `services/option_chain_service.py` and `database/market_calendar_db.py`. | Use listed expiry, strike, lot and tick metadata and the effective exchange session window. Retain the legacy strategy’s selection and liquidity rules where required. Use the NIFTY future for indicators and the spot reference for strike selection. Tie-breaks, expiry-day exclusions and synchronized Greeks require fixtures. |
| PCR inputs | `services/option_chain_service.py` can supply the chain universe and quoted legs. Its response defaults missing quote fields to zero and includes a response `server_ts`. | Keep the expected CE/PE universe separate from actual, timestamped observations. `server_ts` cannot establish per-leg freshness. Unverified scope, missing fields or a truncated strike universe must produce unavailable PCR. Require explicit OI or volume definition and retain the oldest observed leg time. |
| Risk and accounting | `services/risk/` for stop, target, trail and aggregate risk rules. `sandbox/` and `database/sandbox_db.py` for simulated positions, orders, fills, funds and square-off. | Adapt NIFTY-specific sizing, entry caps, health/session gates and technical exits. Use the shared risk evaluator for overlapping rules. Reconcile against Sandbox state and distinguish strategy-owned exposure before flattening. Persist only strategy-specific context, such as immutable settings, decision IDs and active locks, where the chosen host lacks it. |
| Historical research | `services/history_service.py`, `services/historify_service.py`, `database/historify_db.py`, the Python host’s strategy backtest helper and the chart terminal’s research UI. | Use native history and catalog data for a closed-candle study. Require timestamped option quotes, actual depth and dated metadata for the legacy quote-replay model. Candle or OI history alone cannot establish execution liquidity or causal option fills. Keep research isolated from the operational Sandbox account. |
| Frontend | `frontend/src/App.tsx`, `frontend/src/api/client.ts`, `frontend/src/components/ui/`, existing `/trading`, `/strategy`, `/sandbox`, `/scalping`, `/historify` and option-chain views. | Rebuild only strategy-specific panels inside the authenticated shell with existing queries, CSRF-aware client, components and charts. Strategy controls and status must resolve to the paper path server-side. |

### Execution and research semantics to verify

- The legacy paper executor models displayed size, delayed eligibility, adverse ticks, partial fills, limits and order expiry. OpenAlgo Sandbox has different fill rules. `sandbox/execution_engine.py` can fall back to LTP for market orders, `sandbox/order_manager.py` can match marketable limits at LTP, and the WebSocket execution path can set bid and ask from LTP. A fresh-depth entry gate alone cannot guarantee depth-based fills later. Record the actual Sandbox model in results. If strict depth-only execution is required, verify an appropriate native path before enabling submissions.
- Legacy SuperTrend encodes bullish as `+1`. OpenAlgo’s Python strategy guidance documents the SDK encoding as `-1` for uptrend. Verify sign, initial state, crossover age, warm-up and session reset against legacy fixtures before substituting SDK indicators. The legacy thresholds are research assumptions and the original video was not verified.
- The legacy aggregator expects one instrument and anchors to 09:15 IST. A port must align to the effective session and keep futures rolls and mixed instruments out of a single aggregate. The rule evaluator and signal study require ordered, complete bars. No synthetic candle, premium, PCR, fill or forced final liquidation belongs in reported results.
- The replay preflight accepts any option quote and any depth event anywhere in the dataset. Require depth on the relevant option legs, current as of each simulated decision or fill. Legacy replay also sets `verified` from a caller-supplied assertion. Carry dataset provenance through the adapter and report missing coverage explicitly.
- Preserve fail-closed behavior on stale or unavailable data, entry idempotency across restarts, one-position and pending-entry checks, and persistent lockouts where required. A submitted order is distinct from an accepted order or a fill. Retry an exit only after reconciling Sandbox quantity and order state. If using a Sandbox smart close, verify the zero-quantity, zero-target form on an already flat position.

## File-by-file inventory

**Port** means reuse the identified behavior or implementation after checking its inputs. **Adapt** means retain strategy-specific behavior or presentation within OpenAlgo’s interfaces. **Reference** means use as evidence, fixtures or design guidance. **Exclude** means leave the legacy file out of the migration.

### Backend domain, strategy and runtime

| Source file | Disposition | Reusable portion and target boundary |
| --- | --- | --- |
| `backend/app/__init__.py` | Exclude | Legacy package marker. |
| `backend/app/domain.py` | Adapt | Closed candle, quote validity, PCR metadata and clock contracts as needed at the strategy boundary. Use OpenAlgo’s instrument identity and order types. |
| `backend/app/strategy.py` | Port | Snapshot and `Rules.evaluate` with 5m and 15m inputs, deterministic IDs, pass/fail/unavailable checks, and CE/PE bias. Keep signal strength separate from eligibility to submit. |
| `backend/app/config.py` | Adapt | `StrategyConfig` validation, ordered parameters and immutable version semantics. Leave legacy `.env` loading, standalone database/auth/provider settings and execution flags behind. |
| `backend/app/instruments.py` | Adapt | Deterministic ATM/ITM/OTM and optional delta policy, plus freshness, spread, volume and size checks. Resolve metadata through OpenAlgo and require trusted Greeks for delta mode. |
| `backend/app/market_data.py` | Adapt | Complete-window aggregation and duplicate, regression and missing-volume invariants. Use OpenAlgo history and feed services as the data owners. |
| `backend/app/calendar.py` | Reference | Bounded date and permitted-window behavior for calendar tests. Use OpenAlgo’s effective sessions and exchange calendar. |
| `backend/app/risk.py` | Adapt | Fee-aware whole-lot sizing, stale valuation labels, single-position and pending-entry rules, caps and gates. Remove legacy SQLAlchemy reads and use Sandbox state, the native calendar and shared RMS. |
| `backend/app/engine.py` | Adapt | Decision deduplication, entry eligibility, technical ATR/SuperTrend and time exits, and state transitions. Reuse the host for lifecycle and recovery, shared RMS for price exits, and Sandbox for execution. |
| `backend/app/runtime.py` | Exclude | Standalone async ingestion, queue, provider lifecycle, backfill and polling. Its restart and health behavior informs integration tests. |
| `backend/app/api.py` | Reference | Dashboard, settings, decision, audit, journal, CSV, chart, dataset and replay contracts. Use OpenAlgo’s native authentication and routing for missing feature surfaces. Leave FastAPI, bearer auth and the standalone WebSocket server behind. |
| `backend/app/main.py` | Exclude | Standalone ASGI entry point. |
| `backend/app/persistence.py` | Reference | Decision, configuration and provenance event fields, and accounting invariants. Use native Sandbox and run stores for balances, trades, orders and recovery. |
| `backend/app/data_providers/__init__.py` | Exclude | Legacy provider package marker. |
| `backend/app/data_providers/angel.py` | Reference | Binary packet scales, timestamp, depth, OI and symbol-master test cases. Reuse the fork’s Angel provider, master and streaming adapter. |
| `backend/app/execution/__init__.py` | Exclude | Legacy execution package marker. |
| `backend/app/execution/paper.py` | Reference | Acceptance cases for idempotency, quote causality, bounded fills, fee allocation and no uncovered sells. Use OpenAlgo’s Sandbox for operational paper trading. |
| `backend/app/execution/charges.py` | Adapt | Effective-dated estimates and first-fill fee allocation semantics for strategy sizing or research when required. Keep estimates distinct from native accounting and broker charges. |
| `backend/migrations/env.py` | Exclude | Legacy Alembic runtime setup. |
| `backend/migrations/script.py.mako` | Exclude | Legacy Alembic revision template. |
| `backend/migrations/versions/9deaacf326e1_initial_paper_trading_ledger.py` | Exclude | Standalone ledger schema. Existing Sandbox records own simulated orders and balances. |
| `config/calendar.json` | Reference | Legacy bounded schedule and special-session fixtures. OpenAlgo owns the calendar. |
| `config/charges.json` | Reference | Historical fee estimate inputs and effective-date fixture. Verify a rate’s validity for the replay date before using it. |

### Indicators, backtesting and analytics

| Source file | Disposition | Reusable portion and target boundary |
| --- | --- | --- |
| `backend/app/indicators/__init__.py` | Reference | The legacy indicator facade and public function names. Use the target module’s actual interface. |
| `backend/app/indicators/common.py` | Reference | SMA seed, Wilder/EMA smoothing and true-range behavior for parity checks against `openalgo.ta`. |
| `backend/app/indicators/supertrend.py` | Adapt | Recursive bands, direction, ATR, flip and duration. Validate native output conventions and retain snapshot fields the strategy consumes. |
| `backend/app/indicators/macd.py` | Adapt | MACD line, signal, histogram and crossover direction/age. Reuse matching SDK calculations and derive missing signal metadata causally. |
| `backend/app/indicators/adx.py` | Adapt | ADX strength and optional DI direction. Compare Wilder smoothing, seed and flat-series behavior with SDK output. |
| `backend/app/indicators/vwap.py` | Port | Same-future, session-reset VWAP with typical/close basis and full-session invalidation after missing volume. Substitute the native indicator only after parity checks. |
| `backend/app/indicators/pcr.py` | Port | Complete, dated, one-expiry OI/volume ratio with freshness, scope, oldest observation and coverage checks. Feed it native metadata and observed quotes. |
| `backend/app/backtesting.py` | Adapt | Causal signal study, replay clock, receipt ordering, coverage report and walk-forward windows. The legacy replay instantiates `Engine`, `Store` and a paper executor. Reuse its research contracts without importing operational infrastructure. Define non-overlapping train/test boundaries explicitly. |
| `backend/app/analytics.py` | Port | Decimal-based net results, partial-exit consolidation and trade-level equity, drawdown, win-rate and groupings. Adapt Sandbox/research inputs and label realized versus marked series. |

### Backend tests

| Source file | Disposition | Reusable portion and target boundary |
| --- | --- | --- |
| `backend/tests/conftest.py` | Adapt | Deterministic clock, candle, instrument and quote fixtures. Convert them to native service contracts and isolated test storage. |
| `backend/tests/test_strategy.py` | Port | Bull/bear decisions, conflicts, stale/missing/PCR inputs and optional previous-level gate. Assert documented semantic parity after adapting models. |
| `backend/tests/test_indicators.py` | Port | Hand references, warm-up, recursive flips, crossover, flat ADX, VWAP reset, scoped PCR and no incomplete/future aggregates. Reuse duplicate and out-of-order cases at the native data boundary. |
| `backend/tests/test_reference.py` | Reference | Independent ADX, MACD and VWAP comparisons. Use checked fixtures or available test dependencies. |
| `backend/tests/test_foundation.py` | Adapt | Config/schema edges, NIFTY-only instruments, calendar transitions and inability to enable live mode. Replace the legacy factory test with entry-point tests against broker order dispatch. |
| `backend/tests/test_provider.py` | Reference | Packet/REST normalization, quote-time and depth errors, master contract parsing and read-only allowlist cases for testing the OpenAlgo data boundary. |
| `backend/tests/test_execution.py` | Adapt | Idempotency, no uncovered sell, position/risk checks, safe disconnect, lot sizing and fee cases. Distinguish native Sandbox contracts from legacy depth, latency and partial-fill fixtures. |
| `backend/tests/test_api_engine.py` | Adapt | Decision-to-paper workflow, restart and daily lockout, stale-data exits, authentication, replay coverage and hand-calculated metrics. Replace the FastAPI test client and legacy persistence with OpenAlgo fixtures. |

### Frontend source and build files

| Source file | Disposition | Reusable portion and target boundary |
| --- | --- | --- |
| `frontend/src/main.tsx` | Reference | Page hierarchy, query invalidation and connection status transitions. Use the fork’s router, auth and streaming. |
| `frontend/src/api.ts` | Adapt | INR, numeric and IST formatting where native helpers lack equivalents. Use OpenAlgo’s session-aware client for data and controls. |
| `frontend/src/types.ts` | Adapt | Decision, indicator, freshness, chart, journal and research view models. Source account and order types from OpenAlgo contracts. |
| `frontend/src/components.tsx` | Adapt | Rule matrix, unavailable state and intent for money, metrics and tables. Reuse OpenAlgo UI primitives and position components. |
| `frontend/src/charts.tsx` | Adapt | Overlay/pane composition for SuperTrend, VWAP, MACD, ADX and PCR, paper markers and equity curve. Use OpenAlgo’s chart layer and existing backtest components. |
| `frontend/src/pages/Overview.tsx` | Adapt | Strategy confluence, next action/status and differentiated futures/spot data. Use native marks, account state and cards. |
| `frontend/src/pages/ChartPage.tsx` | Adapt | Timeframe selector and chart empty states. Integrate with native charts and validated data. |
| `frontend/src/pages/Decisions.tsx` | Adapt | Latest rule matrix, candidate rationale, history and filtering. Drive it from persisted decision snapshots. |
| `frontend/src/pages/TerminalPage.tsx` | Adapt | Paper run controls and visibility into orders and positions. Use authenticated native Sandbox or run APIs and strategy ownership checks. |
| `frontend/src/pages/Journal.tsx` | Adapt | Filtered journal, trade drilldown, linked decision/risk context and CSV behavior. Use target trade records and feature audit fields. |
| `frontend/src/pages/Analytics.tsx` | Adapt | Realized equity, drawdown, metrics and group breakdowns with paper labeling. Feed it verified analytics. |
| `frontend/src/pages/Research.tsx` | Adapt | Dataset coverage, run form, progress, limitations and replay output. Use native historical catalogs and the paper/research data boundary. |
| `frontend/src/pages/Settings.tsx` | Adapt | Indicator and risk form, validated saves, version display and paused-state behavior. Keep live execution out of the available controls. |
| `frontend/src/pages/Health.tsx` | Adapt | Read-only status for data integrity, last observation and provider/replay readiness. Reuse OpenAlgo health and authentication. |
| `frontend/src/styles.css` | Reference | Information density, numeric alignment and chart readability. Keep OpenAlgo theme tokens and scoped feature styling. |
| `frontend/index.html` | Exclude | Standalone React HTML entry. |
| `frontend/package.json` | Reference | Legacy dependency list and build commands. Resolve required capabilities through the fork’s toolchain. |
| `frontend/package-lock.json` | Exclude | Standalone frontend dependency lock. |
| `frontend/tsconfig.json` | Exclude | Standalone TypeScript project configuration. |
| `frontend/vite.config.ts` | Exclude | Standalone dev server and localhost proxy. |

### Design assets

| Source file | Disposition | Reusable portion |
| --- | --- | --- |
| `stitch_nifty_algo_trading_terminal/obsidian_algorithmic_terminal/DESIGN.md` | Reference | UI hierarchy and visual vocabulary for the user’s existing design. OpenAlgo owns global tokens and navigation. |
| `stitch_nifty_algo_trading_terminal/advanced_live_charts/code.html` | Reference | Chart view layout, indicator control placement and panel organization. |
| `stitch_nifty_algo_trading_terminal/advanced_live_charts/screen.png` | Reference | Advanced chart visual baseline. |
| `stitch_nifty_algo_trading_terminal/backtesting_and_historical_replay_lab/code.html` | Reference | Data coverage, replay controls and result layout. |
| `stitch_nifty_algo_trading_terminal/backtesting_and_historical_replay_lab/screen.png` | Reference | Research lab visual baseline. |
| `stitch_nifty_algo_trading_terminal/main_trading_dashboard/code.html` | Reference | Overview layout and information hierarchy. |
| `stitch_nifty_algo_trading_terminal/main_trading_dashboard/screen.png` | Reference | Dashboard visual baseline. |
| `stitch_nifty_algo_trading_terminal/paper_trading_terminal/code.html` | Reference | Paper-control and position/order presentation. |
| `stitch_nifty_algo_trading_terminal/paper_trading_terminal/screen.png` | Reference | Paper terminal visual baseline. |
| `stitch_nifty_algo_trading_terminal/performance_analytics/code.html` | Reference | Metrics and equity/drawdown placement. |
| `stitch_nifty_algo_trading_terminal/performance_analytics/screen.png` | Reference | Analytics visual baseline. |
| `stitch_nifty_algo_trading_terminal/signal_monitor/code.html` | Reference | Decision checks, status and history layout. |
| `stitch_nifty_algo_trading_terminal/signal_monitor/screen.png` | Reference | Signal monitor visual baseline. |
| `stitch_nifty_algo_trading_terminal.zip` | Exclude | Archived bundle. Use the checked-in design files directly. |

The design exports are mockups. Example prices, P&L and statuses have no data provenance and should never appear as observations in the migrated UI.

### Documentation, tooling and deployment

| Source file | Disposition | Reusable portion and target boundary |
| --- | --- | --- |
| `docs/STRATEGY_RULES.md` | Reference | Rule IDs, order eligibility semantics, snapshot/dedup policy and contract selection. |
| `docs/STRATEGY_ASSUMPTIONS.md` | Reference | Parameter defaults and explicit research assumptions, plus limits of stop execution and data coverage. |
| `docs/VIDEO_STRATEGY_ANALYSIS.md` | Reference | Indicator-to-rule provenance and explicit distinction between secondary summaries and unverified primary material. |
| `docs/RISK_MANAGEMENT.md` | Reference | Strategy gates, circuit breakers and session policy. Adapt to native RMS and exchange schedules. |
| `docs/PAPER_TRADING.md` | Reference | Legacy paper model and tests for reconciliation and outage behavior. Describe target fill behavior using OpenAlgo implementation evidence. |
| `docs/DATA_SOURCES.md` | Reference | Data provenance, dataset coverage and entitlement constraints. Native OpenAlgo services supply data. |
| `docs/ANGELONE_INTEGRATION.md` | Reference | Read-only provider and entitlement assumptions. Future live execution in the document is outside this migration. |
| `docs/ARCHITECTURE.md` | Reference | Legacy dependency map and separation between research and observed paper state. |
| `docs/IMPLEMENTATION_PLAN.md` | Reference | Legacy phase and acceptance register. It describes standalone infrastructure and a future live design. No OpenAlgo-specific master prompt was located in either checkout. |
| `README.md` | Reference | Workflow, UI inventory and known data/replay limits. Standalone service startup and credential instructions belong to the old app. |
| `CHANGELOG.md` | Reference | Legacy release scope and recorded limitations. |
| `.dockerignore` | Exclude | Standalone image build ignore rules. |
| `.env.example` | Exclude | Standalone settings and credential template. Use OpenAlgo configuration. |
| `.gitignore` | Exclude | Legacy project ignore policy. |
| `Dockerfile` | Exclude | Standalone backend/frontend image definition. |
| `alembic.ini` | Exclude | Standalone database migration configuration. |
| `docker-compose.yml` | Exclude | Standalone app and database services. |
| `pyproject.toml` | Reference | Legacy interpreter, dependencies and test tool settings for portability checks. Use OpenAlgo’s project config. |
| `requirements-dev.lock` | Exclude | Standalone development dependency pins. |
| `requirements.lock` | Exclude | Standalone runtime dependency pins. |
| `scripts/organizeFrontend.cjs` | Exclude | One-off legacy frontend restructuring script. |
| `scripts/refactorFrontend.cjs` | Exclude | One-off legacy frontend refactoring script. |
| `scripts/setup.ps1` | Exclude | Standalone install and build workflow. Use OpenAlgo’s existing setup. |
| `scripts/verify.ps1` | Reference | Categories of checks to translate into OpenAlgo’s test and build tools. |

## Implementation handoff

The source inventory and native integration points are ready. The OpenAlgo-specific phased master prompt is required to choose the intended hosting surface, order the implementation phases and apply their acceptance criteria. The legacy register is useful background for that work. No application code or runtime configuration changes are part of this analysis.
