# Execution Safety Center

The authoritative recovery model is [SAFETY_MODEL.md](SAFETY_MODEL.md).
The existing Safety Center blocks entries through persisted incidents and the
existing PAUSED/KILLED controls, including transactional admission/fill checks.
Protection and exits remain independent of entry readiness.

Incident acknowledgement changes OPEN to ACKNOWLEDGED; it does not resolve an
incident, change a stop, clear a lockout or resume trading. Resolution requires
the existing authenticated application, verified reconciliation and a separate
manual resume. Discord can acknowledge only.

## Operational procedure

1. Pause entries and inspect the position, pending intent and protection state.
2. Reconcile through the existing application control. Treat uncertain execution
   as unresolved; a timeout does not establish rejection or a flat position.
3. Verify recovery evidence before resolving an acknowledged incident.
4. Resume entries manually only after fresh readiness checks pass.
5. Inspect Discord/email delivery independently from incident safety state.

Local incident generation cannot be disabled through notification preferences.
Delivery runs in a separate process and cannot hold the protection scheduler.
The outbox preserves uncertain remote outcomes instead of assuming rejection.

## Unavailable Live capability

`LiveAdapterStub` still has no broker transport. This extension does not provide
or certify Angel One live reconciliation, broker-hosted stop ownership,
verified emergency flattening or partial-fill recovery. Those requirements
remain blocked, and Live cannot activate. Passing Paper mocks does not satisfy
them. Do not use Discord delivery or a reconnection as recovery evidence.
