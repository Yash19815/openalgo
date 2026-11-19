# Future Angel One live integration plan

Design-only milestone. A later project requires explicit user authorization, current broker approval and a separate reviewed implementation. The NIFTY initial release keeps PAPER_ONLY execution and exposes no live-enable control. This document does not authorize broker order calls during development or tests.

## Existing integration points

OpenAlgo’s Angel plugin owns authentication, normalized data, instrument mapping and order translation. Inspect `broker/angel/`, `services/place_order_service.py`, `services/place_smart_order_service.py`, the strategy module’s `order_dispatch.py`, broker binding, acknowledgement reconciliation and order events when planning that later change. Audit the actual revision again. Keep the existing paper executor and paper audit trail independently identifiable throughout any future extension.

## Permissions and regulatory review

Confirm NFO activation, API order permission, applicable retail-algo classification, registration/tagging, permitted hosting and registered static IPs with Angel One. Its March 2026 notice states static-IP enforcement begins 1 April 2026. Keep market-data entitlement distinct from authority to trade. [Angel One notice](https://oga-prod.angelone.in/news/market-updates/what-s-changing-in-angel-one-s-smartapi-access-from-april-1-2026)

Refresh the SEBI circular and exchange implementation standards at approval time. The reviewed framework covers algo identification, RMS and order-rate controls. The initial NSE threshold is ten orders per second per exchange/segment, and a broker may impose lower caps. Resolve exactly-at-threshold handling and aggregation of place, modify and cancel traffic in writing. [NSE standards](https://nsearchives.nseindia.com/content/circulars/INVG67858.pdf)

Use broker-approved bounded limit orders and confirm current rules for IOC, market, stop-limit and expiry-session behavior. The NSE FAQ and Angel notice differ in the specificity of IOC restrictions, so the later release must record the applicable segment treatment. [NSE FAQ](https://nsearchives.nseindia.com/web/sites/default/files/inline-files/FAQ_Retail%20Algo_03112025_NSE.pdf)

## Authentication and deployment

Reuse OpenAlgo’s server-side encrypted credential storage, broker session renewal and logout handling. Validate session identity and trading account at start and before recovery. Keep keys, PINs, TOTP seeds, access tokens and refresh tokens out of logs, frontend payloads and source control. Confirm current token expiry with the installed broker adapter and broker documentation. Use a stable deployment with clock synchronization, approved static egress, protected backups and monitored connectivity.

## Execution and reconciliation design

- Require a deliberate manual launch authorization tied to the account, strategy version, risk limits and deployment revision.
- Bind each run and every order/read/cancel/recovery operation to the same broker account and execution mode. Validate structured contract metadata, lots, tick and freeze quantity before submission.
- Apply pre-trade capital, premium-risk, daily-loss, position, entry-count, liquidity, spread and freshness limits. Serialize competing entries and persist idempotency intent before network submission.
- Treat transport timeout as an uncertain acknowledgement. Query and reconcile broker state before retrying. Persist exchange/broker IDs, cumulative filled quantity, average price, rejects and revisions.
- Derive positions and P&L from reconciled broker fills and real account records. Compare orderbook, tradebook, funds and positions periodically and after reconnect or restart.
- Handle rejects and partial exits explicitly. Emergency exit retries require current residual quantity, a valid session and approved price bounds. Block new entries during uncertainty. Display unresolved exposure prominently.
- Test against an offline broker-boundary double. Any actual broker certification or staged live test needs separate authorization and a written procedure.

## Rollout gates

- [ ] Current exchange/broker permissions and effective rules reviewed and recorded.
- [ ] Account identity, static IP, rate budget, tagging and permitted order types confirmed.
- [ ] Independent technical/security review of every order-changing path completed.
- [ ] Restart, timeout, duplicate acknowledgement, partial fill and disconnect reconciliation proven.
- [ ] Emergency procedures, operator access, alert delivery, retention and restore verified.
- [ ] Maximum exposure, duration, daily loss and rollback conditions approved manually.
- [ ] Separate deployment revision and explicit go-live authorization recorded.
- [ ] Small, supervised staged rollout completed before any increase in size.

Forward paper performance provides evidence about the tested simulation and data. Live execution adds liquidity, queueing, slippage, broker and account risks requiring its own measurements and reconciliation.
