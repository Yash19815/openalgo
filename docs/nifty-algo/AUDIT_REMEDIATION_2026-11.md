# NIFTY audit remediation — November 2026

## Scope and provenance

Execution batch A, incomplete overall remediation. Do not merge as certification of all audit findings.

- Starting origin/main: `dcfb8df6e0f5ef3e3d9365b6e449d91c81c1f09d`.
- Audit report commit: `1cc30502d3d66a8611fd2127f29e5169e0b3f021`, fetched using Git without merging its branch.
- Branch: `fix/nifty-audit-execution-correctness`; PR link pending publication.
- Historical audit PR #9 was not modified. Findings below distinguish code evidence from unverified policy and feed assumptions.
- This batch does not claim full end-to-end audit reproduction, full manifest reading, or completion of PR B/C.

## Finding register

| Finding | Confirmed? | Resolution status | Code change / disposition | Tests | PR | Remaining risk |
|---|---|---|---|---|---|---|
| F-01 | Yes | `DEFERRED_WITH_REASON` | Indicator alignment belongs to PR B; current defaults remain 10/3. | Static review or pending | — | See disposition |
| F-02 | Yes | `DEFERRED_WITH_REASON` | Factor alignment belongs to PR B. | Static review or pending | — | See disposition |
| F-03 | Stale | `ALREADY_FIXED` | Main includes 3.2.0 MACD ages 0–2; existing MACD suite passes. | MACD window suite | — | See disposition |
| F-04 | Policy | `REQUIRES_OWNER_DECISION` | Keep documented /10 and /3 normalization or approve parameter-dependent normalization. | Static review or pending | — | See disposition |
| F-05 | Unverified | `DEFERRED_WITH_REASON` | No dated statutory fee and rounding verification completed; estimates unchanged. | Static review or pending | — | See disposition |
| F-06 | Unverified | `REQUIRES_REAL_FEED_EVIDENCE` | Need complete dated expiry master plus raw full-chain packets with trade, quote and receive times. | Static review or pending | — | See disposition |
| F-07 | Unverified | `REQUIRES_REAL_FEED_EVIDENCE` | Need native depth update timestamp contract and raw packets during inactive trading. | Static review or pending | — | See disposition |
| F-08 | Yes | `DEFERRED_WITH_REASON` | 20/2 tests belong with versioned indicator alignment. | Static review or pending | — | See disposition |
| F-09 | Yes | `DEFERRED_WITH_REASON` | Current indicator documentation remains pending PR B; historical provenance preserved. | Static review or pending | — | See disposition |
| F-10 | Static evidence | `NOT_YET_INVESTIGATED` | Boundary marked before assessment; deterministic retry reproduction still required. | Static review or pending | — | See disposition |
| F-11 | Static evidence | `NOT_YET_INVESTIGATED` | Opening-bucket mismatch and prior-session tails need complete parity regressions. | Static review or pending | — | See disposition |
| F-12 | No fabrication | `VERIFIED_NOT_A_BUG` | Raw OI remains None; zero is conservative scoring support, with explicit coverage flags. | Static review or pending | — | See disposition |
| F-13 | No | `VERIFIED_NOT_A_BUG` | indicators.adx applies period 14 to TR/DM and DX smoothing. | Static review or pending | — | See disposition |
| F-14 | Unverified | `NOT_YET_INVESTIGATED` | Historical root tools left intact; no removal authorized or needed by this patch. | Static review or pending | — | See disposition |
| F-15 | Research limitation | `REQUIRES_REAL_FEED_EVIDENCE` | Risk ceilings retained; feasibility needs observed premium, lot and fee evidence. | Static review or pending | — | See disposition |
| F-16 | Intentional distinction | `REQUIRES_OWNER_DECISION` | Gating uses ask denominator; ranking uses midpoint. Unifying changes ranking policy. | Static review or pending | — | See disposition |
| F-17 | No regular-session mismatch | `VERIFIED_NOT_A_BUG` | VWAP resets by IST date; observed bars are filtered to session, futures identity checked upstream. | Static review or pending | — | See disposition |
| F-18 | Historical semantics | `REQUIRES_OWNER_DECISION` | Initial SuperTrend direction unchanged; alternative seeding requires versioned parity analysis. | Static review or pending | — | See disposition |
| F-19 | Static evidence | `NOT_YET_INVESTIGATED` | Calendar authority reconciliation needs separate reproduction; exit semantics unchanged. | Static review or pending | — | See disposition |
| F-20 | Intentional | `VERIFIED_NOT_A_BUG` | Shadow has a separate ledger and documented entry/monthly-lock rules. | Static review or pending | — | See disposition |
| F-21 | Tooling limitation | `DEFERRED_WITH_REASON` | Recursive dependency junction is unrelated upstream tooling; no dependency deletion. | Static review or pending | — | See disposition |
| F-22 | Yes | `FIXED_AND_TESTED` | Replay pending expiry includes early-close buffer through session_policy. | Audit regression / focused existing suites | A | Offline proof; full acceptance matrix remains pending |
| F-23 | Growth observation | `REQUIRES_OWNER_DECISION` | Retention would delete historical evidence; no deletion performed. | Static review or pending | — | See disposition |
| F-24 | Yes | `DEFERRED_WITH_REASON` | Full-month event payload materialization remains; memory optimization not implemented. | Static review or pending | — | See disposition |
| F-25 | Yes | `FIXED_AND_TESTED` | ATM requires actual adjacent 50-point grid rows; exact midpoint picks lower; shared consumers inherit. | Audit regression / focused existing suites | A | Offline proof; full acceptance matrix remains pending |
| F-26 | Yes | `REQUIRES_OWNER_DECISION` | Eligibility stays ages 0–2; score normalization remains unchanged pending explicit policy. | Static review or pending | — | See disposition |
| F-27 | Yes | `FIXED_AND_TESTED` | ITM requires strike exactly one interval inside ATM, otherwise specific refusal. | Audit regression / focused existing suites | A | Offline proof; full acceptance matrix remains pending |
| F-28 | Yes | `FIXED_AND_TESTED` | Admission expiry and locked fill honor earlier configured cutoff; restart regression. | Audit regression / focused existing suites | A | Offline proof; full acceptance matrix remains pending |
| F-29 | Yes | `FIXED_AND_TESTED` | Selector refusal converted to OrderRefused after safe structured event, preserving specific code. | Audit regression / focused existing suites | A | Offline proof; full acceptance matrix remains pending |
| F-30 | Yes | `FIXED_AND_TESTED` | One SESSION_EXIT_BUFFER definition shared by risk, expiry and protection. | Audit regression / focused existing suites | A | Offline proof; full acceptance matrix remains pending |
| F-31 | Yes | `FIXED_AND_TESTED` | Field validator reports crossover_freshness instead of empty model location. | Audit regression / focused existing suites | A | Offline proof; full acceptance matrix remains pending |

## Regression evidence

Before production edits, sparse midpoint CE/PE and reordered records, missing adjacent ITM, off-grid ladder and MACD validation location produced **9 failures / 4 passes**. After those fixes: **13 passed**. Configured 14:00 cutoff persisted PENDING across restart at exactly 14:00 before the expiry fix (**1 failed / 13 passed**); afterward **14 passed**. Early-close replay regression failed before the replay expiry change. An additional off-grid master-row test failed before restricting the ATM choice to grid neighbors. The 20-test expanded batch then passed. Selector refusal test failed with SelectionUnavailable before conversion into the established OrderRefused path.

Focused existing suites plus the initial 15 audit regressions: **116 passed**, no skips or xfail (169.02 seconds). Suites: audit_remediation, macd_window, paper_executor, execution_completion, compliance, selector. Later selector integration run is recorded below after completion.

Final audit regression and selector integration run: **49 passed** (131.29 seconds), including all **21** new regression cases. Counts overlap the earlier run and must not be added as unique tests. Ruff check and git diff --check passed.

Commands use Windows .venv/Scripts/python.exe, NUMBA_DISABLE_JIT=1 and PYTEST_DISABLE_PLUGIN_AUTOLOAD=1, with pytest -q -o addopts='' and unique --basetemp under tmp/. Disabling JIT avoids startup compilation stalls; this is Python-path verification, not compiled-kernel parity. test/conftest.py disables dotenv and assigns isolated test database URLs. No production migrations or broker requests were made.

## Behavior and compatibility

The user approved grid correctness and cutoff enforcement. Missing grid neighbors now refuse ATM reference; strict spot-based ITM classification remains available to shared checks. ITM preference refuses a missing adjacent strike. Exact grid strikes remain valid. No missing instrument is invented; token, expiry and dated-master checks remain unchanged.

The shared cutoff is min(14:45 IST, configured entry_before, session close minus five minutes). Pending expiry additionally takes min(admission plus TTL). Equality expires. Admission persists UTC. The locked fill reads its order's pinned configuration. The mandatory protection buffer remains five minutes.

Source for short-term grid: [NSE NIFTY 50 F&O](https://www.nseindia.in/static/products-services/equity-derivatives-nifty50), Strike Price Intervals, accessed 2026-11-24; page updated 2025-09-23. Weekly/monthly interval is 50. This does not certify broker master completeness or longer-dated expiry classification.

No strategy/configuration version change in A: current 3.2.0, legacy 3.1.0. SuperTrend is still 10/3 on this branch, so approved 20/2 alignment is **not complete**. MACD stays 12/26/9 close with ages 0–2, ADX 14/14, VWAP session hlc3. No score formula, lot tier, target fraction, risk ceiling, balance or old record is rewritten. Execution corrections can change replay outcomes for affected historical scenarios; no claim of unchanged execution-engine replay semantics is made.

F-26 arithmetic: recency contribution is 10*(1-age/(freshness+1)). At ages 0/1/2, moving freshness 3 to 2 changes points by 0, -0.833333..., -1.666666.... A total of 40.5 at age 2 becomes 38.833333..., crossing the 2-lot permission boundary to 1; 70.5 becomes 68.833333..., crossing 3 to 2. Actual size still depends on every risk/depth/cash gate. Target fraction changes by 0.05*score_delta/100. Restoring denominator 4 or using parameter-independent normalization needs owner approval; neither is implemented.

F-15 exact existing arithmetic remains: planned loss = (entry - stop_exit)*quantity + entry charges + stop-exit charges + buffer; projected reward = (target - entry)*quantity - entry charges - target-exit charges. Maximum 400 loss and minimum 350 reward remain unchanged. No observed feasibility band is claimed.

## Safety and outstanding acceptance

Strict PAPER-only execution remains intact; LiveAdapterStub still refuses LIVE_NOT_READY. No real orders or notifications, no credentials, no Docker publishing changes, no merges or force pushes. Further work remains on F-10/F-11, full runner/API boundary proof, grid checks at every lifecycle stage, indicator migration/UI, dated fee verification and broader NIFTY checks. Pending items are not relabeled as fixed.

