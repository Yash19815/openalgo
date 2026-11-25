# NIFTY charge evidence — 25 November 2026

F-05 remains **DEFERRED_WITH_REASON** for exact broker contract-note rounding
and complete GST/IPFT invoicing evidence. Known rate and GST-base discrepancies
are corrected for new 3.3.0 simulated estimates; this is not a claim that F-05 is
fully resolved. The historical configured formula remains pinned to 3.1/3.2.

## Primary evidence retrieved

- [NSE/FATAX/73524](https://nsearchives.nseindia.com/content/circulars/FATAX73524.pdf)
  and [NSE STT computation](https://www.nseindia.in/static/products-services/equity-derivatives-securities-transaction-tax):
  option-premium sales incur 0.15% STT from 1 April 2026; previous rate 0.10%.
  Exercise taxation is separate and is not modelled as a PAPER sale fill.
- [NSE/FA/73061, 27 February 2026](https://nsearchives.nseindia.com/content/circulars/FA73061.pdf):
  from 1 March 2026, options transaction fees are INR 3,552.99 per crore of
  premium each side, and IPFT is INR 0.01 per crore each side. Combined outflow
  remains INR 3,553 per crore. The PDF's decimal `.99` must not be dropped.
- [NSE/FA/64232, 27 September 2024](https://nsearchives.nseindia.com/content/circulars/FA64232.pdf):
  the prior transaction tariff from 1 October 2024 was INR 35.03 per lakh per
  side. The 2026 circular separately documents its prior INR 50/crore IPFT.
- [NSE levies](https://www.nseindia.in/static/invest/first-time-investor-sebi-turnover-fees-stt-other-levies):
  SEBI fee INR 10/crore both sides; options stamp duty 0.003% on buys, with
  collection regime effective 1 July 2020. The page states 18% GST.
- [Angel One published schedule](https://www.angelone.in/exchange-transaction-charges),
  retrieved 25 November 2026: standard F&O brokerage INR 20 per executed order;
  options transaction rate 0.0355299%, IPFT 0.0000001%, sell STT 0.15%, buy stamp
  0.003%, SEBI INR 10/crore and GST 18%. Promotional free brokerage is not assumed.
  Account-specific charges, auto-square-off and exercised options are outside
  the full-quantity simulated intraday-order model.
- [CBIC stock-broking FAQs](https://cbic-gst.gov.in/sectoral-faq.html), questions
  77–78: brokerage is taxable; pure-agent recoveries require their specific
  conditions. This does not by itself prove each broker's IPFT invoicing.
- [NSE STT rounding procedure](https://nsearchives.nseindia.com/content/circulars/cmtr5588.htm):
  daily client aggregate is rounded to the nearest rupee, with 50 paise upward.
  Rounding each fill independently is not equivalent.

## Implemented model and limits

`fees.configured_total` is pure and shared through the existing `_charges`
boundary. Admission, sizing, fills, protection, projected reward, replay and
journal calculations use that boundary. No Sandbox ledger or charge engine is
imported. New defaults use the published rates. SEBI and IPFT enter the GST
estimate's taxable base. Exact IPFT invoicing remains an explicit evidence gap;
including it is the conservative estimate, not a certified tax determination.

New entry authorization refuses configured fee inputs below published standard
floors. Higher explicit custom estimates remain intact. A historical explicit
lower tariff requires review instead of silent overwrite. Migration never
changes a pending order or held configuration. Structured review updates only
the draft; saving remains an explicit operation and pauses entries.

The model identifies charges as simulated estimates and rounds the total upward
to INR 0.0001. It does not falsely label this as Angel's contract-note rounding.
`round_daily_stt` independently implements the documented aggregate rule, and
does not rewrite historical fill charges. Actual broker rounding/aggregation of
GST, exchange fees, SEBI, IPFT, stamp and brokerage still needs dated evidence.

Golden turnover INR 6,500: new estimate BUY 26.5279, SELL 36.0829; legacy BUY
27.6365, SELL 31.5040. Components and effective-date boundaries are independently
tested in `test_nifty_algo_fee_candidates.py`.

## Evidence still required

Supply a dated Angel rounding/invoicing specification or separately authorized,
sanitized representative contract-note component totals. Include multiple
executed orders and partial exit orders, near-50-paise STT totals, IPFT GST
treatment, per-order brokerage aggregation and per-component rounding. No broker
was contacted or authenticated during remediation. Do not certify statutory or
contract-note parity from the current estimates.
