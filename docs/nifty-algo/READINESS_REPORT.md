# NIFTY paper-trading readiness report

Status: Phases 0–6 implemented; Phase 7 hardening verified offline on 21 November 2026
(283 NIFTY backend tests, 28 neighboring email tests, 26 workspace tests,
production build green, Linux runtime gate 1,456 passed/3 skipped — see
`PAPER_SYSTEM_DESIGN.md` §5 and `TESTING.md`). **Real-market forward paper
readiness has not been verified.** Live mode is blocked by design: the adapter
is a stub with no transport that always reports `LIVE_NOT_READY`.

| Area | Implemented and offline evidence | External or remaining evidence |
| --- | --- | --- |
| 8% stop and point trail | Filled-price stop, conservative ticks, delayed activation, monotonic durable peak/stop, gap and depth rejection tests | Live feed latency/liquidity behavior |
| Profit lock | ₹400 activation, ₹350 modeled floor, tick-aligned floor stop, gap-through-floor honesty | Real-time bid-depth behavior |
| Dynamic target | Deterministic per-indicator contributions, bounded tick-valid 10–15% target, immutable entry settings | No calibrated win probability or profitability evidence |
| Data and PCR | Native source cache and futures history connected; full dated master expiry, timestamp/coverage/definition checks | Genuine Angel complete-scope observations and entitlement |
| Calendar | Approved NSE PDF import with DRAFT/APPROVED/REJECTED states; `CALENDAR_UNAPPROVED` blocks entries | A real uploaded NSE circular per year |
| Cooldown and monthly locks | Next-session loss cooldown; ₹2,000 monthly loss lock and optional profit lock, latched and restart-safe | Forward observation |
| Runner | Native IST scheduler, three named jobs (`:protect`, `:entries`, `:reports`), lease, startup floor and restart reconciliation | Full application process lifecycle under Linux workers |
| Paper ledger | Atomic reservation/fills, displayed quantity, costs, retries, partial exit accounting, isolated journal, ₹20,000 virtual capital | Extended unattended forward observation |
| Shadow and research | One active hypothetical shadow, primary mirrors flagged non-additive, bounded research observations | Forward observation |
| Trading modes | Revision CAS under user lock, masked broker status, Live hard-blocked by `LiveAdapterStub` | Independent Live verification (below) |
| Reports | Deterministic sha256 PDFs, idempotent period keys, CAS delivery claim, bounded retry only for definite failures, uncertain outcomes held for operator review, `SKIPPED_NO_SMTP` | Real SMTP deliverability |
| Workspace | Existing route, readiness-gated Start, panels for locks/calendar/shadow/mode/reports | Real-session UI observation |

The offline end-to-end simulator runs actual five-indicator calculations and
verified-fixture PCR, selects a contract, reserves risk, confirms ask fills,
advances protection, exits on bid depth and checks fees/net P&L. Generic order
transport canaries and import checks remain untouched under Analyzer enabled,
disabled and changing. This is offline isolation evidence, not a real broker
session test. Test totals, command failures and platform limits are in TESTING.md.

Before a forward paper session, verify today's broker/master identity, full
expiry coverage within subscription capacity, source-level exchange timestamps,
actual futures volume, an approved NFO calendar for the year, reconnect
recovery, correct fee assumptions, and the production worker startup/shutdown
behavior. If the broker cannot supply the full timestamped scope, entries must
remain blocked. No real historical dataset was replayed and no live-market
paper fill was observed during implementation. Database retention is not
automated.

## Live mode unblock requirements (by design, none are self-certifiable)

`LiveAdapterStub` reports every prerequisite unverified. Replacing it requires
a real adapter plus independent evidence for each: broker authentication and
token validity, market-data quality, protective-order acceptance at the broker,
fill reconciliation against broker records, and deployment prerequisites
including SEBI static-IP whitelisting. A mode request is also refused on any
open exposure and without an explicit acknowledgement. Until then Live cannot
activate; Paper mode is unaffected.
