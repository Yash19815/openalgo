# Local setup and readiness

This is an in-progress OpenAlgo extension. Follow the existing root README, installation guide and `.sample.env` for the platform environment. Python requires 3.12 or newer. The frontend's current `package.json` requires Node `^22.23.4 || ^24.22.1 || >=26.12.1`. Use `uv sync --frozen` and the existing frontend lockfile. No new runtime dependency or service has been introduced by this feature.

## Startup and persistence

1. Configure private OpenAlgo application keys and database URLs through the native environment workflow.
2. Use `npm ci --prefix frontend` and `npm run build --prefix frontend` for the frontend.
3. Start OpenAlgo through its existing deployment command, such as `uv run app.py` for local development.
4. Sign in through the existing OpenAlgo session and open `/nifty-algo`.

Startup adds `nifty_algo_state`, `nifty_algo_configuration`, `nifty_algo_event` and `nifty_algo_decision` to the existing main database. Creation is idempotent and leaves native tables intact. There is no second database server. Back up the main database with the existing platform procedure before upgrading. Configuration changes require the current revision and pause entries. A stale save returns HTTP 409. A persistent kill lockout cannot be cleared by changing configuration or pausing.

## Data connection

Configure Angel One market data using OpenAlgo’s existing broker screen, server-side credentials and instrument master download. Use the native connection and subscriptions. Broker tokens must remain outside browser payloads, documentation and logs. The feature reads the normalized master and cache. An unavailable exchange timestamp remains unavailable even when a cached price is visible. A local receipt time alone cannot make that price eligible for strategy execution.

The current master schema has no per-contract download date. The feature labels its freshness unverified. Verify session calendars, dated master metadata, complete one-expiry PCR coverage and genuine futures volume before enabling a forward test.

## Current controls

Start returns `PAPER_NOT_READY` with execution prerequisites. Pause and stop persist their respective control state. Kill persists a monotonic NIFTY entry lockout. These controls currently manage feature state. A runner, native strict simulation profile and protective-exit recovery still need integration. Account/order/performance endpoints return `PAPER_ACCOUNT_UNAVAILABLE` while isolated accounting is absent.

The generic Analyzer toggle has no authority to enable NIFTY order submission. No feature path changes another strategy's Analyzer state or account capital. Review the [safety model](SAFETY_MODEL.md) for the target execution boundary and remaining gates.

## Verification

Feature tests are in `test/test_nifty_algo_*.py`. Run them with the installed OpenAlgo environment and the repository’s existing pytest isolation. Local isolated runs and environment limits are recorded in [TESTING.md](TESTING.md). A full locked-dependency application startup, Linux eventlet/gthread validation and a real market-data session remain separate checks.

## Operation, backup and retention

Use existing OpenAlgo logs and diagnostics. Feature configuration/control events retain user scope and timestamp. Never infer a closed position from a process exit. Before shutdown of an eventual enabled runner, reconcile pending Sandbox orders and confirmed positions, acknowledge exit failures, then use the native strategy-host stop and application shutdown procedures.

Back up the main and Sandbox databases together when preserving strategy context and fills. Verify restored account/order identity before resuming. Event and decision queries are bounded to 100 rows, while durable records are retained. Automated archival and retention policy are pending and must be chosen before prolonged forward evaluation.
