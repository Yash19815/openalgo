# NIFTY paper-trading readiness report

Status: implemented and tested offline; **real-market forward paper readiness
has not been verified**. No live order capability was added or used.

| Area | Implemented and offline evidence | External or remaining evidence |
| --- | --- | --- |
| 8% stop and point trail | Filled-price stop, conservative ticks, delayed activation, monotonic durable peak/stop, gap and depth rejection tests | Live feed latency/liquidity behavior |
| Dynamic target | Deterministic per-indicator contributions, bounded tick-valid 10–15% target, immutable entry settings | No calibrated win probability or profitability evidence |
| Data and PCR | Native source cache and futures history connected; full dated master expiry, timestamp/coverage/definition checks | Genuine Angel complete-scope observations and entitlement |
| Runner | Native IST scheduler, separate entry/protection jobs, lease, startup floor and restart reconciliation | Full application process lifecycle under Linux workers |
| Paper ledger | Atomic reservation/fills, displayed quantity, costs, retries, partial exit accounting and isolated journal | Extended unattended forward observation |
| Workspace | Existing route, readiness-gated Start, indicator contributions and protection state | Real-session UI observation |

The offline end-to-end simulator runs actual five-indicator calculations and
verified-fixture PCR, selects a contract, reserves risk, confirms ask fills,
advances protection, exits on bid depth and checks fees/net P&L. Generic order
transport canaries and import checks remain untouched under Analyzer enabled,
disabled and changing. This is offline isolation evidence, not a real broker
session test. Test totals, command failures and platform limits are in TESTING.md.

Before a forward paper session, verify today's broker/master identity, full
expiry coverage within subscription capacity, source-level exchange timestamps,
actual futures volume, valid NFO calendar sessions, reconnect recovery, correct
fee assumptions, and the production worker startup/shutdown behavior. If the
broker cannot supply the full timestamped scope, entries must remain blocked.
No real historical dataset was replayed and no live-market paper fill was
observed during this implementation session. Database retention is not automated.

Final focused evidence: 142 NIFTY backend tests, seven workspace tests, 98 isolated upstream recovery/risk tests and the earlier Angel/host regressions passed. The broader frontend run retained six test timeouts and two hook timeouts despite the storage compatibility flag; see TESTING.md. Production readiness remains unverified.
