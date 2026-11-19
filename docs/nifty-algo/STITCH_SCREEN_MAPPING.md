# Stitch export mapping

The NIFTY export is present at `../trader-bot/stitch_nifty_algo_trading_terminal/`. It is read-only source material. `STITCH_EXPORT_PATH` was unset during inspection. The target repository contains no equivalent export directory. The sibling export matches the requested NIFTY platform through its page titles, navigation and indicator labels.

## Inventory

The export contains six HTML pages and six corresponding PNG screenshots, one `obsidian_algorithmic_terminal/DESIGN.md` token file, and a separate ZIP archive in the sibling root. HTML references Tailwind's CDN runtime, Google Fonts for Inter and JetBrains Mono, and Google Material Symbols. These are design references. The React integration uses the installed OpenAlgo toolchain and Lucide icons. No CDN script or exported example quote is imported into production.

| Export directory | Exported screen | Target surface | Current integration |
| --- | --- | --- | --- |
| `main_trading_dashboard` | Dashboard | `/nifty-algo?view=overview` | Dark sidebar, metric panels, confluence, risk and decisions bound to feature APIs. |
| `advanced_live_charts` | Live chart workspace | `/trading` through the workspace chart link | Native chart routing reused. Dedicated futures overlays, PCR pane and execution markers remain pending. |
| `signal_monitor` | Five-indicator monitor | `/nifty-algo?view=signals` | Indicator observations, persisted decision records and an explicit native-history assessment action. Rich snapshot drilldown remains pending. |
| `paper_trading_terminal` | Paper terminal | `/nifty-algo?view=terminal` and `view=positions` | Start/resume, pause, stop and confirmed kill controls, plus simulated records. Manual exit and cancellation controls await backend contracts. |
| `performance_analytics` | Performance | `/nifty-algo?view=performance` | Backend performance fields and trade journal. Dedicated equity/drawdown chart rendering and CSV remain pending. |
| `backtesting_and_historical_replay_lab` | Research lab | `/historify` through the workspace research link | Native historical data access reused. NIFTY replay form and research result views remain pending. |

The PNG dashboard was visually inspected. The design uses `#0b1117`/`#0e151e` backgrounds, `#121b24` panels, muted slate borders, emerald `#42e5b0` accents, amber paper-mode status, compact tables, sans-serif labels and monospaced data. The initial workspace carries these colors, sidebar hierarchy, rounded panels and responsive stacking within the existing authenticated OpenAlgo shell. Complete screenshot fidelity has not yet been verified.

## Remaining screens

The export has navigation labels for more screens than exported HTML pages. Configuration and risk use the same feature styling. Connections/setup links to broker selection, instrument master and native Python hosting. Account preferences and notifications link to existing authenticated OpenAlgo pages. These links preserve native ownership of credentials and account settings. No separate exported onboarding, account-preferences, connection, activity or risk-management mockup was found.

## Data and interaction contracts

The centralized feature client uses OpenAlgo's cookie-authenticated `webClient` with CSRF handling. GET responses use `{status, data}` from `/api/nifty-algo/`. Controls use POST `/strategy/start`, `/strategy/pause`, `/strategy/stop` and `/strategy/kill-switch` with the current state revision. Start currently returns a readiness error. Configuration uses GET/PUT `/configuration` with `{configuration, revision}` for conflict detection. Status, market, indicators, signals and risk are server observations. Positions, orders, trades and performance currently surface the backend PAPER_ACCOUNT_UNAVAILABLE response. Empty and failed requests display explicit states.

The workspace registers a `nifty_algo_update` listener through the app-wide Socket.IO connection. Backend publication remains pending. A 30-second query refresh provides status reconciliation when events are unavailable. The frontend presents the server's automation state and paper-mode assertion. The kill switch requires a confirmation dialog and waits for the persisted lockout response. The dialog identifies automated exits as pending execution integration. Backend validation remains authoritative.

## Validation limits

Frontend tests cover absent data, server errors, kill confirmation and assessment initiation only after an explicit click. Build/type-check results belong in the central implementation tracker. No screenshot comparison or real broker-feed browser session has been completed. The initial workspace is a partial Phase 7 integration and does not satisfy the full chart, journal, replay and design-fidelity acceptance criteria yet.


