# Research sources and effective-date register

Reviewed on 19 November 2026. This register records source evidence available during Phase 0. Broker-account entitlements and a market-data session were not tested. Local OpenAlgo code remains the authority for the installed implementation. The reference checkout for this audit is recorded in `MASTER_DESIGN.md`.

## Exchange metadata and calendars

| Subject | Verified evidence | Runtime consequence |
| --- | --- | --- |
| Expiry | NSE specifies Tuesday expiry, with the previous trading day used for a holiday. The June 2025 revision changes weekly NIFTY expiry and monthly/quarterly cycles. | Resolve each listed contract’s actual expiry through the native symbol database. Preserve dated metadata for replay. [Specifications](https://www.nseindia.com/static/products-services/equity-derivatives-contract-specifications), [NSE/FAOP/68747](https://nsearchives.nseindia.com/content/circulars/FAOP68747.pdf) |
| Lot size | NSE/FAOP/70616, issued 3 October 2025, revises NIFTY from 75 to 65 with contract-dependent transition provisions. | This is historical evidence. Read current contract lot size before sizing each order. [Circular](https://nsearchives.nseindia.com/content/circulars/FAOP70616.pdf) |
| Tick and freeze quantity | The specifications table lists index-option price steps of ₹0.05. The contract-information page links current lot and quantity-freeze files. Direct CSV retrieval through the research browser failed with unsupported content type. No current numeric freeze value was verified. | Read current instrument tick and freeze metadata. Missing or inconsistent values block the affected order. [Specifications](https://www.nseindia.com/static/products-services/equity-derivatives-contract-specifications), [Contract files](https://www.nseindia.com/static/products-services/equity-derivatives-contract-information) |
| Holidays | NSE/FAOP/71777 is the F&O 2026 holiday circular. It includes 24 November and 25 December. Special sessions have separate notices. | Reuse the native calendar, with bounded coverage and explicit special-session windows. [F&O holiday circular](https://nsearchives.nseindia.com/content/circulars/FAOP71777.pdf) |
| Session hours | The generic NSE page currently displays 09:15–15:40 for equity derivatives. The dated CAS 2.0 FAQ applies from 7 December 2026 and specifies 15:45 closing, with expiring index derivatives ceasing at 15:30 on expiry day. | The generic page alone cannot resolve historical effective timing. Use the native effective-date calendar and reconcile its underlying circular before forward testing across a schedule transition. [Timings page](https://www.nseindia.com/static/market-data/market-timings), [CAS 2.0 FAQ](https://nsearchives.nseindia.com/web/mediaattachment/2026-11/FAQs_for_CM_and_FO_FOR_CAS_2.0_20261109152618.pdf) |

The CAS FAQ references NSE/FAOP/77356 of 6 November 2026. Direct retrieval of that circular failed in the research browser. Do not overwrite an earlier session record with the future FAQ’s window. A conservative configured strategy deadline must still be checked against the effective contract session.

## SmartAPI data and limits

The official documentation describes FULL quotes containing exchange feed/trade times, volume, OI and five-level depth. It advertises 50 symbols per quote request and one request per second in the market-data section. A separate rate table advertises ten quote requests per second, 500 per minute and 5,000 per hour. The pages were available through search extracts, while direct MarketData and RateLimit opens returned an authorization message. Treat the quote-rate conflict as unresolved. Share OpenAlgo’s limiter, prefer its existing stream, use conservative backoff and verify current account limits before a full-chain polling plan. [Market-data documentation](https://smartapi.angelone.in/docs/ResponseStructure), [Rate table](https://smartapi.angelone.in/docs/MarketData)

The published history table lists candle caps of three requests per second, 180 per minute and 5,000 per hour. The broker team explicitly corrected the minute cap to 180. Limits apply alongside other application traffic. [Broker rate clarification](https://smartapi.angelone.in/smartapi/forum/topic/4387/changes-in-api-rate-limit/5)

SmartAPI documents three concurrent WebSocket connections per client and 1,000 token/mode subscriptions per session. Subscribing the same token in different modes consumes separate quota. Reuse OpenAlgo’s connection and subscription infrastructure. Actual account access, complete one-expiry chain coverage and source-time availability remain integration checks. [WebSocket documentation](https://smartapi.angelone.in/docs/ResponseStructure)

Instrument symbols and tokens come through the existing OpenAlgo master download and normalization. SmartAPI publishes its consolidated instrument dump, but an account’s present segment activation, feed permissions and expired-option history were not verified. Keep credentials in the existing server-side broker session. [SmartAPI instruments and authentication](https://smartapi.angelone.in/docs)

## Retail algorithmic trading framework

SEBI’s 30 September 2025 circular makes the February 2025 framework, exchange standards and operational modalities applicable to all brokers from 1 April 2026. This establishes the reviewed effective date for the future-live design. [SEBI circular 2025/132](https://www.sebi.gov.in/sebi_data/attachdocs/sep-2025/1759232056254.pdf)

NSE’s standards address static-IP controls, daily API logout, algo tagging and a threshold initially set at ten orders per second per exchange/segment. Broker limits may be lower. A future implementation must confirm boundary treatment and whether changes/cancellations share its rate bucket. [NSE/INVG/67858](https://nsearchives.nseindia.com/content/circulars/INVG67858.pdf)

The November 2025 NSE FAQ describes client-hosted logic for tech-savvy clients using static IPs and broker hosting for provider strategies. Its order-type answer prohibits algo market orders and explicitly discusses IOC restrictions for commodities. Angel One’s March 2026 notice states market and IOC orders are prohibited for algorithmic trading. Resolve precise segment and order-type treatment with the broker before any later live design is approved. [NSE FAQ](https://nsearchives.nseindia.com/web/sites/default/files/inline-files/FAQ_Retail%20Algo_03112025_NSE.pdf), [Angel One access notice](https://oga-prod.angelone.in/news/market-updates/what-s-changing-in-angel-one-s-smartapi-access-from-april-1-2026)

## Video evidence

Original YouTube watch-page and Hindi timed-text retrieval failed during this review. A secondary summary was accessible. Its transcript tab failed. Therefore no rule currently has `VERIFIED_FROM_VIDEO` status. See `VIDEO_STRATEGY_ANALYSIS.md` for the limited evidence and `STRATEGY_ASSUMPTIONS.md` for the automation hypothesis. [Original video](https://www.youtube.com/watch?v=94Vph1miSYg), [Secondary summary](https://videohighlight.com/v/94Vph1miSYg)

## Review controls

For every effective-dated dataset, retain source URL, notice identifier, review date, effective start/end, instrument identity and checksum where a file is imported. The latest web page does not establish the historical rule for a replay date. Missing calendars, contract metadata or required feed fields fail closed. No external account permission, regulatory registration or real-time trading result is established by this document.
