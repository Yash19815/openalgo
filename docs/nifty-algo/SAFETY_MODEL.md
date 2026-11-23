# NIFTY paper execution safety model

## Research evidence boundary

Recordings are research-only quote evidence, never order admission or fill
authority. Signed-session controls retain CSRF, owner scoping, bounded bodies
and count-fenced sealing. The HTTP API accepts no market observations.

Native capture now has an explicit internal opt-in and immutable metadata
sidecar. Existing recordings are never automatically adopted. Freezing requires
current runner ownership under the owner lock and occurs before observations.
The scope contains at most 1,000 unique, tradable NIFTY options from today's
master and at most 512 KiB of metadata. Its hash is bound into the recording
identity. Broker labels and hashes do not authenticate provenance.

Native opt-in appends require current runner ownership, a frozen token, native
source classification and a source timestamp at or after scope freeze time.
Scope conflicts and storage failures roll back atomically without renewing
runner readiness. The sidecar has no trading authority. The current explicit
recording controls and separate runner capture job use the existing cache;
they never authorize orders or upgrade missing execution evidence.

The native research reader uses only identified mode-3 source snapshots from
the existing supplied cache. Display fallbacks, missing sides, stale timestamps,
malformed levels and depth lists over 20 entries are refused. It reuses the
paper depth parser without changing the paper path's default policy. Native OI
and packet sequence remain source fields, not a certification of provenance.

Internal sample deduplication persists owner/recording-scoped identities with
the evidence transaction. Repeated polling retains first availability, including
after restart. Quota rejection or storage failure must roll back identities and
observations together. There is no separate in-memory deduplication registry.
An internal native-capture append can also require the current runner owner.
That lease is checked under the existing owner lock, before deduplication or
evidence writes. A missing, expired, released or replaced lease refuses the
append without renewing the heartbeat or changing entry readiness.
The optional capture job is connected to the runner scheduler. Sealing does
not make quote-only data complete or execution-eligible; Live remains blocked.

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

## Execution Safety Center

The Risk view exposes durable incidents from the isolated NIFTY ledger.
Authenticated reads return at most 100 incidents; the entry interlock considers
all unresolved critical incidents in the current primary mode, not only that
page. A critical primary incident also persists the existing PAUSED state for
rollback compatibility. SHADOW and RESEARCH incidents do not control paper
entries. Protective exits continue regardless of an entry hold.

Acknowledgement records the owning session user, time and new incident revision.
It does not resolve the incident, clear the entry hold, or resume the runner.
Resolution is a separate owner/CSRF-protected action requiring incident and
strategy revisions plus the exact `RESOLVE_ONLY` confirmation. The review
dialog states that trading remains paused and restores keyboard focus on cancel.

Only PAPER incidents with codes `STALE_DATA`, `MARKET_DATA_DISCONNECTED`, or
`RECONCILIATION_BLOCKED` support this verified recovery path. The incident must
already be acknowledged. Resolution requires PAUSED state, no kill or daily
lock, no pending BUY, and verified nonlegacy protection on any held position.
It checks the current isolated ledger's cash, fills, positions and reservations
under the same user lock as admission and fill. A previously saved reconciliation
flag alone is insufficient.

The runner's assessment must match the active configuration, be no older than
30 seconds, not precede the incident, and have an unexpired owner lease.
Heartbeat renewal does not renew assessment evidence. Resolution stores actor,
time, configuration, runner owner and fresh check timestamps in the committed
`safety_resolved` event. Status reads recover those fields from the matching
owner-scoped event, so evidence remains available after refresh and restart.
Resolution never changes PAUSED to RUNNING and never clears kill, daily,
monthly, or other incident holds.

Start remains an explicit strategy action with the current strategy revision.
It rechecks runner evidence, active incidents and current ledger invariants
under the user lock at the write. Failed recovery rolls back without dropping
exposure or disabling exits. Unknown conditions, LIVE recovery, broker ambiguity,
live partial fills and broker protective-order verification remain unsupported.

## Native research capture

Recording controls require the signed session, CSRF, bounded JSON and exact
`RESEARCH_ONLY` confirmation. The optional `native_capture` flag is a strict
boolean, default false. It creates an empty sidecar, not feed or order authority.
Caller-selected instruments, provenance, timestamps, prices and observations
remain forbidden. Legacy recordings are never silently adopted.

The independent capture job reads only verified, acknowledged native depth
cache observations within a frozen server-derived master/broker scope.
It cannot initialize a client, subscribe, reconnect, renew readiness or place
orders. Owner fencing, count fencing, immutable scope and durable sample
deduplication apply at append. Lost ownership, changed feed generation and
concurrent sealing reject stale writes. Protection stays independently scheduled.

Capture is incomplete evidence, not broker-authenticated historical execution
proof. `NATIVE_CAPTURE_REQUESTED` reports opt-in only, never connection health
or coverage. Empty or insufficient recordings remain non-executable. Real-feed
rehearsal, replay, experiments, exit studies and capture UI remain outstanding.

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
