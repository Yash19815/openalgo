# NIFTY ALGO implementation tracker

Baseline `main` at `de8456ab38d722fd1fd3b83b8c97ed6895684945`. This tracker records measured progress. An external market-data session is required before claiming forward paper readiness.

| Phase | Status | Local acceptance gate |
| --- | --- | --- |
| 0 Audit and design | IN_PROGRESS | Native capabilities and hazards mapped, research sources and Stitch mapping documented |
| 1 Foundation | IN_PROGRESS | Authenticated blueprint, additive feature tables, versioned config and durable controls pass tests |
| 2 Data | IN_PROGRESS | Pure normalization, causal bars, PCR and native adapters verified with fixtures; real session pending |
| 3 Indicators and decisions | IN_PROGRESS | Independent calculations, deterministic snapshots, missing data and look-ahead tests |
| 4 Contract resolver | IN_PROGRESS | Structured NIFTY-only metadata, dated expiry, lot and liquidity tests |
| 5 Risk and execution guard | IN_PROGRESS | Durable limits, concurrent intent protection, native RMS and final broker spies |
| 6 Simulated execution | DONE | Strict native fill profile, isolated capital, costs and confirmed fill reconciliation |
| 7 Stitch frontend | IN_PROGRESS | Six exported screens mapped, typed authenticated UI and build tests |
| 8 Native runner | NOT_STARTED | `/python` registration, rehearsal, schedule and restart tests |
| 9 Journal and research | NOT_STARTED | Native fill journal, costs, independent metrics, causal replay coverage |
| 10 System verification | NOT_STARTED | Critical scenarios, final broker boundary assertions and regression tests |
| 11 Readiness | NOT_STARTED | Runbook, measured checks and explicit external verification status |
| 12 Future live design | IN_PROGRESS | Documentation of separate approval, permissions and effective rules |

## Execution checklist

- [x] Produce file-by-file legacy migration analysis.
- [x] Record fresh local commit and branch.
- [x] Audit mutable Analyzer routing and explicit native dispatch branches.
- [x] Identify native fill/account differences requiring scoped extensions.
- [ ] Complete official research and export mapping.
- [ ] Finish and test module foundation and pure core.
- [ ] Implement verified native data and host integration.
- [x] Implement strict native execution profile and isolated accounting.
- [ ] Verify full paper lifecycle, journal and restart recovery.
- [ ] Run backend, UI and relevant upstream regressions.
- [ ] Publish readiness report with external session evidence or pending status.

## Files and reuse

Phase 0 owns `docs/nifty-algo/`. Foundation adds `database/nifty_algo_db.py`, `services/nifty_algo/`, `blueprints/nifty_algo.py` and scoped registration in `app.py`. Frontend adds `frontend/src/features/nifty-algo/`, route registration and navigation. Exact changed files and test results are recorded below as implementation advances. Native dependencies and engine/session conventions are reused.

## Open issues

The native Sandbox permits LTP fallback, lacks the requested independent NIFTY account semantics and does not provide the complete requested strict fill model. Live data credentials and entitlement verification are external prerequisites. The original video transcript has not been verified. The sibling source is read-only.
