# Paper execution safety model

## Audited native hazards

`services/place_order_service.py` checks global Analyzer mode and can route to a broker when disabled. Its authenticated internal function accepts `force_live`. Smart, basket, options, cancel, modify, close and GTT service paths also require route auditing before use. `services/strategy_module/order_dispatch.py` has explicit live and sandbox branches. `services/strategy_module/signals.py` can select live mode from strategy configuration. The NIFTY feature must never select these live branches.

Analyzer transitions in `services/analyzer_service.py` also manage Sandbox background execution and square-off. Consequently an isolated direct Sandbox adapter still needs execution-engine readiness when Analyzer is disabled. A UI badge, environment flag or startup mode check provides insufficient protection.

## Required boundary

NIFTY order-changing code imports only specific `services.sandbox_service` capabilities. It has no generic SDK order client, broker order module, live-mode parameter or fallback dispatch. Every instrument is independently resolved against structured current metadata. Allowed exposure is long NIFTY CE/PE on NFO. Exits reconcile owned quantity before selling. Reject unknown or stale risk authorization.

The current native fill engine permits LTP fallback, full-quantity fills and shared account balances. A strict NIFTY adapter must refuse automation until a compatible scoped native execution profile and isolated accounting are implemented and tested. Existing generic Sandbox simulation cannot be described as the requested strict execution model.

## Durable state and concurrency

Configuration updates create immutable revisions and pause entries. Kill switch is persistent. Starting requires reconciliation, healthy data, valid session, required warm-up, complete PCR and execution readiness. Stop and pause prevent entries. Closing positions is a separately acknowledged operation. Never claim that stopping a process closed its positions.

Before enabling order submission, atomically claim each decision intent and reserve risk. Duplicate or concurrent requests must resolve to the existing intent. After an ambiguous submission, reconcile native order and trade records before retrying. Confirm exit fills before declaring a position flat. Persist stop state and immutable entry configuration.

## Verification requirements

Assert zero calls at final broker order-changing boundaries under Analyzer enabled, disabled and switching, expired credentials, restart, duplicate and concurrent signals, stale data, risk failure and rejected exits. Also verify native Sandbox failures never trigger another routing path. Readiness blocks remain visible until these checks pass.
