# NIFTY paper execution safety model

## Execution boundary

`NiftyPaperExecutor` changes only NIFTY feature tables. Its generic `submit`
method remains permanently closed. Automation imports no broker order module,
shared Sandbox executor, smart-order service, or live fallback. Analyzer Mode
has no authority over these orders. Only long NFO NIFTY CE/PE exposure is
admitted; averaging, uncovered sells and quantity overrides are rejected.

Buys require ask depth; sells require bid depth. LTP never supplies a fill.
Missing exchange time cannot be replaced by local receipt time. Source age,
receipt ordering, instrument identity, ticks, fees, latency, TTL, displayed
quantity, capital and risk are checked at the execution boundary. Insufficient
depth defers an entire order; partial fills are unsupported. Explicit partial
exit orders preserve protection and allocate entry fees by exited quantity.

## Protection and durable controls

Initial stops use the confirmed fill and round upward to the contract tick,
so rounding cannot loosen the maximum 8% planned stop. Trailing uses Decimal
option-premium points. It arms only after the configured favorable bid move,
tracks a monotonic bid peak, and never lowers the active stop. Targets retain
the entry-time research strength and a tick-valid percentage within 10–15%.
A trigger is not a guaranteed fill or a cap on realized loss.

Price protection precedes target, maximum hold, enabled technical invalidation,
session exit and operator closure. Technical invalidation uses fresh completed
SuperTrend reversal or adverse movement against the recorded entry ATR on the
same futures identity. Forced time/session exits can create intents without a
fresh bid; they still cannot fill without a fresh executable bid and a verified
open NFO session. Failed exits remain visible and latched across restart and
retry. A position becomes flat only after confirmed quantity reduction.

Pause, stop and kill block entries while protective jobs remain attached.
Kill is persistent and cannot be cleared by a configuration update. Daily loss
lockout persists for the account's trading day and resets on IST day rollover.
Configuration changes pause entries and do not alter held-position settings.

Known v1 settings migrate into a new v2 revision with retained history and
paused entries. Unknown or invalid settings stay blocked. Legacy pending buys
are canceled. Legacy positions lacking recorded confidence receive emergency
8%-or-tighter stop protection without an invented target or confidence. A recorded favorable legacy peak is preserved as a conservative protective
floor and latches a review exit, rather than restarting at a looser stop. Such
exposure keeps entries blocked until reviewed/closed; this is not retroactive
proof that old trades used v2 targets.

## STRIDE review

| Threat | Control | Evidence/limit |
| --- | --- | --- |
| Spoofed observations | Native instrument identity, dated master and exchange/receipt timestamps | Offline missing-time, stale-chain and master rejection tests; live feed still unverified |
| Tampered configuration | Strict validated units, immutable revisions, revision CAS and paused migration | Migration and racing-control tests |
| Repudiated orders | Durable deterministic intent IDs, signal context, fill observations, fees and events | Restart, retry and journal assertions |
| Information disclosure | Server-held keys; errors record type/reason codes, not credential-bearing broker bodies | No credential changes or browser key transport |
| Denial of service | Separate entry/protection jobs, bounded history, subscription quota refusal, acknowledged reconnects | Production eventlet/gthread rehearsal pending |
| Privilege or route escalation | Session/CSRF/user scoping; no generic/broker order imports or fallback | Import checks and runtime canaries with Analyzer states |

Windows fixtures do not certify Linux worker behavior, real exchange data,
entitlements, or profitability. Durable decision/event/depth records require an
operator retention policy before prolonged forward operation.

Recovery verifies cash/held-cost equality, confirmed fill references, journal quantities and reservations. Inconsistent state blocks new entries. Exit coverage is independently bounded by confirmed buy quantity minus confirmed sells, even if a position counter is inconsistent.
