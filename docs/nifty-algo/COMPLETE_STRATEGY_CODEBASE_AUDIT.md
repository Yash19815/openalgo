# Complete Strategy Codebase Audit: NIFTY 50 Options PAPER Strategy

Read-only forensic audit of the customized OpenAlgo checkout against the
trader-approved NIFTY 50 options PAPER strategy and the authoritative indicator
settings supplied on 2026-11-24. Nothing in the repository was changed except
this file. No recommendation below has been implemented.

## A. Executive verdict

**Overall verdict: `PARTIALLY_MATCHES`.**

**Audit coverage: `INCOMPLETE`** (36 of 4,055 tracked files read end to end
after the second pass, including all 32 files in `services/nifty_algo/`; see
sections B, S and U).

**Second pass (section U):** the `fd-audit`, `security-review` and `code-review`
skills were run over the NIFTY scope. They found no descriptor or memory leak
(static check) and no security vulnerability at high confidence. The
code-review added eight confirmed findings, F-22 and F-25 to F-31. The most
relevant is F-26: the 3.2.0 MACD narrowing also lowers confidence scores. The
verdict is unchanged.

The core risk, timing, PAPER-ledger and live-order-isolation rules match the
approved specification closely, and most of them are enforced twice: once at
admission and again under the per-user database lock at fill time. Gate 1 does
not match. The qualifications that decide the verdict:

1. **SuperTrend settings do not match the approved inputs (Gate 1).** The code
   defaults are ATR period 10 and multiplier 3 (`services/nifty_algo/config.py:30-31`),
   not Length 20 and Factor 2. No NIFTY configuration is saved in the local
   database (all 43 `nifty_algo_*` tables are empty), so the first use persists
   these defaults (`database/nifty_algo_db.py:978-995`), and they become the
   runtime and replay settings. Both values can be set to 20 and 2, but only by
   editing the raw configuration JSON. The structured settings panel has no
   SuperTrend control (`frontend/src/features/nifty-algo/KeySettings.tsx`). Every
   signal the strategy evaluates today uses 10/3 on both the 5-minute and the
   15-minute series.
2. **The approved MACD three-candle window exists only on the audited branch.**
   HEAD `58c77fc` (branch `fix/nifty-macd-three-bar-window`) caps crossover age at
   2. `main` (`574f71e`) still has `crossover_freshness` default 3 and admits a
   crossover at age 3. HEAD is one commit ahead of `main` and not merged.
3. **Confidence scoring hard-codes the legacy SuperTrend 10/3 geometry**
   (`services/nifty_algo/confidence.py:38`). If the settings are moved to 20/2,
   the SuperTrend contribution, and with it lot count and profit target, shift
   without any code change. Nothing in the code ties these constants to the
   settings.
4. **MACD 12/26/9 on close, ADX 14 (both DI length and smoothing), the
   session-anchored hlc3 VWAP and every PCR rule match by value and by formula.**
   ADX uses one `adx_period` field for both periods. That is correct for 14/14,
   but the code cannot represent two different values.
5. **Live-order isolation holds in the code reviewed.** No NIFTY module imports a
   broker, order or Sandbox order path. `LiveAdapterStub.submit` raises
   `OrderRefused(["LIVE_NOT_READY"])`, and the store refuses a LIVE mode change and
   any non-PAPER BUY under the lock.
6. **Conditional practical risks, unverified with live data:** the full-chain PCR
   freshness and 5-second skew rule is measured on last-trade time, and the
   approved risk limits leave a narrow feasible premium band. Together they may
   keep the strategy from ever entering. The strategy fails closed, so this is
   not a safety defect, but no evidence shows it can trade in a real session.

Nothing here shows that the strategy is profitable. Every test uses synthetic or
offline data.

## B. Audit scope and completeness

| Item | Value |
|---|---|
| Repository | `Yash19815/openalgo` (local checkout) |
| Path | `D:\DATA\Documents(old)\projects\Main_Projects\openalgo-fork\openalgo` |
| Branch | `fix/nifty-macd-three-bar-window` |
| HEAD | `58c77fcfc3a2af03a3962165bfa7f095a593e895` |
| `main` at audit | `574f71e8c50fccc96308ff7db4f00a7578c8c939` (HEAD is 1 commit ahead, not merged) |
| Starting Git status | clean (no staged, unstaged or untracked changes) |
| Audit date | 2026-11-24 |
| Tracked files | 4,055 (4,032 text, 23 binary; 67,398,236 bytes) |
| Untracked, not ignored | 0 |
| Ignored files | 674,053 (aggregated in C.2) |
| Submodules | none |
| Tracked symlinks | none |
| Untracked filesystem links | `frontend/node_modules/openalgo` is a directory junction to the repository root, created by the upstream dependency `"openalgo": "file:.."` (`frontend/package.json:61`, upstream commit `48820efc1`), so the ignored tree contains the repository nested inside itself recursively |
| Inaccessible during inventory | several `tmp/nifty-*` and `.pytest_cache` directories (permission denied) and deep `node_modules` paths (filename too long) |

### Review status of tracked files

| Status | Count | Share |
|---|---:|---:|
| `FULL_TEXT_REVIEWED` | 36 | 0.89% |
| `BINARY_INSPECTED` | 0 | 0% |
| `GENERATED_ARTIFACT_REVIEWED` | 0 | 0% |
| `ACCESS_BLOCKED` | 0 | 0% |
| `NOT_REVIEWED` | 4,019 | 99.11% |
| **Total** | **4,055** | 100% |

These are the figures after the second pass. The first pass alone reviewed 19
files. Of the `NOT_REVIEWED` files, several were partly read (the line ranges
are in the manifest notes). Several more NIFTY and shared files were searched with targeted
patterns but not read end to end. A search result is not a review, and none of
those files is counted as reviewed.

### Classification of tracked files

| Classification | Files |
|---|---:|
| test | 856 |
| broker adapter | 729 |
| frontend source/asset | 656 |
| documentation | 583 |
| generated distribution (`frontend/dist/`) | 400 |
| backend source (`blueprints/`, `services/`, `utils/`, `sandbox/`, `websocket_proxy/`, `mcp/`) | 363 |
| configuration/other | 163 |
| backend source (other `.py`) | 133 |
| database/migration | 92 |
| tooling/script | 77 |
| workflow/CI | 3 |

NIFTY relevance: 171 files carry "nifty" in their path (`DIRECT`), and 20 shared
modules that NIFTY code imports or depends on are marked `INDIRECT`. The rest are
`NONE_IDENTIFIED`, which means no dependency was found by the searches made. It
does not mean a dependency was proven absent.

### Limitations

- The request asked for a complete, line-by-line review of every file. That was
  not done. One session can review about 6,000 lines of the NIFTY core with care,
  against roughly 67,000 lines of NIFTY-named files and several hundred thousand
  lines in the repository. Review effort went to the code that decides signals,
  contract selection, risk, fills, exits, mode and live isolation.
- Not read end to end: `database/nifty_algo_db.py` (5,260 lines; about 1,200
  read), the remainder of `blueprints/nifty_algo.py`, the notification, Discord,
  report, research and analytics modules, every NIFTY test except part of
  `test_nifty_algo_macd_window.py`, every NIFTY frontend file except
  `KeySettings.tsx`, and every historical NIFTY document (searched for settings
  only).
- No test, build or application module was executed. Behaviour was established
  by reading code. The only computation was stand-alone arithmetic for the
  feasibility band in F-15, which imports nothing from the repository.
- The local database was opened read-only (`mode=ro&immutable=1`) to count rows
  in the `nifty_algo_*` tables. No other data was read.

## C. Exhaustive file manifest

### C.1 Tracked files (all 4,055)

Every tracked file is listed with its size and SHA-256 at HEAD (the working tree
was clean). The review status is the one this audit earned; hashing a file is not
a review.

<!-- manifest rows: 4055; statuses: {'NOT_REVIEWED': 4019, 'FULL_TEXT_REVIEWED': 36} -->

| Path | Type | Size (bytes) | SHA-256 | Classification | NIFTY relevance | Review status | Notes |
|---|---|---:|---|---|---|---|---|
| `.claude/skills/broker-integration/SKILL.md` | text | 26631 | 550e410e318b5d1fdd4b7216a2b18fa3bd5045b71e844626f8f5fcb86dac6131 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/broker-integration/references/auth-and-login.md` | text | 30580 | cf98caa0fb7a227c2ab76fcfbc1d244db98904aab5a4a5e8c7e146d33e071744 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/broker-integration/references/cross-broker-reference.md` | text | 5807 | 4ebc72ce2c4f11c0b0f5bc5f4346faa4d4d470e3118de76abf5d82e430e93de5 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/broker-integration/references/data-and-account.md` | text | 18302 | c68725c8a8baf228bdbd532276e6e655b80b4f7c05d40513772ed4d60dd75fc0 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/broker-integration/references/hardening-and-verification.md` | text | 15592 | 6af289fd255bf574676c7b095c72549fb3a0f4da6e355e00e03f93b1afeed6e0 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/broker-integration/references/history-data.md` | text | 13131 | 07fa5a221d96db6e68895f0f90fafd3611a3df95d60073aaf0ad76da13b95175 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/broker-integration/references/master-contract.md` | text | 12571 | 455bbb6fa420c34e4d3aeeff69cf56049ec38578126be1f5e143de869615ab4e | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/broker-integration/references/order-type-emulation.md` | text | 8738 | f37f9da3d0cce711bfebba185c93253d7ca4a9ba2e91aec60dfe8eedeca12539 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/broker-integration/references/order-updates.md` | text | 8650 | 6cf588b31d1d64cebe873665e7fc53bcd35d43b1d76529e54ea637cbbc47a9e7 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/broker-integration/references/rate-limiting.md` | text | 8196 | e2d1803dbc52d88a5eae4e566b0ce9e10b9bf46d3da81a2ead5b8b553f2e35e1 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/broker-integration/references/streaming.md` | text | 15686 | c770e46ebb59581966bfaa64d393e1578b133537fe4ca0895bc3922327598f24 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/broker-integration/scripts/check_nifty500.py` | text | 7975 | b2f4802ecf7c3f6a5b85014226a258490730ec2daef07255c678aee5c46aa4fb | tooling/script | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `.claude/skills/chart-indicator/.gitignore` | text | 9 | e98b489fc82363b3989c677a3dffa5bf13a21edfbb20581af7f1a32377273272 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/chart-indicator/SKILL.md` | text | 42191 | 89e2ad99a309f50c36828400ad9b7f28b7c738c875bc5a058026482c5f342cae | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/chart-indicator/coverage.mjs` | text | 9513 | 3fdf714c941bab8feb9595d47b55986233853c663dc56f6f6a871d16126f1b96 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/chart-indicator/examples/complex_session_vwap.js` | text | 8888 | 045ccf993d4e67ab6470cd398b645e7b501adb36dea2db46e0b35bd8d20cca2b | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/chart-indicator/examples/dashboard_table.js` | text | 10347 | d4107a36c9a43eb96656d1a64e69bd0f2fac0a261609f0ef914155109b458912 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/chart-indicator/examples/displaced_cloud_zones.js` | text | 7627 | 413bbb6daf1dfa25c1be6b4b55312dc7a1b57b60968145442206335d276fb00a | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/chart-indicator/examples/ema_cross_signals.js` | text | 3537 | 29cf8d37adffb0edfa5d4377139c8696bb8b8dcb7c9cc13f17cbda814932c725 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/chart-indicator/examples/heikin_ashi_candles.js` | text | 2679 | df2432dc330e9db8b12c6992d55a59710cb82ae78d2e71e2f67897fad7bd0fa4 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/chart-indicator/examples/higher_timeframe_bands.js` | text | 8659 | 02102b68dd2e42cf0fe78fdc667968d4c8eb383c34049f96aa32cb86672f0e27 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/chart-indicator/examples/intermediate_keltner_squeeze.js` | text | 4593 | 237c67af4fedec379a46d3ec9f0361f42008b50afd7053870eefd5dcae6c2424 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/chart-indicator/examples/regime_shading.js` | text | 5581 | bda211b9ac34e60f62ae5e406fc75fa577fc7dc5d284688ab669701dcfaeaee9 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/chart-indicator/examples/session_range_modern.js` | text | 6375 | a36fe4123bc9fe23f3d5a65ec9ea4f14105e7e2206edf3c516fad49f248387b8 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/chart-indicator/examples/shaded_trend_zone.js` | text | 5212 | 93afb42510fc8b6f7668514d85ee66ff11d6d6958e1f9bd3b3901afc2a8699de | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/chart-indicator/examples/simple_zscore.js` | text | 2046 | 8ecc25eaad8c7363045aa0ed1194335e1af23ef645cfc0b172892efbece39d0a | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/chart-indicator/examples/tier2_external_data.js` | text | 5335 | 5017fb240c92b70aedbb4cbe7e9406773a1539e25a33bbf62d009391c0964a17 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/chart-indicator/examples/zones_with_draws.js` | text | 5619 | 1c8cd841106ffd7086ff15b137888fc326a85ca7c6bac92940caddf5e6927523 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/chart-indicator/generate-api-index.mjs` | text | 10737 | fef2cf03ff35a5dbb5d5eebfd917885e818ee717d3a856a174f8a7f9a9f94b79 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/chart-indicator/reference/api.md` | text | 38914 | 777d95845cd6b4ba18eb262f6e60862a4959cdb340e070ee844a359ad85488f0 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/chart-indicator/reference/contract.md` | text | 21737 | 91def275a28276b705a928016bf0c3e97058c56c3ef232698e01ea5b93a3eafa | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/chart-indicator/reference/cookbook.md` | text | 16027 | 2bea47e49d4a9407546dfdbfa03023cd2cb6b8316f84ebb64a6666dcee8ee337 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/chart-indicator/reference/pitfalls.md` | text | 18556 | 9b36e7383a8ab4692f56df6b9a9f64602326d0c3d10ec7afdc1bf41bbb28f3bb | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/chart-indicator/validate.mjs` | text | 38431 | c31c3e805a23299ac9740456d3a5e4dda3b1af797fbc92539756c59f8d45c84c | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/fd-audit/SKILL.md` | text | 8762 | 0422295b79ce498fd4cc51a6bbcd950bcad7c75bdb1fb19d8353d4a09443daae | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/fd-audit/soak.py` | text | 16001 | 168d6c33608cbba20af6f246966bee0f91c04946ec469606c45c53df4754492c | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/flow-builder/SKILL.md` | text | 8630 | 0af3fbdc866dee0768d96cc5287bf59982b4328ab0ab40bcac3a1f1f67950bd8 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/flow-builder/coverage.py` | text | 2530 | 509bc8b7fb016f41c27d814e57126949a087b6c28988dc4d152549dac1d0b549 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/flow-builder/generate_reference.py` | text | 6887 | c39185cd677c379d8847a04efaffe5b68e740d49c5c585f9c3eb307005e1ff52 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/flow-builder/reference/nodes.md` | text | 7023 | 7539971a601019829f607e26ce35bcd7f3a9f9a1fd3dbce098a5379122a36a1c | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/flow-builder/validate.py` | text | 5203 | 94cb26b3fae8fff779c556425203b775ad24d08cc625ade4b3c884057602b396 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/grokbot-setup/SKILL.md` | text | 15385 | 38b7655bc07f5969fad7fb73bdb312ee34b7daaf38bf972e1a50c1f1aac056d0 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/grokbot-setup/references/brokers.md` | text | 13979 | 4682953f0bcf64dfcf7461299fbdae8096e579b9d7b8cdfa4a2a1d3ad81fd357 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/grokbot-setup/references/install-and-run.md` | text | 7398 | 44359ed056e2913d79cd89a7321d0f729935e8c1792d5d7fd7f25eec17f6269f | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/grokbot-setup/references/login-routines.md` | text | 7561 | 14483a3106262d7b32d288b6e2395a556c67f166b27457e766f7f74793d0132f | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/grokbot-setup/references/openalgo-knowledge.md` | text | 34889 | 2e24373362374ce9ed58a6836ef09e5ef8ac87f1a9aca9daeecb019f5e13b087 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/grokbot-setup/references/weekly-upgrade.md` | text | 5339 | 6d68919bb9c5b1909b189b19bf92c857572dab7fc58bffd64d29ec0b48a50546 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/openscript/.gitignore` | text | 9 | e98b489fc82363b3989c677a3dffa5bf13a21edfbb20581af7f1a32377273272 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/openscript/SKILL.md` | text | 9410 | e41e15f4442e0037306eff43b728177263590a463d92427fc2bde69d8e1aa754 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/openscript/check-pitfalls.mjs` | text | 14222 | cbc2c14f59afcbc2b9257ce55f48f43dc5f7a2b1d90bfff01dc26940614b27cf | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/openscript/coverage.mjs` | text | 13800 | 3098f8f8bfcb2a82817835a617ed236ef2e1470e58890a7981431aa4d2e415c3 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/openscript/examples/intraday-session.oscript` | text | 3006 | eaf8252c6c5b32d699f1fb08fb14bb08e8d3bff3b89cfbcfda86e2e919689939 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/openscript/examples/long-only.oscript` | text | 1056 | 982047353a89f29fa53b0740c2302469902764a59675cc7d922072824236362d | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/openscript/examples/short-only.oscript` | text | 1196 | edaf9a48083daba76eaca27f36d282498dbb8b152a5f88ac2ebb85abf3a17ba4 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/openscript/examples/stop-and-reverse.oscript` | text | 2600 | 04e71aae87190e973567fc77e4b11182566ecb46e795a27efa2fcbbbcf241bb9 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/openscript/examples/stop-and-target.oscript` | text | 2409 | 08742bda2d36073a5ddba9df79754e5e2609c028da8c84cddbf1b0c9f8be1d17 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/openscript/examples/study-bands.oscript` | text | 1455 | 4c5d90393fa1dc2de332d5bc7f91282ca86d17f56b8f74ebeb435cfd4c894731 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/openscript/generate-reference.mjs` | text | 13744 | 05d4c41be6f8438f92f4bb782f257b5122871939255f93ffdae081e72673bade | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/openscript/reference/library.md` | text | 33923 | 2e76495f79db75a70e2ec548ca07438b320ea4491f0a1c2bc5f832aee77cc539 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/openscript/reference/pitfalls.md` | text | 14141 | 12207e33b2e92d404cad5939c34db8c90acf58a7030e9fcafd9fed6872c098ce | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/openscript/reference/porting-from-javascript.md` | text | 30522 | 3377ba7986ee5152c19bb68629ad6343920fb8f1dfce80516fbf9f0127e424fe | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/openscript/reference/strategies.md` | text | 8939 | be0c589e39ab003ff2a58e6ad142fd05e6857c6f35a4bc73119eb62824a73317 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/openscript/validate.mjs` | text | 13506 | 52fcd8c36d911c579638d2035c078499619e466021808b1456a85f77bd3da702 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/python-strategy/SKILL.md` | text | 9872 | 50b02dde3b78caefddae2de069b0aad2d198c15f232ee3c1b1ccc634b71f7d3e | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/python-strategy/_host.py` | text | 5152 | b559bb9b209b6781cb8face139ba5e47693d37bbeb6a4920a3aef4222a3410c6 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/python-strategy/backtest.py` | text | 14404 | 13d6da34458c03eaeb5bbf8cfb23a1726dd214537fe63e262024e11efd0293a4 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/python-strategy/kit.py` | text | 43447 | 8cb925b326a89c2ee26ca85413858a955c11b1ce04de6d55738e6d31122a1859 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/python-strategy/kit_sync.py` | text | 3161 | 564590febe09ebbb61769c6aa7f0d311b7fc5628623d1e51f81fc1712cd3a630 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/python-strategy/rehearse.py` | text | 22225 | e9dcffdc43816d71f906f11cb5a1c1d25dba6e1f2ab724c3b419398028db26ee | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/python-strategy/templates/ema_crossover.py` | text | 46582 | 134837ad74a07bf2955e42e3cbc09e2d0d469e94fd315c98950b35a44480c35d | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/python-strategy/validate.py` | text | 25302 | e5a62d584e91c8d7a4d01b2e3361a0aac4889224c93f91bd9896fbd439632c9a | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/security-audit/SKILL.md` | text | 7678 | caffdb870961242b2898e5dadbc9c9971d145df384173ac8928ef86c1d73214d | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/security-audit/audit.py` | text | 55723 | 209f2ab1c0f5e59fc05b47497db2b77839a1133ba55e8aaca34f5ff55e5b5f8d | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/verify/SKILL.md` | text | 6625 | 3511c367798ce28954baabd6fa64779de49772a0a1f7e658c43dab16788f4cd9 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/verify/redaction_check.py` | text | 2628 | 17ebc3964c56294196edb06fc714ca91a8ac0133485afe4535c7d83e223119f2 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.claude/skills/version-bump/SKILL.md` | text | 7269 | 4bd67dafe9306a169bea0f93137461dc88a003c800bf07f1446e10575748c526 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.cloudflared/README.md` | text | 1967 | e89fdc418e12ad8be9e16fbf34e419f234a163ab7740094b912f5dca83071208 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.cloudflared/config.yml` | text | 171 | aa085e291f40b9f76cbcae4e8130eb42b5d5e122c6e83324d02d2ea638c34c5a | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.dockerignore` | text | 1342 | dd3fa3f961db86133e3ba71bba06eff84d9c3e7c96d26ccec7025d5082ef5449 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.ebextensions/01_flask.config` | text | 1097 | 1b295b690efab6db89b869fbccab48d4b1c51172ebc9bd3523fca0e220ad1a01 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.gitattributes` | text | 394 | 6389158876aa9d7403e00c1f0d3442529a4cdd6856d2318f5ee66174639427c6 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.github/dependabot.yml` | text | 1564 | 4db9b9ed51ebfa8935d98cdab3248d67e304e4cfb08482bc4924fb95e791ca2e | workflow/CI | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.github/workflows/ci.yml` | text | 30157 | 91b8661198f4b3e5ecd6ad12320930fa2a7397dc680c479bd5ee1cbea4678f45 | workflow/CI | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.github/workflows/security.yml` | text | 2962 | bb6d467ca02d296c79d48fe4e3d41e8e6baf78546b815d4dde241c0d6dd35b65 | workflow/CI | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.gitignore` | text | 4234 | 1898468c7a4190faae1833ef0818b9c1236190bc2c05ad4994e6b860890d5a83 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.pre-commit-config.yaml` | text | 1130 | ba8b35b6811d6471e96e4edf108553f68443a1d5c8530e0dacb1c207758f2e70 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.sample.env` | text | 22993 | 03d52ac1db5c518f2adca640ca1d1546ca85ea455ebc892a521282e77930bebc | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `.secrets.baseline` | text | 2678 | 1b52d4b8ebedf96505dbc576a3f2f16a33483ece62831f1e2591015f7e9551e8 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `CLAUDE.md` | text | 72896 | 3767f514f8e49a2b88fd6c69f075bab44ff612177287606e000d34f576d68306 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `CODE_OF_CONDUCT.md` | text | 3386 | b998e71ecc19c4874f74d8d1cbf4f7de2cc0522144e518f10d961a9697bda8e8 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `CONTRIBUTING.md` | text | 40978 | 08201350a2aef231d313e38152f93ec1af2c8274b034d546e50395862280f64e | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `Caddyfile` | text | 53 | 9f29ebe26b1b38e9d5066b33adafc0641de633e21cd01ecb69b9d47af31c9b88 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `DISCOVERY_MAP.md` | text | 65558 | cb6d7f9b9cbce1f6b0a88934a3c6680c5819b386bec73b68c52e0d3365bb605e | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `DOCKER_README.md` | text | 2336 | 2d777ac8df2c5290223652d78f827bd4d9575c85882437d4349e141589ecf79c | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `Dockerfile` | text | 5598 | 4ebbff4cfa10be4e28bf839d7d09c3c4a36ad0813c0e819ebf247c5034a2b1a6 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `INSTALL.md` | text | 1507 | f9a90bdb83edfe1c8ce212aea6897e8d843ac574c7e230061c0ab7a5ecedd53f | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `License.md` | text | 35181 | 6da1054eef20b8949622f2acc5a89c3243ff3b3d7aa8c2bb8fa5c04d15113c00 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `NIFTY_COMPLIANCE_AUDIT.md` | text | 30763 | b4bf523c418a0aed948c003643164678f62fcb972e822716b14efb891d465b7b | documentation | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `NIFTY_INDICATOR_PARITY_AUDIT.md` | text | 46870 | 6c82dd07694dcf9afd1e725ab96ce92e418d4eff57bb162e4a849ed360dcfcb7 | documentation | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `README.md` | text | 29429 | 05f96e3587059335baa402a587265db55aaaf3a1241987cf68be1baaed0cdaa2 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `SECURITY.md` | text | 2526 | 764874ae3c4fe3f3faa2f032ef291a62108f4c7e3c4dfdfb1e0d0655c7210a11 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `app.py` | text | 63164 | f92778541a9543529438f63b1efef8d54777f44364b8cb4343a079ee3ece397a | backend source (other) | INDIRECT | NOT_REVIEWED | PARTIAL: NIFTY registration, CSRF exemptions and teardown (1105-1164) read |
| `apply_nifty_report_recovery.py` | text | 14211 | c9ff7184932203a6324b1af14e3f949cc211963ea25f5c615722f04f3d77237d | backend source (other) | DIRECT | NOT_REVIEWED | PARTIAL: header and write sites only |
| `apply_nifty_safety_fixes.py` | text | 9630 | fde68729bd20afca35caa80483dfecefd3c43c6bdab79e0649261b68b7d36eb2 | backend source (other) | DIRECT | NOT_REVIEWED | PARTIAL: header and write sites only |
| `audit/BROKER_API_COMPATIBILITY.md` | text | 12248 | 1582147b30dc497823619ad0b2be841cb7f484f2f6b057ce9b428c974cce02ee | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `audit/FD_LEAK_AUDIT.md` | text | 17041 | 8dc2b7884ce8fbd163aa4b3586170ab9aeb972435e1ebb7dd66a1a3945a57828 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `audit/STRATEGY_BUILDER_PAYOFF_AUDIT.md` | text | 46534 | 1c9f3828e145620fd116546ccadd02119effcf0a5bcc99f28df7d9eb7c3d081a | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `audit/STRATEGY_BUILDER_PAYOFF_FINAL_AUDIT.md` | text | 66325 | bf4f16b7556b1ec32e4d311bdb4a425756218325a2f3dc5dfde0b771c79d7a77 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `benchmark_api.py` | text | 3470 | 45267da086754d65ff06deca0598d2f44d39170f449fa6bcb533b0895f93cad4 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/admin.py` | text | 102608 | 2c7006e98db21792f30d99e8f6f54a89a37001ef603ed79ba463152d37012447 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/agent.py` | text | 124671 | f2130fa3b49480ac1d1716edd6e6092cefcfdd51653dd113c68ff9e953561ab1 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/alert_channels.py` | text | 7284 | 78dc6d4a283641fcb2bd452e5eed2c5d2ebe0eacf81d1b81fc7d658a153b2883 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/alerts.py` | text | 4451 | 869ebcd822a8e06a842241114a49a38cf87b50c9da3c7dade46eef4b61bf2dac | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/analyzer.py` | text | 11936 | b2a6f64a0b763bcb8ce2965277f3419c19297f841867652e6967a2c6342dbde2 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/apikey.py` | text | 5512 | 7a0a250acd1f100afa802c9e78a6f3036b727edeb095fb83477e931975068975 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/arbitrage.py` | text | 2100 | 019e6147c5fde35710e4982beb108573767f96f474bdee6d41f7bb3cfd205cc1 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/auth.py` | text | 70533 | 842c64863b6c506e93c4ff148e243bcd9455c864414a4fc83125c0a766a939c9 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/brlogin.py` | text | 67937 | 2fc9d8cfcc798c14c9b0f5731b6f4cf4b7088b4d45f93c878b70a28a94938961 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/broker_config.py` | text | 13635 | a76af1e2a649df2ec70746bed215cf20bb018d5c590ffb6a943e864cf2d12e96 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/broker_credentials.py` | text | 8047 | 37e4f24835c9b92f5441a7ed29f8139f7b85545b62e0dfbd9c9a0cd84d723d46 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/chart_test.py` | text | 7200 | 899d621af4f5879edef1c34052394eb8f9ce0deaed90afc6fc3ada756c132e3b | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/chartink.py` | text | 45646 | 0299909633fd733a7c3179ed2487b1841f84d41aa2fba56021516eebc66fd453 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/core.py` | text | 3245 | 7060a4738b25f8d384a0fbf30797ab72877c53daf88deaa9fe8013cbfcaab65c | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/custom_indicators.py` | text | 4528 | 1bc192e2902287c4da51a82a9c69574ae59140b03fbfd0a5a6eebaad1325f604 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/custom_straddle.py` | text | 5170 | 6d8d8e929955dc28be00ffeb3de4e154e740197a77b409ffbbd105ce6b74bdd1 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/dashboard.py` | text | 2615 | 3e598ee241740bfe87743e80c84d96b1ede025156c696f095902007478f6c70e | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/flow.py` | text | 72059 | c484a2b33b4cbda3776629ed2fc830c0a4c25b3d3d292ef09ff06c6c608aaa98 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/gamma_density.py` | text | 2870 | 694b6613ba0e1a7efb86839682528e3a4ca4021b4c5cac64de2a4b3ac8d45a5c | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/gc_json.py` | text | 3044 | 29e34495dfc51a6c81485a9b726533945725cc13faabbdeeb3490d3170ce55d9 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/gex.py` | text | 2588 | a3f8fa565a3c10e508efb771792f984f831276ec07db33a39992e570057eeaa5 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/health.py` | text | 17445 | e396c7eda06867f7aa383378cec295065fdfd51bcf44b3ffbdc97ef2625383d5 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/historify.py` | text | 59712 | 339d586933d6d6c41338e45712f9833ad014f4e015d643fc2b9b739f7551fbc3 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/ivchart.py` | text | 5213 | 11b2b2b38609b8b8cfd7725a017a936447dd7aba625228455af0f71e415412cd | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/ivsmile.py` | text | 2655 | 44c62a76724f4aab29a11c14e15bc82df93233f7d40a71fa8086529a2e14034a | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/latency.py` | text | 11064 | 5862b28115f46a30fd1f3437a559102562810eb3499c2e5bf624fa338faf98ed | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/leverage.py` | text | 1946 | 83b65942c0d4485fe86a2c88766ec17df126984ad0d48acdbc20554dae5a87e6 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/log.py` | text | 10285 | 745c3bd064813899297080b092829fdc79dc0b78d8f3746b3fc7d44f5a3e3849 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/logging.py` | text | 605 | 907a1223d44f970de6efa159ccd62853f03eb02f36bfa0f714102963ddae6664 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/master_contract_status.py` | text | 9689 | 8cbcb2381b748d2b973c942b299e444783d423a8c7e22676463aeb5e60c246d4 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/mcp_http.py` | text | 45517 | 75512e832a69be437918a07bdc1b4fe4813ec0729a082637965a5615d1e30a50 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/mcp_oauth.py` | text | 41902 | ac13d5f03db4b28de356e2ecafd54f5530f35361ac350550b4cb511c1321a111 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/nifty_algo.py` | text | 51746 | dd4adf231c095648693915f3a18dfa33e1e6a916284e3c45c6762b4cc3c852ae | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `blueprints/nifty_discord.py` | text | 10490 | 5c4fce4dfa06d5961b7b93d83e7f8c1c9cf76a6d5b30012847807c6d8a07d5dc | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `blueprints/oiprofile.py` | text | 4736 | 31597c4a38291265d7da7f3a930ae8e2c04bcf5628979e653aca7ad61b4d5d1c | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/oitracker.py` | text | 4671 | f4347286666afd38c738c9edba176c8a88c48b93970db73a1ae78dcbcf9a3c89 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/openscript.py` | text | 21285 | 8cf11ade17bc812f90e916e342191b899366e690e29ff27d7ceee40c88a28026 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/openscript_runner.py` | text | 61703 | fd3c4a39b0cf00eb9a538eab51f4e6ec45d822edb864b9e0e80451e0778da240 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/orders.py` | text | 49510 | 054891a3871fae7dea5b519b647c42786179fd80b921e038deaae50c772e4918 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/platforms.py` | text | 482 | c9f0b40b96a9d7128e52464c4a58615d700531f9f144adf23d43e95b8f75b8c0 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/playground.py` | text | 14002 | 8c2f07a3a3f6752126e39360d4ed503062c38841315ea14d4a747188544287ca | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/pnltracker.py` | text | 52440 | bb79cd77a8aa7fb8625ffd14f80bef2b430deb33331e80edc88eaf1b28499de2 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/postback.py` | text | 15723 | 11be4285f88566dc664978a89ab27b0f028f8fda832298685917c58e81a2b335 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/python_strategy.py` | text | 164752 | 78bf4975682cccc0cf978b4dda13386b2c1397cea53e5e2267b00c3b06dc9600 | backend source | INDIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `blueprints/react_app.py` | text | 27912 | 824066140b1980cffde8c33d953421c74b72737526242f3131e8a6b8c56e4cc1 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/sandbox.py` | text | 58679 | 715727a59caec11843b240bb192817ffc2d45239910defbea96fdc55d228b7ed | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/scalping.py` | text | 41515 | 95999c781963a816adc5151d5fff6fa41f57abbf9589ea84f7b9f5787a7ae026 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/search.py` | text | 11465 | 7cc3cb21f0050ccf139c9b8ad4aad8db4828627d02945dadb40262be9e1fefeb | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/security.py` | text | 20387 | f0f2e622220d843f21fbd5b91c9a63c1eb2dd274b76929c569ca770467876b7f | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/settings.py` | text | 1841 | 7c9c5a11413e65a516b7b16d8df0b6a7a57ea9ab592a0f30132d630328684c87 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/straddle_chart.py` | text | 3313 | b008ea8bc3a0ee5065b0f7a81842b9c3ac66a04988105eb1d731c6cd6f4851e2 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/strategy_chart.py` | text | 8376 | e5dece610df8caa53f98c50462e8bb218da57026e2a5ff00cbd820e2c4ca90a3 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/strategy_module.py` | text | 78522 | 9d73296bbbaff56103326cf3195b6a4261bbf0fd0ba2be24cb6e943f9197b63f | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/strategy_portfolio.py` | text | 4522 | 1f9e773056aa4e08b0d463ee6eb92a9bfba185ab29ce2c2e8cac999e776e1f15 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/strike_profile.py` | text | 3584 | 9c2f4efd1b080d8bc8b603f7c44bae79adb612f0ce8d38a4536d20a4f736e372 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/system_permissions.py` | text | 14259 | e7c2dd3e9b56befee9ba3d9d92c376cce300950a78af6778ec50f3b8ba43beeb | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/telegram.py` | text | 17758 | 2da94d0aa9a279fe593e0b0a1f8928688e076a04b5d4433f3265c77169a34dc9 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/traffic.py` | text | 6850 | dee5506b3082d84ce2b2844f548b9b6b5f9bcf96efce14ca8b8a7ba7f55df353 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/tv_json.py` | text | 4364 | 38fae61d0289e853e86cc33cac91660810193b76dc5d078b55fbea431c45552f | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/vol_surface.py` | text | 2644 | f447dc9d6fd8726496015594508482c1de3424b4447a5cb4aa5a0e93c308de19 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/watchlist.py` | text | 6480 | 94d77d468adb7519d57b2183944c1673859b40286fa906816d5289a238f18ae5 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/websocket_example.py` | text | 16374 | e7ec23869f6336b3672139e8305a9dac56c97507760308f79d202a60dcf53ee6 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `blueprints/whatsapp.py` | text | 14970 | c16f260ff8eb588f31e960e10bb81b69db00263aa8a0a0dd7fa1e16ccd58bf4c | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/aliceblue/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/aliceblue/api/alicebluewebsocket.py` | text | 46605 | f90ad3afdc46d7f0f618ff31dac178187bfbfe0200259345c799ce794bc5f586 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/aliceblue/api/auth_api.py` | text | 4223 | 65a2eb9afefd13a12333e3423bdb08439f226e844c1de983a8f05c75e50b5edc | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/aliceblue/api/data.py` | text | 51051 | a25bbc12581d6766f60b9efe8bceb088e0da7f36a4609b06339a59d6c8009e47 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/aliceblue/api/error_codes.py` | text | 10004 | ab966b958389de54c40b10a3d0059c4d83b5f5e3756915304a79dbb03d688315 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/aliceblue/api/funds.py` | text | 4020 | 5e98f6038b7e3a978721ab910f1a3adb903ee7a3751b6cf4461f6d76df24417a | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/aliceblue/api/margin_api.py` | text | 632 | 32527b90e27826b7d02559818ce387c426da8d1f3d945c3ec64ccfeb3cb85a30 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/aliceblue/api/order_api.py` | text | 27683 | 1d148a79b01b161c6ebf6164b2e63e9b8740c9bfcd1b46af0ffefacecf3907e1 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/aliceblue/api/rate_limiter.py` | text | 5039 | 8cfaa148980393d21418c26606ab94a8e361ad213dca02830cb6ccb5eb3cc109 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/aliceblue/database/master_contract_db.py` | text | 30053 | 2477f32a4ef9dd6f9b61670d1d21e0d154cc8692ff98b162eb4f6d93b3ddf800 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/aliceblue/mapping/margin_data.py` | text | 1090 | 8c6d20bb5cc0fd3106c56f1475ef8f51898d0ba6e8c3fa80ce5afc43b745602b | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/aliceblue/mapping/order_data.py` | text | 29256 | e328ed5755bdf21fd2f492853acf390595ab31ef25cf646ef65dce029a641039 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/aliceblue/mapping/transform_data.py` | text | 4024 | ba707ae3d78cfa240fee051c7b288cb5df268872f05038526392e1df715da06c | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/aliceblue/plugin.json` | text | 396 | bab5d2748719b7d020dc4d0b266cefcf39f2cd286cf063da140a9286b8925a54 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/aliceblue/streaming/__init__.py` | text | 998 | 5e7cdea8ccd212a1d6a167864de592de72fb5038cefb136783be87dbc0f56e0d | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/aliceblue/streaming/aliceblue_adapter.py` | text | 61720 | e1d4f387d6b5cb7988a7e46382665a0be0e50a468af62bd44b5d2999842eb234 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/aliceblue/streaming/aliceblue_client.py` | text | 13400 | 8ae59e01825806b9781d7c8cf4f6570b5fc834f504d7209a27139f211deed6ed | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/aliceblue/streaming/aliceblue_mapping.py` | text | 9174 | 1240bdd3f320d19425f9a5b822f9e5eb7c06fa46a0d06e21ace7a67d0bf718fa | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/aliceblue/streaming/aliceblue_order_adapter.py` | text | 10325 | c1161c202c636c85d7cc36facf292b60c268df5ae973ac2966403b10f0e254e7 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/angel/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/angel/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/angel/api/auth_api.py` | text | 1800 | 4501c2f3595760d8419455bf45d9dad2383d182c6b1988ac79a990d8e1e3201e | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/angel/api/data.py` | text | 39066 | 4e0bb2814adb4b64071327301bebd8537450927dac481a20f3f0f18cb108c07a | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/angel/api/funds.py` | text | 4322 | 3e5d39748b4f3359e42d67d6e3f31233afe1ad4db5913e496b087bf72cf4e223 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/angel/api/gtt_api.py` | text | 21623 | 335c269b63dc88d8a6da1b43c936f21747c58aea786786b59d21da8003c38d30 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/angel/api/margin_api.py` | text | 3152 | 777082540fd3b2a5820ffacd78071aaf6acd533c657e2eb4d6fe633cc56db0bb | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/angel/api/order_api.py` | text | 22634 | 1dffda3002bdf8377c2ed5f96b95d36472a30f29b89170849d9476ba4d86f46b | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/angel/database/master_contract_db.py` | text | 17328 | 4f6e1d29f7837a22483646837985887c291e399b33ddd8ebdf2409b98ecb2bac | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/angel/mapping/gtt_data.py` | text | 10945 | d11363e162136ab3006e4fe3c45d1df080b6ed7de74cd23a011ce06f30e65630 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/angel/mapping/margin_data.py` | text | 5488 | 0ff2857e0d6c0f3e5d5e6bdd4e0a587eff9064158795b751798b128adcfcf93c | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/angel/mapping/order_data.py` | text | 13627 | a9e7030239a8164feb2fbda54240ed9bd63d8ea09cbe12d5e9343fdcb43e9f97 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/angel/mapping/transform_data.py` | text | 3519 | b0555e85d44c0abbcc68109dcb29e10c8d9135177aa76cd52ad1a20e40cc0f62 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/angel/plugin.json` | text | 391 | 74c68ccfd96e8a839ea895c105229922f03e78bed66e9aa129fc76ccbf6a0b77 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/angel/streaming/angel_adapter.py` | text | 39738 | 840453df689c694f5fca602e454d6042e102c9bbaaa3381e14ba854459e9e7f2 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/angel/streaming/angel_mapping.py` | text | 3184 | 3cd5f9a88fa0accb3355a76c76695e922d42d0d53af568db09ab9883fea022de | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/angel/streaming/angel_order_adapter.py` | text | 5482 | 73ce98218e2a79b98d14cc26f40bcb7d627406c8fbb41241e94c4ca1b58bbd3d | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/angel/streaming/smartWebSocketV2.py` | text | 30163 | 53baba13ea9ed4ced4ac5af8a2cd5275134bd8d605fca06eac4332cec20a69b5 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/arrow/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/arrow/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/arrow/api/auth_api.py` | text | 3405 | dfefd0edf5d905e548b890f084ac68d0cf7eba46ac579dc6730106cea31af43a | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/arrow/api/baseurl.py` | text | 2308 | c875e80b71f78342c23790b65b48ca8440a4b50d09b97d25828c90eb46b22a36 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/arrow/api/data.py` | text | 21785 | 43dccca44cafae759212cf2918f1f770244c6f429cf8bfbda800a67182cb890c | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/arrow/api/funds.py` | text | 2599 | 67d38eb4520e4283564878ea33ec5312e49c6038be3b4d31f2a632d8e1579514 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/arrow/api/margin_api.py` | text | 7795 | f6ebda4ea7962e68729692abf7e11360178f24553e6e8e9e05d79773ec4f52c0 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/arrow/api/order_api.py` | text | 14234 | 73e34070b5e987d8fc03c7040a7321625dda721298ae0901884ae91333383fed | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/arrow/database/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/arrow/database/master_contract_db.py` | text | 14351 | 01ed3f502afdf8d1aa4f97df161602c3dc8f5f31b06740e1c5ef3ec863939750 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/arrow/mapping/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/arrow/mapping/exchange.py` | text | 9927 | fee1c88a5b9f13fa1022e509f9afe44068461b9927e14fd26cedc60135378f0d | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/arrow/mapping/margin_data.py` | text | 4210 | 7d189e7d6066eb1c7b386d05066a3d924390ed3e4a8731db458d602a9dd2373b | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/arrow/mapping/order_data.py` | text | 9706 | 8a1ca481fba709a4ab2d69d5b34bef7810d4ef6f4d4e1cb3dc2ac308e1ca5567 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/arrow/mapping/transform_data.py` | text | 4302 | 0ec8a312ffefd9cf0192917c73a5bcf92d5cac45be8911212751de05eb09d7dc | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/arrow/plugin.json` | text | 384 | ee6d8118563bff43c2560f7021f0c8f66e450b7d4f79f7d304c491396f8e1725 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/arrow/streaming/__init__.py` | text | 111 | 82a28fa538910a2c91189201665a66c6a2a1c87bccafce08b1acfafd769a9b69 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/arrow/streaming/arrow_adapter.py` | text | 10021 | a9d2d0e614cae9a8f2a3ec59be6130baf4492bd07952037a55ab8a552d40acaf | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/arrow/streaming/arrow_mapping.py` | text | 3202 | a863a98c6a0de8ab099c51da5e0a8ef328c9df1cdee137f5e18627602cb259ab | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/arrow/streaming/arrow_order_adapter.py` | text | 5451 | 915807110a8442afa1d7ed3a3eea9d07f93e340c4b22507a65a66cd590297b4d | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/arrow/streaming/arrow_websocket.py` | text | 26830 | 4e63a6d75e33c6520b7301b7379ce68c1bb08a1f393e18bf7f36d67d367669a5 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/compositedge/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/compositedge/api/auth_api.py` | text | 4499 | 3beb17983b37f37099ed12dc02faccbfb1dd6c314813bf51327ac33f07090fb3 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/compositedge/api/data.py` | text | 39880 | d8c13403b08da245ea75a7e73a491d6fbe216e12854e8d098f1cc7e5227d04b0 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/compositedge/api/funds.py` | text | 2211 | ca0a065c8c15238664812d5d2cc6462894699f4c46b30f21e30de2c76e556e20 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/compositedge/api/margin_api.py` | text | 647 | b8635a0b8ba09134a1d171a07117b517a0d0cdca7238f2ce9172cd914b90ac7f | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/compositedge/api/order_api.py` | text | 15777 | f14a9a75a59efaec89a5e5457eaffbb4cab2a2c400e511793aab78439c54ee37 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/compositedge/baseurl.py` | text | 277 | 22d14b774a3c2e9ac2e4006b05efb26cc5e0f62b87029ca13b962a047c5498ef | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/compositedge/database/master_contract_db.py` | text | 22911 | 6dc8b5fcac0344eb735b9b3dc93de16905d1462d5c0deba5f410bb9b77b789c6 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/compositedge/mapping/margin_data.py` | text | 1111 | b25e2802ba8f95e5ed3af73311f856bb2039e1697c3186786e8080a6589c3690 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/compositedge/mapping/order_data.py` | text | 16249 | 66f97d4e144f5af4430af7740e9175e02e33a840c44247466336eef38db3efec | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/compositedge/mapping/transform_data.py` | text | 3233 | d632da622fb66c51fd49b8af1f06f365928863e181110a1ed3eb4f21183c075d | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/compositedge/plugin.json` | text | 387 | d019189bb8879299aec451a7073555833baf827224711865582e4d5cd424724d | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/compositedge/streaming/__init__.py` | text | 33 | f2fba127d071bcfb497b0c586812a21447157208a6c1097ba6cb70d2a3cf6f22 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/compositedge/streaming/compositedge_adapter.py` | text | 37175 | 2e0501eb7a73ada07fb3f66d821cbc37de408bb89ef5c924e406e5eecb4bd165 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/compositedge/streaming/compositedge_mapping.py` | text | 6540 | 893158e29be0e10e016dfff413cb118eb4e65181c4c70bca091609b9748cfe9a | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/compositedge/streaming/compositedge_websocket.py` | text | 21935 | 3a3b0719fd231af0651a24a754da12c69a48dbf3dfb64602a7e39b50263cb05e | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/definedge/__init__.py` | text | 56 | 27bbef9a84e3430d9af7c2a3590ab4e7286c13f1b2c63b1c9273a7aa893957b4 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/definedge/api/__init__.py` | text | 36 | 91a1b8595ebc4f5ca7bd02861d16492c49e4157031903fc0249de87b19852419 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/definedge/api/auth_api.py` | text | 4183 | 57f4b3dad3996d0af4c6b0881ffb458af9917ba14a308143bad9931d82cee8d8 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/definedge/api/baseurl.py` | text | 852 | 7f32f1b44c33b3584c60d6d7f255c9ebb2cec9df57a02eae8dc1b445d5cd8486 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/definedge/api/data.py` | text | 56296 | 9b6ec29780fba0ac56c896d19fb2198a2ba0f66fb6ee30e6c27f6038e7f75ec8 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/definedge/api/funds.py` | text | 7223 | 33ebd4481fde0d9db1e49a9fcfb99d7b6cfc2ca455104a880a8924f1ee4cd6d8 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/definedge/api/margin_api.py` | text | 3374 | 9dbf40f4058598e7c75069881918aeb4ce76c28066f0ab4752399ccc1df2d0f6 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/definedge/api/order_api.py` | text | 35817 | 3d78a4c596842810035994f0cc869f6b1abb0e9f84b3da29ea27e849a80926fa | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/definedge/api/rate_limiter.py` | text | 5694 | 8b993994263503a845fe6a285df201f780cbc977edebf1b7e12ec6c561f95371 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/definedge/database/__init__.py` | text | 41 | f6e0f996705fa7aaf88eaf9b5b50f64a9d928dd9fe78bd5fbdc5da410477818b | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/definedge/database/master_contract_db.py` | text | 33884 | 9899c9c4cf708d783a08ab1b822c3230e627063423fc38b01ce6593a6b1bd4f9 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/definedge/mapping/__init__.py` | text | 40 | 2b623171906d76fe3d836de6762a4eb789e926340a29c8fa562f9037054094db | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/definedge/mapping/margin_data.py` | text | 5501 | 7dfe90654caf70935485b1b59d8d49e15c0f148f4e1c48c9840e496c9958c589 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/definedge/mapping/order_data.py` | text | 21666 | 0e9c1673565a03666f5431a66361f33b221a2aa7b062be80bf87bf79757e550f | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/definedge/mapping/symbol_map.py` | text | 1116 | 59627ee69bcd81f46ec249cd0174ac16ba35c1af3ca1b2514a4ae9b167cbbbbd | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/definedge/mapping/transform_data.py` | text | 13019 | 097b14473a4052b7945af1ddbeead08468ad1b3a9b5e308705e85c052f3a92d1 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/definedge/plugin.json` | text | 409 | 104f68bf53800448ceb6ed75425734d7a5b652a2de1d4a50f773f4f8a3f4d6c6 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/definedge/streaming/__init__.py` | text | 42 | 22407fe987cd35d8313d406cdb83a606e0cb18a7b101e74392d529b128ff759b | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/definedge/streaming/definedge_adapter.py` | text | 51632 | b78d4734394ffde9395697b347c5b3a495e563f7226f3540919a1dd38c764061 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/definedge/streaming/definedge_mapping.py` | text | 2835 | 8d1b8d4d3db82f0203f1e8105155d456a6b1ee7ab0f5596dfbc132f6c8e51457 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/definedge/streaming/definedge_order_adapter.py` | text | 6261 | 90e89d3b8118cd2c3c82b8f4dd1dc56e6a692c0379e573566e4708dd3fcfeb84 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/definedge/streaming/definedge_websocket.py` | text | 26935 | 63e831fc896666e14e4699fa0761f616a728e9421330111446c0d99eaeb4e6c3 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/deltaexchange/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/deltaexchange/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/deltaexchange/api/auth_api.py` | text | 3589 | 76d7ff1ecee9d240164b03df96d6ee4dc8f623c899d9ee4d8ef157f05cc504c2 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/deltaexchange/api/baseurl.py` | text | 2677 | 134b54a3cec2286675ea8180f24791b7499b2a55b7945e977f7f00557c9c1202 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/deltaexchange/api/data.py` | text | 33340 | 276188b403e626e53d2afd6d0d7e46bbeb9d4a6cd47f79ed816e2a040af76731 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/deltaexchange/api/funds.py` | text | 6973 | 8679d6ac05872acfe433fe194d10f4461f59aeb5f25ce242149ee340f9ec11c9 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/deltaexchange/api/margin_api.py` | text | 7681 | bf72df484e8e2206b0d46eb968c0dd6511c252cdd27d660dd8529fa043551246 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/deltaexchange/api/order_api.py` | text | 30409 | 426a5ada1bcc5ce94919abc06dbb37afbf4e13fd853e415aca143d620f073473 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/deltaexchange/api/rate_limiter.py` | text | 12615 | e9a162cb3cb0a0863c6f1767ab5a529e50176af1b51a6196856d4d9a7fe77152 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/deltaexchange/database/master_contract_db.py` | text | 26117 | ba9c513acf1d5f0960d430d3a84aa4965defe1131bdfa0dd4b78a2c70954cb02 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/deltaexchange/mapping/margin_data.py` | text | 5737 | 138791992d2ff4e4cd5de18eaee9ce5547ad7efc5f0e6eaf1a4d11652ea9a6de | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/deltaexchange/mapping/order_data.py` | text | 28365 | 73140049f122b7942425cb1e4be9462ede3112d79c7cef43fb77afb7df529eaa | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/deltaexchange/mapping/transform_data.py` | text | 8441 | 98290694fe7b25685a2fe4b1e1f87920aa7073815b1d5c6c5f630582ea3fac87 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/deltaexchange/plugin.json` | text | 413 | db5add6c3bf3905d196d4160f4f9517cb619e8e724702765f6aec0e30ea7a64d | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/deltaexchange/streaming/__init__.py` | text | 387 | a5bce5190f53d40704c7dff443e3d238fe1389a6a39c06155d9b743f086f77ea | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/deltaexchange/streaming/delta_adapter.py` | text | 31110 | 4bb210dc8e33f3c366b9a0fe010fd6b7f3320af6a0ad1a42dfc31b0fccf97966 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/deltaexchange/streaming/delta_mapping.py` | text | 3155 | 7decb9564d13b4488358e2bfdd7435419d7e5c7b1d19ed27c66f865a181e466f | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/deltaexchange/streaming/delta_websocket.py` | text | 20080 | 248b9b0b778f1adf647b13b9be229bdf26f10054e5929c64513c89925f5e453c | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/deltaexchange/streaming/deltaexchange_adapter.py` | text | 560 | b95423cc5eb8bedd295d547f4b46221381242bf35750de7be38e6b0c3ce819ce | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan/api/auth_api.py` | text | 7584 | a7d844b63dd6d0d52a0928c896380ac07214f48e515e0487a896d6a4a78522c0 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan/api/baseurl.py` | text | 502 | 0659ef2127baf17661532316881a3afd45c17209d29e398219e228e51cc77ee7 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan/api/data.py` | text | 57920 | f80db9cf524862ea1a92ebc58d6d648144e4b17280ef8c3a1414546e985673aa | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan/api/funds.py` | text | 6268 | 2092b7eb83fca56192f9259361c9daa625f3120a9994d8c3a82a9e2c32ed7bd1 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan/api/gtt_api.py` | text | 11772 | dc8a40a7d22d567585ffd2ec491a1cec6f3c02c5a7500987b8207454c3c46d5e | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan/api/margin_api.py` | text | 10090 | 29314018dac03c52f20eb1d35f12a92300127c17bfaccdc79bdacc0e618bc5da | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan/api/order_api.py` | text | 19069 | 3da8ddd309a30be1f3a3314b8bdb79c0564ea10ec9e4f35d3eda050b467727ac | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan/database/master_contract_db.py` | text | 24967 | 6d0d5b02a9392004ac348f4f2a723a69f73a6e80f38e05da3a06df9259140d87 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan/mapping/gtt_data.py` | text | 8373 | ca7601310a147cb4cf91dbf874756c3e832df20f0dedfdde5624ef92156d9fa4 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan/mapping/margin_data.py` | text | 3821 | 26c99fe598518c1d3733a273815b3695a8d40fdcfc21f101bcb3702d96cf6faa | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan/mapping/order_data.py` | text | 15833 | b8840bb860730a671e528cd1946f21e9332df3780e01257cf32eeb46f8e10bfe | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan/mapping/transform_data.py` | text | 11855 | 95e2e5b91ca0dca9a57bfd8ee9104131ba509405087e30cc33a526996f17990d | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan/plugin.json` | text | 382 | 1db84d89243543295a2461cb4f76cbef7c2b8ee1eec56fe6ba8db777c50f1b93 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan/streaming/__init__.py` | text | 309 | 540263cfc526e99d6fdad50778e3d55b605941f10d4176d420e7b519765420fd | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan/streaming/dhan_adapter.py` | text | 49552 | 0061939edb397f0c953635af0942b5cc57fbc0563ca53431d90cfd33dccae73a | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan/streaming/dhan_mapping.py` | text | 6169 | c0f4fb6fb9fc7e18e03439007e5aabf98873ca14c6a7d7230bef132133de40da | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan/streaming/dhan_order_adapter.py` | text | 7256 | cb2a7e2506f802810886d2d698707b12a43018c6af2d3b960db11f4bc0f6d75b | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan/streaming/dhan_websocket.py` | text | 40169 | f12baffc94e1b0a681276ba703d44c7bfc7d537969fb5a68ef1de15648ecfce1 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan_sandbox/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan_sandbox/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan_sandbox/api/auth_api.py` | text | 16501 | abd955813fa65446079aa88f11401026931fa305e8ef81e5588e566261901e75 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan_sandbox/api/baseurl.py` | text | 554 | 1be16c694bbaf00fe079ce686e57cd3f21e6c2485d9abcb48f3f3682395fce61 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan_sandbox/api/data.py` | text | 47861 | 994896cc53920271d53ef0cbe07b5a6a635a22bb944278e53a9064071f382415 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan_sandbox/api/funds.py` | text | 6030 | 19aeddfcee18d31a20c16691e7a9e396d33f88541b9779f494f9283073365d31 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan_sandbox/api/margin_api.py` | text | 9638 | 872a5c11f7285e2c572d4e1803f546d1b1b8f86479fb9890b230003cb84bcd3c | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan_sandbox/api/order_api.py` | text | 20920 | 0847a49b6acd62098f35bb48bed1738eae3436322e844761c2de226531b43e66 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan_sandbox/database/master_contract_db.py` | text | 21170 | f94ab43b047b7d65141fbf65b5711f12b2f6e7d70fbb85f60083f6151cf876f4 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan_sandbox/mapping/margin_data.py` | text | 9295 | 9e7fab1a1657d99a97411781ff56f504649f3dc2ac4ca9029431a4f2876d1228 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan_sandbox/mapping/order_data.py` | text | 12285 | 593bf74ec5740526b1c99fdc5507e15c29d2810041622b3639cc9ad74aebc0c0 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan_sandbox/mapping/transform_data.py` | text | 6391 | a161bc56c0aeb813c0376c81c3fcd18bc34ca6ab3212aeedb983ab1518806ac8 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan_sandbox/plugin.json` | text | 396 | 956a5cf1985416f87adeacd7d43410cd15a248331d5e4699f09f8bcfbe30efd1 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan_sandbox/streaming/__init__.py` | text | 246 | 4f5134c4a69f3daf09947cbaec26f5fa47db2eb47e7ca386a252626770756ccd | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan_sandbox/streaming/dhan_adapter.py` | text | 53968 | 6a406bd424b299b42d988b86bbd3d83aa9f187314de16c176b8bf3b1bfdc3f1c | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan_sandbox/streaming/dhan_mapping.py` | text | 1390 | 2557baa6bdefbd14f00fa98f4b93be79a19edc275f245edd3fd2936fb7089f20 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan_sandbox/streaming/dhan_sandbox_adapter.py` | text | 12848 | a84a5fcfb40dfcc2b0d1d17636fdd823d205df24b69e9f3ad7384ef6bb5b7d92 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/dhan_sandbox/streaming/dhan_websocket.py` | text | 131300 | 7294a87828bbc727de57f0352591135e93332cc02a0e49fcd4b36ddcff91fc9e | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/firstock/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/firstock/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/firstock/api/auth_api.py` | text | 5417 | 5c898a59ccb355ec5a19b5da948510773ab186d2bcd513823e15c3949f512754 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/firstock/api/data.py` | text | 48281 | 70ba76c7994a696db657f4182236895c0dd4ffe0484c24e693f39baef772e0d0 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/firstock/api/funds.py` | text | 3538 | c835cc5e2419a3a70479c678929f706477ab0c80f9a9defa4b3c5efb49b5f9db | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/firstock/api/margin_api.py` | text | 3056 | cdaf69e848447b68db8b4d8beac66549f59de6b9a4fb3c23cd12cfcffd431469 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/firstock/api/order_api.py` | text | 24443 | a001b842e3b7c77fb3090152a253f0dfe90ab77f0b9ffbd1a08de781def59fbd | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/firstock/database/master_contract_db.py` | text | 31574 | d2e22483781ffade8e0bee91b3da486ed727f95b4fb6f4d229de4792e3fc50f0 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/firstock/mapping/margin_data.py` | text | 8178 | c6a240b40cb377a9d7385946a91ad03fbdce954f6081727a4fb743f5ed948a7e | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/firstock/mapping/order_data.py` | text | 24812 | 8d383e3e155c7ee2308741c26f192f0f328b9fe22c5dca9ebd67d49a38721204 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/firstock/mapping/transform_data.py` | text | 16110 | 3f85967868ca13bbb1f31f0a8afffe75b1ae87b95cef1ee242bda8a14eef2903 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/firstock/plugin.json` | text | 354 | 9c89795af55ec9038b38d2a2766e0bd09a1249cc657fbdfd936f62457d1b6b4a | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/firstock/streaming/__init__.py` | text | 250 | ae07cad896dfdadfb4f24f21d28b201bcaaab19b647e6c10911359c94864a129 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/firstock/streaming/firstock_adapter.py` | text | 39127 | 631eda9aaf10971a61c776f685624ce964de35e7f688de0407a4d0ff06fb861d | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/firstock/streaming/firstock_mapping.py` | text | 1349 | 0431c89bacb21faf4e9dad541b182f6fa562a9f546acfbb19509e40354f73d56 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/firstock/streaming/firstock_websocket.py` | text | 31016 | fd1ec74d2d63e648bdaead919a62a8a3ac057ad042076a7080367395a1f1df4a | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fivepaisa/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fivepaisa/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fivepaisa/api/auth_api.py` | text | 3926 | 6e8cc683a4370b99691d29b10b5f19668876848c2decdad7be4ad98ca1c90ba9 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fivepaisa/api/data.py` | text | 44518 | e7df3d33b5ece7e827a49403c793f387184c415d792d6e7c76729d5625d009be | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fivepaisa/api/funds.py` | text | 4098 | 25e3a10a4e11ce58ab372d208ea0dd8445f9bfcd2f52770c4a99e4fdd7e2238c | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fivepaisa/api/margin_api.py` | text | 853 | ed92e7b48d7461a4388683df31cb2e096736f548cdd6814c39a85b0bf69f19b6 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fivepaisa/api/order_api.py` | text | 29973 | 103b677081a1da53dfb8ac4ee1862e24a335cba35672d5c239ccf9099446373e | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fivepaisa/database/master_contract_db.py` | text | 20180 | c4c0343cdbe514c79cc58d303aaa2e0af0767d694a770349fe0586a2f711b7b4 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fivepaisa/mapping/margin_data.py` | text | 1349 | 91531e1d1ce811711996ba94354b68e4eec5a0d18de6eb7d523fa5c564fcf73f | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fivepaisa/mapping/order_data.py` | text | 19266 | 713d0827e41d9119f8506116b7febb04351c12406c8189343537eeef9d5a78ec | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fivepaisa/mapping/transform_data.py` | text | 13438 | 2bc00d2fd9e766761b20ccf7edb3078a6eedc7e3625e062d719776e064663641 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fivepaisa/plugin.json` | text | 380 | f5f3d013282a049e4934746062e5bfc0e444a64014e245f82d0d8f82623700c4 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fivepaisa/streaming/__init__.py` | text | 343 | 2d99ffbf32428a84e26a6909b619d0ae9198f96850ce64110f4f6ed1d17eadce | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fivepaisa/streaming/fivepaisa_adapter.py` | text | 42166 | b72c53e012902eb865b61c21a74e95b14f689ed1f6cde44a50a63396ed9011f9 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fivepaisa/streaming/fivepaisa_mapping.py` | text | 5016 | 5ee94c568d168b1feeb47dac108286dc95a5b868b53d4928bd78ae6cc5fe8440 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fivepaisa/streaming/fivepaisa_order_adapter.py` | text | 16057 | 30c1b705d862276f94a1a1b3125a62ca8cd03b49757658238defa4c0670861a9 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fivepaisa/streaming/fivepaisa_websocket.py` | text | 11424 | db749961125e3e5d1191b7e9b5db5652adbaa3fa21367ce725f9cb7e52b1cbc1 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fivepaisaxts/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fivepaisaxts/api/auth_api.py` | text | 3795 | 3e7063a9f11d4a8fa4a269d6e9b587de4ba708d02f82b6b2a77450783d39c427 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fivepaisaxts/api/data.py` | text | 39879 | b5d178304a999d53658a08835a1c63341320b2110b64ab0c8cb9456a68f17673 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fivepaisaxts/api/funds.py` | text | 2209 | 320a73d0a79d3aaf9d4ea02d709020019ad6dbf254a4b6746cd694b80954c0d6 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fivepaisaxts/api/margin_api.py` | text | 647 | af6a7d33a953902e7e841e2cd5aca0e3e8e0db6cdff194c4ac1b52e4618fd0f5 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fivepaisaxts/api/order_api.py` | text | 15744 | 4589354b395ac71da85e60dd62628f39cce45e54275b23de97df703d43587436 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fivepaisaxts/baseurl.py` | text | 275 | 9737372a00c1eb39945a8cdf53eeb9da6ba9474dfb8565c11dbc41b289c3d8db | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fivepaisaxts/database/master_contract_db.py` | text | 23571 | 4ec1cbf64991b4569591831ac4374920c250f314a4d54380aa26161dd7bf3946 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fivepaisaxts/mapping/margin_data.py` | text | 1111 | 667bffb4f142ee945f3c9ca1f153f5a35623e2351cb3bc8997f0d162eddc02f0 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fivepaisaxts/mapping/order_data.py` | text | 16185 | 91ce39d0c93356d60af0959f1beddb1c867e17c3d18b1c608dabdbb08a097916 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fivepaisaxts/mapping/transform_data.py` | text | 3233 | 9fd148b3b4da70028c3ca2abcbc1cf9862ebd549276d50cedc1f5667a06eb118 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fivepaisaxts/plugin.json` | text | 363 | 1674740a5f977288d272cf622f0f331c150a9552bf83bcd8dd928a41c8a054e2 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fivepaisaxts/streaming/__init__.py` | text | 33 | 0a39279a68e382b48bf4f06cf9cba24bde4ca2a18c1ee1a8e96d48c806460969 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fivepaisaxts/streaming/fivepaisaxts_adapter.py` | text | 48429 | 562653f2b0bc9716bb983f3eb018e827286167336d5a60def25f918fcbe35ccc | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fivepaisaxts/streaming/fivepaisaxts_mapping.py` | text | 6501 | f757853b30775fbd355f8792a7c34d33ceb3b8330216067b729ee6755d7b98ea | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fivepaisaxts/streaming/fivepaisaxts_websocket.py` | text | 28323 | be0dd339bab1e96c93dcbde28472c698a1de0b23981df6fd34ddb9315727c319 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/flattrade/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/flattrade/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/flattrade/api/auth_api.py` | text | 4012 | 9197e0a1bafa8de119ac7d7895c8f0393598538de8307bdb1c4097e74115fc8e | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/flattrade/api/data.py` | text | 41532 | d195fe1e5fbf9f8c9195d5bc1519833994e9f3bbe3b76135ac5dc808cdd5204d | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/flattrade/api/funds.py` | text | 5056 | e6bffa04a0ebff4b756f48b2f92fd23c6eefb02bb8abb4c2a964b03778ff913c | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/flattrade/api/margin_api.py` | text | 6229 | 6ae594da1199a22db6f1fbdc0a834b5354e84307dacd8e2a469de6a9dab10298 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/flattrade/api/order_api.py` | text | 19706 | 77edc38215cd40123a4bb933d0c35a6349309b740d8cbc7fa3547edef38e23b0 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/flattrade/api/rate_limit.py` | text | 14942 | 2ec1cb7a3e9b3410218afedaa38c694bd0995b95c99369f6f395e30a05080b1f | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/flattrade/database/master_contract_db.py` | text | 36848 | 362170ecf9e2676a0bca9c571b80b5642863a450b0588883dc05ede9760ce36d | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/flattrade/mapping/margin_data.py` | text | 10829 | e6e312b5684fe37c90854eb421e7bda9f598e81f25b853ddfea01c8a15ff867f | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/flattrade/mapping/order_data.py` | text | 24918 | 94b61d221c24a75465ee743dc3ab37b545ad348a3cc43831bc1445f58ceea985 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/flattrade/mapping/transform_data.py` | text | 11205 | 80aa5b8ec9761e4e9316fb46b3318f2c06d4d45333282975ff5981a773960216 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/flattrade/plugin.json` | text | 383 | e11a0a40218656db6e2bfa7b606c0fc4c255074c870d90291ff907ff397e2619 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/flattrade/streaming/__init__.py` | text | 393 | 63a32e8c3af80d676476c72b459781dbf62db274bd3f861825658b4a46fcb95a | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/flattrade/streaming/docs/reconnection_fix.md` | text | 3200 | 8341d70db2cba10a0af8d96e96627327c0e773f6da29302b3f404578ee27e50a | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/flattrade/streaming/flattrade_adapter.py` | text | 61757 | 2263f2602304569ac4af9a0059b4544e9fe6d48b6b491332dff4fa74e34f2378 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/flattrade/streaming/flattrade_mapping.py` | text | 2499 | 553ee822fba0714d49bfa5d6cd797ea1d0f77a4b9ec105006b0a10c0397bdf5b | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/flattrade/streaming/flattrade_order_adapter.py` | text | 14840 | aac33d9d41ce20d976a5e894e720369911088ec90c36474f7cbdde170b6cdcad | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/flattrade/streaming/flattrade_websocket.py` | text | 34036 | c61660a9706348b1db9ba5b494f72f3e2d23fad93723a3e2ed6dec9eab51f4cb | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fyers/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fyers/api/auth_api.py` | text | 4242 | 8bee1c9f81051b438d3ee63ff214f553393072a7ebb112ac499dfe62cdbe5ccb | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fyers/api/data.py` | text | 32415 | a944679d4f68765f8e56e405712a798381eb7a5efdef6686565e12f0a76bb324 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fyers/api/funds.py` | text | 9617 | a87773a9afe5a727c4b0c33a42d6648e2478baf13b831fd7909fd2b846c68c3a | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fyers/api/gtt_api.py` | text | 15718 | 9adcf72dbb722621bd2d19baea3d442b15437639d7ae45853cf278e308e558da | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fyers/api/margin_api.py` | text | 3777 | ff88bf56e568693d215ade3d3e030a381c9cb2402f39f6be8db777aa616995c5 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fyers/api/order_api.py` | text | 21806 | d091830b9bf255344f485345959869cfdf0c9f39118c8e13126f1b7a451e9acb | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fyers/api/rate_limiter.py` | text | 4391 | 097be1bfdc5cf2a569395b89fb5dbf4eae13272a379ae390ad79c11e93a2c03d | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fyers/database/master_contract_db.py` | text | 30816 | 9c7fdfec37930602da0f781b4bd9a3d7d812464e975654e09f2fab626d08b2d1 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fyers/mapping/gtt_data.py` | text | 10016 | 39999d069cd1220551fbd0469a4e26cb2ca111b5a1419d92133ea8f7d8d2d512 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fyers/mapping/margin_data.py` | text | 7362 | fe09b8fb13c32343def9e57accc25bccda8289a50f8aa9a2413d810609af209a | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fyers/mapping/order_data.py` | text | 14487 | 59776df98639f54de9b1470add673df67cac82d078413677dcd817cfeda47a3d | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fyers/mapping/transform_data.py` | text | 4288 | fb0cf65be5502e0a5fcacd19fc891cbf3fffcebb9eaab98d82c4e7d6d4994a81 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fyers/plugin.json` | text | 377 | ec4d96ff730819090f8f66a64647344d316b461533a8190645ee222ff55ceef8 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fyers/streaming/__init__.py` | text | 40 | 0e24f0629c56905a3a06842d6667a87018664721b4403701480626ec01d397b3 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fyers/streaming/fyers_adapter.py` | text | 29134 | ef589a63b4f1eada7ba0277583b1584b3b1f92debc54b0aea2759ed6fb689fd4 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fyers/streaming/fyers_hsm_websocket.py` | text | 48478 | 212017a454fd475ba4f6febb96f8045a828ef06ad7a19a6bc451227e07b87ed1 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fyers/streaming/fyers_mapping.py` | text | 18654 | 92ff43efe2679bd8bd0bfc178cd411ccc8c48996eb091bd36e811ff06fa7389c | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fyers/streaming/fyers_order_adapter.py` | text | 9304 | eb1324ec822c00e521f004f17475626739f8926c4715c64588137053b71cb140 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fyers/streaming/fyers_tbt_websocket.py` | text | 32274 | 95afe6f1242ba41445ac36b314df0743ae504d248baa4e26ca889437515afb77 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fyers/streaming/fyers_token_converter.py` | text | 20252 | 925b8f0f492758e3b5bec8b02764704a750424562134b3d43eec03fe89a7fe1a | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fyers/streaming/fyers_websocket_adapter.py` | text | 57518 | 1dcff388e0e26bf7d1ff8ed0533bc237c89b48c611826153b42a43cfed3d2f0b | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/fyers/streaming/msg_pb2.py` | text | 6394 | 8a4f56a5c044074e7ac234e52eb3ccf101a5639376e1695cd9e930704baac870 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/groww/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/groww/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/groww/api/auth_api.py` | text | 6501 | 45795c45fe51b358f55e50c498231766d2a345b5ec6724a68a71d510a5ca2924 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/groww/api/data.py` | text | 87205 | 32bbb30dcab5eb867f259ef75b79ef3f4885b23de8c4225d445b4de08b4a1582 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/groww/api/funds.py` | text | 4866 | c4f054c2a17c0e02de1c1ba2da8ff7314fdd83acb33ddaa6d00b1b713fc1a8b1 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/groww/api/margin_api.py` | text | 3475 | 785d2e570e5f3a333e10d71b238073d16127b6ab587485c9e7751bf59e400ec9 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/groww/api/order_api.py` | text | 82103 | 33ed56dea07e743b42ed4773319b085fd562867a818bd5e62ea0d66e419cb53c | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/groww/api/rate_limiter.py` | text | 5030 | a1719281614cc3b2751e2a24d2cd4d50e8e3a84434a2d52b9a8d6e688ef76b37 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/groww/database/master_contract_db.py` | text | 39127 | 15c3ae4d3485ae681012bdefa5b868e43b15739f2e87714758c1045496ef0b9a | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/groww/mapping/margin_data.py` | text | 3693 | 0e38e0ee8ce997a95d00eb9b9ce258bff4cda818a8728be04ba2d3581167eec3 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/groww/mapping/order_data.py` | text | 14761 | dc9e3604f841a35866d16d646cb12b265c8c4086ceed9f4ee7162cb12b0b3400 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/groww/mapping/transform_data.py` | text | 9255 | a1a9988c0d8f82b81aad7ac08327b508c10737accf24510cd1e5275eb4cb2831 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/groww/plugin.json` | text | 361 | d466813d9fbd0574ff9bf43c1ab3a3c8fb1ecc2d55ff2ab9f10cfc33f717d004 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/groww/streaming/__init__.py` | text | 271 | b6dc0a4c55cb1ee2ec19cb92d34a5cc00cbd1ce16ab734ff5e8540cdcd088cb8 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/groww/streaming/groww_adapter.py` | text | 56895 | 31af841b42564e035300a954875c09815e18208809c053303895a2730870211b | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/groww/streaming/groww_mapping.py` | text | 5233 | 366d43453f049cb9fa21d465981b9c561f7d8a64ddecfb934bc3cdfb780acc9e | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/groww/streaming/groww_nats.py` | text | 15739 | a2cadf4dbe0dd74257871726535161231cf9c24dba7c804441d8fbdc0b32d8d1 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/groww/streaming/groww_nkeys.py` | text | 10184 | 9e99ea1e4aff06bebddfd7d027e46ea10c41279a8b89e58d92b243bc2273876d | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/groww/streaming/groww_order_adapter.py` | text | 17266 | 9d370359d530ed3fcc5037d53f471cad7ba6fb12e699c2ee2c24f06c3ee1efa4 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/groww/streaming/groww_protobuf.py` | text | 10879 | dbdeb3d7d6a7e11cdd99a9babf7c4abf3e5c89f9871b2a505b6510a3a8682ff2 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/groww/streaming/nats_websocket.py` | text | 49081 | 051425a82943fcd2f229c97a51bbfb7366d6079e25538ca80e20d3497ede93a7 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsecurities/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsecurities/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsecurities/api/auth_api.py` | text | 3127 | e2d82494926a72b6014ec3b84f66b7cf8aa87c497e3c964ba98b367185faa9db | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsecurities/api/baseurl.py` | text | 3022 | 5fc1131c1f3ff9442a0041c3f421d390caae6836c75dfc74053d9eec097a954e | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsecurities/api/data.py` | text | 21794 | 7419f36bb40a670ee2e405d2ae11fdd5ccbdc73d3ce4ab1202c0dcdf2862f9b1 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsecurities/api/funds.py` | text | 6014 | e585a1f02f8c16320b7f4fe5adf6668e5c0f4c9cc29acd55a6b2160281eb971f | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsecurities/api/order_api.py` | text | 20383 | cf4bfae8ff34000362522bc3a6305e47e80831dc9d2b26f1fabe393f1a04d2c1 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsecurities/database/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsecurities/database/master_contract_db.py` | text | 19005 | 837edbc0f34f06e1da3e93c875aa3d6edfa8d073596e37db34d81ef8794c0966 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsecurities/mapping/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsecurities/mapping/order_data.py` | text | 19250 | d675abefd23171c8b4c10cc5e442649de16837dff398444947798c61c0c4afe5 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsecurities/mapping/transform_data.py` | text | 16067 | e06f1575c09767b0f560bcb65f7a8fa5f1aa19c4fea452b50530b51e2833169a | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsecurities/plugin.json` | text | 283 | f9674a456d1081caacdf3179f7794711c23a965f44394fb437be1a90d3cc00be | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsecurities/streaming/__init__.py` | text | 158 | 78b2f75587bd90d482bdd6d78c610b78eae52495cde8f2f7b7243ba045f87f1c | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsecurities/streaming/hdfcsecurities_adapter.py` | text | 17931 | 51644c497e7c4b11c38359039a2e96079aec319876d9a70a483e6c7ba1deb60d | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsecurities/streaming/hdfcsecurities_mapping.py` | text | 2540 | 7389f84b9f3a4be17a90565f495fc01b39cff5759590b578663ac915b947c253 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsecurities/streaming/hdfcsecurities_market.proto` | text | 23201 | 8968562379b21ad5c696058fe40134b3d98bb437e585d1f93c19c3dd93fd6e27 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsecurities/streaming/hdfcsecurities_market_pb2.py` | text | 38361 | 235cf7ae291bdc14ec4fa919198d3d9662b80d78cea8a26760b08f7747f27456 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsecurities/streaming/hdfcsecurities_websocket.py` | text | 31875 | a097b7690b7f6ac81fd3b6236fcb53191a22a671cb41e9a6dbaf4072279d10ec | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsky/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsky/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsky/api/auth_api.py` | text | 3061 | ce2949acabaaf878aa48aaf4006cd3c06f13c8526fc35cb776bf594a41936787 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsky/api/baseurl.py` | text | 4703 | 287de128f2ad39d8c28b461a90f8760c2670d792a44441f5770ad8cdbea3777b | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsky/api/data.py` | text | 38281 | cd1c924ddfb2b9b1a7d9bb71ed02a82581aaa5feab42e5dfec646f479f02559c | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsky/api/funds.py` | text | 4858 | 9be70564cfe01f70018233d2f79d728df8e9b3096246cebdd5a347271172f1a9 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsky/api/margin_api.py` | text | 7956 | 9990e2d5649f2ad73e6fae108d8e8718c6ab7a28749df7325d23dd70dfe2f9d8 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsky/api/order_api.py` | text | 16129 | 46d407cdc66f23284ddf45fdae215e1cc041aeefb8d8ce27c2894e5f174360f3 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsky/database/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsky/database/master_contract_db.py` | text | 20736 | e894600e937bb8b160f4e62fa287da517b1d9a8c85cfdff294030244aa10c47d | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsky/mapping/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsky/mapping/margin_data.py` | text | 4551 | 277f150f44ddf305aa9d6cdd1873e9fc0f7ef785f171102b9507ecf791da9226 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsky/mapping/order_data.py` | text | 12720 | 98f7b764f9caf0d124d3cf5aefa08e8750ca594fb2b7ce7ec89b4db403982e78 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsky/mapping/transform_data.py` | text | 12797 | 3e0aa65a66a9ecc04eff6bac6cfcda1c8f47e506c7e8f94eb2a30894c13d8bdc | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsky/plugin.json` | text | 382 | 31edb4f5e361c45085394fc808083a75c946775787df09c7662412d0399f63c7 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsky/streaming/__init__.py` | text | 119 | d9a2681a89f5f997eef393a5904884188a8ba9edd02117fb9a51489caeb019c6 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsky/streaming/hdfcsky_adapter.py` | text | 20984 | 42b89e7d3bf1d2276091929a4bf0b321f201e6e7d8d41009f7c0b7a13fe9c757 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsky/streaming/hdfcsky_mapping.py` | text | 2483 | 90abd0325784f145f60c0b931edb00193a02cdbdd858cf0be750f78e80e59139 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsky/streaming/hdfcsky_market.proto` | text | 22612 | 540d06c28c7ae93fd8f79d866a0a353a703e51cd1007f2d9f04c07836bec3866 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsky/streaming/hdfcsky_market_pb2.py` | text | 38036 | e176b2d419e493432c769a25f90e579fd3b8972222b63d3fa36f06c029b028e2 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/hdfcsky/streaming/hdfcsky_websocket.py` | text | 34521 | 8b07385d247c596654f626f7fe28554c51fccc29aa3e0875a78d846912319d91 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/ibulls/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/ibulls/api/auth_api.py` | text | 3789 | c9caca848ab8755ed583c171c756e9123a7df97261ca3482ce8ec723a8a2ba8f | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/ibulls/api/data.py` | text | 40490 | e9ea0643dff456efb1aba87ae5334b9908b4491a2ddf8f03ee5c257bd8c85f72 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/ibulls/api/funds.py` | text | 2203 | ce0fa31c8ae27a14296b5267c8f8ca33a23cf34b2bf758b446ef4ea83f514cbf | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/ibulls/api/margin_api.py` | text | 617 | ae7706d09bb42cd73da71dffd3f7805cb34c9a4a9f0bf2b235e486df8e4fe698 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/ibulls/api/order_api.py` | text | 23459 | c21568fc7f96f72b6c4112de4f92d8df2aff230244a1729eb5e8ef8e030af89e | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/ibulls/baseurl.py` | text | 287 | a4b44dd51b628d832c16b34e6c4f766bf27748bf3d1e33e7c6bf66189ace33ba | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/ibulls/database/master_contract_db.py` | text | 20297 | 9badac9f28754539dede6397654b2c7d4fc25fbb83b4c3223b8e95e67942db56 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/ibulls/mapping/margin_data.py` | text | 1069 | daed01ab3c66eab720451f04d1ac770a10c2d57ba06620c6ea6b55af6fbca3c7 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/ibulls/mapping/order_data.py` | text | 16193 | 58f35304cb5dbbac216272b59d53cdceef5cf0651b303029922fe7c5ec5418a3 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/ibulls/mapping/transform_data.py` | text | 10180 | 6dc3f4cc220fb711dd3dc52d6931393ede850d01db3a884a0c7695cb989594d1 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/ibulls/plugin.json` | text | 360 | 0a5c686e780d33568bea851e69bc832d80c7b077be6b3956d66c87a63ebeb5de | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/ibulls/streaming/__init__.py` | text | 27 | a43975de528db1c7da30f179e093855038fa72620d7489c291177ac553aef372 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/ibulls/streaming/ibulls_adapter.py` | text | 36851 | f9ac486249cf5ca23f8f08d79a0a2482ba6dbc6b13ddfbaafc13fbbe780af5a8 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/ibulls/streaming/ibulls_mapping.py` | text | 6426 | 26522e17bafba31441f7861e9a8aaccdc0455c3ef66ca38a64bb906f762a9906 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/ibulls/streaming/ibulls_websocket.py` | text | 21808 | 4786919c20f2595e48b247518eef0488fc1a0d1243e798fc3e3d5b2f1ddafc76 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iifl/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iifl/api/auth_api.py` | text | 3787 | 449e2e972782612461d6f90023fa2587fd87da7d1241cc7f904d8e105ae4153d | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iifl/api/data.py` | text | 41396 | 4b4eb138ad92bb08a82ad6c91eb0813a77694a4c5406740c6a6e83f31ca3d6e4 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iifl/api/funds.py` | text | 2201 | 1b0383ffd37c9dbcae31b92f372384ecd1cb07dccd0f2f8e4d3b41108b06327a | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iifl/api/margin_api.py` | text | 607 | c0c30fecfb9cf0e58fb8dbd7ba3858d86228d84ebf1fd8d2928b1c29b9a2459d | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iifl/api/order_api.py` | text | 15619 | e2e47ba3ea1058d50dbbe29dd237ca115690ab2cc65689fcd73fc671fcfc6e21 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iifl/baseurl.py` | text | 257 | 8114bed72355738bacb2f08a01dd23c2bf00d69db0c6ed28213f9f0bd43fcea3 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iifl/database/master_contract_db.py` | text | 22901 | 0fee0d091763074c7cfe53e528035aef4f37daf37171725b62393f4195880eff | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iifl/mapping/margin_data.py` | text | 1055 | 45bfb9b88f1adaa461cc41975dd18fcf34c4b71154bd8518b638ef5e1e83ba6a | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iifl/mapping/order_data.py` | text | 16177 | d354d2fb34a493488397a7544cd5ae03d8880d9f5f7e5c8176fc363edbda972d | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iifl/mapping/transform_data.py` | text | 3225 | 7e6811ec522697b0827b61457b233508c8656a90e217ab9aea5a22443e243731 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iifl/plugin.json` | text | 372 | affd9feb532e46823eabcc3b971a08b756e802fa615cd5f9204cfbdb21258d4f | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iifl/streaming/__init__.py` | text | 25 | 0504ae22d2ae2099e6044555cba68853866c89ce65b9f50c33ca1cbcaeba470a | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iifl/streaming/iifl_adapter.py` | text | 36781 | a2f170de736a7c65cf1036611d464599a14a8b8bf7f9c15482f27713eca4ca9a | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iifl/streaming/iifl_mapping.py` | text | 6388 | 37547ef6aba2a070a0daf2bb33803d0c9153bd80aec02316d827f4731a8e9040 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iifl/streaming/iifl_websocket.py` | text | 21780 | 91131d38ad2a711500dd5dfb24ec27aa5b5a6004ab18af8b0430df192af399cb | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iiflcapital/__init__.py` | text | 35 | 9447da6f1583ecceaf7e3a63728c621c10337ddb39c5d4abf41cff2514c0a1a2 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iiflcapital/api/__init__.py` | text | 33 | b871804b398ba1b2a4486e283dd5225a6af44247eb0106fb3b52741a10748eae | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iiflcapital/api/auth_api.py` | text | 3233 | 6b211a58d5178a4842470f3b02a069c551f8d466ba642e1448fd79a3f94d6cd4 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iiflcapital/api/data.py` | text | 31063 | a51ce085618fc51d82355d296d996a0c8e5714c24b9983ce87724c5f18ada875 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iiflcapital/api/funds.py` | text | 7638 | e41ff9f91606f63eebc63abadf45d58f9fb4e9c6add10ae2c0eb41c0071172af | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iiflcapital/api/margin_api.py` | text | 2434 | 083150859a144ecc3edddb842a2adf98e5462d036a8060c46756decbc891e896 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iiflcapital/api/order_api.py` | text | 20793 | e4a293071dc381a35a860cec96be722abdadada72c3d7aa3ceccf5cee78fd6ec | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iiflcapital/api/rate_limiter.py` | text | 7536 | f012c9b00208ea4e6fa01314ab52ac7515545ec5b8170937bffc2b3cd4654810 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iiflcapital/baseurl.py` | text | 135 | 75bdeb79334c3080bbf0e2d30557518608dc61e27ec63645c7c4338c033fa9c5 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iiflcapital/database/__init__.py` | text | 38 | 5240fe9a0ceb76ff5a6cc40f3583ca4224772101133d35c6c097938a716ac63d | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iiflcapital/database/master_contract_db.py` | text | 20897 | 6926af2e46808195144e2ec064e59482d01a8ef409afd9f1ebd2f2a1e1115187 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iiflcapital/mapping/__init__.py` | text | 37 | 88edb0751d3b7b93f792bef324eb7817b8168c5079e61ffa46986f707cdbfccc | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iiflcapital/mapping/margin_data.py` | text | 4637 | 75c54cf1057740ff9ff16ab5f47f4cd583f4b3cc30ebfa72edd7370fbec28c92 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iiflcapital/mapping/order_data.py` | text | 14821 | 8b2352fde00fa4dd26c54c0630773cd3c0d78703c8d1382baa522fd00f107b3e | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iiflcapital/mapping/transform_data.py` | text | 10660 | d6385489b6f999928f0fd99c8286267a1a2cc65f5146da9204b8cd6ab1a7982f | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iiflcapital/plugin.json` | text | 399 | 487900ec869340c94f96b296309a9e22905170f5db77de3ae5dca45da5661075 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iiflcapital/streaming/__init__.py` | text | 39 | c13939953555b40baa2aa8255d7d39db4719fb2239589feea8e6298bfe084eae | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iiflcapital/streaming/iiflcapital_adapter.py` | text | 19031 | f9c7ba2c4830037896e925455a6f10bea8141141e0c0709d256304a792da2ce2 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iiflcapital/streaming/iiflcapital_mapping.py` | text | 1828 | d417aa755b48f03139b1dbd26ca22abcb73b0ebc5ef6680493f28147439b60cd | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iiflcapital/streaming/iiflcapital_mqtt.py` | text | 21709 | bc789bbd8192693a26754373f84c0d92ade83c1c8b625ee1bd0dc0e70a19a3ee | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iiflcapital/streaming/iiflcapital_order_adapter.py` | text | 31754 | fa1f45ca844ba28d43dbef181a35df45a3c1984c11e108cca62cedb399ccd3db | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/iiflcapital/streaming/iiflcapital_websocket.py` | text | 29123 | b70cc516240697080f5a58342b60103e098f8099d2d641cb7159f24198591de1 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/indmoney/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/indmoney/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/indmoney/api/auth_api.py` | text | 11216 | 215de7da2cdb548dfc956acbea7d51d438317b2cda82a6489f95a4826bf8fb83 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/indmoney/api/baseurl.py` | text | 516 | 67e71790c6a82f776d948b080c80a70fed87ff426aa410c4b0c54b27280862e9 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/indmoney/api/data.py` | text | 49284 | a399b90e0ca272786543f7df4c4be1fa2945422de2787f5812bf2c13ccda006c | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/indmoney/api/funds.py` | text | 8113 | 5ed7d17dd97f4780af5846c7b9bc9480cd36fe77d5320d0c10e6467df67207f1 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/indmoney/api/margin_api.py` | text | 4990 | 7602ff56f05b44d92e30a2e8d4e416562f06b3f07ea6f78dc00d1d02de284165 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/indmoney/api/order_api.py` | text | 43874 | 47885807326c0196e44f3d3bedbe608a0bc62df72e6b80161c2b6f14440e796b | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/indmoney/api/rate_limiter.py` | text | 11946 | 71c9e8f35f0c7f2ddf0f99ea2a14a185b38def7c96a3dc8b3c964825e18ab369 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/indmoney/database/master_contract_db.py` | text | 23100 | b7b44125bdd52748b4b1e5a412459fc5a681ffabf872624f9dc8e430cf5ee514 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/indmoney/mapping/margin_data.py` | text | 6045 | 37a46fd6ef855d4f183425571a4c49d5d411319cf21a92b9051117959fac7d4d | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/indmoney/mapping/order_data.py` | text | 40631 | 463ac16e67487bd0484cd7026b0aef62f13bd51f621bdb45dd1b09db005cc814 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/indmoney/mapping/transform_data.py` | text | 13006 | d78fbec1d18b767ac578d04d31934a3f0949c6f121f15a5205d36d6c954f0de6 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/indmoney/plugin.json` | text | 373 | 368cae677ef15c14fb08bca30c50307123cffb570ecd21e63f3dcc5f9ab45e1a | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/indmoney/streaming/__init__.py` | text | 404 | ef45ec05725952b08d1a9946a4bcf157f7776267f0021e3b573a07f35397f7b1 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/indmoney/streaming/indWebSocket.py` | text | 16696 | 8d73e36dc610aafd1dea701c68ebf6af9f7a514d0fae95069dae300b7d2d9c37 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/indmoney/streaming/indmoney_adapter.py` | text | 30714 | 52da25f1e153523fedb230002e2e2c5cbc1055187ce78bdd019d16767f368331 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/indmoney/streaming/indmoney_mapping.py` | text | 5423 | 60bbdda9483bbd5523f8853586255b10b21a6c96bab73c865341c347beb5b470 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/indmoney/streaming/indmoney_order_adapter.py` | text | 15141 | 82d08ef1c793520cf0cbcd9d36a38f6dfa92467c9de9e233afed5e76f8b5593d | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/jainamxts/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/jainamxts/api/auth_api.py` | text | 3881 | 4d1383dd111c39b7a82970a201ba4ed18dc6cb504236411baf522e4c85017138 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/jainamxts/api/data.py` | text | 43156 | 0ccdf82075bf3d511ce96423da7a87cfd53c9de3e089371ffdaf05b08ed18bfb | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/jainamxts/api/funds.py` | text | 2186 | be64e65f95dc045d0b27bebf2157d24dfa0810d67ffa2b821f105da90ce98c94 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/jainamxts/api/margin_api.py` | text | 632 | f8103a0ad82dfe2f0b5129e904385778d6593e6e3532f9f3ecb2fd2b75a4db72 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/jainamxts/api/order_api.py` | text | 16597 | 9ddad01d0d3a6c95d976dd6efd93a2426ed6feec77a20c13428d5971f2ad209e | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/jainamxts/baseurl.py` | text | 278 | 70d9c9f461b3adc99d1711d2e8268412a7f33da03ee95f6c846715dd400b7fb2 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/jainamxts/database/master_contract_db.py` | text | 23708 | 33fe210c45cdfabc274e80a1fce6d50305393cd5b90a55f6e469efd5ae9fa78a | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/jainamxts/mapping/margin_data.py` | text | 1090 | c1c77c12b067d593e70240e2b40e251210fa5696d4d479f8979e235fe9797080 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/jainamxts/mapping/order_data.py` | text | 16250 | 622f4ffd8cfb5789dd5cc9c0fc3e212d9f113da7a538ecf0e2ba30c6ab61f717 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/jainamxts/mapping/transform_data.py` | text | 3231 | bbddccf153efe51860f5defb97ae59e8ff991cc21bca7be9149b606632e86432 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/jainamxts/plugin.json` | text | 370 | 13de6e5bfe12cd079016d9b53e7fbd849dcef977bfb500f131828ad90b143ac4 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/jainamxts/streaming/__init__.py` | text | 30 | 5e01516bba8809788ca37e1a29e6ad8b76eb298bef70eac226f69914740b9c18 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/jainamxts/streaming/jainamxts_adapter.py` | text | 36879 | 8f4f0dbc7033d1307719715f8464d4e5cd66970c859522c55aa8c79ce04e4214 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/jainamxts/streaming/jainamxts_mapping.py` | text | 6455 | 72f269a89dadc8d362d55d9e4a45cc9df4b2d3885ddfa8e44b0562cdda62a8aa | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/jainamxts/streaming/jainamxts_websocket.py` | text | 45661 | 04e88925022dac9a0958283c6566566de9d76517b1fcb7b1067e18f650b02411 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/kotak/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/kotak/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/kotak/api/auth_api.py` | text | 7356 | cdca89992960ef8c2bd8ce4984b65e646107ebd30873657ff40bbc92ed300507 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/kotak/api/data.py` | text | 57415 | bb718d8a5500457c282b07cd07d33d9942832373d3e6f91f1d516aa3715bcbe0 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/kotak/api/funds.py` | text | 4403 | 8eb7c4e81cbce36b864cb78dcacba5f571ce7170e0a6f2491146e0b1934b9bc8 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/kotak/api/margin_api.py` | text | 5840 | 713808d0d43efe255cab5ff14fa8ad2834a9e42d9dc2887d1449a803548f5af9 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/kotak/api/order_api.py` | text | 26743 | 47c46f5173e630b89e694f6920030141ea55022b5f6da21a52d809295e8f85e4 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/kotak/database/master_contract_db.py` | text | 31610 | 4770acb44ca2974af3f2d6e22d9fdad4351b4ef457708bd6c1cca9fd5f9e23d2 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/kotak/mapping/margin_data.py` | text | 5510 | 500ed08a3c39c57750f3eef6f5400e05283c7a97789ad2804ec16ec41ef5e71b | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/kotak/mapping/order_data.py` | text | 28160 | 5300542e64cfdfa360ac45604dad177c617c9e8644625059afa20f2d7113f79f | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/kotak/mapping/transform_data.py` | text | 10603 | 227b7498b7b62ed529371286d61a078932e63c5a903433f5776a19af5ab05957 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/kotak/plugin.json` | text | 389 | dd31f486d600ae9cc447e5460bfe531dbbad2bcff4e850fafb5f59d6114c760b | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/kotak/streaming/HSWebSocketLib.py` | text | 63265 | 85e322cc2bf5e200fffaf74f6ecb0df602ff6cf0228321f80fc8a4ab591b536b | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/kotak/streaming/__init__.py` | text | 276 | ac43f483be3d44a8cf76e693cba85dbce667b74fce176c6abb6854e2f8a6707c | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/kotak/streaming/kotak_adapter.py` | text | 74365 | 7eb6ffe3b170ffdc8e1f01ea581b1a28d4f074a47b6ead3ae6d62e1d85e3fd84 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/kotak/streaming/kotak_feed_config.py` | text | 6707 | 1f6f09f4a5beaa604243686ed45319c66be1c730607336f748c36ddb7fcf2d52 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/kotak/streaming/kotak_mapping.py` | text | 3268 | fda5493d16ed62502e40df00173ce77d72fe31470f46b910a94f248bea397098 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/kotak/streaming/kotak_order_adapter.py` | text | 13537 | 6220ae95a73a6bb9a18d683747fa870803e4a5aa55a37ca210f94321e4ff8e95 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/kotak/streaming/kotak_websocket.py` | text | 26221 | f9aa70bcb864ab05f16faf22922c94d5e76c2be55acf63262474e8df36df6493 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/kotak/streaming/sfeed_protocol.py` | text | 15406 | 80b0ebf0a5eee87f8818e7ba239d14a0f34be040a83691ec192085ad9d3a8205 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/kotak/streaming/sfeed_websocket.py` | text | 27875 | 624bb603918f3c71bab8f0c492e782b1afb5c9ce5031135195827b98616867e3 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/motilal/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/motilal/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/motilal/api/auth_api.py` | text | 8558 | ac7bff52823af5250c5b8de58c80f93ca2e7de9dc158df5c6fd10cc9051ed218 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/motilal/api/baseurl.py` | text | 9554 | 60125e71a9f240778a68ce87e55b753c1f5ddc352177d7049f480f3abeddac43 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/motilal/api/data.py` | text | 64876 | e5dae676232f6e8a25f086b78ea78615f67ef2e815e1a2e50d21e701be2e241d | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/motilal/api/funds.py` | text | 8495 | 1b46079dc6c754f1814d49c54742b952dc02f7371a84e4cbceecad95438baf6c | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/motilal/api/margin_api.py` | text | 1365 | 80c98a3c20335fbcb95429eb020b6b0cb36e0ef2b0850f44e304b16990077bd2 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/motilal/api/motilal_websocket.py` | text | 63891 | 61278bda14a4e5ae856f9a6f2577b6770e83f21638aa714803d72840800a8600 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/motilal/api/order_api.py` | text | 37950 | 1a2473287910e6767f4302ad7ad0cccf82d1ee9d3479c9d53a1e210895ed1e3e | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/motilal/database/master_contract_db.py` | text | 35609 | b0dce7771a8edac8d02c388a6faf12a01d006f2bc56f3b8c2e20d74644e04634 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/motilal/mapping/margin_data.py` | text | 1535 | 1c48b84a15672af205dfa9f3d18d6a5c2a5c6c8c1f10c4cff543ad60b5f600b7 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/motilal/mapping/order_data.py` | text | 31609 | b552fe53d0abb3aab90febf0199ef4e3d6bd0e88423631501c6758fa91698bed | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/motilal/mapping/transform_data.py` | text | 14086 | a69587bbc093df62de74c56c910b692712f2e5fa382ecbf299d363723ff7728b | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/motilal/plugin.json` | text | 389 | b96e2d9412676d5b9f4d8da3724c243594ca5196398415565a76dec10dc11c64 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/motilal/streaming/__init__.py` | text | 741 | fa91835719173633d602071b5a1dc893f0d7aefb7c7962fa5da81998a458a4a6 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/motilal/streaming/motilal_adapter.py` | text | 28984 | 6e856ba6a465cc3dde0640a8b3448dd69dd768382857f1ff0b7c76dd091d5419 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/motilal/streaming/motilal_mapping.py` | text | 6291 | 9ebf450e0e7c296e59dc3f8d233406c0dcf1d337bbff0428559f8e1c1ccd05cc | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/motilal/streaming/motilal_order_adapter.py` | text | 11238 | a3085822ab875ed722208331d31bb5dcd2198ef745035ba36d320a929245408e | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/mstock/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/mstock/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/mstock/api/auth_api.py` | text | 13153 | 54e5cdadb9193f55024b3a1a04bfb03f5851fcd2d1a9a881c24ec19898fa4a98 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/mstock/api/data.py` | text | 37550 | 16b4c1993344b97da02326e03790d62e7af6f6e220b45640d3f04dc2b45dd7b2 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/mstock/api/funds.py` | text | 3194 | 0bee6d88abdfdf952aa45794ffe23754d7f4a1a5bacb221ae497f2c422d107ac | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/mstock/api/margin_api.py` | text | 2987 | 1a5f34843ea4cf6b3918b68e593f5cc451f47d2f6a9b07b15ea9cad90d82ab59 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/mstock/api/mstockwebsocket.py` | text | 41126 | 39341562d33e9231c6fe3ba3b73fb183218f7a3d02b9454a9e04c345132038c8 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/mstock/api/order_api.py` | text | 27107 | 2febb6e45d604de7a6523080dbf7182c3405a2370ec326f456fba430c2c42bfe | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/mstock/database/master_contract_db.py` | text | 29625 | d1f34df94b27d00853a9e584d232b057cd1f2d7faffeff7a3202e56e8f686dce | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/mstock/mapping/margin_data.py` | text | 5524 | 917443b229305524d637d8c70907f6f4af0f76749f41d80d333df4df18500715 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/mstock/mapping/order_data.py` | text | 29164 | 1ad298ce3e5a470634eb9b7c914fd5a60e647141944fcd25f66b548453d86437 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/mstock/mapping/transform_data.py` | text | 6593 | 3df56a39ec5be3a3d4169c83281e919b7bb054515d3bde9b536ed89bebb96b4e | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/mstock/plugin.json` | text | 370 | 3dac80eaa6e9e161c297717d39b7b339fa22a6000380837c1f0345d44f691f57 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/mstock/remainwork.md` | text | 1135 | 68178e85594f3fe1208c387265f53cc46e1cb7be7be9dc52dd3e6765943832a5 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/mstock/streaming/__init__.py` | text | 384 | 754b9b9ed3d57cc4be4736abbcc244175362425e0b44bfa03b9d1d4490383b06 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/mstock/streaming/mstock_adapter.py` | text | 34375 | 42f3fd101c76615c668abc18a9d333f6050c7b130cddb5484a92af22da2043ae | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/mstock/streaming/mstock_mapping.py` | text | 4979 | 3efc734c5c693e439f30f16d504328ca5cf33c12a470194a3839fefc00834249 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nubra/__init__.py` | text | 28 | dc7004e504fcb9c548b2ef16605cdf473f34a1a94f38d1e306d8bef234eab07c | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nubra/api/__init__.py` | text | 20 | d3ca4a7f2637c284def055e7311f42423bc7246c4bf205c7a4e788e67aa59c8f | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nubra/api/auth_api.py` | text | 23185 | b68c5ef5ef7e2baf479393f9ff6d77b1e9d6d5779fd4002efac2645cc7aa46ef | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nubra/api/baseurl.py` | text | 3501 | caee0c1009704fc6f5294b5b22ca832c4ed1aa7c571d7828d26744ad7fd15ae5 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nubra/api/data.py` | text | 62690 | e7bfc7a93edb781ffb9fa6f57aa42886518a049b9ece2881904005947e9eb4d4 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nubra/api/funds.py` | text | 3669 | 147ef7cc7b1b0ea3d64e45e75d4c783d589de5c33926f9d69854bac21f63beb2 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nubra/api/margin_api.py` | text | 2951 | 6f1dcbf194b655b661047affd1eb3a4973b7f7b906f0b96ec5391b4d5d83cfea | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nubra/api/nubrawebsocket.py` | text | 26838 | f33be14796acd28a2215587fe146a330e23256b545877272eb272503661eaa80 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nubra/api/order_api.py` | text | 30860 | c25e298eee16e3c832acffce3e86d587ef3d0039ad2205482d7ec57c4f519982 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nubra/database/master_contract_db.py` | text | 15713 | eee3c9bbf240318a7f50bd6fa3e2a8f5f9f483efdef3f22db7a91e4268c74aeb | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nubra/mapping/margin_data.py` | text | 7220 | be98485b7e0998ed3448da90c3dd3199e639819c8601a5e3b4b1526397907139 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nubra/mapping/order_data.py` | text | 27254 | 5694e52fdf9cd3e7b99b6fec2c98286b9231282f4d2b1000f892d555d6776a43 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nubra/mapping/transform_data.py` | text | 10631 | 6e5cf49be9b4d90772a9e591ef8afb94639466963b711231be60789d57b6ce70 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nubra/plugin.json` | text | 371 | 7bf1617a08e1980306b41076164ccd5f20843b55064a9badf2de1e66c9109093 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nubra/protos/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nubra/protos/market_pb2.py` | text | 17043 | 0c8546223538c53c88cb7e5883d1e58e731d22240419efa4cccce226a34d04a9 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nubra/protos/nubrafrontend_pb2.py` | text | 24533 | f7e8574b8982729e8170e9d587c3c3addebf987a2300f08c61ad38cef4f25e86 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nubra/protos/orders_pb2.py` | text | 72310 | 1e82bd4ef2e0d6e48b5c903fcc0b459b34398f8964e5b080bb38620c7f877573 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nubra/streaming/__init__.py` | text | 289 | 7d144446bad68df7a81baea33c1f7e0c36bd0c8a47075e72cae4e782e99943a4 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nubra/streaming/nubra_adapter.py` | text | 36799 | 1e4983471cd051f2e39c93ad1c4d541281c135b8feb8509034c7721d5ca6d48e | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nubra/streaming/nubra_mapping.py` | text | 2850 | 44f48a8690ba9185dbd88f6f4085b3604ebbc16c2c97750d5b0eba2c3d08a21c | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nubra/streaming/nubra_order_adapter.py` | text | 10682 | f7e095f1e85e589a8326ff836a66dac7d8f4edbb42e4bad100268ff8d3563e85 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nuvama/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nuvama/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nuvama/api/auth_api.py` | text | 5276 | e11699695c10940e35460805b0cee16d72431437cb51113d7651715d5f337649 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nuvama/api/baseurl.py` | text | 7833 | a445542c3126b954fecbefa8c43696170ca2c57133113cc211a642f87c0c9a75 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nuvama/api/data.py` | text | 18290 | 82174c7928b943fbb1eb122d8cae67dd86ebcd4bb9b36d5f774f70f739278c43 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nuvama/api/funds.py` | text | 1638 | 2bbf782cc22a0f9740f3e54f51bb552bed62dbced184fadecc03d50b713663f7 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nuvama/api/order_api.py` | text | 12965 | 95bf25bc70585033f09a4b5688e99f2c3f56fd7b6e380ee830f51bc6ee64d795 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nuvama/database/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nuvama/database/master_contract_db.py` | text | 10171 | d6fbca5ef2a753d73c1948299e6bd91202e294c2bade46b463fa74653bd4e8ad | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nuvama/mapping/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nuvama/mapping/exchange.py` | text | 3433 | 2b7df5061b5a0dee2454d0764ced91e756df2eff0c3199f7da0b9dca99b6edb0 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nuvama/mapping/order_data.py` | text | 9589 | d388888bc5964853945d0af072360f71fe1fec197f8406a131488228ad5bc368 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nuvama/mapping/transform_data.py` | text | 9415 | ad8edb4ba33cac80a0bdd24fa459bf69af90dfd684b0cb3d0fde361bbebbadff | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nuvama/plugin.json` | text | 406 | 61d4bdf98d0b2ece9e05cd790155431035f683b0dc75604e63b20033dd6add16 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nuvama/streaming/__init__.py` | text | 92 | cf38569e8d95d367230880dbbe020df1dc9e2f5cbb3d4e3cd4ce807639e3d88d | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nuvama/streaming/nuvama_adapter.py` | text | 10832 | 68d5f6f70a0e01ec5e6f62eca9f0b9d191336a209805226f9ee0f48c2aa7e92b | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nuvama/streaming/nuvama_mapping.py` | text | 813 | 76d8ec2064110fd9fd47e0d4ed489a3c3b68e1cc2bc37a2474b8f175f32ceefa | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nuvama/streaming/nuvama_order_adapter.py` | text | 6620 | 72a04c2e1f3a11cb460472b2395076372a31d06c03cbebb8904e38370903218d | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/nuvama/streaming/nuvama_socket.py` | text | 11186 | 7e8d297b3230a19296697d9aa5204b68f4abfaaf21d75d4d1abc5731f275068c | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/paytm/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/paytm/api/auth_api.py` | text | 4058 | 8b697a747ab8ef963367db8baaf3c30e06dac0d7a83ea99a2b0c37c57d4eebac | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/paytm/api/data.py` | text | 19674 | e20faa7a5a3322f43f9573d6f787c8df1026c5e8558f40226a991f257367eb9a | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/paytm/api/funds.py` | text | 2649 | 2380102f84879c03db1b5350923ca1e51b6e3d7396f1d95fb533a9431ac14ba9 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/paytm/api/margin_api.py` | text | 894 | 05876c1ca48655437a442234f19a413f63681260239e2a28fa2a7549d0de83fa | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/paytm/api/order_api.py` | text | 31033 | 10c9bb70eb8d718d4ab12afbf4069424100b43fecd9eab131255edac9160ead6 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/paytm/database/master_contract_db.py` | text | 15824 | 92c890bc03d300aa4a192ca1b1773de62bf94d90f225e9b6128420a80abb389e | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/paytm/mapping/margin_data.py` | text | 1416 | d7d71266f82c37733359d0e7a62f1fe03f62822e3875dbf0dac7ca75d876cb28 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/paytm/mapping/order_data.py` | text | 23997 | 285f18f64658165d1bc96dbb656ffd732dc82a35929a1e61440b5b83a13e3e28 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/paytm/mapping/transform_data.py` | text | 5060 | 4cfdd44c87daed8ebbf81cab27fdddcf6a299ae1543f889d64e816783733c95b | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/paytm/plugin.json` | text | 359 | a7ed06a744c3aeb605e03ee98bc2aabc15d99b93ae044281ae4ed67c2cc4867e | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/paytm/streaming/__init__.py` | text | 325 | d22baf1f0c0848e544149e80a74f87fd986f84964febc6ea3e3e4c5c3f5e73ac | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/paytm/streaming/paytm_adapter.py` | text | 33571 | b8bed914bab1a0597f8639b2254ff0970bc62bf58e7724ebccfaae4967bc8094 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/paytm/streaming/paytm_mapping.py` | text | 4308 | fb99d8ca205201a383e91dc86cdc83d79d1d8b891e80e4a92664632d9f6e653d | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/paytm/streaming/paytm_websocket.py` | text | 22057 | aca2c370620700e0493b3d2eb5bb7abe8264e7d465f6abeb6e432b6651f9dfdc | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/pocketful/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/pocketful/api/auth_api.py` | text | 11671 | b1c851a0e9db0b69df0effb6593189acc8adce55888a0bdaffc1e33640705118 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/pocketful/api/baseurl.py` | text | 5715 | ed41af90b431d526ec5fd0dab13cd6656a3306d06acd95288bb371363e699ebc | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/pocketful/api/data.py` | text | 31952 | 5f3156ee22e250573c8c6aad436e0f0d9ae854b3b2a3b11688c9ab1cd9198ad4 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/pocketful/api/funds.py` | text | 5288 | 6eaf237325172281a3fe0d3a0d000659048f7a113268b115c4147eb6317fe46e | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/pocketful/api/gtt_api.py` | text | 13027 | d7bd44264c3b04b7d280776c9f74f16e6644d97a57bd159aa6a949d6e0149a41 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/pocketful/api/margin_api.py` | text | 4653 | 50fc47874f4c6dadf983f0758ddee1c9ede408c96d325168b72a2349f7d7d15f | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/pocketful/api/order_api.py` | text | 27270 | 5f3474ae30b969ba317910e230dd4574d9c94d9e3a5155db187f138e829da9b6 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/pocketful/api/packet_decoder.py` | text | 9414 | fc5e9c53fbc97e3d3f8dcd7f72df4b941f56eceda01639d84f5cd62a83331acb | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/pocketful/database/master_contract_db.py` | text | 27630 | 323afc724ea089396603d95df808b23c7699eb6f3009275171f6ff4575f27de6 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/pocketful/mapping/gtt_data.py` | text | 11492 | 67d476eb206f0b62b0a5cdfcb8223dcd583f8de22cb75ea0e04beec2efae5ac0 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/pocketful/mapping/margin_data.py` | text | 8309 | 01341f69269971c6cb6fb2d316abc46faf641eb28f71f65a610fb95c5a2fa4fa | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/pocketful/mapping/order_data.py` | text | 15758 | e1c1958ccac942f775b199a07b12610b9861196a1536c038c018b7d9a00b1c98 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/pocketful/mapping/transform_data.py` | text | 12090 | c90de81086c17c7ae169f670303b35410baa010aeebc20842ecf0fb1f3a58da7 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/pocketful/plugin.json` | text | 382 | 87f1d766336f141c0c6d4e68cda8839099b74a4793dc68effb3369af645d6605 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/pocketful/streaming/__init__.py` | text | 244 | 0886e454221c5379de77704129aaa22b1581999fe31fdd869fce768c69d05d66 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/pocketful/streaming/pocketful_adapter.py` | text | 36441 | 3fe828ecd2fb0e7e2e5de2df3ccbd34bf56fbeb8acc2e0259093010d523b568e | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/pocketful/streaming/pocketful_mapping.py` | text | 2337 | ad2480035d0f434bf6a06440847ac1228993f6f33073e3e3116bdd6a31c60ccb | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/pocketful/streaming/pocketful_order_adapter.py` | text | 14999 | c13169e1d01eb408b32ddb1706364c2902e98ad450f088fca0955c9356531485 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rmoney/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rmoney/api/auth_api.py` | text | 4951 | 89e3db2a2c117252f4ab364f21368b1f6b52eeefe60d8bec82c56e7049cbf162 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rmoney/api/data.py` | text | 45461 | 155d8646557f09dff24acba93e28b95d881a9e1072130a6d3291c00754e75366 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rmoney/api/funds.py` | text | 2286 | 533dd9e60a889c1b3960f12ba170c427b44b45d1c0eea42604cafccbf5132390 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rmoney/api/margin_api.py` | text | 3042 | 48aee4198575da95c9af3ea1a6d93a18a192917afc20864a176dfd7c20431ef1 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rmoney/api/order_api.py` | text | 17282 | cbaa1fd5279e59a9c96c2b04d209c0c75636a16a4f1aa6103756c63f187d653f | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rmoney/baseurl.py` | text | 580 | bd4d2fb078223fdeef1a67f139fe631c1500a40799132ac975c94e2fc890ad6b | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rmoney/database/master_contract_db.py` | text | 23565 | 636eb932e72df5e752a73357df8533525d58874f1f4de301a10afb524b0814c2 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rmoney/mapping/margin_data.py` | text | 5810 | 64565f36348bdc7f89fc942aa3522dcd4c41dd4eccd190cec79a5650f966a25e | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rmoney/mapping/order_data.py` | text | 16209 | 8495e336c1b20367f003bc67e9e76dc7a1e59d064be4e59291a710fa62e3115c | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rmoney/mapping/transform_data.py` | text | 4473 | e565ed77455247f2f84e11669300cbf19b1360bafd2324a80b5f5beaab67be16 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rmoney/plugin.json` | text | 359 | 0c7b34bb2ce4af7bb062acb617e195604acb997c30c8b3b7cad5bc40c2d0206a | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rmoney/streaming/__init__.py` | text | 31 | fd40dccf9864fae188a9e549d381321733b944e257a34c7dc74dd53a60e58e40 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rmoney/streaming/rmoney_adapter.py` | text | 42375 | 9c1bb092c202975110200ce15ba6a18dd6b80ac308337892b7daadcaeee2afd6 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rmoney/streaming/rmoney_mapping.py` | text | 6570 | 6bf4ddb9985b3d07c80d391660fcaf84f7443bd32959e90c7f3e7be50a122799 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rmoney/streaming/rmoney_websocket.py` | text | 47981 | 0d12559cb7af9fd7ac39747d63f91977ecfa90573387e91b0442875deb8ad4d4 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rupeezy/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rupeezy/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rupeezy/api/auth_api.py` | text | 2845 | d527544f6c476ff028ca50d8ffeba916a473c0f6473190995b714250fe1e2ba7 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rupeezy/api/baseurl.py` | text | 1449 | 56baa1e090ca3a49bf2c9e7c9599d10fea2bfdcc604f19698cb5cd44a68d3af5 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rupeezy/api/client.py` | text | 4923 | af3c815aec9f0c0166fd46ab48528356b4d5e67a0f2e8bca611a46d74a4e9dc3 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rupeezy/api/data.py` | text | 11261 | a5a3f81a6d5bac1c5c107dd3ce96e1ac4320df5fac6d150ecd568bfad71c6602 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rupeezy/api/funds.py` | text | 3456 | 55aa6fb84304c1ea6aa5b122939df389d73608d1bf9c31a70d1c5dc7a6c41c1f | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rupeezy/api/gtt_api.py` | text | 3817 | 521b19fb3a5af56e8e1b3d615ffc817295b712e072288741de6e8dcfcb6c16d4 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rupeezy/api/order_api.py` | text | 18173 | 4765ff831d94839f6bec9a7f35799410d33b6b8c527c392da410768e90dc5016 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rupeezy/api/rate_limiter.py` | text | 2159 | a49ed82d0e29870674961a8ef61b4127d203679f26aedfed6a596c8ef844bc27 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rupeezy/database/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rupeezy/database/master_contract_db.py` | text | 8592 | f7b98994569ed69d1f81e255bed846b839cd419718b8fde8112a56c93bfc23c1 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rupeezy/mapping/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rupeezy/mapping/exchange.py` | text | 9425 | 0cae8e486ec7afd10f535f3b48e6a99a5646a71eb3cc62059fa18a4add2f85eb | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rupeezy/mapping/gtt_data.py` | text | 7889 | 91908e4e375e6638b67e6738957065df98c5bda5c3246cc31c56e3b8bc9649c7 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rupeezy/mapping/order_data.py` | text | 12939 | 69c30a4aff08b9d360033e821c49891a60c08cadb18adfee57c4942b49f9f26a | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rupeezy/mapping/transform_data.py` | text | 4449 | c93a77b138734319bb70e6b5df4aa66b8399a2a89c16a1bc6602c58c8c9a22cf | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rupeezy/plugin.json` | text | 389 | 98cf609ac5a333a8501143ef635ff0f77267485421dea16f8f641b3c5c46bae9 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rupeezy/streaming/__init__.py` | text | 119 | 327c4798aeba996980a0b7252ac372103da1a3dc6595372effabe613db0ada27 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rupeezy/streaming/rupeezy_adapter.py` | text | 10879 | 5932179b84d35fa8557b8e879723ba72411c8f1deec81f5c713833983faf6ae1 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rupeezy/streaming/rupeezy_mapping.py` | text | 1096 | d53f23b417ad3ec3d5f04b6379863dcbf524dcc39f48309e014be2cd5b108981 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/rupeezy/streaming/rupeezy_websocket.py` | text | 15762 | dacaa62a51f4fa387cdcf076d26b3e037bf267416a9a243390c02700747194eb | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/sahi/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/sahi/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/sahi/api/auth_api.py` | text | 7167 | 3dd98774a2672b2de3e9d913fd77b804234faa31c300680823a8ba2b03b9c2e1 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/sahi/api/baseurl.py` | text | 1276 | 2e4c6712684e6188f3c9024ec73ba0f21f5875a473fb02eebe2f864d53a3843c | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/sahi/api/data.py` | text | 15638 | cc3064a136f1c8761401b1c6e192e578bc0820a6c93202b24766b0375c446963 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/sahi/api/funds.py` | text | 4114 | b63e5f932f6282105478f86747060e2b8c2853df5a532a3723ace3e8f53c3efb | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/sahi/api/margin_api.py` | text | 4752 | 7b257514ea889f3e875063990cf482756648a2e42ecc547b98e6ea2b5ab4f611 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/sahi/api/order_api.py` | text | 16633 | 4f2a68d1f7495f79b99bd940ae180b8f4b9da116d9a4dd7f016d961dc43ad575 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/sahi/api/rate_limiter.py` | text | 6618 | 29a314e93e3e6e83231999c3eb441fb34cbe6b2f2b9b5d4571d7cdea106a0c80 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/sahi/database/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/sahi/database/master_contract_db.py` | text | 13954 | 431d83de4f8904014a4eb5ea07c69622a9c1222b602e2f59e3294a824f5adab7 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/sahi/mapping/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/sahi/mapping/order_data.py` | text | 11600 | c411fed28e9f50a0bb3512ad06a7670732982a12f3c50814783d2455599f8cb8 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/sahi/mapping/transform_data.py` | text | 5963 | 368ed9141d99f12eee35615306c66c853f7d3fc1cf658bdf31881b8f67d0f749 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/sahi/plugin.json` | text | 359 | e61c0a606232fa28faef1687c56411bf271e867c7dba1bb98e7aae62fa1afc07 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/sahi/streaming/__init__.py` | text | 156 | c6db5d89c4d30007f6afa91d759a1947753a6f8d3424356e09a8a8f8eb94b927 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/sahi/streaming/sahi_adapter.py` | text | 19243 | 141cc30476cdf6cce6a9b167b6a6f1039f0d1c9fc4360bec478fde2de2742f6a | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/sahi/streaming/sahi_mapping.py` | text | 5977 | 05bc97a5ff47507733b116d4981fa66aac83f4b3639add87cfabec149d3f4926 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/sahi/streaming/sahi_order_adapter.py` | text | 4607 | 84fed8b431fa89f8efdd0b8f12716ae7f547dcd674d9192194f433ce485e60ed | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/sahi/streaming/sahi_proto.py` | text | 9962 | 11956fc4705620ec385ae208f3ceacc82dd9f55030b1e795591053fc6bfdf3da | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/sahi/streaming/sahi_websocket.py` | text | 15143 | 28f622ca2c5e14751fe9cd12f7dcbbb8beada5c28e1688c3a712e3bb5b9399ea | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/samco/__init__.py` | text | 23 | 6fe62b3d6c16f6df67e86329f07e9bdc313f3a75ed992b11fa5a60fe77c78f56 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/samco/api/__init__.py` | text | 20 | e3b78273ba8f81a0b3a0cebd13083190f27e263da3a44e6cb1bc88a5871b6772 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/samco/api/auth_api.py` | text | 7166 | 81b56bbf70101ac61d75eb3d9930ded1f921f7ef9214b7c3ccc515653ff125f0 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/samco/api/data.py` | text | 43448 | 5520ce327cc0e7ebc3f3e6587cc2a1f1f1c09830c54b121e3e33641a54bc9377 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/samco/api/funds.py` | text | 1950 | 8d4c8414b09cdf37c213acdb88826a7a3eb17bdfc809d794a4e3bccd0ab7a17c | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/samco/api/margin_api.py` | text | 4601 | 9595a1a94c0019494dc131a443efa333f9020c5fadfdc84e97503072407d0a85 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/samco/api/order_api.py` | text | 19242 | befd0c18b63037209a86313858e2cc1cb6d92ffa62cde3095ac75c336df11539 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/samco/database/__init__.py` | text | 25 | c99fa00a930965014a3b8fb91eff3818e9284697c8d7d8be0cf365ca97c75dd8 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/samco/database/master_contract_db.py` | text | 35205 | 816f733b0679a0096c15d0c97f2940d0e594763d821bed4f1394702e21a8d72c | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/samco/mapping/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/samco/mapping/margin_data.py` | text | 6543 | 7af366a1422e5f0e7996f5a1f03120acce688f30a2db5deba925abe785de5ce3 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/samco/mapping/order_data.py` | text | 17958 | 65154a298f9209c90b401d706d98694729525e969cf18bdb54599ea977f408d0 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/samco/mapping/transform_data.py` | text | 9974 | 45551392db58f774e7c237db75633a2e07fd27786551e52f588e5b17a46fe177 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/samco/plugin.json` | text | 377 | 8d66c5f049ec7ddf2d4610e1f9891f21e1889a47cd35236fae9729898f61eebf | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/samco/streaming/__init__.py` | text | 298 | 6b02764e4346f58cb1c561921c92d9ca15577bbd0d26a1470bf1f0c456121a85 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/samco/streaming/samcoWebSocket.py` | text | 44332 | 0e6a35822d67f421f24f6a76dc96b1c09fdb8c24611a9490223a53da16677188 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/samco/streaming/samco_adapter.py` | text | 29779 | 5206a08c1015cf0c57b37fc344b681f4d3615a17c11363fd2f77e8cf2f802b14 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/samco/streaming/samco_mapping.py` | text | 3500 | ffac31425347adb4d5e8397a50eb0959e474415d17d696150173fb44fa52cda5 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/shoonya/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/shoonya/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/shoonya/api/auth_api.py` | text | 2466 | 3ee848b708cf07bfe2e3bae0bbd918b9bd4f637e87d6a14c2fc888dda82b3cf6 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/shoonya/api/data.py` | text | 58985 | 7421e9a01aefc8c77fe03dad641a210fdd4250e4dd34690a2e9997721460e331 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/shoonya/api/funds.py` | text | 2635 | 298ec6301069f65887c83e2f88eb62c513e38f9ac355c1beef37563d1fad1d9e | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/shoonya/api/margin_api.py` | text | 2979 | 84b20751b0e8691c6cd808306a6641206bba82496ad4880733da1058345d0608 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/shoonya/api/order_api.py` | text | 15960 | 14fe8cd37c877a36c674970147ef0bc71baa48331a61b7eb79a9dc4251b1ff76 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/shoonya/database/master_contract_db.py` | text | 36256 | 61268d558ba71d8213eed2e842bca020c853545cc3c89e2514e98a655b6cb675 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/shoonya/mapping/margin_data.py` | text | 6648 | c4776f4b54d31ed641aeea28e64fc6c5a3d4c14b03ba92037cb105bc9b576606 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/shoonya/mapping/order_data.py` | text | 19206 | 5fcf4c2e93bbb3261ab16f30129ffa14312c1516dc447db4b148de2e176c2652 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/shoonya/mapping/transform_data.py` | text | 11203 | d258e3f8e33d7d2c82d17db02f5619810c74d99b5eb2756a5d85d2ceb99aeda0 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/shoonya/plugin.json` | text | 379 | af0dd211301bb3ca6e94400c97630246bfc0104b0564461a5736314163486e99 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/shoonya/streaming/__init__.py` | text | 308 | 25ffa00b58759492bcabc7c4988bc92a5128f0ab093ebb7aacd4812ee9508cdb | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/shoonya/streaming/shoonya_adapter.py` | text | 71893 | 61055534784bf6dd6a93681141cc91cffc8a1f2f3d0ce6450b7feebd2c59c366 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/shoonya/streaming/shoonya_mapping.py` | text | 1327 | 051884d2986cd93973d4589c808b817844b42505752051151c565a659f06c6db | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/shoonya/streaming/shoonya_order_adapter.py` | text | 10654 | 7b22c01736abc7eb81f72b1e2ec71a2908e4ee72c44c0dfe818eb368d07bf50b | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/shoonya/streaming/shoonya_websocket.py` | text | 41997 | c469f05b8f4d920ac4b8fc9cbc61a09d75a14345ed1f63a8dda0d5a99c1a4293 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradejini/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradejini/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradejini/api/auth_api.py` | text | 7665 | e87df4dfca0e312447a244de3f224a2f394d504ec482305361298c4df8c6ecb7 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradejini/api/data.py` | text | 54013 | 37f080ed5e7474c4db8608380222397c268a1001b1692e60fe0c655dd9f79036 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradejini/api/funds.py` | text | 3590 | a8aea26da552519e84cdcc89654ba38d8a7ec02d3281cca573b43f97958ae351 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradejini/api/margin_api.py` | text | 868 | 143d8a64974bc8a6ab2bcf642d9a0dfb0481a226f92c8c49907975600747815c | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradejini/api/nxtradstream.py` | text | 24973 | 811e8152b89824f7aa529c331dbdacdcdd043a4d571dbe2cc63f52a6195cb6b6 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradejini/api/order_api.py` | text | 70817 | 8f82351e0da79737f12f8fead6b6ebc9a35dad705da9ab9d944a7b50cd7bcf0a | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradejini/database/master_contract_db.py` | text | 25415 | fd868761ec6e20f632d6fa06e9bff4822f612303b0ad472ebcd4faa7d2af38f7 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradejini/mapping/margin_data.py` | text | 1370 | 5f9d946674cfc0c5220fe9ca1710f256a0c31e72dbe88996637c81a5e806032c | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradejini/mapping/order_data.py` | text | 31458 | 3ce0fc5c5ce73f3faed031a2cb492a1645e4743d0e9cd14449aba662cb5efa48 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradejini/mapping/transform_data.py` | text | 6417 | 8be0c5c7c87338ec7f5888d7606526625ca6ae4db5610d00d8bcee635890fcee | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradejini/plugin.json` | text | 383 | 72bd48a70e42ec853aa79bb9037e896589188c95293c99b5b37da4a1f7ad5cf7 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradejini/streaming/__init__.py` | text | 294 | e2fd31894c98d0a5607de0d0bef5ca94a90b45593619848796b68fb18695a825 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradejini/streaming/tradejini_adapter.py` | text | 39108 | 5e53fb0ce20d944227f8d013d0ee2b2bc8bbd94528eabd02f0245b9b833249a9 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradejini/streaming/tradejini_mapping.py` | text | 5449 | d936957ea4c2c279126e302384dffdca04212939203cc0233e21af01ff92e362 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradejini/streaming/tradejini_order_adapter.py` | text | 15020 | 986dd3e00cb444dfaa828b4cd765146f2dd662b6748fd5b005e653009cbe5ce0 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradesmart/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradesmart/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradesmart/api/auth_api.py` | text | 4065 | bc20bdf9564b240196be18e67707525ee70865cbe779c45578374acd7ce4ef83 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradesmart/api/baseurl.py` | text | 3608 | ed70041434ff169749b2fe3658d90643e46246df5116a49dcd53d834ea4146f6 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradesmart/api/data.py` | text | 38042 | bd0e206d4c618615d7407dcf120b4cc1fa70bcc9d91aa35709909f6ba8f3d482 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradesmart/api/funds.py` | text | 2811 | d7f84cbb1923c89ea5ddf737577daed96bb68c24daf9fae75bb121822646b018 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradesmart/api/margin_api.py` | text | 3026 | b8aa3dfe570753592e0d2146564459c24bd5984a273b79c96c229ed5009c9265 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradesmart/api/order_api.py` | text | 12002 | b7b23332878c232731e20304b889aa6bb3bb3a191d0146f39aa9e31527759234 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradesmart/api/rate_limiter.py` | text | 7799 | 4f7680f8c3e678b2c576e2c675800b6cdb30bb8801f6d78ddbb4f7ffcff8af44 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradesmart/database/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradesmart/database/master_contract_db.py` | text | 20486 | 57b3280d09388339b2d43beaec32d1958a651a7a6ba7a167dd218f6a0418a150 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradesmart/mapping/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradesmart/mapping/margin_data.py` | text | 2357 | f73016fe9ab2856ddfeda2b0dd61d8636f6e5330eff10a456b0491c54f8db949 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradesmart/mapping/order_data.py` | text | 14648 | 4748cf4355012c6a9d491fa6db134cb9bbcd0eb5a76a474b5a5feebd35266180 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradesmart/mapping/transform_data.py` | text | 6359 | 3d8b17115ad95517e62a5fa825ff64d50ad569139c4ee0dd88ef10601557ba39 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradesmart/plugin.json` | text | 398 | 0f20f98a1273ded5a4294b2c30ae786359c98ddb3f447cb79805337ffadee592 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradesmart/streaming/__init__.py` | text | 405 | d52fb441e5469d1f843955dacb20ac2faf05f4601fa6d1c2c26219966160414c | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradesmart/streaming/tradesmart_adapter.py` | text | 34265 | a1eb735e018c1d03502a0451f8f268f27120bdae60380e80f765bb22115fbdfe | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradesmart/streaming/tradesmart_mapping.py` | text | 1963 | dd3cb78f4370e040f32c1cada1c6a291ffae04f117545d5247bc8e6eece2326f | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradesmart/streaming/tradesmart_order_adapter.py` | text | 10665 | 88ad717b302fbf4190bb399e91ebf8f8f41e46f9d0143ada891e64213dd33458 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/tradesmart/streaming/tradesmart_websocket.py` | text | 21079 | 737e8fe87c44a958a33aa6a2b09fc8641f8f8d3c9499751e6fc5dedce15701ae | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/upstox/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/upstox/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/upstox/api/auth_api.py` | text | 2758 | 132487f5a0b06f5f73602087944f51457322a8a6324ac597a2a96e4038e48261 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/upstox/api/data.py` | text | 52125 | a6d1578fb0b7810360ae320374c373f3aa31e93c38b8eda636bb1effec17b88a | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/upstox/api/funds.py` | text | 5891 | 33a3d6ec7aaeeba1d1f1e773b26bdc682656864c324a9fa8e37095e1b6d8ad33 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/upstox/api/gtt_api.py` | text | 14208 | 5cc113da088b0acd3d9eeb2332eea034a68b83217fcf466c20fe7169f2d15e70 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/upstox/api/margin_api.py` | text | 3553 | 95580d82b1a08c1b342659e042fe0c5cae5a82d632d5093297ed65345c25cca7 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/upstox/api/order_api.py` | text | 27264 | 9d344dfe72ff4f3ef9ce88c948d491c72480be5b6101484278a40785d7af478b | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/upstox/api/rate_limiter.py` | text | 15927 | f11482900e3faa837288bb05111db21e0d2c30cadbed6dddd2e1e7ba0bb65150 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/upstox/database/master_contract_db.py` | text | 13923 | 59f2476ebc879cd015713d5adc5526d63874d39fc525f4f90115b2a76c76ade8 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/upstox/mapping/gtt_data.py` | text | 20063 | 378c3424fe9d267e1b1dc05eb090eb0e4d7dc11fcced3b7e92ae824e094700be | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/upstox/mapping/margin_data.py` | text | 5676 | 3265cacf7dbaede39eefa5402312244d080e7ab1c09e6f6a47fdef18f565ccb3 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/upstox/mapping/order_data.py` | text | 13419 | 9b017f42787912bce67358b7c6edf71317a041caecb08922b7f7dc06b5d392e4 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/upstox/mapping/transform_data.py` | text | 5116 | 864c6cd95ff4eaded853bd31b3fd3bfd55c3ec979c74ff4a856807fff591736f | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/upstox/plugin.json` | text | 402 | c017d945b031409c10dc981549a7f5139f54e2dae336fcbe0a53a2b305f62033 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/upstox/streaming/MarketDataFeedV3.proto` | text | 2897 | aabf92e5dedb16add110488211f3fedc1945790788d280962f751458260f496c | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/upstox/streaming/MarketDataFeedV3_pb2.py` | text | 9553 | 9620f968a990f75273fef14d87c2e56625ea6058b49401687bc2f6cf881c947f | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/upstox/streaming/upstox_adapter.py` | text | 46999 | aacf9d9f55713e3be2473ea3fe288ba242c2e86c4dff51a7a3a417f26dc30c65 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/upstox/streaming/upstox_client.py` | text | 37305 | dfcf07c92791fbcf8a1be3687dba95c1dd55585f965efaa2c208e26778f53495 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/upstox/streaming/upstox_mapping.py` | text | 3805 | 55d728277ebb9b78ec5ea42b91acc89a77255bc777c8ea96d90f58ef23a55f76 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/upstox/streaming/upstox_order_adapter.py` | text | 6767 | 65b488145a5e7053e279819c663988dbc4080463b0a2c58f446031e4859e09ca | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/wisdom/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/wisdom/api/auth_api.py` | text | 3791 | 77e214a9d20055227a3e33d1eb3d879f8aa02353c4931dc05cc5e5aa8a979b7a | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/wisdom/api/data.py` | text | 39820 | 0783ffb7fef188f47e3ce941dd77680ab8e08751826b4b1faddc0ebc4cbc7c25 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/wisdom/api/funds.py` | text | 2203 | 2f02cfab23f7ae9e54371afe4e7608759b8c814bbfa00238db353b8dfc5f63ba | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/wisdom/api/margin_api.py` | text | 617 | 3090ab2266cf44e9986052e23c3997891dd1c44e0efd5045b5d65032c1a7e3be | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/wisdom/api/order_api.py` | text | 15628 | 5f12c8e24471609cdc681722aad389c085ee236934a991cfbc90ce3dfd19590a | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/wisdom/baseurl.py` | text | 267 | d6d54c9e10170d01650390cce4bf5a7e382cba37f9f691c5d6c3f0c3200b6a29 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/wisdom/database/master_contract_db.py` | text | 22908 | e3f8225efea56e34f56c0ccd00e08f7f5e0c770e37c634fecd5a081dd1605285 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/wisdom/mapping/margin_data.py` | text | 1069 | 11b18a33c5fef9b4f42949a356afbbbaf166af05348580c5e0a3f10d96ab201a | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/wisdom/mapping/order_data.py` | text | 16555 | 057d19f283de82bf3c670e5081f09a1f964bd3dd6b664042550d24a1ba2d0891 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/wisdom/mapping/transform_data.py` | text | 3235 | 2211ad177b64272b526ca539e04edcbbe6f0efe28a0e674ba0cfe72ee0d912ad | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/wisdom/plugin.json` | text | 393 | 9f43b23bd70acf5f6dcbe1758a1738abb5ed0edc8047587871e13b62084c70a5 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/wisdom/streaming/__init__.py` | text | 27 | 02f7ec82b0c66327ff90c755823d0268f3f81fecff409804152ed92775cc8c76 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/wisdom/streaming/wisdom_adapter.py` | text | 51247 | c602c7133813837311cdc02a5c96d417c9e604d71f4b8e0d57d1aa653ea09b7f | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/wisdom/streaming/wisdom_mapping.py` | text | 6426 | 7dd68fb9eee4d19c173796135eb757fa11f49cc476259ee082348ce566b2aa05 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/wisdom/streaming/wisdom_websocket.py` | text | 32857 | bb8a1a7ac43f54549805e2a34abc27c4776cf80a7715a9426e75c11051c93d92 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zebu/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zebu/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zebu/api/auth_api.py` | text | 2295 | 552a059ff054617d3a89155c67648728f114189a21b00fd2e3f6426b9a95635a | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zebu/api/data.py` | text | 28062 | 9f2467246f16617895fb7edb76c12d38181f9cecfb08ae613e6ea340f48afcd4 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zebu/api/funds.py` | text | 2755 | 4ba0f8ec55992272dec4b451ed5580834f8b4b65468df40f9a613b690f39ec06 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zebu/api/margin_api.py` | text | 843 | 6ad81934faa674fb772a51c2d82d3bbc6ec70ef07fd8edaa092332b50fcf162a | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zebu/api/order_api.py` | text | 15415 | b7c7bf335d06c5f51644b75a644721bcafda529bc0a131e8b84f960a88c5e647 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zebu/database/master_contract_db.py` | text | 29495 | 0b27399742d936f2db1958fe5422569e4c452cf3951385ed4fd8699e67750b76 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zebu/mapping/margin_data.py` | text | 1335 | 9456c08689d058abd8ca11b899983e1c6e5fed3ed7e97e3bffd721dc2d1e16b6 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zebu/mapping/order_data.py` | text | 19088 | f193909d6b3e1eb8cf329312311bdd13f33d55918c07331a5f3383d96a14e413 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zebu/mapping/transform_data.py` | text | 6661 | 16faa8a42f00cc6b9949c994e68ff67b383c5b7341d97791d271fe791c295056 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zebu/plugin.json` | text | 360 | 3920cd041548758e3faa8a195aaf751a9f57627f2da8dfacf137fc8ff673eb47 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zebu/streaming/__init__.py` | text | 322 | 12abe94dc40f8dd5e30265ba60c079ea8b9c96db57594983c2184c64f3f77670 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zebu/streaming/zebu_adapter.py` | text | 46332 | ce61e772bc0f1c7cf7b0dab5b6c74038711119045a0288c6fcb2b9c48c371ade | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zebu/streaming/zebu_mapping.py` | text | 2450 | 62cf8827358e3eb8e8e0ef9a11fa8ed490e3f16a7982f9d9728a016794554d32 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zebu/streaming/zebu_order_adapter.py` | text | 11108 | 365f8ed74377b124034befe95f89d0fa9aa242eefcecf0a41fc80f28ba546f58 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zebu/streaming/zebu_websocket.py` | text | 23900 | e48c342356c2b031ff60aecea89fed6f973fc993ae177dd23fccb58cad985902 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zerodha/api/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zerodha/api/auth_api.py` | text | 2450 | 68c1d89b18ec24f68b1f4a464966e5bb90f4e3a3fd712841945b971170c95acc | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zerodha/api/data.py` | text | 28481 | edd5120bd8bd1d074d8aa9281adef4a3409f1e2bbd782884325a9165e6f5f3bd | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zerodha/api/funds.py` | text | 6559 | 35bc5600c52494eecfb552829ba13524eed5e0104256ec72e3fd7c02c1dd117d | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zerodha/api/gtt_api.py` | text | 11405 | f4e74d922321cfda989e4e3d4b9fbb98be4907d223e5bcf490222d8909ac1ca3 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zerodha/api/margin_api.py` | text | 4947 | 2d2121d9564c228e15f00b10007f78d6cb345177a2f994677903d2fedbb245c8 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zerodha/api/order_api.py` | text | 23958 | 2e7bb26efae3d9348db005f1f2cc834b6eb43028c3194d7a10ed94363d227ef5 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zerodha/database/master_contract_db.py` | text | 20633 | 610900ae751a73d2191cbc1be879e8b9f8065d4a5a0615caec6e5129ba966af2 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zerodha/mapping/gtt_data.py` | text | 6040 | 01a38611f8bfa5195af166a8ad26a358785dd1732c75cc1ddb2c66cb4e30538f | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zerodha/mapping/margin_data.py` | text | 13453 | 6c345c68a87d6b76897b0ffbbd90bd131d66124aa4704635228458c86db64ee0 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zerodha/mapping/mcx_contract_size.py` | text | 16911 | 2e00a2b1c1bcfab079e2e3b87aefb5e240b1e7698cde07c1e80168a6b7486307 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zerodha/mapping/order_data.py` | text | 18203 | 38c6dd84dbeb0c9a83485d60b2c0f46ca0d83819b4bb7633534fb2a532c7c6af | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zerodha/mapping/transform_data.py` | text | 3654 | 3cc5d043adb653c27548f44ce9477b3f664a38ef00bc7736459b93bd09c171b7 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zerodha/plugin.json` | text | 417 | 2fe7ebd43bbfb2b9d9be59c3b4dc048e0123f9f2a2a398eda6ad8e8c33d5a202 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zerodha/streaming/__init__.py` | text | 299 | 5b2fcdbecb48b4fd8b4e9e49d27fb54aa2f2489b696331c5ab154e37f42c933d | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zerodha/streaming/zerodha_adapter.py` | text | 36747 | e2f3bbf0b4c10858a1c5eba9256af6715274c0ce1b4f3b295239004eb90f9059 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zerodha/streaming/zerodha_mapping.py` | text | 12147 | bc00a42600096c112fe3dc33a9f7d96f7a36242f7eb6bd56b1c960bc2b28661b | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zerodha/streaming/zerodha_order_adapter.py` | text | 5704 | 434e5638d46e97b152e86b22a2ff8afdf7caffb44c161fc19265fa83e9eb8266 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `broker/zerodha/streaming/zerodha_websocket.py` | text | 35092 | 54d1d1365b8c77909bcdcc82ed0224b73cf77b47da5d6b2758c04b4c26ac2865 | broker adapter | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/BasketOrder.bru` | text | 784 | 6fcddcfe363820062a84561e4c6f20a93bc256d768a3b57777bfac88b8b85231 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/CancelAllOrder.bru` | text | 306 | b32a68f694ecf7391c700b0339e13b455018f0e7ded125d5651ac1c2948f535e | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/CancelGTTOrder.bru` | text | 334 | a17e847530c8d8d8eccb49bdfaad929be8c628dfac822c14aa7988b0355e699d | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/CancelOrder.bru` | text | 337 | 0fb19784edf29a4600ee7c9ed21a7a01cbfd42836ead4fccc298a3cdd3c7ce51 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/Chartink.bru` | text | 596 | 0dda55214a135686bf98a4e56403ff98402d3ab303ade179d5801fba51913c06 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/CloseAllPositions.bru` | text | 308 | d8bcbb993d1ec296c4d13c2e2f16aac2bcf562416b0a816a84f54cea446f0cb6 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/ModifyGTTOrder.bru` | text | 645 | ba73283f499b287935999b4768a4c4aa108d227b8feca3bc82d8501401501f16 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/ModifyOrder.bru` | text | 582 | 2987b1a47a207c51dd24dd6b58ab7b8ea0640b2a87d2bc049631468d81db540e | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/PlaceGTTOrder.bru` | text | 612 | bb2a7b145a34819c66b92ea9e945e35ad0ee0ab6ce9035b042257f36bcabee81 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/PlaceOrder.bru` | text | 528 | 93f26a46058e3789821a3beb0924ea1fb170c9c2ae739a31223203b566f69da4 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/PlaceSmartOrder.bru` | text | 574 | 2a22d3f4c2975804f1c6428c4b6f32ebe7835241f6b00474437af6935daf5489 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/SplitOrder.bru` | text | 479 | 57484e60b1a6a6d29453bac10af4afdb2e717eb60188b9050534ef7459a1d503 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/WEBSOCKET_README.md` | text | 2884 | 2c7572a870c3b303a87697b39b1e0e6d8ec82d36653c8841251fb791306a2978 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/analyzer_status.bru` | text | 195 | 0f6a7031504595889750722b6e2031c44c70a763e667e3b833c5bdacf09fb1b0 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/analyzer_toggle.bru` | text | 223 | f9f986afa5940655ad22e0abacd3fdeb6693f63526828ccbd6babd59be81f3c6 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/charges.bru` | text | 336 | a9befe732357da16338260ceb627e5a4b62d20014b34394bae73da2814a2e0e4 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/chart_get.bru` | text | 210 | e7605ba93636aac1ac5e2106654add224499e9386793dac658a4ca076ad87c3f | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/chart_update.bru` | text | 333 | cd1a9daa7a7c1bf90d8464e235c6e436b3fa28e161d89919d640262b490b57cb | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/collection.bru` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/depth.bru` | text | 303 | ff7ffa8a7e823d1c836afefd530ba413cbb1570a0ff2514a972328892b901f5f | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/discord_notify.bru` | text | 963 | 93acf5e95f40057f3fbb163f04887e323d43c27039ceac1db51b5dc741dae557 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/expiry.bru` | text | 273 | 4126c6a30936735fb4ba640f131be074b3b6cde01ccf93fd3810d70a46b1e361 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/funds.bru` | text | 247 | e1ae712456f2d3b0e64504ba8a3309211e4baa1d3c5b9a1e73482bbb17b011a7 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/gttorderbook.bru` | text | 261 | 1562de166150b22565dfd95c7b03998045bdbc8b3f0ed8b900edda6dff37665e | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/history (DB source).bru` | text | 1683 | 61232dd85b55179ccb24cf6f013b5902dd4138352b45e70d161c3a86e8093b8e | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/history (EOD).bru` | text | 1183 | b43616d7bb166238f87fc7487d54d6ae78146aced9e50bae7755290565ce7355 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/history (intraday).bru` | text | 1079 | 65f510d31770eedc38c065c4eccc9cfcf4305b83a122859c98d78517306fc75e | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/holdings.bru` | text | 253 | ae5b162e9278ea38ff8ed190489a9e7ad40a883b617ebdb12b680469d8f47545 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/instruments.bru` | text | 251 | bafd746cf43cf307b4b12371d42dca666999bfb1a9cb15108693b1e9d9f6d3d8 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/intervals.bru` | text | 261 | fa968afd0194d6f9cf8a037a780192cc45eebd2f52685c66d241e573f0f4c055 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/margin.bru` | text | 502 | c69095718cab20b225ef14e1d4ea2366d3ea920dfbff81e2347ba1f1b936e10a | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/market_holidays.bru` | text | 224 | 432135a861a18752b5fabb1cdaa6d5f10b0bba5d50c933e6892bf9442e2d6350 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/market_timings.bru` | text | 230 | 7e36a3e2a1370ec178e993933340550779368076dfaec205151ed95f348e3655 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/multioptiongreeks.bru` | text | 430 | 7797030070e95f0e43f199be491937d5de6afa393874db03a5995d98dcd61ff8 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/multiquotes.bru` | text | 621 | 460e374b6e0336bf4e32033ed98768da83ce36d5bc8ab2da4c8d559d9b7e19fa | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/openposition.bru` | text | 376 | 7f456adf473a8cd42e224bff163e113b32603b08627e4e22a65f9e2798088791 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/optionchain.bru` | text | 346 | 8a7093837261e1a5027fa497b813546c56f618d31380198ee32e116d02945190 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/optiongreeks.bru` | text | 264 | cd13bcc1582ff2655e82460389ae315d3c4f0930709a52624232357373cd6328 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/optionsmultiorder.bru` | text | 1390 | 7cba2072398306dd5fcb941e4c96cf28ca2b1d373248213020a2541cae0d7d35 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/optionsorder.bru` | text | 505 | 8f28bc9df668419c99ac39b5b7fd8b0033df9e4f3f87bc368b17fbfb030c3372 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/optionsymbol.bru` | text | 345 | 2674d0358b394a269bb40da5a566d2d965aebd76fd3f82a70fbb3f47e3640720 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/orderbook.bru` | text | 255 | e111f31ab8cc7788c006e95e61a56f479d7b7bbd210af45d74f2c1d18b196ead | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/orderstatus.bru` | text | 254 | 110c192a697566c161ea006199dde43a1e2b04a1d016a8df73d479f592552e99 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/ping.bru` | text | 181 | ba5d96fa091257def2784095bc7bb3da4bf2ffb7a9429e3ccd861473feae8cce | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/positionbook.bru` | text | 261 | 7f54f6703bdaf54646a787ad3cc881833b91636cfad1e5d8468d9ed4d5e7568f | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/quotes.bru` | text | 302 | 9cb23fcc911c3cad22f73ad62363d8a9d78a8709ec28ac4e85ec5eab8669a0a9 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/search.bru` | text | 245 | 19d3ea07c73a91722396f592551f6bad3ac488c8289060ae84c3947208e6f442 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/slack_notify.bru` | text | 985 | e1caa7c7cc8246cdad3aad56f5c6c0335272478280b75dd22e7e04cfebc5651e | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/symbol.bru` | text | 236 | 89a538d25fc75f97a5f1516b003deae72cae2a9783f54ad3750109ea41b7fbf9 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/syntheticfuture.bru` | text | 299 | b936404ed1879bce97f93a746a1cac4a1de4fcfc1f247e9a5573ab3c17fa136d | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/telegram.bru` | text | 320 | 283cfc1df5167ac22fe8ac1c27783b6b133a869460ed1199e41e5e544981ed3e | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/ticker.bru` | text | 206 | 993d9e5f84283138f8ea4291521fe90ba5009a79d7e0a8412b69a9bb2269d30d | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/tradebook.bru` | text | 255 | a7dba29350e6fe6e74cb3ff0a498ba4ff215d3014d766ceac2ff47195a3c1a8d | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/whatsapp_notify.bru` | text | 1431 | 51fda1d79d8ce3d8516f4bab3a9a623b87da55eb761fc43b0376c3742eb1a390 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/ws_authenticate.bru` | text | 527 | f9febe9eb34fd0354283ae587317ada2b028c58c6a901a2cc79c7341a8973f31 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/ws_get_broker_info.bru` | text | 586 | e94ed9f7e5f3b06180a42e421606f5b0c7775afb71337a606767b7e017155967 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/ws_get_supported_brokers.bru` | text | 674 | 47ab2df197df550737c2e6caa85faacdcb23454726272a579eaaf4698348e9ce | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/ws_ping.bru` | text | 604 | 640ffd4ff764f189c0fe03353e3c676f519e4e3077d9d68d170ac21e17767e84 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/ws_subscribe_depth_20.bru` | text | 762 | da47da15f529272acf1d71cafb154e655022ce9d9c1f31f2825d341e553d74ed | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/ws_subscribe_depth_30.bru` | text | 766 | 22617dc1ff9724a57eed64223e4443575fe428826c6556c733273b49bfa4e90b | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/ws_subscribe_depth_5.bru` | text | 815 | d46a99a96254dd87a66d1d5e04b1f281802b9e1c40bbf4149347a69d0607246a | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/ws_subscribe_depth_50.bru` | text | 805 | e40720a8758087cb483f065c8d371a1f376f8aff09083ada8266c357f0f2e2eb | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/ws_subscribe_ltp.bru` | text | 647 | 310c35614977bf578f6f6952f6feb4e0a077251e664fa38f3b186ab033a9555a | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/ws_subscribe_multiple.bru` | text | 918 | 3fdddbfa5c96ce65d3dee257026cf736c76556f5263eefb41390de99d9035cdd | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/ws_subscribe_quote.bru` | text | 829 | e691a55626366bce0e32568fdd046e5394d13808ab02941e0dfa0bd1d5b1f43b | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/ws_unsubscribe_all.bru` | text | 482 | 55faf800526e7bbf8e7063be68712b1e39c2546ee501a5acd6303369bb355e16 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/ws_unsubscribe_depth.bru` | text | 559 | 4ec277a7d8e9ce6f020ea7dcf7f2b7a9ac1d55f74ce2b9e940474c7b91c6845b | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/ws_unsubscribe_depth_50.bru` | text | 710 | 1bad8bd0076c4652909c32140f3d660e3eadb1048f158a8ee05e73835e14cb89 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/ws_unsubscribe_ltp.bru` | text | 556 | ccb509c9fe8070654002e8923e74f8ebcfb2d984fe1b0e5509a786c3742a3c96 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/IN_stock/ws_unsubscribe_quote.bru` | text | 558 | d0360e868b910e9f09f03f95d21edd2dee80708192e247282e505a9548cdf08c | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/bruno.json` | text | 124 | f73de5e115d5f1d4163d0ecd3d8415baa55fd915bc45975e2d14df608bd9b431 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/BasketOrder.bru` | text | 950 | dc0bdf8a9db6f482284cd695bb77c10039dbe45a48af128b996f918d87f9b563 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/CancelAllOrder.bru` | text | 238 | 76badd231a5ca375f050f521b8abbac4e275e8e53e530c488c45ff9b99ddf739 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/CancelOrder.bru` | text | 263 | ea8a2e9e08b36e136a4c3ffa18111760016a329d17891c85d94b601c240cfe19 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/CloseAllPositions.bru` | text | 240 | 32a8728c509ca29098dfe8f7cb529f4fb317b20f40a92bc7cd86f0e5f05aa6a2 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/ModifyOrder.bru` | text | 513 | d40659681d58617f6b1c8d6026b13099cc93e84eacfcffc78219cfedb52754b9 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/PlaceOrder.bru` | text | 477 | e9422566a5e16b7134966f2557e3cf268780faf56d33910c9aa01d12358928f9 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/PlaceSmartOrder.bru` | text | 516 | 9e02dade544f33ff1a9b7d8501822824570e2c0a41f2780fc540ca6658ba3c06 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/SplitOrder.bru` | text | 468 | cc8301049bde28e91d3e2486a016b87684852c6e5f3cede08657ec9517308f24 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/charges.bru` | text | 341 | 59ad52641c1418c4164f4016b3bc3feb39973e68a9767891f7ef4b156aa40bdb | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/depth.bru` | text | 242 | 618550d77c80b3b221b887bc29b3f03df50857ffa09dd49f22c3eb9819f23179 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/expiry.bru` | text | 274 | 3f8afd28dd6b1552e92824820d57aa811dec9666a52247083557d90f9cffa76a | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/funds.bru` | text | 183 | 4048a384d1fe3dd565516fdc3fb82c99a36bb847f82e0eb8d508bfd62718df6e | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/history (EOD).bru` | text | 344 | 27fee13c03ca67b63e74ea827c66d3a4b4214217e6fb56f637feedaa52b74130 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/history (intraday).bru` | text | 350 | e9004ddba4faf289f5b9e3a2e2e78fda790e4c83eaf8f9f74a96665e28eb4313 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/instruments.bru` | text | 248 | bf0b75afc2150d328329457f3ae24db01ae61510cc7c684036158d9641caa269 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/intervals.bru` | text | 191 | bd55bb51bcc41d9e8ffffd3349241ee4c29bbe99ae94d4707dfb8afc2cfd8ebb | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/margin.bru` | text | 482 | 3fac1d377ff231bf40b2e1adb5a7287de21c75679367ae977d0e3dcef0c464f3 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/multioptiongreeks.bru` | text | 430 | 40568379fe816c3c6bf0df887f0007b62b49db29e76d067654487d7ddc196018 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/multiquotes.bru` | text | 491 | 0b078ac267e6b03b6887fe747a18e783632c9a9f035d8781914440d873b7442c | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/openposition.bru` | text | 320 | a7a1d7f1c6c042ab089879275e28def9fc9cbf732b7472f0a202d2c24c174007 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/optionchain.bru` | text | 340 | 24ee3229006e0be3db067e0aba963f5d25bc4efbda4b822ef3a20ce36ad3c2d5 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/optiongreeks.bru` | text | 264 | c8489d6b66806fe02e23fe849590e20d35e1d3f37e096fb5491659963d50898e | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/optionsmultiorder.bru` | text | 851 | bbc07c22ce553c96e731841a04b2d2a39b870e13f437dfcac9b821b90acb3894 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/optionsorder.bru` | text | 501 | 76a9adbc34baa136e363a5f26466df89a7068590c18e7966304d91167c85afd0 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/optionsymbol.bru` | text | 339 | 15cbd6d477292d631ae626198c7a6a6248003fa9b1d601dd50676d75d806a8ab | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/orderbook.bru` | text | 191 | c5d8244cc06ea40691f85bf221a399fc4335f49b26cfb938c41ac7607a76b7f8 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/orderstatus.bru` | text | 264 | 7f5f27da50f46bb459cc063d8d2bb7f65ccbb1101c7d6cf2144e155e2eb5b426 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/positionbook.bru` | text | 197 | bea7a8e83a4fa4406287231535cbab9510f4b521f10cc74416d7e5d9d1d42f73 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/quotes.bru` | text | 243 | 2591323d5fa4c68ff76cd8fc2773e9eb83dcc786abc6841db2182bf61d4ccf48 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/search.bru` | text | 237 | 81954cba959f800f74c740db56bc1ab4ca1a38234cbc60117a05cf44d8880552 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/symbol.bru` | text | 244 | 3c7570f87314237a393f5e80fc9689146d7c5bf9dc5a24867aeb6317cba2c5fe | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/ticker.bru` | text | 214 | fbe695e5df20f85ca0744ab209a16502b0426f76aa793a2ce99bf72f9ffc0ad7 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/tradebook.bru` | text | 191 | ebc762e3223e0ed629d8d68f34cdc1f6b72109829cc6e5e40b453777dabdf854 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/ws_authenticate.bru` | text | 528 | f16dc1b145050c5f8f254dfbab15d63e0f1379a14063f96ae7e8eb0b7ea59875 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/ws_get_broker_info.bru` | text | 586 | 14c1d28988c7d2d0e8bad6f3632bdf336f9cde020b4d90a834e6e4ce9d530b94 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/ws_get_supported_brokers.bru` | text | 599 | 4e7ac550cd4335282f9d855e18a21b93d7e0b7958eda748c68f0a403c0147517 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/ws_ping.bru` | text | 604 | 587464a8fe050c269827d50550833bf468066df2589768f034e3040cc73a4f87 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/ws_subscribe_depth_20.bru` | text | 767 | fae69db6f6f69d9d128bf8f374ec91cc38bca7db7276326f6199b94f4797550e | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/ws_subscribe_depth_30.bru` | text | 771 | 1b020ae86fb46e99eacf653f3f57c8155de07845a7401c5ab35226374b8e1ef5 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/ws_subscribe_depth_5.bru` | text | 824 | e9dfec1a2eb29321b4738d0c4106c1245556bebadab3caa51260b3fb1d7d2d63 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/ws_subscribe_depth_50.bru` | text | 810 | cda922f8574e81d402f68c132863ba5e08814ed542c816367687d3042ed9c174 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/ws_subscribe_ltp.bru` | text | 656 | dcd9d665b9da9f0627e7c8522b61007f2556355142374c0147e16603d943447e | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/ws_subscribe_multiple.bru` | text | 759 | c8a905dc287bff449a9e08531da547d7e379835025296733cb1f229fcd587ae3 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/ws_subscribe_quote.bru` | text | 838 | 5ea84d399904c4b41ffee4b10a9fcfa4332187e5831d2b3ec52a97224d2b9e60 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/ws_unsubscribe_all.bru` | text | 482 | c7725fdeeedaf23c40de7c11283a23fcfb7d43763a487a94fc0a66f464cca1a7 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/ws_unsubscribe_depth.bru` | text | 567 | 3753be2d2b37497ea423492fee56797aefb63cbeb213569c2ef757409e7d7630 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/ws_unsubscribe_depth_50.bru` | text | 718 | a00b50478f13390cb1947e0c2bf8542de465bfeacd1025a824e32ae858c70703 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/ws_unsubscribe_ltp.bru` | text | 565 | 9c969437de0e40aa5cf5e573982deac4f43d475861adb0dd28e6132dfcfee6c7 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo/crypto/ws_unsubscribe_quote.bru` | text | 566 | 35f333bbd4f8393239a4d81cb449de8aeed07328328f85ecee473b57ba5899f3 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/openalgo_bruno.json` | text | 17985 | d14a923de797dd3c2f57066486c2b775e0b646b7c579de0c673834dde8776dae | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/postman/openalgo.postman_collection.json` | text | 21465 | 31866e768a1dd9b8c301e349b71b7f1e270dff9210738904db9dabd362870ef4 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `collections/postman/openalgo.postman_environment.json` | text | 574 | 11f99c2f1ce0247826dc38f4fa8b2fcdfa3cee1a4d275799df4a6358b42265d3 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `cors.py` | text | 2518 | 6b4d8bec13aced1b2f678d4958f3ae1a2019422f639ef62e12a010191158eefc | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `csp.py` | text | 8730 | f17d171092dd485a0ec402203035ea7687b11e341577903ad662f8c8762e6fa2 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `data/qtyfreeze.csv` | text | 7310 | 830c40448e6ffac7a42d3cbea3831981c16bcd9a06e26fa1e479e58564069b42 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/__init__.py` | text | 9173 | 33a9aa5b1406da98b9ab9e55121960b0c423d00380c56fc76776227d4465d09c | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/action_center_db.py` | text | 15407 | 0c1ccd90567c4620d5a5b7ad2aed63a8df2725ac5c5f09d8e9130ea36d3b7cdd | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/agent_db.py` | text | 67094 | e3e2faf52198239cf29ecf692f82cce3b1e9c35e7054c8a8860ff93c8da4d02b | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/alert_channels_db.py` | text | 6439 | 5f6bd9e993d3ce046eefb83ac18b3bd571b1542bd5eea61f2a129abb84b95337 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/alert_log_db.py` | text | 12141 | a327526f35c169af83824b778d1f16fdfe3fd1cfa3b940112f777ce1f9fc3d2c | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/analyzer_db.py` | text | 3951 | aa298a7cd158601d526afc05881b15f2717913aa24c51d34cfcd21ae6b34597b | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/apilog_db.py` | text | 3885 | d4958753ad15fa93efc2b7fc2fbbef10a36abeaa7bf3eea8fef172bc349249e4 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/apscheduler_jobstore_db.py` | text | 5543 | 16ec3bf045af55c0f2634ec13806ef96b376df3d3df73fdd8d0626c3f9989e52 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/auth_db.py` | text | 74040 | a890543ef5a8d3b0748d45fa67d05e9b1e715eede7e20e6b6c3ee5fa82a631eb | database/migration | INDIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `database/broker_keys_db.py` | text | 13864 | 2d1fa946cc3bd91824a6c67a9eb5e2b5a649ff4cf5786572e3a0685d9ce70c89 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/cache_invalidation.py` | text | 4420 | 8d1ad4b31218c58475bfb38401b186052e8d3f44d57233e72c738d1866eb5c59 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/cache_restoration.py` | text | 9329 | e78b64516934ea0acc339945d3520779293897f452b04fb0ecc21e80a657d99a | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/chart_prefs_db.py` | text | 3865 | adca1e4ed164f59788bda99f37427509728797cfd0b410704932120683b806d2 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/chartink_db.py` | text | 8504 | fcc31945a486b94df22963951f40e462cdf307eba0b4c1fb99b54df95f59b4a0 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/db_init_helper.py` | text | 4540 | 9a0738dd88e5c012d696a0adfbc2f4e8043b046f98b7fd69c72000f65b4aca13 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/engine_factory.py` | text | 2517 | a979f6eb2de04ebd1e9b0f1c01eb9e5b6a88341cc35c86e27b91bb95451425c2 | database/migration | INDIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `database/flow_db.py` | text | 24511 | 44a5354512d90916dd49f3b7853a52f2c8a2b98970073eb44c7ddaac119455e6 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/health_db.py` | text | 19725 | 63487808f519ed96f0d75022bfaa62b98511578b25d808f3080c1d72a892deb3 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/historify_db.py` | text | 137949 | 4b174f1941b64231627582646c022ce672158f56b3abe2499d002bb10350cf9e | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/latency_db.py` | text | 18881 | 34880d6764ff685db018cc83ab89242d433c5bc6d805781f370a25102d3d60a6 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/latency_groups.py` | text | 11937 | 6857aadbcde49612f2784361d55d90445a715cef4b29f3099bc2ed81be7d915c | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/leverage_db.py` | text | 3356 | 877c4e3dbf3769cba62afed05b0d731d79e3e9d3826101e97ebe0c08126f6b40 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/market_calendar_db.py` | text | 68341 | 4f0a327a5dca82fef62e71c6d8794fd1659ff0a353123c7d015ff69fcd7df0ef | database/migration | INDIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `database/master_contract_cache_hook.py` | text | 8407 | 270c4eae03bfda22d06d38475feefba7e1c0a9f9dfea844fec9da38dfabfdbb8 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/master_contract_status_db.py` | text | 12112 | bdea2bffbf7f7af2aa43c1f703b1a17c8a56a770658d76f23d2bb636282281cb | database/migration | INDIRECT | NOT_REVIEWED | PARTIAL: session lifecycle lines via grep |
| `database/nifty_algo_db.py` | text | 229131 | 8a2ff238b93432c1f900262f788075514c62783ba9af81854711b7e9b10ed15d | database/migration | DIRECT | NOT_REVIEWED | PARTIAL: lines 1-3953 and 5095-5260 read; 3953-5095 (recordings, experiments, opportunities, report store) located by grep only |
| `database/nifty_notification_ops.py` | text | 20025 | c1b1e22085d9a45d43340e4777f9e0ea74d8f57208a5c5bfd6e41e047cc73703 | database/migration | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `database/nifty_notifications.py` | text | 27390 | f60c24057c8cb285cc524ecb6ab2d82566997a6023b63ba2dad1e35378eb9209 | database/migration | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `database/nifty_replay_storage.py` | text | 17100 | 38f197881cf0b8e855894ede12a39201e9cf633f145eb595b081db38dca38ec0 | database/migration | DIRECT | NOT_REVIEWED | PARTIAL: lines 200-280 read |
| `database/nifty_research_analytics.py` | text | 26228 | 68a2737b33fef724d2fdca5f12b02002eb08d1c65f8b90e158b0ec59a610b90d | database/migration | DIRECT | NOT_REVIEWED | PARTIAL: lines 385-535 read |
| `database/oauth_db.py` | text | 10182 | 19f70abb1ccdaf5293c4bdbdb72aa64eabb58bbdc8417a0cb6b410c16ec66262 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/qty_freeze_db.py` | text | 10965 | 281e253988cca263e5a4d726960d6445c8144df17a1de00b8af0d81abbf03c36 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/sandbox_db.py` | text | 35708 | 3f16d8b9c0dcf756778632d537299ca992ac11f6afd7dcd81bfdd408c1aa5d2d | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/scalping_db.py` | text | 15321 | ca96900c7dcbed28b1adf8c5c64540a694d43641469aaf4e4d202dd75a42581d | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/settings_db.py` | text | 12002 | 429681ebb90d6ecd5dd5fef44a1df50c0f62ee41388ac6e8aee79d67130ca918 | database/migration | INDIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `database/strategy_book_db.py` | text | 25067 | ff2fcf236e95aa791afaca075ea553a973745e7bac9a1fc7867ff030b2b2555c | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/strategy_module_db.py` | text | 101396 | 4b6500ccb2dbb9d770dea15d0f398b2c8db93e77fa22977d12f178217ae26005 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/strategy_portfolio_db.py` | text | 5998 | 5b1703f8c5833f7d3fc546f10923d0c5c8d0be78cc84b4ec9953a15eb25c1625 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/symbol.py` | text | 18452 | c849f5d22f403db9eec2dbbafa83f2d55704e33652b90f02e96bf4728ba7a022 | database/migration | INDIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `database/telegram_db.py` | text | 30995 | f55f06c8d79a987f1dd6919d62dfe879225d2f894d949b1198ed88f952169497 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/token_db.py` | text | 2049 | b45f7910000e127154bde12ff7a664436d4df531964f2ba66f57976e0368257e | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/token_db_backup.py` | text | 5772 | 8d335947a7b6f19baacb3015f116f618f16ccd37740145844cf27e21db5a9159 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/token_db_enhanced.py` | text | 55560 | 25ce1cda5d601b491ad9810a61fe6d920900acd5deb5dffa52b040a8732f2d9c | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/traffic_db.py` | text | 24270 | 69f87bf98ba0f4f79970e2abc53cef6542c6abb7d79be32c8c2e012821206301 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/tv_search.py` | text | 667 | 26c0770b37765a0fad44c24662b3271dbaffc8d463501a6394b7792edcf83064 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/user_db.py` | text | 16704 | 7877873308adc4dd4a6c9400422bbcbf0ce6b76591e69180960537241be3e527 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/watchlist_db.py` | text | 12812 | ad67165a4c2ab439847634e386f9008f64f0211a3569327622ec42149baf94d0 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `database/whatsapp_db.py` | text | 36193 | 0591f962acc73b4247db228526d71369c61e3c34aa5cf8bf98db22792bff577e | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `db/readme.txt` | text | 36 | e5a0948a5cf21ebcdc5b25e03b74d624f24169949240b5e90914977231724034 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docker-build.bat` | text | 4699 | 068f215db98694dfaa012a6061ca3af3b6e16b357d4c19cab3e9bd63d19b20ed | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docker-build.sh` | text | 15199 | 21d83110c8313557941f1ce31d34b585bef88cf43fc46292a99355f54da7aba7 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docker-compose.yaml` | text | 2541 | d473b175c40d9a0df737d50e82e0eed325e7e35275eea3c060519ffc68f9d641 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/CHANGELOG.md` | text | 195701 | 4b261a7824b850e04e4a9c60e89d4ff76a67578727e7d06a3694358de95e30f9 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/HEALTH_MONITORING_IMPLEMENTATION.md` | text | 5851 | 87428f6b001893dff91338e447bb9e130c60957aa0b5e2076ee92798e036b0e7 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/HEALTH_MONITOR_REACT_FRONTEND.md` | text | 3803 | 13ce2d1bcaf23f202bf8b048a63000b6481a58493460772727f78f72832ffd4e | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/INDEX.md` | text | 8370 | 7e98a6f48a3aad5b8931cf0d74ded3383c998449491d93f51a7c5d7c5ce8d38b | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/alerts.md` | text | 8556 | 79d59b4d37de250cf757004c00449b1aee9d37edc76ebebf42453f9b18cdaa12 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/README.md` | text | 13830 | 0919393448f4608d603c6afb9f54a7f8078789b41bad018f3d2dd212741b2de2 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/account-services/charges.md` | text | 14657 | 7c97daddeaaf499f222df068d51532358f02c58e1e5d348052ec529f2390fb94 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/account-services/funds.md` | text | 2368 | b62d85a2a55bddde5d8bb5a4f78920d95dd8ca0320c5ec58732c542ea20fbf4e | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/account-services/holdings.md` | text | 3274 | 961fd4240bf394cd37f3dc59e2e3fd63a6020e007941c8267dcc1a8b9e0709e9 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/account-services/margin.md` | text | 4138 | 2c5260fb481f03e9b7759ffe376dfcec54459421c050c658c2e777c29a226d9c | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/account-services/orderbook.md` | text | 3659 | 910a7ab296fbd6bb6c05bbf1d29672ef0e5b9f809bf67a16952cf4a572ca1bff | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/account-services/positionbook.md` | text | 4842 | 1c189f3b86971f8c6d769ae86fd60b2a9141b8dc48272593dd0a098c144d92e3 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/account-services/tradebook.md` | text | 3003 | 0dcd8ff571c706ce28bb5bcec9a1b08ca27ba5aa5b06e8470548e89267480942 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/analytics-services/portfolio.md` | text | 5223 | a12418290f173391a686b82fefb1159fb6cfe3607f1403317d7cc6ed77a0dce3 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/analytics-services/sectorrotation.md` | text | 3262 | 77236c8cc2211d4b9fedd68e4010b308976f8d13ceb9ee351f5fbf011e98e716 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/analytics-services/sip.md` | text | 3680 | 6447e18620f62c9c27648fb093f2bf2911e98c5c7409ed7dbbe91951f6cc5a88 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/analyzer-services/analyzerstatus.md` | text | 2388 | 691ccede8d8f35dbc572080e8960ef04f63070dc6e843dd31fed148850ae75c3 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/analyzer-services/analyzertoggle.md` | text | 2975 | 9ff1ef1d05554bce7b6ba38ae6ea0ce88c2c1bba2bb51a8edb8af1189b0f438b | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/analyzer-services/pnlsymbols.md` | text | 972 | b1dad5467fb32327efeb493b705ad06d73d09fbd832fa4a31928ab4219691c24 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/chart-services/chart.md` | text | 995 | 8b572683785bc1c263c7223c8b599e4815fd7070fb6db5dafc741a8a072d67f3 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/discord-services/README.md` | text | 2102 | 209a1472426d6959ff0b232e9e10dc19f3a3877271b30987cc28eeee2a0f49e4 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/discord-services/notify.md` | text | 2682 | a18464f6dfcaba5d2574ac5fab0bbb627021c2e82a58051d9b80255557a03740 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/market-calendar/holidays.md` | text | 3766 | 1a43f43e503483dff7ac1c9108a73a250ea9be780e48cffeb572b6ed80db2589 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/market-calendar/timings.md` | text | 3338 | a33a9435ff8b176c97ff27f75c54eefd82be5e8e8f309149076cf99a1a8465f8 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/market-data/depth.md` | text | 4576 | 6b518d96322da6ae07f7c76898081a075c4b5e128cf7b1f1f216a195ce0053b1 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/market-data/history.md` | text | 3505 | c8ee27b25d4ae6733df3eaaa38e1747e44bdce88cbf9779f7db2a6336eda9c8f | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/market-data/intervals.md` | text | 2243 | 6d2ad355b48803745e404a6e7a6c745a07381fca83eb9790f01d4d39ba564d4a | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/market-data/multiquotes.md` | text | 3878 | e7dcf7d5657c9bc044f0a51775f09e816815ac326e0131507c026ecafd524add | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/market-data/quotes.md` | text | 3040 | 9f744ded8f1f91b881b39775650a56f389844f28cecfca9907a442474ecca817 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/market-data/ticker.md` | text | 1592 | 8c7032fe9d643aba063936bf196db308ac028e8ccd05a79e44703a9e8fc5066d | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/options-services/multioptiongreeks.md` | text | 1909 | 9e0250f2b8ecd339e02b7d747146c5a9108cbf4234d7f94129c0bd21e854e8b3 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/options-services/optionchain.md` | text | 10833 | 0265ecc2c94d6084b2c91777bff36127846063bd19647a8c3adbb87c267408c1 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/options-services/optiongreeks.md` | text | 4579 | 853882e4518aa4528fc1bba259f83c52c650a117437f8bbabd1c81cb24a4eb11 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/options-services/optionsymbol.md` | text | 3934 | 7a7756330a4bcd532ce860b140b8e1899f6686f15ace04aae9e596f744515faf | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/options-services/syntheticfuture.md` | text | 3109 | ce2f45faca42791280dfd29c690e5a7aff5a966ca64eb1e18f3f8f8ab969b8f8 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/order-information/openposition.md` | text | 2871 | b6d433ca6b3219be1178d39bf71edc53f9ec14d051abad3acfcd5e80319a2b1f | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/order-information/orderstatus.md` | text | 2832 | e198881eabd7d848d6570e13f4d82c4a0710eb166efe594221b7e8ffeb9ef1c7 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/order-management/basketorder.md` | text | 5731 | 258e9bcfc2fa9ffd6e5720a07a3c9eb0e3661050494998f70efb4e8240c06b9a | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/order-management/cancelallorder.md` | text | 3252 | 85634e8c481f9a263e093b8b747d1caac361eb73d57226534b23d6c6dad81d3a | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/order-management/cancelgttorder.md` | text | 3370 | 6f1d2b3c72646ad488313569cd72f7c6cc33bf3fa1a7dab4f2ec551df96921b6 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/order-management/cancelorder.md` | text | 2043 | f6bd90c2333e5a7a70d9a5956337965fbe2ee57a5dd397a59aeacb65b2553364 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/order-management/closeposition.md` | text | 3214 | 0449f525f8d45648fb625ce5990a0d6506fcd8083eb262e26c8906bd7bb73ba9 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/order-management/gttorderbook.md` | text | 6757 | a423bd827ddf25fa174589c976a6259ac22e708524e4acfb0733fd1ed7519282 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/order-management/modifygttorder.md` | text | 9540 | 62741188b9c0d80fa6640fc5a7b39bbc39f3e67e4b5f104e58f4aa609372a806 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/order-management/modifyorder.md` | text | 3797 | 2a5e8ae7a0e1b1fb7925cc0afa3d201be44bda62b6945a99b6e00f5ca31a38f2 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/order-management/optionsmultiorder.md` | text | 6765 | 2dee648b8c22a9957399c81d559662103d3aee883756d19326fc6b6ddc6b0569 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/order-management/optionsorder.md` | text | 5268 | 0311b9a12ebf6e24dae9ad3bee47a61dbf7490ca36552d7d2a9e5dc21b9ee3ee | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/order-management/placegttorder.md` | text | 14489 | cd59f4add6a82b62767ff7be93f110ba12bf9b264d6e01e694a4a1e7924fc923 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/order-management/placeorder.md` | text | 4689 | bd6c38408f74a7d2ed847508fd729843aff437be073e3c70f96e44afff8cb5fe | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/order-management/placesmartorder.md` | text | 4669 | 49da7a9ab22ed61357e4ebfae721df2cdd1fb7540911042cd7ed497436e408ae | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/order-management/splitorder.md` | text | 5000 | cca53c96fb289a1e98b8bb5e889778e54cdac75900831f0cec8d0238e6a75ea6 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/rate-limiting.md` | text | 11597 | 0d5e16414809b97b91e86c13449d12ea270bc3cf40999801381a7c3ca4d51c7a | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/slack-services/README.md` | text | 1899 | 25ba003351b5b8ea4e45a7d44ce04f100d0a7ad28f45d6b58531d46e0bce865e | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/slack-services/notify.md` | text | 2686 | 415b6019f7c09b2f2a7320631a60c4950bd40c3a278ba1f733b3dff5087b2ca6 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/strategy-services/README.md` | text | 13747 | 572fda31d492e59b9d2aeda889a5b0b00e449841f014ab9f071b91859f14a19a | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/strategy-services/close_all.md` | text | 4488 | 640ffb6cb405353fc0ed14e24c2825cd61669ccbbb8cfb02991f7281471c4d4b | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/strategy-services/close_leg.md` | text | 5705 | 9ac0488b72a4ced5e05ed0e330905afa76113a8ad464e39c37e3493db8c35c9f | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/strategy-services/events.md` | text | 9183 | 5485c82ae4286cc15240eadee7513beb039ccf06086b07103322e38723040025 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/strategy-services/list.md` | text | 7550 | b059b07f7b2e176985949530d78ca7f41806d0889c8d17b0f022ffee3a027770 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/strategy-services/orders.md` | text | 6870 | 774c22e5027e1a9dffe18938dcec3043225465fb614588f0399fb1dc0f1d9e39 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/strategy-services/runs.md` | text | 6678 | 9a101ab5613f9e4a550ae88c450e579235749158147e1a3d35145325af38202c | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/strategy-services/start.md` | text | 7599 | 0a986fc884d7ceecfb5046c723f2032b6ee254f8a6be4ff561ac74619cf2edd2 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/strategy-services/status.md` | text | 7663 | 01b7e70f2bd9c95a35449932c3bc3022be532b1a06cce1114c457c3b7cf120ec | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/strategy-services/stop.md` | text | 6418 | ad333e6119d8040bfbd5135e200a2a4837bfbb97cf1e88f0c6477b760413e0ba | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/strategy-services/webhook.md` | text | 19803 | 04afc08dfe7360e956e69826d3356c624fc4ed5fb4724bbc589ad35bb8bed843 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/symbol-services/expiry.md` | text | 2607 | 3d727a83fd9568bffea61f97e0a7a2b04f84cbec314650002482ac9ced0a0c56 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/symbol-services/instruments.md` | text | 1921 | 1a5ec5e78dcea479e7e81292078224ecc5b75a4da80b400c4a74acf44ff646a1 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/symbol-services/search.md` | text | 3492 | 501ff03bfc9bdd8314cef7ca085f788735ed51f225ba28fd07a38f151b927f3d | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/symbol-services/symbol.md` | text | 3677 | 72e1c938866297b5985b28d47329eadd45ade1b0a47b09a5a09985ac570266c8 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/telegram-services/README.md` | text | 2859 | 2449bd91ff68e213d20e3ae09313edd446af49ab9e23cce5ae6ecbab8262a054 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/utility-services/ping.md` | text | 577 | 9ae31e6234b4ecdb889755dc0dbdd4ec9190c56cec03365eebceae70abab942b | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/websocket-streaming/depth.md` | text | 5937 | 57cb37908c64a87433cb19f53a9c33aa1e9afabde3c5de9c21c02a4db9ac6584 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/websocket-streaming/ltp.md` | text | 3643 | 8e5dbb64818dba76b88b3f35f42400b2320a76b6593be8cd3dc58c823220cdce | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/websocket-streaming/order-updates.md` | text | 4554 | f335dec538be5752f0967e7ca4e650d6239042c89b9e6f3925c01e23abfdcce3 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/websocket-streaming/quote.md` | text | 4557 | 1765bca8c34ea3d66ed59c31860d51369a50d6d9ea08cd1ba31da343a425f6cd | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/whatsapp-services/README.md` | text | 4984 | 07750638d4d084f2bc532ada13cc98ad3b72e97237d4279cbfff2c06d6de7d4e | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/api/whatsapp-services/notify.md` | text | 5173 | 329cb0db42bce3e512f85bc71854e0d8b89b6a143de273e3d9c81d79f219933f | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/architecture-diagram.png` | binary | 121569 | 5ec44cb31c1c5a9f754399038a9774948220414e5b5f0d3baf2230af9459c55a | documentation | NONE_IDENTIFIED | NOT_REVIEWED | binary: type, size and hash recorded automatically; content not examined |
| `docs/audit/2026-11-06-documentation-gap-audit.md` | text | 24543 | 93e9d7e1fe6d6b4608d4f45828e9e3c19d1a5eecb755767284318843a33ab0b2 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/audit/CACHE_AUDIT.md` | text | 32962 | c1cd417f1e55b5af27058b0a6d965e6cdae9078c83b3ca700619e02910766f5f | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/audit/DEEP_SECURITY_AUDIT_REPORT.md` | text | 22334 | 245b4c3ed50f380ddeda1f40a8fcb081f9d64fa52111cd02dcee8f544c4de0ac | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/audit/PUBLIC_IP_SECURITY_AUDIT_2026-04.md` | text | 22336 | a6bd4e551101594bb8107628d0a8cd520fc9cdde8f12ac1d484fb1e7d200bf7c | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/audit/README.md` | text | 9883 | 567341404e604a70b74c400ee58b94e2efa51e4a131e30ae011877f2aebb0151 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/audit/api-security.md` | text | 7645 | 0d84d27078f0ba19925a8b791f73c4fdfc7b08cfb1cc43c704fa18f4a5fd598f | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/audit/authentication.md` | text | 5673 | 757899461ba40d24373d6f012b43f90c58e1b2321a0e28e1709e78a65714357f | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/audit/broker-exchange-separation-audit.md` | text | 37576 | 2e388a67d2204e3663f57cd9a75c4f073f3049f8957ebb7ba3d396e24bf67e8a | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/audit/ci-cd-audit.md` | text | 9053 | 80c2884f27d7af3001f53ce614a6348d815bd7760b83d87eb371ff060854657d | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/audit/dependencies.md` | text | 5395 | eee2f70acaafcaa4c3b11f289311dead540e84e0d70207545dd2785b456f865c | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/audit/file-operations.md` | text | 5475 | 08d235c76186ef7687a6c2f09723fbdb7b1586d7a647a8b63ed237197b0b3659 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/audit/latency-http-pooling.md` | text | 6997 | 6ed6df3488af0b48683b2e042f7b301b2437b22f72e817a7d47212f6c257a34d | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/audit/parallel-ci.md` | text | 6287 | a0c0f9f0c958ff795340b8a8e022dfde64f29e43c7c3fec73b97e9f966f5a6ff | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/audit/qa_audit/broker/broker-qa-audit-checklist.md` | text | 70482 | e0a56cad606a87f3fc1b242d311c2406e5d04b810f35ededbb853c9fa9ebaf03 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/audit/qa_audit/broker/qa_common.py` | text | 27396 | f1c2f6ef4ca8be21ed05bb0e3fe960911929730a4881e33dc377da91de1435e7 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/audit/qa_audit/broker/qa_live.py` | text | 26034 | 40d2ed87aafd3bbb5ef34381919c405ede4154e073ef74f55b60217ca68e8ab5 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/audit/qa_audit/broker/qa_sandbox.py` | text | 289778 | f5283d60c118570cc584f7b19923a9c54be3c511eba13a01a79423e0d75e06df | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/audit/recommendations.md` | text | 6852 | 5e94c70601528ac616ad2f33fadd5ee306074c2c3cbcc4973c899b1233829c8e | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/audit/secrets-management.md` | text | 6762 | 3b58baeff366a836421056821bc99f806b3adedcb76de8b770ed56dfc12459e7 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/audit/security-audit-report.md` | text | 23798 | 68263415c1f144e69e5273cd70069ba141e1b32d5c071849cbf5e6125b6ce0b2 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/audit/sql-injection.md` | text | 4051 | edd685aa9204f9f96a3ac1f7d35281a6c9636b97f362e9413e29efe0cddf4ea8 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/audit/websocket-broker-priority.md` | text | 60325 | 84b6633de07986eea410a0903283ea846ca1e057fc9381eb60ad2377e2e4ac57 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/audit/websocket-frontend-management.md` | text | 18033 | b7c8bdf2688e0099ba5599ed77078245933475b1487a2564c923d28775416565 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/audit/websocket-integration-guidelines.md` | text | 23176 | dc6ad14a56183bef6bf38aba4928b4fa44b3e3d65cf5e44fb48ed862ebc87820 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/audit/websocket-keepalive-audit.md` | text | 29434 | 8e830b6773491e1f143e6b25ffec85512a999e68d05d8101aff8010d000122dd | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/audit/websocket-security.md` | text | 6235 | c7f8fb293b6e3007d8b7729561cb11d5729df157e5e9bfaebd98bd48ba327076 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/audit/websocket-token-refresh-audit.md` | text | 14797 | f8ebff769998a32bd52c7597d78cbb7c59d0e051469e67c03e37c1511f18cd25 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/audit/xss-csrf.md` | text | 5436 | f392d4178d7e1c0f50c956c2b3cc1325e67b0f6d03e0b7a42afcb32dd85a8d6d | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/bdd/README.md` | text | 3148 | d67c760f2d3632f6ab59300bd7b693173a578264e9f29972a0bf11a2470a7ac4 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/bdd/account_and_depth.feature` | text | 2288 | 1d9133245ebba82436cdb425fc63c856cb5bf841b9dfa3e22ca6c86276a0e317 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/bdd/admin_and_security.feature` | text | 1390 | a410b64f40992283081ddbe5c617dd10d42aa3728722f2231ce89a4ab266ecb3 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/bdd/auth_and_setup.feature` | text | 3710 | 76da7cd6398f9b141c72c169e43d40b4ca1b1f14a56980b983da91a26bfaef08 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/bdd/automation_webhooks.feature` | text | 1914 | 5db989ae1ec9d856b1183e3b64e81aa84084a06b3192b123aba294190bdef626 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/bdd/broker_plugin_inventory.feature` | text | 1712 | fd9db05da204110af4343c883add21091fd30b4d7414558d46eee0b9762541d9 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/bdd/broker_sessions.feature` | text | 5235 | a46586914a04b4d583ac2863a69679232aa81745de3574a53e214e5752075880 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/bdd/flow_workflows.feature` | text | 2399 | bfc3112d5659706677a1a9050802209ca4eb2852b084e3ad2318b2537c60e47a | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/bdd/gtt_orders.feature` | text | 2656 | 7c2ee496eaeea8a7c0d3cdeec664e038071879827d2cfc115a601b9beb3b5206 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/bdd/historify_and_tools.feature` | text | 1280 | a784a117353cf5b348359528ee94018cda4202a9a499d2a3fbc1aecd92f1e1dd | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/bdd/market_data.feature` | text | 1779 | a4c5b721ff21d002332b093bd78723d2094222641944cf0b5126621e9363b351 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/bdd/notifications_observability.feature` | text | 3783 | ef421fbadae2ed3dee2da998287ee373f65024f381b170ceac2833b326c91cad | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/bdd/orders_and_action_center.feature` | text | 3810 | 3b6a0033a70364b871c3ddae68204e8cef4095c63c534bda21b712a864c34a23 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/bdd/rest_api_inventory.feature` | text | 4412 | 0a5f036f5286398e70256f54f7be03922df1cfc59acd8b46672d27f57b14afc3 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/bdd/sandbox_analyzer.feature` | text | 1731 | 8636d70597d1f16855290ba07b2fc4db0fe5aecab06ab7d5a8dc4767ea7b8091 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/bdd/scalping_and_tools.feature` | text | 4459 | 395fef4fa9a9e3101e55a00df2096e4c3d20e6b835b4a35b98134bd62c43f6be | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/bdd/session_lifecycle.feature` | text | 2059 | 0ff879d6af2238ac4075572a257af3dfe0a8fa81731a797670b0bf681111d65b | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/bdd/strategy_module_rms.feature` | text | 14829 | 2a1eb18580c9218ee5d6e80b2de3ff1e4a5e99ba19c53c881c683d8f59fa5d05 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/bdd/websocket_streaming.feature` | text | 2796 | 5f92397c4ee17d50129f29715395d5b24d574e8f19e7e103e76d7eae06456fa8 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/benchmarks/greeks_baseline_pyvollib.json` | text | 30880 | 70481852be73c3470e2f0c60d6f6c7c15137204a8744ae2edaec99f8095daecc | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/benchmarks/greeks_baseline_pyvollib.md` | text | 8269 | 82e21874ae5ad58a90131f12ea003bc06869ff2764ea7aedc65f7370e9ce835e | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/benchmarks/greeks_opengreeks_parity.md` | text | 11231 | 2920a1263a1389afa8e9549f3169519c5c0624468eda450b364ba3252821e707 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/benchmarks/greeks_parity_opengreeks.json` | text | 48476 | 6bd0c4a668ed5f98db7bdb68da657a39aebe5ebc01888c8ba5d4e7e84115470a | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/benchmarks/greeks_post_opengreeks.json` | text | 30875 | 409a19637e1498fe098ab464344f45faa80d18ab9b869226a7afe6d68ed8fdbf | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/broker-integration-guide.md` | text | 52993 | 20c37cae0e86854b96643596d474fe37de4603965109cc313ca54ec1f51ac0bb | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/custom-indicators.md` | text | 29733 | f1b92eec0a8d415fe6f1c7cc9caad1bf31c75a9097148b44a7c079ce8f123332 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/00-directory-structure/README.md` | text | 4810 | 10b23f6d2f50fa458287ebd2c6f17fccd6a698da0c2f89f51192a876506da6f6 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/01-frontend/README.md` | text | 3991 | 27a660eee27e54b6cf70b67d55b246708650cb41ca79a9e35f3560a6528fb67f | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/02-backend/README.md` | text | 4566 | f6776302da2159bb98072124f8d49f3adf7ae309b5edff9fa5ceec212367b40f | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/03-login-broker-flow/README.md` | text | 5702 | b58182b79bae6fef6c3f26ba5a6dde5564910b3b2a6d7b04e53bd21ae9b0656c | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/04-cache-architecture/README.md` | text | 22320 | ada10a7d0ba619229b144d5f6e522a4cf8d46a03b67289434862978839e1b779 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/05-security-architecture/README.md` | text | 6645 | 78ad6ed3caa363c73eaeac40d1537d8292e2cc3766e3cae557e2ee663db43532 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/06-websockets/README.md` | text | 4344 | c332fc13745f88e9f751d2e0cb5d28dd10396c32d20a591c7844b2066494aec1 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/07-sandbox/README.md` | text | 74694 | 585065a25a7bf60a59e9b064d6d1c8b0fc3ff31eca9b9cdd6ce967a6c48633f0 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/08-historify/README.md` | text | 3031 | 09c5b2e92643bdeb7d342d8e0960bc1c9f720e0c5f794c0181627e2eeaaeb140 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/09-rest-api/README.md` | text | 3855 | 93aa59ba5bb2655a2416a6184d6da9e910a88aa3ff2f85ccb2a20925907d6eb0 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/10-flow-architecture/README.md` | text | 15430 | 318b521a1e96d4572c1c82ca5874a5e8669e00eb37d358b877f457ddc4829d08 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/11-docker/README.md` | text | 17709 | 238491e14a3756babcc9670693d87d877f1db3bba71ff0d84f1400f782200662 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/12-ubuntu-server/README.md` | text | 12233 | e44e71246cc079617f581d60a15ff46afde308ee225754ac3f2f04f1e11938f0 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/13-chartink/README.md` | text | 17726 | d6d1e311dfc8b3fff605bc4dee344d673279560f333ac513abcdab57680a5bcd | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/14-tradingview-gocharting/README.md` | text | 8790 | a15a7458b8569cae67148636c0a2d2c1819bf3efab16d2658f1d41d7c15049c7 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/15-basic-ui/README.md` | text | 4515 | 0bc7090046f563dbc158a57486b0068b102e8d7c04e5b2232c96c8d294d76f2d | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/16-centralized-logging/README.md` | text | 10104 | 5339b1b47164f779db3a801eecfd600849333bddea2df3265098016332f8fe04 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/17-connection-pooling/README.md` | text | 3448 | e5d7d940505bcbc89b700726612e51902158ca6bbced3b0970970c0e4c301a21 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/18-database-structure/README.md` | text | 4780 | bdb7b7c9a895a882cadd4395e484afeb7c4081d168c4cab6ff5d42081fc8a45b | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/19-placeorder-flow/README.md` | text | 25413 | a66503e0c1639f27f0aceeb7a33cb22088d5f023776f382ba0d1cd8fe568989d | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/20-design-principles/README.md` | text | 5596 | 4475cf73aa368ed415542f3ed498ee72d1868e00d45e1c87646ad7d0356c98d8 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/21-admin-section/README.md` | text | 17798 | 66321f3b3404fa80fc4b93a5474f89d5d5cecd202b8cab4b787f7228ff8fad66 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/22-log-section/README.md` | text | 12560 | 9c96bdc66d1afd92fc30baf8bb3fe4e6cb2b79f52d8398e9e36ddbed826a9d0a | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/23-ip-security/README.md` | text | 3619 | 8c44e66af93a4e0d7acba6122f7a655cd5200241f30be536b3579230fbc36fb6 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/24-browser-security/README.md` | text | 11895 | 2961706c12c112a83e0b6748346967df3f1c30b2cdd640c2a7bfe417e6ecc6b3 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/25-latency-monitor/README.md` | text | 18050 | 558d876a6614ca95721abaf75c56854f2339c1930a35e50c886678c8fe0e26f3 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/26-traffic-logs/README.md` | text | 3126 | 8e9c5492ab052056a175d6440906fae2de8cef08b8c1e1eea65b1a929bc2b462 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/27-service-layer/README.md` | text | 4697 | bdc7f0ab1f3fcd8a2f5b7b9815aaed8b3cf7d0b12d7aef39f3bc05c86fa7da4a | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/28-environment-config/README.md` | text | 10037 | c56ef5bf964ec45c2562cf4a8992809c179bd6c80c814a7d853be0c15c7d36f4 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/29-ngrok-config/README.md` | text | 2620 | 8e362e9d5c76417c51c648c826141d0b3fa7c2315db17b75ebc1e66c7d97ac38 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/30-upgrade-procedure/README.md` | text | 5338 | 2847123de45b1d701fe8f4eda0dcd814086aab4399dd43e02b6170a636fb3e67 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/31-utils-functionalities/README.md` | text | 8446 | ce5289f88868419c262e9107f093abbe541880a73714d472bd0b1f41543e75b3 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/32-master-contract/README.md` | text | 15784 | 805fd2f218673bb2513af7edeeb7e667bae38b01970e744d89a65dcd614ee7bc | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/33-broker-folder/README.md` | text | 7704 | 69ec705add6b182bd695dc5a82cb1a9aa1c2f78587a4782f897d88f2030133d1 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/34-app-startup/README.md` | text | 4397 | 4d9698133afc7710ee0dd3afc1d855140545234d14b1627e3e5943c62281ca41 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/35-development-testing/README.md` | text | 4246 | f6b350ee489efefa7ccd6d5737e3629520a6ffb7c2ef2cbdc44f555f7ad20b41 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/36-rate-limiting/README.md` | text | 14700 | 1852c27a80419fcfd22a29fdc7a59612a0716a818e2ae200c95b87d021e822a2 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/37-apikey-playground/README.md` | text | 16222 | 8b7dde6f8f9f48a34d5158d211710b3ec1e1f1bcb94f1139f71494c651d82c33 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/38-python-strategies/README.md` | text | 20821 | 88e80d5a0931456e31457e8e510e68a0d67d208b26ce91a6defb8fc072655888 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/40-logout-session/README.md` | text | 3418 | 86d7f80dfac94c0a34c8dac8f64573c4b5c00d2fcd1a682898a5af86909a4672 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/41-mcp-architecture/README.md` | text | 3939 | 8e7f753f656b69816ccd928c2c0d73da1d8ef029780c8523103561cee0a38206 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/42-action-center/README.md` | text | 24170 | 201ea749f4c536a87294b510ab16eae8b3afcb7c8718dc5aa3b6ee425f28c1ec | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/43-telegram-bot/README.md` | text | 4204 | 1efac158d76abfd813e5ab67ae6826a31166917ecd1d9d652237c9257d001f33 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/43-toast-notifications/README.md` | text | 11970 | 3332c491356153462496b7c4dff157a3f5d6e1fab0035a7ecc2531724d08b252 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/44-pnl-tracker/README.md` | text | 19378 | e7e53d0a7a36216b9ec3401c7c81283656dbbc1a86798734aa46c9b42aa5730a | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/46-search/README.md` | text | 3339 | fa685e7d945e8225615ffe69e23b2614870af994a32a58228d45acc4a693e4e8 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/47-smtp-config/README.md` | text | 2383 | 6e28e5def73be98a6f34674758c249394bcb2ca2372b894915125eb94c200a68 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/48-password-reset/README.md` | text | 23267 | 849c4f08b9dc9d55ccbfe7d8cc4615a881dea3d09b95d9b50afdfbd65ed3af45 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/49-themes/README.md` | text | 2119 | dee7f4f54a2ec4c3573c3daa92caa90c15f1435abc819dbae0a828444cc2a23e | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/50-totp-configuration/README.md` | text | 3085 | b0827be6da1c51e634d9557986667b843f22c2ecbc6c90412f3f860a12f70436 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/51-broker-system-config/README.md` | text | 6207 | 6885bca1f1961c6b1829d2f28b27d59626991d4f586f48b2a2bb6cae3894a4c8 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/52-broker-factory/README.md` | text | 3728 | f70ddfc27ee10d0b7c8bb16ffdc216da59c89208308ce02d426dbc3fb7f3fe8f | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/53-event-bus/README.md` | text | 5317 | a0067ca6e8c6b195f551ae7f37789d20fe6472b45e651540644fd8eb79741d03 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/54-scalping-terminal/README.md` | text | 5051 | 914eae788f6c97a303d48981c585698639484dc6236057aa8127ea6acad078b5 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/55-agent/README.md` | text | 132186 | 7410d7528528468163a4f005ee8b4d5a1e25036723e2b1d511f9a6cea07f89c1 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/56-voice-agent/README.md` | text | 14889 | 07ebcc69737e6a2b7621b8f39e238d12ed634e4f37fbe47578c95b300986659b | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/README.md` | text | 6414 | 4db6f3237d3e03461099af73e072b09c32760d84735a81ef1ffc22681bbaf540 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/design/TRACKER.md` | text | 3261 | 4e26e4b4df1c29d1cbb123bdf687758aa3d287a205c5f386940aa2aa7c37fe22 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/devsprint/README.md` | text | 23462 | 2d5b34ace775acee79a089ae3757cf9f31d67922d48e43da479a32f5a3fb0e79 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/devsprint/participants.md` | text | 2057 | c3948821132399e60effe5f5d83a33c4e37c963f4ca5b00dabc69a95263dfd7f | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/docker/DOCKER_BUILD_GUIDE.md` | text | 13894 | 2128a712112b31c504df9da5566105e884923f0e44d4d22227e8cbe09e0cf2e4 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/docker/DOCKER_NUMBA_FIX.md` | text | 7490 | f13ab5de598bf6c83611ef415c7f5f0103d8f0c74a47d491e07bb5c6cb3a7b8d | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/docker/DOCKER_SCRIPTS_ANALYSIS.md` | text | 8503 | 17110e2f52b419ae656a21d2dc4615e46d057bb64ea4cfcc477aa0ea54888b2c | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/docker/QUICK_REFERENCE.md` | text | 4032 | f91de78a3f1a6ca496c5818d61e9933a1da6860454859edc8fceb8438da6fca8 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/docker/README.md` | text | 7089 | 068dbf499491b2a7f4d780b6e74614b3014874ac60b37d2aa09b19e31c2341dd | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/docker/UPDATES_SUMMARY.md` | text | 10249 | 53293b3901bff24982280b4e09d6463492b768ce28e702e78c5d91c8f4eb2d70 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/docker/docker.md` | text | 2955 | 8901c1b60c3c118e1ae394d506c99b1d2aab46f974d4dd3ccb55ccb2b8e49952 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/docker/docker_env_changes.md` | text | 2704 | 695c3ca0246ac7c6f898141cb13ab4dff68583124d3708d87ec112714c73b750 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/gthread/HISTORIFY_GTHREAD_MIGRATION_AUDIT.md` | text | 8901 | dba57bcf8a265fc229281748871df09153c91e5e330901b73a1a4ff26d587272 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/gthread/README.md` | text | 22885 | 6f208f1ded147eb215a99a78f1c9b96251f1502eb9aff48484463e74a11e7339 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/installation-guidelines/getting-started/ubuntu-server-installation.md` | text | 12985 | ae24cf4d0851381fc5cec6983cdec515025153ea2ed94fc4d1de193816ec6a26 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/mcp-tool-reference.md` | text | 21975 | 223e295671046874c9a3ab807c217081d72d7e5b8fb276d99751460e1308ac73 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/migration/flask-to-fastapi-migration-plan.md` | text | 63671 | fe58f706785050635fc52b8a955e5c728981bd6a7bdc048ccc633228f5ae0861 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/migration/flask-to-fastapi-migration-tracker.csv` | text | 26122 | 08104973964970b93ea4f525ea3c25baf9441795d7fc47233926eb4bcf0f1845 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/nifty-algo/ADVANCED_ANALYTICS.md` | text | 5104 | 7f353c3cc33619fa0fa4d52ab18b04287b9fa8eb5f666f7d4ea0f3171985ad8c | documentation | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `docs/nifty-algo/ADVANCED_FEATURES_ARCHITECTURE.md` | text | 3154 | b48d9afaa352a791472786e7a901662271373b9e1b936dbc88aa99dad36520f5 | documentation | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `docs/nifty-algo/ADVANCED_FEATURES_READINESS.md` | text | 10269 | 36b33407af6f107f69c6c5ab2f34564b261bcaf3f1c61ef33ed185ca6559f4a8 | documentation | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `docs/nifty-algo/ADVANCED_FEATURES_TESTING.md` | text | 24050 | d9d6173a70fe9fdf36c715e329fe165a36c76adb4bc8e174c207f074653c7a9b | documentation | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `docs/nifty-algo/ARCHITECTURE.md` | text | 19117 | 29ccb047e5210b0f8e3353480748431a05262cdcda96898e2047b8b17ab9b92e | documentation | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `docs/nifty-algo/CHANGELOG.md` | text | 11254 | b4afbeb7620a9880089769757af3ee6a20eeb033c71ef96cc679608624aa6c4e | documentation | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `docs/nifty-algo/COMPLIANCE_REMEDIATION.md` | text | 21905 | 13040937d116d82dada655c59eff0722be7758c20c8113762246ecdd2c11e7d5 | documentation | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `docs/nifty-algo/DISCORD_INTEGRATION.md` | text | 9873 | ffbe7f6b6d4ffa34966b50980200630230b37eb889f83a0fa4e36c65da48f083 | documentation | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `docs/nifty-algo/EXECUTION_SAFETY_CENTER.md` | text | 1761 | 720b7b304c79e4b605ed131c413419bfab154caea8fda4812e8cb208082f8017 | documentation | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `docs/nifty-algo/FIVE_FEATURES_INTEGRATION_AUDIT.md` | text | 51292 | f6741f1926e31e192ca6a9007611a656244e6a5baeb7bb0ada441920fa72b4de | documentation | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `docs/nifty-algo/FUTURE_ANGELONE_LIVE_PLAN.md` | text | 5003 | a84388b17a5404e20064f7a0bfd23b3be41595720238603b13f1660b00d2067e | documentation | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `docs/nifty-algo/HISTORICAL_REPLAY.md` | text | 8207 | 3a09b98c861232a8d9252a2ba2ba0a3af82aefb02bda201c3157e0eb16db0c10 | documentation | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `docs/nifty-algo/IMPLEMENTATION_PLAN.md` | text | 5731 | ac7eee5ec176e4d701ce35a67cede214fdc9d815885737300e7dd27ad0c30213 | documentation | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `docs/nifty-algo/MACD_THREE_CANDLE_WINDOW_2026-11.md` | text | 8119 | a04cf493c7836dd17eb105d269fcf507f021ad92c57cd7c8818b3e6aa5b105de | documentation | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `docs/nifty-algo/MASTER_DESIGN.md` | text | 3365 | 8ba0513554e76b13ca828e6bfc51042679c063be671b27845ed8efc5bfb23639 | documentation | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `docs/nifty-algo/MIGRATION_ANALYSIS.md` | text | 24868 | aa94be7113bf1520e52dddf9540215fe265dde0f8b1dc93e74bb97a2433db8ad | documentation | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `docs/nifty-algo/OFFLINE_ACCEPTANCE_2026-11.md` | text | 36262 | 8ffb55a1ab81d7012553c7b725ca64c8ba568eef2436dd83b597536d9d9e6d5d | documentation | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `docs/nifty-algo/OPENALGO_REUSE_AUDIT.md` | text | 5365 | 35e536597658f0778ffa572a4f54cf907d708da834c40babf50ce08db62e30f7 | documentation | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `docs/nifty-algo/PAPER_SYSTEM_DESIGN.md` | text | 27634 | d736a1bdc4650a9d1659e4472be2f5d45a1f53ab2f45035502b2e3fae68014ff | documentation | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `docs/nifty-algo/PHASES_1_TO_7_GAP_AUDIT.md` | text | 20897 | 78c418314f94e6daeb9f9f7b4d617de36e18e75977146fe0f920b60bab5e491c | documentation | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `docs/nifty-algo/READINESS_REPORT.md` | text | 27995 | 52e091bf0a83b90ef33b9e60abee456e5af122f5f9a49c2c14a6cccb498b2663 | documentation | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `docs/nifty-algo/RESEARCH_SOURCES.md` | text | 7560 | ae782432727d6bd04c70bc4c03d46426d0153ca99c97b01e5c38bb4d93849fda | documentation | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `docs/nifty-algo/SAFETY_MODEL.md` | text | 10517 | ea717a8260d543858dcd44e5eeadf456ce50903159b9db6a690853eaaaa36e72 | documentation | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `docs/nifty-algo/SDK_241_PARITY.md` | text | 20980 | e04876ba1bd13711b27b6f5d8eaee6d38398cce9bab12454e52c0dc5927e2167 | documentation | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `docs/nifty-algo/SETUP.md` | text | 7511 | 634ac6cea366b4a47ee1050ecde61868664d7799ca4b27c3ef0adee9447245bf | documentation | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `docs/nifty-algo/SMART_CONTRACT_SELECTOR.md` | text | 5379 | ff3b57ea0d9aba62ef3260432c413b0328bbcb1b821c71d1160b09175a3379b4 | documentation | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `docs/nifty-algo/STITCH_SCREEN_MAPPING.md` | text | 4831 | fc7c44d46420c298c38f2332df12fa3215cf6985facc4d6cd66819e81cd66e33 | documentation | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `docs/nifty-algo/STRATEGY_ASSUMPTIONS.md` | text | 7866 | 5e6ee668e43beb1999e539ec24f600894c552a69ad1c0af9d5db11e5cd27ae51 | documentation | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `docs/nifty-algo/TESTING.md` | text | 17891 | 4124828138713950dd5da2f8183336a91a9cad4b770f936ba7ea1dd6ad661f82 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `docs/nifty-algo/VIDEO_STRATEGY_ANALYSIS.md` | text | 4683 | 0c7c5d4c635fad2a2c7afad20a43f29fab0b92e3fc05ba3daec2ee8a055d253b | documentation | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `docs/openscript.md` | text | 21933 | 6947a465ce5fff28764e27b667cc915591988827681be2bec6dfee6aa282bba9 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/plans/2026-02-06-strategy-risk-management-prd.md` | text | 115406 | 73f2d2bbeed74375c8dbc74186ad862b97c57e125e5f42457d8cb438d2b9b083 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/plans/2026-04-22-gtt-orders-implementation-plan.md` | text | 49970 | b83e13fd7478225625bc72d6dac0f83b96d23f16443ca6db70100889b8b0e697 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/plans/2026-04-24-kill-switch-implementation-plan.md` | text | 37521 | 39dcacca3a84f1f681ecd5fae3ae97ffbd5febaa3809020cb213bb2cc7dc0a67 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prd/CONFLICTS.md` | text | 4422 | 72834637b62ac990c07e290894afb151148281258d007b47d5b3faa537c3db06 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prd/PRD.md` | text | 39284 | dd55f6ba19724709a56bf603c4ee4af7726f278945bacb79141303c04b3a57c5 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prd/PRD_TRACEABILITY.md` | text | 5088 | 3cce6efb2afbc1ea931a47c579cde174879717dac0c2dcc00412d70b195ecfbc | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prd/README.md` | text | 3006 | 18dc80d5966941b1b67f119b2c737944bcca951f3806c547cacb01a56035c9f9 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prd/analytics-tools.md` | text | 3937 | 87c1ff0f4ea666f852a8114b64ff5b5f1283664c12fe10bdecc4ea47f525acab | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prd/ci-cd-local-development.md` | text | 5734 | 1abb8670ad8711a410108e5b2a57206bf0b0cb7c75c40fa83498177b5b6ddff4 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prd/ci-cd-security.md` | text | 5827 | d709d8205c7eaecec0e2e00c27a7a4ee4b7e40ddf831a8ac38e9e86920905006 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prd/ci-cd-workflows.md` | text | 7726 | 278ddc637182927dc4829466f9cb81f0443115fe581085502cd965d3a6b17eb8 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prd/ci-cd.md` | text | 7065 | 9ded53aa5a8c3e275f0ec2eceef1ea5b55291f0dc5ff82678b8351673bf822e9 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prd/event-bus.md` | text | 3325 | 401a7b030d457cdbe45bce4d7b22e733e1ddbbab9db1d573a5eac3af884d69d3 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prd/flow-execution.md` | text | 33133 | 87f33928336370d7cf3a2b616244ce3bfc6e130911c6a4891a2007d9e08e5285 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prd/flow-node-creation.md` | text | 19441 | 1fdcf44acb0253fbd5335798df5a928a857f684d24ed74c590ae0ff2de5463bb | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prd/flow-node-reference.md` | text | 16465 | 47e77e8c803fcffdcc034b673478ff875736433cbe230ee3314ea301b8e2fd1c | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prd/flow-ui-components.md` | text | 24394 | 4bedbb3b7371720143ab1d0471d5767137954e1f9818056527a10ff1593799c0 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prd/flow.md` | text | 10968 | 68e96f5b6763b81510c5810e7b5f2e4f23b190eca523978cd363dfd3d2496db1 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prd/historify-api-reference.md` | text | 8633 | e081541fa02baf2ac60a078a3efc7b95752ba58c20b2cf35c2b1a61c3cbc7df6 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prd/historify-data-model.md` | text | 3449 | b162c8507c46e38a4b9815b5eff1751427bd2ac069b175df5e993c684d62e9bc | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prd/historify-download-engine.md` | text | 3752 | eaa164be767fb6ecacd4c20af2b9cd6f8cb6c726527d7c72cdedb8ec2538fe83 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prd/historify.md` | text | 3776 | 69e5a17489c8049677c517082816c4329916207ced962e7b6588674a484c072c | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prd/python-strategies-api-reference.md` | text | 10354 | f2bebdb65158ef90b5ce81911b6faedb295481e115408c310e9d6cc04364a2b4 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prd/python-strategies-process-management.md` | text | 16839 | 4b72889f127ad8a8da8d5c6ff39546573b718de120c8294755138b96b85e1011 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prd/python-strategies-scheduling.md` | text | 20841 | 8e483db7c49e07d7e38514ba056e1828a65a86d4cfc8f470a9553d858a43e4f1 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prd/python-strategies.md` | text | 12372 | ca54a01a1f03d211ccf051c0f59586a24189ab3c03dbd8521dcacd33d5928b4e | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prd/remote-mcp.md` | text | 5794 | d46165715582e1bd9759bf6e386e6b756178f2105dc7142e4caeaec5b5f26d0a | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prd/sandbox-architecture.md` | text | 15425 | 2eee8e83ea527dc8e782286b2c576686a05f1590092fa670b9caa6f16e8c9a5d | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prd/sandbox-charges.md` | text | 12808 | 1ff64be5a82b8b8a42cc7c57a7303fc40dc87b389e2f87a022a1045767486972 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prd/sandbox-execution-engine.md` | text | 3764 | 256eb1b7e26a0573e1e681b5915d24c923b037ff9d1f18867a8b88a09ed6df4d | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prd/sandbox-margin-system.md` | text | 17838 | e6ecbb822051fefcdff5694068ba04ba9c8ac007ff17b7a74e41d0eaf6bb9d00 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prd/sandbox.md` | text | 12883 | a6989fe3cc2e2e9727a6d0be0ec568f0f5891252ddc4a87fbe00a1c7dd2806f3 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prd/scalping.md` | text | 2147 | 3a9c880039694c5cc64b676423b1d00de9592a04f50f19355803baaf0f4c9b42 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prd/session-lifecycle.md` | text | 1549 | 2ecdc15df0aaacc2a178d58eccde23710ed7ce6ee19c6e5454bd7aa776ce15e3 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prd/strategy-module-rms.md` | text | 18326 | caa948f7c7476f1d97e9a6dd4dc32d2b2f314b3ed47994eb84def68e85482387 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prd/websocket-proxy.md` | text | 4593 | 85e8cc47da81e9556f3eb8b0dcb31b2d7992873b9f27871588d97231b3a64b30 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prompt/LotSize.md` | text | 5783 | 7c3e43361973a16fa7443d7c804d9d48ab133aae3ba362d15c2dec5e814e12af | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prompt/crypto-symbol-format.md` | text | 6606 | 1546b9a4e1c3effd2213f831d971d5607230de5a3d6a3a3d90e9f1fd92a9722a | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prompt/flow-import-format.md` | text | 128757 | c826d683c0f11fc0273231a830da3c5778d9b4f24f82c2c08b387770082b9b8e | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prompt/indicators/chart-indicators.md` | text | 5651 | ff2ad6e392215a34b7b0cf033a5b2f0916b3269d3a01ad3ac1cab358da351bc6 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prompt/indicators/flow indicator reference.md` | text | 18620 | 19b1a5ab867f18dee318468f322493d70b8e8d4db9d998d257369f67d2e6b701 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prompt/indicators/hybrid - openalgo indicators.md` | text | 16433 | 71f714f484aa236f3847a2bee12ec3201e1f5093d493a5b6c77ec5c6f35843d3 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prompt/indicators/momentum - openalgo indicators.md` | text | 12072 | b96371fe2ed96d1b966a088e54e335f25e65612e45b4ae69b7381f348d616943 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prompt/indicators/openalgo indicators - introduction.md` | text | 6142 | eac7586992277e72112de744bcaaf38a6a620669016e14c404d020715460fc6a | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prompt/indicators/statistical - openalgo indicators.md` | text | 16884 | b407f53bea71574e2f776778e207503ae5d87288d32fc0f3a955970d0b95078e | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prompt/indicators/trend - openalgo indicators.md` | text | 16368 | 7efb258a20f19c0fb3ef242dbe1f384ddab41545b3dc599c0053e2d70a68e1f8 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prompt/indicators/utility - openalgo indicators.md` | text | 15583 | 5df4bba233ad190b0958df92f341661eebeb23ddb723edf1f88773d65b83b04f | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prompt/indicators/volatility - openalgo indicators.md` | text | 20420 | 4b2b002941c99420a00efd4985cee84cf68ac1a6f907292fa3915062d713913b | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prompt/indicators/volume - openalgo indicators.md` | text | 17263 | 860491bdb185ee6a22893d1f72aa715b94def33eee76fd87d7dc48e3bbb096d8 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prompt/openalgo python sdk.md` | text | 70150 | 0e918bd1468d759053d019ecc7261402bf6dab40bd945edf8da541f834999b07 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prompt/openui-lang.md` | text | 8445 | b484ca9128c83d59b3d65999b980b22128c603fcdf974030eaa5c1c7174fd523 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prompt/order-constants.md` | text | 1534 | 75f1caca647182b486f506f5f5202a410588c414c2d798ff81a68e5eebe60de3 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prompt/services_documentation.md` | text | 48414 | 68404699b49142217ae9a1f568841b20004c4b22dcdc90b3a1a038e79c3a6295 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prompt/strategy_rms_documentation.md` | text | 60154 | 1df2d4c2938bba4452a67beaed661f07be13c3e1d983ee510cec2acad42794cc | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prompt/symbol-format.md` | text | 14048 | d691ca56fca342ece105ed0472da50b894eaa5531c4c72878a9c8012d768c001 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prompt/websockets-format.md` | text | 11875 | a9d9bbba39cb66f4430ce0b93a0a885012ad2cd783dcb1b9f919d3061a35b315 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/prompt/websockets-verbose-control.md` | text | 5712 | 0a3c922c9ccd8a5ea883937ca3802334c18d52e331526d3b551badfde303799f | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/releases/version-2.0.0.7-released.md` | text | 8592 | 8ba0dfeca1d6b4c5366f4021cdc5625ebabfbd7ee07679c86273b60d27ff7ed2 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/releases/version-2.0.0.8-released.md` | text | 13270 | a210071b3b3c7bc28b7a352fce921a4cf23afabdf60c55aa8e9d99d1a7ef0aa6 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/releases/version-2.0.0.9-released.md` | text | 6082 | ea89649513eabf04dbdf757432dfb49278d00ec9009086524e90cc71fcd4e7fa | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/releases/version-2.0.1.0-released.md` | text | 18038 | 81a21a12d208b9b6bcbbdc90e04519da11c69a53ad5767f4c2e9c7f71f6ce1c5 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/releases/version-2.0.1.1-released.md` | text | 25870 | 5ffec3e4166d1f9cc78206101ca06fc70a85cc55267eaf1a2ad81829b1e33a29 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/releases/version-2.0.1.2-released.md` | text | 14076 | f48958ea92de6dbf7f1f71fd65ab6ccc418bc2deebf20b97bb2d105c8c598584 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/releases/version-2.0.1.3-released.md` | text | 13752 | e67a2c6259362a2f7f878b7557c4809fd61a5aa35c697ca5c104f199ef613182 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/releases/version-2.0.1.4-released.md` | text | 14744 | 044ec118db6064dfc36d81da27ece16adbace3f3ca5755e854ec3aa6d136627d | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/releases/version-2.0.1.5-released.md` | text | 18280 | 1724629dcba58c94a8088f8cd0e520eb10594a372851053d6f676f568c49b3f9 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/releases/version-2.0.1.6-released.md` | text | 17806 | 381b23e0ed41e222eb7f8ebfafaf9bac71e6cffe45bdc3439ceb84f4fc4def09 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/releases/version-2.0.1.7-released.md` | text | 7334 | f232ad18804dc59af1fa3be49eff535788dfd901c7544fa191b1552287e56e30 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/releases/version-2.0.1.8-released.md` | text | 10207 | 06c93ed65f66f67d1c128f9a8ae2cc037c5e0f9ca20385fdacd866160f2ac301 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/releases/version-2.0.1.9-released.md` | text | 10345 | 983cfb56fc7814b6aef4cb6421872883d0bb3374c52296695bc0c49934b71e88 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/releases/version-2.0.2.0-released.md` | text | 13115 | d7146e4af2733d987903ce1773d98be5fdcc2e96f75957719933b55b42336e17 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/releases/version-2.0.2.1-released.md` | text | 21129 | 18f2bb1c29a723a14faf6f96947437e3b26df4c0c1930469ca12d49406e482d5 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/releases/version-2.0.2.2-released.md` | text | 33568 | 8bb1cafa65aeb52957a7fc4db03f3d33ee8600740a35b95c62e8989a9f6c5d0a | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/releases/version-2.0.2.3-released.md` | text | 14677 | f4c176027e8015680c077ea4ab6471da14b68adadae471da9e53bc862e389831 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/releases/version-2.0.2.4-released.md` | text | 9122 | 8ea9e7c6395ec26c3333c84ec1a34b9feca0198944bf4372957ab7c075b94788 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/releases/version-2.0.2.5-released.md` | text | 13051 | 0a241305323d256e5fa311a15f581d2c6a1366f7ed9421d27ecd73ebfef364f9 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/releases/version-2.0.2.6-released.md` | text | 20337 | a5b6c18f35854e47c3107100c0eacf3ee5ff96becbc6235fe4f8c17a2aa4060f | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/releases/version-2.0.2.7-released.md` | text | 15382 | 9f5c9f8161a9e68a230734efba083364dc1e7740cf169636ad2696562afd9fca | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/releases/version-2.0.2.8-released.md` | text | 11919 | 9b12894fcff7be43d85563a343fb727cadd9bfc9add76ac4b15bc40ee4acb2f3 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/releases/version-2.0.2.9-released.md` | text | 6045 | f8c5f98a44f2186ca8abe6be739502edca5598f2a652f9a1170304dbf9181288 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/releases/version-2.0.3.0-released.md` | text | 9724 | 5b45c202e16ce9d35b6e604ea37a3a97be9934ac331cbd84d28b25be8343b176 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/releases/version-2.0.3.1-released.md` | text | 5519 | 17cbe93b80da3f4396a070fc0773eaf8b5ff4e00d45126133bc1f1d7033a3c83 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/releases/version-2.0.3.2-released.md` | text | 4482 | 6b133215a18342916fc0a53ff6c165d2009da8207a69a1b5098c6dd0c4725328 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/releases/version-2.0.3.3-released.md` | text | 13108 | 2960503ee4fd1271b94d7e269f39902333be5e77f558b7bc0c02b762f93c83ca | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/releases/version-2.0.3.4-released.md` | text | 17098 | 276b2e73eba35926784b57d6e1ef3e9ae78b59fc03fa441d418fa4dc2e30ea95 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/releases/version-2.0.3.5-released.md` | text | 3045 | 94ddd83777e54a0904d47b6ce4fdb9d5f5c90b4af523c494f8936b6cbd81330e | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/scalping/IMPLEMENTATION_PLAN.md` | text | 10087 | 48526bb73625e70249303c9e10a6ed88f57ba835b826d2c3de001413e4134d5d | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/scalping/ORDER_LIFECYCLE_TESTS.md` | text | 6278 | a811460fa7e20e531206221ae5dd65382b557ed22ac79e9a5214994227b3a177 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/scalping/PRD.md` | text | 10164 | ea30392851c164c9e0dadcdbc202bd8d56f11e99b8807f4b8235b73f35134ad2 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/scalping/TRACKER.csv` | text | 3575 | 483f050d525248d0ed9e0a0c4334f76a39d900fd323eb96491fe20a9bfe616f5 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/scanner-architecture.md` | text | 37396 | f98d7e1b3270d84ce647e9da897a206b1c96724f4259fbead315c02042b71333 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/superpowers/README.md` | text | 4236 | febee347791bd60cbcfcb22f09a2372ebf4b834fe93b8231ffd7d7a71d73fae1 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/superpowers/audit/2026-07-13-sitewide-coupling-audit.md` | text | 9435 | 99e1b444c61d23dc7c5fdeb13a0fe986d4c01061169127f80fa9f9f110b04621 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/superpowers/audit/coupling_inventory.py` | text | 2725 | 891d8f7e6bbf8045c0a93b5373bd88ab73bbc5ecec019b70b295ec60288b35e7 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/superpowers/blockers/blocker-register.md` | text | 3929 | 39b5e79d12ed6e6fa1a941890f6325caa76e8d50bc2bcb6af56f4fb0d6c6a379 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/superpowers/decisions/2026-07-13-crypto-native-integration-not-ccxt.md` | text | 3461 | f7ab7990705f625d100d20a9dbd5676fb05ea25d4d0f13fe00bf28f97dc6f31c | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/superpowers/decisions/2026-07-13-direct-api-integration-no-vendor-sdks.md` | text | 3593 | ebb76c4dc08bb8d1a334c20fdbb10a889ff528acbec8c78cda4c45178e03ad89 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/superpowers/decisions/2026-07-13-in-tree-broker-model.md` | text | 3534 | dca9d5f4ffeb709fc72e85f46657b58d346caafd7727875373406b9aff81a4fe | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/superpowers/plans/2026-07-31-portfolio-backtester-release-hardening.md` | text | 21246 | 201c5a9ba5f626ec9645dea922c9522c99340a7d6ec1bd4090232d97fcbb90af | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/superpowers/plans/2026-08-02-repository-documentation-freshness.md` | text | 20908 | 372ff7f78781a4f27105d0e8b6d3c782adf4d06fbf226d7ccff06e0da2715f63 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/superpowers/plans/2026-08-22-flow-contract-repair.md` | text | 37895 | a5351bf7d125893e5af88ae6ce11e4124e80af80aa13b2a3edd426e41e9caedc | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/superpowers/plans/2026-08-30-strategy-release-blockers.md` | text | 36655 | 5f2d412ee5ad18fa2174382c8279e92560e10e187919a2d3844171cfb59bcd4b | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/superpowers/plans/2026-09-20-charts-245-consumer.md` | text | 18243 | 733d38f9035060aa6fa0da7a65c4ee55010195db1325fa1d4c6d3ce7fea058cf | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/superpowers/plans/2026-10-17-chart-and-mcp-upgrade.md` | text | 2725 | eef1daf8b03fe0476733fcc7c495c2e1808c6d1520ece015707bb35acd68589e | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/superpowers/problem/2026-07-13-challenges-and-solutions.md` | text | 6047 | 8c9081f0e7a5f95003a759172725d8a3172c5145adf33cd28aa112f5f40d42e5 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/superpowers/reviews/2026-07-13-codex-review-2-response.md` | text | 7157 | bb2a7183267940dd79cd93b596444fe2c4c438a9dcb6d8f4e54b08dcf80cc361 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/superpowers/reviews/2026-07-13-codex-review-3-response.md` | text | 3766 | ebafd81de1b4064c7f5a352e0f5ec798a140d358b7b954069098095614a72d46 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/superpowers/reviews/2026-07-13-codex-review-response.md` | text | 4945 | 2bddf5f220e4fb1457b4a19c846894ff89892856ae0de1ea9bcad81eacda5b03 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/superpowers/roadmap/2026-07-13-phased-roadmap.md` | text | 10385 | 94dd4ad025fcd30a1e255f6c68c0696d333c72a9819d16b8aed19f224f3362ea | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/superpowers/specs/2026-07-13-global-market-architecture-design.md` | text | 19135 | 1908ff897f92f677e6747d13931c4d46c0ddb13fefd45a8547794c18dd034d1b | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/superpowers/specs/2026-07-31-portfolio-backtester-release-hardening-design.md` | text | 9248 | 3ca272f2f973ba2a6f6742102006c70bb50c7c19898ae7683be90554019d34b9 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/superpowers/specs/2026-08-02-documentation-freshness-design.md` | text | 7178 | 13430a9fb09d60c4f2e8eaef35da625c01daf53a80cd8057fab89a87d83a2125 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/superpowers/specs/2026-08-11-strategy-builder-repair-design.md` | text | 11759 | 9f29f59a97295aa57f1b8c7b38afe32a48b660d79f98767bc033d2978ee84231 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/superpowers/specs/2026-08-22-flow-contract-repair-design.md` | text | 12248 | c11479b907e6d6d797c58bc76001533e78dfa68b9fb0fc287f6ea06088f378e3 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/superpowers/specs/2026-08-30-strategy-release-blockers-design.md` | text | 15585 | 7b1f150b1b1c30abd877854197ef56f5599c74ad5d98cf668289e03d729fd2d7 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/telegram-chart-rendering.md` | text | 22283 | 1de2079e0bac42b6c938def31a548a93acc55f109a9a7000b183e887af309c9b | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/test/BROKER_INTEGRATION_TESTING_GUIDE.md` | text | 21325 | cf4b6b88a79b6956f2bb045514284af210e81611fd1838fcdb2b59fede256a70 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/test/MANUAL_TESTING_GUIDE.md` | text | 33504 | f4effd1e2fd760b920c2a8bdfa43e3011a80a9370a0d83a485d8e551c90de002 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/test/QUICK_TEST_CHECKLIST.md` | text | 8429 | 226408caba0ec560363087f203341232acf2ed921a2217e4a5f2de148e0eacc6 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/test/STRATEGY_BUILDER_PAYOFF_VALIDATION.md` | text | 7594 | 0a9e336b9094c759b9a834c545859cb98af63c6d4e72c5b0dd674880e3de7e1b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/01-what-is-openalgo/README.md` | text | 14359 | 7502c10e21aca8d2e00a1b08a3a7ddd2a7884eeb55fb474d85ad7d226a47da93 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/02-why-build-with-openalgo/README.md` | text | 10415 | 48810a56a3f75a63eb41cac0eea743268f558e9d778d07735d85aeeb773bfe8d | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/03-key-concepts/README.md` | text | 8437 | e870c501fdbe42aeaaac80e097fec250862dbdd73407176485b77f72c108437f | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/03-system-requirements/README.md` | text | 7593 | 18298e7f13d8454779212f66d78f6d0d7d05a5ed17336cd956e04be781a99df4 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/04-installation/README.md` | text | 26326 | b2a8338ecb46a124b1a5db432d16ad2108b102e8c017525c7ad891082ec6f50a | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/05-first-time-setup/README.md` | text | 5342 | 6299eac63ee26db2edd9cd1b5d5cbb1957aedfbccef195275f5bdf1ee47599d2 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/06-broker-connection/README.md` | text | 12394 | 3fb011e50adbd8295b34330c1bbf99c1dde5fea806809d14b61f6e9e0410fc2c | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/07-dashboard-overview/README.md` | text | 2910 | b7ac92dd2c66871d18890a2cc187dd5c506a2135284f9139f29b1c74c548de5c | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/08-understanding-interface/README.md` | text | 4512 | 0de48702471cf592728911d6f06db1d3156ac055982c4a557037bf89f5c01a1e | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/09-api-key-management/README.md` | text | 4396 | d3c048ee3ddfbb56b9c3f808686d242c2782cce9abfe0ce2143a350babb460d7 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/10-placing-first-order/README.md` | text | 11510 | ace65e3522d810cad0ad9fb3fc3000d62392dd7406350e81e09d477dd53e9180 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/11-order-types/README.md` | text | 11943 | 36873872fa0e305f73168a75105c9227ac50c5013c0bcdccc48f733634441aec | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/12-smart-orders/README.md` | text | 2987 | e52d3a9b2d187bf1eeffaab302b2602e435d6e4e55db7ab3b732333d0b64bd54 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/13-basket-orders/README.md` | text | 9699 | 346b159e754cfcbf149ce5ca05b35e9b08b699802f5752f4dcb40fc71f5fd10d | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/14-positions-holdings/README.md` | text | 3957 | 8475eb51e533c1ac805540c9c9498d33dd0d7ae771457a4c7e9098bea8db79db | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/15-analyzer-mode/README.md` | text | 5726 | 5faab7edb00c8b1518aee2d9b62bc5834e2f049daacbaccf912b73d8406940dc | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/16-tradingview-integration/README.md` | text | 4592 | dd75ff935c6b3e127e0c0816a853bba72b2ca4686d4092b62faf90150668d78e | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/17-amibroker-integration/README.md` | text | 3763 | 1cb6a1c22fa268c3effce2f9fe7a77844d50166a7f1f0bff2e31eb18f06f872a | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/18-chartink-integration/README.md` | text | 4332 | 0f7f2dab16d95f8ba8550bf75de12416cde8a01293a04f742bf9d1aabf177776 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/19-gocharting-integration/README.md` | text | 3195 | 5aea9439c0c6826b0d92a598582a1e1d6f49b18671edb1dbfac7d77c9361ff92 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/20-python-strategies/README.md` | text | 6961 | 16916e66ce36d506226aea206a4e98607c8b01104fe1db2b1a35e9ea39f50a37 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/21-flow-visual-builder/README.md` | text | 5472 | f97befc5f9360e4744001528f8fa9f21c4434e7689c17a7084da9a1fe91235cb | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/22-action-center/README.md` | text | 5663 | 12cc20c91254c5874cd8749a3db8eff639fc9948de25499f957b83267f041adb | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/23-telegram-bot/README.md` | text | 4175 | 614e435930397c705c2e720e85ea6a4af59867d0357db404658e730c6aced499 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/24-pnl-tracker/README.md` | text | 1892 | 984a572ac7f7bebe8ba07561c1a74761143b2a89c811fb2c849c8d7f04dad33b | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/25-latency-monitor/README.md` | text | 4541 | 2e14a4ade6974778d36527b39c55b1a0e53543cc82a8fb190b19f7c9bdc3a523 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/26-traffic-logs/README.md` | text | 2545 | 856efcd488731b78a4ecac080fe23345468671a72491dfbf4ab0cf3a2a3a1402 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/27-security-settings/README.md` | text | 4781 | 66db6e312434179bb3f23d4c0a2cbf354585adc6cd0906a492f68c70138ca15c | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/28-two-factor-auth/README.md` | text | 3816 | db82d4b968ea614a4be211b6f60545b1418173411ecb139c44f07b7bf7b272bc | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/29-troubleshooting/README.md` | text | 11571 | c11f376bc98411207208e4e9ed3426370fe83e6b0a70bc395f87ba79b9761fcf | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/30-faqs/README.md` | text | 7625 | 97402cc0d116b5f7f0dc706d330afbab52ea83f9bf70d88c20bdf358fca7aa1a | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/31-tools/README.md` | text | 12178 | cd03cd0aeecdb0fe7710d35692671cd2d897149441c6bc78c2662980d77d7d34 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/32-charting-terminal/README.md` | text | 46729 | 8a7a5ab17c00a368bde9ba99a4a911a8e4a9fdf487453f9abcb4b39927aef231 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/README.md` | text | 4825 | cac542d01a55b8905267ab79078161c035f380858cf8aa07c3f1eb77e843ead8 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/TRACKER.md` | text | 3495 | 0a2991c81967366e46f7589520c5af40f2cc5b5424506f41edb5116748c311a1 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/remote-mcp.md` | text | 21860 | f1679d9ae5e9898a6015daa8d90621e225337a1769928225b6c7cdd77ed4395d | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/userguide/symbol-format/README.md` | text | 18035 | 461c6ac3df1f29d6d992fd585a9c766917a4fb7677a5865025db4a118e5fcd98 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/websocket-architecture.md` | text | 11235 | 62c6e13973723f162de96d5e4af987d2b2f521ca7eae1f07bc7ec7588d6d2371 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/websocket-quote-feed.md` | text | 5176 | 29055c23d6c4815c1965839238d618935a76879da481172bf469b5a362dd7975 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/whatsapp.md` | text | 32855 | 47bc7a489e5986081cdad7508032c2bfc91be26683ca257687eb19812efca697 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `docs/xtsapi.md` | text | 5651 | e07053a5b760682832063ac364d4b3221b2c65c75e9c7a2e862ad2d877b16d4d | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `download/.sample.env` | text | 167 | df832e70c854fecb7aff81f44eef6b06d6017f68279cee6bef8a7e29138889a0 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `download/README.md` | text | 1986 | f6299f6cda979541fb5acc36d0223942fb79b7e48342fa2f23bb22cdd7117b21 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `download/duckdb_downloader.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `download/ieod.py` | text | 6507 | 1bda7a9f2febdba3dcf5bb74d2d59696f4360333d2d43fbfe4f3a140a38e0f7b | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `download/sqlite_downloader.py` | text | 3254 | 5465eea60c454b995a95223432adf375a939feeb403bb3b6a146c9c412670d8b | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `download/symbols.csv` | text | 46 | f16f54731ba7e363a96a3717c64f03849c8d2a90c2582ab488bc0ea66827f675 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `events/__init__.py` | text | 1796 | 5fac30f411c1f1906e49d02587cdd0d0e05fff7fd99bb660088e94f4714c356f | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `events/alert_events.py` | text | 1264 | 8e3af24aa460e3e2113b19e6f9d27f399c4ad57f3c7eca8dd421f0a85b3d0dd6 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `events/analyzer_events.py` | text | 335 | 5f3bc3553c23eda6a38e58d24b194351acb3b36e98cce13f213c1cabf48a99c8 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `events/base.py` | text | 737 | 6cd3630919607862f03b11540222cb854db15844238fc0ba9301fdfd99073367 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `events/batch_events.py` | text | 1674 | c535d215511678425e2eeb9b741444109033c067110a2f935b0fbf709a2a7c2c | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `events/order_events.py` | text | 5159 | f28386a03f4c18c6e754692bf6fef0e8996079f893b0c91e57313e6d70fdd9ee | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `events/position_events.py` | text | 719 | eb971337357ac7bfcbe396444e19ca52942dbeefc637a636b38b8f3ad5298311 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `events/sandbox_events.py` | text | 1834 | 0b67fa8d8ce7507c656c6bd67fc69bbc09f5c68dad598a9ac535dbe16004fa2c | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `examples/go/readme.md` | text | 24 | d8aadd2a6bc0d461d978a290e635b50a832d028c9a5932cc31382374686ad39c | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `examples/nodejs/readme.md` | text | 28 | 4fe1edc3697b4b17af71a29a592acdc3ea8678c93807e56a0f7752e3107b55b4 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `examples/python/Nifty OI Charts.py` | text | 13140 | 94b456ef284db47d72b379570e0cd4e33cb3862aed19de384cd642c35c00eed9 | backend source (other) | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `examples/python/NiftyOI.ipynb` | text | 50081 | 79e2638068367085f508a60545edd92514ec36e4e7cc8f92bbd3a909fffb01a4 | configuration/other | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `examples/python/backtesting_vectorbt.py` | text | 12460 | 25115325e7877486049faafd2e2e0344cc2f0d7eb3ddfe465beab11f400b65f3 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `examples/python/broker_sdk_downloads.py` | text | 3206 | 9d16625f40a73d0345e0b134599e5b00858025bbb1b2a03500303a233f9ae6fa | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `examples/python/cagr_heatmap.py` | text | 7194 | 7b0b8cd6f76ecc97139d0bc85471d29d93baab15e9d006c40e617b48c0a95b02 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `examples/python/data.ipynb` | text | 12024 | fc981fea0f9a87ea37535a332613bc5d8f5eb77b7ac8aacb7fbb7898265794aa | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `examples/python/depth_20_example.py` | text | 1564 | 9297caaba086b3258e484671525922bf460a400fc53f16fb7d2e7cedd5ce79a0 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `examples/python/depth_50_example.py` | text | 1518 | 3c7a7b16f403937d80b0e05d57aba1d9a2e1f02b55d86d98779e2ddb0510a2eb | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `examples/python/depth_example.py` | text | 952 | 741259dc0be17a8e0a946cba781c2c45bc9e6775fd0506dc59c12138e956a210 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `examples/python/ema_crossover.py` | text | 4800 | 6ddbd9e2522a9df628765452f158f35b966fbcae67d4c7a823ae5eb4d15a171b | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `examples/python/emacrossover_strategy_python.py` | text | 25091 | f6d6e6f1ab26e91290d9e9b5e77f9342cbe8b55043151dd3a93484e48916e489 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `examples/python/expiry_dates.py` | text | 5688 | 738cd50be6de18449517fe97552664dd4fa48b192ff12dd9934d2dd6a5fea069 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `examples/python/flask_optionchain.py` | text | 6699 | d10853c6a5a902961119ccc868cb037a4d261aca6dfc648d3995d68ca3631627 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `examples/python/heatmap.py` | text | 3364 | a8c101e6925ee0346c1c17ce0bcd481a42ad1d01a85e1f7f93a44db2d0671461 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `examples/python/ltp_example.py` | text | 957 | 46d022ffda56044799b50977ff289d849944eb7f2549831724f684bd3e73403f | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `examples/python/margin_example.ipynb` | text | 8237 | 8ccb0448225bdf2db96f242c6774d2c799c02c5384b525850f5d8deec0b04b30 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `examples/python/multiquotes_example.py` | text | 409 | 420dff3e1b87588ed331e5234fd7998537166e0e43bd6d8bccd16bbb169e7ff5 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `examples/python/optionchain_example.py` | text | 1709 | 2492dc908aebb8320cfa931c05c9ad8e06ab845dc24bd3de331d89cad1498a9b | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `examples/python/placing ATM order.py` | text | 1160 | fd829713028ccdc4714eb91517e9b24d62d185e5864e057b633988fc5e591cf8 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `examples/python/plotting candles.py` | text | 9746 | d1ddcbf1145c7587ae7339e8cee0ef05b2aeaadb2fa12b0529fbdd973f06ab32 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `examples/python/quote_example.py` | text | 1041 | 318d24da819c4e237a262f387cc2e86816ccb226e2f81d4ccaa45eb04966d083 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `examples/python/seasonality.py` | text | 7325 | cb4bdc264058851fda8691568f9a061ff6fccbb0af8db74cfeda6687642f3f50 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `examples/python/stoploss_example.py` | text | 3670 | 91afb84f4e81fede17b9d244293a109e36a7f7192991c94813234653c3755101 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `examples/python/stoploss_target_example.py` | text | 4388 | df8d946e161585820945fde57dcbc0e6093c5aaf6f3cbff2f48c932308dbb6f0 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `examples/python/straddle_scheduler.py` | text | 2456 | 8b81a83239b89bdcf4219f8a785a6167914a19dfcdaf4d8ff7ceea8d24fd3f2a | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `examples/python/straddle_with_stops.py` | text | 4528 | 163a15d7c55f8532c36febad9dfe4f10199f277ea662a4cbec9d738f79cb5236 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `examples/python/supertrend.py` | text | 5926 | 4e77b7a331f387c05affecf4b3e7a010c24256b4cc829dfae6a4a655f0ddb180 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `examples/python/test_2340_symbols.py` | text | 3974 | c8a9c0e84371421fddf23febb7a9d195fa60ff13f514a7c457b8d2cb36cde3f3 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `examples/python/webhook.ipynb` | text | 2743 | ebf6533e155b4459405d7c336fe13c137cc03a53dee66d4287b612daf5ce0fb4 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `examples/python/whatsapp_quote_alert.ipynb` | text | 6107 | 64ba6941d0f91fbf026dfd8ed3c12a421e859096f5fd8d3ef90194a574193f67 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `examples/python/william vix fix.py` | text | 10697 | 1e34f037a9f0e354f871f3040f80734d9a0250d74069562e7f9428aff8ed7490 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `examples/python/ytd_gainers_losers.py` | text | 2955 | e5ccfa38c25420a204642b8862da21824c314509fd4c97a18a85f788b794ff75 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `examples/python/ytd_heatmap.py` | text | 3109 | 35230c2e31322ae49989deda4683333ad8f779b857fcf7b3e675323b19663445 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `extensions.py` | text | 7022 | e700b0546d936b374754604b40fa9b34447eea8f5b429baa76a63f7d784e8e5a | backend source (other) | INDIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `findings.md` | text | 5606 | 06d775481ac049f581f5d23547b5e3fbf88bb16327a91e99b32b0632f12240fb | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/.gitignore` | text | 382 | fb400200c3ea73eb4768f47ba9f055a7f00fd51fbe7042d04294483492308abb | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/.nvmrc` | text | 9 | 7c415154bb9f8e90394317c7109261249d2c4fbd549008ae6d014ee565ee7967 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/README.md` | text | 2628 | 2428c4c18f14c5809f8e18e24bb7a1a4c7ccedf238406d9bd901364e47ae4206 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/biome.json` | text | 1739 | 9fab6f753bbd32307dbf62d2581dedca985e05cd63d04028feb0d766c9814fea | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/components.json` | text | 468 | 265a8e2ddf7afd35ff1cb261b05e369574e191f433763fab4ccbe534ecd925fd | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/apple-touch-icon.png` | binary | 16784 | c9dd2ae15f39b16cdc7367d252e54ee1c68313296270a553ef0c7f692c403662 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | binary: type, size and hash recorded automatically; content not examined |
| `frontend/dist/assets/ActionCenter-D0IVWLjP.js` | text | 15926 | 38a3767478df4f989a3f0a0ce2d1a6626dac53eeb301877ef4386bfcad05fd40 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/AdminIndex-DzXvcdrm.js` | text | 4969 | ca919d5b7a2d7beff7572506af247010585c8823bb432915b6df772c18c20473 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/AgentConfig-CwF3AE85.js` | text | 91073 | 5b193777c9b0028aa4af7475e68671e3453de3d73aebf8cf14a421ec9d8dfdfd | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/AgentIndex-0mPp2P8R.js` | text | 28406 | a4140e484dd503648d7a4ec9fa9a171a69e8cd60b6a8841d607e5119d0acd3c0 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/AgentPanel-BsKdhBKp.js` | text | 4437 | ef18e85554f0e87c0752be389d5301891059a8ee1368ea684d8f463decd925c7 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/AlertsDialog-DdmkyjaV.js` | text | 8666 | 2769d54697970ea712a553fcedd30627b6aa4dc15fa79839a068e0038a6e8f4a | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/AlertsIndex-BiMMRN3z.js` | text | 5333 | 0a3d1c512e1accc8bca506bfd542d0bcca30699820f78408d65a7501a2d8a2dd | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/AlertsPanel-VMULJHS6.js` | text | 10850 | 021606b6016687ac3a152f0356720473bd88efaa10bb44648712807f4222187b | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/Analyzer-3qLahCkF.js` | text | 8876 | aa988fff9fb2935ad9d292f568eb9c109536344f03d39bdb8c5afe4037b66f1c | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/ApiKey-lmcCWnLa.js` | text | 8807 | d395ae071f9ab37f85adf1078c5a5ac1b999e845b47f586446d0f65646a70451 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/Arbitrage-DQgk69T4.js` | text | 14723 | 2c28e3fa55dec2cb03a308f288178b4ff8055c2889d3d4b3fb2b903bb7e54657 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/BoxChartSettingsDialog-cXrig4_6.js` | text | 9451 | 92cb3abf7ae816534a0d4c84b73681e8a46ba117c2a91a4a85ad1839652dd7a9 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/BrokerAuthSignOut-Ba5ZMt0u.js` | text | 902 | 741460616b9de587442034cae5c832c97de6f2ab0adae939567f8bb967244905 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/BrokerConfig-B-2MKL6I.js` | text | 8769 | a5648fc0e9fc76960e553636c4e37fda8aa59e9d74e9f3d60719e202d020c773 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/BrokerSelect-9erqBKl0.js` | text | 7540 | d21c3959e51e73db824367b7893a4070e1f0e95035d6ab73cdda426df800de0e | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/BrokerSwitchConfirm-8-FkQ5bS.js` | text | 1388 | 955c462fba2df140064d9d0f2b89ed14bcba1f0900e7ab5d373e5334f6921f0f | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/BrokerTOTP-XIH6teep.js` | text | 11072 | 8e1c07c1a2e155d803748504da31eed988cff0b46d25a4e8a786088f134ce2b7 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/ChartDataDialog-Bwnk_jMt.js` | text | 3124 | bcb8ce131ed6e5d0a8631a8cb3f967a01c17fc155a808a630460fc8197eb4baa | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/ChartSettingsDialog-wDPW8s6H.js` | text | 5500 | 87b446f77a9be2ebc5341e71f39a610baaa457bec3ad0369d5d45dc3acd44990 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/ChartSymbolLink-CiHQqRDM.js` | text | 724 | 4bb269611b966275ae2b70918d0ce88c91db4b9fdb98665f22b14f65e91b48f9 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/ChartTest-DCzETTGb.js` | text | 8213 | 94df6948bb4e5d56374a82145fa6d741db691eff0137b8cb660f3d30d862042d | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/ChartinkIndex-zn43JXUj.js` | text | 8215 | 895df6b86958c201b5a475a854bfbb273ddebf9b038f7c001ba7cd10c3931b3b | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/Combination-oHDiUB29.js` | text | 25242 | 9ec8b853f5b234e630d82edeeb014ffd4ec0da128c7f5ca8e6fc081cdcbf4b66 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/ConfigureChartinkSymbols-9AmERU79.js` | text | 10250 | 5d8a55c4ffca7b3869f0b70a6f95199c91f4d4c2bb5bd5e998ad53123ec7ed6b | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/CrisisChart-CWYkCogy.js` | text | 3910 | 8c70ed908a636b80f18b1a726c0d68653a52a5f2c02ab61f055c70c70a6abdc5 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/CustomStraddle--m8dXZF7.js` | text | 17783 | 40fa6716239acd8be4dd7f789389bac972574f6198d84b6423aee3c6b51cab42 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/Dashboard-mBNBEALM.js` | text | 9959 | 34547ced81383e03486ffff65efe01993c9f039f6e5ce9e670c307ceb7f5656f | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/DataWindowPanel-BKKwNmAl.js` | text | 1493 | 14f8666e206fece40100b5d0550c2a351d939015cad9f2d14ef38d42b070e012 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/Detail-B4_XB60m.js` | text | 64059 | 229ee130e5d4d0bc2b1a8749ed6d8097d189693265ef50551a366599e737d92b | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/Diagnostics-CSPxcMKj.js` | text | 21202 | 80da23605a4029aecb6a8859ea12611263cb04c8111637833e0faa6b80f3c48a | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/DiscordPanel-CE0jEotG.js` | text | 8446 | fe106fe6a6e7c78b93843e149e68b0f30776941e956fc57435e266014b86f249 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/Download-C2g2T8Hw.js` | text | 14851 | 8d2baa5c630ad7705d704788ae2446c7c53ec4280ee434ffba41d16622569f72 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/Edit-BW2ZA_gJ.js` | text | 1253 | ed2a289cddfe2446fe7f7f6420c3828a37a220b00d1424db592b469927ace863 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/EditPythonStrategy-DYP-CGxB.js` | text | 56686 | 219e8cd15deda5731af1722a966ba111266f9b44d066e4529c3c1ff3a39080f9 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/ExperimentsPanel-BnNzylRY.js` | text | 8343 | 564eb38083ebf5d98c5cfb2f595683cae6dc2b113cbabc8b4cd75616f69c5cf5 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/Faq-BY9M414N.js` | text | 14135 | 2d951ea59fd43b8898f2927395ee1a75b8fd383da5fd18ea9feefcb91cb56bc0 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/FlowEditor-CHpVij2M.css` | text | 15395 | c0bb205e5947a876f05b696f066a672180d980fb88cb81c80a51fe0fab4870d6 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/FlowEditor-DWF9qTvT.js` | text | 426665 | 2de4687944603ee3fd9de560c31ed79c4a8635a538b7981a220ed25f3b857655 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/FlowIndex-BD9OUxWY.js` | text | 16985 | c785d5be1ad714d5af1e31295e19e4d32a26d058eb9d6280328f7c49fc182370 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/FlowKeyboardShortcuts-BvuPf1cS.js` | text | 3586 | ea5710685dfe8f65b25912a643fbb6b1d4b748023cd7e61702b2ed577ea239f5 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/FreezeQty-Dqi7utFN.js` | text | 10521 | 91a732c505c6aa5e448ccdce559bf99d268876a8b57efd922a8aa78a35245d05 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/GEXDashboard-zKiC-GjT.js` | text | 14661 | 6cf222e23e81ba81feac01e64b00655f94dbcb73b300b1663ddd8a3ac1656c73 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/GammaDensity-DaVPB0M-.js` | text | 10192 | 90253c1b137109bc3b93822cc4316135940f68951ff024646232c0a38232cf26 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/GoCharting-CaBNNUp8.js` | text | 9045 | 1bd2e521050dafcb3e8f4b877a7c02b4fbbc82f665bc464ccc13c365c688de74 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/GttTab-BvgJGslX.js` | text | 12815 | 6cb9845d29098a9f8873406c1410d0ce0c65bb12978011139492711ae0dd2c4f | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/HealthMonitor-D6HvbBeY.js` | text | 19289 | 9693c1676e7ccc2f1f3b3c91e909672ed3030b5461d5ec271474073fa82853c5 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/Historify-D9WrDe2V.js` | text | 64907 | 75d3bdcc728f87ee31f4d672a434e7350ba16be2d5b35b0de0334fe90fa0e6f1 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/HistorifyCharts-Bl65_IYJ.js` | text | 28324 | c2f57c31910bbe58bce5c959738efb7aefff93ba8fb17d33a55219ae95aabb27 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/Holdings-BT31zN5S.js` | text | 9051 | 441578876b01a513e06eb5343bd50b8ed11f3fb72acf75665ed42a7e44c503bf | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/Holidays-ENsajLEi.js` | text | 12517 | e9248cb29eee3b67c6f1542d402a834ff8967e495559af206ad7f4e5727a540e | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/Home-fu9oB91p.js` | text | 14939 | a3957721dbbc7339cf630e4d2a411b436bffc13614d37257daa07f8a42e934b7 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/IVChart-CIpGUrIG.js` | text | 10192 | 7272e3472c693ecec50db377eea1dba410265806c4a3e6c104c28a7185338021 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/IVSmile-g0yKcxz7.js` | text | 9726 | b5a404f42cc5bdbb244c263b0d0cd9ace49444764f07e51f94f7f93456d0372c | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/IndicatorPickerDialog-CorBk2BG.js` | text | 6987 | 872677b7ca5f59bec61c4493606cc8b55bb16bb61f8db82a84bb9ce79e25b153 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/IndicatorSettingsDialog-BgMcqyer.js` | text | 16862 | 9bc11ce05ab859543c848e07d453121e4c240775b3139945d4ced7bab6964d7b | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/LatencyDashboard-DMi99Tl9.js` | text | 18951 | 947529ef4969b6139bda784be7017163d5461bd8cdd2ec70c57c10399b1ba229 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/Leverage-CL-FST9H.js` | text | 3111 | f815b060b771aea2fd461c2f6059569129ad2398c9c66985188ad09a6dd69e95 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/List-BxCBz-6J.js` | text | 5301 | cc809875dcfb3dcc297623ca5589ae39873bf92c35aa1facdcdd8d398a93cee2 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/Login-2Spon3Ej.js` | text | 7955 | b9c976588e7f557c77786bc59a646503e5ea895900faedf1117795caff49adf2 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/LogoutConfirmDialog-FT4-RFOw.js` | text | 2247 | 1ab5f62eb38196acc5202ac6823f6e62e3956653bc680fbbde9654be22a8afdc | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/Logs-D48Am03H.js` | text | 9460 | 1dc07b251e2a85fb69070c287256a51391f8af78227c1fb5c3c7b9d29453d154 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/LogsIndex-CYpxZTNk.js` | text | 3138 | 603355cd40f176abaa6e31bd6a32123716b9aea6e16fc928fbcc8035d5b5bf8e | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/MarketTimings-BHjICGC5.js` | text | 8335 | 4061c0d31ee24b2a28a3b44ebe732bfc9ca2afd5be40f5289b399ee20ee701bf | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/MasterContract-BnD-4_k3.js` | text | 11630 | 3a1c4187f269974ce071e0b2fcbab4bb56b8d3f67baa14c5a4f0a041042fbc92 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/MaxPain-BKfvcHpQ.js` | text | 7355 | 71ecb1894a6771125c3c7593edfef8cc16874e96eef0e4b1df679f9803bb2f57 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/NewChartinkStrategy-Cqj255kN.js` | text | 5587 | db23f2ff5cbfe3ec68b29e916441837a7312afc6775e5cf28a94b29e094a50fd | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/NewPythonStrategy-CsoIog8n.js` | text | 10815 | 714e00f8129ae449d4c6d588a868f02e3ccd6d11f465107d7255807e0d0f5a38 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/NotFound-DAY97a7T.js` | text | 2685 | 42a87b0f2fe613e04fbacedde70a66c23501fc3953ea07678c83d832bb180078 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/OIProfile-BihQO3ke.js` | text | 9589 | 0c7671c3409c933189a99ce1aba476f824574e4663f74ac8894770c2f98230d8 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/OIRange-B_nxAeQS.js` | text | 12486 | e559de03072c7a96d6dd8f2c08d5e4304951552a73a8199b99b9122a02eba8ff | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/OITracker-C9zExVuJ.js` | text | 7770 | d3572db3d4be70dbbe7115c2d46f9a79229982c31ee41fab26dc01be64f32e5f | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/OpenAlgoChart-Cu3ohMU8.js` | text | 7931 | aa1f1ca81987ce2056f091b22570343720e64e6c9cfa6b94efa2786d65a93bbe | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/OpenUiViz-BYRaNWQ5.js` | text | 1959343 | eb0870869185fa843fd1ea2eb425950dea7968a1cdcc5e531cc10743036839e9 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/OpenUiViz-DS-0klc7.css` | text | 221801 | 168ab6690e5a0ba5c077f68c1cb66bfe6f3459fb160a949f65f0bb37cb3f5a54 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/OptionChain-DSqTaPf2.js` | text | 31163 | 00929efb4bccb04c6811a4be9eab7b0905bde682fe6a0b1a4171feb3f67a7520 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/OptionChainPanel-DBFJgYC6.js` | text | 12957 | 232699e4ab4bc53d51c0d405f9634f8dc66c35d11fd96255df4b368dd86b6938 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/OrderBook-C0t-ywj3.js` | text | 20486 | de7c0c0c9eb00087f0c8a24ef8d38a8da4f505d8b891d0c24a19d23ab60c7f65 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/PayoffChart-ChSE4Zt2.js` | text | 8939 | 89519f32241adb3480ec5a7d3688ae15704d00a24c3f7088929317152eebf9f9 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/PlaceOrderDialog-BFEsnMRN.js` | text | 13893 | c370d85a55e6fbd5bf2f5fa9d5bd75799685f1e2c8f3acde9252e337e482cd6c | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/Platforms-D6k1hVnb.js` | text | 3050 | d0fc834eac1328afd6b3476b6ec51a38c8c9f141d035512109e3f89f2ca223b8 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/Playground-CZMOdDhr.js` | text | 43502 | 4f5c43e711d8ffe4c360c85aa28cbcaa5a4e5cabe089a92e025ef2f1459707f2 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/Plot2D-CmbCOaxQ.js` | text | 57750 | 82dc0fb7c0d0d2a749c8f5d1efe26e18e046880f6df46217854c1553c2ec457e | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/Plot3D-_wJV1oxP.js` | text | 561482 | be11b9ec1bac3775936139a244fc33cfdb2bf72ada23b5021b5c2d4eb245aad7 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/PnLTracker-tTeqQlx7.js` | text | 9483 | 92f054a9b04d0a2eaa4cf4ff64cc69f366677aa6829edb092a94b9053a96857c | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/PortfolioAnalyzer-DgSdQU8T.js` | text | 12927 | bf14012dc920c993807eebb34ba36bb6a830b32c079adcb0c7a37cd804d6a238 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/PortfolioBacktester-D51xLrQJ.js` | text | 8290 | 34d826efaffc33b0953f56a1b0c63a530a6ced852f5fd53eb62aadc48c3d3a5c | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/PortfolioBacktesterResults-tMU4Vmwk.js` | text | 58141 | 80e7497658c0e6d9baaa14fa9829d7cedb642769aede2f9e7703d0fa5b1b2618 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/PortfolioLineChart-TtR0E3qG.js` | text | 2745 | 1561eeb578fcd5b64f97484cc4456544c187ecddc0fc57fa4829dfce0a9df18d | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/Positions-CXzheHgd.js` | text | 19044 | 8c2d94c80b3d28a3822831cddc89ea7005308d705db80bda714f451534dcd3d0 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/Profile-625GSM5c.js` | text | 55568 | b80f5b3d1f5c5c9d11a0d29c471132265344067a8cd63ea7bf2eef7793106ced | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/PythonStrategyGuide-CVzUxRqu.js` | text | 53987 | b564d77e6453ce9aa5c7cd8bffbee9f4a6863363c16a30f52af19acefec896b9 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/PythonStrategyIndex-Cm8EglMo.js` | text | 13427 | 37bfb355060d56dbe79c1ecc3fa4b7661cfe70a873add093eab53a3d5f0e363c | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/PythonStrategyLogs-Cj1pwtbq.js` | text | 11027 | 6c00ed04d233f3f1d2fcf776d94095d619ce612810f6ddbbc6a9e536944e6b08 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/RateLimited-BDgUxjgp.js` | text | 3490 | 34254ccf44bdd0853c3d7179d45d4655f269e1aafe1e83fa7a10016d6381f52c | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/RecordingsPanel-NYzuapyH.js` | text | 6688 | 363acc6ac6bd134e1cff0985f6f5d3e4698b855e519423efb2920c64476a11f3 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/RemoteMcp-Bgbx1Odl.js` | text | 20732 | 14954a577bbb23267cf064e839543771062d0baa5302419b3d55f9a8d6cc5eb8 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/ReplayPanel-CZs2RQnL.js` | text | 12108 | 9fe054adde9e718007565991f6f445d737272e33523c7e4c295d82cd66b044f2 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/ResetPassword-B8ZpQ6oM.js` | text | 11192 | c3e8168c5ee01722c28ea347c8123eefc0a5178f625d6b20dc0d2e8ae3bdd041 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/RunAllDaySwitch-CBKmEVFm.js` | text | 828 | ec2266adf1e428f93ccf11c4c4bf1e637c031af21b2084fc8733afb7a6a8bcd1 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/SamcoAuth-D2toGr7h.js` | text | 4977 | 2835452d88c1c72151044b12c04f170c355fe1c67f2cd39731e296dda58f50aa | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/Sandbox-EoEh21ex.js` | text | 9262 | eaa076af70bf45b6aa9c1044e583cb4b880824f33251db1073f43de4333f4e68 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/SandboxCalculator-7zswv0tS.js` | text | 8937 | dae737ba00e7ce8f643039e4ae3139831e4cd773d38af487fde1f350b339fdeb | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/SandboxCommissions-dl7sAgQZ.js` | text | 19648 | cd32dbbf9b2e9103ca586f444fdbbef81f378b0b0982c9f0fc046bbbb4107851 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/SandboxPnL-CtPUqKjG.js` | text | 14565 | dd92d766ce6461f15649ca4490766409dc7dac9f2faf3987a2d8dd05f207fd8d | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/ScalpChart-YkUa5VDb.js` | text | 5793 | 16f61bddd56548630d5fb0d19cb34bd3419ad7d81b62a9a1a6f8165bf75f2c72 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/Scalping-_iLybF8z.js` | text | 42967 | 4b83db154f33e04a3da2ba5cccef160427067c5e8856c91181479960470bbd07 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/SchedulePythonStrategy-Bj7aPiu8.js` | text | 7348 | ce88dde40d2cfbda1c477ca9d27a93b4ed54d2723ae54535413f8ca70c0ee6f1 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/ScriptPanel-CVP-agjT.js` | text | 23924 | 86a3fc5ccab6b29ddc0020ece7e5e65a0faa431f4975f9ff564e39d2b535105f | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/Search-OEYVS5ko.js` | text | 10716 | 70a035d413c27bf16ec7eb2246c79ef45271a7c19d853f42c84f43f606bce6a0 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/SectorRotation-CnqOGQJD.js` | text | 23909 | 200fd38c0817109afdff9630a62ecc79de436b9592a2ee746b6cb9965a0b0844 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/SecurityDashboard-c0Qav-Te.js` | text | 29521 | ae7b30200f1bcadcb8a5665be670e30b4ad63ab8005077850dc3d1a939a16d3e | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/ServerError-DFJR9089.js` | text | 3876 | a53eb3fa233edf9f49264664c069c6797a30a7c52124a26390cd4333cf07ec49 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/Setup-Conv5DFd.js` | text | 6136 | f757250ed049101d568a51d875bc419548241e8131d67982e79bbb5def72d353 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/SipBacktester-Cg5HQIoh.js` | text | 8164 | 1d9386b3c74809382cc73743192dfc222a52f1488e3be457056ca99897cabbef | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/SipBacktesterResults-Bo5-k2Qh.js` | text | 20403 | f6b7698dbaabd879e08ded735fb60c5384e7b17dcb9d7e360214bb6d19be921b | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/StraddleChart-BV7oHfe9.js` | text | 12704 | 06744967da1bcebb99d37679069edd02ca3e87131e00acf11311ac5b059851df | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/StrategiesPanel-BUVkGfMs.js` | text | 29398 | 22bcf9cf57bf3bad083065dafd35cd8ba74183f65d958a1af1e6fd662a010f6c | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/StrategyBuilder-C8ffRBBh.js` | text | 142051 | 098cd32060060aeab605443d8c41d3ea43fc63e19ca5300daa0fc59714d404ae | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/StrategyInputs-A-GfOww7.js` | text | 5297 | fd24d848b4a1ce0fab0568f1f9e839a9ded8c8d0f4a778288644855df4e679ff | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/StrategyPortfolio-BSb-2smn.js` | text | 15908 | b17e967ab19294d705972099e73ccad365c7946dcb064b78e2737cc2e2683297 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/StrikeProfile-WjK8QIys.js` | text | 18092 | 712ed1c373cba43c81fffa9025c9ed84f6b402aab653960dbcd5ed253ae11251 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/SymbolSearchDialog-BI3ad3vi.js` | text | 10837 | 46f43ef8113541bff3bee07549b7f5467b3461c4aa8442b2cbf6bd55128ef6df | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/SymbolSearchInput-cJDb9yDg.js` | text | 5227 | 8944cf5f183d2273416f0659552c57169da6c940bebc97f8b49a3d86b88886e6 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/TelegramAnalytics-Btzx8euY.js` | text | 7612 | aba5c914956922d3aeff1d20e891c1cd6051915a106814967e35f7c85b6f4bb5 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/TelegramConfig-D1qIu07b.js` | text | 8692 | ccd9aee8d69b1851f3378fd431cf32b2db5a36a5b5fbf08fcd9bf61553e25f1f | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/TelegramIndex-Db56rrV_.js` | text | 12122 | 69859d178d790b1e64cf21b1cdc138c38d48275acb244d0d7a1d66cd402516e3 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/TelegramUsers-f7Rv7kjM.js` | text | 8511 | e199fd1583646f966197e7e431c583bcf80cd245f93520af59b99997f84665b2 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/TickBox-Ci_1nf6_.js` | text | 1113 | c39b38d04a4161a70a5bee7a43e7a53043513b7bb302c799024bda82ed040758 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/Token-B4aJx2AY.js` | text | 16344 | 375ce11ee41c04e1c620bf27640acec7bf1d72d33db9eba3f1ecd081e371de2b | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/Tools-cjCHDIDR.js` | text | 1455 | e1fa08bfa96c206d3887e99eb333ecc32524d702ed4012585de8e67a94f5bb5f | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/TradeBook-BhmTZDMB.js` | text | 11276 | 6d1ec043765904f3b15078ac4d809aa9215471e46368747229fb0c4193682af7 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/Trading-Ca7GSZui.js` | text | 456839 | 2bdbca0a61539b824795b2ffd588af84239b008b2272d9aa7e9586d317302da2 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/TradingView-_Eh7u8UF.js` | text | 9211 | ea512bfcfee1b65f1cd00c0cef3a590192e961782cb5837df472c2bd1fb5b103 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/TrafficDashboard-0jyPm4Cx.js` | text | 6890 | 41015a6404fe4037cd4de42a82e3cd4d4804d37f98acbe8a9852e70b91ff4e42 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/ViewChartinkStrategy-DStWqqXB.js` | text | 10357 | 915f537437a3e44a6dfa2fd835ae0d35d52a9eab8c1662bf9dcb13e373238475 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/VolSurface-CZ8kLxBD.js` | text | 7887 | 8bff5964fdbee115b2a8adc790337d11ad957eecdecc9bf3b869fc6fbfd6f1a8 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/WatchlistPanel-W0z9Skuv.js` | text | 18014 | 22c17d48d5c7dcbd255e30302149af4b327cb3999e9f71c7c03002eb099f2aae | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/WebSocketOrder-Buxo8Qt8.js` | text | 15182 | 0b51b035268a822a6a51f390c715a61808006d7b4dad2485fad8a28cffbb31f9 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/WebSocketTest-DNfdTp5c.js` | text | 29268 | e6fe647b37ffea14dd2e8d93c7fa6827e21204e8f2cc027db4c2e1816eadd5b6 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/WebhookChannelSetup-BxoNSE-m.js` | text | 6046 | 5e84a028f375a4744fc588522b13afd0ba7b03c17d118c6a4c58f94378e8db89 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/WhatsAppIndex-DepD6x8K.js` | text | 8427 | ba25121fb35258fd7555516221a9d787f35b858a5c44b34f4497d7e340e7b169 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/Wizard-DHChM2AM.js` | text | 40127 | cc295f38c3bf9351c03de10c3b8149c8013420f30537b459c43d02dbea2c6e85 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/Workspace-BA9K8qnR.js` | text | 64822 | 6ade0ce13c886643019ba47b7facfe71659ee14704e0f269c1c32e5188c4dc56 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/Workspace-DVmfi6EF.css` | text | 5998 | 05a6a7274a90191d12a593fb42fbd6f3c197cd1448f0585be2e12948680a98f0 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/accordion-Ch7aJtmc.js` | text | 1122 | 0e8eba542db448a9de7472c096b864f72805f42332870c80d03f8296dfe32c4a | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/activity-CkTnF0Uz.js` | text | 234 | dd9ca570bdd715169d397e5e37de61fab66eb7519b489c4cf8b6508fc680e197 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/admin-BMpeMbsf.js` | text | 2707 | 71cc6eff379a8c965d18aed8213ce7539a69debd7ee2c52f87d93524f996a797 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/alert-0S80sd6Q.js` | text | 1112 | 66eef7c05fe7eb7a1f4ca6b0bb14c5903839ce619ba46089605fd76f0b17ddab | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/alert-dialog-CxznvvFZ.js` | text | 1842 | f468de5a14c6221e0e48159c94aeffc3c7df0a40ed7aface0ea8af82257f5e6c | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/alertStore-DkAcAr5k.js` | text | 33669 | fcf74af0de81635026efc29ff4440426e4d9488087e872b00fc91080b17800c1 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/alerts-DRJ1e4Vx.js` | text | 617 | d52243a74d9321919978394d83bc89fd1842c1ec750b77b7aaf6f8cc394280af | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/alertsModel-DBKfK47l.js` | text | 10545 | fa587c0cab9574061ea6ae699d1be2565a5ae60b88c0c5fa9e27d7ebe87ca4af | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/arrow-left-Cy6gG-TD.js` | text | 165 | b4b5b867cd02095f72f3ed0aa515ca0445401b3c953914f2fd4b9b554fb79503 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/arrow-right-DsWEetDq.js` | text | 165 | affd4e83470151a3f7c282fc094d33d94ed8e8478c1260d619228d4d3398af03 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/arrow-up-DhmltaHw.js` | text | 274 | 80d9242368a3ea6978e098dbb7f99548cf03cfdeda2cb075398b1a3121bcb385 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/arrow-up-down-Cmv2X7ld.js` | text | 245 | b2b02db33e0264956e4be6fa0419d48794580b58003220de8df2bc4f20126733 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/authStore-B9OXFg4B.js` | text | 830 | 27af498219a998a57590eeb619a79c5bc18f69e06a0c2326c72d1b4782208f20 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/backtestWorkerEntry-D_6SmTj7.js` | text | 482450 | 54f7f074352f02e4b120f1eb5032884320e02b08f081dcbb37758a345083b70c | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/badge-C3BFb1Ad.js` | text | 1242 | 84de29ba6c4b6da83afd2de2bc9221b0622265d817b5f8cbfb54d0a5f4c737c2 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/ban-BqU15T8F.js` | text | 181 | 23cee77daba0e52c6257fcb996ad6ca922f6a08dac6cd6f358893ba4fcff920f | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/bell-BYVXgYpq.js` | text | 290 | f9c037fd593228945621abfc785dacc31f0500ab5d09e38c65058e92dc079e36 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/book-open--2jVZ6No.js` | text | 279 | bab141ecb6fd7a15e2c947c62815aa350458069b69140ad41c6e8d7090a2a5e8 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/bot-Be6jiaI8.js` | text | 328 | 90d7a0dce58861c1d254f15fede63e5611e582ee26e452229450c16110f67c73 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/bottomBar-DLCyICF4.js` | text | 5252 | c791470c5db070e75c78df2c6d88b71377689220e2b18cbabf5d62e783b8e313 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/briefcase-BbSg7fpz.js` | text | 220 | 8adc3b518bb3a03d51ab392151a7a5572bdf3e294a4e73facc321d5c45b27b01 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/brokerStore-uHSR3GjB.js` | text | 407 | 887722100ce1b62a4f48646429a9c1f17a8d639c7f44a9dcad518c3dab8f0429 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/button-HTrZcQG6.js` | text | 1701 | 49838523d3d1e098fdf593e0a5275042c20a7d49d6b2f8612f5a0d63d82788ab | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/calculator-_ZlTpC08.js` | text | 530 | dd89b38f8d7ddcdbe37fc3541dba5502a71f3ec83756ddbbbc5887bc03adef57 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/calendar-HcMCJz-m.js` | text | 257 | 16a48648c62eb8926cb7ad4cd5be91058d45355fad6edb86dc3442352335444b | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/calendar-days-CPRhLxSm.js` | text | 494 | 2b95ab7c152520c7025b36daba77ed4eaea0c886ab75af36304958e9647381b1 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/camera-7YLqac_2.js` | text | 336 | a4a4eeebe11578765d15ee8ecbce4c9e9522f422d2a6077acfb6825abefac8a1 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/card-D1LPshfs.js` | text | 940 | 448442affdee30a8fad6b17e308ac7669bf8c3ec942d7b897466642a7e58747e | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/chart-candlestick-Dm45h_UH.js` | text | 418 | 500eccd8e7b93c6508a58a470269f13a590c81526e9a4620224c1800fd05a571 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/chart-column-B1pu-0P8.js` | text | 251 | 42ff48093583e77153175a19bc9accbf37991af2d667ea7b6b2599aa4ba3c630 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/chart-line-CbvSy_ui.js` | text | 184 | e925dc3cf568ed2fce216e9f2fc8489509da11b31983203c78fa74d28cec0112 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/chartLink-DLYTHgmE.js` | text | 375 | b4596bfe9563c056fa4692a2080819fcf5570d44ccb079c8ceca00cd4a0790a6 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/chartProfiles-4WItg4Xc.js` | text | 40406 | 79766083caf2b74d17238152d612f6896578c5022f3531023d24acddb583bccc | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/chartTheme-1dbaRLUU.js` | text | 3287 | 08a81bc50092c21d66484f29a2ed7981c3c389dcf6208f370eebce26db1f23bb | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/chartTypes-DwCCs5A3.js` | text | 36105 | 3e3333b630282f4886c3f91925b22091527afec32c66da96aefe32f6ddefe5e5 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/chartink-Di51QzRm.js` | text | 921 | 794501fe79c35ab65f816126b7616de2fb25098f19487f566cd61a1f5af28d2c | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/charts-Bev8G1d4.js` | text | 25375 | db1ffef5735f07e5df5f065adf1bd542c4040b10920dbd29ffd18b2f002fd865 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/check-DpWt5Haa.js` | text | 124 | 6e8661dd661a5fab246f808325e3721930a49b6c05d7a1b41676d45071d5c756 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/checkbox-BwPvEPXe.js` | text | 810 | fcc74fa6bafea9a6547bcad4517b1edaa8c4dfce77f014ed1cebac7793453d2f | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/chevron-left-CyG6PEgH.js` | text | 130 | 906f1c86a918c9916c47d660ec0bc480c4f879f81c580b3947f44cebf964bc98 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/chevron-right-BB0aszD9.js` | text | 130 | a24ded4082c64e904006f8d5ec28aa52eff17edd742e2b8fb2699fc0e8efd5da | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/chevron-up-C_Kzwu3n.js` | text | 128 | 93a9147639bdc3159a698a7b9d1d9eb7ff210ea6702fc97e803d786d1930ba99 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/chevrons-up-down-qdLo-sdy.js` | text | 174 | 3e01b32b7018d65bec0a6c13e0bca7f8361fb3a34ab505228a693126d78c3d79 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/circle-alert-BZjkJqnO.js` | text | 250 | d3ffea1ba9315a9ee581c16f4b7f30f973f9205ba31a1ba5c08e88d7f0a22e3f | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/circle-check-big-Biht8GqT.js` | text | 194 | 221c36c611cff0a4b95e0a581522574a5616a9259b60346b4d5334bb8e486a56 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/circle-question-mark-64M3aWpG.js` | text | 248 | eb4837b9b45afcc3f42edef657415ee1acfe81910eb3954407dbc01f903ddd39 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/circle-x-BC4ShLY9.js` | text | 207 | 81eb4edda6b2a240c81b7dca55a6fa1fc2f0b04a3d7f576331d55fd46c491ebe | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/client-wf5xZPTh.js` | text | 51678 | eb5473222226ab1220a24bbef30ed61a6bf3a94199c5b30cf7319496f1f41fc7 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/clipboard-list-SuKyZvfx.js` | text | 411 | f96539b0f42f759d0fde41d98c4c5605357fcf362d312cc475e9a21abdf9028d | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/clock-D0YVZsfQ.js` | text | 169 | d0106d6804b8d6a727879fca853922e5dd1bb03bec348308f6b0e49320ff8f95 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/code-xml-BH5Izhg8.js` | text | 208 | 42db0767fca071ea4b274086db3708c281da0ca4e8eb71bd1320927ceb1d7bc1 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/collapsible-B5hUTcru.js` | text | 98 | a2ad2581fa644aada60c5e8ed1129df4518b25e9f9f89c763cc7049f08fa98c3 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/command-DkoDGSBL.js` | text | 13232 | d67ab4df388b58e99d865804ddf9d6cc9effc4edbce9c86233f1398e87d9f720 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/constants-BxEuaFCm.js` | text | 33973 | 13b03864962a54d5d4030271302ceabf551fd02b14e1936197209351e5271b4c | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/copy-BTqqbGsC.js` | text | 236 | 8e6f8c73ec572079ca209d00b6e39533e478fc6b0ac93ee5d95a21dcedb93e21 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/core-BS0xFFwT.js` | text | 1020511 | d7ade7d2fe718dc0d2e229ae1c813df2e2bc08031d5794040ae88a926e05484e | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/core-CJJi_dht.js` | text | 472633 | 90f5150f35879ba544bb27b55af940a68bec12cdc378514a8505af93c2a76251 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/core-CKRTiAqP.css` | text | 82869 | a44e9c8519685a73587bcb465401eade1c3491d382c22243373c1c42b766f186 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/cpu-DPPcf1af.js` | text | 642 | 8ff8855747bd40ae82d99835335ce129adecbc6259b77f99f58449d6cd0971d8 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/createLucideIcon-ezpVwW4n.js` | text | 1240 | 7f015783cc2280243e1b494da8ca093e2c788566c07e7a4bfde46e0981760ab2 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/customIndicators-Cx6gVLIk.js` | text | 6021 | 0a8aa515304e7c0f8691cdc2b8697da3ed2bb6d288e8b6c9df43483daa5c79ac | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/database-B9PNg4f5.js` | text | 243 | 1dd03854a39ece100d7715a76f73101de040dac86b6a5c10a6c390dc0a53055e | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/dialog-D4OC6IXl.js` | text | 2529 | bda23e683b0fdeb35d0bdfae335214faa062317600cb967bfd587485a2783ce6 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/dist-0Ncn8xoj.js` | text | 515 | 95ce868972608cd51135984adc05aa3eed21ee404df4702f9cfd67e4b5421e33 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/dist-0mJCKbLu.js` | text | 224 | ef8a5391c26f62f3848e128bb0a40930f1953dc80d71020f7a5ac2b854c117af | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/dist-BN2YMLjq.js` | text | 544 | e3e96e46e8c9f4716203cbbcf4e36aed1c90f2325a6de54594e32820d42f785f | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/dist-BQ9R4h47.js` | text | 4586 | 38bc03e9f6e6a79ea2ac52f5f954a11ec4715955287cb140d64754e9f71a8ffe | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/dist-Bd4S_96J.js` | text | 598 | aab05012a01784df28bd340e408d788a027a566c00ce418c1ecad0ec78b91520 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/dist-BrFNsU8-.js` | text | 412 | 40bb688c18f558a54b441f0a16cad0c83aa1b42a2c57d3e1a1a3402ab7e643da | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/dist-BvnWFe0_.js` | text | 1231 | b89b6dec421d76c4ee7e05c5c7cacf325dc5b513b00588553465478518ed3923 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/dist-BzPIIhog.js` | text | 10553 | dd0995dae5163e8333cd324002f7ae3118e08db1f3ff7c5407b50710c3937207 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/dist-C2J943E6.js` | text | 68 | b2d7d7e44fd1c0799ac1e13c575efddf3e7473a46876b8bb7b1bd70837c586ab | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/dist-C7FOtvjj.js` | text | 30605 | 6d5822d9885679e9d42c127e89bbe4e6db12ac1654dc6beb7136df63184b0dbd | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/dist-CFWLpIS3.js` | text | 23365 | e3b16b90fa53ab5fe1536e0d0d028dfd9408da30b4123bba9270f71fc27caddc | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/dist-ChL1So-D.js` | text | 1996 | 70321ddf3b1f526d5be5978001733b1d1960f748b3e5f2e0878c3510cfae307c | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/dist-Cl-rW76R.js` | text | 296 | 4ac825b974334579d8da1dd075a4612f28fe7e3409c6422d40b9b4d6c5a9d451 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/dist-Cp8zVAVe.js` | text | 6137 | ca2ba6b2ea5df911d1462ff9f0004ea44d86c6db50377bc6a8c7da525aa2f858 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/dist-CxoFDJBa.js` | text | 460 | 63b16002579ca9766a1336967ee9b306d206d5efd7117f73bd573a40c0ed2f51 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/dist-D7t71Z5h.js` | text | 20784 | 6911b8ec32297bf3815db3d85a7ab41430ade62c181fc3cf6019ced64138524d | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/dist-D8ZeP7XW.js` | text | 6318 | 39fb15b38d49069ef49d9e07ef3b2ba3cbbaade61bdb4e5f225a53056342363c | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/dist-DAFZc4Wf.js` | text | 8288 | 9c47352f3ac368d394aa81d7e1cb08b1c14e1d6fcae1e808a88610b6ec9f7401 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/dist-Dd5y3iv0.js` | text | 26302 | 023437870240596864a7834c0f23dc3ba7a2ef604363bc7a6da51dbfc38429da | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/dist-DrMlnKz8.js` | text | 5139 | cf95d310b70cd2dd872266948e6ffe7ebb53ac6e484da3f14c002ed2328e4f53 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/dist-KhN1CtAQ.js` | text | 2181 | 1bab2c301096a18a9b3965ac355fa191c0a8dbbdd3d9b2ddb462c8ed2383d737 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/dist-L6UV4v-H.js` | text | 2138 | 1b7b1be975bbfadcbdb0e89a8079467a58350bfa25bcc2f1256b506408024ee5 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/dist-NjQEp321.js` | text | 242 | 409146fb92391eb81570b0ef39506fdd4fffee60cf514fa48ba2b32a2a3e5f77 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/dist-PIwEhYPu.js` | text | 641 | 8022e6c03e2c8df1278a841291f8ddc87e853bf18f8298db8c849527adb4ed50 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/dist-Si-xRDpj.js` | text | 3530 | 5e03e4300809aa007efbd279b2209a0637496c817c03f0a76bc555df3f66db3e | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/dist-rBpUA6_1.js` | text | 6539 | 495809117ad022c0c55abdc0b0ccd40a8cca867b59e1ca982b90135f8d1ee0e3 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/dist-tV6HHOL2.js` | text | 4999 | b7f8e9fcb7fc544669eec461976dc29b92b41d922b317340f2b95bb8566076ec | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/dist-zSHjC3Cg.js` | text | 302 | 48fdefe016d63b14fec37a760a48fa59a33722bd9b0bc736f7ebc7b254de0977 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/download-ZUoDWjV4.js` | text | 232 | 1d7d9492e2b140548a10811ee013429d074d520bfbdc1e3a0e0378b2bce69251 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/dropdown-menu-Vdlf-Ejk.js` | text | 5139 | 0d49aff4387e7e9b0e28b3367b886311b65690ee15f6aebd7f44516d6068a61b | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/editor-Dt_hA1OG.js` | text | 1752 | 3577cbace8b5abbd83f649b340d4e56e9dd0a9222d3e7f8fb3f6c2bc883076b1 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/ellipsis-CvDFwQTh.js` | text | 226 | e552f54646724f1f4cd0a4aa603995651a28db8b374cca7f3fa134d58fc6feec | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/ellipsis-vertical-2kM5wjIU.js` | text | 235 | 9bb3b4aa74c65885b7885af1d94621ab49535bb4ba4d3d063a78e6a534d13f46 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/empty-state-JJ220Gao.js` | text | 438 | 99559b0d7985bfb50b33f6361e1df4a2e336599cc3690be9aa2294790f6d59ca | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/errors-uRY9Awr3.js` | text | 408 | 30341a21be577ee0ba4b30d6fa1a8e52307931c3707313a1065c120fa096edd9 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/esm-DdnYk2wN.js` | text | 406570 | b6878721ddbeb9043ed7b4ef553c25cbf01cf00e6466244d0326c2c6d2a47376 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/extends-C0i0KCCT.js` | text | 374 | f2e09868545e4f2bafe94c0ca903d8232c954c0dad2b4b219b9de280bca3639c | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/external-link-DyctbjmR.js` | text | 251 | 4d00a4a6a0ad14784397953b5470e1f102eafdfa79822452188212b83d221887 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/eye-BumAMVQ2.js` | text | 256 | 740f7f81d761350e9dc34fd5d59dbad9828c0f9843f7391ce7379588aa8ae920 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/eye-off-jio3Dgo9.js` | text | 430 | a0670e0175d42430cf31e46c363ba1345e270e128d7147ecca973ea48a341f37 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/file-code-gh35Vw1P.js` | text | 372 | 34359e47352b8387de2839c8ce7522eb33c50df8e8b28dda2020192949d07dce | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/file-stack-0X_WpsUU.js` | text | 373 | 39ead4520b90a8646233d5b8c1693eb15ab3f83a32562cbff130bd2961872746 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/file-text-CmTY7aWy.js` | text | 385 | 67c580d4050e6b1e26891b184ce5027bc0d23e1ba62ebbaf6b1a771823f0eda5 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/flask-conical-BDCgz9PP.js` | text | 302 | 8d23ad0d5bdf38dc19d89fcb26d3f31749ea1f0c1d09146d3bc419f095a84c30 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/flow-C1kekzQS.js` | text | 2219 | 292094aa01e438875a7f05774a225b8b1393904e70529f129c828876cd25e066 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/format-BtmU_QWA.js` | text | 683 | ceece602bbde93368cac0e31e886a909642e998bc0615126e5ea5adcd972efa3 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/funnel-DbMSypeu.js` | text | 256 | 9d7c6eaa58fdb36f53efb832a3ee0c6104967a1cb864ad58e14f95de05a41f2a | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/gauge-uyquSlM0.js` | text | 176 | d623de3704085ef94f87d182575d64143d4e0429710dd29e239aa00e680fb682 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/globe-Cz19bL_6.js` | text | 242 | 5b27c4d3e33eab7699212fc3e767ab159523cddd240081dcb38020881332061f | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/graduation-cap-Dd0zYwYE.js` | text | 332 | c0cc504da1759ffa9954dab25fe29ec542e423ad03291cdfcc52c791dd8ff9fd | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/grip-vertical-DW-BREmd.js` | text | 371 | eed4f874aa9a2f0f5f346117f8607587c10c8ff995f1830b7901dd59a8243a52 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/hard-drive-01E4TrEK.js` | text | 391 | 6a928de96162a691cd2e50f9cedf49ecc42f8fbed0d6425f0727ac5b94f6fb73 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/history-C9Wj62oa.js` | text | 237 | b43e7bfe2ef0742cbe169263acc0557fb986850b4a91fb288c6a1d183ff5c6f1 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/house-DHWeJyMN.js` | text | 281 | 4af02c7bc1a173514a27859812ead0d8ea0128ee1b9a50e7f9b50da3f2d3de42 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/html2canvas-pro.esm-BcOh49a5.js` | text | 206370 | bc76e2ecae5bb9c0c48946c08098c70ad0b88cad5ae8ce45142cd9b2b7c87fdf | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/index-CF6TBa4K.css` | text | 239898 | b2ab0cd03f3c347efaf87fb77146207fc10686dd223caa6113ad45936728981e | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/index-oPvPwIFL.js` | text | 141269 | 3b9e0fd3f1cbe39e0885faa7cd424727207e9a1dc6229f4ba47b1a12e147d6e1 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/input-8aeYaTWx.js` | text | 849 | 6665d3116291780c932714237143bca9a0ab8214584248d42e07f35e22e48abf | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/intervalRegistry-CdlVDuSb.js` | text | 733075 | 935ef7caef430126654a9c199dd668b8f6d1ed412621bc7491d44807bf966c2c | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/json-editor-CLeht8iC.js` | text | 4455 | a3624c233097564b94c34981a31f3e8515e0e250158ee62a703801e0e762bce6 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/key-BphqmdO9.js` | text | 264 | 786607643872d0987760211a377ac49d23ba7f1799bd8b1996979ea06cd5fa5f | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/label-DTvyJR5G.js` | text | 452 | 4a02625bd59d488d6b40aa50c260bf7a47fe158c5dc909c9a61b0364d959261f | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/layers-CnYexF-s.js` | text | 421 | 6656a6f7a0059be4627282f8ba2e7aa637ec8e1b9dcf62cc37f56039deb6d88d | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/layout-dashboard-ClM4kvOf.js` | text | 351 | ea812837468a1a43ba6936700d12eb7ad572606f53b19105f1946d12def841b5 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/link-2-C3IuXudc.js` | text | 242 | 64b8d0350a2e99f6fdb29c7bd527e2f260a86b6721ab3ed0fe20b2aebe534405 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/list-plus-CbMhDUWx.js` | text | 268 | e29ba88d71d0b18b43c058d0efee0695ad5f773b16efccf9079164fe08e9c0be | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/lock-Udagx2h7.js` | text | 206 | 7e202a84ed73679ebc8b242891d5a296cffbf9cc5d0de44587199ce2f890062c | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/log-in-Du1HLnik.js` | text | 231 | 4928b46d4959b2f859565cde17ea71f2c1d9207788614d48835775333d819843 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/log-out-B-ajpPuI.js` | text | 230 | 86ba72ea4e65db2cfa027283266da875ea15bac34a5bbd2c421efe4197422557 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/mail-D-ae-sF_.js` | text | 213 | 117f094e58e9db86882967243a017aeaf2f749e848f72de6ab07cf9107079512 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/message-circle-fg8xPSoJ.js` | text | 241 | 02163fa128ccac7dea6c1fca2953541e1afe32bac62f826628a3ee991b7913c7 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/message-square-P4vK_j2n.js` | text | 233 | e6ddb471a4f6d43f4693f13b5d6d604aa4db3c6863e6f57809b4eb1d3ca41ce8 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/middleware-Dy1wFKiq.js` | text | 2151 | e1ddd92062422c8b7ac886660864bb42922775a68670836497ec35cf57f228be | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/minimize-2-B4YF-pdo.js` | text | 425 | d755057ff60465de40c60e4e485a22c834b4c3569a4986c8988759fe7c187ea8 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/minus-BYho1s1k.js` | text | 117 | 39e8ebff6ba94f116dadcefc2cf5b7ccaa386f282bc8f6c28d353ededa1c7696 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/network-GrMdjpGq.js` | text | 384 | ae7ef603affe07173ed17a5063e2c0c68eb1d8e869b50d1befa978106a910ff7 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/oi-profile-ioHcsKej.js` | text | 409 | 22ee7da830d47f61283f82d04e5b6bae10c2bb76788303087d65f0dc2d4dd88d | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/oi-tracker-DPRCaAuj.js` | text | 398 | 7c2bf1a659241823aeecf6818effef09e677b4c07cdb41503fdeb5f007be599f | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/openalgo-charts-dG88RCVU.js` | text | 624296 | 11f26220ec64ac6bffcebd7c6d5c389db80f5f36e2382748b571a843c6f3d8be | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/openalgo-charts.indicators-DNZv55eX.js` | text | 197606 | 6a57a781c4a43155a4cefca7731987931c62015293982301c879a51d6baa43af | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/openalgo-charts.widget.chart-data-export-dialog-we0VDywF-DtmfOD1P.js` | text | 3201 | 875078240192664af64811fcb67169413db90fafe213acce51bf886cad7aaf33 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/openalgo-charts.widget.chart-type-settings-DYCCD4Ax-C0hMID-B.js` | text | 6607 | f1a30850ce595a348bd0e5fe7931ae5a3e2c70a50b741f5f25493186349c74be | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/openalgo-charts.widget.grid-bar-CWfujvFQ-Du_9hIHr.js` | text | 5622 | c6ca7ea0138f88179d970dadb209cd27d29a9dd06e0c74c6044240dce22abe75 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/openalgo-charts.widget.grid-menus-Ujc8dpxO-BLYA_F7P.js` | text | 9879 | f2161079b15511731a7aaac16ab00d2ddafd75bbfed82fe5163f44aa16ea0eb2 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/openalgo-charts.widget.keymap-editor-Uozy6qFE-Chw7-Qz9.js` | text | 9349 | b6c23c09c0e06461b2674a93d67cb1edc72905a5363bedc228ad26219e95dba2 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/openalgo-charts.widget.layouts-menu-B7XYKPAW-DsleQT7t.js` | text | 16037 | dc1a53e9e0c422cb5a30a92131a2d5aae750829cd45b501c76d6d2f199b6a503 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/openalgo-charts.widget.layouts-templates-menu-DPPa9Cn1-LGZJR3vd.js` | text | 6622 | 930279940639027489bb91d9a0ceb4933ca2f22974161e6bc8267fb18b44fa3b | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/openalgo-charts.widget.storage-idb-JzCQh1Se-CURk9ZUM.js` | text | 3708 | 3dc56a535d37a610dffa54d600b6257da714b2e91f26f86e947a8c06fac83ef1 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/openscriptIntervals-DEyk2kX3.js` | text | 1229 | ec7b147535b00f71b741daff4814568e3c5c9f7d8a6fc81eccc1c76c8705843b | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/optionGreeks-DF5Y6Sdu.js` | text | 2452 | 3878fa2fb581f5211e6ad8af45a73a57ee97f73ad4d0e2d3c245e0083d56f54a | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/package-B0boYlnj.js` | text | 372 | f9a2e04caf13103973baf55afd05cf57507dd32b81b0d851981521eb78aba0f7 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/panelShell-DgfvmAp4.js` | text | 2109 | f65d2228780457bf7e506e43b52fd2ae1a011785378877e1e32b665087561347 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/parts-DwdooL4q.js` | text | 7808 | c58431b8e9a7937dc81b9cb72f8c8ddef8c6f46e15ed43907092406a4f7b0703 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/pause-CimyrYGP.js` | text | 211 | 864a910d8732008e7500f30361e6e97de247123585289f06d07eda22b9f997a2 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/pencil-boEOmzw4.js` | text | 276 | 76708894303ba97263df273fb22af5985dca6e6ec233a2ad812ccd0eb197b7fd | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/play-CIG6m1tB.js` | text | 190 | e4a594f886f6918f34b3944ae013387edcacfb509590155e6546c2a12d51ce21 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/plus-BexkoNp2.js` | text | 153 | dc70e74fa59ab832946cad1bb02d179fe9f42ccd4bcacca7f46a6ba85e751a13 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/popover-CyV-U-fF.js` | text | 8345 | 4254e056437e2e2c9e65222c489eb5e66597054ac2830ea1315b05e5c40fd31f | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/portfolioBacktestStore-Clv1VD6W.js` | text | 172 | eb0bc6c2be6de66669c714096a3125740184e36100cd12f3dbf7454adc4ce9b5 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/portfolioRequest-1ZQ5Egv3.js` | text | 1714 | b8721d0655d769de4db1192a5d4a3bd2f333711d2aa6228c24d7ea894047f90e | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/power-BS6MnblM.js` | text | 173 | 8ea039025a104e49d13c5cf871b21323d756f64c97025da6617a57ec1baeaa99 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/previousClose-BstI7Dkb.js` | text | 1457 | 30676cf37ca77ff50d4a0d392bdc64a737626b1761d40c6120fbea7846469fc9 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/progress-CecgwQ1B.js` | text | 634 | a71951a40b0d7c40c1c3eb2316bab4981c81a47e06d0fecfdb639fe724c30709 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/python-strategy-CX8OC6KW.js` | text | 1225 | fda366bf1ea42e02f4cb35b62135e6435bac9c268aa699d59d2f45d4bdc38d08 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/python-strategy-DHEwVAQ6.js` | text | 1916 | eb5d5cbe9b80cc2c37637daee56823f19371757aad35274a1d15aa17d4d66535 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/radio-czGdapvZ.js` | text | 374 | 5130eb8edf939af88edd12d9c23b54e5558727c68491173a1650d0635bab814d | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/react-BcIZ_tGm.js` | text | 710 | afbd8502a2a89f15639766ed251e6b473ed0ebf01ce3dc9243cbcdb9cf9ce021 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/react-vendor-DonmOD7c.js` | text | 230557 | 1595ed6da9d5c4bf85e33713d038d5757724c339409501375f5d94770f90745a | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/receipt-text-B2OuUMZw.js` | text | 663 | 4621d9954f4773c8cb18a7e2c3ea3dc29d73ef70be472383823717f51dc7ff91 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/refresh-cw-C8uogk1m.js` | text | 321 | 5f5f90bdacb941a4bbb004c55154d656bfc8e2191b2933a852c19060bf17b43a | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/rolldown-runtime-CNC7AqOf.js` | text | 879 | d4a36920c7bab6ec97d0bdc5d1233622f28fe010198ca32bcdd80c8cb6b64aae | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/rotate-ccw-DUw36Yn9.js` | text | 200 | 5e8a3428a9faf3f6a49f99dcee911938665fc849f153bb8bd72ae732ed844245 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/sandboxCharges-DLlwfpDU.js` | text | 2031 | a27e1f23936d181a504e6eb6a0f4a86f516b8371aabc6d1c4183872563d544b7 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/save-BX_8C03O.js` | text | 327 | 21c9ec77f90b5db0ab2bf28a86bf4b87a66e58e0339e4a4ae73a652b0fcf0472 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/scalping-C313xcye.js` | text | 1484 | 5ec1a6c1a002d0f62ee68555ad7e66aa4d2ec82516407c2ee13e2a2390651df2 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/scalpingPrice-BUUPKlxr.js` | text | 89 | 115558ff55e0871d37f71883f6effd2c2e25ed6e319cf7b3ee603925505d28f1 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/scroll-area-Cy3f_Tgb.js` | text | 15420 | 2ee8870f40867199df86d3a5d4af571c628437bf6d7047ce6fa1547b03d3f4fc | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/scroll-text-C6g2-5LX.js` | text | 349 | c56c47375da743aa8d84d739e8b5d02fdc9027ab099f424d50dba02c3026e8da | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/search-ndrqGsjE.js` | text | 174 | 98041e4155471a840849a06e44666d3bcace09526f1326320c191b4f9c347be6 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/select--7PeE_DQ.js` | text | 4099 | 05b73d575736e88a84d5b966e9a9045262f3b4589c8a28fb850ffbbe6d832464 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/send-Co0sd_af.js` | text | 290 | 29551aedb8d8792c24f1331b181d60e9fafa0d6c13cde18d0ba57ab35f98b5f5 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/separator-BwI-pIcQ.js` | text | 473 | 3c79363de3646bb5c69352680fb3d922a4af534c6ac7fa712f5eefb4e8d9edcf | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/server-IjAVUNWH.js` | text | 338 | 936e574e77c5b21ce2ac2bad7d1ac8da6eea8dd0a8c9adcbbebf1953d66e40d8 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/serverSentence-B5_EkKqy.js` | text | 839 | a9130b7561dbb019c365a12fb22ce83bf07429769f2a13b5610a24d23967fe9a | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/sessionHours-hLROJ7hR.js` | text | 14891 | 60869e258c4a8a23be4703e27f68f84748458f9b279d9b22dae756948a2bcd69 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/settings-2-rNlfBm7o.js` | text | 252 | cedb26601ffdcd1493713739cb376eaf8fc3dcd0aa76635ab3d7dc02896d89e3 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/settings-B8g1AOHW.js` | text | 487 | 9656eba655f09a81e819e7185b48d1d094e56a3bdd44f6e5d205b089f5869137 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/shield-GrBtz7-3.js` | text | 272 | 16544bd5e9bc0b6ec19a8beb519a0a0765afe1c8864c76ebb53816e5fbfa5eda | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/shield-check-zhPhk7-M.js` | text | 320 | b513f4716adc50b857f762a1edfb0d6145bc1d87b3f1ffc0c421729f82dff87a | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/sigma-BaJ7jpXu.js` | text | 215 | 5a0d321f6c43b1e2f8770317cf73a9c5e69055dfff19762278d5d29a83726297 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/sipBacktestStore-Clv1VD6W.js` | text | 172 | eb0bc6c2be6de66669c714096a3125740184e36100cd12f3dbf7454adc4ce9b5 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/skeleton-Cz79WdPY.js` | text | 243 | 6016a9db2fc43b148b3ea0c55fe93492023a705dfe44e3fb023f82fbdbfd7543 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/sliders-horizontal-DSt-xZfb.js` | text | 424 | 3884ed899d732bf04a4bac02a00b2ff7c2aa6637008a32c5e6c4fecd53031aa7 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/snowflake-Dt2ljLD_.js` | text | 628 | 10b8cdfa339518bceb808dba0fefd0788b00c54db1de3f426bad0b2d8349a3bd | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/sparkles-iSsE9E3i.js` | text | 494 | 624efcb3f6b6171cf3c15c31367fa9b7e3dbddefa07b16ec7ec52b37acb7ba49 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/square-B-QzUovw.js` | text | 147 | 59b6dab13dbd53f0b8ae680016c6783eab212bc11b74a9ac681a1ed155ead4db | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/strategy-portfolio-B7Y-JG5K.js` | text | 951 | bebd18a92384773e76d4e7f6355ac49b13a40674a5686ffd4e7b518d5d9e6e76 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/strategyContracts-C_C3Nx8N.js` | text | 1619 | f056947ba09cea1e0a998dddc7365909e1b95dc5da2f7712e6417a2e27e86590 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/strategyMath-SJR49u1I.js` | text | 9214 | 06034eca7d54c4b8356dd6344820afaeacd5ae21b7c3585e1a70042026e2685c | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/strategy_module-rnYs0osp.js` | text | 26317 | d34b36111848c16625bab755c8376ceff0cd3e062cf3ba0980a33c0f0052e157 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/subscription-BBYQDqHo.js` | text | 4730 | 2293efb422ee08eaf786182d0ab37b6ea059b20a552ef98be1b43fd0e99f0b54 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/sun-BD7nGOrn.js` | text | 636 | 8fdbe3b91e486f3d422b3ece5d4d63d2a55cbc4d45890ef33b4515b9eca1a5a5 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/switch-haF1McGb.js` | text | 919 | 41af4b9c9d22cd89eac74eeeb389cc7626910b4cc387713864551b6e1ac0ed38 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/table-CsrAFPfb.js` | text | 1425 | 027b62c4d4ef0012ba400354e48ba8f692890ab8778440ae4228a05d84873b34 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/tabs-CwWugrww.js` | text | 1393 | 53263f9f26753a4450df413bd44f1a5da299cbc11da7d9a643386fc9eabec431 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/tanstack-BSV_EFBq.js` | text | 30654 | a523ee856da139cbccafa77ac8ddbb0e2b17553fb7d9d7bd4cc4bf69abb3ab8a | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/target-CHp1Wu91.js` | text | 226 | 1c747a50d049ef0cfb96892508ec2075b2ef18ac72a62027cf43a72ff30a7b67 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/terminal-BVfVR7Hn.js` | text | 162 | 882b7bb2a375916c7afc7a8dd5573a999282fa328807008876f55ab76f18cb3f | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/textarea-9yeQjCP9.js` | text | 604 | 92d2e6b0b4b5c6c6f59ca9ea52505669e98496575463e3bb84ece69a10d2d3c8 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/themeStore-DEySrVid.js` | text | 2289 | a7668b2100961dd04e2697a7d3fb0373ba151dab98e88684a00a0d3ce1f9eda4 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/toast-BkwEjjDk.js` | text | 347 | 7154e13d8740ba5db43153b3ad62e591998c5e73877d30d2247c5fd4121dce60 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/tools-CNfdyouc.js` | text | 3517 | e387eb3360d6eed6c8f568d6b1f148a544e6df1907d21be068f2c25b7c0c2c67 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/tooltip-DBamU-Tn.js` | text | 1196 | 083630f3cd2fa56a191336bac84e65c8979fe3fb01e8e34ddc585aa77eab299f | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/trading-BhkX0mQk.js` | text | 1450 | 2f0305b6bbace52d9cbda9ba486ca5475e7d1e488f0dc71ebbbae385f0bf44bc | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/trading-CTUItlFz.js` | text | 39 | 5d334d37df2005f93b6fb79076140bda8c93406beae24b39c4c779c6363a9dac | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/trash-2-CVDSav2D.js` | text | 328 | 97818f401d12d198a821558796e10e75d782c3812f7ea5fc5cd9376c8aec2e5d | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/trending-down-5bOAne3-.js` | text | 178 | 5c8c0a4859e6d811b8c94c7f1a77a5ac57e290c30c9bf0411d07d324d41910a8 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/trending-up-5zaSk-oH.js` | text | 175 | 097cbc5d9ce5eb3a390fc0a38b7e9d1f243479c9dae5e10fe984d1f21cfb8e7d | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/undo-2-CJ66gHvi.js` | text | 208 | 37285fbb9597dc5458857970005cee599083929adf4581ead57493017ac25124 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/upload-9WHzEEsr.js` | text | 230 | 984e6568e8f87366fdd444069a93de1b28a0f2949b70bfd8f88179e98bd72025 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/useLivePrice-BxFaUqCa.js` | text | 2412 | 7041c892d39274027dc9871555e1c61958702e372996e45c7c3373b21655551d | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/useLiveQuote-DyfBu-Gx.js` | text | 2753 | 6d65c9441198496c61f83fb304cebe2fa49f408b318534d422063f97645d7e94 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/useMarketData-BbFwRo-8.js` | text | 1779 | e7501c9426ba00390c7b76518373d124ffca044bbf09ada91699b74d0fe2f610 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/useMarketStatus-DvEJPzkO.js` | text | 2023 | 1ee3267379357c79a6a01deaa58939b56a1773242ce808be2b47c5a845e32093 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/useOptionChainLive-D05Sq0zH.js` | text | 5541 | cda406f2dfe570a982ce6b97abe163e7126afe7cf5e72d23a55c4ea227055d3d | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/useOrderEventRefresh-rqOcVAG4.js` | text | 547 | 0048b0bb03dabdde005c3d53e5383740b5cae3a41724057499a915d3f05d970a | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/useProfileMenuItems-0jdMlWbP.js` | text | 4549 | 3b17c0f206ae3e018f1faa5ffd677be0c2a36c8e9bcd96176d062eb02dd58fda | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/useStrategyExchanges-CC7JpPgA.js` | text | 743 | cd623d1082aadf8ccfae9c16d9455bf74e259f416e4e3b38373e1697bcdfb88d | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/useSupportedExchanges-CilMwbaO.js` | text | 1362 | 6bb3c14aa8bacd46fc2d99e7784e9b5a1c06479d5f647f05d0be3be4ef0c1a32 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/useThreadScroll-CdPg-Ela.js` | text | 325134 | 1f78c005765eef0d08271e007fda6da42787896ff1b55dffdf7970da3cd139f2 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/users-vjE8yPM1.js` | text | 306 | 961903a89072142914ac1f3cfaca512a0e4009b9941d16d43517eed47c9802b6 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/utils-BhWVr7uv.js` | text | 25677 | 70377f280a0c7495c53cafe9111e6dc760064464ccc1726d0eb61c9cde91b05d | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/value-8xOwwyZS.js` | text | 9231 | db2fb6f5a236f56e7bfa37d71bd309133c56ccbcdd54b000c88b5324458bba47 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/volumeSettings-CxRGFpqE.js` | text | 4024 | b5999c383ad0fb1439737d7ab8654eb89ad771fb9c8dcb78a84570ca3d1eb6c5 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/wallet-Cxz5H2LJ.js` | text | 286 | ffa9a7ee34d11f09068a8ce95096f367ecc1dc429b2c0d608870737e4af002ff | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/webhook-COuccqnt.js` | text | 352 | 63f46aed23b7510786635b5e654489f273ca9b4bfdea20e188fd9442ca5add87 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/wifi-D5f4ZTzZ.js` | text | 280 | 7bfd8e9ba3361ab63b8bd64943b29c45b95d3c276b3fce71758a63c6c72a112d | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/wifi-off-CF2dBbf4.js` | text | 460 | b7db7d0f8c977fee1be41c784c9cbe83d339145ffe103f8235b59a08e0092ea5 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/wrench-DxJg4I0k.js` | text | 446 | 36b9680fe32432a13dcebe08b6ed7d25199121853ee41f86ac65d14fa5239660 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/x-CFxAQ7Rv.js` | text | 154 | 617480b0b2a3122e36dc53eb42497c69ee0168a89fc03a7970a68db9f36dbbf1 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/zap-Daz-axWs.js` | text | 262 | d4036cb83d87494847f17cfc0567aa7a3bfa005f729a9c37c111511d932f116c | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/assets/zap-off-BC0r1Oer.js` | text | 1083 | 3ed3c3bec2b16b1d06d9402408223ab8b66db15d9991b35fb5ec362bd6b2eb04 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/docs/gocharting_webhook_setup.md` | text | 16557 | c25990964e276d2ba44b20deca781c541fd459fe213a79bba88c072aa045d719 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/favicon.ico` | binary | 15086 | f9f3de086173638a959c688cb60a77b604bc53552dd1c9a741b1580259b0acdf | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | binary: type, size and hash recorded automatically; content not examined |
| `frontend/dist/images/android-chrome-192x192.png` | binary | 18419 | 8e02797e2de42e8af57ca6bb5a342e409c22e7fdc2fce75b2249a88d3fbbf80d | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | binary: type, size and hash recorded automatically; content not examined |
| `frontend/dist/images/openalgo-glyph.svg` | text | 2261 | 278214dd37f39505be610ef7c13e174742a77a01ad122d886af1c1ed6a464e62 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/images/openalgo-mark.svg` | text | 12160 | 8e1fb54037cc17f5b0c9a6a86746878bbc35138535a7e512da28733a9c1cf303 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/images/yoga.png` | binary | 96551 | 2919df0fde044fbf6dcc50c40b0bf557123c565e471998050479a100b5f184e8 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | binary: type, size and hash recorded automatically; content not examined |
| `frontend/dist/index.html` | text | 5500 | 969cd321f8e0ee41e9ce61f7389c0761879a5cb0dfc3b05ceeed4152156fed13 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/dist/logo.png` | binary | 18419 | 8e02797e2de42e8af57ca6bb5a342e409c22e7fdc2fce75b2249a88d3fbbf80d | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | binary: type, size and hash recorded automatically; content not examined |
| `frontend/dist/sounds/alert.mp3` | binary | 33024 | 11e67403a8bbe26debc7e6ae634f54d26f6424b7edb83d18880c3a10b61912a4 | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | binary: type, size and hash recorded automatically; content not examined |
| `frontend/dist/vite.svg` | text | 1497 | 4a748afd443918bb16591c834c401dae33e87861ab5dbad0811c3a3b4a9214fb | generated distribution | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/docs/frontend/README.md` | text | 2351 | 8bf86bb7bf93315087472d6bc2699b6e139c17ecdcd36e670e8bffdf5c764a84 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/docs/frontend/api-reference.md` | text | 14117 | e51124f222433fad8a97fa332acdf654b49ece877284c5e92c946ff86faec838 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/docs/frontend/components.md` | text | 12060 | 11176ee578152377bdb9f24f4edbfe56c4bda2e7110ef8ca25e3f9bed9878e41 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/docs/frontend/developer-guide.md` | text | 8778 | 47d7eca083d45852d8afc30355ddf3424b0cb893d3f26501ba870ddbd507225f | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/docs/frontend/session-management.md` | text | 7233 | ed019f93b67e411810abc4d99707df8d0d2a658102bca2e3f18b8cf2ab0b57d1 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/docs/frontend/testing-guide.md` | text | 15434 | 1ecbcf00a48e7e7f4d085d2ddb8891602731419a4141dc4906531db67b3c6189 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/docs/frontend/websocket-manager.md` | text | 29366 | 9c1bd85f1e08819b299d9affa8407fcd2c9456afa98be9c54a4d2fc5584ee485 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/e2e/accessibility.spec.ts` | text | 2601 | 9fa3cb71ff712d2a0a2d620c9600972f76d233ed66ddb4137c03fec376c41c7a | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/e2e/auth.spec.ts` | text | 1268 | 49518a41eead5266b3cdd6fd931ce07c605193f7463bce359fe6fa89bff9a0ea | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/e2e/home.spec.ts` | text | 1520 | 62c346b8c74c16020eff714986bcdd0d8daa69d3ad19465a29d3dd73d69d412f | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/e2e/navbar-fit.spec.ts` | text | 3595 | 24bc148c110e1d35d085e11cae49262519dffa257ee303e29a0a2f15535421a8 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/e2e/navigation.spec.ts` | text | 2322 | 2604ccfe3cf34310f22d763eedc1bb09d4d57f5180364f3acf24da34c0ae1300 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/e2e/watchlist-fit.spec.ts` | text | 11069 | f9d50bd4887f5378e2ccd3105bcf676162813657b31a897b3ba1c6d08118af2e | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/index.html` | text | 609 | c0691076262cd9b56ed64dd793ed17be1dc8cef5c86226844afdf2d457958a92 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/package-lock.json` | text | 575368 | 09347bdfca2cbb7218ed1dbbc9cafe76ed8a063c73cf2bd6fced0ef6ca10a00f | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/package.json` | text | 4252 | 59a2f91f0e974e829423900bfe2188469578760871572f60b28bcc403ca890af | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/playwright.config.ts` | text | 1683 | 00567a91d43dba89ce0b3a3cf5450d52eb2492f91d5d0a4e92dc37bd186e4abf | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/postcss.config.mjs` | text | 36 | 9678574654ab5343e316e89a306890846ec5dbaa05b072cea3ce1bd3aa758152 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/public/apple-touch-icon.png` | binary | 16784 | c9dd2ae15f39b16cdc7367d252e54ee1c68313296270a553ef0c7f692c403662 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | binary: type, size and hash recorded automatically; content not examined |
| `frontend/public/docs/gocharting_webhook_setup.md` | text | 16557 | c25990964e276d2ba44b20deca781c541fd459fe213a79bba88c072aa045d719 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/public/favicon.ico` | binary | 15086 | f9f3de086173638a959c688cb60a77b604bc53552dd1c9a741b1580259b0acdf | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | binary: type, size and hash recorded automatically; content not examined |
| `frontend/public/images/android-chrome-192x192.png` | binary | 18419 | 8e02797e2de42e8af57ca6bb5a342e409c22e7fdc2fce75b2249a88d3fbbf80d | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | binary: type, size and hash recorded automatically; content not examined |
| `frontend/public/images/openalgo-glyph.svg` | text | 2261 | 278214dd37f39505be610ef7c13e174742a77a01ad122d886af1c1ed6a464e62 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/public/images/openalgo-mark.svg` | text | 12160 | 8e1fb54037cc17f5b0c9a6a86746878bbc35138535a7e512da28733a9c1cf303 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/public/images/yoga.png` | binary | 96551 | 2919df0fde044fbf6dcc50c40b0bf557123c565e471998050479a100b5f184e8 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | binary: type, size and hash recorded automatically; content not examined |
| `frontend/public/logo.png` | binary | 18419 | 8e02797e2de42e8af57ca6bb5a342e409c22e7fdc2fce75b2249a88d3fbbf80d | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | binary: type, size and hash recorded automatically; content not examined |
| `frontend/public/sounds/alert.mp3` | binary | 33024 | 11e67403a8bbe26debc7e6ae634f54d26f6424b7edb83d18880c3a10b61912a4 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | binary: type, size and hash recorded automatically; content not examined |
| `frontend/public/vite.svg` | text | 1497 | 4a748afd443918bb16591c834c401dae33e87861ab5dbad0811c3a3b4a9214fb | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/scripts/check-chart-legend-actions.mjs` | text | 8850 | 541e2005385b0bb1f074e258cc821530fc8139c245c284951816e6991f4e7c35 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/scripts/check-custom-timeframes.mjs` | text | 16837 | 022681000682487ce775456a36e470055736c558c1f518facd3e416b0f135cf9 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/scripts/check-trading-workspace.mjs` | text | 26195 | ac55b8b164c7849abcd1d5652ce3032710818911efc1ceed6d71d0b6b991b1a1 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/scripts/generate-chart-indicators.mjs` | text | 4745 | e834f47a02bce54f5da6cc61d94491a8bbbbba7c6153dcc2b8500d58a31ebdfd | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/scripts/generate-chrome-icons.mjs` | text | 3056 | feb145573925f277a3c7212c6360264429b0a6a13da91648d5d55aa2a58fd46d | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/scripts/generate-drawing-tools.mjs` | text | 1633 | cf1248d34f45e3541104c2a5d38d9b80e3b2c52c08ddd9fd8bbad297cd7a2d43 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/scripts/generate-openui-prompt.mjs` | text | 2655 | 19542744fc8cec34ed331b357f34faa492249518abf921b9c38f7c37b32e5ab4 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/App.tsx` | text | 20243 | 78d158db81be8d8acaa2c9551667afc52887ef1809ed9d1441dd0752b13eef3d | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/admin.ts` | text | 9235 | 62faa75538c21122558fc4021125c9cc26b0779ee3483e8cd49d0c0873c1ff98 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/agent.ts` | text | 57598 | 9deb7d278714656be586c857152ff89b22b1541a8b93555c07d1511c30e7d1fd | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/alerts.ts` | text | 3579 | a7d4c0f7cb6a1c9725398c1ad3b47e824ca172ffd13680852c7982c5a62b39f9 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/arbitrage.ts` | text | 1385 | 33da33c188f57d4e2a3ffe7420ff93d8501a7ebfde917938e5e2cd01b500bc49 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/auth.ts` | text | 3075 | 75e794759200213022939a9a40ad494aee42ef172f8a4394c2e1fd204d86f3b0 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/broker-config.ts` | text | 6535 | e7fe01042a53eee14db5e89ab0d9a20c97798f6fd13a54347bc4c80ec62570dc | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/chartink.ts` | text | 3665 | b2b35e5ac9ee71da491948a9af13bff28dc8aba23439aaeff6ec74147d45da77 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/client.csrf.test.ts` | text | 2729 | cd0f40c63fae62930937ab7433568724fe121df2b8bb14781fbbbe1c96c64292 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/client.ts` | text | 5904 | b885ddf2227e1d2ef7f184ce73676b923528957957f6786a78447b61f9ac50a5 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/custom-straddle.ts` | text | 2391 | ced9e1a9a4d2e62acca4d032652247a4ed0cb1f9b9a11a519ce4b5d43683e680 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/flow.ts` | text | 13353 | 7b0223c7c26997d2c217b9e779a2829484fab7b93087c46c47dba43fd4359d80 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/gamma-density.ts` | text | 2062 | 5aff015836d7b4729f23474b00ec5acfe8123d976b58ed165e72bee894efd0ac | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/gex.ts` | text | 1650 | 98a5accaa721cc25fc2cc36bb626bfea71c0c0f5914fd96b730d3caf547a0fc7 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/health.ts` | text | 5420 | 7f7eba76bc255c200e6786fc636a387e64c56a421354ab5513a5c3bf164949f3 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/historify.ts` | text | 5911 | 034b583c5fdb95089f38310510e1bcf50b5234b9cff1072b86655fd7abd237a8 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/iv-chart.ts` | text | 2750 | 7eb617c78e2bac8483370a7bbb442d46058f2bb97d8068889507fd2fafafe771 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/iv-smile.ts` | text | 1459 | 284ea38b6db6615f39e8cce876b9cb03bf9478641550a59b0f470e342a5c31f2 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/latency.ts` | text | 5223 | 175c8656c5df992b48c3c369663385f0145d66568b2828c9c793f4e1c16652ac | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/oi-profile.ts` | text | 2102 | bc7c41a233ba073cf0847a1270cedb85397f599cef5f2bc7fe0bcf1572cc48cb | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/oi-tracker.ts` | text | 2255 | e473f1aed6c29b31b7e64e33d2df348ec6ae05891d2f310393ce511cf66fbdfe | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/openscriptRunner.test.ts` | text | 3774 | 4fc14d1eeb837fb49fabaf32d4ed5c1028385ae12bff28a46740a3de9c7aef31 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/openscriptRunner.ts` | text | 16894 | 1de9b3b4847e48825139ab60c180fcf90df5f783eae60b34842257cdb90d1417 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/option-chain.ts` | text | 1152 | e3e7909e483de5bdfb48e619e1e95e64c40d2a6ee72d3951c7b47bb8f640b6a0 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/portfolio.tearsheet.test.ts` | text | 2898 | ab641269918ff8608ca6424d37b4ea7ef3c88cc3fb5ee6b65918d9787c3a4c11 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/portfolio.ts` | text | 14547 | 887d5e8a8a54e43f81061bef7dc1e0c22bba3279ca23dc56862451d3364ef7e5 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/python-strategy.ts` | text | 6941 | 233ad9756af98e3597981d0a070a2fffdb14accf0c5f219a64194df2bf918f4d | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/sandbox-charges.ts` | text | 6768 | 142a363366e83fa0d094bacc8a830a510b2acc3c9257742926488de9be60a9fa | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/scalping.ts` | text | 5435 | a04692109b84b334789ecca337333bce774e5d28266ad2c1bdf14787588975e9 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/sector-rotation.ts` | text | 2376 | 60286fdce5f29667e652d734a55a43d469d6e8c30dc9e4a4bca618b12397f770 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/sip.ts` | text | 7058 | 8e94f70986f4eb45063b57221d14514380467cce8e572cad6e071d7eff2b7f4a | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/straddle-chart.ts` | text | 1329 | 7c08e964b2b48d3122320ff8630c672c29cb2c4bb91fe65f4493c0af36ba75e4 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/strategy-chart.ts` | text | 3627 | 21d29fd0ab4214867c561610f219a88e455fa6ca2dfbf5649c76f8a4571ce345 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/strategy-portfolio.ts` | text | 2926 | 660d6acda5ef5ca877a4d59943dfdf9e6b31a4f9a6c3da340877b03306575318 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/strategy_module.ts` | text | 63820 | 5ccbcacd6ac4612ea6e605ff05e0a39284a276df59e895987cf991e762a80c74 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/strike-profile.ts` | text | 2090 | e548a7f9d95a03c9c52797dd9104ff427996b1bbd00aa6c7a3730bb6cd77bd9e | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/telegram.ts` | text | 4008 | 2f4944c20b1f27e5074d2f48eb03bc3c0a5fcde123639004e1c4a4bc86fc624b | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/trading.ts` | text | 8640 | 80f6efa7fee4a21466af439d3cbecc31cb4c7e682e3f84b860a61a8ffe2a8c90 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/vol-surface.ts` | text | 796 | 929424147e72f8420f03aceae785ca69f7a490a0c39e988c7f41cc16a24694d5 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/watchlist.ts` | text | 2924 | 6244a4ba1265e7e80132e020730b0b9f096dffb145b5ed0a2ab91e31eb80e3dd | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/api/whatsapp.ts` | text | 3547 | a625c888962870462dbe2b295238e81fb7b005697f87a02c94a401d8f67dd7bc | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/app/providers.tsx` | text | 1103 | 9e25255e65fb9d5d977b5073ff3700a057e411eb6c8629127ed1d09c4b9c8cb1 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/assets/react.svg` | text | 4126 | 35ef61ed53b323ae94a16a8ec659b3d0af3880698791133f23b084085ab1c2e5 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ErrorBoundary.tsx` | text | 3704 | 4f0229b90f55784988f67e720a912bc0e1404d087131fb02fbe839fcff43da27 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/AgentSetupGate.tsx` | text | 4041 | 6d65633d11138a25ab71f8ef5949a7398a4206ed51e9d672c1cb32e951f4d5dd | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/AttachmentChip.tsx` | text | 2844 | 453b15ab77cc12abad762a920cb1da9d58c5f6f542a21660060f2f81a10abc4d | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/CodeArtifact.tsx` | text | 8747 | e7bb362c7d01c9100071b5af3dbcc8510a9c9b76066e6c336030a4690595d058 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/Composer.test.tsx` | text | 13466 | a5e5766d9ee25fa0db08ed8c4b7f003a882384bfb477d7f38ddc8c2d05fec97f | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/Composer.tsx` | text | 20697 | da98b08fa61a02e26dc7d5ae1a72e4699cf1c648e07a2899036e98575e1d4ad5 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/ConversationSidebar.tsx` | text | 19617 | a1844430f61e53f5fc03f3f19c5e49285a6214661edaea242d379833b8019d54 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/Message.security.test.tsx` | text | 8936 | a0f823e19010193a725e9c67a22ab6ca6f166c20f652c34dd9398f175f756e32 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/Message.tsx` | text | 20991 | 38e268fa0a30779b2aefecc636152e9c0bf3dc27e68804675a38692130796451 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/Message.viz.test.tsx` | text | 5225 | fe10c90129154636ad2a7a7c5845d3e5025396156630eb1bf326c48866b64ac9 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/MessageActions.tsx` | text | 4566 | 3821feb698241d617716424f55a0f8709376390e4ac78a5f326de98e407a5aba | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/MessageEditor.tsx` | text | 4036 | 5386ff10bd37e6012174d57aba67d1521b6d084e571a0a4135110340adca9801 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/ModelPicker.tsx` | text | 12507 | 36ee7a5a0f9e3725aac95022b75342a109e963d44506b41771030ffa7aa7e4aa | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/ToolTimeline.tsx` | text | 11874 | 510acaf917763f3f2bc0706b190b7c1db230e27a87ec2e67eaa47e36d8b31a66 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/UsageBadge.test.tsx` | text | 4934 | 1272467dadf14ad02a50d276830703512ca733a743765c3bb08a1e6541e14cce | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/UsageBadge.tsx` | text | 11480 | 79aa05ff005fbc922bbf5fa6b2592e891954b713ff766838c9bec9331cd4eed3 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/VoiceButton.tsx` | text | 8485 | 92bc38e0576816e237d5d9ef73537e7f5d7b85aea7db4a9fa16f7ea46ab71fb8 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/config/AddModelDialog.tsx` | text | 23882 | aceb6d892ac854c0c4077215b92520b3ad5c7d37260471430b7b1c0cfaa1eac3 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/config/ChatGptSubscriptionPanel.test.tsx` | text | 12136 | 9c2d5bbca94eb2068bb042ab0d22667a5efd5a11f53edb149a9e8a8e7deb7fe3 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/config/ChatGptSubscriptionPanel.tsx` | text | 23429 | 38bdd30ba80ac9f633f3cc9a571fad52b78c50e5239e6be19434f4ac96c0ee40 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/config/McpPanel.test.tsx` | text | 2334 | 6a95069c543e7604de480eecc017d439b29cdaf149c3a5fd270af0dbb996c459 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/config/McpPanel.tsx` | text | 6558 | 68625995c1913fb16eef8c5ee1120fa95836613ecb8f969ede943894febf9425 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/config/ProviderCatalogPanel.tsx` | text | 26854 | ea991e319e132650900194230ffa675678d53c2a9c84f0beea99b8793cfd3b65 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/config/RegisteredModelsTable.subscription.test.tsx` | text | 5565 | a1852a9943b4cd34d350a265f7680a3018daab491597f37f3d16c4e037b70fac | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/config/RegisteredModelsTable.tsx` | text | 46496 | 33f1db05413d49b71d06be213dc2ec3a5f9755e64d07e272bdf5dbe4188e5032 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/config/TradingPanel.tsx` | text | 6448 | 000122a36c94558f0f77ef26c6fa95d0db35ec6e8799772659187068a73afc93 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/config/VoicePanel.tsx` | text | 30707 | 03d8042026ae0038d3b7a759e545da547e42777a9ae8b2d74bcc5620b175f9a2 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/config/WebSearchPanel.tsx` | text | 34832 | 78eece183dd45979153ade4b8c495b81bec35557876ec41e65dbbf71b1474d7e | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/config/providerIcon.tsx` | text | 6063 | b852cab4b80d0c42231aff9f2c36b0ec7ff5a8aa591281780ab8a7d8da339ee4 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/viz/CandleViz.test.tsx` | text | 11182 | eaab2f795daab26e76d59a6e77011208de4bea7a2ed97a099951638c2b7b063a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/viz/CandleViz.tsx` | text | 21429 | b46c72cd1bdea89436505295e9f278b217abc5f2728cb6b095c021d463d0748e | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/viz/InstrumentCard.test.tsx` | text | 17033 | 5c4d0787e623cfcdfd7c848fcc115fe108c75d9f71d13b35679e1292b23e7f07 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/viz/InstrumentCard.tsx` | text | 35016 | f96dc614611fed1b220b3f91211ff6057a9819f64b6e579e63e60a165c805840 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/viz/LiveComboCard.test.tsx` | text | 11699 | 88eb58cd676b3a728a3fff1682cc6534c10950857e652e2908e1e2e818c1b829 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/viz/LiveComboCard.tsx` | text | 20035 | 60b6d280074322c991283846af95bcf40b4e571c4cda0fd1d878f1961781fbd9 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/viz/LiveQuotesCard.test.tsx` | text | 16020 | c9d696d394556faa336fea1559dc1e17a7b61b4d3ec3e80683940ca8c4ec7bab | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/viz/LiveQuotesCard.tsx` | text | 21110 | 05df1b00fa8ce71f87f9bb056b34bb7d50a24e436bc8d85f83e6d9cb08a34fef | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/viz/OpenUiViz.test.tsx` | text | 3619 | 872d8b773ee3bc3d4e570d59a70dd9e00f8661f5dd138ae1849fec57e31c6d18 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/viz/OpenUiViz.tsx` | text | 7035 | 93412d32d34757e2649415c4bc535f71ca0515bcc9405cb758dc2fe74360ed2e | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/viz/PayoffCard.tsx` | text | 13063 | 018d2387e34a214300e526cea4b5b6950457746e79784518d7ad95b60dfd692f | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/viz/PlotlyViz.test.tsx` | text | 6203 | 974a4caf425a08904a376eff2ca95f41a7ad0c2121544211987456eecda4897d | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/viz/PlotlyViz.tsx` | text | 26803 | acbfab037f77ae2de075ab4902640a87163f13119c265840bcc5e3c1ca5acd12 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/viz/VizBlock.test.tsx` | text | 6040 | bd8cdffcf56eb4f25d4b675f6654d742b5d4a68c04003bee973300661ce9a1ca | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/viz/VizBlock.tsx` | text | 5607 | fb47f4933d0565514858afb5135f375c996268be07ae08e786c7c96111f049a4 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/viz/cards.tsx` | text | 8591 | 0fe340dbe232aa331a4d87bb133063acc48aaaf8e0466ad45454e8e2261617d5 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/viz/live.tsx` | text | 31681 | cd977d62041b674ff01a594ab997364864a0f389045badf8659d8b9267e6b836 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/agent/viz/spec.ts` | text | 5949 | ad8707ab4fad04be21f7d31fba8f993b907dcc1bf59f77c1e6c035fb78cdccd1 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/auth/AuthSync.test.tsx` | text | 2343 | 89164de5ab2dda953808bbcadd549e4a966f4ffc4a84d01472f8afa29ad8f9de | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/auth/AuthSync.tsx` | text | 4198 | 70001c30703954206e3223e8c8a005c313f8b3f38eef41a362a0fa294ccd70f8 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/auth/BrokerAuthSignOut.test.tsx` | text | 4240 | 0b5388590e26b0b3659357fae113955de79e519b2fc3e1ce68dfa31d1529ab7b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/auth/BrokerAuthSignOut.tsx` | text | 3352 | 6005249171ffb9e592fe742afbf25672ef92f502b090dc533d8303e4ba632f2b | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/auth/BrokerSwitchConfirm.tsx` | text | 3034 | 74e0eaec52a0c4261b219aebbaee18550000db41ad23d71cf43a0189d5cc7ddd | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/auth/LogoutConfirmDialog.tsx` | text | 1896 | be3a3dd543e1a5eb43d377d4c88b9a3dc1f56347d4b0e021d18a67a171f32664 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/auth/TwoFactorEnforcement.tsx` | text | 9185 | 1b5a3548d857125ce735a949ae6793ac2fb35a89f7efda5328bdbd084ad599b7 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/chart/ChartContextMenu.tsx` | text | 6652 | 5d35d887cb25bec46ab566ee3fc8af9e4370f71a20ff4fd489d8a4c27643dad6 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/chart/ChartGrid.tsx` | text | 3416 | 95228aac127a83ad32270e5b9e25fca56bcce42343b72099bf5a11c16ea6928f | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/chart/ChartReplayBar.tsx` | text | 3393 | 632ac594ba0b6075718c850275d37d7835260bb2a36261c08f11519a9901a723 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/chart/OpenAlgoChart.test.tsx` | text | 20381 | 62607a951c792052319ea9867e2e9b44c8c9e50c1e4d60b693064c018be6ca9f | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/chart/OpenAlgoChart.tsx` | text | 19914 | 78993967d595dbac85ec3eb241d6054244417cf2b1d4097289a384cd8ff1f573 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/chart/menuIcons.tsx` | text | 1618 | 56532202b4c5bf886394be2e3dcb06c8c38791fb8a14d213842bf02313625148 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/chart/useChartReplay.ts` | text | 7395 | 044ebf5de02f2ad8532938154bbf222aa79a380134e0f0ded655c2a0406f5ce3 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/edges/InsertableEdge.tsx` | text | 6599 | b6bf3abfb0e7ace05e56e43580e75ca4a095ddc0aaadcb611d2eeb3a9910b4c8 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/edges/index.ts` | text | 222 | 8d09117a77cdde709ffea8147657f854e99f0621cca29020bbe7837174c38fdd | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/AndGateNode.tsx` | text | 2311 | 9a70d785b01224edb17750c3d54ed94031c4035b60185061693a90685b79d153 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/BarOffsetNode.tsx` | text | 2226 | 8829404d7378f8a63e30396f1fe9435d1a52c34b4bda4e3134ecd28977db1d39 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/BaseNode.tsx` | text | 5746 | 4b21d9fba4aba68ef84f54dc86a49728553fb169f04a6560a34898fe881e4285 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/BasketOrderNode.tsx` | text | 2158 | eeb2e994056505396f101604e152b9c2dd3fcc12874e26cd23c4fc743f8d1d90 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/CalendarNode.tsx` | text | 1992 | bbf80471e0c1942f156f07f821e7190ceeb71775ea4b097cdf2d91172a840525 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/CancelAllOrdersNode.tsx` | text | 1400 | bf438e6d6e81fdf7e62c6f48bde2f02e1a84cd0e402447a22fb17a761586edbe | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/CancelOrderNode.tsx` | text | 1693 | f078deeee49572276ed4c20698a4afef561acccc24b4d8ae6f2b8845b76e1e7a | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/ClosePositionsNode.tsx` | text | 2890 | 7a2b1da200467981dc4a7ad191236a448ba85c875863a2519d64437d27f25b50 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/DelayNode.tsx` | text | 2220 | fdbc57f4c4b143ddc76a673e284a5ece13ba895e25978655878fbb42898771a9 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/DiscordAlertNode.tsx` | text | 1754 | 8d48e7f491eb407f630be7fcea0c5d233f516b5fbebc251f055cf6c6716cb121 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/ExpiryNode.tsx` | text | 2146 | aa965356626254930d0a78b6433d67bd1dc523290d8beb9c68f948435f18ee35 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/FundCheckNode.tsx` | text | 2576 | 1cdaaa15ad0448222e863c5e7b985b435c99fdf4e6e039b00a16fe295a0f86df | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/FundsNode.tsx` | text | 1518 | 16a91d2fb243b3663c3bfda0f0d5ab0e0e612e24b3a22610b6590ce70629a360 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/GetDepthNode.tsx` | text | 1735 | e94e21399dbf455eb39b30d1fa21cb9c9cd6a546e894c4510667d85d1abaeef4 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/GetOrderStatusNode.tsx` | text | 1752 | c5e45c22a2e79a6ad8fee39172b79c36cc292181ab6b751f76b716e928db751f | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/GetQuoteNode.tsx` | text | 1817 | 7a7e139ca3a899503ea252ccffa8f15a828ae21d96fc7e3caa107e8c21a799c1 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/GroupNode.tsx` | text | 1857 | 121a6787b9a8438a96eadf93739f0368021814fb9cc9d98528e11e3633c9572f | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/HistoryNode.tsx` | text | 2059 | 8a0e815f036e68216161a984c64f57e0b63efce1e624c724db1ace3182e10195 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/HoldingsNode.tsx` | text | 1542 | f3a6230f11a8b233e084dabfa9629fbee1a9476fca508e35aa47e36388b995cc | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/HolidaysNode.tsx` | text | 1858 | 06a5148ba1540b204686d6ea6e3897a245f132d57dc9fdaf51e637bba773da52 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/HttpRequestNode.tsx` | text | 2483 | 7c35f811721c9bf27e83f029d5bb2622bb92b8269d6cee8046a0db86fabfe38d | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/IndicatorNode.tsx` | text | 2255 | 94e1ce9fc9cf22c2b8dc6e131b55440c11b69a9eb7201a879cd8d47a37386956 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/IntervalsNode.tsx` | text | 1667 | 0a6e20cc386d5e43dad2052ccb419ffa5d45cd4c6b0230384176abb1fb7dfcdc | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/LogNode.tsx` | text | 1963 | 4b025ce2ca97c531260dc384b04366c4321036c78136f858459fd6847cf09a91 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/MarginNode.tsx` | text | 2175 | 7e1038fdd604918f0724f4e345f9caad95127bd4a4050c1429d13c5407adac1e | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/MathExpressionNode.tsx` | text | 2088 | dc20613a559485245f382718dd750c3cb315395f166ee2bd4fc3fc1a27c880d8 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/ModifyOrderNode.tsx` | text | 2269 | c8a664f6d9eb04439d9b258a5e9aeb6e2f0543a94bd94b3f459bb3bd5acae542 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/MultiQuotesNode.tsx` | text | 2552 | 8cc8aa72b8f4447055b9f48839a70f59dbe959abf0aae195e265f4f69f9df18a | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/NotGateNode.tsx` | text | 1898 | 343c11129493491aef7734ffa5052178eaebe5d2dc772e030b1cf7944f669cdd | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/OpenPositionNode.tsx` | text | 1913 | bf55f616eb3ff7877761cd259450a2f542e6497b69184340f0e3e432727f2fda | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/OptionChainNode.tsx` | text | 2419 | 74f57c2f7da7129d2bcfd2ab522502960990311cf636899bdb9d1c9ddde08aa8 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/OptionSymbolNode.tsx` | text | 2209 | 06208f6980f946443d75862a6a371230130e64d2a2753b8a3d2bb377f09b4077 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/OptionsMultiOrderNode.tsx` | text | 3753 | 17ca38c0206147378ec0f34713aedb9c6b3a3be13057c843a36f570bc76c3edd | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/OptionsOrderNode.tsx` | text | 3664 | 41846f4bcd99428bbf13e7665948cbad1ccc810cb62bc0dd6bf7f6e31d339aa3 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/OrGateNode.tsx` | text | 2295 | 1d4bf4e07677cce887454e73b75a399352a6532e8a90eed2fcd130f713043da0 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/OrderBookNode.tsx` | text | 1541 | 725e9338bdafdccc00a20066bddb68f7ded8dfecf07de8c486f527f77859bc39 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/OrderUpdateTriggerNode.tsx` | text | 1729 | bd305ed1338d21acb7aaa6df0a6f24a60a9e3c5413e526de5792d88423180a86 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/PlaceOrderNode.tsx` | text | 2917 | c186daae72f2d66772a29dd58ef46f3f4b0253868d87916578a061f33471abd2 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/PositionBookNode.tsx` | text | 1555 | ed75aece51c028ac2bc3a4c88ae429f9afbbd7e11bf6d90da13806cf9b24e329 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/PositionCheckNode.tsx` | text | 3339 | ccd1d81ca088941510d80a98e870758b2e05cf22206c86f2fdddf998779ce5d8 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/PriceAlertNode.tsx` | text | 3608 | 600a85f5bfa5252cb4999471170610408e3a4becd2a652e1cb9ab1321f90c5e2 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/PriceConditionNode.tsx` | text | 3205 | 26c2b70f425bf91308ecc6108db2519934ba4b0fcf45b4bb1f6eba51ffd17fd4 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/PriorPeriodOhlcNode.tsx` | text | 2211 | acc801a657d7e62096ea5bf60fa91fc2335c4f0bec52063d39152b6d82cf2e61 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/SlackAlertNode.tsx` | text | 1714 | dd79c1f0ba02938a1b95f9e22035ce23e27647032d8125ea9b79deea1acdb7cf | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/SmartOrderNode.tsx` | text | 2833 | 58e80aeeec1ec54ed5d20ff9f2c36e3953ce777417145726c9b27e0760a0ba2e | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/SplitOrderNode.tsx` | text | 2221 | 627e9695c64d0381d66d4501f90c40688882fd00696b52b605719c106530295f | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/StartNode.tsx` | text | 3065 | a388434ddda3d21025b334f031d848f6da06bca274a8eb5c7a838f58057804a5 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/StrategyPnlNode.tsx` | text | 2018 | 0c2f48c9fa28d508ebc4116e32c1adf000b3070778943638fb56dec920836dcf | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/SubscribeDepthNode.tsx` | text | 2090 | 5973ac5494a0690b2661ebd2a8c9ce08858d167a58afde68f27ed4c68d31b99e | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/SubscribeLTPNode.tsx` | text | 2071 | 08d52966c10fad8989e75a988767cf9beaf0cfecd8a57dc7e65e2d49295a9214 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/SubscribeQuoteNode.tsx` | text | 2102 | 2e4196ae38783be933df8088d139ad453e2f9954b0c31788b2d6d11c8fe1c6e0 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/SymbolNode.tsx` | text | 1806 | 1c93ba714920586d59e19df48a8f3078c56732bd2943f3dfcf4b0abde5b75f4a | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/SyntheticFutureNode.tsx` | text | 2175 | 78a358d92f0ae4832dd6676c02974877f636df5f1fdb51589a94bb54d3f11521 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/TelegramAlertNode.tsx` | text | 1841 | 9a88a9e414550f2d91f955ef938971a11d2fa2c7218018953b85f45e018346a4 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/TimeConditionNode.tsx` | text | 2912 | 6449327127f7828f61b23a4590a4f2becf0983dab31e187210430e9825dbdf5e | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/TimeWindowNode.tsx` | text | 2901 | c5544b853d968b24e9f748f99f57502234c9ec6c244059def25a026352cdba74 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/TimingsNode.tsx` | text | 1790 | b83ea095db480bdd94aa15c2c7e5ee4239bdb0364748a21131d2564b4266f654 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/TradeBookNode.tsx` | text | 1539 | 2803f8123a568fe3110244f19710f0afb73442cf4a724f90bda8ccabaaa6dc8a | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/UnsubscribeNode.tsx` | text | 1971 | 8b9dd297385022ac023fea1031c7c1c7ba3432720c7a5b82a3d1798554f4cf88 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/VarConditionNode.tsx` | text | 2890 | be43df3f916531663a255447d6b0dcef586d46a079fc8c9e932279800eb9aeda | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/VariableNode.tsx` | text | 3050 | 6b6247aa925903723676353b1dd9d1927489beab5b5a984b2cd9d093292fc884 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/WaitUntilNode.tsx` | text | 1908 | 976e380b0bba9b9fce67930b628651c68bd09937de6d8fd23095200f39af95f4 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/WebhookTriggerNode.tsx` | text | 1682 | b73a2f3ebb8254a694edfd036eaa9580e2356f282841e344df95352ffacba7ae | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/WhatsappAlertNode.tsx` | text | 1763 | d4085fe143877942c2c0c93e93fb1fee7528391f15d480cc0aec9199f7da0182 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/nodes/index.ts` | text | 7268 | 33072ac1faef678242ca7a63dbe028e325b533b3dee07cdf857cd961c3ae214c | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/panels/ConfigPanel.test.tsx` | text | 9274 | 6135c2cf1d229f3d542361693207cc24ccb46694f3e61425c6738042531a1f9a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/panels/ConfigPanel.tsx` | text | 155501 | cc868188f2ba225c18d6ac018bcfbfc21c33ef38287e202df9f0b5cfc49ca003 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/panels/CustomLegsFields.test.tsx` | text | 13230 | 154664a4e44731d8ed4eade63a57f9b34ffe6b1621b01ca5d0985987294d1086 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/panels/CustomLegsFields.tsx` | text | 29207 | 31ab738575663785bc3d6986f0ed4038b7380540f6fec3989ff817f98a8e2809 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/panels/DefaultProduct.test.tsx` | text | 6040 | a177c3be00da346dba525369418f4463829f3ad84a5d4753d23c94f0341e3319 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/panels/ExecutionLogPanel.test.tsx` | text | 1465 | c668cbffd5f88382b27fdb23f4b7bb153091465c9ceb128118548ca6b077fcb1 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/panels/ExecutionLogPanel.tsx` | text | 5910 | 761d42ebab7464088e616e8c834a1c5a1c169cf6552a3576aa0d3ec28da39c5c | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/panels/IndicatorParamsFields.tsx` | text | 7582 | 5453b344c8d3717b9d861fd2a87aff03976155dd68316dc1f5d03de47a226147 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/panels/MarginPositionsFields.test.tsx` | text | 15307 | 89f487ec320cf6e85607c9d65e9c9b5a765e63152b432a39da1d4fe22b75e46c | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/panels/MarginPositionsFields.tsx` | text | 23521 | 0a6532cf99e5b03b2fc88c5b128e46b98ed3dca7040f5bbf1206c298432d56b8 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/panels/NodePalette.tsx` | text | 19909 | bbd1ac9a19b18627becb25e2a5d8fc54fc130427571f380f0002847f16758a28 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/panels/OrderFields.tsx` | text | 7579 | 029e7161da70f26be80ce1df671d6da4d73afd912b1127005b1e64f41a52ef88 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/panels/OrderPriceFields.test.tsx` | text | 2875 | 381aeae3b4741c2042e8c2831c43e6b647d4d82189a0ff2d6b1251f03b093d65 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/panels/OrderPriceFields.tsx` | text | 2928 | c65222cd6cabf152fb7488b94e022333c416bfdaec9d94a6c86aa24514d9444d | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/panels/TemplatableField.tsx` | text | 3788 | 4eb3b8369a90a61a270f332718d6771f378ba5a0d26fb96d5c30442ab014180c | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/flow/panels/index.ts` | text | 309 | 783243db80ffca5d17bcfd0bb944b348c471e2302dd3f0a9ca48613f84b5a151 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/historify/HistorifyChartPane.tsx` | text | 25547 | 446e51a50348ab6cc41941fce09aef007e1df4ce4439d99e2c12726eb6ed6964 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/layout/AccountControls.tsx` | text | 7894 | e0ae771a8ffde73be20b4878c76070b800f841ff88862cc725cffceb018a0ec2 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/layout/Footer.test.tsx` | text | 3060 | 54644558bfd7571969d25550bddf18e81e0bce0426a45f798ab59a3a5b443ab3 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/layout/Footer.tsx` | text | 6217 | cbf190417e160a1d1e8a0ed0fee809068eb04a4625005ceb30566ed3678ac7fc | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/layout/FullWidthLayout.tsx` | text | 730 | 09bc5321e29c6032428ebea65a3857b8d965d922d1ebb6e1f107c6889536c44a | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/layout/Layout.test.tsx` | text | 2481 | 1317b6c5c0572e405871eca5924188e19bad423fc0c79e26d8f25de23c5933c0 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/layout/Layout.tsx` | text | 1623 | 5c39f5c8cb93a0ae4ace2ddd4567bf197b23ac578c180592e2ed1f5fe8d01b81 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/layout/MobileBottomNav.test.tsx` | text | 3948 | 002e53ac2c8df5cd776668b9125a631241ab380021a27dffc89db88ff1be1cae | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/layout/MobileBottomNav.tsx` | text | 1306 | 530787af722b834fd06d8a3b33d2cbf249eebc9936f8690097421d028ddb7bbf | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/layout/Navbar.test.tsx` | text | 6095 | ccf2a08b0e456356f73fc6f00c3d9540eec5e468db52609960fbab0e27eeaecf | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/layout/Navbar.tsx` | text | 12434 | a9f46c238330023fe3c0f99c7f98581e4930a7a4fce8473aeb8c329542e8ef82 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/option-chain/BarSettingsDropdown.tsx` | text | 1974 | e2d77565e0001abe0b9430317cb7a262a678a4cb5b6720bf8c648f32457e80a2 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/option-chain/ColumnConfigDropdown.tsx` | text | 2569 | 636d414d5f556ab592e28001c421d6015cc85a3880405becd972368a41e481b8 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/option-chain/ColumnReorderPanel.tsx` | text | 7129 | 71f0a034854cafc7217a8abcaf8035f1c772154ffab1c7ba2064829af3b77963 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/option-chain/ViewModeToggle.test.tsx` | text | 1485 | cde165a5886814522db0d779e22caab67cb98d233c14f22add41ff86d13b71e2 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/option-chain/ViewModeToggle.tsx` | text | 1606 | cf1585c376c18acc206ea29821ca1eb75bff7f34206981a850fd9ff464de53fc | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/option-chain/index.ts` | text | 234 | 411c3582cd7d610364189b3a41225f8e557f53e96b73d537b066c5a85beb942b | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/playground/ConnectionPanel.tsx` | text | 5246 | 249606132677edde3df5f23915539d1428c53f7857055cc125859c7c2ac58369 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/playground/MessageComposer.tsx` | text | 11865 | 57843d979eafba0feeaa525dc108e99a94759b4841b6a7affd7b4f968e7f9ab5 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/playground/MessageLog.tsx` | text | 9960 | fc8e120d03e7996a528c6eb0097c29a1aaf003b540a71f710d585e9a71dc42ed | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/playground/WebSocketTesterPanel.tsx` | text | 2639 | e4930316c45a1c1d2de1b6528464db182700139bf322cf301ef4c7942ad76834 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/portfolio/AllocationChart.tsx` | text | 4766 | 992b00a9d0c53d96283861c367fe9e84e87ba097ad4668c812828b7b86ea222a | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/portfolio/ChargeControls.test.tsx` | text | 987 | 0a00618e9595ca79c7114d5ac8e1a1567adacce1d8132a4950b2ceb0314baf35 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/portfolio/ChargeControls.tsx` | text | 5730 | 721cc078e2a46ddf1a8fd4f8c5370fe73772d27008a54380f61b683c739c5183 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/portfolio/CrisisChart.tsx` | text | 7235 | 80d8bbda1d35c7c1fffe8177085b6946db74be63c98285800d740408a0763caa | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/portfolio/EoyChart.tsx` | text | 5857 | c60a78ac6a14e90984e7298e64fd58fdb46427b5d4eaf8cd8782d9c47a5b72d7 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/portfolio/MetricGuide.tsx` | text | 13896 | 13047f95bc58d5659cbb2fddffd91d928d466235630a9be76130fefa8913e34b | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/portfolio/MonthlyReturnsHeatmap.test.tsx` | text | 788 | 4f0f30af294022b4063a2afc52052720cb727b5e3f790d3a4604fb787f425993 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/portfolio/MonthlyReturnsHeatmap.tsx` | text | 2436 | ccd513a339ccb7aadf8f01f36bd1e37c64387ccbd96307efb3def729f9d8eb3c | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/portfolio/PortfolioLineChart.tsx` | text | 4009 | f6de71b3aa2e3b3ac234f3a1e3ac8802fe104b7f67461742e4d4dc40c54d1b16 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/portfolio/SymbolSearchInput.tsx` | text | 4047 | ea6559df4f713d7be878f3f1b34c37e89114b74d97a8e625214d1b7b9a6c4801 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/portfolio/WeeklyReturnsHeatmap.tsx` | text | 2917 | 78c34af75f7c296bdb68811a9ddd3e8117d7e514618521b8411a415f68b605de | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/scalping/ScalpChart.test.tsx` | text | 7834 | 6d5046f1010a33f3b5eb44b4b101352b59dfeeee35c7c621c75242be9922f72c | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/scalping/ScalpChart.tsx` | text | 18061 | 27b439c584de436762bc43859bb13c8cc44d0a6f8373db58368b8e56d75dd4be | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/scalping/SetSLDialog.tsx` | text | 8452 | 5d1601fe60e9dfde242b9c6fdaab62bd5734a18602820bbacebe09f92c9dcdd3 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/sector-rotation/InstrumentSearch.tsx` | text | 5950 | 3fc67ad63b999c58050f1930e330ab9b1aec252b55f22dac2c40c233f504c035 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/socket/SocketProvider.test.tsx` | text | 17560 | eaf3f077cd2e8967459a5541f0844382bce176bfa4b8369ce071900f950b8a81 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/socket/SocketProvider.tsx` | text | 1240 | c2a95dfa2725e488fa23c48465b6fd642b607dc220c76c0834cf69e3c6e75c17 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/socket/useKeepReconnecting.test.tsx` | text | 5515 | 2f10f1c2814fcf3c7fe4d05261b3f88a28954ce389507e664b19e2084c640e24 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/socket/useKeepReconnecting.ts` | text | 1888 | fa6a950f671d68d04d5eceb19af4b9e01aba6d80ee19cac3549bb7ba7bfd72b7 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/strategy-builder/EditLegDialog.test.tsx` | text | 9382 | 266f0a2b3ddbe46d33ea700dd8d4d40a428e10bef18696f2ed407b3bcebe18a5 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/strategy-builder/EditLegDialog.tsx` | text | 17782 | e3c9cc17d4e724509870c6e2c372480a43a6fc6be228f46805c0c371176718c7 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/strategy-builder/GreeksTab.test.tsx` | text | 4058 | edf8dec69126ef8b9f2b93c70bcb535e4b301d97c0760d896f38022dc0ed37c3 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/strategy-builder/GreeksTab.tsx` | text | 7308 | 98d3692d9d1f159c4d7d25abec3c68272c1f83dac733bdc9e2a40810aa249fbc | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/strategy-builder/ManualLegBuilder.test.tsx` | text | 9557 | 6d1ba51398174a30324a0707554c743d8b86b1e110b52bea27ef3097fe976792 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/strategy-builder/ManualLegBuilder.tsx` | text | 22837 | 1dc51ac4f594ad436ebff6e9bd916796f9fdc8092558a188c8f1e2001546e86f | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/strategy-builder/MultiStrikeOITab.test.tsx` | text | 10263 | 4bade7e57b7452636673c442186eea268e350e2f6e7c43d2834e0ae5918058ac | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/strategy-builder/MultiStrikeOITab.tsx` | text | 16189 | dfe36ca55b579088b9d531c6894bafa4ebe62d0cb68e1f0ffab18066d87ac750 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/strategy-builder/PayoffChart.test.tsx` | text | 12477 | e61360d2e74fac7b0b4af37991498934dd81aed3c83f4ad553045d4f0b111bc4 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/strategy-builder/PayoffChart.tsx` | text | 21776 | ce9569bc26333b401dd5be059f98acb6b1f3dc0bdea1ed986619329f712a92f1 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/strategy-builder/PnLTab.test.tsx` | text | 2195 | ca2a219e159d804c74af41c1c546cde4f52e75d9eb5aaa1eab45325366d6e6d8 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/strategy-builder/PnLTab.tsx` | text | 14194 | 69a982201be25407c4aa5452e658abf2a14e1ae915b0040a70c73f6d429b6224 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/strategy-builder/PositionsPanel.test.tsx` | text | 1576 | 60574da9887ce8ac42dcf3773619e44e42f12894317a4f3dd2f7c61326bdd565 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/strategy-builder/PositionsPanel.tsx` | text | 18935 | 9cbba0429303778c2db498143c91a0a26afff04d35fff71cd8e6a5fd6cc876e9 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/strategy-builder/SaveStrategyDialog.tsx` | text | 5211 | 7c2061f1561ba38b24bd4e036a76f486c323edcf0afa2f5a005155babee25d1a | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/strategy-builder/Simulators.test.tsx` | text | 3622 | 22f3666153a248a8d9d80e2bb1ba80eff759389f3d896ba08b5de7e5efab8a0e | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/strategy-builder/Simulators.tsx` | text | 8580 | 3b0eef5f1424d1884cc53a624957060d2890379bfe44662121d14f1345695b61 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/strategy-builder/StrategyChartShell.test.tsx` | text | 5118 | 4de2742f6789d6002c730ac2038b3b82f7c97506764a0517df76bc34cf5fa781 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/strategy-builder/StrategyChartShell.tsx` | text | 21317 | 3424ff8660b6d92c9f8d2017cecb9330b64cf578ddb0614ca53e910ef0ad17c8 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/strategy-builder/StrategyChartTab.test.tsx` | text | 17083 | b0bbcaa0222b9b65a3242fa990eda21ab82624139422e35dc08ec6dbefed71e2 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/strategy-builder/StrategyChartTab.tsx` | text | 19794 | 5b0d764a746f7d139032f6dc8abb65bf7d96feea01bd64675581116a84d5389d | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/strategy-builder/SymbolHeader.test.tsx` | text | 4241 | 5b4b77dca7fd6e04a06565099f4b9b5e69e3169ed2f71672e498d20b50b66cc6 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/strategy-builder/SymbolHeader.tsx` | text | 9697 | f61c279e9cd398e53793dc4bb567429ced7547ebfa654e7ecc5baa217589b850 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/strategy-builder/TemplateDialog.test.tsx` | text | 4751 | 125dc0f220936a95622d23e6b1b1b1a0566937034016924328f393c919d7c957 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/strategy-builder/TemplateDialog.tsx` | text | 13377 | 25d16431875a90ddc73539e157927cca964f697340c32a147e697c921e7b5ea2 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/strategy-builder/TemplateGrid.test.tsx` | text | 754 | 64877a9cc6a44d42587b2ffbac0dc41ee10b526627f7aa5098b2abfde031e366 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/strategy-builder/TemplateGrid.tsx` | text | 8397 | 398a393448f9742f1a898cf1852eeb37c4d71df29118e8bd4fc6602ff3336588 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/AgentPanel.test.tsx` | text | 17252 | 5e35c3419f2ff3cd8c6af1970a05d7ba89d0bb63c8a8b8cf817077466668f359 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/AgentPanel.tsx` | text | 12463 | 9209cae0e662dda65483a429d072bc4d9d94603db4e9a4526308512769b890fa | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/AlertsDialog.test.tsx` | text | 3930 | e836b76d1776d68d3e38fc5d6f2d888a509675968997157f05918a51e9a56707 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/AlertsDialog.tsx` | text | 20783 | ea4c7e4d235b9b73fdc57bb792724bdaea055a963ce010cc3622effa8b939537 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/AlertsPanel.test.tsx` | text | 15229 | 67c39f10e8f563d73787e6aacf7de9f888b6d4df82bdd1e550783094fb47cab3 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/AlertsPanel.tsx` | text | 22993 | 6fc30bfba826f73fa8bd5f5795ce816ab4079aea44e2adefa2ee53babf587cb0 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/BacktestChart.render.test.tsx` | text | 1683 | 35573f8770d350fb663216b0819e84a36f756098b3e0957650ff47622bcbcdbe | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/BacktestChart.test.ts` | text | 4333 | 11165445c2bcf2cc7e9030a388a6bb2bccef5e96a3c423be17ccd60fd43e288b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/BacktestChart.tsx` | text | 12364 | 87af292e9ae4eef0201cc65674eb4342ce6193517cc0b1e03c0baa759c747777 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/BacktestPanel.test.tsx` | text | 8525 | a1a4b290e9b43692470857e18854854f16e8c54d4bb76e6620d99a64743c9422 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/BacktestPanel.tsx` | text | 39102 | 65decca3ad3c8572541ccffbf8050e1808317ae1d594a75c850ff7beea523c06 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/BacktestResultTabs.test.tsx` | text | 3970 | f5aba8b99fedbd2a830aa828c4ed34b108a0c3a03ab2b8077c07a531dd7b50c4 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/BacktestResultTabs.tsx` | text | 7267 | ed1e611be85018077e86adb3c567dee347569366d245e153c705bb130f133941 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/BoxChartSettingsDialog.test.tsx` | text | 8801 | af23ee47c5d9fccdf8a542a12a486b76c1059a211cfb4e797b3684c7dccbcc19 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/BoxChartSettingsDialog.tsx` | text | 18876 | ef02f81a4f32dd879da81a665fcbf98299cfc41aeb92eabd504a07fd01761f36 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/ChartBottomBar.tsx` | text | 3521 | 265b671adf5c8b3411504f0e62c6f4b065032e5034e3390c2df87fd1ac1bc921 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/ChartDataDialog.test.tsx` | text | 2451 | 3cd89b3b80d986f07188f0fca1d1db332dfd0b00d0d40b7b4d24451614768fb5 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/ChartDataDialog.tsx` | text | 5702 | 9c65dbbc2550090d5dd758dfc21831b20fdbb6afbbf909c91e8eefdce39ff4a3 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/ChartPane.actions.test.tsx` | text | 17501 | 50a07fb187e4f341fa5b2a5a3f4047c250293c5af40474d5f96647c1d8253f60 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/ChartPane.test.tsx` | text | 29969 | 4965cc6f9ab4c6beca8a3fed04fc2517c32ffd1d496269f422b717c5fd29232f | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/ChartPane.tsx` | text | 98226 | e9b39292d192439d1834ba25e70691775075fab151612a684e668af64910c874 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/ChartSettingsDialog.test.tsx` | text | 14319 | 92b9d66e27bd313086c429518c8ab1e9bcbb8cce0dbadb9a55dbd37a9b318973 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/ChartSettingsDialog.tsx` | text | 13857 | 1029dc98c0007ba6f41c463b3b25ffa29adf775aba7c937f41ec93ee4a5a5d39 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/ChartStateOverlay.test.tsx` | text | 2163 | 94a99e491e56a37d95a42bc3c8a548d981731f388664d9f5ae94efa4ffd19e0a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/ChartStateOverlay.tsx` | text | 2758 | 43e727f8a0dcf2ac21a2aba974013d593f9655c9eac8b974e422407fec1bc50e | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/ChartSymbolLink.tsx` | text | 1162 | f0d159d163289f9654f44e287904fd833b6285bb316b4e89f0b23f195f88d4ae | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/ChartToolbar.tsx` | text | 516 | 2e45bdc2426c8be2f1beddbd54191820610b3f902e1593aac4aa99ff00a06a85 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/ComparisonMenu.test.tsx` | text | 6019 | a0b09230cc46d97e037b7d961e21196c98d99b6eab83e42d34e3b113e31f68fe | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/ComparisonMenu.tsx` | text | 9062 | 885d1de4f8a51bcfda45c63c5598bdcf9cb62b889818cb4cf083d088e2233c7f | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/ConfirmStop.tsx` | text | 5050 | cf2b922858c508386f68342c163612e0b2dc95c17c24deeeaf66d137588f0af1 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/DataWindowPanel.test.tsx` | text | 3842 | 19de346cd698c70c616137eb922ab05bf449ea46bc33f025d5dc48ef06173bcd | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/DataWindowPanel.tsx` | text | 3395 | 91c6ecaf1630eb45f4eaa016d85a48dda58b422610e2391a79f6305728de9778 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/DrawingLevelsEditor.tsx` | text | 7181 | 933708d8b48ced816b12903aa4e8bec5307cd1cb1b1cbe7d52b447c95cfa5bfa | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/DrawingRail.test.tsx` | text | 9668 | e66d11a12a250b0e90eb94004ddbee9c08a63a9203028f3eadf8264e23a5488f | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/DrawingRail.tsx` | text | 23642 | ef780f5c8e8b47ffbec5c6e7f8d023fc0f16c112503d1f6d1ff47b15dd73c880 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/DrawingStyleBar.test.tsx` | text | 5532 | deb2e62beefa2e79bc8c76cf154fab64456b5cf044ab6185e1b4ba2c3e6c5a3d | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/DrawingStyleBar.tsx` | text | 17272 | 3a0e16ec58f54e1057a202f015910821441c1e502971314ea9719d3b5b68904a | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/DrawingTextDialog.tsx` | text | 8878 | ff1406e9454d991133b5a78c19282d6a115131d79b9f61c895973cec8ca4bfee | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/ExecuteBasketDialog.test.tsx` | text | 10198 | a7987adffad3562a8714df91e79d0dd9955f6f6ddf6dd75cfec9d172837df57f | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/ExecuteBasketDialog.tsx` | text | 21146 | afec59d6c478ee3a6a84070d91adb6d1776de665ae435466c09e6bdb4167ee48 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/GridDividers.test.tsx` | text | 3126 | 72b5faf3d416942a388cf213abfe854910a31c8b129674fdcdb4e2708464e61a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/GridDividers.tsx` | text | 8501 | 522c737a76b98b7ff4b4f68a3d59a5efffd3a762a72f291813f97e3d9dc2437c | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/GttTab.test.tsx` | text | 3001 | ec28841c0f74eefaf0b8cb57500a706c0f2f60b0102813dfe754ceb4939a0a18 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/GttTab.tsx` | text | 27316 | a5c804093cccd1c12ed47e510509f1678f02c0c8d09ad38474f311196cb9d8cc | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/IndicatorPickerDialog.test.tsx` | text | 8728 | 68a5b6debf796acf79102c9dde6807ff14997a7debae3c0396dd860f865d56c9 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/IndicatorPickerDialog.tsx` | text | 14764 | 1e63499228477bb47722c6015529f11b963534ed61240effc15dc17b9a836e57 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/IndicatorSettingsDialog.test.tsx` | text | 12918 | a72adc3d6fe4f0702365701d991d036b6fed98b0b2be4bd18205e0b9680eb986 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/IndicatorSettingsDialog.tsx` | text | 25898 | 501ad2c969a8dfadbb49ec7308e2319d5d63d2d01b001ce70f228e8ee0918c2d | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/IndicatorTemplates.test.tsx` | text | 9999 | 66294e84aad7a4185ea2bd364a6c3588b75016340956788eb92643f0e7dddc81 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/IndicatorTemplates.tsx` | text | 14177 | b0b37706f915a260844c3b1f7c7af9c8ddc7dbafbfe756bcd97c8abafc01eae4 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/InstrumentPicker.test.ts` | text | 2741 | e715e3900603d152346063563daf2baa70d53e11e9b0f378b43fe9dc5fd08cf9 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/InstrumentPicker.tsx` | text | 8881 | ceb32286034a3d70b7a888b6f379401f9ca2e59e39d4ad07a9725ff977745527 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/MarketDepthPanel.tsx` | text | 5521 | 7d93e100148e3bb2139c752486f3c48e5eaa8d87e638bbb9ef25dc10bbb40728 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/ObjectsPanel.test.tsx` | text | 6808 | d01785a4017aa4b6c952a6201d325c6c10d386e4bb1f0047ee172c9c79750ac2 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/ObjectsPanel.tsx` | text | 9426 | ae6a96193c1be97e5f8f5f1874e3f65964b6457ab4189774a7c7c5265bfcafad | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/OptionChainPanel.test.tsx` | text | 14948 | a3f84211874fc186eefe4ac6e9debee90601a769b4e8982de51c5197b97c75de | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/OptionChainPanel.tsx` | text | 34880 | 8c5cf9d9e2bad0d39037595f3e6c1860bb516ae90caa9d507c167289fffd22b5 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/PlaceOrderDialog.test.tsx` | text | 6068 | a608f45c2aefe2a89998e29083ac6dc519334040ffe12a85989d883d37a0b486 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/PlaceOrderDialog.tsx` | text | 24219 | b612fab0697ef0035aaae205680067e179a0e674bcb6d301171f51fdd693e066 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/PlotStyleRow.tsx` | text | 10568 | b773925822c1ac16d55f518bafe1376d59ac197324fb3718d9b6eec311181f96 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/PriceScaleMenu.test.tsx` | text | 3975 | 84b218846f13d9ea1b7aec199c91104426df91495e7217e79b5e3978948de49f | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/PriceScaleMenu.tsx` | text | 6602 | cb5257d6a0f6fa2904d42766dc2ddc3f9ca452bc21be5372efa7d3594df4feb9 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/QuickEntry.test.tsx` | text | 3469 | 71febdc7a471599aa0b98830b7e8264ddcdbe8651eeb42dfd27446e2b34e1a49 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/QuickEntry.tsx` | text | 5822 | 1a368a46c2fcf07f2f995ddf54954d9680563a1da6189de27466c1a4aeeba2f9 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/QuoteHeader.tsx` | text | 4140 | b4b4bace6cacc901b14f30a3516ab897a8cbed920858e89a9e033099c31d5a7c | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/RightRail.test.tsx` | text | 3444 | 55393d352f17304d80c694c70fcba9e6c4931c6434a715ff17e3fcbf31acaf16 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/RightRail.tsx` | text | 7068 | b9c17f3525aeaf24810adff30fb81a0a0ada4a7d70d3a9fe1bc9101ae530e5f6 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/ScriptPanel.editing.test.tsx` | text | 8964 | b0ab9f809acb6af0db56b01ececbb7ad4fa67ea436b7a0f75b26e56ae1caf8cc | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/ScriptPanel.test.ts` | text | 2050 | fe50ad03259b8685c178a94f3997257ba0e2b1d9b7d033c6d0bc77d506fc9cf1 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/ScriptPanel.tsx` | text | 60071 | 8d2b11da9c5e9d98f540f9959ab5adcead11a8e86f38dee97e3f7ba811f02298 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/StrategiesPanel.tsx` | text | 40501 | b743423f43c487c772a56ea296b61303f5b1eadf703126b085342905583886c3 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/StrategyBooks.tsx` | text | 10553 | 1ac857c3e962d79bdc716a2025954ec131f6eba2b26c2a8a515eb542aa2defa7 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/StrategyInputs.test.tsx` | text | 2135 | b84d2b0a5b7cd552ff23a315af3c05299e6c3e0c2c4259ce168ea1a1327e994d | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/StrategyInputs.tsx` | text | 6376 | f4a5a90138eb3dae3b8682d36b856ff07a6e722b0e68f019f184fb06f95309d8 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/SymbolSearchDialog.test.tsx` | text | 22330 | f8f8f1b9c691531c26dd7b7644f2376de3600c1a76a70ab86fd1ac48ba46a88a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/SymbolSearchDialog.tsx` | text | 24810 | f9aeb49e5b249d14c46878b457fc14b154ae8b78b6d938fd28cac65e48c76b36 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/TickBox.tsx` | text | 3810 | aee14ca588ee1aba5f8f75602f2360a45a2a801ca3b0ff86348b6a2b66f12d8d | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/TimeframeMenu.test.tsx` | text | 5042 | 27f50ff189b4269d5442f395d27ab8fc785c052d4e667ef83537fd4361ccd5ef | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/TimeframeMenu.tsx` | text | 13745 | 7b631d3b47aa05e3e61914f0b7cfbb5a3df761fe74b6d6f1beff55a960e385eb | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/Tip.test.tsx` | text | 3898 | 46ea84c0f68f9f25611a21404ffd00f8d619409b99ba824533480731cddad80b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/Tip.tsx` | text | 7097 | b3bb3ecd6b994586d21a01a15acdce47c2238924a95e08d95d5fc84c25fcdac9 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/WatchlistPanel.test.tsx` | text | 21188 | 31f4514919d962e4033d77e408ac7e1b5e1647118a139582f3b6b70b6ac9d912 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/WatchlistPanel.tsx` | text | 52021 | 0b2f7c85d20e99ccb7b7c795923b670ddf97bcf7fceac9ae31f18ea17d07614d | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/WorkspaceGrid.test.tsx` | text | 5828 | f769b64a115b7710c94c3655d971de7efe6b7f0d842260d83d1687b02de46370 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/WorkspaceGrid.tsx` | text | 6473 | fa3ee97f232f02e6c12d9486a809411b40190552216d24370de3e42597c44c23 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/WorkspaceMenu.test.tsx` | text | 7494 | fd88c8c53092bc1230339aff155c5b63006eaf326c2afa2eb328c03ac2a05878 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/WorkspaceMenu.tsx` | text | 15145 | 64d5c6f6bd789b8778297d533ec4bbf615128d2d8827f1ef99e1fe6e8d546001 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/WorkspaceReplayBar.test.tsx` | text | 8261 | 3d779dcbd832d2fd02c7bf9f5f75e1142fafe92da86537f456f0b8d68175f9e4 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/WorkspaceReplayBar.tsx` | text | 9111 | 5a84ff965e2ff897f2308f0ce51eb1fd858e419be7b393121263d2bf646b7d28 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/dock/DockShell.test.tsx` | text | 4874 | 806ed37a47f844f57724e25b87501fccf4e909189a5e01e4023a128dc3d19031 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/dock/DockShell.tsx` | text | 9852 | ddc8f82e91edd20cd0a683c0d9e5e154ab55c82d1830625b08dca6e0b15485ec | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/dock/ModifyOrderDialog.tsx` | text | 5301 | ed1cf05ad9196446207cae1de9f9ab4ea309768db57f299c55fbb909ca9cf678 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/dock/OrdersTable.tsx` | text | 5620 | 2578c169beb583b110be00dde09bf54b72f79fac8d94fd7dfa287d6e7d924ad8 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/dock/PnlStrip.tsx` | text | 4167 | 2877e9f1b1f435d94e42b06e2d1fc4b86aab815a0857882e2e2c5e89bf5616ca | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/dock/PositionsTable.tsx` | text | 5506 | 9845a63c8af6825f6b75456d2eec65b165ce3a736c53c284a9f9dd7c2bbf9ec7 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/dock/TradesTable.tsx` | text | 2918 | 7b893c4c315beda943a1092545e8b4a13be7b7ff82ee1005cb0acc2266341f03 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/dock/TradingDock.tsx` | text | 9007 | 131a531816c5e428d867c6ac56a8170dd4e8709e57e4dd563a85c9ec9f5869d7 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/dock/blotter.test.ts` | text | 12487 | 2fc55b39d3a9a41d75045e89b5f0dde96d06f70ba941404002c3ed019cc454e3 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/dock/blotter.ts` | text | 8293 | a91b60289d128628bb2a48c134c3ce35b804ec5418ee296b5aebdfcda583e77c | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/dock/cells.tsx` | text | 4446 | 5f3ee6311cfd5a4ca58f72a87157ba96d9bda0d015e483dcc74d45732d187d8f | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/dock/chartOrderBridge.ts` | text | 1184 | 9275f8109b954ff73594bebaf8b406ce1420c12a9bf2c980ff8a12e1bac61862 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/dock/chartOrderRows.test.ts` | text | 6431 | c70057516cc34043a9129bebd347ae305f9e2f526b3080e491fb7a62bdc64168 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/dock/chartOrderRows.ts` | text | 10522 | c216ed9bae1a0b3aa076d957ef2028736d64b25b84d5b65709b18b7f0a387004 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/dock/dockState.test.ts` | text | 2574 | 946e0d95398bac59d32732c600cb137ea1977f74bd5ebd396b5991c2485ecf51 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/dock/dockState.ts` | text | 3509 | 90b57830c61a342ef236109a3412494d0fa4e7467d2a15b0ba101b3524b1ab3a | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/dock/format.ts` | text | 3153 | 9ea88a1826865afb3d2c79b0ef5efdaa44bfe41069da0ea5cd6f623f6efa7715 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/dock/orderActions.test.ts` | text | 2390 | d51207502c1350b14112ea16ae43ecdc6391cae69fd8b545ce8a94fc4ed2027c | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/dock/orderActions.ts` | text | 4287 | f0e9af8983e0805b0c09e098b5845e03a1f25023e4ae621e6ce6e7ea36c3e20e | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/dock/orderUpdates.ts` | text | 7103 | 93eaaa060856989d0ec4393b05623a4d8ebbbb532c143318b1cefeeb471db4a8 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/dock/useBlotter.ts` | text | 7814 | 6585f05bca28aa9ca62e4aa1a56547c1bae0d3ac63a027f40ba9c48d81141343 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/index.ts` | text | 427 | c673cfb1f507667abe4f85a911699b6fd7d0a6b434b6ac030f75a67333c04d14 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/panelShell.tsx` | text | 8084 | 9cfe4150e88b1aad02c121a2c835345f90851504319c8e5c8a4fac9b1b14c3a5 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/railStyles.tsx` | text | 1339 | e5803ac877c3696a11f1e200a3bb1c70de80df6373b75eaf5b669d522984721b | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/tokens.test.ts` | text | 3372 | 7e21858da95b6fe62d57c52e40e4fc4a3241107fa6bef1fd5bc33cb60f89ed97 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/toolbarStyles.tsx` | text | 2950 | 058e187b3a3d834b0e806d8e5643f9acbb0c767819d61469299d2b4b386590cf | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/trading/wording.test.ts` | text | 4371 | 476b9ec86aef717aeaa444255383e1845a8f3a137f9c65faf006ab42f52cbeac | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/accordion.tsx` | text | 2011 | 1f7020132aaff24c23142cff20ccc21e5ec6adba7b8a7bac37347ee98e6c47c5 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/alert-dialog.tsx` | text | 3476 | 47d831d4e1cd39e9a0a8d78df0d5af1cb0a7806dc3de950c416b62c1093cac48 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/alert.tsx` | text | 1651 | 331ad2812cd15db66caf5e074b6c9ecfb3c131c8eed42c24e6d80c93f0727c5c | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/avatar.tsx` | text | 1071 | 6044339761b6b25fd82b8b13e8da8549d3ee72ce94fe929a5751ded73efe2b83 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/badge.tsx` | text | 1621 | 75b4ad727d1971ddde945fa3bc3e5833fdc2e856d8eeedf47a6ea17b55b23f66 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/button.test.tsx` | text | 5520 | 0cf116f3963f59251e5c40547ad6298b2b6b12dba5bea30e0854fc08da4c4b5d | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/button.tsx` | text | 2263 | cbd670539a4dc9c9ad8993c3efc7a0b2e20f73024c1fcbbf9acf4b460db25cba | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/card.tsx` | text | 1996 | 00e2858a1b703848e40af13c02d397d07609cf2adafba51699a8e2e3e55842c7 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/checkbox.tsx` | text | 1087 | 8f0acac1d554b94a62947581f4886122a6d0c7c2ed5e555252c87e60a3648675 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/collapsible.tsx` | text | 340 | 9a10702e7919bf60637256e441876a4deb661f189560d4a72410e6e9c692dd85 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/command.tsx` | text | 4958 | 3964d6ac725d943c9c59117fe8e78a9a0acc77f16b86a6910908a1632d69cb59 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/dialog.tsx` | text | 4329 | d20fba4d9bbe3faf673bdaba22bf888bdc6b1adc7b61d9c611bbcf67b84d2034 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/dropdown-menu.tsx` | text | 8908 | a96c86a4fd766d195c57b07cef5b37979f415805a3f8f67ee3a575d6cffda9ce | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/empty-state.tsx` | text | 634 | 5cbf00a1b36ae7995a9a232608ee71b83b2460b841dd1ca5fb9047e82742a6be | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/input.tsx` | text | 988 | c7d3c9118010862ee30a62268beeabade201f0c269703e9f454081cdc6939287 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/json-editor.tsx` | text | 4955 | 92fdea3696b88887e1862c4788bc1d4a55a8e664d6a27046be8ab89090ebe2db | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/label.tsx` | text | 617 | 5465045d58b6e81a29cc4e56a689161beee7dbf5a24f7fc10fb793a4e6dd67bd | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/log-viewer.tsx` | text | 7955 | 9ef02030088447c6241413fd70563dee726fb07260a74008d3445e0a5b1a0790 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/page-loader.test.tsx` | text | 2549 | 1c54fa86dcfedac1117c8bad2e1c7883640a596d50e300b1c67ae65e74baa5f1 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/page-loader.tsx` | text | 1420 | 7bddb3757b6fbdfe3bb60ffa4177fe52d74118b3819d3c932031b82eb97a4521 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/popover.tsx` | text | 2085 | 09c7a1bba9cd31b198da5b32f070227b9e19d31129389a90ee4663c06dad9fe0 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/progress.tsx` | text | 1045 | b7fe8c4e5ca26b74e805f9c6b23b7d81c46d5a7cb71c2bffa1f29843da335af7 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/python-editor.tsx` | text | 5813 | 830376084baade7f6e421cb0feb13156215cef839dc5f0ef169f1870da0b4b61 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/resizable.tsx` | text | 1872 | 6e7566e18a0f7256bf41b328ca85bcc5bc7bff97b901b09870ab80392d835eae | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/scroll-area.tsx` | text | 1670 | c1ff3e5f7def688687eec404609faa87287f146bac7295c4a5454f3709880890 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/select.tsx` | text | 6481 | 4417e8dabda11bd1b5cf8e1dc2317e728b9d8fb37bc3413a0cc8c540a08e1a17 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/separator.tsx` | text | 732 | 06a52408e2418206146cce0f93cb5a530927260b89bc4292ff2abffb6c5bea7e | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/sheet.tsx` | text | 4215 | d1bdccb373401c25fb618f9e7dd9a6ad80fcd43649d51ed95d837a9f5549df76 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/sidebar.tsx` | text | 22195 | 32514c1547fd4ad88b8cc2d1442d798dbb08802179e41d7058877f83efca7f0d | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/skeleton.tsx` | text | 289 | 68bf11609c04a24c046838df50485a010c92186134a1038ba0ec77af843ee6fb | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/sonner.tsx` | text | 1079 | ccfd3a855b0982c4ade61b54539ce483938b3d774cc6f12a8f45cadd961e3c06 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/switch.tsx` | text | 1166 | eab5c64b8e18f4e07589818515b0417bbcdf591fda3cada4ab47c8e1c52ee168 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/table.tsx` | text | 2451 | 37be43d8b89408070a0d959ba50ba89918dfec089376539ea7ce2c428eca8824 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/tabs.tsx` | text | 1996 | f2b43d606074e5e6ff1972833c06b875ecfd78c1787747434eac5181213e74b5 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/textarea.tsx` | text | 730 | 72de1c1c86e04d92175e5c784a46d1e930712265e17df5ac19943ff31d35daf8 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/components/ui/tooltip.tsx` | text | 1950 | 087ec4365b7d777bd3ba653329ef9383ee8ea4dbbf0bbce432a8be6fb09e0a9d | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/config/navigation.test.ts` | text | 3891 | a1d64f014c0a7e4ea87474cc2403077da316a570c3e02acbc694e6a864973126 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/config/navigation.ts` | text | 4322 | 94380892b60759d98414eefb2adeb72910b7c28a2bec5ef64b34a967aac428a6 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/contexts/MarketDataContext.tsx` | text | 5387 | 5657c3d451fe642fc082db71a35b29cad0ebab6c5a3bcde8fce8de91056048e9 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/features/nifty-algo/AnalyticsPanel.test.tsx` | text | 7911 | c44018111ce84160c8d79538bbb6db13b29a7df5213c6a075ab4544f81be5227 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/AnalyticsPanel.tsx` | text | 12939 | 4f179665a56443d92b11a52db806234a902a994ee30075ac9ae68e80bbe1e86a | frontend source/asset | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/CalendarPanel.tsx` | text | 19393 | de7f173e304bc1134a37e09be597f53c0904709fcbb51c32f31391dd8f75c616 | frontend source/asset | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/ComparativeAnalytics.test.tsx` | text | 3429 | 7c72ef9dbff14bdb2dfcc6394672d054f5480064bba57ee8105d4e9f67c08c62 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/ComparativeAnalytics.tsx` | text | 6943 | 67635f9a684559db82d65eee2b73e049cd072ef30df638bd6bfa507706a73595 | frontend source/asset | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/CompletionPanels.test.tsx` | text | 6602 | aae8b99a265acd0b09f5b93e4b7d012c02d604bcc6448330baa05152da1838b4 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/DiscordPanel.test.tsx` | text | 6538 | 149938e408a011bd7229ce58de8554d6a9c45c94e51cc2e55673d0a0db98ad8f | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/DiscordPanel.tsx` | text | 15214 | 855eaca749d2e352d771230b9b8369af20bd5be6839188ac927132bc2549379b | frontend source/asset | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/ExecutionComparison.test.tsx` | text | 3367 | 8c1a8c20e905ffcf47eac7a83c4c29d04a704b158b7ddf21a61eced13676378e | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/ExecutionComparison.tsx` | text | 4632 | fe794f5f0ad2573b51a9401835a561b3aae5c52c52b829cfff7c17b89f564b1c | frontend source/asset | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/ExperimentsPanel.test.tsx` | text | 9186 | bec9f42ea4605f500f2eb4de3652a3dfa7ef245c154950fdc2c9d7a01beb3cc8 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/ExperimentsPanel.tsx` | text | 13009 | f830fef90786508b05d38799b44523af3a3547ee757dc3c162d135837ec92db4 | frontend source/asset | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/KeySettings.tsx` | text | 5981 | ad13bcdb8af341b5df710add6ee62b854f8002a9e08a86928ea431ade95a3b12 | frontend source/asset | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `frontend/src/features/nifty-algo/Panels.test.tsx` | text | 25685 | 795d18b58247308b25df82b9a778d6dfadb8d9f1368eba02121229b0fadb91f1 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/RealizedCurve.tsx` | text | 2581 | f24fe641c688bdc2617f943a54c17f4eae7de30c083805dd0bf46579340c05e5 | frontend source/asset | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/RecordingsPanel.test.tsx` | text | 9076 | 65f83f6d2e73c55f94ed1e819132ae90d90478dac17d8440fbcfeec798cba256 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/RecordingsPanel.tsx` | text | 11370 | ab46d44f0640cf61e5a2619fbdda6b30fe3f36228ff9619d129edf28f491f468 | frontend source/asset | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/ReplayPanel.test.tsx` | text | 2685 | a90972c7d728c85aec36483b843bf61e500b951091faae2822ec9b0786f4d5f2 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/ReplayPanel.tsx` | text | 8216 | 72ff14aa707c979fb0f8d21d810ab3a06a0300832265ba5412e247be999c2d9c | frontend source/asset | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/ReportsPanel.tsx` | text | 5980 | 6e1f8e252a479315c3064c083d89764579e68a3d3dc8ab4addb0f10d4421e3a9 | frontend source/asset | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/ResearchOperations.test.tsx` | text | 3927 | 7b2e0d22c4f007520c62ead6ee2fffcf492709fa102ffbbf1f48ef2a2125490a | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/ResearchOperations.tsx` | text | 8228 | 55c7abac67f699c79486d266ef493962ae85048e29cdca3ec54f07ef20ae13da | frontend source/asset | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/RiskLocksPanel.tsx` | text | 2878 | ce8c2741c45f23785f00c43c10da2758a13a8f06f2ba58a83aa0aa07e677f8dc | frontend source/asset | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/SafetyCenterPanel.test.tsx` | text | 6822 | 3566188f730637d0d87a718f0e968eb402c4b24b54ccf1ea324ab2830951e276 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/SafetyCenterPanel.tsx` | text | 7767 | fd6c6f01cf4ba0e09fdb9bf0aec4ffe817e4453a5c6a7da1892c4f62c37e2f63 | frontend source/asset | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/SelectorPanel.test.tsx` | text | 5720 | 357d5b6f1f52dbbf9671f330f3508290e95bb1db5c59d6defda415129346715f | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/SelectorPanel.tsx` | text | 7399 | f37a3ef0c6372a6c70bf174605684b0539925226f6b087377afb09c648147369 | frontend source/asset | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/ShadowResearchPanel.tsx` | text | 6443 | a2b453cdc69f1047f05835a2753f816830564aef9bd1863a8d7352d140a24325 | frontend source/asset | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/TradingModePanel.tsx` | text | 6749 | 45be765a9102f634841f84a34e2ce54f25f52ef8325cf5d915fe26f92300b3f5 | frontend source/asset | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/Workspace.test.tsx` | text | 6653 | b5640dfb5224a562f69094b1be4598f30c6299d3118602afd49b698d6441cb79 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/Workspace.tsx` | text | 19365 | 995e45b90184a38cd053f0ed74b1cfe117a3a47efe2df85319032568c7ab87c5 | frontend source/asset | DIRECT | NOT_REVIEWED | PARTIAL: configuration editor lines via grep |
| `frontend/src/features/nifty-algo/api.ts` | text | 18256 | 5132077270917428980da0a4df484c9ae3b014da9d9d7763f92e37c2a9c21601 | frontend source/asset | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/errors.ts` | text | 1099 | e31b667468590d344a9bc4e37813b817bf35ea26f88e0c6e03a5a8cd685df12c | frontend source/asset | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/experimentApi.test.ts` | text | 1830 | ee0453a42bef3055628598eff7f574170fb80babdd7f12b4959ab6562ae92be9 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/labels.ts` | text | 3276 | b50b3d1236a2816e9e37d5bfcb5567247d1b63050e9b3b346f4697d061c17124 | frontend source/asset | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/parts.tsx` | text | 1853 | 7e14141c337004cb9b35f9741a2e5dc274527b662e9cfe3fe1ab74c80788a801 | frontend source/asset | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/recordingApi.test.ts` | text | 2180 | c96e357cd85143a1712fe952f8bf1f79362b6521545e64b84bbb890f445d6107 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/features/nifty-algo/workspace.css` | text | 7881 | 20f3c9806ff28252dc95e3e3077a6675218772420f0a7d58b8912214c3cd5179 | frontend source/asset | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `frontend/src/hooks/use-mobile.ts` | text | 584 | 86cd781770e3b67544538f3816f55e219d43a0ecca79665fd748e9979e0b10ee | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/hooks/useChartWorkspaceCatalog.test.tsx` | text | 8662 | 96c270ccb435dbf0220df4950243a2eadb6a060ae7a02222e5f475baf1cead92 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/hooks/useChartWorkspaceCatalog.ts` | text | 5000 | 44c5401c81ee085d6162442391a195e72815a67d84c52c19e5f5886a53c0f842 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/hooks/useLivePrice.test.tsx` | text | 2895 | b0abc4802803f4887ff45e4f1973c89f956d0c3622489ae6544795adaf02296e | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/hooks/useLivePrice.ts` | text | 11792 | 487e2cd8a5c54a60da9f4249c334ec1ab5060b94a0a47b9fbd986ddb73c9312d | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/hooks/useLiveQuote.ts` | text | 11726 | 55ba2770a218ff407032a69660d0ea16ffb99121cd60105355ccb15041929753 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/hooks/useMarketData.ts` | text | 5776 | db737b74542500834b307623489f053e1d6719672eaceadef26099788870c4e4 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/hooks/useMarketStatus.ts` | text | 7044 | c52da68675afd84042b29d8dabf562dec0e80371644d21869b0d73ef63b2218b | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/hooks/useOptionChainLive.test.tsx` | text | 15065 | fb07d5da9b6d332cfc6a282ffc345ffa240407d56e2eec4e16c10060de232d1b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/hooks/useOptionChainLive.ts` | text | 13860 | 3c2b04e4a0d2d54ac8ada1c73bbc66692fd5ed1440247e5a31099d167f10a3cc | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/hooks/useOptionChainPolling.test.tsx` | text | 2542 | 31e86b37ed93c28855b4f372722d6728dfa60bbd317522aff81207625f55adce | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/hooks/useOptionChainPolling.ts` | text | 6817 | 1f81e2dc4479258c1bf8c065fb9e867f992e79bc0622c27891dadc278133ccb5 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/hooks/useOptionChainPreferences.test.ts` | text | 7280 | fa6f38218e3e2bf33b6dbc86de70f0ce83b6908c5ec5fcb5612218ed117250bf | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/hooks/useOptionChainPreferences.ts` | text | 9613 | 71ad6c420f498e8f76f2af11117c559c331fdf176efa457eea705dfd98f67bce | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/hooks/useOrderEventRefresh.ts` | text | 5032 | d393488fb3311174854ded465884aa5d984ff9c5193fd1d43dded9d68193a712 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/hooks/usePageTitle.ts` | text | 3860 | c99a901559764b80c13794afbe24e1e034d0c259b889ef496bf85b583f302675 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/hooks/usePageVisibility.test.tsx` | text | 3647 | 3c338db560808620df454487edc51b0723dd4ab71f3cc039ae9abb1d316bdf3b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/hooks/usePageVisibility.ts` | text | 6294 | 29f948d84cc1e44aa3e886ae385194e63ec552570a0fef6894b4c0f253bb3baa | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/hooks/useProfileMenuItems.ts` | text | 1151 | 667cf923eae06f3fa06b1dd85b2b75b50e5b9dc958aaf76d10c6da33a8f2fd0a | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/hooks/useSocket.ts` | text | 11062 | b6147433df18a6621c5a0a091cbaea397f8f8dc7fc1d9d6b1e20937580ca0e93 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/hooks/useStrategyExchanges.ts` | text | 2075 | 14a5ba403d95b73b25bc9775d4115403545caa617e3b700daf40dff2d0ae0e7f | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/hooks/useSupportedExchanges.test.tsx` | text | 1688 | a26d1043180c88132dd1454058ed3445fea162018fdcaae10632e33f98ed3dbe | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/hooks/useSupportedExchanges.ts` | text | 5112 | a3482d29f92db8e851773000bdd69ee76dbcb2513128dfc01beab7523c81ef69 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/hooks/useTrailingSL.test.ts` | text | 2764 | 74e16d854af6c9bd3db299e210d5fa43086d8507490b0350774461ada1c93c7f | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/hooks/useTrailingSL.ts` | text | 8016 | 56c08628ddb1a240899c01d0d60d1d70dc9ca8e4c7de5580d150ace5fb37c2f5 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/hooks/useWebSocketTester.ts` | text | 11443 | dcc404fb7215ba0f143fb080d5c212cfbf5a19eb28c2ce9e11ca1922d23abae4 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/hooks/useWorkspaceAutosave.test.tsx` | text | 8512 | 6a5e40f63cf12acd3d792f36afb7d14755db16d35ce79e779ae00ca85cff2bb1 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/hooks/useWorkspaceAutosave.ts` | text | 5827 | 91717262d3164657b6426ba06bdbe94908ea815f4dcee1f7d1ef6de570b90221 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/hooks/useWorkspaceGridTransition.test.tsx` | text | 5880 | a3b4d5305ac1deb9f4b1acf10c0a14a07f5cae3dc8657f7451c0413eeb8b4e04 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/hooks/useWorkspaceGridTransition.ts` | text | 4191 | 843cfd4217b6fdda422a0f1d869ae328d23c03288e154908273fb7b316921bd6 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/index.css` | text | 35566 | e29bf5558ac8bba67a94c8e39484ddc91b0902384cddaf8e8094f3daef2c8dd0 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/MarketDataManager.test.ts` | text | 3113 | c2f4d13c4fe87f362d5c9d58028776f910f21c624c4245a1967d7bfa3b2e3ae7 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/MarketDataManager.ts` | text | 26504 | 8072f605036596b77bbcd6132298e8f56d517e2b11ca5e03a03ed9f3c8e46fed | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/Plot2D.tsx` | text | 834 | 993e34d9254ce76520db3a210a0ccdb1a4a479968355168f53603cf3279eb2c0 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/Plot3D.tsx` | text | 718 | 5ba6f853460df3c3124fcef6f9f471571c72330a928ae667e9d818996305a5ca | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/agent/attachments.ts` | text | 10892 | 1d4fa910c2f5c3e9c7ab91d108e89ca68213faeae028ba0bf1a964eb328a2a19 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/agent/composer.ts` | text | 4626 | 746b4c1a356c78b9fff6164d2b94231ee580cddaaedff5ea528660f2981316da | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/agent/hydrate.test.ts` | text | 11895 | 01e8e54bb6adc9dcb9b7b140a4e9343be6aef6ca6c6b6417ea67a0af845eb9a0 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/agent/hydrate.ts` | text | 11554 | 8d2c9834e0683e8590feb42e456d69e3aec46a1d5404bff464a015b55b6528fe | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/agent/openuiLibrary.test.ts` | text | 8467 | b7844a7ff4db4c7de758660f8ea4acd14b0db07dfcffd35a23d679273f26bda1 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/agent/openuiLibrary.ts` | text | 13228 | 864d5ebe9eac1059591234ebbd7073a227c1f5a5b8bbf642563399efefedc26a | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/agent/stream.test.ts` | text | 8088 | cb16e675a827cfeabe83aade6666540b5765fd8cdb03c544d85e76fe7790a30d | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/agent/stream.ts` | text | 14719 | 175af8be2d2d567f6c844807414f9eaad5d10504ebaab956ed7244000ec21cc7 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/agent/subscription.test.ts` | text | 3482 | 7dc81ef4b794b1b8391ff1b1275327a8d016529ad8d897cff7c296609ff1d11d | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/agent/subscription.ts` | text | 4390 | 49abd947dad256cba0bee5a897b199a22cf1015af85b94f9f3d01aa3f9a92296 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/agent/useAgentStream.ts` | text | 25062 | 02ef2017009879087bb09e93050ef43b4b333445537e987c2cfe4b5140b0e748 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/agent/useModelChoice.ts` | text | 2814 | 27e591dcd1f089b18cfd016da052a899588e7851eedd0a802e764326c2e4b9a4 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/agent/useThreadScroll.ts` | text | 2789 | 00a6c1151dd8da7988fabf024340536c20e188dbfdb6278de015592dc72dcbfa | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/agent/useVisionCapable.ts` | text | 6316 | 54b2976e509d3e632f478d1af3f067560ef5d495bbf8367b30807adeed777229 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/agent/viz.test.ts` | text | 7956 | bd78d26e4cf61f5dd889d2690b65b34fe5766ee1cf4ba7b9440a75cc1b7ab919 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/agent/viz.ts` | text | 4615 | a063e513c60944b4315db6d75826eb230812590abf1ae6adbb7c65099b175c2e | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/agent/voice.ts` | text | 39665 | 3b97edb194beadc0af5a970aeafb54e6460ba163b6c6dc231bd3f1632a7e752b | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/brokerProfiles.ts` | text | 3984 | fc83c044b0b3cb47cadd0e44e7a6e863a33240b6075728aa0a39804d7bc3dedf | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/chart/chartEngine.test.ts` | text | 1991 | aeee37a167178569a0d6f86d81f16ba272977bab2c07494a13e2b346e9f70b94 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/chart/feeds/historifyFeed.test.ts` | text | 5309 | 782e324ad4bf3810f63cdf9b5dd8c1ef17fbd66fdfa3e29392b40dccc35157c2 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/chart/feeds/historifyFeed.ts` | text | 6622 | 56c85e55979397a8de4d5b49fb9102187d2e29e90f6ea7a784e08acc8d88ef49 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/chart/feeds/strategyFeed.test.ts` | text | 13738 | 1c1720603a10559efc99831473571c4b496fa663ff8ae8fd8bd174958656a475 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/chart/feeds/strategyFeed.ts` | text | 11724 | 99af4e9d417e216e6148a9327d07c8cc426b24f1a2c55d428394e1195ea5e86e | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/chart/intervalRegistry.test.ts` | text | 4612 | 0f1cba9c3e0ee0a8d671734289d88e71eb3bd8f0c141b298af4ec9724abffa98 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/chart/intervalRegistry.ts` | text | 3326 | 75c819b756ade5efea59809ae4012cbcbd345ec8f884e17e9c1204d63e556713 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/chart/layouts.tsx` | text | 2899 | 5880dbe4c73f5056c9b522270ef9d063d1a0f0ee295502d57f5b3894a4f86946 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/flow/constants.ts` | text | 62823 | 89ccebe2035c6932b4bf7027b2479381995f5824fa55809ebc381114c7b4980b | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/flow/customLegs.test.ts` | text | 11515 | 382cf0902521fee375ceb14f10a734d72981850c22863d787ff31ca74f62c3c6 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/flow/customLegs.ts` | text | 12811 | 9a31c9c6b47ad60cf56fb8919c61143417b8c7af0299e147e170cc8c41bb4c87 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/flow/defaultProduct.test.ts` | text | 3550 | 2f1e288ee42ca7efc37110fd3bcb30a8673d72d6ee75590400afbac532aab411 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/flow/marginPositions.test.ts` | text | 8969 | 3b362c27f7048584ffd773b10b092f90225630558bb4767682769425b558a050 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/flow/marginPositions.ts` | text | 8748 | 3070ea0cc65ab11dc06e27b112d5803b3f7396d816168966af544180b584a196 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/flow/strikeOffsets.test.ts` | text | 4041 | 2ec49cb6953ddea01fc85c72deaa168d4238b9d0e1e53ede6b17a243019fd14b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/historify/catalog.ts` | text | 4905 | e8782b3e2eb649595d12f2f128b97fabea4f5258d7663efa4611b6babf8808c1 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/historify/intervals.test.ts` | text | 8334 | 58ad02fdf7724f2d74568deea5b22f8234938d65a9851cc18e720ec60cba6a04 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/historify/intervals.ts` | text | 6233 | bd7674f1f60631d2e75d1520e1c3f1d4c12fa59faa8d2dfddd997b853f11ed1c | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/historify/timeframes.test.ts` | text | 7582 | 9ae87c631a133d36dd0046b8c46fe2751ff4f37f4f38e2f1a99f64cd2d33f98a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/historify/timeframes.ts` | text | 7176 | db8c482091852ff6f8730dda1eeaefd2109617ae30a191b3e0103b4dbf780051 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/optionGreeks.test.ts` | text | 16580 | 3e6d4fa4c652a436958f55d2d67f00f6de5ac8770f2ec5efb960d0022ae31ee3 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/optionGreeks.ts` | text | 11208 | 3a61da86227ee1fff3ac138e43d7f0939e6fba2e64a61de60661f2666418226d | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/plotly-2d.ts` | text | 680 | f8c437367aa3f17b6f9d5919d9fe4228402d6de39aaf294b8da6332d77b79ba4 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/plotly-3d.ts` | text | 418 | b0836b49ab3d3ed9dfeaa164339d6e79c9a53950506c02d68704b1b9bad79c55 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/portfolioRequest.test.ts` | text | 2322 | 4a74a49ee5f4e84e2f92c7c82c3d6e69bc373189991977db3288d71185e286ed | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/portfolioRequest.ts` | text | 2610 | 5a76a0a005065fd6867b1e3133e7c5cab309c6176e98a201bc4eac4e853e6926 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/rateLimiter.test.ts` | text | 860 | b90ceacbfefb75df0dd75b0a7016752d89d86eba83a56a327e902f5c53eb1324 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/rateLimiter.ts` | text | 4576 | ba7c0c96de3f2234fa2ce245d8b5977dd70e790399dc45099fff0bcac24adf6b | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/sandboxCharges.ts` | text | 3304 | 21072db27399a02db86400ed357ebe667e6012efb994ee39fae9091193a89a1f | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/scalpingPrice.ts` | text | 537 | 717155f96288f8960b9d843707454d6e1ba21d4c47e5e718c37a916a8095cf37 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/scalpingRows.test.ts` | text | 9366 | aefd4f45c9ad118489fde11c2a832115dc52c999a36a2e31b6cb84edb8e4a98f | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/scalpingRows.ts` | text | 6715 | 2b91cbe7296097a7c9bfc33d66c23bee92d1ac6f5f4e5b9e97a76dc2f7e59bce | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/scalpingTick.test.ts` | text | 2592 | 5ca9f0a7c07270580fb1c630392c9a8eb6c358d43fe33eaf7e43266c2fd67fca | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/scalpingTick.ts` | text | 2008 | 6098c09fcf4b222738500660439132b1622a6f219a69e7131f359374cf2d7448 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/serverSentence.test.ts` | text | 6209 | 10acb716e7898cb785d2426f19b85b5c3d672379163bad54b331f26ee9843ed4 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/serverSentence.ts` | text | 4271 | 65378bcc351f08e2d96146f4f936bd122955c82fa9546bc44cf3c6b6f427914c | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/strategyContracts.test.ts` | text | 3684 | 61e14289fc58623594e4dc74da229d0b416ad1cd90ecb83da22b741fb8551734 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/strategyContracts.ts` | text | 3669 | 4126f7313579ef23c59eef08cf1414bd9ed895a60e1f6485748623d7e240497a | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/strategyMath.test.ts` | text | 29389 | 173271baaa5407ef7b904db68d55ee225cba5a36265961da908b1e71e1ea0f13 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/strategyMath.ts` | text | 40670 | de36f4879dd64b01cdc15391acda63516f7a26720c55b01894621927befd006c | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/strategyTemplates.test.ts` | text | 14429 | aadb3c0d8038c873f0cbe126bf7f71b64fecdd03bea386d2166a0b189a8e3fd7 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/strategyTemplates.ts` | text | 30236 | 2760762c7e518ae624c802e5404fc353896f78672002b43e8130545e8a8f5837 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/strikeProfile.test.ts` | text | 3982 | c0fc89e791409e7d5edc9e6b40f7d1b76730300b83645d0f0287a8c17eabc6d7 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/strikeProfile.ts` | text | 6548 | 85c4244aae05e3e33d9f59d2faf7e62be7657ad46fd19f7f9d0a15c887e0b462 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/templatePayoff.test.ts` | text | 6416 | 23d93848b90b41e0db5a46312f380adeb021ccb4abdea0b645540b840c130d3a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/templateResolution.test.ts` | text | 8118 | 8a6da8455109497d436158a9e4bf521c739b7b121b3da4e2d5d56734a887489d | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/templateResolution.ts` | text | 3118 | 49ed8a58becf2672950a286c0f7d5bc02bccc04c59affb035c099d6ca8d37bd9 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/tools.ts` | text | 4852 | ff72c91aded39fdb6d0ee2d47a360628f6b1dd8af5e5218c6ce4eec79b753761 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/alertDelivery.test.ts` | text | 13077 | 15cea11eae9ecc38cd644a19e3eb1820c77740fd5c0c7fbb22260ed7d4c3eb7e | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/alertDelivery.ts` | text | 12223 | 131e5946fa2b08191d21ab75ee824b72676cdbe47a481bc3650cddbcfa6a3282 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/alertLog.test.ts` | text | 5038 | f05604259aee112f328b17177c778ef3e45c8d1d4f076f27b2b6e4374ea10b93 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/alertLog.ts` | text | 3814 | e3f318d94ee9253e1309aa2d79442383d3c8e0f1469d02879cc8a7b7eb3cf9c6 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/alertMessage.test.ts` | text | 4037 | 3b82d84fa061c7ccb209e19896e0a003824bb2fcd7c784486e7cf643cb9cea39 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/alertMessage.ts` | text | 6021 | a0f672fac97141e307f2b30c5f48fa7432b44619193591ad04e0e44d04df6e10 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/alertNotify.test.ts` | text | 5641 | ac620506c7cfb44e842ee1c780f313907e4112c746cd9423d8890dff883ebcd2 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/alertNotify.ts` | text | 5500 | 522bc37d09f08beba3f27f86c6b6e583a6e258db178ff0db5fd35d35070a329a | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/alertRuntime.test.ts` | text | 3533 | 80fec1e699c3066818e6fce6a9df66071aa1627e5dad2fadf6f01ae550e503a8 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/alertRuntime.ts` | text | 2437 | 00e6acf3b577036cf673a976844fc7627ef8a8f2d50ffb0405468fd35771855b | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/alertsModel.test.ts` | text | 21544 | bea1ce72d12ffdd69c3b4bacb694a6fa994c459ef37416936e201cbfea748666 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/alertsModel.ts` | text | 24251 | 0b11d7f4684fe09bde49d0fa3b1bddcbbcb494233de40c3bd5489f23e5cdeedf | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/backtestCeiling.test.ts` | text | 3223 | c4748e54c90dad370a812691bfde490ab2b8e0d426ba00d23bf80c14e7cc2902 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/backtestEngine.test.ts` | text | 6008 | 96f40e1178c65ef83912232a9ec2a1c4f05c15d25f0de25c7f7f7ccc15509a2f | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/backtestFold.ts` | text | 4858 | 21d2d689ef602dc065f31fefacf5659edae4934acc0ee495f9544316c408752b | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/backtestFormat.test.ts` | text | 1271 | 67a84dc9048f51bff1d514f74f4ad8c1dfac8ef10ae9680aec8636a4edb2c959 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/backtestFormat.ts` | text | 3368 | 5dd9bf944efe53e6187cfe6944362d4e3757ca069ffeb79f6abc7ea9bc04c103 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/backtestInputs.test.ts` | text | 5587 | fcbab24caccc44e16bf88e805c5812a8068c32e8218c5cd533b625bb18ca5bbe | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/backtestInputs.ts` | text | 7318 | 076d8bf5fb19e47e30d5ba04e8b2e96ae369dd9d95584c8045493ad670b43a9f | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/backtestLookback.test.ts` | text | 3501 | 5320753f1a769b6b7d785efd07d091b8495e55b0a179ef73f30010423b97ecd9 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/backtestMarkers.test.ts` | text | 8658 | 62b02d52931e1f77992f83e19f368e992df4b9b0f35d28738f947ee2e6be31b9 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/backtestMarkers.ts` | text | 9398 | cb6c8fabc5f46da9160a058598745cf04b76752e2d5bb19222f7026c9314cdf6 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/backtestOffThread.test.ts` | text | 11247 | d43c78d4075e0126efc73cfe06a745591947d0fd5f7b4f36a3307735d3392bf8 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/backtestRun.test.ts` | text | 16421 | 97ef22412388793f027b8d0c24ab44d643a2d746ce712f1b272af54050b9e93e | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/backtestRun.ts` | text | 19274 | 3b428e6211724896cf9050a1bcbd341a6858ccf29ee0a7990f42424cbc05c6a4 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/backtestSession.test.ts` | text | 8759 | 00ed8a018753bd95aa89d8f764f383624580fdf536ed0bd71e07ce053cb64c07 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/backtestWorker.ts` | text | 6142 | d020f5be28b11efb5c486d958327556a197d9f52d011bccf5578c409442d69c1 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/backtestWorkerEntry.test.ts` | text | 2848 | 8eda75f22369fcfc7ffb25daee29cb1ac7422737cb23ff2e7cfa0f35abd99818 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/backtestWorkerEntry.ts` | text | 1567 | 28998c0e51a2835deaa3549e1fe9f4a5acf906759b808ea12e166f9966f23236 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/backtestWorkerProtocol.ts` | text | 4569 | 75d4ab88b632134771d2ba4f81c228613c478f33b8033c52916be864befe9e6f | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/bottomBar.test.ts` | text | 8541 | 5a0305e03a46c0d3c5c0110f9e8150b9ec9c5cac9ec9cc2bb6849e20bf739036 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/bottomBar.ts` | text | 14866 | 1046501af341efe8e869e1d4239be1c14933cbc8e4038a5bde5e5b118ab23fba | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/chartContract.test.ts` | text | 14716 | ab6a125301f991d40ec7bb7344afb4dde8e8c09ed838b1c5657e107a54e2071c | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/chartContract.ts` | text | 20254 | 1e5cc0fd146e28c45c2523851b40cad165a5d09238e4c46e82b62cc8c9f4a8f5 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/chartDataExport.test.ts` | text | 1836 | 6606cb416bbd7ec0e78bf2effaba6dfcd131ef33204fa9cc8e135754465f5690 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/chartDataExport.ts` | text | 2229 | f7b051dcb9c19d7d0967de7377f78126b8678053de1a4bcd8dde3c0bf54ed753 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/chartHistory.ts` | text | 6719 | 26546ca821203aada80e676f141733fe947b02c2b41ca73fcd5f836075a77dfe | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/chartIndicators.test.ts` | text | 2820 | 5e8367be44c97569ae58d4b955fd850935b66637d5e65c3843d8cbca674671a7 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/chartLink.test.ts` | text | 1559 | 30aa32473048a8954e1dd6e0a79bb04ff28043d8b6450a31187e63cb74a3887c | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/chartLink.ts` | text | 1722 | a98df7f6b635d661d78a860066338b7f74cf4d55b0db6c3fb0731a21a71c029f | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/chartMotion.test.ts` | text | 842 | 2ce0fb9a0eec1777da9c2b2c5619e2e4332ba8d94c15bdaad4c5f032d691d30a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/chartMotion.ts` | text | 836 | f3b375f69ff5902772489089c8d61f2dcc0a9358f330dc6b47f8321e739df895 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/chartObjectsAdapter.test.ts` | text | 4496 | 8dd7f0bf9a4e1272699af38eae792491fed4cd344afca4605f4173790fd905b0 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/chartObjectsAdapter.ts` | text | 2492 | bc691f05f6e7128eecc7afe50fa81308c5da19829f4a8ecce6edd61778b2ba29 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/chartPaneActions.test.ts` | text | 2960 | d48027e88dfef795e22b87ae0eb94e7e32d70f0ba378a4bd3632523657fdc0b8 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/chartPaneActions.ts` | text | 4691 | 088a469211fd51353b09d5cb4ec245ce16fc405ef6cb14fdcde1bc7e8c967435 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/chartProfiles.test.ts` | text | 32811 | 090a77ca47c57888439623020cb62ff71ef625cae4a6226de590669fec54b393 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/chartProfiles.ts` | text | 39388 | d55d9839b61cf5bf80ee6445145428e76c10a1309fdd525f8cd0cce0edea92aa | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/chartState.test.ts` | text | 3653 | ac00c39c15ec5e928dddd15db5cfdcf583d0e969ad828ad088e72f4dac66a8bc | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/chartState.ts` | text | 5516 | 251a75c26a0a6f93af0460d299a2dedfed443d75bd038e27e29a61d51679d50a | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/chartTheme.test.ts` | text | 3052 | 3de915b4b5d206e3dcaf39c53753fbe51bc362754fad19ed041b8603defa9947 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/chartTheme.ts` | text | 13880 | 2a1be431024f17ebedc14fd7304a60652015d037a9e3d6a69447ae912dc9f4ab | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/chartThemeAlpha.test.ts` | text | 7678 | 89c3ffb95ba539de71e3668ebc66e2775ce020a394a875b00065e3824a9acb07 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/chartTypes.tsx` | text | 7365 | cb07c22192eb68423e2f50457fcd4ffc7056b1bad169707c3e48ed4b16b9d144 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/chromeIcons.ts` | text | 9651 | 2f263f79d50949f399fbd75cdc30388ddb8f5505663b2ec8fdd6e85eace16482 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/comparisonColors.test.ts` | text | 5356 | f07b474c4b89da96e6a09eac89c40582ab8bf89fb2562b1687c4febc6fb23873 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/comparisonColors.ts` | text | 5928 | 4ddc526a382d80f1851433fa595bb37502e66fd90666f0219eca764c325dff4d | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/comparisonScale.test.ts` | text | 2275 | c7335c6bab3bda294bea00b842b7183d2f5c393cfac4ab61e1e7272048c3c000 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/comparisonScale.ts` | text | 8013 | 1e64b21b70cd7b93d8118f3a750434d317b285cf34d1782c11d9a3b43ab37ae2 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/customIndicators.test.ts` | text | 14819 | 6d4ec685d06760a2a78d272cde5a06d53053b90ed3915683dd1bc4363b33e432 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/customIndicators.ts` | text | 23107 | 7c2b9abf1796131a698ceda94ee71e6bd2cb3895bc2bc3d73d8902d32601b196 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/customLookback.test.ts` | text | 886 | 09f1ce61d8e522a45840b9b5746e8b8e879788ffa47d63eaf0b6829d82dbd091 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/deployments.test.ts` | text | 5581 | c0e346bcc1f8544afe03544b900ca1995ccc492e31f15d8383f0498b8307b696 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/deployments.ts` | text | 3458 | a084c87563007f4c3398b8919e96c71afa5c24afd2a285e70f1ec6ddf5661a72 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/drawTools.test.tsx` | text | 1684 | 4a5fac47466bb0751b5b31856273e3e5ba3b6af3625f28598826aca5087e3090 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/drawTools.tsx` | text | 5729 | 9034f164c972fee6c459d295d8b40142a592d389b63547408f9415760345505a | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/drawingActions.ts` | text | 9894 | f0133177cfc730b1c4e0f594c3820bcaf263896453ace0d7e938c6502ce4a06f | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/drawingClipboard.ts` | text | 3142 | 23bf6e125e0b5bac971d5cc6c4dcbdb205b14b65a370ff3a695a51b95305cf54 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/drawingKeys.test.ts` | text | 3648 | 545faa0c2bb86c3eb1b3f5a51dc747961bd7e6f6516ff799f995b79ecf9cb6ff | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/drawingKeys.ts` | text | 2592 | c91dfb662443aeafb57413d5477bb5c04d0d26616a358731a4ac8e6030eb22d4 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/drawingScope.test.ts` | text | 5337 | 2cc23c15a8e3e51436cf176fb7c071143f1d4550570aa440575619b04fca68f8 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/drawingScope.ts` | text | 5214 | 80b3f9395a29c21465de176a1c2d2a23f5cd840a140916ca45fd33f814751f05 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/drawingTextAppearance.test.ts` | text | 4680 | f4733db94ee70f593a895cc0dd92cb2fb2382a51a22bb0418ec1e9aac07e7cee | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/drawingTextTools.test.ts` | text | 1342 | 64b2a0940f85bc1b9507b392b76084d8a4685a050ef141ba10dd90504935cea8 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/drawingToolMetadata.ts` | text | 25651 | 9b3f92358e8c200b5e433115880a6453236effb0aad649bce6d00f6c9ea01474 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/drawingsMigration.test.ts` | text | 4413 | a78cbf1a4b375c691084ca863ce2d241a6f7c98b987ec930d0c7268afc16b12a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/expressionFeed.test.ts` | text | 6191 | 5a58a1004c579ddda5956a8ebda58e17da4a4a43934fa244bf055029f1f0c218 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/expressionFeed.ts` | text | 4563 | f5c8b33d97547148d62f0a197d07af6d3354fb89a544db27fbee16d28d949ca6 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/format.ts` | text | 2862 | b2664d28a275cc53cbd275c273767182e2f2afa33615980fef203d4774e10060 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/glyphs.tsx` | text | 3746 | 9b170019e2c92db8075f7e7723e32599456ab851b0c195c3a4ce3c609edc47c6 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/gridSizes.test.ts` | text | 3781 | 86e6f1f3877d2cda54df576063fa0bb0d07329722e3a8a91f8b8929f7e063e12 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/gridSizes.ts` | text | 6625 | d92073fc8cb7e0281eff7c138dfe26b8cb7801e837602581102a95e41d416aa7 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/indicatorTemplates.test.ts` | text | 5424 | f77a5513d2754f83570febe69040a0d8eb229b731d7358f5dd9c60d8b3dbecc3 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/indicatorTemplates.ts` | text | 2895 | 21abb9b2a297ca423202c3598a3f4b2dc9903b861701be110f975b6318eb3617 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/inputConditions.test.ts` | text | 1091 | 2ec4e1b4a647b6c8b3d46f9c0d7c09029a0ee93cd32d56d845698bb082d3deb0 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/inputConditions.ts` | text | 1308 | e5b57094062edf29fef8da5c7c3e70553adefdc8f0a23fbe5e196d73431e9eba | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/inputValidation.test.ts` | text | 1316 | 6b0b16d4bfe0f68af6e03b0cd75427fcacc23b94ea8f5c2fe11b60f65d41fb98 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/inputValidation.ts` | text | 1794 | 5d28eff9ad34179c9c5d7033d60b996a33f0b9d4e66a7709ddfe42afe4f42ee9 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/instrumentFacts.test.ts` | text | 11042 | e62a938afe5e76f882792d4acfe052ec8df51cd158fd0ee236f667d863712620 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/instrumentFacts.ts` | text | 13248 | 8f03e08f6969c3d89fdb5bbfcfb0d9fd819143129408df3012bc21f18814cc5f | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/intervals.ts` | text | 5339 | 3ccf1a10fe3449933317522ee0dcee96054091bec27781ede723ec29b5f83ed3 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/legend.test.ts` | text | 9469 | 4eb85b2374a4f20edb0117c19ed4c9bd41d55cf360dc8e327a43e115a67caaaa | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/legend.ts` | text | 9414 | ed7e0fd9f0ff10174420ad2105b8b7647d96fb37e01630968221d4d6fae29693 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/openInterest.test.ts` | text | 1197 | 6eb05981d2b16eccb2201c94f773ddea7a0eb3c874a9673b80bb9900de50eed0 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/openInterest.ts` | text | 955 | e6cd0b0c36059705519b5a24e79d5e52c0583d0221c86f3b15ecf060daa872f3 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/openPosition.test.ts` | text | 4176 | d5042b70a7669815336f517c2e1bc628b109b1aa93c7251874376eadae7f0886 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/openPosition.ts` | text | 5955 | 78e170a93286ccf4878a31f2958d90fc06e70e8327b94946a208dbb148df3bba | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/openscriptDrafts.test.ts` | text | 4243 | 9bbfdf5e15b305ec7ae0efd8101edbfd78c1386db0f490275e7798b366d96998 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/openscriptDrafts.ts` | text | 5882 | 0f84ef7610dcfb48d51acf94d3baf0d1b249bc5be76f7d57eab05342a9231e54 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/openscriptFiles.test.ts` | text | 8724 | 358b9a608291654e67f19376e97e2cbbe18b5a24620acd1cf3210b00c9d30846 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/openscriptFiles.ts` | text | 18753 | c0dc15ff5628181df8ba2e7f003b83a3c83cf50c4b468d21ab5ba3511a57857a | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/openscriptHighlight.test.ts` | text | 11843 | df6a8050059094a33e003bc64cc58fdf6babce4f59b67c31922afdefe7f6b778 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/openscriptHighlight.ts` | text | 7167 | bd04f7761d1d729a83ba7d0aaa9ff94b02b2246d1063d04be2db38f772dc25a5 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/openscriptIndent.test.ts` | text | 6774 | f36f933001def30fe81c8d0964f1d94d0af1398808bdf8815e090110dea1cbb3 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/openscriptIndent.ts` | text | 6152 | fbdc97ecadab96fb729752d4542d06e0943d43163a8bb671636a721badc52f72 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/openscriptIntervals.test.ts` | text | 9712 | 0110c73bdfe4c499dcce5f5256fef56f6243773015ee44810683a67adf57525e | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/openscriptIntervals.ts` | text | 6253 | d8d1236c5d2862a2711b793dcd9d0eb66de900d8f706b2204b557cd409d3c6e3 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/openscriptSession.test.ts` | text | 5459 | fa63073a88bcb99b5d18e8d210ff6755567c04e8fefef142ee9c3c0efab9af03 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/openscriptSession.ts` | text | 4069 | 9a352c7ddc9241af9d6eb9b54d6dc9092df1aa9fd52f5809569f807a260958bc | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/openscriptStudies.test.ts` | text | 19098 | db39ee05bd56b70fb60a487aa2c6d9ccf401593a169523a4e8cc3da48c121ee9 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/openscriptStudies.ts` | text | 29987 | 6b088e96447ee5c2c8530f730c4595361dfddae0143628102186899945465c17 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/openscriptStudiesChart.test.ts` | text | 12171 | b4d6e9d39bfe89727d557a51c70a62d55b599d2ca6c58007e18c62bb6638253c | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/preparedGrid.test.ts` | text | 5856 | 2cd4ceb89b467a43081d6b3ffc87ce30f8f719f3109ecac96a2dc7ceccd783b5 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/preparedGrid.ts` | text | 5609 | 836ccc06c1ccabd0839933f8dcb4501ef65257a7a8453c6d6428e2762be75e39 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/previousClose.test.ts` | text | 9339 | 1b597c943fc423a4747d320a6c61a752569aff52cb884ea9ade00afe58fe8c2a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/previousClose.ts` | text | 8550 | 51777d0d2738b1fb025a7402f97a3d00fd883ef8b983f437d363c33eede874c1 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/priceAxis.test.ts` | text | 14327 | 2c48c271d60573dff856a7cf9eaf370da1708486ce61227eb870aa86f00201f0 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/priceAxis.ts` | text | 17812 | 36ec47644fae7c034a8ff2887eebb91203640888224d34551cf85b249160929f | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/profileIntervals.test.ts` | text | 1314 | 4ca382aca26d33b51e2e249c28af3bc6dec0c21350ab4f5b7b58015dba6f3d1a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/profileIntervals.ts` | text | 898 | b46b2f71fb06890b8a0b65782d1c76640bc74c8c518d1759c0fd48ff2f7278ab | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/profileLayer.test.ts` | text | 4333 | e80a627a943a1afde6d26c6a420b12578fc2eb6f88d4c395b5b6b2584c71238f | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/profileLayer.ts` | text | 2942 | 92742109db4208e19b73db8bdabb14e59d7265e8d6e1035f07623d0cd0b6a0b5 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/profileSettings.test.ts` | text | 6169 | cd986c7639a9b19a0d82b262c1657c3a1f0fd0a2f3d5e89bf97708cd3e9c1646 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/profileSettings.ts` | text | 13281 | 19f0ce5900f7a66abc39269e68828cf7dfa45346066172fa6f420b020098100f | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/profileSettingsView.test.ts` | text | 2261 | 25b0cd0dbf62bb7d7e0d9ddc46c94743f5409cca1f78ac029a880486e1871557 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/profileSettingsView.ts` | text | 1648 | 1ed31f512671e8b217e21d2d320e96881ed99e1112358f284cfc2a92a373216a | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/quickEntry.test.ts` | text | 5656 | e0cdf25cd8a0c901370b781986fc2d2737ed25f1f8de64e944a2966d9c98f47d | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/quickEntry.ts` | text | 5017 | a3f70b35879ea7bc52e960acf5b4ac880a92b42fb7716b12a60eabfc96df2edf | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/rangeChoice.test.ts` | text | 994 | 6a3f10ca16a707dd13c57bee0506b4bfa185221d9bd1c8d71f7b4ac7a7480493 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/rangeChoice.ts` | text | 1365 | d32427d9f6ecbbd983a5d8f7b9296f3f6ad58b260c78833f1e386a44574b18df | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/replayClock.test.ts` | text | 995 | 637ede7c2c489e9a50e35998c0e37865230e3b9111d5574d3ba238eda76904cf | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/replayClock.ts` | text | 1827 | 8893f6ab4069b3fff15b3825cc56e4bef90cc08ff37965aaa29a84df750b7084 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/replayTiming.test.ts` | text | 3105 | 1f7e1841c47eb331ca50a3ae4b9d8c4fa370d608d22dbc265d43f57ce7df5b69 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/replayTiming.ts` | text | 2925 | 9e5ea85e23ece3048fc0e0c5eda3ea3c80378b297f8aec77ae89a6ab64602abb | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/replayTradingLock.test.ts` | text | 3925 | 8d1d8b05d194e91822666fb87bde4a7c3a82fd030df0acad99cc8d08e9c32a68 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/sessionHours.test.ts` | text | 9828 | 02c24292aceb854254783078af24502dedfefe96de6a9d0bf15786bc5acfd318 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/sessionHours.ts` | text | 12083 | 1c117267d650d04e76b360e6c4cc497acaf8c6445350f19c0383dad35e56c4f6 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/strategyPosition.test.ts` | text | 5331 | 56bc66f75daa99c431fba0d37373b73d08699c8b11f6984e541598873ef1b0ea | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/strategyPosition.ts` | text | 6017 | 5b05c55208e928fba857f286e1603163c5e507f4bd5e6a18ca255d1b2c50bb7d | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/strategyQuantity.test.ts` | text | 5104 | 196097a83e7087ca3f342ff3bd74aabe73a8ade094a5b78a1c1d961c2047235c | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/strategyQuantity.ts` | text | 5860 | c86c610fbb51f11e8c03544147c227d98a51d79d491e833725f26873c3a53251 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/terminal.test.ts` | text | 33206 | b1cec097d433e33727496c4074b647b045cbc3273853d57b0e3aba056daab0a1 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/terminal.ts` | text | 330012 | 1bd77f75c160ab63d945fea8bf101f2e5877dce30078f817dab8ac0069f83d00 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/terminalAlerts.test.ts` | text | 21408 | 3e6de68edcba0afcc017d9e8b14a6998094bab9f7fe832c4c709b0052dc61619 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/terminalBacktestMarks.test.ts` | text | 4792 | 3647b717c45793d394fff70abc98a26cf42140329c213788bb5eccb7eb031590 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/terminalBottomBar.test.ts` | text | 3626 | cc00f0b46c3910ff5e92dce8cbade99af3d7c7e567985ebcc88b0d7ce37fbbd3 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/terminalChartHistory.test.ts` | text | 9394 | 3e340e5f93e94b728fdce59cd5e0fce27f8e5738cd249462de8a3d18c73aecdb | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/terminalChartState.test.ts` | text | 5888 | 686d6b1cbfac2601540936892bd5c0e07806354005aaec8210d0f82841d87c1a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/terminalComparisonPreferences.test.ts` | text | 7269 | 7f23da4de4395db98a99eb0c49da4601b4d806edc5dc9e6a5892df4965512610 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/terminalComparisons.test.ts` | text | 23633 | eb7e4dd3d50d66d9a8a8bc57bc80ea1a54fcb3777c0ddec1f5003a58d3e4e276 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/terminalComparisons.ts` | text | 25983 | 0086839a929bb23dbcfda270f3b91fb4921efc00985c243942b15c04ed9b2888 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/terminalDeleteKey.test.ts` | text | 10993 | 66016993ce68895115ae535f146a21fd70cf4084e151a01bced01ead2fbae181 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/terminalDrawingTools.test.ts` | text | 13304 | 061db030b7cb9ae91572817865c1d7e5dec9298ce179b02a5442592c39e33c3b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/terminalDrawingsPerSymbol.test.ts` | text | 9643 | 3782e0267289cb717a69e2526779768061a56c1583fbb541c9f0956406fa7336 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/terminalHistory.test.ts` | text | 63620 | 9aa75bc662d9d2e3adf9711943693eb0c13fafffcb91e1b1deab1a2d56c864d5 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/terminalInputPick.test.ts` | text | 2918 | 124e33a29f88ba5b7f74da458b85c25aef67543134a8ac6ddb0c6d7b07506219 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/terminalIntervalSync.test.ts` | text | 4331 | 157b1f09ba0a067073a8559167b5605ee3f0950942eb047401c3761b905fe3fb | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/terminalPriceAxis.test.ts` | text | 9228 | 6fedb3fbbdf88492fcb43c30fc0b098e07afcce35df82bccf65a30047929a5b1 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/terminalReplayCleanup.test.ts` | text | 3738 | 3cc3014c8b20e5e4e3e7ed1bd9d808db41e884113d565d8b4a07168c00e208f0 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/terminalScriptStudies.test.ts` | text | 12028 | 58f87a253a74b1fedc1dc117856eb102d6f0fd89dd78161f701f508a2a5cb3c3 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/terminalSpentLines.test.ts` | text | 5280 | 28de7a4aa43ca448aedf4ed86fb844302f9cc238d99e80f509e70dcaff34028b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/terminalWorkspace.test.ts` | text | 11667 | 6fa72324abd06b817e2fa6188a18cc2c4d768b423472fade53df6c009bdb8bd8 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/terminalZoomAnchor.test.ts` | text | 3808 | 4996099b71ab3a4002358bc750343956dc9caa111f450d3cd9fa6edce255c12e | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/timeframeFeed.test.ts` | text | 6351 | bd2b2fa46812c4b32c247a8d7aae0e4077da1e78525675a28b3f1cff1675fcc1 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/timeframeFeed.ts` | text | 6208 | 4567ec0a9f65481a317a41f239db34eba679edd40af5ea4c78a06a97a8af3f30 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/timeframePreferences.ts` | text | 645 | 5a3b390613dc8c4727756462e2efef07aec2b15a42087abd80e6ffc287266cf3 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/tipPlacement.ts` | text | 2292 | 6ee90987bd9534adb79a9465f41fbd084fb5e678dadee8b6d178e1a9caf7d469 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/volumeSettings.ts` | text | 3903 | 85d803dace42d9c4cacea9cb3f60d393ad18080653585dde73adb404996af697 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/workspaceGrid.test.ts` | text | 4917 | 6ace0665274311951423468f27da87f08b00fcec4677a6eaa6e722a7840dc9a1 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/workspaceGrid.ts` | text | 3489 | 85ba25b64b2588cff0bfb779e2e7963f7fefe0b476870d62e1110b3524a43c39 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/workspaceReplay.test.ts` | text | 18764 | 6706f6d977634680d9bf5d0784569e8659fc16564ca197c4d154487bfc1bb158 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/workspaceReplay.ts` | text | 14599 | 4d881e5355b084fd4bc7c292b9a07de54b8bdd6d7ee8abaf9cfd83e567ad30e9 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/workspaceStartup.test.ts` | text | 11172 | 9cf6e364dcccdc6b3d8b66c2a19f303a935e02484017da57e2991f865333e6db | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/workspaceState.test.ts` | text | 4658 | 704cc7321aa545d4f738ec2b21c025ad7d4df0d6b17f9828146f8af7ba02b46f | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/workspaceState.ts` | text | 3030 | 2fc36b5e465b18d58dc137a1aa0f91ac789a1f424a131a703f717c4da4d26fae | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/workspaceTransition.test.ts` | text | 9451 | 42610d9aa578803a1b4d592475e68b4819aa48fba580808c271692c046d49443 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/trading/workspaceTransition.ts` | text | 4041 | ae07ab6422edaa32c50061e5d1f02a478a48b15d738d4cc7936acdfe744145f8 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/lib/utils.ts` | text | 1444 | 3d243df5fed43be22480108770ecdeb42f930bc6314ab743ccca4560ab6cffd4 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/main.tsx` | text | 444 | b5793066fe15f1d9680f32fb33e0fa5bbb4adbf969f21091eac15fbffadc4448 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/ActionCenter.test.tsx` | text | 9945 | 9f80268ec89b45a972f305065eafc3b5f057f4a0df692de6e88f28ce8b1db639 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/ActionCenter.tsx` | text | 35201 | b29ac4d6fc37d52f473f9b55faae4a66938910def50fc2195efb8d7ca5ac451f | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/Analyzer.tsx` | text | 15267 | 32bc782d1142deb277946a9f93a6114a4c0542033a0741d74065381eec588f5b | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/ApiKey.tsx` | text | 14518 | ed5de5e4abf1263c809fb1d59105b02eb4082917d95d70ff7432d57d279a94d1 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/Arbitrage.tsx` | text | 29170 | f746437055fdee8ae92b234c6062358351119b93b75da49448400b63bfa232cc | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/BrokerConfig.test.tsx` | text | 13516 | ce3039b0d7a05efd39af70f301221dc51e06221bb098dbaadace5ac4384fa7f6 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/BrokerConfig.tsx` | text | 18333 | bf56029d78b40c0a19b3e99d188e5ed7986a521b8c92fc32c80801a300decd21 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/BrokerSelect.test.tsx` | text | 15399 | 8015c67952782988092ec6536354eff26889fef534c97088f0df653ba5884d0a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/BrokerSelect.tsx` | text | 15313 | 4003960fa786cc8f2fe5f31a3321bfa907536dc4fc6bf74054051c2d2237df45 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/BrokerTOTP.tsx` | text | 18809 | e5fdc5f13a88f66d7c6dc43274ff16da970247a4a1cb99617f8827804c6b3507 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/ChartTest.test.tsx` | text | 8851 | 8141184f7c81fbca7c6df518c1faef6f6aa1ee978ba159090a781c3cd1c936b6 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/ChartTest.tsx` | text | 19583 | ebe33dec7f2c8d842d98456e16b2870a370568ae4716eb59b88e5e3e254a28c4 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/CustomStraddle.test.tsx` | text | 12424 | 374cb6165fc947bacdddd9ea2ec2cad6df2cc88cbb54ab0d1b45513cc3c8da90 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/CustomStraddle.tsx` | text | 36264 | 260c32d287ddb9f71b80ae2002f20ad5828f2c556f2b765ee4a845dea8dbb455 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/Dashboard.tsx` | text | 17233 | cd53b80589a75ade2523eb8514d7f488d5b100795c9da35a9093e8a5e369c0a0 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/Download.tsx` | text | 21490 | f9a03245d788863118f0c63eb20228bd549844ea5741172df0e8bea069bca609 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/Faq.tsx` | text | 19250 | 0038cfe15e2a307365ef7164a2fb22dd879d02975f583cc8a79cac733f83e139 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/GEXDashboard.test.tsx` | text | 953 | e02aec64a9e8b96a339f8736c6390aa60c8b9a60c58f7a809f2de2c2561898a3 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/GEXDashboard.tsx` | text | 29144 | 4e21af15eda106c44226795bdea3785d6b098b42c14f2261ef4b77aca8e0583b | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/GammaDensity.tsx` | text | 20443 | 979644135becf8f1aad5ed3f0db11c89faa099decaa4a5442c54d50c2491f0c1 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/GoCharting.tsx` | text | 16497 | 33c3867c67f5edd29b0949f0ac2fbfbeb6677fada062a2e9b1db244e8ff3b3a9 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/HealthMonitor.test.tsx` | text | 8893 | ccda2814ab341ab3ceb964ebc7e97ee20b1385bcb3dee1af3f853f2f37f4f1c6 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/HealthMonitor.tsx` | text | 33054 | cf6097cd469b7623dcc7a82632897f3ec2e3d1525dda101c7b4e604909fe7cc0 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/Historify.tsx` | text | 152574 | 96ecd1f22e731f03ef377ded853389d85bda25773d003ede3e1f696b79380ee4 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/HistorifyCharts.test.ts` | text | 2709 | 6afcfef48a39caa52be2166f5fc434da3a63ef825cd966bd7e690538c067c1c4 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/HistorifyCharts.tsx` | text | 11420 | 42de0635c7f68880b9216b531acc8227ac271cc6707aa6407e81c541b28a4dd8 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/Holdings.tsx` | text | 19020 | bdf80b391f80bde99813918cf9114d6ca52fa95fec4f2f1310fce104e8af6aad | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/Home.tsx` | text | 19540 | 7ca5081873a3caad314dc0592426445293e4fdd3ae4c76e302013ef2f2915a71 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/IVChart.test.tsx` | text | 8021 | 3c04321cdcb14fb3cf30e29ceb0d097471930dec86420aa9fd87273599c0a80d | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/IVChart.tsx` | text | 23748 | c2e4f991be44781529e507e572b3306e9665ecb306324640ed2808754e09599a | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/IVSmile.tsx` | text | 20051 | 344d021c670bd41a4336f1f563f0024d04289ca35cc620616a36dfa088ec98e1 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/Leverage.tsx` | text | 5133 | b52ea113bf81cb010e0fa6b4f835d8bdc76d32ff44fd4b1b1f6f5f990f09b1ac | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/Login.tsx` | text | 15382 | 3e7739c0676c41f6075078fa2b7f28832585100602e9c0ebc1c85b161752e729 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/Logs.tsx` | text | 17551 | c0412bc9228b1a1049b38b6e4b0408b27d0469eb274675994a5facfb1321b25d | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/LogsIndex.tsx` | text | 3636 | 08d9d40f969cecd42aefd3bacf09035fed41ed326ccf4baae85f4feff6c588a3 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/MasterContract.test.tsx` | text | 3452 | 03a977f10f28b5e90f5fbe297e3a65f5c280c7e834482941514887361a289ffb | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/MasterContract.tsx` | text | 19404 | 20354a9533481af1f81c52dc0380ba0ed455b06a1af4c8a49e5529f8da2427c0 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/MaxPain.tsx` | text | 16199 | 15b3f434abff6c881d1fce8cb284c9dd09e7ad3ffdadc5c9619b1652408d88b9 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/NotFound.tsx` | text | 3066 | 80b9e9f859efe31e6625c7d5e4d1ff41f32a54b469fb0260e52a47b1ebe4ffef | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/OIProfile.tsx` | text | 21431 | a7fed4e68684a4f0f3bf580c096daec577919ecc09dfe662bd3961f86abae8ba | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/OIRange.tsx` | text | 27550 | 284e5cf4def51b6d645284d1e428c33a5404d4e4fe4aa9f20cb3ec19b78b4f3a | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/OITracker.tsx` | text | 16887 | fddf119dc67777edf6bbb88bd3c64c750c984319501919b861533c6e33dccebc | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/OptionChain.tsx` | text | 39982 | 072b13094b33a0728c9b68a57477c858af4b3a9397a7ada7f4816e40dd4885c4 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/OrderBook.tsx` | text | 39279 | ac37defc6bcef623a86c474c1b42d9a8648f7f3e47bfae4182b29e57ccbdaa37 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/Platforms.tsx` | text | 3631 | 438bce18f23ad75b3e10602826f257f6857b9747c277ceea2ee6785535a6e7e7 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/Playground.tsx` | text | 45926 | 632e397c418bc031ae566cdd2eb1c65d713c8a3d3bce0daaf56260ce5db6f132 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/PnLTracker.test.tsx` | text | 11403 | 1273bd3b8589268b8da439c11fa8dabc933ecd2683c68685ac369a126d5878a2 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/PnLTracker.tsx` | text | 23120 | aa152d57c98551ff738f445280805fc67a8c90dc781621bab6e723f17ef71ab3 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/PortfolioAnalyzer.tsx` | text | 22492 | 8238e66cbc565d12e06eb48567be3d5b42a54a40bf346089af8d9d5b7b8b8068 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/PortfolioBacktester.accessibility.test.tsx` | text | 2364 | e810c2dccd9e6004295768644fe843d8fe9cefac58271d1d533a1a56dc351b1b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/PortfolioBacktester.tsx` | text | 15981 | a297f1b76de221c8b8cffacb29c48e8d30d37fcd8d0217b46fa1592bce89a866 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/PortfolioBacktesterResults.tsx` | text | 68719 | fef844056fb65870c817d3d7c33011201f8a3c08cbdfce6d13b95eba1c89e242 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/Positions.test.tsx` | text | 6215 | 5cf542d0d56f4b5c5e7dbb3684e2a84cd94de42e3e823d71c634f0ec84a2c763 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/Positions.tsx` | text | 40953 | a160e32ce1b0a23bb605b8f91cc7b844758c45d338950897bb3b6b44b0096fb9 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/Profile.test.tsx` | text | 5357 | 4717515fcb3d5e0305dcc198387b8dd3646d7a06e1d15ccb3cabd24c78c1120b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/Profile.tsx` | text | 86527 | 0c9095d70c779c3f4c426ecb0d66893b35b9b317e399fee324b17a3c064bfb49 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/RateLimited.tsx` | text | 4297 | 7bd134ca6edcb8a39f6cb7959890056a5519118478ce2e50ecbda589b7911a40 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/ResetPassword.tsx` | text | 19285 | 4f531530ac6f71f99e39ad24fbaec18a6b124648d639c4c6050d79c55632bbe1 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/SamcoAuth.tsx` | text | 8017 | 2aa5ad83afa6bbc6f9f405fb02df2210cfdb88978d001ca11ff4c31627d7eb99 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/Sandbox.tsx` | text | 16721 | 63c600faa03c7a77d7c7eb6c4d825844ce24cee84ce738c1e39bd1cfc925f529 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/SandboxCalculator.test.tsx` | text | 12925 | f982fed82cc27362179306092cc7b82375b430aaccbf796ca2609b63b0ec7dec | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/SandboxCalculator.tsx` | text | 15230 | 724075bdfa3053ae317aa85c9696c43ee900ce988aab4f09f7256793e19ec2c7 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/SandboxCommissions.test.tsx` | text | 16484 | 94d377e330ad08c9cf3d5c0391332b7f96339b8f96f520db765543d555231dcf | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/SandboxCommissions.tsx` | text | 34864 | 35fe81e9c03ec5182b552426f1e375c5e1e5f1b018b07f4b4b0c748159703031 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/SandboxPnL.tsx` | text | 26693 | 2425e6a909e9f52f6eca879fb9de7dcf2710adc65ece4318e747d15dbe92bbb8 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/Scalping.tsx` | text | 75836 | 600f2115766ff506fbb893b233ebe4831889b5c05dcd42adadc9e43090469cdf | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/Search.tsx` | text | 20745 | 7302127bc06f52012815a06b65fad1131931e0fcfe42f8f06a2e6ee6eb9b8d8c | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/SectorRotation.test.tsx` | text | 6660 | 301c2c39015d178f59dc97f1506df10f5afb9e5353c653c97d70f6d0d8476a94 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/SectorRotation.tsx` | text | 34919 | 5e77bf34ef1c80d47acf328d91e48d41d0813330e9819c5722762358c31209ac | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/ServerError.tsx` | text | 4674 | 6eb6c0d8ff0b9020348b8590675a5506ba10256e5ea8fd3e354bae4ce111e280 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/Setup.tsx` | text | 12002 | b6dce318f639e9be06f8cdb2e852968feccec40e1e1bf464b13a006a6784a76f | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/SipBacktester.tsx` | text | 14177 | 7cac24bd00789aee3d3662dbb69d1b6fb3d3385415d15c39a9adbed6d9bde43d | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/SipBacktesterResults.tsx` | text | 32078 | 1f4bccc83c0a575e19a01c2e0d6fc57ce352d580b0413bb203aff812f4d1083e | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/StraddleChart.test.tsx` | text | 9941 | 9b88d4d2eb0d6391ec12e8576c40186d380f8b2d8ef86fbe598de54b84236eb3 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/StraddleChart.tsx` | text | 28679 | c8e513444ac580b4fe041bddab0b474b2ea652d517fc05cae8c3849b8e5a558b | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/StrategyBuilder.accessibility.test.tsx` | text | 9014 | ee6e3f370c82e880096711998a95b15dbb2d7586910ec315fd4988f3c23d9d34 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/StrategyBuilder.test.tsx` | text | 65791 | 0178c4c5baa78415b82a65080cf68099eb782b3475ef4a302afabe61eecbdc9a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/StrategyBuilder.tsx` | text | 81828 | f7b74df6488b2c92a9a555b24a7d0f66ad56c109052a211e1ab65d0ccdfdd2dd | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/StrategyPortfolio.tsx` | text | 36359 | 5e21d0d0480b7807eb2ec561fba2ae28f92ff61686573a0a5664fc3d12710c78 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/StrikeProfile.tsx` | text | 33831 | 602cc25f2c5fd61abe7bf6c283a75fc75cc08c480d477402a07163f118e2238c | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/Token.tsx` | text | 31603 | 5753c42c7c5decbad9c1d73c6fefdd50379b41431a8126fde7890d42c7c91dca | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/Tools.tsx` | text | 1990 | b678af7f0a71365f48ebad48a68801add9a6877d2a4ed2aa93965531713b597e | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/TradeBook.tsx` | text | 21242 | 6b41d0f0eda30fd320d992457424e43054947f902c80c1ad1f0c04eaa38d0c5d | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/Trading.test.tsx` | text | 16533 | fc22a12a1f65c51419d10392c7eb80a58aa55aa9f5b0a48fefa2da5e112da72e | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/Trading.tsx` | text | 79162 | fda572a5d7f44b02283fd9ee8808b97f6746cbf8b5204060d92a917c871aaf62 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/TradingView.tsx` | text | 17249 | 09e7797769c63deeef5e9a64f01dc6f96b1ab6e031496af290cb7dd12f8c4d82 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/VolSurface.tsx` | text | 15811 | f01924617bd19ed12c9f7572fea7f689473364ed4d96ce61a1c5b97663a75543 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/WebSocketOrder.tsx` | text | 27131 | cc8f21e2501c7735e3adaee58346b3925fd5d86f09cc1bd1fc30214114db7a7e | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/WebSocketTest.test.tsx` | text | 2625 | 77ea32a36888feb4a82e667169be3d4b47cac409781200ae76b93a4c2ca6ba52 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/WebSocketTest.tsx` | text | 57587 | 10a46c69aae8f77ac81f9f03a8bf694b8509c841aa6092809c0c25d61d57731c | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/admin/AdminIndex.tsx` | text | 6440 | 059eaae825383e95c0e7d7e9a770aaade673b6ca5474fdd810621724b5eb36e7 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/admin/Diagnostics.test.tsx` | text | 4605 | b2089973464bbee49ff0d86200255190e260ed08f5b48c4c66ff0dc5121603d8 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/admin/Diagnostics.tsx` | text | 29324 | 5206d1c43d8d038c300649ea874a092fe0d1d49479e5c44227b52fdd04601676 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/admin/FreezeQty.tsx` | text | 19464 | b32a02b9f8011966ae4da836ad2c9ae47281349b894e2f8ec202c2a523bf1aec | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/admin/Holidays.tsx` | text | 23835 | 0b52ccf0b0d4cf8cf50461652f4db1946bb03c8ead732c03d22f7cb30363d8a9 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/admin/MarketTimings.tsx` | text | 15042 | 875611c3f93bc4d30bc3b8f08c1ec558fe4009a83d31e8aac51c26823661004d | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/admin/RemoteMcp.tsx` | text | 35371 | 0a73ad4378f4ed8f6b64ab05467e96bdc0510e57478e469bd7a8b79de06b2ba9 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/admin/index.ts` | text | 216 | 2be92bfe710f59bac06737358c80532bd3f41ccdc6acfbfc93ecb095a22c6914 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/admin/webServerSummary.test.ts` | text | 8158 | 9c292c41886fb9fd402aa117c2196ca7cfbd3c0e4f32fd2611cf1aa3760b020a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/admin/webServerSummary.ts` | text | 7466 | ac438202d8bc4c2aac94c63519a3780bcd1715767b99cc249c74f454e777c51e | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/agent/AgentChat.retry.test.tsx` | text | 3716 | 74c684183a6c9b68c153b591a795f8a77f06682cda9b8bf23baa5e84713f6313 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/agent/AgentChat.tsx` | text | 25393 | a3bed241b7597f8d51737d88b703412c11d484026e4084cc8fdd9c328e15dbeb | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/agent/AgentConfig.tsx` | text | 8019 | d08d6ea69766a3dc9cc544fddd0bb0cd76312b07f9def1d04573668b4633e976 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/agent/AgentIndex.test.tsx` | text | 2778 | 52c127e0ee95f34bdf233df593502b1f6a0375cfb8abe3f941379d73baa4bc4a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/agent/AgentIndex.tsx` | text | 3055 | 41ad49e895b3707c46c8b1a55d98997623de8b53ce67ff9ea7cd3c6a9d8ad6a4 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/alerts/AlertsIndex.test.tsx` | text | 7724 | 69e010145f029fddf2e92473c2835fd52751dd9c154b55eb5231e5e072d40fa2 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/alerts/AlertsIndex.tsx` | text | 10130 | 0b91242fee7c5e795fd1d35e9a90b8f855c0ddf4e0feaf28a6e094a887cd7676 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/alerts/WebhookChannelSetup.test.tsx` | text | 5377 | 0977ad9045f99078806f526d13b407a09ef44be4745cacc32b0d0bdb8179131c | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/alerts/WebhookChannelSetup.tsx` | text | 9702 | 48a1c70548b4f67d265df9999118e32688e8ed34cc2f5f69c83ddc27fc2dc2ec | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/chartink/ChartinkIndex.tsx` | text | 11704 | c671d0d44febc7796171ace28a6fd8e4e24cbbcefce67ca362675ef4e4c325ec | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/chartink/ConfigureChartinkSymbols.tsx` | text | 20377 | d40e00bbf6c9c8c767d4429ea14e56ff08d72d8ff838d7b9ef2638dc1888a274 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/chartink/NewChartinkStrategy.tsx` | text | 8973 | ea47c3326a17350e65010f430db50768d79ed0a5b0fd625c2c59889141b174e0 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/chartink/ViewChartinkStrategy.tsx` | text | 16196 | d0162e38f316026188bed23522687d8df38fbadc0bd4307e08336c0a4ceafb56 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/chartink/index.ts` | text | 288 | 5d50a25e2ea3834384c4e4afa79e1330a8c3f4e5f9d6c384c1a10be2187e8161 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/flow/FlowEditor.tsx` | text | 36000 | 0b019a9b3aeffef5ae441930efdca0c34797e85c9701473fe93d797dc7af730c | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/flow/FlowEditorViewport.test.tsx` | text | 3035 | 296b22b9b1d293f0dde3ee1a53f5bd4ebecf96b4fc4d50bfbcbc1fadad84ff36 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/flow/FlowIndex.tsx` | text | 29978 | d81353024319a21826bb24d6c55428098fad91f85164918bf3c5310505c63324 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/flow/FlowKeyboardShortcuts.tsx` | text | 4894 | 4c646fa89cb5a75fb5c8024ed7d299bd271afa5919dde5f31595a76cd887cd98 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/monitoring/LatencyDashboard.test.tsx` | text | 10989 | f0947234738255bb02998ed52560b56e08dc23baa925ba73358458ba22c603d6 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/monitoring/LatencyDashboard.tsx` | text | 30545 | a7945ab0b943453031a894d09d875b3197797019e961d04bf13c45072abe82ff | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/monitoring/SecurityDashboard.tsx` | text | 60751 | 8cd62b2dc3f3e8c560701ea911d2acdc4f81fc98eefbfdbf85348a35da6d6d81 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/monitoring/TrafficDashboard.tsx` | text | 12545 | 00cd3c3f6d032146bcdd70c1d4dcb8df8c1bdc15df0757e88b7d7c2153e152e4 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/monitoring/index.ts` | text | 200 | d7e94cdfc012bc7f232b87e4ea00a8fa531a698f90bc4cd131c250ef26238363 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/python-strategy/EditPythonStrategy.test.tsx` | text | 4708 | 132f6bc345aafb0f19e6e868d7674b9ae1132b1826958ed30b627a33d7b46e54 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/python-strategy/EditPythonStrategy.tsx` | text | 15789 | 5bb26ca07b7557be929860ab87471e85a741d13698822c45797abf85fc95e6c7 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/python-strategy/NewPythonStrategy.tsx` | text | 19323 | c85cc480e0438b6248933c64e25b9994d95637fd9b05008daea20500b7dc141c | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/python-strategy/PythonStrategyGuide.tsx` | text | 64490 | 3b9d50877a10a6cb8cc73d98bbec9607b9ab93ff6fae70bdd0e229dc9081598d | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/python-strategy/PythonStrategyIndex.tsx` | text | 24110 | f94c9565a81807284458c2cdfbf4e05b88981cbd8e2030d26caa199ce1a868ad | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/python-strategy/PythonStrategyLogs.tsx` | text | 14049 | 54b8637a6743c050a8711e76ca19a2dcae8e8bd6e97492dfdd8118c8b4e29df9 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/python-strategy/RunAllDaySwitch.tsx` | text | 1401 | 15ace144c786c62caa83024f394da9e19e391127cbfa4cafd4785f73983e3e62 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/python-strategy/Schedule24x7.test.tsx` | text | 10130 | 57ae5b08176138de6697c5cf4c28cf6011586f593b9e6e1d750c2d0f44e9d8e4 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/python-strategy/SchedulePythonStrategy.tsx` | text | 13915 | 44ecc15f57091faf9827e564c0d216286e78d9d1a287ac6255bb421895f6b48f | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/python-strategy/index.ts` | text | 280 | 71eab1654b4dc100740c0796accf2dfd7631417e225a595d974a68d9109d62f8 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/strategy/Detail.test.tsx` | text | 45355 | b163c38a3c06f108337dad72a8d5147e94d3a0d8587b8ed48a0fa26ffbeb781f | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/strategy/Detail.tsx` | text | 124639 | 2646d80bf79c3c676a4151363f9dc45af09df04437db6cd265991135b34f6782 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/strategy/Edit.tsx` | text | 2302 | 5a7c08385b8f127d916767677ab15bdc0da812d466339253f303ed9690f2e044 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/strategy/List.test.tsx` | text | 3211 | bad1562ebcbc03f104d820cb863edacc1d608cd22146c1694caa8416fe4db7a7 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/strategy/List.tsx` | text | 9897 | f3165e36552eb08257c27a2ea121337827cd5605638242a9136eeaee44442923 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/strategy/Wizard.tsx` | text | 82241 | 183a2e16ab5a3ad7743ca334d1cbb5a1cf94677116448b1aa7344ea7c199c859 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/strategy/index.ts` | text | 208 | 7a518d212f81ecc2016721298ee8ca5032a872b4f52c1b233b62b41c7bc1cfd5 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/strategy/routeParams.test.tsx` | text | 4186 | eab7958cd7ca1767b27623d4d096340fc570b7f79239611f738942aeab07cc86 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/strategy/strategy_module.test.ts` | text | 51842 | bacf10ae2fee31cc748f1ac89c6423932a71288bbb984363488fc0a79ac11880 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/strategy/useStrategyLive.test.tsx` | text | 18777 | cb476023c9dba3a5383494a4ccdaed4ca12d13635dcdfc1394245530ac69da7a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/telegram/TelegramAnalytics.tsx` | text | 12030 | 13340bad29d7325f4df17b703d46e889f19a520e0f8313dc8f559ef3d1af9f79 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/telegram/TelegramConfig.tsx` | text | 12011 | ef461ed19f4e7bc0310bb054628c823387c16e5abcc000b519006f61af719476 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/telegram/TelegramIndex.tsx` | text | 18737 | ecd35509d41e9d610768e7f94e76ad8b8e1088808a4da07d743beac1aa93975b | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/telegram/TelegramUsers.tsx` | text | 14415 | b13f9c688f0b11b932dce5ee9ae4b2f0ca8e9efd70e68a5eb5e7233770910f5f | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/telegram/index.ts` | text | 250 | 9d4db77dfa8b5b4bb3101f39277040e133ca7619591df08d84c6bf5be7de6734 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/toolsRefusalMessages.test.tsx` | text | 6430 | 074b4f91d165f772d95aa793a3da273eed143f1c8ac096900c18a5c7d903baa1 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/pages/whatsapp/WhatsAppIndex.tsx` | text | 12345 | 353b8ce167491ca424b506702d615ba9577008c9e16b9fda9778ed917e75a6d7 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/stores/alertStore.ts` | text | 4525 | d7fa771c8ff242c2106fade955d12a6823bf0ab4750a7d34267bd53e5cedad8d | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/stores/authStore.ts` | text | 2634 | 68a8f0e0daa8b269008c386181ad76e2fd727d4c29b7d22ea493ae8bedba82c9 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/stores/brokerStore.test.ts` | text | 1506 | 78307332b67cc80769f37bf0bb0fa210676d47ab24979c3e34ef871315a85eff | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/stores/brokerStore.ts` | text | 1366 | 3a17e628f24c35f7f7a9e5eed3fcc6824496e64482098810b84bd1efa05f85c6 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/stores/flowWorkflowStore.saveRace.test.ts` | text | 3553 | d2ed7fd23dd4338f9399bfc34cc870afe6351a7670b33aa3ddeb4de0362b2d98 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/stores/flowWorkflowStore.ts` | text | 6969 | 11c4cbe8140e0bd0b330c47ac5e8230b304865fed167576214012869864cfdc7 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/stores/portfolioBacktestStore.ts` | text | 802 | 156225fca7660d7cbeb0c3e861298f535080616ee0a7fa9d5536273312f6d0dd | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/stores/sectorRotationStore.ts` | text | 2394 | 5c622fbee41923cc31abed5ae20dc51d012e721c92eea1570b862ecfe3e7a04d | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/stores/sessionStore.ts` | text | 316 | 9a650db8f9a34d0ae8186b02351f042a128e606c65a63e645cb68cad55761b31 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/stores/sipBacktestStore.ts` | text | 789 | cd66f47b7aecdc8e71c3070801989510c212547c8b1de6d5f126260419754cd7 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/stores/themeStore.ts` | text | 6434 | d88cef405af092052f4466874fb2024ec6a4a20655dd2132cafa034685d8778b | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/test/a11y-utils.ts` | text | 925 | bed86026984e39f4fa0d8f140e1e2aaac49b018bd5704e54e6a78f2909b89767 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/test/axiosAnswer.ts` | text | 2377 | 2547814cbbaf23b7a7ebdc4c327aef21346631f76c002ad763dc56e657881485 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/test/brokerList.ts` | text | 2054 | 3d5fe5fe0157c8c86513911dcb554a7bd9d891a5a832d6f4ae29c4576f18e850 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/test/fakeChart.tsx` | text | 9915 | 850c139223df97d46d775ff8ced8e3d5620715cd8f00fffa97b9a1be275b47a9 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/test/marketDataHarness.ts` | text | 6403 | 61186845b9a186719e4eade6f8ae9832f404f4f71f1632301bdf1f5fc8313025 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/test/queryRender.tsx` | text | 659 | f29f8e8c3823232925f41ac5d9404279f54909af022d6a42c023fa21bf43e78d | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/test/runtimeReports.ts` | text | 4715 | 38348fd4d82310d6de87c9f4da1ce9993100d7e76783ecb897117b8f1eff8285 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/test/sandboxChargesFixture.ts` | text | 6892 | 70cbd63f4555faa963ba0b63a6d7587b6a29268db1f936113cb26ffc99751773 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/test/setup.ts` | text | 2810 | d4181b6270aa17d29d1b052b2e37492e17bc6121a4d1a5c76b63044e9ff5eac3 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/test/test-utils.tsx` | text | 782 | c9a60437badcf5e630d36ded963af7394af76cb48ed99e79781ba428de604f23 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/types/admin.ts` | text | 10314 | 47ca61041b742d697d9f4973027fed8e3b8dd854fbfa5ca236955ba3becebe64 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/types/auth.ts` | text | 679 | 1c407ec721ab1439088d40d42cd083684a1cb5ebe80938cf2278acee920f9ebc | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/types/chartink.ts` | text | 1468 | 53322117741b27ffba010858bf050029597c0217cc2d470c91708662b7c1aa05 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/types/flow.ts` | text | 24754 | 99d585b87418f473cea4bb807161a968e78d0dcd57378e4bdc0deadb74f338c2 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/types/option-chain.ts` | text | 12113 | 79df4c9c66d6109de435349200996dc54f5b080a53bbae9859fc35c731168aa2 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/types/plotly.d.ts` | text | 1287 | e8ee1e42946c02ddcf791e8ca785eef378f5e163f4e4c5fdb33ae33679eff5fc | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/types/python-strategy.ts` | text | 4408 | 826e6ea55c4a547fb65901c16bfc5f07722bcdbe5a4a1c86edf912f41ac158bd | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/types/scalping.ts` | text | 3680 | e625479283f527574dc60da263cfe6b0d6af6a839bf0b13be7843435b63c0626 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/types/strategy_module.ts` | text | 44900 | 409e89565ce298056fcd41a03b49551c815ce8f3c982023a5e44f56d85cffdb5 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/types/telegram.ts` | text | 1236 | 2a68b931169f8433434a31576a587ec170bfa8554f7255cf3d527a12e91b1d3a | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/types/trading.ts` | text | 3140 | 040e8c0596c1e4133ab9a0b00516002856b875763ed20252a2072f9cdbf259b2 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/types/websocket.ts` | text | 430 | 0afb52a572e2d7498d0726678484a7d0fd6248ead795264724136e4db52d567f | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/types/whatsapp.ts` | text | 2588 | 044eb193a1946a878ecb264ae6d16e91577761a686e0eab1d8f41758773a672a | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/utils/chunkReload.ts` | text | 3455 | eb7e6fc770f81b327013e1adee638bc83422b3c66de87623c6bc13532df24f92 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/utils/errorReporter.test.ts` | text | 4845 | 08118b6e71adcf42cb234863e65efa8b1c296d6922bbb1424aebab7649c7e672 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/utils/errorReporter.ts` | text | 7046 | d7ee2f3772fd80ff8b244c66bdc1059153a3926f519ed85aeee4fafb3347bd3b | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/src/utils/toast.ts` | text | 2819 | 0987ad4f11c9e591b1cb7477a388930d803a45adf59d0c968eef0ba229bd6f12 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/tsconfig.app.json` | text | 992 | e99051a5cd6113371155bef9631875693c5ce15d8d5c60dd8a8fba34beae6916 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/tsconfig.json` | text | 245 | d8a63d63426b7566eb0dd8aa36838a96b5fe3c5d59645da0a75c3fb9daed3bf4 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/tsconfig.node.json` | text | 679 | a6d49d645590cac21c235a0548605d867321b2e1750e99176d2153d702dfa842 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/tsconfig.test.json` | text | 438 | 653052300f747b39d1545664719550430b8c7fc8dc073e849d8f7b701be6f020 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/vendor/README.md` | text | 855 | eda8ce801c352ffa9face2a95940596c5880dedb424846c1add88a1c92aebcb3 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/vendor/openalgo-charts-2.4.0-0939bcc.tgz` | binary | 1206096 | 5f633b1acffd017c464f9d4873efd53332582bcae840207a07b459a295065456 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | binary: type, size and hash recorded automatically; content not examined |
| `frontend/vendor/openalgo-charts-2.4.0-2a7ca17.tgz` | binary | 1205385 | 36db694d57303b7ed75412810f038f562b5050a3de5f17f113d317b9ffec5244 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | binary: type, size and hash recorded automatically; content not examined |
| `frontend/vendor/openalgo-charts-2.4.0-87f1589.tgz` | binary | 1144841 | 3974af8a8cea5b39f876f8734aece9b7b581bad6efd4ec846bacb52c907abe6d | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | binary: type, size and hash recorded automatically; content not examined |
| `frontend/vendor/openalgo-charts-2.4.0-b26d6d5.tgz` | binary | 1151170 | b33418ae424f34f67b87e533aecb6c0bce7845497d7737bc7e76f804394602aa | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | binary: type, size and hash recorded automatically; content not examined |
| `frontend/vite.config.ts` | text | 2874 | 11a1630a2e8c90dd987ac186b43cbb1f9d20be1fe54485de61b0bf84d7062792 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `frontend/vitest.config.ts` | text | 855 | 22387dec1430e166f9182a55595642675591ab5c205cbe2ffe9df5a82441f002 | frontend source/asset | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `install/Docker-Multi-SSL-README.md` | text | 11712 | 8c6806141b1de7517b336dcc9bff1afb812937e5d28945343c302fa90619b07d | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `install/Docker-install-readme.md` | text | 18220 | 6ec38c7aab3db72d4b76f169f7cca1a3cdf7a85de4bfbd0bd60d768e95d07493 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `install/README.md` | text | 15964 | 9b217b3ea03d539108c595f0c546bc9a7d8f5a632a5f9aea39686ed046ee8702 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `install/Remote-MCP-readme.md` | text | 13111 | 6536c5565412c6c6ff4bd0975e1c785880a69ec4f1238b7552a6ee9ea03547d8 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `install/change-domain.sh` | text | 29114 | e5b05294a70f681c4c025003f6e5185a29a8868d09228216ee6a0ccbbfcd14a5 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `install/docker-run.bat` | text | 16777 | 75eda291db35ee4b4a8fb37b34f54bbdbe2a3dfd99666cfc4a615fc9e9874e3d | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `install/docker-run.sh` | text | 17788 | fab64b886845e31cfa7045851e8801e04a24f32c042442323c0915a2a95bdee1 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `install/enable-remote-mcp-docker.sh` | text | 12355 | d4ca7c205ee2bb9a8eba814e70b1896f48c8a972e5f679c75c37e4e858ac95ef | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `install/install-docker-multi-custom-ssl.sh` | text | 70220 | 320ee0b680da270915330a28772c6dfe4294d70c714dcce8e0b1ef7882e4e156 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `install/install-docker.sh` | text | 40557 | ef9d2f20563f695090c00975bc216b1607b24ba2001aff45cfa43dec0fc4ecf8 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `install/install-multi.sh` | text | 34491 | e6018fcf954f9a5cfff99225845782aac2e55acafef2b15555bc19142623fa0d | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `install/install.sh` | text | 60373 | b1d3efab423967da167089c08a68e122b70e3ecaa812249fa6b820170f54f90d | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `install/lib/gunicorn_hooks.py` | text | 7706 | 127343be8187981b15f932a146bfdaa4bc1d890fb77a0d3c082d27f7cdf5ff6a | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `install/lib/resolve_runtime.py` | text | 14027 | a82f0f470de54498696107bd6abbd8b3424b42a60328370aa8f447af16510a99 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `install/openalgo-gunicorn.sh` | text | 9183 | a1ec7a9cb14ed8bfa8188f06a7dbfc4d6f4c6b4ae367142d282320a70195c9b8 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `install/switch-worker.sh` | text | 29034 | ef34b9b8d87552e5058677df3a644bf625018edb3bc2737feb8b39f797a73900 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `install/update.bat` | text | 11193 | 02b1f1b2975473727e371f0a4968399b4eeb59f55e0504a3e789bb5eda6f7357 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `install/update.sh` | text | 43333 | 2d437899a75305e3a697ea8987541d80aba81df77669cde002a3e7ebbc267ea8 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `keys/.gitignore` | text | 187 | b7fe317f4c919b681e5e5bbda2e20c8a1dd9e715cfc06944f134a50e1359d9e1 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `limiter.py` | text | 254 | b6dcf86ac1a0948ca121093998480fbb8a2b9b3d0306e191934da030313fe4e1 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `log/readme.md` | text | 20 | 1fe42b819d9cdae384d5b0780d4f790b3e1ea2da7b64d9969f79097335cf0bdb | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `log/strategies/.gitignore` | text | 170 | d9982d5385b4b145995a79bc04fc1f724e9b6d3e0fad5835c360f15f43f6b235 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `mcp/README.md` | text | 13421 | 51058111a1522c4d06b42b11fc76ffb373faeaa4dfe1ce63f2524bb13f3b6001 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `mcp/mcpserver.py` | text | 105540 | 377c393a62578154771099950da76f0d5d33dff0503d6a22c6b2fe05c9b7d7ef | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/account-services/funds.md` | text | 781 | 5fe62e1672217beefc7209792a52aa9c75010bc4e7922a61e2f196b12243d73d | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/account-services/holdings.md` | text | 757 | cefb477a05e11c600c360474d2863ed336ddde6870a316268544999d12db0abb | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/account-services/index.md` | text | 403 | 71b618e40facccfd801202d0fe32681c7c2b79775f90b7a17ff84eb7c8f5a3f7 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/account-services/margin.md` | text | 794 | 41ef8f9ed038cb22e6b30ffcd4053749f320852e3e816496bf8d527aecba4195 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/account-services/orderbook.md` | text | 760 | e592e7e63bec25945760fde218250055d5cbb1f5debe80a89f02074a2074b375 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/account-services/positionbook.md` | text | 777 | 8aac80f14bd4e875f8370e4c3f3dba89997a634c7663e9342d07840d4f68902d | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/account-services/tradebook.md` | text | 778 | 9ed6624bfe537838edfe707d2cc623fc33cecfb366020372d4900eed87288b61 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/analyzer-services/analyzerstatus.md` | text | 798 | c0e444b4b82e214aa4806b01a76e39edfcb249d147c975f7d53af34df67d8f6b | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/analyzer-services/analyzertoggle.md` | text | 810 | ed11ddffc1a9de60f351ed9919a6b572a8bc56db2304792c34dd809853aa4520 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/analyzer-services/index.md` | text | 181 | e945660071f76c65b6d079015a4f53475a616d9b5cefc933723a20a6f3031f25 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/index.md` | text | 1396 | 21ab11836b1ed2011c5d66112d876c6c1eb5cd5bd0eaa471472f543ba3a0cbe6 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/market-calendar/checkholiday.md` | text | 812 | edb0bcf7401fce3ecf69a66f513ffa15a428a41905b06e8a88cc0e82c8b183a4 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/market-calendar/holidays.md` | text | 785 | 61ce5d017a27432a2b73093d38fb94e54a1bba28712823cf2f7e1f74cf6dcec0 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/market-calendar/index.md` | text | 234 | e2949b696ed092c4e554c669fb19c29a0fd9076582cb53d75186b625e906bf20 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/market-calendar/timings.md` | text | 760 | 66900f945a5df118c002de52931ac941dc8ce2aedcaa8d299d2aa31299d6fa6d | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/market-data/depth.md` | text | 775 | 0497c2f0b09f8c003d9d67f426623f1f7af308a9ec3723c90b5c8b10f314f619 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/market-data/history.md` | text | 747 | 247a96f2b7495b2be4107b581b85d5adc14b9c8666a90265d521d0110197de7b | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/market-data/index.md` | text | 348 | 6808d06ae59c8ed7abeab3343b47ce0379857681534c65f87973ba73392cb0a2 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/market-data/intervals.md` | text | 788 | 4bfa8ed163e4873f8ed4350e5b6aff3db90c6349e98caca534034040a7d6a9ce | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/market-data/multiquotes.md` | text | 787 | 7e90056ab265dd9f457357d7aa9b2da985f42ac3b43a4aa9f5c7a806615f4937 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/market-data/quotes.md` | text | 752 | 5bce9e5c3e37f487f780e6106e4df29c117a2f6278fe340177580946b9e3ef72 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/options-services/index.md` | text | 364 | d342862ec9558c3cdb6e2bf4c4eb06fd1893e4211a1f3eba45a49c6b2d599116 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/options-services/optionchain.md` | text | 822 | 0dd6bd40d5bbc69cad854efdf3fac41a1b5ffa60d50e733cbfae4d7ce33f2757 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/options-services/optiongreeks.md` | text | 833 | b724e080119ce04b9e1cb356b79f8e2232b277f04878efd8e0ab7c270f6e8f15 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/options-services/optionsymbol.md` | text | 823 | a609f1f27fbef166e61a6b65ddb89f831b30d160211f2071e4348e263788206f | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/options-services/syntheticfuture.md` | text | 861 | 8a3486f7056fe074e643d5d1e0d2f11e8b04f5ae894190ae551132ba19968be5 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/order-information/index.md` | text | 174 | f4ea8731d133f3b7b97abec0968f379606b937b8acd7ddec1d1c2303257f22f4 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/order-information/openposition.md` | text | 821 | 5e59dc6aa19db2550c5822de020a78de24bc751d9f6462e3930a7b7128b5dabe | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/order-information/orderstatus.md` | text | 794 | f4689853c41e76fe0e318a8fb5872fc588bdb1d225ec7c08a66246d478e2d989 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/order-management/basketorder.md` | text | 821 | 4151f5bdf19a987ec223feba19396c211bcbcafcf747d0587d718143724a8907 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/order-management/cancelallorder.md` | text | 776 | 191b0d3ec61d0ceab8de3d2d291f4ce490fa0f90adbec30808ad7d82fa1d049f | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/order-management/cancelgttorder.md` | text | 787 | 4873d5133bfe09aa91fea2ec756b5488441c7e9d2ff3accd9e058bbd0b130468 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/order-management/cancelorder.md` | text | 792 | c0f6a52508a1c79a2435d4edf6e0f4d133c552fed5695d90cdbf86842934785d | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/order-management/closeposition.md` | text | 784 | a353243675f155d347799c8ec1fe71315440dd0e41a09b6b6cc68b8271113cec | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/order-management/gttorderbook.md` | text | 774 | 97ee537588b2e6f3bbeb10d666d7c1437219f07eaf9402788090d08c56049099 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/order-management/index.md` | text | 1117 | d1315adf455da03325e215fbb6a1aac0e790f3555115abcfad374aadda42993a | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/order-management/modifygttorder.md` | text | 783 | 1caffba55be90484fa979b1b07ba74ea2d0e2a2805fe0aa0999a9542842191af | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/order-management/modifyorder.md` | text | 770 | 09cabe6cac4f53a6d79301f4537feb3df02048d9df87645935129edc5431b71c | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/order-management/optionsmultiorder.md` | text | 847 | 1cd3fb1a0f0ea521ac2c1b1117f9fae21e1c98919b3f0c6a7445c35b7b13e2ac | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/order-management/optionsorder.md` | text | 837 | cd778743bb892a43e129807b4cf0490486ac5033f07f494773c5bfe74c180989 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/order-management/placegttorder.md` | text | 830 | 389129571cf63090195b6e750a44e682d341fb368dccc7d43ed9ede7e93e54ba | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/order-management/placeorder.md` | text | 779 | 1055180e0e8e25af72a5cbe2b866916c5e05008fc5ec2105d64644d8bfb565de | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/order-management/placesmartorder.md` | text | 897 | ca4d897354beb73c293b50630c86ebd0fe0a586a5e69b27a3f5fbc9a7a4f25a9 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/order-management/splitorder.md` | text | 798 | b177d18fcc3c3b0468aba1c486095122565a6cd906d4aad679dacd7135dc5c11 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/rate-limiting.md` | text | 727 | 7f1f7d6ac4a8b0c036cb80e405a8fc8992ab3d8085393322f591995c4ef188bf | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/symbol-services/expiry.md` | text | 773 | caa9bdbd4afe5ed45b6279ee58b658e12765bca37b80950aaddc51dd5b63f68b | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/symbol-services/index.md` | text | 288 | e6b23f5e0b14937c360fdbc083be939a8a3c2d83c6f6874bc9e16342e4317989 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/symbol-services/instruments.md` | text | 831 | 1273c833c8997648a0b4de3187e6bfd64b9c73f4e06fe6016fab5ece2e38d43f | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/symbol-services/search.md` | text | 780 | f8daae594287593cfe1696b196ec0fc81755a36a85576d44d15107d802d8eccd | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/symbol-services/symbol.md` | text | 788 | 32e2c5e94caab136ad9da38715449489f88106c3a7c4c9ce459bb93ca32ab0db | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/websocket-streaming/depth.md` | text | 809 | b6b0469d3adbb1c7e4e587d74a31f51c0d67c2be00ea0774e5e95160c71136a8 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/websocket-streaming/index.md` | text | 261 | 5bdc5557f20e9f56d7e08f01ec542c3e42d31cac7103884c771230b74ff9d3ae | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/websocket-streaming/ltp.md` | text | 821 | dfd849bdbe0495812d71545b773f1a202bef8977b187e36953e9765b47d9c781 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/websocket-streaming/quote.md` | text | 811 | 33e04503d5a027f543b1f7bb4eede4f3cb90d653e5bd311c1301237117813c3c | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/whatsapp-services/index.md` | text | 240 | 45cb3040f7f698d9a72c6bd73ff40e9a7895dc8c5b16804e036e7a3694b3c0e7 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/whatsapp-services/notify.md` | text | 851 | 77f53c424a3ae567d527c81e2107f61a5719cdbf2018040e46364a97edb2e81a | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/api/whatsapp-services/overview.md` | text | 874 | c3b9d286d8e71a59bab6a64130848ae178f376a9a35ab7b9ba56c26055fc0240 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/index.md` | text | 1520 | d27bf7219fec4a18fb993d0c51d4b71d03d11a76cbc7dd7a99178135f112ead3 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/indicators/hybrid.md` | text | 921 | d6bb993052cae85cc47e98f207ad2c287d501f012f0e8703c58b1abc796ca4de | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/indicators/index.md` | text | 1459 | 456f6356430f0cb7fc6398de9c547cfed59dbd853b037a1f59ebaab16e1a5b81 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/indicators/introduction.md` | text | 871 | 9a4bfc441f6f0b1277aba9598cdc8a376ef0ca6e05b68ac59d4a7a17f4001a52 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/indicators/momentum.md` | text | 958 | 5d670f345a79983956de49948b898ed721430e4131dcc6c18d2c194cbaac1e9b | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/indicators/statistical.md` | text | 1074 | 6c8775a6eca4200c3d05300ae56018ea1d2616680cf0d8cdf5a8d50cb284f46d | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/indicators/trend.md` | text | 918 | 560e1b7a8e98a69961c1f31887eba282f79b8a919c03d30e5163d51eadf326ac | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/indicators/utility.md` | text | 1018 | 4f6ebb95e931abb942b1d1912c17058297e2efb857b8a69376654251d5a54d6d | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/indicators/volatility.md` | text | 1046 | 38289fcc2d58438ba67338cbfcca50cdbfd67ab60170899e27b0e807275148dd | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/indicators/volume.md` | text | 969 | 416debe19f40d1905ca4b284c21111595a3f0d5bc81bbca95cc917af593de432 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/installation/forgot-password.md` | text | 897 | ceb0fc9dd667ecbf7d046e0a8cd537ef9371fc3e547ef1815661559b5da53c03 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/installation/index.md` | text | 572 | bbe934a0f8e4a7edc8974e03f98d976d97a332c2c3eeddadc9fc925df69191ed | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/installation/smtp-settings.md` | text | 921 | 7913a3139d4cd1872406e75e58bb4945353f36e1297afb038eda5baa0faa94aa | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/installation/totp-configuration.md` | text | 881 | cc03501474b62ce4502627cc4d410be5de251ae510910a414a5755a47c6f3413 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/installation/upgrade.md` | text | 895 | f74070bbd860b713c098f487c18d51677aee43e6874958472c9fd6d5d0f7e211 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/log.md` | text | 1626 | e6991f414e1f4156078ac7c2b4252185aadbc62ddb5cc9ed08c07eea2a128db8 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/overview.md` | text | 1007 | db69d9612c5745f568fe5afe6cc93ca02c3867ac622f60528f8e05fa43e560aa | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/responsibilities.md` | text | 828 | d99f5f229fbae271ccc0713fc689136036ca0ff646aba8c2cffb891f4b0b8b43 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/sdk/flow-import-format.md` | text | 745 | b9623a14e1059e4acbc1dceeea79849ccb3b2d4107515e68a800488f2745b43d | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/sdk/index.md` | text | 954 | 26926950d70419f2b0011ec48c3b9dcdca47922ce5376eec0021ebd67557cb30 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/sdk/lot-size.md` | text | 646 | cafe503b0e7680150ce8ceb543cb1c5495f6fe441675b92896c3d9f5d9bbb049 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/sdk/order-constants.md` | text | 754 | c048e5808a86eda22294e4b240348cbd24d5f0bcc7db9f3b6f269320b4f287c9 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/sdk/python-sdk.md` | text | 833 | c472670deefd40e11870bebc09ed0c5603c0de55b70ee1aaedff2164fc2f981d | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/sdk/services-documentation.md` | text | 731 | 388c43ac08ffac8e8180f29c8d47d6a49a20f616c1bdad661240aa730de591d4 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/sdk/symbol-format.md` | text | 756 | 15b2b39e08bbb4f820e423461f6b63071bee00d091267b15472af985c85cc944 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/sdk/websockets-format.md` | text | 734 | 5b5b71aa40cc91d2151d1fbe5d3e867af941f247edf54f92602b95545a6f4a25 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/sdk/websockets-verbose-control.md` | text | 746 | e2ed5b655fb48d03773a729e637aafc912e90b8f25d9e096044fdc8e4ac90bfb | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/skills/backtesting.md` | text | 872 | 5a56a4ee8a6a0d011f37d59aff6f36b23e15cd753a7d42a2b00fa2061ec86e02 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/skills/execution.md` | text | 827 | c070b8c5e916f8709b5a93b45c8b5926414d0cbff2f889401c0b87a9c592d04d | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/skills/index.md` | text | 593 | dc7b30d23fb035b27ef831cc186790dcfe446f0b9ae1a906550ab02bf8971450 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/skills/indicators.md` | text | 818 | f290fe9a031b1f78a8b6dd8095cd201398d499e7970f5635314dd4c65e81d8ed | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/tools/index.md` | text | 493 | 440ab0660354b2079206788c992b2adcaa858c97bc93a11999bf52b86fed196d | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/tools/options-suite.md` | text | 759 | c3ede1fd686d48b3536c9fccceb66e9f877eed405d16379bea1bbf602f3695dd | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/tools/scalping.md` | text | 829 | d8816ba5d28ca2e4f7621c7c208dd9cb230885e6f312bb2da5c5f87c38099672 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `okf/viz.html` | text | 104207 | 764df2a0508528dc4f4690f68128408388b4b9b512e2ab8ed0f7b4bfb2725892 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `openscript_host/calendar_reader.py` | text | 11721 | 83c6cdf1ac8e4e542ab7ded0ac8dd1c46fcb8624a392b8400511e9815e8f90a2 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `openscript_host/live_bars.py` | text | 15214 | c8e67a27e33bca567185870d24f3ebb42102145e828fb4050737e6c90a734021 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `openscript_host/openscript_runner.py` | text | 146366 | f36036ee3a5361a6c0d73ab432b5f722d141297859430213fbd0648376769030 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `portfolio/__init__.py` | text | 1905 | 0297a285dc01ac185b68aad3cef79b1cafac1899205a79ed72ccbe5f49aab1d5 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `portfolio/analytics.py` | text | 6854 | 08ebda0eae8a6409782ceb9324478da9ec31bcc97d8cf0c9fa9706c795f002c3 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `portfolio/attribution.py` | text | 5898 | 91e15fe6601e0d21d6e7b82a9b19903217bd77bda482a704cb73ef2d6d72050a | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `portfolio/compare.py` | text | 5383 | f36232028a35ad68da3ec2415d6118425a6c94f37c6ddf68fdf66276877fd1e8 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `portfolio/costs.py` | text | 10384 | cf8df26fd06167c73897776eab2d3a01c062e877fbda8a9438d39f5cd5714ca5 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `portfolio/crisis.py` | text | 12134 | e3e594a4106b2954ed80af0c4616d5bbcd43093166c5a5b61396b82087be7cba | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `portfolio/data.py` | text | 16759 | 600bc4de83827a1f4e3445f5a47cc0a48f11d89991cebd67b4d03a5dac73e16e | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `portfolio/engine.py` | text | 11309 | 209e017d900665779a863fbcf6e17229b02f07d26b71b04552675fe116406cc6 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `portfolio/grouping.py` | text | 5760 | bbf23589a129e0bf45a8a5f18e105ab877fcde788f0a3c02909f5b9eed51ee73 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `portfolio/health.py` | text | 11194 | 83483d4cfe78bcabc39eee883d529e64340194041bf1efbba972bfcc316185cb | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `portfolio/holdings.py` | text | 6220 | 3c9e480d125ee9468645921f5774daa19a8bd39856a8a379b1080e682d0ab6b7 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `portfolio/insights.py` | text | 15450 | acd3051ef258ebbee09639877e07e255315f4b22ec6edc034c55a2c3a61e9702 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `portfolio/rebalance.py` | text | 3024 | b4574da29f36c00bc0e464d31f28cd59ec7b8894c23f2a26f85b4267d1cfc840 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `portfolio/walkforward.py` | text | 6851 | 6f7f907f551dc7e3d6ec662876a7fad97d4e1160e313d8d4c4f2e89c38acd3a6 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `progress.md` | text | 199472 | f6ef451604a741803c0c56fd222fb746e2915ccbb6fa5fbf515e8183208e914f | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `pyproject.toml` | text | 9286 | 8f0d79131a56e4b5dd905b23a3cd648e6d953c24c7939fe82e4934365b901f0a | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `requirements-nginx.txt` | text | 4153 | 9c26a79738e71dc1fb85492cfb869415ace2e558e191da0ed6b976884bf6096d | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `requirements.txt` | text | 3693 | 72dfe8f7d48ff1737db5d1abd4cc8aac1f06c1dccf88f5f9bbf46c96dd81e955 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/__init__.py` | text | 5552 | 17e6cb9e31ef963a82642db9d6f99c2d5d3f0526e1c0772546f13aff10e9039c | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/account_schema.py` | text | 1937 | 0692d81283007c44ba0546edecf170a13161f704e7af49f692c0df25de502927 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/analyzer.py` | text | 3797 | 69b0a2d8ef9d6ec7db38c794b61b0bfa90f0402fb5eb70b6f1958ba97d049419 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/basket_order.py` | text | 2824 | cb37e1b9f63e4f15556a26b1c8fd3e93d4cd1d433fc94f9b28f32450d9a57f17 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/cancel_all_order.py` | text | 3592 | 0e8c95392f66e8d3c560a68e71c5f4156d36466f41fe5178490ed341b261d78f | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/cancel_gtt_order.py` | text | 2495 | 0b419ead3f78775c484ffabe8e687489871d3e46117aef3a415d29d00cae61f7 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/cancel_order.py` | text | 3571 | 37d35386d3a004f8390c75fd171fe10c7120ad33703c8b04bf143f4f8c70feba | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/charges.py` | text | 2530 | ac21205e98af0eafac1d6e71ccb59d0c61db4fe9cac07ad13a24a765a7e43f3a | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/chart_api.py` | text | 4486 | 356721ee29c75f4321218196bf1c235ca70afa87c12555cb5a1f3ecfe8c10a4a | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/close_position.py` | text | 3584 | 9c95454230f1a1ea0eff06eb7cabc8f3bfcf8d504ed3c5a32e247e9110eb6457 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/data_schemas.py` | text | 11235 | 14267ec7be91d7537931b768c1b367fb13dfc04c865ec1984e137a2e8b15ddc7 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/depth.py` | text | 1631 | 6d7e9f8304ee864aae1a08ffc512f93046f26808b88e32311488cfe9d8b7f64c | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/expiry.py` | text | 1853 | 71237b87d7a269f5cfa917e777c6c3c74ebde94db3e723a584ee2683ebf91061 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/funds.py` | text | 1531 | 8c2a9360c1dae39a857a612e99dcc007204f5a57079a94aac25bf8bc62c374dd | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/gtt_orderbook.py` | text | 1486 | d2417cdd61d7c7f0cd746aede339da59d31516a3d92b37ef5e164ea0b34fd7eb | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/history.py` | text | 2087 | 0814dbc4dbf72df17f8a4ee1e0c6ea02f6562988a089209735f2f4456b57a0e9 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/holdings.py` | text | 1499 | 5b23075a3639e223eb9438c2bdcfdac9240171df1a09adfbf21a68eb50add4cd | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/instruments.py` | text | 5189 | 46978414983102b7689b192160042272ab2497c86075db2fc5b88d28d5ecfe9a | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/intervals.py` | text | 1539 | 73af81418e12673c7c97937754b1aac6c4001e74413746ad0cdeaa97b2f2a705 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/margin.py` | text | 2521 | 065f3e08e011f4094fecdde2dc3ba3e607c9024ef2707cb8ec5d6b50506d0994 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/market_holidays.py` | text | 1573 | 7704a51ff32d4844e02e219ad05d2377cb70b0eec17a6ae303c15a1b047d070d | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/market_timings.py` | text | 1567 | d4148c1ea9174d0d9b93586988ca3488c73ecb1e2ee370c9cf03208f1dbc1615 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/modify_gtt_order.py` | text | 2463 | 145b179b64642dbd84350beefe8058961b1c05221de37c6fddcb1e77a5c2fa52 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/modify_order.py` | text | 3547 | b71a50adcc80e445152ee27991a3c33b122381685370a2934fa671a9aa5dc728 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/multi_option_greeks.py` | text | 5290 | cf40aba4ca62eb3d9fe8eada35cb205a9ead5c7fdfb9153f50ac92e0e4a2c917 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/multiquotes.py` | text | 1637 | b9e74bf1c8858905dab80c49b1aba0009b61ddf3fc1f99ef252156a90e00f2f6 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/openposition.py` | text | 2542 | ba569280cbe85a0824051e016e6e96df1ed18008f175b82967a22517b386a5b5 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/option_chain.py` | text | 4066 | 2df6aae6613a1d6448d03d461f5e6d390880c596b16ce842cdd578d7c848dbd3 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/option_greeks.py` | text | 6163 | 244d3fe6c875581976f94638eb1890727734c91498d0d2bbcd3a26b6124fd54c | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/option_symbol.py` | text | 3492 | a60f4f1283ab876444dd90547d6495fd18aa38fcac5e9d9d831a59d5b1de0e94 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/options_multiorder.py` | text | 5065 | 4dd394c65e5c0e62324c6bf889391006a10d025ccfef67912495c7044a69aa05 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/options_order.py` | text | 4752 | 7458e70266eea294e37e27d325e91e998fbd239a33566f4f143184039d12c457 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/orderbook.py` | text | 1516 | dec7ab58ee6e5ef74dd2d2c106398c2a31ca5c827de1c4443cfa429f093ed720 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/orderstatus.py` | text | 2508 | 131bf818bbca7c5558a6fba4fc89ebcc717cc9309477b047a726a40870e88635 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/ping.py` | text | 1507 | e401c78293f332b302fd963756f64d7101fc40e01961c7375923437250f6881e | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/place_gtt_order.py` | text | 2495 | 65e7bc37235a4864d185427127ea5d3cd54a319f493056023c275a7d07f0673d | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/place_order.py` | text | 1770 | e40cabf148e346cd6db8f93a63457d6a14d8130bc9acebe7ce43870f26644f4b | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/place_smart_order.py` | text | 2843 | de1ecc47b1190ccd768f1e5e90ba0f49f9def6e24f63a0d56957487798230ecd | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/pnl_symbols.py` | text | 2000 | 1396ec40850aee7834fce622ad01d27e62c3eb0f0be11487fbdd39840c52eda1 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/portfolio.py` | text | 14952 | b646c9bcaa18e9fca3445f66ad0c89280d388cd83b25ec0d7fcfc6f72de4a3df | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/positionbook.py` | text | 1561 | da00b195a453944e73afc798ec6b44a67301824ff7421ec1075e373088b3dcac | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/quotes.py` | text | 1654 | 6fddb10e07e75a1c415a8ae5830321df05b817bb72d33876bd9ddc228d22a633 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/schemas.py` | text | 26561 | 60a139cdc08791cf2d7c12029c65be436b6b61189f5b4e46c5c241a90c94356a | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/search.py` | text | 1688 | 60200833f84d575c735c85b0fc22e1eb71581ac4e16b806240f4064edf64430b | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/sector_rotation.py` | text | 5725 | 54344ea23928e5df80cd97395cce9625e82fd90362b07aa36980c28484ad0099 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/sip.py` | text | 8640 | b2d6e6fdf1874d9f1eb65e4bbb9999ee6cd1cdc94ee4a0e2e25f0c99384d21fa | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/split_order.py` | text | 2800 | 078631551b013c4402319d53a3adfbfc939379cfebf3ced2bc25f0c1e64c7163 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/strategy.py` | text | 15487 | 8b3b876ce552ae6cd0103997cb517d8b27ffa593b8e32f802d34cf7f85aa7cb0 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/strategy_schema.py` | text | 4894 | 662e9763ed7ccd794400b30850f036695a66848d8b766c8128377e125dcbdc65 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/symbol.py` | text | 1723 | 1293fb9ee0196ab958d601364ed072cf6c024b16cdd66a1393ba9c19a68315a7 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/synthetic_future.py` | text | 3114 | 97f62a1ac06aedc348e247c8e6085b567e3fe653b85319fd4980239302d9a4b3 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/telegram_bot.py` | text | 26655 | 4e340b798913b1cde6e30a00b6acdbb0d84f88966b0d76ac01ffb72d5e1a5322 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/ticker.py` | text | 12457 | b053edf87ec2d579ac65c7264c0462b8eb9bcca9df6355fa610b648d341d3fc9 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/tradebook.py` | text | 1516 | 205003efcd15d68b66f25093b3e40e145684f5b5e5ada26f164b15bc6752195c | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/webhook_alerts.py` | text | 4047 | 2b77ee8ad98df2beb7ffa9ad5ba90c6d3f588251e79c81f22a6e1ce0d7c4c647 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `restx_api/whatsapp_bot.py` | text | 15583 | 65339dca09d6e0b74d6a085c570666b668b4de4f38b1a7b4b498132ac4e4fe90 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `sandbox/__init__.py` | text | 740 | 38359d41e05bea6be0147252ec532907bb6a49c5e182a1d671ee5493f8810f00 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `sandbox/catch_up_processor.py` | text | 20285 | 12a4a48498dc7f37133a2dc95f10c893502d542c418261cd56f96509cdbc9b53 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `sandbox/charge_manager.py` | text | 22503 | 190727c342ec0ebb961a7e80e61d25b0478889eecc561cec5ff5e9380adf20d9 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `sandbox/charges.py` | text | 29936 | b21e7b452c0643412bb2bb4f168a7dd19e0211f6caec22ba7254bace703d585c | backend source | INDIRECT | NOT_REVIEWED | PARTIAL: statutory schedule lines located by grep |
| `sandbox/execution_engine.py` | text | 59287 | 1d2e846bcba77683f3758f553198dd6ce1d19a96293de53f551ff13e632a79e2 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `sandbox/execution_thread.py` | text | 17536 | 3ef7959fa2b1c9b002726b7122eecaef8d79120e0633084921a837e0a70c2ce9 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `sandbox/fund_manager.py` | text | 53052 | 5d42158a5a0f25702dabeabf02d9ab46187dc31dbf23b43fcce62ee9bd7f607d | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `sandbox/gtt_manager.py` | text | 62328 | f6829db6cad97ccce6e195bff696260ee0ff4b6a5f6794b33a8af9c612b9eed2 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `sandbox/holdings_manager.py` | text | 19303 | 270fc7d7e20e936bbea169aecdc19717dfaba6b4bc97831b19bd4c8fbcecdab1 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `sandbox/order_manager.py` | text | 73215 | b7f479f1ff4531f4761453707f3f32902de405a9bd5cfbf165c0a9a3c08fce8e | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `sandbox/position_locks.py` | text | 6447 | bc4cce63ec4666697c082eab3a1f60ec7f5ecfff33ceeab4e195181c54705352 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `sandbox/position_manager.py` | text | 66757 | 8b81ef24eda24fc860d387f580b7b2961961e90a2b31094b7c51dc69c2369e7f | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `sandbox/session_boundary.py` | text | 3145 | 678b4a99811edeea912d1091cfd47bf15099ae59565233dbee1ff0411035b1d4 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `sandbox/squareoff_manager.py` | text | 18195 | 8b382e4e1a60604435c9cee98f88bddc6620d819d8cf95550d7a04feb9ecd43a | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `sandbox/squareoff_thread.py` | text | 18432 | e646a64f8ac75a6d2799f27534b01c2e8e181854ef040411b77afcbdf0c3b772 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `sandbox/websocket_execution_engine.py` | text | 40368 | 7efba6d200d56d5ade1745500d2e4393283e16059e5afab8f801f3242590a125 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `scripts/bench_greeks_baseline.py` | text | 2765 | 6aec79657beae5a278637e6681691837ffba0fde08b7b693aa44314cbc1684cc | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `scripts/bench_greeks_post_retry.py` | text | 1453 | e2ff396284e451cff399e65dbeffa306da9869f6c753e1c21d5529633f77e8cb | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `scripts/bench_greeks_postmigration.py` | text | 1840 | f714f57c0a521c68c498a5156c532712c8fb2647e4c2b2526c976c5fbfc7a73a | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `scripts/bench_greeks_retry_failed.py` | text | 1396 | c3ec2eca6efdb66b253321b8da572c7be08c2b9a39b39195654501707f70343d | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `scripts/bench_parity_opengreeks.py` | text | 9642 | b8e3c8453cafea8ef426dbf6842d24b3309c601adcf5316213d7e32da4c8dc97 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `scripts/extract_broker_token.py` | text | 4196 | 53bb5035da635301a3bdb72a851423e7a5815ac845733c1cc67d4356412d1d96 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `scripts/flow_diagnose.py` | text | 6182 | 17ec4f68bc7d1357ffa30aa61edd5f9c8e7f853ef6be6df05752a9ca305f3ad0 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `scripts/generate_broker_compatibility.py` | text | 13763 | 85dc6be55fc552c3a37f807cae81f852de72f2106c7f473d4858cec18d013be2 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `scripts/generate_indicator_reference.py` | text | 7249 | e167241c03ef3a51494a4e20f35f36fea6ae9b88a15228693411f4f8ffaf4608 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `scripts/gthread_broker_smoke.py` | text | 11978 | 07b6b93625bca062dfd5b27ebe18daeffc75e0dafa0e33495cba4321eee5a7c5 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `scripts/gthread_check_then_act.py` | text | 16170 | 5574074a0ba88b96faf537747e20f86b58867797d2043963e8ef0607a00686e9 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `scripts/gthread_check_then_act_reviewed.txt` | text | 5276 | 1fa5cf514e6141900d8a743b638dd38c48c8241ea26e5814d0cbb8b17e4a3f56 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `scripts/gthread_sleep_gate.py` | text | 11355 | c57d75889108b619d82c4dc83845b3a0e99a0dcdf48fa1baef9efce6515f6e23 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `scripts/gthread_sleep_reviewed.txt` | text | 1717 | 7c903f3ce85fafe7f49453105c19fe196e6087014b7f8ee7d08729a9c2a21b5b | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `scripts/gthread_smoke.py` | text | 18197 | f72b200f1979de7b59be06d7c9d63d0c2bba3bad08fbbfbbd68246dbbb0a4b53 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `scripts/mcp_live_check.py` | text | 4481 | adc2dbee52f4d0423cec320202eb7f39b22a4a2f83b5d44d74e0cd7788e54e42 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `scripts/render_baseline_md.py` | text | 6254 | 55967ca68ce54b0a0e6f8c225ac4de59be428f0ed34e52c6198a75740fa3d0c6 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `scripts/render_parity_md.py` | text | 12937 | 415f19d7f2c1cb1b74305166b5c9ea0ca4c42436d4b0c6cb58998bf131447e41 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `scripts/update_flow_workflow.py` | text | 6065 | 4eed6b4c6da4361179bf77e5d6a96271b50ce8acc1fa2e6188c62409e0084236 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/action_center_service.py` | text | 13470 | cd4e3f94975a435d3c63a122c64bd3b445c46a1e0565089aa8f578e54f0251c4 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/__init__.py` | text | 507 | a2bde490995bea14c116f24d6cc7b26f168c3b14e69f6c282dbd24398cbc8883 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/attachments.py` | text | 22980 | 09cbe71ce26a1b811f832b6f0541f40877d0eac540f78699324452c3637d8db8 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/builder.py` | text | 48418 | 785d383595c50953778463c023bcb6efd5e948517115315d9a273c9e94f9ca08 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/catalog.py` | text | 46189 | 114ded7d76ecd8e1e03d8a22bf577121e9b52d3cdd688f33da1d806dbfd4c6ed | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/chart_contract.py` | text | 21201 | 0ea9879262050c198a6d28f1084e28d1202b2f2775378ffe83448568a8b1d838 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/chart_geometry.py` | text | 51547 | fcc4b2ab38be4851b82ec52ac4ac551204112ce711a8a02afaedd2dbfef9f6e1 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/chatgpt_models.py` | text | 9625 | 0eccbf18605ee6e4b16adee297e2255c68df932d9240af110b5d394fadb2487c | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/chatgpt_oauth.py` | text | 67694 | e080f50e328668b62baab268a8cc841419a3e63d32befc8e3eda6c2cc818c337 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/error_messages.py` | text | 11413 | cbb3a2010794d408f8258e706042bc6b575bce5befb3db9100151083450ada7d | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/frames.py` | text | 18166 | 836fbfca3961da792982f6145e0076bbc9f8e1a5a01f25c900639cf5e9958430 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/indicators/__init__.py` | text | 1095 | 49fd9d3ee20d5b9cd1e9a21de7615324b1ecd1e26c1f23ff8277c4615c849662 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/indicators/compute.py` | text | 26053 | c16406d4e22c4e2079777ff138f259974c9c1f6c03a380a384ebec254c6210ff | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/indicators/descriptions.py` | text | 11465 | 19cc7f66814880f6aea833521d1cd2350f65ac5d705e2a36eeef33764c802595 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/indicators/registry.py` | text | 40683 | 9a9b6cd09a8427323296d77f6eb0b4a5f78d653295a60e2115c209859efc8152 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/litellm_eventlet.py` | text | 6471 | 0e2da51bb458ddfb78aa7b7420e1973f01caecde492fdee9b57bec2e09c8c9c4 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/litellm_loader.py` | text | 5168 | c70cc9108f4563fd3524f2d8669fd2ead85111c54948ae1abee8338c60f670ad | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/litellm_mcp_gateway.py` | text | 3867 | 632443d98abe9287ff7afb562b0fa95ac075bf114f8c187003c5020343fca104 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/litellm_tool_args.py` | text | 10014 | 9948973e638420cf6f945e706eb358b4df172c6ea0b755733bb1a14a87c98a41 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/mcp/__init__.py` | text | 588 | 8f2909fa064b54e49e4dd635ffd1d79433f62c6634cc5330aeb9b24dccca1710 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/mcp/client.py` | text | 42124 | 54f3985a4d9b3c6ace8d0b49a88400aa07b9a9e8667caf653f5eefd0fad88220 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/mcp/prompt.py` | text | 3263 | 7640fec6a68a61a82e3cae1a1ef818bca27fc4f17dceb20903873d262922e0ed | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/mcp/registry.py` | text | 8937 | fc0d4129c67a369e544607f86a18f9e1ca494110e997082bf3161253c70d4264 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/prompts.py` | text | 59826 | 01ba26a0ac4feae9190e9ae65785f57f9b0b42402c8cb0ae2d534a5ae366f203 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/providers.py` | text | 22765 | 29c3c53445f0f8f338e056a4ff71a82a763ce8412b3a07256fd9494d4812e2c5 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/safety/__init__.py` | text | 1370 | 6929b26ac06e1f5de69b51d81404bf5a6475623c606f68fbf808c517048aff06 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/safety/audit.py` | text | 19316 | 7c1cc2bbe4e177c30b90e496c6bb0a5053c4e349b029fead8d5a8753298963b9 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/safety/risk.py` | text | 50447 | 5866772c8f4608bc2e51d4cdbbf3bed59a5e6353e6b72cc6ef2abb31cac7e76b | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/safety/voice_confirm.py` | text | 6814 | e729d2d905ba0adb01a01b45036386a0a092cb69986006ede8172fef58b243b4 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/settings.py` | text | 86050 | 887ee8dafc3db109d205cf752e7da4390bb8a928e29d14b42ffb053be12cd6b0 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/skills/__init__.py` | text | 360 | 8f79e8be2f0707bda7aecf609a4a3dc4d2761e0a3b40a8b40cd7a0376bce5695 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/skills/loader.py` | text | 15387 | 705108cf60a934fb0c21590d253670cfea77a8b210bf124cac40bf78c37ca79d | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/skills/prompt.py` | text | 2360 | 84fdb6082cd0c6a6dd11ee9678000fbbab4d8025421f3da6bf92da58a3111068 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/skills/registry.py` | text | 6155 | 1ef1c81d3f296d44172d9170e601af5e5f3e33e2bd6730173e8d0a902eec0c3d | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/stream.py` | text | 71606 | 3fb16695d35a2a7e8bce086f5917b659abb91348a879abcaa4bfdc47115ec189 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/tool_guard.py` | text | 8106 | 788fa37bc77373c0544475b4a75f41c4365f6cf37a77fe089467d151b86b7511 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/tools/__init__.py` | text | 31893 | 1704ee916d4957b509a1f1d8abbe7db0c440859ee059dde02b078741e2ad1d6c | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/tools/account.py` | text | 32762 | b75082f67c05009d2b59add4cc75f0c79055a111f29e0a2ed41a78b79f29e98c | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/tools/base.py` | text | 62538 | 21775f352d1ab5f842746f1992ce140b115a7f1d80f3c2d850ca2bb1e5757555 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/tools/chart.py` | text | 63561 | 90d777f0b3c2cfd3a7a99477d7e92fbba4f87ecbb96ab98c078071ce16bc109c | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/tools/flow_gen.py` | text | 19162 | 5e38736c009cd6d54171a34908b9bf8134b2ffc137d4c189b56ebee0c54abf9e | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/tools/indicators.py` | text | 51919 | 5c60c0afd303ac4322f02702140c833085514502f0ca76f1e5f6a09a9db1bd75 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/tools/instrument.py` | text | 42680 | 5571afd46fd5d100c2c8468c165d7791459b765571bf8e96443d9526993f14af | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/tools/live.py` | text | 69336 | f9bd096a308a193d3a35b9a56995f249a773b096c8ce7fd78952a2ef35677390 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/tools/market.py` | text | 70090 | 1104700ac2c8c307c00ac3199a944388ab7cff27d4b7920e6e21d87a16ea6958 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/tools/mcp.py` | text | 27742 | 38cd55913f3dd3bd20f461c45f53c01519484e46f23aeec08d5def76590a7713 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/tools/openscript_gen.py` | text | 16003 | 454e37a5a81bbed00001ed5e6200b134fe1985ba2172ac3356ce1527450c7f1a | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/tools/openui.py` | text | 10263 | d564041c9fec9447657ed99e26c6bc737ebf99eaf8a24100733a16939616ad02 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/tools/option_viz.py` | text | 89390 | c21ec54b2561ad6888fb07c09bea71b9748121189aed4b5fb722607a8cb6ef64 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/tools/options.py` | text | 40907 | 00ec6c89f6ec3ecd92c83a3fbf9f12c25f432122b8e6f78deaef76744a6a0557 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/tools/order_vocab.py` | text | 4846 | 6ca5075c02a4c98fd0b06cefc86b863e0a9395b25289b47273d0c7f9cbfd8fd6 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/tools/orders.py` | text | 74475 | 6904e6e8af0bf31992255c5748a6cc8bc9b56f8ff3b55c119e05921738905255 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/tools/skills.py` | text | 11840 | ceae2ceb898acdfc6a26651484cb3604ec2449b8d693cfd69aa0ffe755c631db | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/tools/strategy_gen.py` | text | 33760 | b05ce2e99db41c71379043e295449c1df958af0288bc0036ca339497dfeb89b5 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/tools/symbols.py` | text | 39333 | 6fb7e6b1b1026b933f8d244ce1e7a55b14482b362a8d00e1ece7a841f136b241 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/tools/viz.py` | text | 53344 | 294f5afd81991f151aea3cf948757be54ff508e9d14dae43383fc639ed186b53 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/tools/websearch.py` | text | 114739 | a339843d1161805441bacfecbf4785a422c81d61f51ac4563ed34f1052bfdfb8 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/viz_sink.py` | text | 9473 | 926b1da2fd252d9817016d28f336c6589ede7e7833ddd9f577dc27f2d41bcb66 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/voice.py` | text | 26939 | 0bd9dcf500a30ba00c02de6074e85378ca79db757917ffa10d9e89ffa15b22ca | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/voice_providers.py` | text | 5186 | 200957bd5eb11105c5bdce329ee79335b05cb4106c3ace452c35350a5d4d5b9d | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/agent/web_prompt.py` | text | 3820 | 096e4f5573f840cff15d7628ccae21418a5eaabefdbd3b937bea02850a003ace | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/alerts/__init__.py` | text | 1100 | b83f7f8164249a0d8986b562b256f96af7123edbd7faefa5dc50fdf55c87582d | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/alerts/categories.py` | text | 3192 | e56d5697caf9c7258ac968ceca603adb4f0b8743e00ffbeb279daa51ffa18a51 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/alerts/channels/__init__.py` | text | 71 | e3a93fbbb6f85c93dd8971cb767b82a8a72f26159a628dbc881f56f5f9ba0956 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/alerts/channels/base.py` | text | 3093 | 84218242c7a62511e8a40358594e0f02db61a3ee4a50e21c84d398e4296f8b41 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/alerts/channels/discord.py` | text | 2232 | 7f69c72d6348c4b7cf91d21d36a0d3d6a4617a66339008dd854390edf839052d | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/alerts/channels/slack.py` | text | 2103 | 8fc0490db1499475e4d435d13a780aaf85a117e13ea9807eec51d26eb8dbddf6 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/alerts/channels/telegram.py` | text | 3261 | 8ea3a7916961dc8c11e9ceff35b34616f3885a094e3b9067505197897161ff95 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/alerts/channels/webhook.py` | text | 15701 | 08e555cc1ef855d623b0e79ba748fae012635ab63258c887f0088463b9dc6e59 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/alerts/channels/whatsapp.py` | text | 2700 | 96b12d2119f3637b22d72a51f53c81c32c6bc492e3b5ffe39ab4a37dfc4c4ba7 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/alerts/formatting.py` | text | 13300 | 1c735526122d6629769a25b5736fc704f56f3c4fa5df9d43007ec6f35f94b57d | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/alerts/notify.py` | text | 3211 | f311f6c2a095fe98064d12ddb565c345c9e12cbad4c8e4d9698d067836ffdf85 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/alerts/registry.py` | text | 1249 | caf46c164de477aee639e30bbd29d6644ca8901e29f6dd064c5da9a3bdb6cf27 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/alerts/router.py` | text | 2040 | 259a80293d0ecb233bbd7297e16003411503154c0393a20400461d22be8727ef | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/alerts/settings.py` | text | 7094 | 831b6c7639e9dcd66c4c13472c69f5fc94c32a7501a5cfaa47197db09b567f09 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/analyzer_service.py` | text | 14658 | 62c8aee12cf97797baff84073a7b652bfb70cb37f8155d315f7027aac3cb718c | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/arbitrage_service.py` | text | 7940 | 0857d9ef08daf31d689f3523ec541385d2039c872c1fe06cc564b8cc819b39da | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/basket_order_service.py` | text | 17161 | a5be49d71ad8064a4b4c6c7415492072569168f448250568a5dadcf55cb48356 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/broker_busy.py` | text | 2126 | ec98a50938c6b27fbf395e859cb4d8b0f9d174ef9cb79e4da0c8231fb25a8866 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/broker_keepalive_service.py` | text | 7117 | 9640ad2bfc045acc474395687ece3517d91c36de6fb105d5d6ec4a3cb31e06a4 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/cancel_all_order_service.py` | text | 10354 | 9718db8fa03c4e4152d4c31f98a469c29bfcf31aad701e539c494a144296e548 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/cancel_gtt_order_service.py` | text | 8114 | ea0ef04e05b89c527cd69279750ee5f74d7af8e0a4f5212ce84c8d8428a51611 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/cancel_order_service.py` | text | 10727 | 18d0ef15dc789cf25aa9a27bea34639bd3fa113e5020ffb49ca07307040b8c4d | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/charges_service.py` | text | 6774 | 029636687096adb9390c7c14e97ca102af02056d674a6e6beb9393581e6595c5 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/chart_service.py` | text | 3528 | f45143e544f4f964e89d24f51abc2fa7243967377683d67661634e4a85e8bbbc | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/close_position_service.py` | text | 11950 | 67147a3a532623d1d4dea4d20474bb11fd475af593201ed1b95a3a9ea8e817ef | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/custom_straddle_service.py` | text | 16870 | df0cab1f2fb18ef6334d3d84033d6ac3b192502260b71c7a5d2c111d17b28e4e | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/depth_service.py` | text | 6867 | f39236a4804734bbb61b793a5cd361338ae867116377b4b3914539d38a73e482 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/expiry_service.py` | text | 10891 | 9d0efd21fe7da74e6bf95b48f1f67bda7990a944e5306786744b25f330ec35d4 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/flow_executor_service.py` | text | 233563 | 27c9dc77f31e332cfff75226ca63ffa8214a6ef895257c2347582be84dcf9b3f | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/flow_node_contracts.py` | text | 4968 | e4d064f850961ea8c578af7205e539e5daea2d45c21cf488470dd6cdf638a4f1 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/flow_openalgo_client.py` | text | 30513 | 00bbdd5ee41923d4ebf5a0367e81fb1338bba4e1aa9a5f279be3ef051f52c498 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/flow_order_update_monitor_service.py` | text | 21797 | 8ec308b84fbb214e9ec979035709cf19dc1440a6e3d7b67af305fcbd96cb2742 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/flow_price_monitor_service.py` | text | 28802 | 0cc3374e1e75ac92996d2f678dac9dd411df508f5e3fcf46d62a3175dba9afd3 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/flow_scheduler_service.py` | text | 28325 | efd6b225d86a572d4acee7ad794bb1d728b9fa19df0a9a9b1692480210a35f23 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/flow_workflow_validator.py` | text | 65339 | 79688268fbfd1c5ef70eacca3be1a2f706bcdccbfb4d3cad439ec9255e16477c | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/funds_service.py` | text | 4244 | 13406330dc42bdc499ddc8bd62effb0d3d68e6974cfc13f5793f62caa2ac2a5f | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/gamma_density_service.py` | text | 13605 | d81a0e39b36ae46b1ac4eaf6e69ec8bbc3631faa636038a8ecb0326349f4544a | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/gex_service.py` | text | 6905 | ff8375a1b02876696c5dc3a5aa96079e6755d413223d481dc51fe81c8d990e15 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/gtt_orderbook_service.py` | text | 3703 | 4e17117c72c16324be2ab32e1b02741cdd1ae7071b1051c1bd7d38f694fe8e20 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/historify_scheduler_service.py` | text | 26991 | 88867b692a0bd8565b323679257496bd053980eed9162150434ae77eb09f7738 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/historify_service.py` | text | 84848 | 1ee5d9e8bf951ea48cefc4a209e8cc633b652c7b7b3e8ad5166cb42e584c0a84 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/history_service.py` | text | 12189 | 50522919aac0f2d6aac4bc52544ad976a296a489ad61ef6a8a222abfd09e79c3 | backend source | INDIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `services/holdings_service.py` | text | 6384 | 9d3ba1bfc8eea294bc6138ca7b2053d95645d784f528813fbe05267a8b2a866d | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/indicator_service.py` | text | 33102 | 314621acf3c79e9f15ec1608f52a724934c56da31cdf41db68509edb1f22448d | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/instruments_service.py` | text | 4502 | bde45a51f2f1c0f3fb83d055c75ad61307e33e1d183f0b76f3e704431fa3759d | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/intervals_service.py` | text | 5079 | e6b158cb10d53dd90b1315e2923ebd363d09315a7d875fe18137a49dd4047882 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/iv_chart_service.py` | text | 21916 | d951b6920e27a41f49fefa1c9ff54f4bd4a5e27402b136f1c40882fbf62662a8 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/iv_smile_service.py` | text | 6490 | 6c1a4de4bc5b5c61caafdf779f58fe93410a21fe98777675561d01a8a68c7008 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/margin_service.py` | text | 10714 | 62f539e72998414b2a028095617982779347f76c2a2a323222d092f590db1355 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/market_calendar_service.py` | text | 4885 | dd96c5a7d73f12e566acc7aa971560d674efc5d1102b7703a59c31cf713b8985 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/market_data_service.py` | text | 43283 | f5de678b17cdc21952a2dfcc9e9db51da3a7fce68d7bfddb1ecf78617f6fb8b9 | backend source | INDIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `services/modify_gtt_order_service.py` | text | 8552 | 3a6895ba527b0649f319c534f801968e78a87f63eac983351e1685812f8a7fa2 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/modify_order_service.py` | text | 11180 | 3d3a9e77a09314560dccd06919eea26bbe9ddaa3a4855bed4c224465aab2e808 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/multi_strike_oi_service.py` | text | 10237 | 98f30b09dbf93e8c59c6ce08d4737b4030256f65c43523a4d229bf25c19fa22c | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/nifty_algo/__init__.py` | text | 68 | 14e22addb9b89d86086b8db3e308dab741fca972d50157e7f150a2ec36458e40 | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `services/nifty_algo/analytics.py` | text | 8691 | 0bdb54522f3be782de319540d71643817df8aeb326f9c47398409b8d1e38316a | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `services/nifty_algo/analytics_report.py` | text | 3323 | b0e740cc647299cea84120e9a393d5e590af1e8a75adfe2f3dbec251ec819350 | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `services/nifty_algo/assessment.py` | text | 8312 | 06a405984520af227b2ce5de1f7da05453b44e38eeb7c591d24e98d61120f7b0 | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `services/nifty_algo/calendar.py` | text | 3433 | 98a85e56a682b100389bd640a8d6533d2f6b8879a9a0a65d1436fdbf9321cfa4 | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `services/nifty_algo/calendar_import.py` | text | 11282 | 169b31de2fb767a67c65bbe0c918cb5879c268b4398516d34bda69868d63fcaa | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `services/nifty_algo/confidence.py` | text | 3096 | 6e8c4cf52e69b83a6f3b632b16232a0c5b8d17415439de02d6863ba935e94b10 | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `services/nifty_algo/config.py` | text | 13507 | e72e68b21ece543e04e4afa31493aa694f21f23716bf08a6c55afd831407b6ac | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `services/nifty_algo/contract_resolver.py` | text | 16747 | 11c892599e5ab3e2617521510e4207483d42e6678fc3b7acbeb356fb6696eb43 | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `services/nifty_algo/depth_quote.py` | text | 4451 | c86826cf86bbbdfb4971d9925fad630ac8216d0388cbd7068864a6bc26e70e87 | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `services/nifty_algo/discord_bot.py` | text | 22650 | 22b278e2adc77cac485fe9df1f35435f5d8c0e378006776d9e4be3ec4745b279 | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `services/nifty_algo/execution_quality.py` | text | 4865 | 469a1e0af456b559c6ac65bee89869d9f61b97aa9e872a1f46edae8959430da5 | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `services/nifty_algo/execution_replay.py` | text | 31857 | 393f45fe4cbb55172cd67fa222be8058f544a8384f525616d1db0d45f7a84bc3 | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `services/nifty_algo/indicators.py` | text | 8020 | d8c0f2e41814c0c1e777ec505e1d314153f29885a02b048ae5fbcda513b1c277 | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `services/nifty_algo/ledger_analytics.py` | text | 5434 | 64c416962429bb38fc23b09a003ff6a86ad0dd40b515314b7a9527b1c825bfff | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `services/nifty_algo/market_data.py` | text | 4641 | 916e97bb8dcc4170dea2a0ed4494ed5478badfd4c6e9687e6f1cfeae60d4645f | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `services/nifty_algo/models.py` | text | 4185 | b49a97a64e48e8fa95f2d83be929b49abe9a20d95260eb5eb226361ae18cbd17 | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `services/nifty_algo/native_data.py` | text | 16994 | 71c8aaeffd147450f12db847082dcba359f081e06cdeba20b17fd092b5fef2f6 | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `services/nifty_algo/notification_worker.py` | text | 9918 | d8a01488bfa4b43d09de8914572a3ee49f746dc1b59273a7cfed20e55f4ecd09 | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `services/nifty_algo/paper_executor.py` | text | 34369 | c0928dd2511a248b7f68df950b26311a5c4df2214e6555f2cdc1780c27b34258 | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `services/nifty_algo/protection.py` | text | 14309 | 55cc3cb9815ac9c02292c4ab9d401c25595982991a588670baec96f6abac5145 | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `services/nifty_algo/replay_lab.py` | text | 5659 | 23a9b5971a739187fc114321105210740344232e3571e5d7d5f03d56d79623ba | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `services/nifty_algo/replay_worker.py` | text | 4271 | b6a0f1564339a3093cb8d8d4dafc12db943f0064f5b502b130b509e5f4b45a3a | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `services/nifty_algo/reports.py` | text | 34723 | e1fbd330a3bba7e3431d8bccb70a4954d753902e2706cdbcd0eefebad25e5a0a | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `services/nifty_algo/research.py` | text | 24661 | b57ff9028e64dace0e844dd2adcd826bce3504c7ca48efef4b71a58fddf6bae0 | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `services/nifty_algo/risk_manager.py` | text | 9734 | 04951e9edd53c5a339662ee057537ea5503bf87db48c2164c4380a4907f7076e | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `services/nifty_algo/runner.py` | text | 45374 | 2757136a01016f830259550cbf4811e0040116a4c2e14da4c148adf4995b0590 | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `services/nifty_algo/safe_logging.py` | text | 608 | 2e562b14ce4c4f53120d85c9a394742aced2c7abbbebdcf7be3cb427256de93f | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `services/nifty_algo/selection_scoring.py` | text | 3612 | d6aec94aff2658c7f39ac7ea75820bc5c6a4a855d04291d818ab910a3cdd488e | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `services/nifty_algo/shadow.py` | text | 6409 | d5b073855d34e8a8aee6a413d65a73e2c63cd005d3e8254271f6c77c5a2e3d25 | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `services/nifty_algo/signal_engine.py` | text | 9319 | ca2688e505a4fb069828d80c460b2eb93f96050752ebbb6d7ac5dd225cee1e3b | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `services/nifty_algo/trading_mode.py` | text | 7693 | 9c8a5d946c86f0a7bca9ecd019ee47602cae03b9496925c11a309634a7dde421 | backend source | DIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `services/oi_profile_service.py` | text | 16227 | 25f4ceeb3393132ff7b22ab375215ebc20581ee35b429027dfa8825fc0ecdbb6 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/oi_tracker_service.py` | text | 12573 | 3f8e754836f356bfeab14c5dcc497da5f88fe3913710908d1278291cccc8ab0f | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/openposition_service.py` | text | 8542 | 5eb92e748120113ac8681a4c812b6210b0b42510da273fd817f3b2fdb49daed1 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/openscript_books.py` | text | 16932 | 150d58978087dfea4467844dcb9faa37ac4f04eeb6c6bb84d919e3a14c5cca8a | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/openscript_commands.py` | text | 13848 | 9da63b5d3faf740ba78429b4a4c8ee31ccf75028e28ecda2ce1fd0057dadc674 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/openscript_deployment.py` | text | 7357 | cf164de2439b518a81e8c3ae2142945ba0f2835295b834fc458d0f6eb2615fdf | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/openscript_instrument_service.py` | text | 13850 | 2a2a452c3a328f1386e5b8a0eb007227c081ac7792c07b62ad8481056c6082a2 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/openscript_run_config.py` | text | 27616 | a6a4c8fbc0974a4d62a08f2d413bf459d1345ffdeb7842f9787461eca5a97929 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/openscript_runner_service.py` | text | 72781 | 14646d07dcde5f781521d7713cb70f506e783bee0c485708db7f8adf10e0cb68 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/openscript_running.py` | text | 6376 | a8efc391a11ed79488b2211a012e6417fe0493c8106a07cbd3c07a704bb12442 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/openscript_store.py` | text | 14822 | 727799b31bb63d9989f529b0bf4884d82fcb8b976537062d5ff616922932ed44 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/option_chain_service.py` | text | 32737 | 5e5fe333c097f4f0e84a846126413be9231adcdf101977cbc04389a4efb6e04e | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/option_greeks_service.py` | text | 47536 | ee265c5249845784850318262a3870f3ee5907ebdd3a360cd1f3b33735aec201 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/option_symbol_service.py` | text | 40568 | 1d367906f015bde18c077faeb85cf8605f2c0dff789f5a7836ebcc63e4179ceb | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/options_multiorder_service.py` | text | 31172 | 945999e79c74586f0cdfef3a6ddfdebf5884bc4c4d16b0c724321bac6361bbd1 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/order_router_service.py` | text | 5465 | f9fd17b7578d7c22fc73579bebdaed3fadb263fe65da80cea936b790580a9e1a | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/order_update_service.py` | text | 13909 | 405d0f33f9dbd186b379e59fbb92f4d53b72ea7d4c0104745190400abaffbf74 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/orderbook_service.py` | text | 8207 | aa74b688c1aa13216c2375e0c35a2067ba6a99d861ef1bf3025bb8534a590e2c | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/orderstatus_service.py` | text | 14231 | 3fd57a41100ec2bb365f6c733b3106d110056e4fca750f43357706f3dad79406 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/pending_order_execution_service.py` | text | 18678 | 9ab07980b16f123b06812de4a722bf0857383448a643c41e1bb16e3cdcda09e5 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/ping_service.py` | text | 2215 | d7c0938675506af2ae2aeb16a5d031b8e7e39bd671466c91258767caf69b137e | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/place_gtt_order_service.py` | text | 10497 | 5a95b380a6fc510189003ac0be11ac8b58e8c827b1cf3d2c79886fdf1bed9750 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/place_options_order_service.py` | text | 16334 | 77a55a91d0a8fb7a6789bffc75294312e039be02f3481b35e29ae963fbbb0c37 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/place_order_service.py` | text | 15375 | 4730f32d9d5cc8a931793b10a6efb2f25fea39bebf6e08314d3479f9a31b5fd4 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/place_smart_order_service.py` | text | 13990 | b0143b41a0d4bee853577ffc476adb01be4001bbfc79843fa7ec0b9115f3e027 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/portfolio_service.py` | text | 35973 | cb9e620f499759b1aa3f4e8f9cfd84ba581319006872fb1637899ec3b985f8ca | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/positionbook_service.py` | text | 6856 | 0d6bd78ac24543f8cda134796e6a96d31f9122a3d5ca9c62341e70f731a10be6 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/quotes_service.py` | text | 14397 | 3b79085bb32b186b1154ef7e3e6a8fda88b54ba86303a652cf216808587760da | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/risk/__init__.py` | text | 2942 | ac956450ed29d0951cc7f3b266e7bc58c8ccf9ce037622705969e4948ecf53fd | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/risk/adapters.py` | text | 1759 | 97c88b390c038f993ff07a7a6c2f4c2a21a666c25478d4954182c9410266e1a4 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/risk/aggregate.py` | text | 12385 | 94d782a9b433111cc2c042f9d0eac9c409927fd3d85a215418eeb8057d5dab9d | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/risk/models.py` | text | 20354 | 13b53b0ffeae41027d7c6d1ef316333a923817575f670c7f3143d3335b414a02 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/risk/position.py` | text | 15304 | da17b57e66136af3fac55177dce57ba1abf439d309068333bbbdd1f880e19a71 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/sandbox_service.py` | text | 29271 | 75b9f6c6d1a1ce952bb5817b6352677be8aa0c806561eca1bc8b64a16e1a8cbd | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/scalping_risk_monitor_service.py` | text | 34075 | 335a1d2c15b56c6120d034626c5dd9b0cf55dbfd0ae0da7429a582cba0203624 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/search_service.py` | text | 4963 | f7ce48a76d14c3826f14e66100b0a5804a5f6e932e6eb85eb8f3a6e5d22480f0 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/sector_rotation_service.py` | text | 20265 | 29501322cb4af065c1aec6728b26ea11dc8840b6796347154653ed148bf913b0 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/sip_service.py` | text | 13844 | 0209f7600681ec56022b92ac188bb7ba2d1e21f07b33961daaf629b396bfb474 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/split_order_service.py` | text | 18201 | be8aad9fedc624c3ca82218b9cab66977d2994b67e59e7ac8d8a7169418027f5 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/straddle_chart_service.py` | text | 14238 | 9ebcd3e658968590f6622284d25cafcd112155e4c957a5f1bb4eff31fa72d0e1 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/strategy_builder_reference_service.py` | text | 2313 | 8158f41a8fa520ecabce44626a84a137ec1b35b508e4a46fa49ccf5524ab5431 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/strategy_chart_service.py` | text | 18910 | 020b67b332bb5127a6fc97fb03d321b2daf1d56a98235d9d163e93a2e0b350d1 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/strategy_module/__init__.py` | text | 194 | ad6fddc7ba7111c2adc141fcea002ba9b596ea79adf5eb02b32b227977f4417e | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/strategy_module/ack_reconciliation.py` | text | 10386 | 1ef1028655a775de0ed29df7bdde1552366e767bd26b98dc2a93821aba9827ba | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/strategy_module/audit_messages.py` | text | 343 | e44fc10c049c8cacf983a8f26aeea75e0a23e1d9d71bc3e27c40d00d72e6b1bb | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/strategy_module/broadcast.py` | text | 28298 | 77990cd1d280525109607fdddffb98df04fe83d2a08baad567afff598ef0da7a | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/strategy_module/broker_binding.py` | text | 5563 | 2bc0d6ea2bc1cbde0567b5e8a3be822f6f543b13c4ae5a345c7dd4ce07411ab3 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/strategy_module/checkpoint.py` | text | 9110 | f7d7209bca4330e71a617ca79f2e53066a4c0d6b6ef8bcd7e6af693074ce2eb3 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/strategy_module/engine.py` | text | 99773 | 171dc69b164210334eea0c1debcd5bf99b7335b75a2b8e71b86857aae9035e0b | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/strategy_module/order_dispatch.py` | text | 23363 | a582214a0f0f6528c4d53d6f6c5d0d8768e123534bfe5a78d3cac6e70dbcef21 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/strategy_module/order_events.py` | text | 34427 | 35a553c7c323a5cf88b744f820798e23f6a9979d33f8db258e83d8c1f518336e | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/strategy_module/recovery.py` | text | 52107 | 5dffe709e138fea481efc3c4a7e5938b466625c61cbf3dd5658ec8581809f71d | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/strategy_module/risk_adapter.py` | text | 13030 | 5ddd778ddddd0f596ffc34b048c218f4755ac508b8d7bd7d7590b249b590da7a | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/strategy_module/runtime.py` | text | 4899 | 43990d8bec3255fd2af57ebd2bb290e3e3ecf0f25b01ffeca0a8785734130904 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/strategy_module/scheduler.py` | text | 27285 | 7e29a011efa7807be810ce10a0e44a18fa291bbb81af7837528f95c2b789a77b | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/strategy_module/session.py` | text | 2150 | 55b0d065614cd3679658259a02e4bc05011f16706e036c5e4fc47405f548b508 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/strategy_module/signals.py` | text | 36970 | e479498eaed24b6b7077dadb827c0042385cb113efb27a11df01c39de72a668d | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/strategy_module/state.py` | text | 32672 | 44742d9ed7c57b81cc9b710d1d614a1ce502bc0d16afae3bf5fa952675b3661e | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/strategy_module/symbol_resolver.py` | text | 48924 | 22088729d3a403c329246e835a0da30bf01195a87990b13ee5eed954f16167bc | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/strategy_module/tick_feed.py` | text | 49652 | 75a26760e9938501a9903cc0f4a08298569a71833025dc72b8904ca264d7f3f0 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/strategy_module/views.py` | text | 27019 | c5dc4052151ab6f7cbf6e52b01bea68896b69db1f12500f26b7bd4b88de8a958 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/strategy_module/webhook.py` | text | 43474 | 3ac40ead31175cedcaec5ec6404f6261497d563cd017a847155cde538cb3f1ef | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/strategy_module/webhook_bridge.py` | text | 2467 | 9900be830cb1016f95d93403296893165074ea70ac55acf5606dbbca8dd58fd5 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/strategy_pnl_service.py` | text | 7643 | 850f113a983628bf862069f8e34b85df793194b448a831be8773a3f9dc83b7b1 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/strike_profile_service.py` | text | 16388 | ccbc94a46b6803915d7f1ad111cb3ba6686e2e7856c837f02265c3898506eff7 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/symbol_service.py` | text | 4628 | d10d8a7e068f36070fcca3d4a4ebd543f96567d6ef816a2dd6af5de90e5e4991 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/synthetic_future_service.py` | text | 6769 | 2f556b80dea52a392cb859f1204271af4e2ecabd4f9d28b8d12fbe1e20aa746f | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/telegram_alert_service.py` | text | 21612 | 2a8ad2ef1f5265976f4de7eb7fa28f23923fb69439f92d888e33d989d96eaf66 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/telegram_bot_service.py` | text | 124157 | aad8bde8171b289640d4141887e60d596bab424ed648bbb183b99ac1889b75d1 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/tradebook_service.py` | text | 6186 | 12fc0144661573dd1264929af7c13efb843a442b6a853fd2e5727f411532d644 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/vol_surface_service.py` | text | 10294 | ff2516d2fe0d2c41e54824b2c68cbf33d16e4e2e597d0c38bc67d1ae7115ec6b | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/websocket_client.py` | text | 46321 | 8ea349522acbacd664aa00e038bf7f6bf225df7fd2c96a9ab96b1cc22449c8ee | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/websocket_service.py` | text | 12574 | bf5c2439a3b2730524bf1db0aa087214ce693214225e876d3be79fcc52e56c31 | backend source | INDIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `services/whatsapp_alert_service.py` | text | 8927 | 9ab586c4f748bc7cd3dda544b20ce4b28b266992a579217bc89c464e59f3bf37 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `services/whatsapp_bot_service.py` | text | 83064 | 85800e2a276ad544b2ef37208efacc04448b641c61829203914179bf1da0e7a8 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `sip/__init__.py` | text | 216 | 9a3c228588b9248ecf15fefbd0c66ed43775198129ef462d7e7c3527300bfe95 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `sip/analytics.py` | text | 16227 | bc2fd33a1ad75670472cc7f6c16036bc27e05a85bff22b796bccc56d1636949b | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `sip/crisis.py` | text | 6683 | f4f1f6ee9899b961d891c84faf0b3f6869f62a67b59e49e1213ca68fc3acef08 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `sip/engine.py` | text | 11937 | dc75bbfc45b6c6d9864b82efe6b631c8ee0787dbbe81b295c346af9b6229c00f | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `sip/schedule.py` | text | 6668 | fdb350192ab869cbb7d5116a5afdbd9e09222dc45ab81ae5d82634911cde5305 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `sip/xirr.py` | text | 6312 | eb2b761f103e40318f30d891ae08a630f470d77947293ce3cccbfb0a0f416d49 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `start-app.bat` | text | 946 | adeb7b387fb22f2b48132bb78fd83a8b90ef05676a6fba57bb891604c02ced64 | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `start.sh` | text | 29158 | dd558ab86f01671aa4503aa883a111b7259a1418388d1d5c7dca5078ffa5a3ce | tooling/script | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `stitch_nifty_algo_trading_terminal/advanced_live_charts/code.html` | text | 39967 | dc7cb52acb94c267df8d9c2816aae2b15ea5dcfa4d49868fcc7c95ca249abda0 | configuration/other | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `stitch_nifty_algo_trading_terminal/advanced_live_charts/screen.png` | binary | 443027 | 881bd54c3db543aa06518fc24bff0aa1ff461016bd40c249c5970d00f1781d57 | configuration/other | DIRECT | NOT_REVIEWED | binary: type, size and hash recorded automatically; content not examined |
| `stitch_nifty_algo_trading_terminal/backtesting_and_historical_replay_lab/code.html` | text | 52857 | d4bfa939351d85e9aa92203239135bb31f4297e9f3e4bec8ca2127efd3c07e4e | configuration/other | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `stitch_nifty_algo_trading_terminal/backtesting_and_historical_replay_lab/screen.png` | binary | 395667 | fe4e8cf207cf9ee4ccb39aaaec926a240cbd3e4e6f72af0463e733317f25d072 | configuration/other | DIRECT | NOT_REVIEWED | binary: type, size and hash recorded automatically; content not examined |
| `stitch_nifty_algo_trading_terminal/main_trading_dashboard/code.html` | text | 37541 | 75c51df201602aa08df270e98f20a7aa15674aff0907ee554cfb31b16838f69f | configuration/other | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `stitch_nifty_algo_trading_terminal/main_trading_dashboard/screen.png` | binary | 417851 | 81b340a64ddea8810e0c6d2ecf4fb4dfd9d42fe6e9b3f2c3c54bab47b209043d | configuration/other | DIRECT | NOT_REVIEWED | binary: type, size and hash recorded automatically; content not examined |
| `stitch_nifty_algo_trading_terminal/obsidian_algorithmic_terminal/DESIGN.md` | text | 12575 | 668004706f1a19d258d2d67a157a5a6ad6daecc4220402731cb1ef617dc50076 | documentation | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `stitch_nifty_algo_trading_terminal/paper_trading_terminal/code.html` | text | 42609 | 9c16af75364e6d1c6a24903f144a12a974440e432389ac424f2d0ffa95773aa0 | configuration/other | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `stitch_nifty_algo_trading_terminal/paper_trading_terminal/screen.png` | binary | 518983 | f315132bc8b04c21956dc243ce43f373f51115e68eedb89196e78b514e0318a5 | configuration/other | DIRECT | NOT_REVIEWED | binary: type, size and hash recorded automatically; content not examined |
| `stitch_nifty_algo_trading_terminal/performance_analytics/code.html` | text | 55065 | 53e17e02fed2863039755596714d328fc5c2db89f2e44a4735837628392974d7 | configuration/other | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `stitch_nifty_algo_trading_terminal/performance_analytics/screen.png` | binary | 927514 | f285751ca60cd4eb7337bfdf825e3e15d5ffeb9ecd10843e6ffd89a1e8a706cc | configuration/other | DIRECT | NOT_REVIEWED | binary: type, size and hash recorded automatically; content not examined |
| `stitch_nifty_algo_trading_terminal/signal_monitor/code.html` | text | 35200 | 5cb70b0bb8d3bf4e582cb7829eaa5debcae1b74a11c6d0859d8247a0e1d8e8ee | configuration/other | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `stitch_nifty_algo_trading_terminal/signal_monitor/screen.png` | binary | 396006 | e7f6bed4d35b94c2e7363d2f1952b9c67f5d4f28a0b3ed89b9b1a5de1a23285e | configuration/other | DIRECT | NOT_REVIEWED | binary: type, size and hash recorded automatically; content not examined |
| `strategies/.gitignore` | text | 1453 | b680b808f6ab3a6e633149d89fdfb508b4a4d2ccb36ef626ece5903ef4874854 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `strategies/README.md` | text | 13656 | 5cd47c63b7716e3a46ad98ab6ace9dead515a97c524d6795f18cfd1c48f0fab6 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `strategies/RESOURCE_LIMITS.md` | text | 13947 | 2031435edceb7fce98f6d7b7932d0bc35d11bdd5de9dc91f4ebe8ddfffcd5b4b | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `strategies/examples/simple_ema_strategy.py` | text | 5344 | b5138dc8d20f7b0ff4fb435fdf44cf79bb3d10b4bd8d09d90cb0bb4bcdbcec3f | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `strategies/indicators/.gitignore` | text | 527 | 73ec65a239c1dc078c823948fa20a4bf71ea9150b6423bd8f089238af5610d4b | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `strategies/indicators/README.md` | text | 1808 | fb09900a818e4971e9a030957c28895ddecf536cb1c583e755743f732ecf8aa8 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `strategies/indicators/open_range_breakout.js` | text | 9727 | 6556f64a07c6bfd2d6a0ceccddb1a316736b76cd9eff7ffb38c26dc1983e457d | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `strategies/openscript/.gitignore` | text | 754 | 381f599bac9f96923571435e2f0b5c2c2d526a61cf1c9e56ed2a9bf318e3a8e3 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `strategies/openscript/README.md` | text | 742 | 909fd07740c23f06cfa69584dc70903693f25d3075ef4c8666c2b8aa6559c11d | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `strategies/scripts/.gitignore` | text | 372 | 41f16aaa1c1654f2abdd628d3b3451ced26e8d9e9ca827b55e6f6efc1137b9c4 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `subscribers/__init__.py` | text | 6422 | cd9f8941d907e7ba9b366bb07c72624d6fdfc0a454f3002a6175a8337e3d506d | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `subscribers/alert_subscriber.py` | text | 2553 | a86249d7c9f98e49c4b2e15b20af0813f86fef40a996703235e957d66511e75d | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `subscribers/log_subscriber.py` | text | 2061 | 26a10fe1970cfc195fe7133bd47718186676446dc4153c35ca0fac26aac1a634 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `subscribers/socketio_subscriber.py` | text | 10690 | 0e3ce83fde061b4dde98f90d0fd94573d3e9cc8182baec56ce17a88f1879a056 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `subscribers/strategy_book_subscriber.py` | text | 7188 | d8d93469cf18432aebb296aacbf7ef9014481d85285408775ee22db252cc5893 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `subscribers/wsproxy_subscriber.py` | text | 3428 | d6dade53769c3423f2a585c0ae31f65db12841137f4c69a089e7d27cee4fd02a | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `task_plan.md` | text | 5612 | 3c4e10082bd8c25304d0f14c1f74afd837d416e50e71f2f009890eec47d056ff | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/README_OPTION_GREEKS_TESTS.md` | text | 11904 | 2aae50fbf830a45efc33197d7f136b9e84ab55b550ac57f9275bdfb8d19809d2 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/README_OPTION_TESTS.md` | text | 5223 | 73cfe30c1c48658728bf1833ced7199273a4de9b47959f4a48bcf7b2a250a8a2 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/README_TELEGRAM_ALERT_TESTS.md` | text | 8205 | 52af33532b4a1815f37cbc9bf9e4342604b570be5071ddcdc5e987cd48fb6ff3 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/__init__.py` | text | 54 | cadeb49212da07516e43d0323ba0fcbfba02524821529f14d5b94c0eb488b39e | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/all_symbols.csv` | text | 107621 | 6b1b52eea8eaa124e5d40177fbcfe08fe549f4ee1cbe230eb48e7a2b70520968 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/conftest.py` | text | 7399 | 77f906da8c993f603c4e8aabeaa6d61ea17171d954f76c2bafc239ffbad18661 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/debug_telegram_link.py` | text | 5547 | 8ec422f7f87becf71d66a44448894a8b797e40684bb008b2f4ece58d8294356a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/fixtures/whatsapp_alert_golden.json` | text | 10377 | 2ba8d4845bdf836f94a7602df18108970e3750bb5a728724e2bb8493e879d7ef | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/iteration_test.py` | text | 10539 | 49035909ca85af9d7ba799d9cca9b8654bbc353d2b02c2b2d181e29646a51e96 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/ltp_example_test_1800 symbols.py` | text | 13952 | bcc5211d3453620c29c666eeefd31fb499bc2c5e401a5aecde5b55564adebeff | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/ltp_test_report.py` | text | 17831 | c755748707c720b282fce307144b1664f785d705152462e01ef32f75d345b7a4 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/nifty_calendar_helpers.py` | text | 2224 | 2c7ece252af0bac2356e1927a596a459cf68f2c7adfaa38bf6310559431c00a8 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/risk/test_risk_core.py` | text | 30090 | a57f5e8e3efed4b3e7a2939141c81e32189c26378472342d93fd11260a6dafca | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/risk/vectors.json` | text | 27477 | 88b704d5baba3e9a8195ea8a9f8d439e600ee3cdf0fa91fbd3c93fe61ce44bb0 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/sandbox/README.md` | text | 4755 | 802e7378b30ea73e7b47d0415f370c6fcd1a46567cad8f7d101520c2414a3d38 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/sandbox/charges_reference.json` | text | 49516 | 00afca46e79216b3f1a0c535d6609bf5eba82b4a90765cf310c7c0c8c99b574e | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/sandbox/conftest.py` | text | 5942 | ac864740e465218d13d46e6eae509bd55b40a2ae2bb817742f6bd20b05078c73 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/sandbox/test_catch_up_session_boundary.py` | text | 8863 | 5063e67a6415352a654e518a24359eb82fe8f92db297938f534396fddb421ed7 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/sandbox/test_charges.py` | text | 31213 | 1eba6e1c12d9427e6ef4e3f142ffb67664f3c85b85db826e3f10bad793d5e9b6 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/sandbox/test_cnc_sell_validation.py` | text | 9529 | 8c46331ff0cd1c7d05de261fcd9493ff7d0cd0ba6f635a9d4ce8ad6a9cb9465b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/sandbox/test_concurrent_orders.py` | text | 8679 | 1e5722d9d960caaad14c5304a0e6e216f0e5fdfffab948184fe109cc348f1fae | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/sandbox/test_execution_backlog.py` | text | 4630 | ed13d7e36f1ef6c7cba9cefe0d2f3de1aae03d41f9784edf84e6538ca0920590 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/sandbox/test_fund_manager.py` | text | 7399 | 679a11b9beb1881fea4a26737382f2fc21e1beb2fd643b8edeb482de22071299 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/sandbox/test_gtt_manager.py` | text | 90591 | aad43995430d1206398b7dfb08e9f0c547864cfa2f57830dfac66701285e8c8c | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/sandbox/test_holdings_sell.py` | text | 7181 | 7782b5348db60b343d10873cb0a6082a28231f7bc9f8be981509aa35ab966397 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/sandbox/test_margin_scenarios.py` | text | 11040 | 07a68991b3b655beb797107a134b13c5ff7e8d50c4d1c2046fc611c850f91abc | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/sandbox/test_orderbook_api.py` | text | 2446 | 3545e6b31df1d25ce1b8f980c39e782ff9f6c5d4b7a72cbc902fc0fb668d3599 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/sandbox/test_position_session_boundary.py` | text | 5412 | d0da3ed079a8b8541cb271c5854955d9fc8c6cb0571e66b23d55751889fe633e | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/sandbox/test_rejected_order.py` | text | 2212 | a0e8349e94474934271cf12604442bb7be0b71e7a0875482c052cbcbe59c7f2c | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/sandbox/test_stale_quote_guard.py` | text | 3501 | 72e952ae5d4d74a1346354cf08a217dd08738acd90a857d1ee856f93a9ba1e4b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/shoonya_getquotes_soak.py` | text | 44929 | e8abf4c3e279006aad3be10056ad894f2964db4cd8e2c2ab6f349cce4843524a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/simple_depth_test.py` | text | 15050 | 1fa98f352f0483f15b97c2f8ae7ca4a703581ca5c10f2258c796725705a4625f | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/simple_ltp_test.py` | text | 12781 | 5b95b67a8ab1fd0e90a105fc095a32215daab016d98d3625ec62613bcb78602c | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/simple_quote_test.py` | text | 12599 | fe293d3c642207acb16f794991a50b4f7b61b3e58030d1c266f411c8cacce5fb | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/symbols.csv` | text | 19877 | 36cf55105b2ba497a4a4409c8a7b66f78da9656eb85da094a1f9b1801d91d232 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/telegram_startup_eventlet_child.py` | text | 3614 | fb65fb667b47e1ed97d978ce3b91f9eb987900b9218be30892fc22879937b83e | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_action_center.py` | text | 14988 | 53c98e74cb0a36c7936de94133bbbfff8496349cfe438a337f67adbb2739f3ea | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_admin_client_error_url.py` | text | 1551 | f30d22f6a7eff0a0c9ddb458f3c7ce9c66cc07b37edd27739651508c4d9551a0 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_agent_chart_surface.py` | text | 40064 | 06f1659ebb8bb5bbd3d37acd2b3407943b364060a393924498c1cb26046f4640 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_agent_chatgpt_models.py` | text | 6356 | 332347a78c832f11ba831688b4bd0e5685aebf6997935877198f6022efac2127 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_agent_chatgpt_oauth.py` | text | 67330 | d1f9ef26f96dc2f1fb1218d17f83a80d39f0e395a8a8777b63da45f6aaf7a96b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_agent_chatgpt_wiring.py` | text | 30049 | 1823a185cf384150c4676fd0b08ba24c56be6cae60db88cbc27bb8456b199b58 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_agent_combined_premium.py` | text | 11105 | 25aeedafbca1f7c5ce58e5858ab5d1037f932c0e6c400fda183aab5da1b04c28 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_agent_composer_backend.py` | text | 35301 | 0720ee88bccfd6629b1fbbc80e581862fffe654ade24d3715915922534cd3ae7 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_agent_error_messages.py` | text | 9262 | 93d8453f2a673273f50154e5ae99949dd79df6cd20ad2dc157c878e737a069e9 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_agent_litellm_import_race.py` | text | 3046 | 7920449f9c49c345542b3fc635da3a6061bfaaaa82f4c5daf8ad734c6bdb0179 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_agent_litellm_mcp_gateway.py` | text | 7152 | cf794d31cf2abbc8ab62cf421a726cc0bd7b53800ddbfdc4e50379a1447cdfe1 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_agent_litellm_tool_args.py` | text | 5598 | d068e23aeacb94095d795ce1d431144a3fa4f954c1fa4933a6659658e5d997ff | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_agent_mcp.py` | text | 52078 | 13e0a0d244376e6113c4b25b9838445ab3c9f5a1d87404ce3fb535c0a23e69ee | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_agent_openscript_tool.py` | text | 13779 | 00a6ebecbecf7af6801cf343530328683efdf04a44a6deae6247c0e91a71fe1b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_agent_openui_tool.py` | text | 13516 | 089b6ca9a027fcdd307e1a17d0c3ace0fdaa2bf7a6c4ddea0b613804846ad099 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_agent_order_tool_arguments.py` | text | 20059 | 1dbbb3a3e7f0a5ca91dd3d48e385f8c87da390f3cfd60b1e1cf1de0a2e73fcb8 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_agent_prompt_cache.py` | text | 5856 | 459a8d447233d162e33ffdc074c7699e5e31dc5db85c4e237bdcbeb3cae71c46 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_agent_skills.py` | text | 20504 | f97cd0e315e940ca1cef7c3170a5eae22c2782a2f905122a5f1fd1ee37e7eb04 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_agent_stream_eventlet.py` | text | 20738 | e2d1147bfa5295b1a8d3ee0b5d84e3a795aefc369d3ef03b7fdc89b24fea1d9e | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_agent_tool_arguments.py` | text | 26880 | af8cd0cbffafccac97cd1736b82f4b8f82d0b1fab58df70169cf5a31e4286440 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_agent_tool_guard.py` | text | 4942 | a691bc3c5badf25aa5ebae24abfc6dc90aedf9c0e1dae3a6ee5e277dec3654f4 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_agent_viz_tool_arguments.py` | text | 25565 | 8bbb9178f9639433f1b3b88d2c56ea3dc02b80b9f925ca61bbe39a23c461a716 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_agent_voice.py` | text | 38753 | 4f0085a175f72e664739cdf4dded44dc9679de3641fa15000579d776418af2c8 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_agent_webfetch.py` | text | 39202 | 68d8abe244fcc4c62e6da92616f7d0ac6e8c417a4ff3cf28231af205f2907906 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_agent_websearch_settings.py` | text | 14743 | d9018736f79e5d904d93d4fadd4c42d18368123408b25e5ef682dbad831f4705 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_agent_websearch_transport.py` | text | 7098 | f9ed86fe6de6fca50f446d6be16dfae9d8e8a7b7977a3dd7d8247c492a6ae31b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_alert_log_db.py` | text | 9672 | 275c4b85aa431cca41e2295bfa746575e28dd2313d4b9db5c13ed3a8e0d30636 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_alerts_api.py` | text | 26839 | a9a15edadbba7c71e8797bd8581109dbd1934b850c1d27797abdbd1d5d73e9c0 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_alerts_flow_mcp.py` | text | 12839 | 48dedbb779d0b3325d085ac7422753d9a1b9a60f08b17ed11afc1b34ffc00ed2 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_alerts_formatting.py` | text | 5524 | 01617944efcc2c3ad3d21cd0f99a618a02f1412e5b29630147f410ff34380c94 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_alerts_routing.py` | text | 13105 | 2857239b4ba64188144a8b9050597f95aca5c529a25daf151947487cfa2be7a4 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_alerts_webhooks.py` | text | 18032 | 07ccccc2e2c21fac8d403d1bb0cf0899e7f8aff8ccc63e53f1b4d1408766df34 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_aliceblue_bse_history.py` | text | 3723 | 1d646d0863cef0d2b355edead5ab09c6e968635a5e2132afd6db1be7c2d50572 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_aliceblue_error_codes.py` | text | 2151 | f0454a2c0b9856abf46178f4c0901562cd59da3bf5c268f9601b657d73a4797f | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_aliceblue_holdings.py` | text | 3429 | ac22c99c30faed5c0dab59406cf3c9b2c9824ec36b693c75fa63073da41c6a75 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_aliceblue_index_history.py` | text | 3906 | fe99fa0d543f0cb339bed5a6da370c9274abfc471c509df1381d1a8654164879 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_aliceblue_leaks.py` | text | 5113 | 9b744988544590ac6891812b2e68d19f712e0e126dbb15ade5934035985d604c | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_aliceblue_order_adapter.py` | text | 4724 | 613d3793fe14c040baaad4b919b94ee8b397a69dd6c99dc5e52ad0cb5da53f75 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_aliceblue_order_types.py` | text | 4027 | db3cd2d2fce2a1eefa142eab1e37cbefa23331f53ad3976c9a7462a6239f862d | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_aliceblue_quote_feed.py` | text | 6173 | ddeb0df6958504ff55988afaea132f6e0f4ab8fde3f131032974b79f5b0dc9f3 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_aliceblue_rate_limit.py` | text | 3663 | 75bd6600cf98d39ff3f747a17a6da51d2aceaac30cfa4447edb66a6a256cc486 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_aliceblue_token_format.py` | text | 3496 | 09350204b59f373e23f12613308adcc383778e57cc1b21d34499af5e4176befe | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_aliceblue_ws_reuse.py` | text | 4963 | b8f7570489a524dda529b12574194d48ada4b24e4287ea2d33447f2fd7d685aa | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_all_order_types_execution.py` | text | 7156 | 1d03b5234a0f457a3f5ed5d54a79ef8b0fc18757417c3eacc8f05a629ce5487d | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_analyzer_toggle_restriction.py` | text | 2564 | 46d799ab85b620463db6f62fb631433c14837a6c6cbdfbaba5eafdce1c082f68 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_angel_ambiguous_order_reconciliation.py` | text | 6078 | fa2ce39f7167f2bc1583f00e8d1fbc3f914b7ef38f3261002a46b79c5efe9dc0 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_angel_holdings_mapping.py` | text | 3331 | 8ecb4c51e7a1051ee5e7ab1d19e25438b43c1242f7c2928cd585025648561b7b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_angel_modify_order_mapping.py` | text | 1498 | 0a5ecbaf80f2dd23d8c52de742c7256f2c8ccdbe7171e0ab14b4ad191fbcbfc0 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_angel_quote_feed.py` | text | 7326 | 1499be57f3c65a32ce6e2d47a6871fa1361a1ae246a2d8679838db07c045db69 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_apikey_session_owner.py` | text | 5116 | 18e4cd5b36afff0bc1d489b6a005249fbfdfcf3cc00d052c6d4e22bc325bd2fe | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_approve_orders.py` | text | 3285 | d540de4e13cfa9575252e6bfc9af545b744a386b96e35074d2caa0c08ffc7204 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_auth_cache_race.py` | text | 6574 | b903cba5438ce3e979cfe6b3a84426f07ed0c130d93f256ad61cb46ed0fa9559 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_auth_logout.py` | text | 3832 | 0223c5ca191e041f21bd21bad45bc121a7ba44bc79c8fe714c13819c6a1fd790 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_auth_resume.py` | text | 7395 | 749a534c4612860ce7aeff7a8b6065067bf3dfe6425301ccae16cebc19cd9fb4 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_auth_session_hygiene.py` | text | 5582 | a7fa1395092a3bdef6c42959137a50762a6f8f9e0a92311f03ef7bd8a6054da6 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_auth_upsert_multisession.py` | text | 4376 | 194428cc8ebf992dc85fabc214bc10c38a073ecb9b38d6bca620846c3a2a7846 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_bot_web.py` | text | 1284 | f78fd289d2634496b51272a60d403fe67d679c1a92aadee511bdedcc26a73218 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_broadcast_save.py` | text | 817 | 8954924ad58a09becc434730c6d72c1360009db87db8412bab5872b5317a9445 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_broker.py` | text | 13463 | 74c1dbba3c3146557f8f3e58c2e6b72ed0050dd8f76e64508f48f73bec574119 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_broker_callback_logging.py` | text | 7856 | 0778fb9d3cf3f6b6d37f42ee35a259266be7b793015d3e32e7e346b5ff248f44 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_broker_credential_logging.py` | text | 2835 | 7a27f51fd6e902935004580d31f7d1601f85aca7b533fd04e6b7840275d042d9 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_broker_integration.py` | text | 33380 | 5ce3a9052513be90770481e63f8b15c6a3cde9f4c97c6511080417f02e83c1a0 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_broker_keys.py` | text | 154271 | ff871d86e594262798f2f0b5a996f556d5e16ff83d02ddc2b8f67b74eed2df9d | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_broker_protocol.py` | text | 3761 | cc37953485d75f6653f83d1b55daff9744f7e0048ff8edc859a8dec42bc52cd6 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_cache_compatibility.py` | text | 4655 | 9bef96319afb8d3debee73083f6caa01b8be0c70f2dc17728eb43602d590b2e2 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_cache_performance.py` | text | 11875 | 16eb2ab7df5e49cd9e1b84636c3a85be287aebbe1861cdf939e4370d031b2065 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_charges_api.py` | text | 19444 | 1afd1358754dad805ee0b73a095a0c416dacdcb8244beaa8f7a4edf08f6d059c | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_ci_docker_publish_policy.py` | text | 10149 | eebcc7a6c7b37203549d8678877733749de245590b1e9bf78208593574d8df5b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_clear_action_center.py` | text | 9376 | 74b24491d986aa4eb4257cbe17987757e5c4b9c0d58be11769341f6c04f0150a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_core_credential_logging.py` | text | 4288 | 231affe99d7ad77507f70dc91fa102370ef687e803c9a9b413367c9359c895e6 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_cors_config.py` | text | 11799 | 6339c00c5f8ea0b947223e37d6efbc7d7e935796053dfcb5c1a3bc2c18a38bbe | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_csrf.py` | text | 9198 | 348827294db948f5dcf358795746404e485d2bc16fc10a50017a65a99ce3fa9a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_custom_indicators_cache.py` | text | 2194 | d105486024399ca9743e508a1eedcbcdd07c822c28f02ec1e19f94f9b7dfac23 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_data_schemas_validation.py` | text | 2372 | df449c25f434f8afa27d208c5eb018af01c14a95f4d8f71701a131ed249abc97 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_definedge_quote_feed.py` | text | 8947 | 5ee9946d3a2108dfae626825744f7f2a964f44b69a1595825e5267da50fc7739 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_dhan_margin_api.py` | text | 8209 | 448d4300a73b1ad77673b17f05a43bfa38be2b950cc7a55b72ac5278a8995896 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_dhan_quote_feed.py` | text | 6702 | e1430bf330ab0744e4b60652c18d45360ec87cfbf9d4d9ff468543c70f61ef04 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_dhan_tick_size.py` | text | 3137 | 564c935b3bbd6be182fa79cbef2312b3d40cbf40e82d48d7c4f8a688d44c0994 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_email_functionality.py` | text | 6232 | 65877581e4d6e1e41edbbdf25ea61b91f24c39da994c9e06662671322515da62 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_email_functionality_pytest.py` | text | 4044 | c223df1128088efd2b85fe07c4f08abb2efa11fd117e8f6207337723d592456b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_event_bus_bounded.py` | text | 5058 | 52313f8a93325c564a4dbcacfd55163e261228696958ce916bbe64bb0617574a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_eventlet_cross_thread_locks.py` | text | 28121 | 95feadf6e901ede811a6332ce79bf451c230347ce7597eeb30489a4ce828d21b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_fernet_salt_warning.py` | text | 3905 | 112f46e28c0a915b9753d347ba9ff5efbe3b04f46d24192916e0e9142da51204 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_firstock_batch_subscriptions.py` | text | 2456 | ccfaf6bfd9130d3d5c0a2d248db87134dd627eca52df2f3fe5139e19de9671a3 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_fivepaisa_quote_feed.py` | text | 7545 | 492a29eacaaed4b5b36ff14f10279d57be5bf789f321b8479c12a9bef31dcddd | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_fivepaisaxts_health_check.py` | text | 4157 | 94c45512fc00289ae7b048cfafd3313e8c217dec3b23f46aef092661ff55e708 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_flattrade_collateral.py` | text | 3779 | d49998ef5329e48ebf68b5029a554c93c7e199189ce6231529040d03622e7da1 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_flattrade_data_silence_watchdog.py` | text | 8379 | 0d5f10029031ff8ee70ba20047b3fa456b203efa06cab07ca0d79bfa0cfb9917 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_flattrade_issue_1806.py` | text | 39095 | b17531c5fd0ed7447bebe0ba3e63121e67eaafff47f5bd9dbd8ff6841d623835 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_flattrade_issue_1965.py` | text | 15815 | 0188f6df0af3c54b9c94f3c2bbb47867e36bbe5b5662c01cc31aaa4ccbd55fcd | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_flattrade_issue_2205.py` | text | 3782 | f121593d2a1b0989fe63442cdb156d4bb2645c9f89aefae5257ea164fd4ae811 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_flattrade_issue_2324.py` | text | 8528 | a1b8001c2ac506459bda56c8b3ad367e41bd131724bd6e88548d247c5abfe667 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_flattrade_issue_2464.py` | text | 4480 | cd986ff44c242dd8f5583322f5ba95402465bf180956676f03a120e30027e54d | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_flattrade_preopen_history.py` | text | 6106 | 32418234b1520e2fef0e6be08c8a8b1ed06e5cfcec206b7e5adf210392006ec7 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_flattrade_protocol.py` | text | 3953 | c0fffd26a168db1309bd6b6e73db75f2cfc3eb9666cef8ae1ec9d661b9ae3395 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_flow_custom_legs.py` | text | 27459 | 45537421ad1458faee5683827e68c09f9c38f1c7acd00c26cf5994c396900ddb | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_flow_default_product.py` | text | 14179 | 971dc37a0a4518290cf760b06c79d9e8e0a54cbfae4ebea40a20d93e34bd191a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_flow_final_fix.py` | text | 24248 | 755146e143650ae1c77e0028de79b7813003dcbe5d19ee40c214193e01695e52 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_flow_lifecycle_guards.py` | text | 4961 | 4daf15862a9c128a4b60a7b0a4f5edcde2ab8b0ed722b03c328363893bba9d4d | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_flow_market_hours.py` | text | 7539 | 6af3e06432d06b5a1d1cd1cfd4d85468e3d0c5ffe057e0ecfd6738f74633ddcc | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_flow_mcx_options.py` | text | 9125 | 6334638cedf9d4792afdf69509ffa98cd6acf9e006d22081d55c5ef4211f2702 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_flow_qa_regressions.py` | text | 76709 | 73c645ac3ace40609c90d6aa47dc71691862898b74755925f5da19a504d091ec | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_flow_scheduler_resilience.py` | text | 21013 | 0c61ae6d21151ec4176b89fbb61eb451dce936777108a6972c6d94c622403018 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_flow_webhook_payload.py` | text | 2668 | 6da40cb847ddd293cc0650761de414c9a80353e902d7555a4411d4cc58d97274 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_flow_webhook_rate_limit.py` | text | 8591 | 3d8ba416276820fd17f326cc091c9273deb8e19f133dac4f426e6fd24756dd70 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_flow_workflow_validator.py` | text | 55789 | 733a14d0a0f78a4fd5373df7ddfe4ee943e3f3ad6615d5bf53d4f337926d1eb4 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_fyers_history_chunks.py` | text | 2565 | 5c635baf6770788f8740f17f9547594b3a3b79a5ef77f16652c058538af53633 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_fyers_hsm_price_precision.py` | text | 4876 | c9605349ddf08e545e2b2f2ae50680af8b9e962c972d15da4a06a93a84e0a69e | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_fyers_hsm_update_merge.py` | text | 8668 | 056d29d3dc4334dc92c1da5528e834b0e576206da67c721d27b669495420a476 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_fyers_index_hsm_mapping.py` | text | 7939 | f69a0b86cdb2b66e5616bfb27974a6e312d27cad03c790301b8967e36c9a4ca6 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_fyers_master_contract_guard.py` | text | 3459 | 9ba96893ee3c5eaa4387bcaca7a038aa19a0c29be0e82ca4b0b47ab0e48a03d2 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_fyers_quote_feed.py` | text | 18852 | 36386f1f3ccc9c0c90c44621456ef16af07d90446e03cf942c8d5d0ebd9beb8c | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_graceful_shutdown.py` | text | 15694 | b51312b5d9cb069635059ec69e62fab35372f5f6ec00531e8f4a6beecc56b06b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_greeks_live.py` | text | 7782 | 3e834455d18298c103132635c33852a0b856fded4fce2ec8facaefd5b75617ce | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_groww_holdings_mapping.py` | text | 3305 | f4598a5d42a3758fefbc717ff60e010fe01888e70559764193e87019927aec89 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_groww_order_adapter.py` | text | 9388 | f6269144c221a015c1ac8e6f074c3bc7c0b6331417074437173cf7d32766ff61 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_groww_positions_price.py` | text | 4113 | d74a370f5cc82a865656f3b1ad0bdd977155c3f8440a9ecec8e99f43c9df7577 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_groww_quote_feed.py` | text | 4305 | ab2d518b519bce73629d8ea2d906480523a5a5050faffa35ae1c0744651bbd35 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_groww_rate_limiter.py` | text | 3713 | 846d6342554fe03c77e4c9d78dba423fa7e729b1d0293e7d6a6bb354e54f06cf | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_groww_review_fixes.py` | text | 5875 | 214d7c276d9992684a60fc28ad2aabc723d04140164156f6a1819a2daac4615a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_groww_tradebook_price.py` | text | 2614 | 40906ce7fe4c4f8afca6a2bf4cb53a527fdc40b6af9865c4ab7135464c469363 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_brokers_a_aliceblue_ws_pool.py` | text | 9295 | b2b43aff21a903baa62ee6e0936847d216b287c5a67867c3180f1b8db68bc1ca | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_brokers_a_deltaexchange_session.py` | text | 5206 | 1ac82445d8d01dfc36537c249b9f5a4760cd836cc02df1d456392a66339c56f7 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_brokers_a_dhan_gtt_client.py` | text | 2401 | c79b99b788ad880c468daf0648a30c10f707ee9230b11782d9625d17eb8b82f9 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_brokers_a_hdfc_snapshot.py` | text | 6672 | 74416e6524949af0cc2b04a9b9fa9473d0496f95e1626a19e2cac243a8cd8e41 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_brokers_a_imports.py` | text | 5351 | c2bdf9a9d667bfa402853f1cb27426756662d48126363f530d389ebbd6e4ab5d | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_brokers_a_position_cache.py` | text | 5422 | 184c7e6f5a16e981844741070659c32a23e9ea73e1bed9fa323cf35dd1f88645 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_brokers_a_quote_paths.py` | text | 15672 | aea1d5b848d44008f9adb9f84908a16b930d64f5a922b42ed59df84db95a27f2 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_brokers_a_rate_limit_bounds.py` | text | 18714 | d348419c4c942f78ee9a73e82d992541831f98eb13a1f147ea8cf397c5b5349b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_brokers_a_smart_orders.py` | text | 15584 | c0a5d9030e3c30bf1d04786a8dc47c10ce024a11f17b2a16e56a90ba504c4d13 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_brokers_b_eventlet_guards.py` | text | 8757 | 51a715a50dc2aef7f90be8995929920caf88bf13388cc39eb44ea3217a2ca83c | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_brokers_b_eventlet_neutrality.py` | text | 7524 | 8f81cfac58872c57854b64ce99247f14893293df331af407ef1ade0904b4f203 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_brokers_b_iifl_order_adapter_stop.py` | text | 4328 | f3f23ca7d4167984c32b3bd998e62691639d3d7ab1e6f85daf2ab4a338f3f065 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_brokers_b_iifl_order_no_replay.py` | text | 5888 | 3174236793a37dcb4498f876671a9c0a9a6b6921df9d4b86c8898d690cd4ca1f | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_brokers_b_imports.py` | text | 3950 | 9ee17d9939614e8f1f668a0f5c02ce4b7eff5051390556e2b82758155a1107d9 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_brokers_b_motilal_resubscribe.py` | text | 3596 | 3dceee3784e9ff867b46c9d1d771f04197403042e87762cfdd2d810cb665036a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_brokers_b_rate_limits.py` | text | 16612 | ebe4248ef00e6cf1087473826bf8d4991db7270706d6546366ec6b58817654c4 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_brokers_b_shared_executors.py` | text | 7961 | 9f7bbd5ac1af5ae7aec7f27aef5f6ebd4f5aa5b5b1dd7b2b93743cb35374cdc4 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_brokers_b_smart_order.py` | text | 11750 | aaab83e59071fcaca16cd9e0f9ad8c153a588e3ee0a3081545bc6ea2c3057424 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_brokers_b_ws_request_waits.py` | text | 8682 | 4247b0066549b737abbcd6b503553a9fb401ece0182e7998a087d252a1d0ef9b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_core_auth_cache.py` | text | 16816 | 112a08aa10ae7abbc6bd5dc7afe038bcd03eeb9574126d7c654d79e4597bc134 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_core_db_sessions.py` | text | 2338 | dd61df7bd653257a6b1d5cb09d7842792aabe112364608c5f4ab8fdcae8b4347 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_core_event_bus_sessions.py` | text | 6137 | 963056b3080b1cfebd8ce0aa1210b8bc9b52064d45639e7dd8fecb4f37f8cfb9 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_core_eventlet_neutral.py` | text | 6357 | f438c91710c5384db73370c73afc2332ccc45dec1d8763ad3f72e47cf8b4f8eb | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_core_health_threads.py` | text | 3336 | 7dfd1a4aaa5ece79da1be2e8afcc97d00d18b8d5913340dae2f06b2bdc2a893d | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_core_httpx.py` | text | 2616 | 1e729539a8c3e2df67256af9894f0d5f48aae34269994345f986965c478767c3 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_core_locked_cache.py` | text | 5371 | d74ee95e7f47d0c19659683f29ff2cc2ac38456db64b0ada4cec4d6f749b5368 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_core_mcp_registry.py` | text | 2070 | 3ec27f5fadc765b2deb41b1887c3600468dabcc860c195897ca3e5a034965aa6 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_core_mode_and_cache_routes.py` | text | 9473 | f834f420c5a19367bf11db94150c5a4f9fdaf0214fa7262a317c1cd0667e83b2 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_core_order_feed_lifecycle.py` | text | 8255 | 208be94b589896eb0741d60a3ff7854ee62faaedcb0b6ba3ac06b36422c384fc | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_core_pool_registry.py` | text | 2986 | d11bccdd6032406f9e3f354adc4247315bffd3a31b7325ea1771c8a32112092c | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_core_proxy_mode.py` | text | 15782 | 2ba075153d8802d0a55444c17f0e10e33bfc9dfdfb9a3ef846c1413ab7edda94 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_core_shutdown.py` | text | 3647 | 0395d57229ca889198629df690997fe712c8bafd2f36a141a0b62ad4c58c24fc | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_core_strategy_module_cache.py` | text | 6865 | 3fe7dff546bc5d1d889657013e18be55a75f7e30ba7615db6a310e4905c87462 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_core_symbol_snapshot.py` | text | 15817 | 2d3a32d16e17c6b37b46243523a566e4c3b2d24ef6f08c41707e04b0a877faf8 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_core_traffic_counters.py` | text | 4674 | dd6378ed8c2bb145d6cda0b6c92c1ebd4ed38714c5a49ad81a9d264920a186a7 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_deploy_broker_smoke.py` | text | 6134 | 2388ec4bb6bae5ce9eab346522e06e95d38f16ccb737c57390388d6055b07930 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_deploy_ci.py` | text | 4352 | 202aad6a0b5986508d3ece2b7f96a192a8018afedfe7c484eb12e8c9c4c93cc6 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_deploy_docker.py` | text | 13825 | 72a91906f62515291eaa3d37c2eb9a0eae54255f252b382bfc7cf46e13bc401d | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_deploy_env_writer.py` | text | 4189 | e5c02f9c835cd37ea50a20162bfb72e57ddcf2b935eaa9784b075882a17e4a68 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_deploy_eventlet.py` | text | 7099 | 8693a6aec0057e2895c89fe764968e107de3ecb10fe68f1cc7c41a81a651fdd1 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_deploy_gates.py` | text | 7001 | 98324d04d62a8192affd7432160028d544eb2dd383243d10dfc41a53c5a9c198 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_deploy_hooks.py` | text | 9030 | 1c8efbe6a4d6c5e4465f5e2b5fb4d7ead219545d173532c027e85f35ce97db33 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_deploy_launcher.py` | text | 14480 | 49ecd91ec5fd3ae9677e9245f6d9ee9b84eb6e54cb12100074beb9c0e898e9ce | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_deploy_runtime_report.py` | text | 9898 | e57b182eb921b4a7cb0d1d071831943083d37598770af867ce73e06952d68b0d | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_deploy_sample_env.py` | text | 2052 | 78a30136281c7ee3629443cb248629d11199459ab613bd46ad7476ab5284cccf | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_deploy_shutdown.py` | text | 11925 | 3523ea8d2dbfc391123f5139c766935e889bfc0ca2e6ae0181b11b2fb847b1db | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_deploy_switch_worker.py` | text | 24255 | 36d828e75d37f1a001c1c532afa700a59527459d6edbfdb314b315da470fb427 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_deploy_update_layouts.py` | text | 18345 | d8b3ecc7e2f14fb12af50a5f535135b481985fc022236763b06806cea2cbf873 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_feed_waits_return_early.py` | text | 18714 | 38aeff32034234d81eaca3f43282226e2ea7bde48d658c78d5baa945c23a4d31 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_foundation_cache.py` | text | 13221 | 19cadd11aab5a39dc47994493bfe550e9127bbc0977301f19f5d15dd7270997c | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_foundation_db.py` | text | 34443 | 2e6a4cd483b0c6f4046e6a653052f45373acb7a2925eced43ede91da73f7fc5d | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_foundation_lifecycle.py` | text | 11608 | ef294e9f1f7cbde305c2c169a8c06991f9a5cad1673709b925b64a5e0e628582 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_foundation_logging_fork.py` | text | 2869 | 66b8290d04ca8a1fde0a6e6bbf8b4a8848450c8a90e41ce50bf7c294fbf89a67 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_foundation_runtime.py` | text | 24528 | 73dcc44bd51374051a1179aa074425c749740bbdf37507ea5185c7a72ed341e3 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_foundation_socketio.py` | text | 4168 | 45898b007898ee550ecd23083472729bae2595949bf88dd525ee6cc55d604a31 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_foundation_threading.py` | text | 8528 | ec6b5c0aef163b7685ebe822dda2852f72f53eec5c156c5d55b13b5116a9bd34 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_historify_lifecycle.py` | text | 9698 | 421a6716d9879418e2b1852133ecc2f13389f4c2ca96856d7965ec7e64a41a8a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_historify_writes.py` | text | 4126 | 1c843d68f97f2781ad9c090daa41fe35f144030a31e696ef548e07ba47d55f5b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_hosts_chartink.py` | text | 10634 | a303ab35e1235f318c499fee2163a43d318a16fb095416aeba9ddedef6cc1c77 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_hosts_eventlet.py` | text | 5838 | 461d6c1b1aa10c59656988dff5a1545297061263ec513eb8fa4a706335e772ea | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_hosts_historify_jobs.py` | text | 6847 | 8d63ed47b99a2fd4fb5b1f5d0f208e794cdd6ca031e8231065fa27113fddab11 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_hosts_openscript.py` | text | 21977 | c15bcb1b7c954709135b7538404a9ca7852b1b6175b121b12f1bb831dd099955 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_hosts_python_config_save.py` | text | 6068 | cc4e14824d7dabb97fb4521fc784fddfde8c0bd5ce28c0cdd077aaa0fb2cf5f1 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_hosts_python_delete.py` | text | 5213 | ac7558f9782e4e59d41034839c2e08c5946d2ee84a03dd70de0d3d12b5534ac8 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_hosts_python_launch.py` | text | 6868 | 7872367163463491c06dda3750b608a4c891eca42c9c6a21b319c259b7fe2589 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_hosts_python_manual_stop.py` | text | 6649 | 042c6f74ce2284cd32ebe88275ae8ccf09f05100fc97ed9cf97f15265780c0f0 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_hosts_python_registry.py` | text | 6716 | 465e3bba94254d4494d84b78a9ca04ac3967c9022df84d01290c77b88e0648ea | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_hosts_python_restore.py` | text | 5823 | 5822441850ded52af9036cfeb69cf28c23e0e90e88ba2c3a99f8ef0bbe4d012a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_hosts_python_sse.py` | text | 5659 | a4a4c44da0599f94a577059e7bc52f439f8c1ce79dde0206e284a27d020102c0 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_hosts_scheduler_jobs.py` | text | 7266 | 5e91f0a527d0b403a6c0dcbab91497c427297bc2d5d054a179c8af21db46729a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_hosts_shutdown.py` | text | 7675 | 8c6a05e3458f458e7f67fbab23a2b293aa1c282d8e83767f9cf069f58353f89a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_integration.py` | text | 17203 | d9f28272cc9235a86272874f758e198fc6a7be4c5cb9c012a5c691300adc48dc | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_integration_agent_reads.py` | text | 6392 | b00c389ebd190417239007c0b7058df4c6b29f06ccedc6e2ebd549b4b80cc688 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_memory_auth_decrypt.py` | text | 869 | 5fdcf35a5c4dda2a260d200a4137382132446161b4885aa0d8f71d60ed46cd31 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_memory_flow.py` | text | 10236 | 819a93a2b05126a8320752458c73659faf48f803eb0edc306df2365908bae55a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_memory_order_updates.py` | text | 4003 | 135962be0e3030df7af1705f1a3d29a8c5fdc29a85dbd7e3d772bdffb6a7bceb | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_memory_streaming.py` | text | 8659 | 0a2adbb620e9773f43205bec713003f7a9fae233f356c43015bb920d4e0243e8 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_messaging_agent.py` | text | 10694 | e4193fa59988f0d99b88a4509f7fb7ce9873a4837fee04a6f6f50d431253df75 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_messaging_email.py` | text | 5780 | 4fadad72725c256df773c43badb2c677d158fc261421f7d799262640fe40ec0b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_messaging_eventlet.py` | text | 12250 | 69a8226a31bba7089b780348834f71f47cdef7818ca5a8ece3afd6ad42acedb4 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_messaging_guards.py` | text | 6553 | 7093669799f70bdc0a9a5f1f055572ae511c1d03069dfd9e59015923da84b368 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_messaging_mcp.py` | text | 23130 | 10306616002d8b70f02f1aa2887d592183036877c1136e5ca536b19efd281475 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_messaging_telegram.py` | text | 16124 | b5c5ebe5ed19bc5af379d9aeb7f4fe7862283b426b5459cc36dbdcab9982102f | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_messaging_whatsapp.py` | text | 32519 | d55c267140f27542af58cb5dd946e1a1a567ffe35848bca512d108d1c6660a43 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_rest_broker_busy.py` | text | 14395 | 1591af5852f9bb35ee2daf0cd0c1bf6d0f2f0ceb09407dda799967f4ac5bfa8d | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_rest_env_write.py` | text | 10822 | 26ee0dff9e7bc9d2e03bc3a0ace46ef6790ec24ac23b4e50c2f9ec7e2330695f | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_rest_history_limiter.py` | text | 10426 | 5714476a77a0af89c12f9ef32441ce026714f9380717dcf3746675449434f8c1 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_rest_oi_profile_deadline.py` | text | 9181 | 030437a5c68af5ea559de222262d3944138b683a793378c8b2574324e44b5666 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_rest_strikes_cache.py` | text | 12812 | 527c5c4e8e71d21420d49250f2280f880f350c69cc4f0354805494b7d7ab1d76 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_review_action_center.py` | text | 11565 | 93efa7d8d335c9054551abebd8b36760910c2affe7556301261c8431cfdeb659 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_review_brokers.py` | text | 14687 | 2ecb8ea557aeae572b5cdd46cf5ee769f861d8665f568892f90189baa2eb1e80 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_review_core.py` | text | 2169 | 938c8cf0997c2271b11b10f1b408c118b4091d5356ff4c10eeed0cd36306a058 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_review_deploy.py` | text | 12882 | 19f775e371b5931ebec926efb8c6e3f5a9ae1314f01c686d0df89c2b733317b6 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_review_eventlet.py` | text | 6734 | 5c21722382127aca706b0fed7dbe9f13b1ea195838778ca6a22c18079a7bd92d | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_review_flow.py` | text | 8266 | de2ca21c430d311ca4a4a4904b9c9531b5541e4bfa4b4fa79517ebba9b1f8ed2 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_review_funds_cas_cleanup.py` | text | 2354 | f492671eeb28055ee1d41a6f1451e5a27ab3adb79bc53e1537e7abeb2ec68049 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_review_hosts.py` | text | 11422 | 47a9339b953a455042f5c3b691e9bdb539dcbf9d5448e4453eca11af9981ff82 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_review_messaging.py` | text | 3091 | aef57cc8a68951dca95ab94be5f0c0611f89fcec798c6d93c1cf377eedbd48de | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_review_sandbox.py` | text | 10228 | ce5857f4906df837f9ebfbd389fbe95fb02fa67900926ee6bf0359f5bd08c85a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_review_strategy.py` | text | 9143 | 25132048fdf3bb01c31e9e82af5ce294edfbd0536eae6d8e66f3387ca930d358 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_sandbox_charges.py` | text | 21117 | 40e9209733d4ca12ee21076b9d1afdcc1f6f05448a336fdbb207282bf18abb52 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_sandbox_eventlet.py` | text | 11632 | ce2db9cc4146c4c750ec60940e18cc7d7ec99e7d17eedf0f869b394cb2124b62 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_sandbox_fills.py` | text | 10238 | 9302e646b6621f97b49d57d25be7c2d4f8953a307dbc723aeaaa1fd0f991a98c | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_sandbox_funds.py` | text | 9243 | d5b62024ec66226af0248035b9099a0d7924c17784517f41d00aa4d947811088 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_sandbox_lifecycle.py` | text | 18296 | 9bfc23cd9ff6969fb9563dc18917552dc97d9a28715a0c4e4fc06d7bd510341f | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_sandbox_order_ids.py` | text | 4386 | 1bafa60b29e649e7447d82bfac29dd1e2896d5357a7a8d55e639a1bf8abcf181 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_sandbox_orders.py` | text | 8378 | 5e1d6131fe2d5c2233a6cb04588afc38b553484ab32d36bab2d464a3ce007760 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_sandbox_place_margin.py` | text | 5675 | 20deeae3a84515f5abbd7990f56d634b6afe375d0324709148389311380f7a83 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_sandbox_positions.py` | text | 8122 | cab592502bd7a45ae395b533f9685698a2608c03d23d851c18d82e4d978a2c27 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_sandbox_settings.py` | text | 7254 | 32ec055c103c308e1ce71cee93be435fa3fdc875d07722b35ebe141f5d90515a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_sandbox_settlement.py` | text | 10264 | 10187cb8530661cb33fdc4fd85b837f8b19aec66f0394ba790f7e529802dd989 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_sandbox_squareoff.py` | text | 8111 | 8c4d621604691a6890517e1ba8cfe1bb75a26c670f8a0ff41c0745562e4743db | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_sandbox_support.py` | text | 10796 | cac259b15e3c3ea491d6a120994a600758cdbaa18ecdd308e33c329699d046ba | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_strategy_action_center.py` | text | 13100 | dd10fb6e6ebee072660fbfd447af66cc9dacdc9dd942b0d9c0cf5ab3c99976e3 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_strategy_agent_dispatch.py` | text | 8147 | c27a11b895bfe4a40c170ac51fbb2c25a42dad5efd2c0c58b72fbf412ff38b79 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_strategy_busy.py` | text | 7240 | 7b8e960595dca718110df3605ee0c978f03c32eaf39f674aadaad9d07af5057a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_strategy_docs.py` | text | 2760 | 147c3f5d27597cae151b1a002e83faec1a6cf369b5618441136044c7b075c310 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_strategy_emit.py` | text | 7100 | c17dc9493bc60ad53dfb3c633effdb0f7c595ae2acd985b0b1ba67ff9a234011 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_strategy_flow_waits.py` | text | 7306 | 9d04c96815c143b88e3f2321a78b54bc721271d32b351fd96708e0883b58a050 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_strategy_order_events.py` | text | 10452 | ce726ddbbe48c9b91fc234b0b0a2893c4e570bec1ead6ee886fbf22c1a751879 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_strategy_scalping_monitor.py` | text | 12938 | 8507a0134d8454753506f95d061cf76b8b658d70ae4b4dfc90fd0822ace6725b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_strategy_signals.py` | text | 7525 | 16cb1b2ece847ce69bdac11f6f52931fedf99b80cfcc4e943b5278bcb5ee156d | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_strategy_webhook.py` | text | 2698 | 61ddce82b1c5d593c0d4bbc1ad02886ce3278986915786cb9e7d2e0a1d2590ca | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_strategy_ws_client.py` | text | 14772 | 61f07180a133e81cf927f41f5331fd40264c02331b1067d8fd1b9f24ae3ea952 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_gthread_suite_sleep_isolation.py` | text | 3316 | 801c87b5c261b74b9245f457127d257605e355c4ceff48a9af3ed124e51c8338 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_hdfcsky_quote_feed.py` | text | 12985 | 7e203f9405dcad19d03f9094faa5bd1cb47beee89dd9fcdb861391b7d114d3f5 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_historify_custom_timeframes.py` | text | 2853 | 10d5e1c82bce9f533da2973a113aba1f89e5f902052ef0910da3f78f4a04f6e2 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_historify_id_sequences.py` | text | 8011 | 8026aecba5983423d032c9dc9de83a3e1b530a775a62438be07fea46fd3b9294 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_historify_symbol_resolution.py` | text | 6088 | cd497e4e5d520a1541df126cbd8a3c7508b4080609e48201509337271e3ea203 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_history_format.py` | text | 3078 | db80f70a98cae4a3ef6bad898fede8f1418aa6b0e3526d1d1d558b63e029b346 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_history_service_source_validation.py` | text | 3260 | 70778480814741f074d397d90a12a2bd98b5f736a262fe80dec4badf8e187ab5 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_http_protocol.py` | text | 4754 | fe2a78398e87275d3b9069cf210b1438c17be90caf19b65d6c76d754919a45da | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_ibulls_market_protection.py` | text | 14072 | 9130db9891378aed85fd3fd2d5016183d8641f9ce38912e57b806888ce9a74a7 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_index_symbols.py` | text | 20059 | 82cc18b5d4db2b39113e3099eb09b2178e907b6853bb7c3f14888a5858a48307 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_installer_failure_routing.py` | text | 6449 | e7ba6415905a7ec4dfb19678d2334bfe3379e53664eae84e3fefadc1e042aafa | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_installer_worker_and_memory.py` | text | 26324 | 1ee7974d83265f68547abedb0b74eba13225123291f716347a2cb63f844e5ce7 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_instruments_from_symbol_cache.py` | text | 4396 | 712637c92d386fd638d10cf92cb32f9a5faafcc3fecf552726903ac113a1443d | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_kotak_auth_token_format.py` | text | 5871 | 26da4b106dce147063ac01493346d0149b207be6f4a24f69b4f21e950ebff238 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_kotak_cds_strike_scale.py` | text | 3347 | 0f450d7a75f5ea54fd4c0c466ef3ad972cd090418fbeb78da1c31b1ff3004bd2 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_kotak_depth_contract.py` | text | 5543 | 3a0897ab762ff0421112ac0f401c57adaa8ce21dbb15fc97d429bd228a08288c | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_kotak_hsm_decoding.py` | text | 4365 | 9e6b22fbe4fd46df2134b9ecb308de8bd54db562b5354d062ed49987c12794d6 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_kotak_index_depth_tick.py` | text | 7610 | 6653983e86b97e6bc415442bbc3bcf196808da846fb1896a8f9704ac24bc6715 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_kotak_index_feed_subscription.py` | text | 5883 | a19bb5c44db7c4a448f32a84b48d3d288dc807867811a54541e4eb87c55abbc1 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_kotak_master_contract_guard.py` | text | 5178 | 03f1b4d5609754ee0b9c677bff8d4ea70a9b92d8b3b804f7a8bd514a6408c4d8 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_kotak_non_expiring_rows.py` | text | 2869 | fb1d2e706ba76f0df51422cb24af9297dd3c2129f20c5b31442967756761c596 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_kotak_order_tag.py` | text | 2076 | da1b9e7733b7b96fb2befea288a6a50e481a552e3acfd9ae8f2c798e1e03e0a9 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_kotak_positions_ltp.py` | text | 4732 | fb31640230af6fe6485bcc47bd85d42308e14ffb9605e5a6d14f2cdb4bfb0960 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_kotak_positions_pnl.py` | text | 17328 | 71f0a8cd0691122a0b367b611cab88abc8fef5b6a0f07acec77def4e08be4b05 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_kotak_quote_feed.py` | text | 12947 | 22b9c87f7bae608a76b31a60b13a8b675d73be7545df11d6ab9ffe0326690b9b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_kotak_quotes_ratelimit.py` | text | 5800 | d1f0334b05f9dec7a7d6701b63722871b3d721212390235b1bda4d0eb7dd11c3 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_kotak_sdk_2365.py` | text | 8212 | b2e6d8c95385c86a4fe71d7ec36f3bcfb5894e7fa37e7d54bc89cb5498fcd055 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_kotak_sfeed_client.py` | text | 9926 | 9e4f278605c218879afd014410eecfa4b71dba066c5755eedc9f0ab2973375b2 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_kotak_sfeed_protocol.py` | text | 12164 | 1490edd9a57219e77853fb30b954c065914e2700b3582b92f76d7c09828a57a4 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_latency_groups.py` | text | 17714 | 417c0eab3cfb1f1230c0d1fe9383ccbb5ab9a6d76843b7a5b79e5b78cb8351a6 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_log_location.py` | text | 2239 | 62db297a48416c3e961f1e22a471983e5cf6a362221bab4b83f9d2d9c5d30714 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_logging_redaction.py` | text | 9410 | ec2cdc5161a6945e445fe2a1200395876d13035c454d61c1bc4865dd71cb5368 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_logout_csrf.py` | text | 5064 | 3f7f8ce367cb2936fd9c2b4d988e6e81aa832d8f42cbdd784ea4f5e5607f6dcd | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_manual_script_collection.py` | text | 3933 | baf36a47d6dc4909422235ec8ea18ea6bb015df4f699fcc21824210f97384b39 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_margin_2156.py` | text | 15716 | 486dd6d171836fa1af2007968baca861ee69bfe684bbb64ba3d9945568dbf23d | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_market_calendar_validation.py` | text | 2245 | f1706b550838704c328738a801ec447a3a2901c7269930c06864275e216b5d41 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_master_contract_instrumenttype.py` | text | 10005 | f4d75cea75e1839cdd83d3f8b449e10f70691e31a00bf85eb7153f2f56240ed3 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_mcp_integrity.py` | text | 28464 | 585b77595d9987eee952a39eaf28995b40a1e3558f863bb864705f3e3d732a41 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_mcx_underlying_resolution.py` | text | 8236 | aafd0f38da1776abe8ee85f498669a80886e1d8851515572362e1342e2a8740c | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_migrate_agent.py` | text | 14744 | 8aa90998fdeacb5861a87ba1df7ab55773b07322331f11485e1eb360ed9ac108 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_migrate_all.py` | text | 3243 | 61b00096aad760516fa4a585318c1f3fcf1ba0244b47b5b2e778a92871606442 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_migrate_market_holidays.py` | text | 10088 | 3feaa04e5a6614e9a9c398975ad018396ffd4f7fd8212d2c4b3526daf7bd1836 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_migrate_muhurat_2026.py` | text | 9227 | 55b452aaad5130a0e8d6ec980a6d943e7f72c4b1f4d549e778c23ba3a0351180 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_migrate_qty_freeze_nov_2026.py` | text | 8182 | 093f59d1a8e0034e9eada23de9230b2d54b8d13fc7b451eccec9d58b069c6134 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_migrate_sandbox_charges.py` | text | 20999 | 535be65e885c794e9436707e66965cc40da7e505c25b86ff1bafafc69b5edb18 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_migrate_strategy_module.py` | text | 8610 | 5194896533fd8c725cd08d5ea2ece4f47e01a87e5e36d2a8067f1856a0eb4c6e | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_migration_entrypoint_contracts.py` | text | 3042 | eba44cf898005a47af6992a5c96e309dfb89c771ddeb955104ef1e24bf854314 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_mode_normalization.py` | text | 3348 | eea3031dc07960c4f341b19c7af86659f27f01d9bdbbe804d4ef489e0b636029 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_motilal_ws_reuse.py` | text | 6280 | f338116b40b9dedc166f041bfe30dfe89d9891afda869b44edcf8f4adfd3ae93 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_mpp_slab_instrument_type.py` | text | 6300 | 504b68145e12dd912393104ac6e1c6cd6cf6d293193f747fbff87dde08a0efa1 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_mpp_slab_validation.py` | text | 1792 | 31bf19fd057344e72fc150ae94209f4156d4568fbb185824b71de61c3d9ce302 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_mstock.py` | text | 1811 | 25fdf41b2f60524853c20c46b8108de2187776ed0a9a199850ecf2609a99200d | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_mstock_quote_feed.py` | text | 4450 | adc9c728c12388d666fd85a9d35e51573f8e3a469f7b21b074af1cb1100a55a4 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_mstock_websocket.py` | text | 12772 | de0e55edfb591197777fdcd71e0a48d3032c253769c5a95e33d9c7e9117ab063 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_mstock_websocket_resilience.py` | text | 27660 | bd41aa38cf223a6bbb0dea4c21736f33c4d9674d8a14e089c6e1781eb9176560 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_multi_option_greeks_api.py` | text | 7322 | 9423c2ddc3bfa8882b4c40e906c8fee97d73567b47311183b82c9c7fe486dbbf | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_multi_option_greeks_regression.py` | text | 11449 | a1ed4dfe7da405e101697e3e0572006835b5159ebbe5ae48671049e3adf77d2e | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_multisession_rollover.py` | text | 4770 | e1d7b791f811efeb64a45e8d8c8e43ea06b8c66db0e7b0d87941d618f4f5124d | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_navigation_update.py` | text | 4582 | 5b52e4ca5ca294f3f8ce0de1a01add166df2ed229e1e0264365136a20b6effcd | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_nifty_algo_analytics.py` | text | 4270 | 5824fc9f2c76ee8d3385b5b77361adb98175bfc806e082c6e0b247aba8918be7 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_analytics_integration.py` | text | 13195 | 870f5e22be67b2cd2cd6a1414330ada1163bb411a2d2b120813aa810d2de103e | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_assessment.py` | text | 4641 | 19935d83f2b1798675f3eaec55f646cf88018eed3cc72e1efdede56e54b953f2 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_calendar.py` | text | 10406 | dd608183801c6ab2ad92494a4bf8bf0aa1c4ba65f59086e26590fa7394954910 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_capture_runner.py` | text | 19946 | ffd02ddff8a99761d77321bf6b46fd1b2fa39979645c07fea7f75a300749ebff | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_comparative_completion.py` | text | 6155 | 6266801d58aef995ea72065a9a1e03390bc9c79edff19417771ce18cf2b9b79c | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_compliance.py` | text | 13238 | 6b0fdf32ca94ede67e957165560bd01d17e8e610d397e9ef8e741dae03427a04 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_core.py` | text | 8738 | 44de0f7f6034fa71bf4752d17afcd3c6b03e757163a2641c8c4a43d9c2af7dcd | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_corrective_audit.py` | text | 9487 | 03bbc90af6bf777ac31ad23d05d488785759df98816540cb605992d96d234061 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_discord.py` | text | 19355 | aab9ee8a3b58f2aa54062faa44f425664c418e112b1076c822623906feb958ac | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_execution_completion.py` | text | 20806 | 94635ba7a2570e22041abc1f763530a1c0fed4cd1bcba3ff7ed1cf6bac78044a | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_exit_studies.py` | text | 5352 | 8368917e416771acf86922d035e94d061b9c342015b28441d5a3fd3f2dc5bad0 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_experiment_api.py` | text | 9364 | 68751046858ed7f6756b261244056a83f5593dcbd1491c24ef38c47895a0c341 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_experiments.py` | text | 9975 | e9c2b927f0f29130a9a489c520d0a7c5d5e4763f0e42c7e87cbe44fa1831f472 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_foundation.py` | text | 10294 | bfa5a25c715b5935ccee8dcb597864ddb957d8cbd5ba46b3da45091f4045ac54 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_gap_p1.py` | text | 12891 | 245a770765b1fef23c8d1597edf7c6d8b3e1dbd22b64ac718a580073238fc620 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_macd_window.py` | text | 17426 | bf561ae11e424fce7e2404eac9a7ce95363250214c892958148be5c631e37faa | test | DIRECT | NOT_REVIEWED | PARTIAL: lines 1-270 read |
| `test/test_nifty_algo_native_capture.py` | text | 5502 | 290f498ab6370c9c3b2070f61577b2915e2eb460492777b996fd4fb1d360fa4a | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_native_data.py` | text | 4783 | 96b6616c5bd69cb36e1b1ccf0475d10839cbcb7a2c548734bede45fb7237f0e4 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_notification_completion.py` | text | 19019 | 6254bb5977b4c4494c0d8f2430e39f412dc5b49237af5c58e888cfa191e5712d | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_notification_outbox.py` | text | 9675 | bc2169670c64cde7405976dd62fdef945ef622261187fff4ab05eb6d5742bb3a | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_offline_acceptance.py` | text | 89661 | e7af3697ebef6591466e205a5cf8a6c91b19561f6b12f29435af54f7238de5f8 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_paper_executor.py` | text | 12267 | 0553322926c66c076d82d2f67c74d365bd2225ec6e1c2fe570130ea18f538bb2 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_phase1.py` | text | 26781 | 48684b1131528e1753116a6e71fa5aff46b8e30054f163c60c85fb0b55621225 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_phase2.py` | text | 13868 | 888b37f70c8266a0d8bff9bc7393d9e8655838153ffdc5acbb24c731a4c3d8bc | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_phase3b.py` | text | 11957 | 2ff62d56c385c019b19b8bdc5fef6f774261aa5ba3387504bdeb730f5ca6022c | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_phase4.py` | text | 28030 | 03ac81d4ed7f53c2c00d91c38e37ec8ecbf84034e8fc4a06942b16d3ce120c96 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_phase5.py` | text | 28202 | 0e0c7921fb2d68aa5b8dd989f53c405314b43bf69b9f515be36d142c036de0c3 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_phase6.py` | text | 42772 | dd509fb0bc99ff443adaa452001265c7ac5ba9edc22a0a4c95228e889421cb2e | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_pipeline.py` | text | 18139 | 8c8207d1f76d4c53b8a0b114e10122e86d3fab8e45d4ab4e6b285867fb971365 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_recording.py` | text | 26558 | 76f09175f6fab928d65513bfe9243c7a775229515d55df888db061e8560ff997 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_recording_api.py` | text | 12455 | 2282651379ec90b0be8ce7257aaf18386db118452bdde44aad4bce3ae12af186 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_recording_replay.py` | text | 7500 | a385c332c67ed51c0b3f97cc314b3536b6b1e05f96574f3000611461a5826dcd | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_replay_lab.py` | text | 5805 | b896355726d16fb520eed159e2d61c5898f6ed007ddc1445ba6269ff6408d357 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_research.py` | text | 6600 | 330a62b4c8f07b5edbe84ca1f4627462c6c74cab83a5fae959a0938a8fe4519a | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_safety_center.py` | text | 17882 | 31b22ce092c373cbc45491e02d63db023a20c68e8968041563676805a712c02b | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_sdk_241_parity.py` | text | 38882 | 197e87a4036b31d61ee7e146a4925da686bcc270da5865e80f14a3446cb1531b | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_secret_rotation.py` | text | 8145 | 045e15c802a808e4f8835c54573ecdd2eb24cada5a42b29ea7a55b059ba1840b | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_selector.py` | text | 5390 | 0acec0516d60e161f5d581fcdf96184b1a90a44d70de2ecf36ae72b5a6444108 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_selector_integration.py` | text | 10186 | 03a330043005572914cf9c5fac6bb64074f0d28d8e8254e809d821f79e79a518 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_strategy_integration.py` | text | 18336 | c1e341021b45289d9dd908fa8b95633eaa6aa502c5ecc63c03a9580a13830959 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_v2.py` | text | 24778 | d44e06e82425eadb22258424477665762b0d004736f11663ff8de5229fd41988 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_nifty_algo_weighted_selector.py` | text | 3928 | d4048129937f6e634acff7d8eb3c6ffbb02935a291536c40955efbdf9adb6e15 | test | DIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `test/test_openscript_bar_timing.py` | text | 10178 | e72f5a91981cef14288960e92de135d1d70927e2c623fd687f693add94678b0c | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_openscript_book_shapes.py` | text | 11416 | fb446953dddec75e451f0a65c60608698571a4d5d3de53d88015261b6f4573ca | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_openscript_books.py` | text | 11392 | 0c1810b8c476b4ebc4b8ffb648262bce1640ac89d0442c9ec73bb2ecd1634af5 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_openscript_child.py` | text | 48868 | c6457c506f8c0a0e6b065d7b6ebd74c5d32c75f189e84971a25ea5f45d221894 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_openscript_deployments.py` | text | 15186 | f0d66e2e0085f30e98e9ebab60d8799bc30e1d980ae6ad9e283f44bd907a018e | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_openscript_engine_reads.py` | text | 18068 | cc2058ce650c1bf9231840f0630ba543b3f4eafed35cedaa2a072c58c1ae5281 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_openscript_instrument_facts.py` | text | 18654 | 330c31b5c73b9aa700aeb4419af9a7542ccfa848faf31567b568baf723540cde | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_openscript_live_bars.py` | text | 19950 | a12b656ffab5f99fdfd30ec35f2686a45e465a0b9fc5d208d514580aafb8651b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_openscript_order_batching.py` | text | 9881 | 560f61610c90dd54408ef7f4f379396a02fcb0a32b526cb1ca64555af8e223cc | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_openscript_parameters.py` | text | 9623 | 2df25a48a5c2ac6dbfec2ccce40a936b4d1960fe257bd5697a02400cda691f01 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_openscript_pause_and_stop.py` | text | 22054 | 8e7c03854fa42f3b375fc11c7305b409e3419bf664d2afc888779205558266c3 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_openscript_resume.py` | text | 11317 | 13ea8ae58d2c3469a86267284c2beb2f1cf14292e47f5a42ff8baef94ada9780 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_openscript_routing.py` | text | 4241 | 91c197c11cd91eda2620aa1411778821d44f934342fdd7234074e8f9eae851b3 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_openscript_runner.py` | text | 77424 | 77c750addfd0f8c0dac318281d3f9ee424372ec3a528a2d5545493968bb12e2d | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_openscript_runner_facts.py` | text | 44810 | f5b8b6baf990bdfe9fa13a542278d03ad5c12c3ec63e5a50281f58c44c0a2a1a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_openscript_runner_routes.py` | text | 59620 | f8cb84367cee73c9fb8735711409bf3351719158b5b7ffc5ba7664e8eb46088f | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_openscript_seam.py` | text | 39156 | 89058fb9febaece145d31bd7ad8a81c19aaa68c3db4af87c1f03d3aa3aba4de9 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_openscript_shutdown_interrupt.py` | text | 8776 | 01f38aed00af33d278873770c84fcf20a00def350bb4feb862d580e190c92ce7 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_openscript_sources.py` | text | 29555 | ee19f4415726bcb73e0e3ccaf28b267cec6b3ed424ec47faecab2b8a5157cec7 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_option_expiry_timezone_contract.py` | text | 5358 | 27cd70f861eb879d40338056eef542a71b6e45db7276c310f60c7af36bfed8ac | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_option_greeks_api.py` | text | 12912 | 286229c369c41fa20ebfadc05668555bba3ec3921af0d00394282d1931ae48d7 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_option_symbol_api.py` | text | 7121 | 129a6a11787afd60f9c67224c98d1cce6fee0e111851f08eed67fd803945b8bf | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_option_symbol_service_validation.py` | text | 14212 | 79dccfd0a61bef53762ec3623eae73098ac8422f95ff571e661ad8779d6a2fb9 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_options_multiorder_api.py` | text | 16595 | 426d60472635055da11b496461ca208b4b0df50c9ace2c1043d64a241aa59f18 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_options_order_api.py` | text | 10143 | 46fa094820a682dc9c4822513e2a811215997af71881159d15892f3425627477 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_order_adapter_auth_rejection.py` | text | 3413 | 16ffdbc2598926b42b7ce393234c8d2a9c4493b331073940dccf8731daf34b55 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_order_update_adapters.py` | text | 36558 | d1654211f9cbb10e6c7d4903411f53d83a2eb1e0b82b4c172087617e064a9a1c | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_orphaned_apikey.py` | text | 7982 | b89fd26b3d6404ad8e3e0824d8962c0e5631688fc9a3b7cf97617a5d86d4bb47 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_password_reset_grants.py` | text | 18535 | d0773924c40330357d08442bf316f91b8a1a5debf417267e1786131c9ffe8042 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_paytm_cancel_order_errors.py` | text | 3024 | a017d2a0af56b0bce804509ffc29fbbcbfe47893061eb1a5a7975ba448c6ff79 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_paytm_stop_loss_orders.py` | text | 6385 | c1edd125254a13e4b314b5acc2ee9ddbde17c527e27312cee4ca7228de5e831a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_pending_order_execution_service.py` | text | 11271 | ef587e210834f3657383f2d6942e8ec5b13a8981ce333b51bf7c8227825c462e | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_pocketful_account.py` | text | 32849 | 62bb7ce2ab4089f3a39223b1cdedfb5c437c0addfa12aab50398f2d012567e65 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_pocketful_adapter_batch_watchdog.py` | text | 4462 | 58de3fb655c81966aec0f5b1de496d724249f1f826fb2d5edd12ad5ceba84311 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_pocketful_auth.py` | text | 18839 | 13176de06ab8b77c77aa8e18428b25779a2dd68d92b529b971fa0a0e22f0fe1a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_pocketful_baseurl.py` | text | 3275 | 35703c013d25e949b01eca13fb70c170d8c66cf31fb384ba30c484038b1e905d | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_pocketful_data.py` | text | 31530 | 5fd4b9a6dd80b323bbbccf951d0dbae4d69ca527db1fa3c7ede5f88290d2754f | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_pocketful_master_contract.py` | text | 23837 | a469d33ad1bdf82d9b11f070152f8bea1556bdb9a2539197f13b531233354a1f | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_pocketful_order_updates.py` | text | 18550 | 50caab4226286d39d510d2eca3f5a1e87ef0b7ebf70c28d104b9ea56ecb15193 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_pocketful_orders.py` | text | 46357 | 1a906e99b8a3d6a44c2c4c0aff93d60ac35dca31bfe50ba6f77f7eb03dc6f135 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_pocketful_streaming.py` | text | 25328 | 666654f4a9478a7002d126023b60647c1417d46e324a9c985d3b19709877eff4 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_portfolio_api.py` | text | 6523 | 5872bbd0c45dfa12073cbbffe9d0bf0f1f8172ac60e98da8b5e899aeded9c47c | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_portfolio_engine.py` | text | 53208 | 3a452e1b0b42dc24b9dddb71f7a6c60d4c05baaa63f86e047a1306573903af89 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_portfolio_service.py` | text | 5978 | 78c77c8dd8b393118103aeced771af8fa9c75f3ab44544929fa5ad7eb268f317 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_position_read_failure.py` | text | 50482 | 6c3da5cf698fbea2135b84d74f33c73274d1b7619b5f946a2da82b1ab8369144 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_postback_sender_check.py` | text | 7935 | a1aefde97957c6422e9be037336cf3808a6d2d492739498b67ae3a1487f9ad49 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_precompress_assets.py` | text | 7392 | 4a6de7fd85549831e8900ac3b68d8eabb4cbb51ccc70cc8651bcf91ea66f9563 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_pytest_import_resolution.py` | text | 2366 | 03eb4445255aaaece41254dbc8a64184347d53662587276fb9305dfd996d3a65 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_python_editor.py` | text | 5625 | c0b710bfe6b3f59ccf1f7e447d5b23aa2e03b4404e9633b229fd0059cc8a0fb3 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_python_strategy_crypto_24x7.py` | text | 8233 | 55b9a2d1dd286d62f7d5a52cd8e28f8acacd63cf7b03444c4e997479cde1738d | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_python_strategy_edge_cases.py` | text | 29701 | b6421398ec78007636bfb20b090dded634d57cd0d1a8a74df4e533559dff6732 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_python_strategy_exchange_aware.py` | text | 12140 | affbd664c0cd09cc532d7d1066087ae69d1288a6de428023b6970d182d30b8f5 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_python_strategy_stop_lock.py` | text | 17925 | 9290fdbf83d6d12fbb66a9a9b49d5a7f84f9966b367c2630ec6ba1b321651e17 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_qty_freeze_unknown_default.py` | text | 4414 | fefda47033c0679527982bf73c7dbc07809cfeaea3472419576fdffe017d5197 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_rate_limits_mock.py` | text | 8554 | de3962aa6427476081ac7ffe85cc6ffa036e7b688cdae5e7fd822dfff178719c | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_rate_limits_simple.py` | text | 8601 | dc3813fb2ba97ab30f22c3fe873bfe712cefef950cb3ae180543fed94d13baf4 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_requirements_parity.py` | text | 2868 | 961ab09cd65dc3c785350e82b1b375a9112c84551ba7a800014483bc3dd9c040 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_reset_host_poisoning.py` | text | 5319 | f09fd0e69aef2576064b121571b5d9592fcfa3b2bd853cc1f0b7317a5f4a37be | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_rmoney_adapter_batch_subscriptions.py` | text | 7789 | 0402bdea49cb7a532ebbc25a0ed4637237b2265b20d138459dff4fe4041bed2a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_rmoney_open_position.py` | text | 3889 | 0820b6aa4dc9e52d0d40d2a287c72aaac3cd8c12bb42e1ce4bb604d841cc43d1 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_rotate_pepper_salt.py` | text | 4478 | 87e812e7af6e3e753953ad39ddd67fd540db60048feb3fef2c46658ed2f810a4 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_rupeezy_broker.py` | text | 54211 | 4e0dd38a3a9d2637167563866266d6489fde6fe9c4dcf3f53b74546ef35688c5 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_sahi_auth.py` | text | 4333 | 6859e7506458dbac0d19501c0efbc769b282c0e7008851e073d204838194ffc5 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_sahi_order_adapter.py` | text | 6607 | 5659b2a58a67e0360fb01a0ec543a076877fa2e5f06d0d5975f930d8d6150403 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_sahi_rest_mapping.py` | text | 10698 | f87435744178a5b904005e00dde97ef307894521fb219bf3bd39893265f4bbbb | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_sahi_streaming_codec.py` | text | 23153 | 1a55932ed63c40f802d766f84b601d320469cfbd0a389455e391342d7e077724 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_samco_quote_feed.py` | text | 7428 | 6460122c254b3b28b2a22eaf2da27d5bc76872285af17818b3c33a6b2e49adf7 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_sandbox_charges_api.py` | text | 35690 | 1b5a52b3ffdf3c7b7f5562ca5ea93c02afb38af8e6c5c46641fc7a3813b272b5 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_sandbox_pnl_snapshot_days.py` | text | 2247 | 97cfbc905fb2750ce8e790cc6ec9a4c2058f26b1a077ffbbe10ebe4993f40b1b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_save_strategy.html` | text | 2312 | 7ebc59c6f614f6e32ea59ccb006d909db42d5ae77eb6aaf191b33af6fb15197e | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_scalping_futures_contracts.py` | text | 4197 | a89b7bf63081a108e6090a518189891b4146571a4954f08bd60421e5d2436231 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_scalping_risk_monitor.py` | text | 11799 | c8e95f5ac84036d21361a8086df36831784d03c29e29456191eef6013fa8872e | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_scheduler_session_cleanup.py` | text | 4797 | 551eccf39004c2315ed0460e1d54ef1364720e363d5821032067ce281d7f3bff | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_sector_rotation.py` | text | 11808 | 3515b73d3d0a2c4696184ef858ea6e39e99f89a7ea129edf6af2388a56496dcf | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_sector_rotation_api.py` | text | 4694 | 53553545276b4b16d4aa0afb911d49d118a81ae85316e612ad86a46ef91060b3 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_session_expiry.py` | text | 1755 | ba3ffbccb411fbfc2a1647439927cff6b7338c92ca592fa9f40a9f662fa48cc9 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_session_heartbeat.py` | text | 3999 | 146bed3637206d7f6bcef650996c968b345c4d3d6afafc452ef202551910b97e | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_shoonya_history_aggregation.py` | text | 10802 | ac06a7941b16a673999ba61456a1295927b425b0699a75da05a7b1286999da47 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_shoonya_master_contract_guard.py` | text | 6204 | 79e4dcbf4601473fd6c0139e768e23bfa3943bcc128d8ca778140b34d63e02dd | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_simple_editor.html` | text | 3918 | b3f896833ef4d5b7187c62437a819e488b259440ea9d74dd6197874648d654c1 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_sip_analytics.py` | text | 7980 | 6e0f5ed0b0c0676d07148e6779660afb0d2279eb11763f3e4ce162e43143c722 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_sip_api_security.py` | text | 7308 | 9ed2ecac576c12807f4b20f76f1df74612844e86a6d5e14ec3f5388a277fe246 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_sip_crisis.py` | text | 3841 | e9925642d467f6d0c068542f8e486cd5e3453b9a62688be76e0e679afc86ccfa | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_sip_engine.py` | text | 12516 | 43c0385635ce78dd3c0da03d4fa9defa7966131c37d04bacb186070ae07b492e | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_sip_schedule.py` | text | 4224 | ec78f9c429e34bdf65712e951bea2e856fbeb83a856004aee092f8e7771db06b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_sip_service_validation.py` | text | 2900 | cbb464004a51bba0467e8754cb108cd2bb22a04f228193322c760ba396ae0c9f | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_sip_xirr.py` | text | 2836 | 81f2958b38e5fac75573bbb879c55f1c126f5f5cdf8e4068c76bd950ec5c282b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_slm_trigger_pricing_2390.py` | text | 8217 | b15fdeb8400aaa2b3e999ef6105fdb6e1e9caaa37fb4b7e349ea8f334b1e6359 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_smartorder_logic.py` | text | 17860 | b66c2db2099ad56152d734bdc8c76a77cb5367d2b7ab5f36ec348563b4d4253c | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_smtp_certificate_verification.py` | text | 10800 | 70bd399822b303ad98992c89919eb02de43c02398f3ebf3ede6ce49c15223154 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_smtp_error_messages.py` | text | 1652 | 53e455bf63373c031fe1d7b4d24fb144845db19a35e8f018d9986f3c032bf8b8 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_socketio_connect_auth.py` | text | 6016 | a7d382ea588dc21ed1de556de13ec2ab8ac571e38bb9a545690df8f9d829c174 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_sqlite_lock_cooperative.py` | text | 12578 | 81f94dc3b0042ee55d884fd08f5823c29b6e6edb86f17e1f17a2cbe34ba5153c | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_strategy_book_prune_lock.py` | text | 5417 | 7b7b0a87c87c10f6f801c5c8ca004b42fc8397c12766f1872e6c4a45fcb68f10 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_strategy_builder_chart_reference.py` | text | 4706 | 4066b529cb9e6b0fa6244ab78d4f64031b48034eb89ee6c8c438b42e7b5d19ec | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_strategy_builder_chart_window.py` | text | 6318 | 208b2764f0ab7c61e3980f60a92023e2fe33a9660df849a9bf4892b17577b44f | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_strategy_builder_expiry_exchange.py` | text | 2829 | f5ddef83e55228cfb34ab1271e8b53bc3d19df7573f333e5b6bea08dabc544ec | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_strategy_builder_option_chain_contract.py` | text | 282 | 15ee9e20691ae5c9669680b08bf190b14d4154f3b5b1dbc46c4dcc542df17220 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_strategy_module_api.py` | text | 38131 | 7b37eabf6b711583a7d47084f5c3b0345e0e95d05dfa920cae7c67cc1f33dc06 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_strategy_module_broadcast.py` | text | 24189 | 8ca86286d81cb5fc3f40619fd8f51c05428553c762a17e3f540ef799bbee3e4a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_strategy_module_broker_binding.py` | text | 36178 | 4b740bd349bfd0c382d70a5c7e5b6bb11df07254b208f642e015b8117f89f32b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_strategy_module_db.py` | text | 37924 | d670771d587697b095d6fa362be7d48d8ed74d0246efa605fea2bdcfb10bb65e | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_strategy_module_docs.py` | text | 16163 | 7cc8864861a73c637c57a15b3c78fbd14a4639219c520e4bce7adf838ec4a6b2 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_strategy_module_engine.py` | text | 50557 | 9b50b3e60844c77b11aee9d12f5e5ddc3c5c72aedc131d1f5ca9451112f3c43b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_strategy_module_lifecycle_api.py` | text | 22135 | a0d33137ea0b5dfb349d2aabad254a8f4fc708366cf7d11fc9cbabadbf599f77 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_strategy_module_order_dispatch.py` | text | 13631 | 2371e33e1a5797640361f770531010dd26f092abe51a314ad3435b943aa18f10 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_strategy_module_order_events.py` | text | 56573 | 2045ea012185769412cf70aef14a0122ebf9b067bf51921996402924919f787f | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_strategy_module_qa_edges.py` | text | 85050 | 6e2cb7f07a69124b1e04c7dd42c0059b005faa80fdc3ed93a3a8508ce15986f2 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_strategy_module_qa_segments.py` | text | 85514 | 6a24c7e276ed62fdc166b8f13e0807477afab48aaacfca95ab4c1b9041716639 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_strategy_module_recovery.py` | text | 66865 | 7cce83f000c09ece235b1480dc5c970bad96628e634dc38d0b2a4beeccd0d392 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_strategy_module_risk.py` | text | 18859 | 0595ba164f52ac46dd513dc5aa22c614db954e3689fa7842762948c4bc2f6fb9 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_strategy_module_runtime.py` | text | 4163 | 4f824129174d5197256707848c68581c1e92fd1b99a6ea014c08dda27185e4e9 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_strategy_module_scheduler.py` | text | 40109 | 3e656e594b4880f1bba996c8143b7298f20c1e8b8dbcbe6dd68a7d309c0aaa01 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_strategy_module_signal_api.py` | text | 17408 | dcac7230e3c0d43e82ea9c44bcc01f215455893cf9461f57dc4ae41ecf48cef7 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_strategy_module_signals.py` | text | 41035 | 57790e5e37a2a5ffa147b0c9aa4cca23e91df324133b04e3052d10abdadecc2a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_strategy_module_symbol_resolver.py` | text | 28143 | 638751b92619e29e1ee6c4519dcbf7a696c7aba3f5b0e8ff13bdfb3a9be825fb | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_strategy_module_tick_feed.py` | text | 30803 | 1805865c34ba332e5297ecace5d9b671d2d645d2a0b2b27737ea02886509a56a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_strategy_module_views.py` | text | 34200 | 66bf7486d57735ba966a23ebb29e3bda9108a1bf0d6ccce6e17ad684fe6dcf96 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_strategy_module_webhook.py` | text | 34778 | a6c4fe33d31e8c4289a3890b10a026ff03c1f2b63c9277e92517c7d16d583b3c | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_strategy_module_webhook_e2e.py` | text | 11490 | 71e9da1a2feec5074718881a6d3ce5fde3687ab943048957b62000b4bfb0ccd0 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_strategy_pnl_leg_order.py` | text | 2965 | 5cda326da882aad2178e9508a2ef817eb8f89afdbc730992f48ceb32e9991062 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_strategy_residual_safety.py` | text | 26752 | cbc94a2664f5386a72cfd5e1999ce88ff3d9abbf1ed4f337ad9608293ef3bf4b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_strategy_restx_api.py` | text | 23803 | bb6121e46618339be7bd30eac137ef13f43b59d82c305b391ccb6030f8aab15c | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_strike_profile_service.py` | text | 7017 | 6e08d0b31e2b884f7c200ad7a4cff123a0b0aed5aa769d9095b4b5a93ddaae93 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_telegram_alert_api.py` | text | 7986 | b18714d28a3915a6a27547ba3d500765b25927cfcddaf18f2eddd3b6a665ba43 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_telegram_alerts.py` | text | 6985 | 3952a71d201e1fb2ac0ebc90777cadeb2838b66657347f4bd27caff629ba9458 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_telegram_api_contract.py` | text | 8509 | c9fba8e068db39965aeda9277c41148e295e545f964f62b19316469896ab3b93 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_telegram_bot.py` | text | 2081 | ac78cf50189d3008ab6db060ce87c8767d759f5ce3294e41dbb6285d0e4190e0 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_telegram_charts.py` | text | 2502 | f20a30a06bc2ff16c647dfbe798033d41ba1d02a2a0cd65af25ebb6dbd5b9899 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_telegram_config.py` | text | 1962 | aa9f49ebbf97958f8ca97a72291d8e81fbaba3aeedf59bd06cf2b669cbc98961 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_telegram_link_ownership.py` | text | 12642 | 33ad658d8e61adf90b2551447f3b44efa7b249d90ce3f5f38625e86840e6d6bc | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_telegram_startup.py` | text | 495 | 8c1937514c96a45f1161ed40607f6277d80d773a1baac0e7dfe08925d0d754f5 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_telegram_startup_isolation.py` | text | 390 | 7226c1bb3fdb9e99276ae9b0cb0c4159d6c5ab9f34ef4f8b41d15f8181597d35 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_tradejini_history_candles.py` | text | 3987 | 32ed4faca7bf699e26ba5a1ff3dae2d2ad02f6b6ad72fe49176fe7a2e35eae57 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_tradejini_order_adapter.py` | text | 11523 | 9be99aa67ee0a4b813cc9996e728e02e03888e066c85d5a516606be61546536f | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_tradejini_order_refusal.py` | text | 7094 | 7fa205eb38b9963814c5494c3f517334483b37960e5da05a1ba08ac6a5e3566f | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_tradejini_quote_feed.py` | text | 2572 | eb000edf8f5e97bc488d9c699d78f8f1c63d008ed58b40c6f2592c8b5baca64c | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_tradejini_stream_lifecycle.py` | text | 14283 | 87042e99d0f235b56a525d0b3aae0578562b1d98a2e1c371933c3167adcf8037 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_tradesmart_rate_limiter.py` | text | 6871 | 374a43cb57d415a6697dcebba084ab817123bfe24cb5aec55d519e15e038847c | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_trading_calendar.py` | text | 5983 | ab961ccdae2aa0d2a9db19d4ad37c1ec0515a3580628934ee71a0e8dbf830ec4 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_unanswered_order_writes.py` | text | 8800 | 062ab92b177351656cf01f5de3c85c56ae710a87047491d413f4cb6c1bee6846 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_upstox_holdings_mapping.py` | text | 1292 | 89830b29dcbfa9db7409151fa12961e5e0fe9a2036071e536cd73cce87236721 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_upstox_login_refusal_logging.py` | text | 5183 | 81ff446ed317f81a052dd7570c52e578b54eea9d12921409f8a3758a214524a9 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_upstox_quote_feed.py` | text | 9792 | 9c455f49e179a4dde4b17aeeb0254fd8c1a3de744b56c460048d625bdad609fe | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_upstox_tick_size.py` | text | 3506 | b6789fb468e8905ab8f03b62492a7b404cd0d3b9696b05757e0d4ba91db51f47 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_watchlist_db.py` | text | 6104 | a21cea99e08ad5502239d0a3d268411e87b90f7d6b6c0ffd02b61342c22b84b4 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_webhook_proxy_log_safety.py` | text | 2989 | 83f5125b33e66ef1d0736ef35f55a682360be48bef0906625d9de945081d5cc1 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_websocket.py` | text | 9190 | 5af17f25d2fff9f6b19fd3f88a4b31fc357dae7c441a7e5beb84eea45bced509 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_websocket_cache_invalidation.py` | text | 3121 | 9e186ed7cb64f89e8afa9518cffbda1daf1644182be430a7cda4b5c5981b8d29 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_websocket_client_restart_logging.py` | text | 5169 | 0af2cd37613f1ed2028a00f5c650eee6305d4ddaa0dc163ec8033c49b1994e79 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_websocket_service.py` | text | 20914 | 094a97ff06d3af0604e306bd9d699288d74dbfdcc3ae7924dfc0b6cbf4da7842 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_websocket_session_expiry.py` | text | 5867 | 537c906a7e48513ffe002c38b4310cc87862ba8d136f79d07bd97a4001dbfb53 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_websocket_unsubscribe_contract.py` | text | 51588 | 538b390fdc8eda7f4d18461be0962c9ec43954c658ebd3fee2d6e1de2908ef38 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_whatsapp_notify_contract.py` | text | 6062 | 9708053c43ef69c0f6e3b16cb244415f4c73d32d9ed401605cbd213efcc369e6 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_whatsapp_owner_recipient.py` | text | 5549 | d54e2405654fbd6e04fb91a87c54b60079cf987dad61689df0d4e646948a7e25 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_whatsapp_session_export.py` | text | 4090 | 1784789fa3bf0edce38cd9d72390f7e94057f9d9607c9b152e452bcbe961278a | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_wisdom_streaming.py` | text | 25959 | e32b49a3fd00c619b5adead88305b6b2f73da7c77f833ccb420ebd27cf258fc2 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_xts_credential_logging.py` | text | 9571 | ce2f0b749747f1caec9cbf23f148738e15a9c6927b952a67c21cfdbe41216d9b | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_xts_order_data.py` | text | 7250 | 8822054c227f899f70c17292f127d353622226bf7051ee0f38a2a0b122e46f37 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_zerodha_full_packet_oi.py` | text | 3635 | 2b7b3aac62804d30bd94c73115efaad70e214437e461121420489add064d8e6c | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_zerodha_index_packets.py` | text | 3364 | 4b00211908d34fa9c0cad05f36f651bc0bfb60d14683c4374300b2218884a7bd | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_zerodha_mcx_review_fixes.py` | text | 30143 | 835fd941f5bee7fc4161dadd8953e1e70fcafda54dd1079644bf713782527145 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_zerodha_mcx_units.py` | text | 18610 | 75e5014613d070bf0bb0ad8b13500ad897a3e80dca86d28d66b1cad027381045 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_zerodha_order_status_mapping.py` | text | 2034 | dd6a4fa66f392396e29c65c3cc82913be615eca773a645cc44ea5ef5b7222ece | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_zerodha_quote_depth_qty.py` | text | 6760 | 04782474e9922e9101ba39465cf2d20995a2739b3c1d6cd403c04308d3ca736e | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `test/test_zerodha_series_symbols.py` | text | 5560 | baeccc96c5091d25287ba562328f371c897970a55701c8636b066a6964d08802 | test | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `tmp/README.md` | text | 51 | c1981e635fbcdf17cb355088fe3c0abee457200a2e3e2c522f9924dd81f43577 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/README.md` | text | 10465 | 8cc89391b2803566515cbd8d2c128a0c8fe6fc319acd8fa7cd2e99cd3718b2eb | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/_pragmas.py` | text | 2592 | a2341082fb7eb48e26298d4fa442bd8e6daabebd2a5c7fdf805501faf507a232 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/add_feed_token.py` | text | 3981 | 9e2f842d2edfdd5a47a85b9d385ff9a443519a264653e17660b7e451e03a913b | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/add_totp_purpose_flags.py` | text | 2876 | 76c35d1719d2412223dd6dcf18eac53667719b00d8a83e7c769727291fa1bec5 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/add_user_id.py` | text | 3464 | 72038792f87d4fb953fd544859784f3141d64ba511de351a20c0eafc0d316c12 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/init_db.py` | text | 16206 | dde25bd126231f1bc3d462ba5b06bd5a224b048d206af989e9c6b87538272dfc | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_agent.py` | text | 22685 | ea05c734c9a40461882968888347f52c0813357fd93bc5260b62676c0d732ecf | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_agent_voice.py` | text | 13791 | 7751c10254551310957282a7a9ecc868453cf0755d3fc8674a13d4918fa8ecbc | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_agent_voice_phrase_removal.py` | text | 5395 | 9b7840e617022678f7f09dc8dc44e37736bc0781ed531bdbfcec986aa972b1e3 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_alert_channels.py` | text | 5381 | eaf236a6ab193bcdc38b9b7bdf4ee99b9cffb21029fd1a7e3ac045491e71ca91 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_alert_log.py` | text | 7918 | 380298f2f5fb0b84524d82aa5817006ec786e05732b99a18f791e42bec7259ec | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_all.py` | text | 8947 | 421420f786abbbe2aa263e36c96c59124728683b8f8b0e7e7704873abd6e1be8 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_broker_keys.py` | text | 7763 | a13933a3d4b3fded5d00b724cfe16cccd3bf76dbc05c28ae276cadb013c2731a | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_contract_value.py` | text | 3346 | 51d9c3100472b98da4ff74b68648cb48757c4ff5a47359a3029dcac80915a530 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_drop_legacy_strategy.py` | text | 13274 | 04bb9c5417180c107f0e670772061232f741bdace820a95637e102fa0493fc74 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_flow.py` | text | 16127 | 7105526715e74f4ac6e16115f15d8f26fb3c8736e1522d5dd9f5a23b763a1dc1 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_gtt.py` | text | 11746 | 4605a3da3797b38f640049ed7807159df8626af94bb588094dd9135575498959 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_gtt_sandbox.py` | text | 9987 | 61c38cd8f3adc724f9f02e88b4f844e0a47416c7fa22e7c5200044e132796453 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_health_process_details.py` | text | 2709 | 4a633fe18f5903c23daff8d02e78da8733b8738db70e883c9a3c4fd3b940683e | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_historify.py` | text | 11673 | f5c8cdb962bfbda3d2821b358941a54f44ac43b55fe46ff3183aa358071ae7da | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_historify_drop_indexes.py` | text | 7125 | 3312d1f32d1e8a84ba003defa254fa330b51401c5af037c5b721a4c3ef04f2ae | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_historify_scheduler.py` | text | 13594 | 74af1e8899502ea1e0bd0e76c7463b6f6d3f2afe6ccf80bf15cc1133a5b4cb5a | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_historify_sequences.py` | text | 5159 | 26141c55e6b9467683c9565d579e6466580eff36829749670680d0279a85085d | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_indexes.py` | text | 15800 | 6ae1f9e3c875f6eedf5e42ba407848243b7e08f9d0005f4f79e68d3e203aba89 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_leverage.py` | text | 3957 | b634d75b06edf1a41a10ca238900ca4c4893824dedb0fcbbbeede479b1b94209 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_market_holidays.py` | text | 6708 | 8f8d1547d3bdcfca7921af2f9b655be88f26af857399928927b7d24e63d655f7 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_master_contract_stats.py` | text | 5211 | b9c693d5e9a82d8a64a466c1c474dc77fe8fdcfbe01ab6d1a1eb61f06425aefd | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_muhurat_2026.py` | text | 8126 | a6de0cc8842321eebd4049cb6cd972a5d0984b8245cb6f264f45edf3851682c3 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_order_mode.py` | text | 9550 | 8d3ec832872fb7b9ffcf83f281cdd9c9a6b19e7a44ce8ea68d81dcd32365d8ee | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_password_reset_grants.py` | text | 5678 | 89b01128aacb5f5abbae18b7b4b7ad642d0347754691cad4d045a19d1f59ced8 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_qty_freeze_nov_2026.py` | text | 11483 | 0a1f58053f6d5bf1190f783ddbd5d43c88f308262382ecd3f7c343291e311b20 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_samco_auth.py` | text | 4464 | 0dd52a86d4749c62820e27a0939d3fa5dc281cf18fcb03c76689e87d216df8f1 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_sandbox.py` | text | 18702 | e778dea1157d8a779fb8cdbb24d786419b959fee69e7d8564b0c6ae0234f678f | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_sandbox_charges.py` | text | 10857 | 4a22d8292ee259e64b2ce7aad9344daee1c801f62e2ea565bf664ba33f96d425 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_sandbox_pnl.py` | text | 7183 | fce476730b1a385dac1bb1c9876b5d70ca8fa88fc1e4284e6b15b5621911267e | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_sandbox_trigger_pending.py` | text | 9685 | 3824e95761ce9f5d1ec50c95249e9f9b0a9d7d6aa4e6efa2ddca1bf4fe00482b | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_security_columns.py` | text | 6095 | 06f0ecf774c75bb7d5ba8e054304252887a225a655a2072feb4b7c0617ee90b7 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_smtp_simple.py` | text | 14079 | 65ba524713604defe9670075e3d2031641d6aef755f9efe3ab1524dc918b2c01 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_strategy_module.py` | text | 11892 | ba6f4ee965f6c7bb2870a3e549936b0b9c439d52bfa47dc9f2ee66f8ec25c446 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_strategy_universe_tab.py` | text | 8701 | 917dcaa97342fc00ea34566821bfd9e8e029f048e919e44423a9a89e9d8536b2 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_telegram_bot.py` | text | 20071 | a8d8abc2410cacd58474da381c3a8b2ac49a9b91cccc8000ddea377e99330228 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_watchlist.py` | text | 9258 | 95dfcd79ca9e2bab7a7774302e3e1a69143c24c2746a00e2827bed6c59b07b35 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/migrate_zerodha_new_exchanges.py` | text | 5602 | 9cf425a7b8f5b1853fb7ad4292575ac778e62d80609bd27042eed74a8bbc4ba4 | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/reset_admin_password.py` | text | 9476 | 6a0c7e03f803ba60014ae10c965e50238033bd40769d918aea800c8d5da81a6e | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `upgrade/rotate_pepper.py` | text | 29173 | 502dd7729eca6bb21114e1ebb47d5fb0731a1a16cea28deeb02de41a2c81121f | database/migration | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils.py` | text | 591 | 1ec0076d687db41d9d09623a509a4c18e0b7aa7439e3a2b46208a627dbf252c3 | backend source (other) | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/__init__.py` | text | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/api_analyzer.py` | text | 24568 | 210892bd39ae2e1b6dd77c15f4d2cc6851d77bd87b30d08267ec61a430ab6b6f | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/auth_utils.py` | text | 34864 | 31dc9da725e37917dbdfa69ea6d552e5966fd818d01bb1a8b322b7b147c6f26c | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/broker_backpressure.py` | text | 7542 | 631251f1662c343c024ced8037989a2cd527b87719a3074e4395a52af4279e36 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/broker_keys.py` | text | 30209 | a44ac924c280d97a17b8055a25c00316baa163b6b9b7339a426aaa374c51270e | backend source | INDIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `utils/broker_login.py` | text | 12196 | 05dd551728a9620caf24db1653fb1c4426d515de0d9605d92bfbab29c3bf904a | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/broker_setup_guide.py` | text | 41518 | a8edb4b74095072a70286ec1cb53da211c394155c016cb9a2291315115eff19a | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/broker_switch.py` | text | 6079 | af634666d3a19ba0cc69c9ce566bfcaa2d2c34c517620b83805e267f853373e8 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/config.py` | text | 2583 | 507c349f0677be528a76473ad89038fc1570cc2f2a96d441ed35e6bf67c35fdc | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/constants.py` | text | 6161 | 193059eeef23315e5ce14bf0fe3400bca2d017cf0a0bbbf1cdffb75444563867 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/db_sessions.py` | text | 8381 | 8fdd13fe07a2b1ed8bfce89bc2defba0a18f7ac671edac8beeac5a01fcf297f4 | backend source | INDIRECT | FULL_TEXT_REVIEWED | read end to end in this audit |
| `utils/email_debug.py` | text | 7554 | e3b6b08e484e63c9fbcd75e709aff0c56204bce8f2b0c11336a2ab5c6596e2e5 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/email_utils.py` | text | 30414 | 4f1c31dcb95b480cf6b874314ee392aafaf59a3b1e88a8786190ad40b128761b | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/env_check.py` | text | 78557 | d8b7c9edd72886e78196f57772ab708e18dc45e3d472d581fd6ffed6ab9f3e8a | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/env_config.py` | text | 1758 | 4b5270912628b5677a02a3e2b6c46d0138cf69fa4d1565b1f9383e9dcbf4c338 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/event_bus.py` | text | 10203 | 599fe946408f996fdb77cdfe6571b747991ad1cfa8deb3d1031c221ae570870c | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/health_monitor.py` | text | 29092 | 16a1f3f99c87cf1c4c9fbb664f3fdbfff902e69cd94d12a257d514f911f1e69f | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/httpx_client.py` | text | 14137 | 6adcd8f927827d41fea96dfeb5ecc78c22fc4d0790ff96bb711314a3d2d67b65 | backend source | INDIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `utils/ip_helper.py` | text | 5308 | f2e6943c01ed82646141db9b21aff367f9a906d4cb58f7fb651ce4c3f85fcf59 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/keyed_locks.py` | text | 5713 | 9e06e0693618aa3d60da80fca0f2f1c10dfa726b933faad6b96302bf999b3d33 | backend source | INDIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `utils/latency_monitor.py` | text | 15333 | 852287c9182628ce7ddcb9222ad4973e221560e8dcfd5f0253be6e5ad917d7f0 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/lazy.py` | text | 3264 | 50c60f0cc05d6370007407122b5774320aedbc23f7788e359be56cf4a5c64bf7 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/logging.py` | text | 27186 | e719b68ad59e5606c33a280e7cba4acf2ff5b28f3adad1bf42e99100cffd3756 | backend source | INDIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `utils/mcp_tool_registry.py` | text | 14667 | bab7b9ea8fbbcfb5f2b620f801de9addcdcf2c243ac4b79122a85df0db5311df | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/mpp_slab.py` | text | 11224 | 65d6d47f54995b6628b4937f5d1233204b2576e527295804bfc0391a7ccaeb87 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/ngrok_manager.py` | text | 7275 | 32702693eb8d6cd3edfafca0e231527c0566681ed3a69a27a2b28f9fabe3ab1c | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/number_formatter.py` | text | 1702 | cfc17cee19f6ad388583e0fb3ca97de9dd9c890d148827fd28eb3ca31b61cc19 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/oauth_codes.py` | text | 5377 | 08a9c8fa65303c878e2fa2744089566c71f705af43b4a271c406245c350966e1 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/oauth_keys.py` | text | 7727 | 979463b8f3f8f90f97ed179794615c5c3cf6cd6774486e60149caf3261a114ac | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/oauth_tokens.py` | text | 13258 | e5c76ac3be4ee1d1d2fc5c62cb3d46c4fcf56a584b12a34760588b3da1c3d21e | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/plugin_loader.py` | text | 4922 | c082306488a2d11565da6557b2838379c6450b3a5048165fca6b9d6e06806698 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/position_read.py` | text | 12030 | 2039ba48d23425f6d874044cc88607fc206244175ee1737da2f3ead7368ef6ea | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/precompress_assets.py` | text | 9951 | 75c6623c54cbb04bd5bcf3feb3ad6a5d28e91f2024ec4d60db77a5e02bc1ae5e | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/real_threading.py` | text | 17663 | 374328c21a84a3a14703d452e0e4e15d0e0ef538304bd9608ccd83d2f4074c85 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/resilient_scheduler.py` | text | 12922 | 7869cf17abdfa86c97ab102a0a88afcb1adb71ed2e9aaf86fddcc2d88fedf868 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/runtime.py` | text | 11765 | 23432803e36c24402159b183711806b1e550b2851111775c78a7b23c9ca29c53 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/security_middleware.py` | text | 4535 | 5f24936d876755cfef1469042cc977c20bba4da7d7a7c8cd1f87e2ec410e31cf | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/session.py` | text | 22620 | 5bea6f6a0d715eb9cf050b3ad82ff78c63cff85ef1d3072a34a7a04abe9e7be1 | backend source | INDIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `utils/shared_executors.py` | text | 4361 | c9b81f20648707695dfdfc832c9c5e29f7fd4ec08a2112d086d4274169b266c9 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/shutdown.py` | text | 25072 | a8d5edb3cff83a708fa200e81d4545dc81319a14e70f3e5c46482ba118e96512 | backend source | INDIRECT | NOT_REVIEWED | hashed; searched by grep, not read end to end |
| `utils/smart_order_guard.py` | text | 5529 | 94433b3fed0aa6a800377315db6694a476b4c0faadf3b734c595cd0bf54610fc | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/socketio_error_handler.py` | text | 1811 | e07946b9c049f5fd78440a60e0166623ef460e5d94168ccf5b9f8a70860a48d1 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/stream_registry.py` | text | 10126 | 529271a77dbdadefd816c08394a79b9a34b5a8cffb9821486ab6e7962973b847 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/symbol_utils.py` | text | 1928 | 3420016435c08d0e972b3feaaba06f2d7bd8b2d183bc851e82b9087ab9393b09 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/thread_safe_cache.py` | text | 9160 | 930c130269213f05006149c4a0b24433a79ff33db67b6f836d48e679fcfe7212 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/trading_calendar.py` | text | 9822 | 62eee156831a1d8a79a7e55df3b6f4308767a7cbe77420de34d664f9e9089a9d | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/traffic_logger.py` | text | 3954 | 72335a161a07f0f295c5d8490354c123c04eb073dba2047508913c0e70a4164e | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/url_redaction.py` | text | 2177 | bde9e9a2302094c809b2b0dd15e32f1f193a7b5fe72c355c1c06c82445eaaaba | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/version.py` | text | 300 | 2db2821141e5eac5965f92b25cf57320ed7c19e23602bde3fe1cf9aadc4adf1d | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `utils/xts_order_data.py` | text | 4117 | e2a9e1df291accf1629ff2b76e64b2d5aeafe6f07ce651c9812ebc6667b0e8d1 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `uv.lock` | text | 985229 | 330cead640a3bc1dfdd8cf016d11d989ca8ecaec2af1ae2f07ecd7713737dfe6 | configuration/other | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `websocket_proxy/__init__.py` | text | 7811 | 3df30ea2e84e9c8e9376d633cc3ce2de042c074c0258089086940d6022d3e746 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `websocket_proxy/app_integration.py` | text | 27557 | 52a841bedeccfaad3742fa0875fe2e393968e0d17c4b50d009e0d46f44129e66 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `websocket_proxy/base_adapter.py` | text | 22809 | d5aefe0538144734891e496a5728d56ad2d2287128ab754378d8da45d6aa0c77 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `websocket_proxy/broker_factory.py` | text | 17665 | 7e1f9cc549a44ea9c26e26e7a4f26252b6719a3776d911e98dfefe4be1a5728f | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `websocket_proxy/connection_manager.py` | text | 53769 | de1f13b9ceac28960c4bc41d859b96e7c9661278b65e07150b7dccb21059dade | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `websocket_proxy/mapping.py` | text | 4057 | 72a41d60f098970f8a3b1d131a9f7df8fa7f7c194e06fcc67fa6d7c094a6b892 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `websocket_proxy/mode_utils.py` | text | 3135 | 12077da25f0cd0982d3b5c3db3928bfda672d7ea15246a34c47850df2996b91b | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `websocket_proxy/order_adapter.py` | text | 22647 | 8a04f409a7d7c9e25ddd5efecb89c29af117c7222745e128efad7b38152e5667 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `websocket_proxy/port_check.py` | text | 2682 | 7c844c5789c90c2b68bf80757ba964c8f759955060cdddb647abf4eb7b486cee | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `websocket_proxy/server.py` | text | 102316 | b215bcaa885bb98c23e2f83ae37c8f170004f2d8f7c4798b4715bdbe8cb29c33 | backend source | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `workspace/backtests/readme.md` | text | 442 | b59b0b0f850c4f3ecbfac7f62426d9fb6b7f431a7f433acf4cb24e6c1fa58773 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `workspace/execution/readme.md` | text | 3792 | ee59fb0afbef0b39e7729ecef24cadf6edc5cbbead9d473faf2b69dea548ca3f | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `workspace/indicators/charts/readme.md` | text | 379 | 930cdf77a29d5e6219ea684fce978ecbdb532315ef1dcc244ed2b229b85e8030 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `workspace/indicators/custom/readme.md` | text | 541 | 6722c18e7482b6b47ed3bc42390721d054b45c2d8cae14c82b5b373ebff5ef78 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `workspace/indicators/dashboards/readme.md` | text | 448 | dc8b34f036da85ce8c4003ee5d4850f84c680b04e61dc5cdf9abe25cadb80139 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `workspace/indicators/data/readme.md` | text | 308 | c2cccea3da30faa06b119a8aebbf17b234fb6a3718f99548e4fa6aa1f40d8b47 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `workspace/indicators/feeds/readme.md` | text | 355 | 2387e792a6c7528d32a6de168d7ed626dcac988b2a0b09266d8540abb29f1e73 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `workspace/indicators/output/readme.md` | text | 288 | 335ff6f29ad1db77f24556dc3a78bde6fe09f9b14c9d4298c0228fd32ccd1454 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `workspace/indicators/readme.md` | text | 844 | c5ef7174e2b252a6ac449513c07efd5df5d1b4a8254439deb00a2112031d787f | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `workspace/indicators/scanners/readme.md` | text | 370 | 0a009aea017bf579773a4894847b5dac16942b23a675e032da14c61bb41d3c00 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `workspace/notes/readme.md` | text | 244 | 95dd3536ef5d589cc5b57254188185129f78494122ef8a832478fcc3c26285f6 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `workspace/readme.md` | text | 3101 | b7c4a907590ba8e0bffb74baf1768e25a61b92b3137d004f148e59b71a838d31 | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |
| `workspace/research/readme.md` | text | 274 | 57942b88cc898dfdc44d5d16e8260ea327e59ea9861ab291b2455c39240b3beb | documentation | NONE_IDENTIFIED | NOT_REVIEWED | hashed only |

### C.2 Ignored files (674,053), aggregated by directory

Every ignored file is `NOT_REVIEWED`. They are dependency installs, virtual environments, caches, build output and earlier test runs, and they are not repository-owned source. `frontend/node_modules` includes the recursive junction described in section B.

| Directory | Files | Review status |
|---|---:|---|
| `.claude/` | 1 | NOT_REVIEWED |
| `.code-review-graph/` | 4 | NOT_REVIEWED |
| `.env` | 1 | NOT_REVIEWED |
| `.pytest-tmp/` | 1 | NOT_REVIEWED |
| `.pytest-tmp/test_fill_rejects_degenerate_p0` | 1 | NOT_REVIEWED |
| `.ruff_cache/` | 2 | NOT_REVIEWED |
| `.ruff_cache/0.16.0` | 15 | NOT_REVIEWED |
| `.ruff_cache/0.17.5` | 5 | NOT_REVIEWED |
| `.venv/` | 4 | NOT_REVIEWED |
| `.venv/include` | 1 | NOT_REVIEWED |
| `.venv/Lib` | 36672 | NOT_REVIEWED |
| `.venv/Scripts` | 87 | NOT_REVIEWED |
| `.venv/share` | 14 | NOT_REVIEWED |
| `__pycache__/` | 5 | NOT_REVIEWED |
| `blueprints/__pycache__` | 63 | NOT_REVIEWED |
| `broker/__pycache__` | 1 | NOT_REVIEWED |
| `broker/aliceblue` | 4 | NOT_REVIEWED |
| `broker/angel` | 7 | NOT_REVIEWED |
| `broker/arrow` | 7 | NOT_REVIEWED |
| `broker/compositedge` | 7 | NOT_REVIEWED |
| `broker/definedge` | 8 | NOT_REVIEWED |
| `broker/dhan` | 14 | NOT_REVIEWED |
| `broker/fivepaisa` | 9 | NOT_REVIEWED |
| `broker/fivepaisaxts` | 5 | NOT_REVIEWED |
| `broker/flattrade` | 6 | NOT_REVIEWED |
| `broker/fyers` | 14 | NOT_REVIEWED |
| `broker/hdfcsecurities` | 10 | NOT_REVIEWED |
| `broker/hdfcsky` | 10 | NOT_REVIEWED |
| `broker/ibulls` | 5 | NOT_REVIEWED |
| `broker/iifl` | 5 | NOT_REVIEWED |
| `broker/iiflcapital` | 14 | NOT_REVIEWED |
| `broker/indmoney` | 5 | NOT_REVIEWED |
| `broker/jainamxts` | 5 | NOT_REVIEWED |
| `broker/kotak` | 8 | NOT_REVIEWED |
| `broker/motilal` | 8 | NOT_REVIEWED |
| `broker/mstock` | 8 | NOT_REVIEWED |
| `broker/nubra` | 12 | NOT_REVIEWED |
| `broker/nuvama` | 7 | NOT_REVIEWED |
| `broker/paytm` | 4 | NOT_REVIEWED |
| `broker/pocketful` | 7 | NOT_REVIEWED |
| `broker/rmoney` | 7 | NOT_REVIEWED |
| `broker/rupeezy` | 9 | NOT_REVIEWED |
| `broker/sahi` | 6 | NOT_REVIEWED |
| `broker/samco` | 7 | NOT_REVIEWED |
| `broker/shoonya` | 6 | NOT_REVIEWED |
| `broker/tradejini` | 5 | NOT_REVIEWED |
| `broker/tradesmart` | 7 | NOT_REVIEWED |
| `broker/upstox` | 4 | NOT_REVIEWED |
| `broker/wisdom` | 5 | NOT_REVIEWED |
| `broker/zerodha` | 5 | NOT_REVIEWED |
| `database/__pycache__` | 46 | NOT_REVIEWED |
| `db/` | 11 | NOT_REVIEWED |
| `db/nifty_calendar` | 4 | NOT_REVIEWED |
| `events/__pycache__` | 8 | NOT_REVIEWED |
| `frontend/dist` | 243 | NOT_REVIEWED |
| `frontend/node_modules` | 588346 | NOT_REVIEWED |
| `frontend/playwright-report` | 4 | NOT_REVIEWED |
| `frontend/test-results` | 2 | NOT_REVIEWED |
| `install/lib` | 2 | NOT_REVIEWED |
| `log/` | 2 | NOT_REVIEWED |
| `log/test` | 1 | NOT_REVIEWED |
| `mcp/__pycache__` | 1 | NOT_REVIEWED |
| `nul` | 1 | NOT_REVIEWED |
| `openalgoUI.egg-info/` | 5 | NOT_REVIEWED |
| `portfolio/__pycache__` | 14 | NOT_REVIEWED |
| `restx_api/__pycache__` | 56 | NOT_REVIEWED |
| `sandbox/__pycache__` | 8 | NOT_REVIEWED |
| `scripts/__pycache__` | 3 | NOT_REVIEWED |
| `services/__pycache__` | 85 | NOT_REVIEWED |
| `services/agent` | 23 | NOT_REVIEWED |
| `services/alerts` | 14 | NOT_REVIEWED |
| `services/nifty_algo` | 33 | NOT_REVIEWED |
| `services/risk` | 5 | NOT_REVIEWED |
| `services/strategy_module` | 19 | NOT_REVIEWED |
| `sip/__pycache__` | 6 | NOT_REVIEWED |
| `strategies/` | 1 | NOT_REVIEWED |
| `subscribers/__pycache__` | 6 | NOT_REVIEWED |
| `test/.pytest-tmp` | 2 | NOT_REVIEWED |
| `test/__pycache__` | 209 | NOT_REVIEWED |
| `tmp/` | 125 | NOT_REVIEWED |
| `tmp/actionlint` | 13 | NOT_REVIEWED |
| `tmp/compliance-focused` | 10 | NOT_REVIEWED |
| `tmp/compliance-full` | 510 | NOT_REVIEWED |
| `tmp/compliance-import-tests` | 21 | NOT_REVIEWED |
| `tmp/compliance-regression` | 59 | NOT_REVIEWED |
| `tmp/compliance-storage-42c0135bb28a4ad2b915e977b506c564` | 1 | NOT_REVIEWED |
| `tmp/nifty-audit-build` | 395 | NOT_REVIEWED |
| `tmp/nifty-audit-health-final` | 66 | NOT_REVIEWED |
| `tmp/nifty-audit-verified` | 183 | NOT_REVIEWED |
| `tmp/nifty-completion-dist-verified` | 395 | NOT_REVIEWED |
| `tmp/nifty-completion-full-final` | 332 | NOT_REVIEWED |
| `tmp/nifty-completion-new-regressions` | 21 | NOT_REVIEWED |
| `tmp/nifty-completion-resumed` | 136 | NOT_REVIEWED |
| `tmp/nifty-final-focused-04` | 135 | NOT_REVIEWED |
| `tmp/nifty-focused-spot-01` | 129 | NOT_REVIEWED |
| `tmp/nifty-frontend-incomplete-dependencies` | 37105 | NOT_REVIEWED |
| `tmp/nifty-full-spot-03` | 433 | NOT_REVIEWED |
| `tmp/nifty-gap-final` | 36 | NOT_REVIEWED |
| `tmp/nifty-phase7-build` | 389 | NOT_REVIEWED |
| `tmp/nifty-phase7-email-focus-20261121` | 2 | NOT_REVIEWED |
| `tmp/nifty-phase7-final-20261121` | 444 | NOT_REVIEWED |
| `tmp/nifty-pipe-green-02` | 4 | NOT_REVIEWED |
| `tmp/nifty-production-validated` | 387 | NOT_REVIEWED |
| `tmp/nifty-spot-red-01` | 17 | NOT_REVIEWED |
| `tmp/nifty-uv-cache` | 5806 | NOT_REVIEWED |
| `tmp/phase7-skip-audit-red` | 8 | NOT_REVIEWED |
| `tmp/pytest-final` | 416 | NOT_REVIEWED |
| `tmp_pytest/` | 7 | NOT_REVIEWED |
| `tmp_pytest/nifty-baseline` | 112 | NOT_REVIEWED |
| `tmp_pytest/test_additive_initialization_a0` | 1 | NOT_REVIEWED |
| `tmp_pytest/test_api_auth_csrf_validation_0` | 1 | NOT_REVIEWED |
| `tmp_pytest/test_assessment_uses_server_ke0` | 1 | NOT_REVIEWED |
| `tmp_pytest/test_concurrent_control_has_on0` | 1 | NOT_REVIEWED |
| `tmp_pytest/test_decision_deduplication_an0` | 1 | NOT_REVIEWED |
| `tmp_pytest/test_kill_survives_store_recre0` | 1 | NOT_REVIEWED |
| `tmp_pytest/test_sessions_release_connecti0` | 1 | NOT_REVIEWED |
| `tmp2yl0u5x9/` | 1 | NOT_REVIEWED |
| `tmpubxia_nl/` | 1 | NOT_REVIEWED |
| `upgrade/__pycache__` | 3 | NOT_REVIEWED |
| `utils/__pycache__` | 47 | NOT_REVIEWED |
| `websocket_proxy/__pycache__` | 10 | NOT_REVIEWED |

## D. Approved strategy specification (summary)

The authoritative indicator inputs from the trader's screenshots:

| Indicator | Input | Value |
|---|---|---|
| SuperTrend | Length | **20** |
| SuperTrend | Factor | **2** |
| VWAP | Source | **hlc3** = (high + low + close) / 3 |
| VWAP | Anchor Period | **Session** |
| MACD | FastLength / SlowLength / SignalLength | **12 / 26 / 9** |
| MACD | Source | **close** |
| ADX | ADX Smoothing | **14** |
| ADX | DI Length | **14** |

These supersede the historical SuperTrend ATR 10 / multiplier 3.

The strategy rules: buy NIFTY CE or PE only, intraday, PAPER only, on ₹20,000
of isolated capital. At most one open position and one filled primary entry per
session, 1 to 3 lots. Signals come from completed 5-minute NIFTY futures candles,
confirmed by completed 15-minute candles, with at least 80 of each. The five
mandatory gates are SuperTrend, MACD (crossover age 0 to 2), ADX of at least 25,
price within 80 bps of a session VWAP on the right side, and PCR: OI by default,
complete chain for one expiry, at most 90 s old, legs within 5 s of each other,
at least 1.5 for bullish and below 1.0 for bearish. Confidence is
`five-indicator-v1`, five terms of up to 20 points each. Entries are ATM or ITM
only. Selector weights are 30/25/15/20/10. Risk limits: planned loss at most
₹400, projected net reward at least ₹350, daily loss gate 1.5%, monthly loss lock
₹2,000. Entries run from 10:30 IST to before 14:45. A position is held at most
45 minutes and closed by 15:10, or 5 minutes before an earlier close. The premium
stop is at most 8%. The trailing stop is 1.5 premium points, activated at entry
+1.5. The target is 10 to 15% of premium. Live mode is refused with
`LIVE_NOT_READY`.

## E. Indicator settings comparison

| Indicator | Setting | Approved screenshot | Code default | Runtime-effective | Replay-effective | Verdict |
|---|---|---|---|---|---|---|
| SuperTrend | Length | 20 | **10**: `atr_period` default (`config.py:30`); `supertrend(bars, period=10, ...)` default argument (`indicators.py:44`) | **10**: no saved NIFTY state exists; the first `ensure_user` persists `StrategyConfig()` (`nifty_algo_db.py:978-995`). Can be changed (2 to 100) only through the raw JSON editor or `PUT /api/nifty-algo/configuration` | **10**: replay evaluates with the configuration pinned in the recording manifest (`execution_replay.py:284`, `research.py:475`), which is the saved configuration. A research experiment may override `atr_period` (UI field, `ExperimentsPanel.tsx:200`) | **MISMATCH** (default and effective); user-configurable |
| SuperTrend | Factor | 2 | **3**: `atr_multiplier` default (`config.py:31`); default argument `multiplier=3` (`indicators.py:44`) | **3**, for the same reason. Configurable (> 0 to 10) through raw JSON only; there is no structured control | **3**. Experiments may override it through the API only (`RESEARCH_FIELDS`, `execution_replay.py:41`); the experiments UI has no factor field | **MISMATCH** (default and effective); configurable through JSON only |
| VWAP | Source | hlc3 | `vwap_basis="typical"` (`config.py:43`), computed as `(bar.high + bar.low + bar.close) / 3` (`indicators.py:173`) | typical = hlc3 | same function (`decision_at` → `Rules.evaluate`) | **MATCH** |
| VWAP | Anchor | Session | resets at each new IST calendar date (`indicators.py:167`); minute bars outside the effective NFO session window are dropped before aggregation (`assessment.py:87-88`); 5-minute buckets are anchored at session open (`market_data.py:22-33`) | as default, plus a refusal when today's first minute bar or first 5-minute bucket is not at the session open (`assessment.py:176-184`) | same reset; the opening check covers the first minute bar only (`execution_replay.py:291`; see F-11) | **MATCH** in effect for regular NFO sessions, which never cross IST midnight. Special sessions are disabled (`calendar.py:52-53`) |
| MACD | Fast | 12 | `macd_fast=12` (`config.py:32`) | 12 | 12 (pinned) | **MATCH** |
| MACD | Slow | 26 | `macd_slow=26` (`config.py:33`) | 26 | 26 | **MATCH** |
| MACD | Source | close | `closes = [b.close for b in bars]` (`indicators.py:81`); not configurable | close | close | **MATCH** |
| MACD | Signal | 9 | `macd_signal=9` (`config.py:34`), an EMA of the MACD line seeded with an SMA (`indicators.py:84`) | 9 | 9 | **MATCH** |
| ADX | Smoothing | 14 | `adx_period=14` (`config.py:40`), applied as the Wilder smoothing of DX: `wilder(dx, period)` (`indicators.py:143`) | 14 | 14 | **MATCH** by value. The same field also sets DI length (F-13) |
| ADX | DI Length | 14 | the same `adx_period`, applied as the Wilder smoothing of TR, +DM and -DM: `wilder(tr, period)` and the like (`indicators.py:131`) | 14 | 14 | **MATCH** by value. No separate DI-length field exists |

Supporting observations:

- **SuperTrend algorithm.** ATR is Wilder (RMA) seeded with the SMA of the first
  `period` true ranges, and bar 0's true range is high minus low
  (`indicators.py:31-41`). The basic bands are hl2 ± multiplier × ATR. The final
  bands carry over with the standard rule (`indicators.py:60-61`), and the
  direction flips on a close through the current final band (`:62-65`). This
  matches the Pine `ta.supertrend` recursion apart from the initial direction,
  which here is close against hl2 (`:58`; see F-18). Length maps to the ATR
  period and Factor to the band multiplier, so 20/2 would be expressed as
  `atr_period=20, atr_multiplier=2`.
- **The 15-minute confirmation uses the same `atr_period` and `atr_multiplier`**
  (`signal_engine.py:59`, `snapshot(higher, config)`), so it is also 10/3 today.
- **ADX** follows Wilder: +DM and -DM by the "up > down and up > 0" rule, bar 0
  excluded from TR and DM (`indicators.py:121-130`), DX = 100·|DI+ − DI−| /
  (DI+ + DI−), then RMA. This is Pine `ta.dmi` with diLength = adxSmoothing =
  `adx_period`.

## F. Requirement-by-requirement compliance matrix

| ID | Requirement | Expected | Actual | Evidence | Tests | Verdict |
|---|---|---|---|---|---|---|
| R-01 | Instrument scope | NIFTY NFO CE or PE buys only | Instrument model allows only NIFTY; admission requires NFO CE/PE (`paper_executor.py:193-199`); a SELL needs a held position (`:203-210`, `nifty_algo_db.py:2306-2315`) | as cited | not inspected | MATCH |
| R-02 | PAPER only | No live order | `LiveAdapterStub` refuses (`trading_mode.py:66-69`); `_mode_reasons` refuses a non-PAPER BUY (`nifty_algo_db.py:1757-1760`, `:2242`, `:2589`); a LIVE mode change is always refused (`:1827-1828`) | as cited | not inspected | MATCH |
| R-03 | Futures for signals, spot for moneyness | No substitution | History of the nearest-expiry NIFTY future (`assessment.py:122-137`); moneyness from `NSE_INDEX` NIFTY spot (`runner.py:322-332`, `paper_executor.py:535-567`) | as cited | not inspected | MATCH |
| R-04 | Capital ₹20,000, no reset | Fixed initialization; persists across restart and rollover | `virtual_capital` fixed at 20000 (`config.py:27-29`); the account is created once and rollover resets only the day baseline and counters (`nifty_algo_db.py:1922-1942`) | as cited | not inspected | MATCH |
| R-05 | Isolated from Sandbox | Separate ledger | `nifty_algo_*` tables; no Sandbox import in NIFTY code | grep | not inspected | MATCH |
| R-06 | One position, one filled entry per session | Enforced | `max_positions` literal 1 and `max_daily_entries` 1 (`config.py:69-71`); `DAILY_ENTRY_USED` counts PENDING/FILLED/PARTIAL BUYs only (`nifty_algo_db.py:2258-2267`); `daily_entries` incremented only on fill (`:2643-2645`) | as cited | not inspected | MATCH |
| R-07 | 1 to 3 lots, depth-covered | Sizing within depth | `permitted` from score thresholds 0/40/70, capped at 3 (`risk_manager.py:64-67`); depth check (`:130-131`); fill checks `ask_size` (`paper_executor.py:603`, `nifty_algo_db.py:2539`) | as cited | not inspected | MATCH |
| R-08 | Completed 5-minute candles, no leakage | No incomplete or future bar | `completed_series` keeps only `end <= now and complete` (`signal_engine.py:11`); aggregation drops partial buckets (`market_data.py:38-43`) | as cited | `test_nifty_algo_macd_window.py:234-263` | MATCH |
| R-09 | 15-minute confirmation | Same direction, fresh | `R-MTF` (`signal_engine.py:89-96`) | as cited | not inspected | MATCH (with 10/3 settings, R-17) |
| R-10 | Warmup of 80 bars | Both series | `R-WARMUP` (`signal_engine.py:73-77`) | as cited | not inspected | MATCH |
| R-11 | Gaps fail closed | Gap in today's session refused; earlier gap gives a verified suffix | `completed_series` (`signal_engine.py:27-38`) | as cited | `test_nifty_algo_sdk_241_parity.py:649` (not read) | MATCH. A missing tail at the end of an earlier session is not detected (F-11) |
| R-12 | Opening data for VWAP | Today's opening present | `assessment.py:176-184` | as cited | not inspected | MATCH live; PARTIAL in replay (F-11) |
| R-13 | SuperTrend 20/2 | Length 20, factor 2 | 10/3 | section E | parity tests pin 10/3 (F-08) | **MISMATCH** |
| R-14 | MACD 12/26/9 close | As approved | As approved | section E | SDK parity tests (not read) | MATCH |
| R-15 | MACD crossover age 0 to 2 | Age 3 refused | HEAD: `MAX_MACD_CROSSOVER_AGE = 2`, enforced by the validator (`config.py:20`, `:157-161`) and the gate (`signal_engine.py:100-107`); `main`: default 3 | git | `test_nifty_algo_macd_window.py:118-137` exercises the real indicator at ages 0 to 4 | MATCH on HEAD; **MISMATCH on `main`** (F-03) |
| R-16 | ADX ≥ 25, DI 14, smoothing 14 | As approved | `adx_min=25`, `adx_period=14` for both (`config.py:40-41`; `signal_engine.py:111-114`) | as cited | `test_nifty_algo_core.py:89` (period 3) | MATCH (F-13) |
| R-17 | Session hlc3 VWAP within 80 bps | As approved | `signal_engine.py:115-124`; `vwap_max_bps=80` | as cited | SDK parity session test (not read) | MATCH |
| R-18 | PCR completeness and freshness | Full chain, one expiry, OI by default, 90 s, skew 5 s, missing stays missing | `indicators.py:180-230`; `native_data.py:299-351` | as cited | not inspected | MATCH in code; practical feasibility UNVERIFIED (F-06) |
| R-19 | PCR thresholds | ≥ 1.5 bullish, < 1.0 bearish | `signal_engine.py:132-134` | as cited | not inspected | MATCH |
| R-20 | All five gates mandatory | No bypass | `eligible = all PASS` (`signal_engine.py:146`); admission requires an eligible decision with a matching configuration id that is at most 30 s old (`paper_executor.py:222-239`) | as cited | not inspected | MATCH |
| R-21 | `five-indicator-v1`, 5 × 20 | Equal weights | `confidence.py:59-68`. The SuperTrend term uses constants /10 and /3 (F-04) | as cited | not inspected | PARTIAL |
| R-22 | ATM/ITM only, D-1 rule | Nearest listed strike, midpoint goes to the lower strike, within 25 points, ladder brackets spot | `atm_reference` (`contract_resolver.py:78-100`), applied at selection, admission (`paper_executor.py:264-281`), the locked write (`:449-456`), fill (`:615`, `nifty_algo_db.py:2607-2615`) and replay (imports `current_moneyness`) | as cited | not inspected | MATCH |
| R-23 | Verified master and identity | Today's master, broker match, complete, no conflicting token | `native_data.py:153-187`; `runner.py:506-509`; `contract_resolver.py:143-148` | as cited | not inspected | MATCH in code; master completeness itself UNVERIFIED (Q) |
| R-24 | Liquidity gates | Bid, ask, depth, age, spread, volume | `liquidity_reasons` (`contract_resolver.py:13-35`); repeated at fill (`nifty_algo_db.py:2616-2625`) | as cited | not inspected | MATCH (F-07, F-16) |
| R-25 | Selector weights 30/25/15/20/10 | Sum to 100 | `config.py:57-63`, `:122-125` | as cited | not inspected | MATCH |
| R-26 | Missing OI never zero; no fabricated Greeks | | OI stays `None` (`depth_quote.py:59-76`); DELTA mode needs a timestamped delta (`contract_resolver.py:262-279`); missing OI zeroes the volume liquidity term (`selection_scoring.py:37`) | as cited | not inspected | PARTIAL (F-12) |
| R-27 | Planned loss ≤ ₹400, net reward ≥ ₹350, fees and buffer included | | `risk_manager.py:113-131`; re-checked at fill with the fill price (`nifty_algo_db.py:2570-2631`) | as cited | not inspected | MATCH (fee rates, F-05) |
| R-28 | Daily loss 1.5%, monthly loss ₹2,000, cooldown | | `risk_manager.py:211-215`; `nifty_algo_db.py:2286-2289`, `:3194-3258`, `:3281-3321` | as cited | not inspected | MATCH |
| R-29 | Entry window 10:30 to before 14:45 IST, early-close buffer | | `risk_manager.py:189-192`, `:180`; pending expiry (`paper_executor.py:396-403`); fill cutoff (`nifty_algo_db.py:2485-2489`) | as cited | not inspected | MATCH |
| R-30 | Exits: 45 min, 15:10, close − 5 min | Earliest applies | `mandatory_exit_reason` (`protection.py:284-301`); `max_hold_minutes` ≤ 45 | as cited | not inspected | MATCH |
| R-31 | Stop ≤ 8% of premium | Premium based, rounded up to the tick (tighter) | `ceiling_tick(entry × 0.92)` (`protection.py:25`) | as cited | not inspected | MATCH |
| R-32 | Trailing 1.5 premium points, activated at entry +1.5, never lowered | | `protection.py:180-189`, `:242-247`; persisted monotonic check (`nifty_algo_db.py:2909-2913`); the distance is fixed at 1.5 by the validator (`config.py:153-156`) | Worked example: entry 100 gives stop 92; a bid of 101.50 activates trailing; a peak of 106 gives 104.50; 110 gives 108.50 | not inspected | MATCH |
| R-33 | Target 10 to 15%, by strength | | `target_fraction` (`confidence.py:13-17`); `initial_protection` (`protection.py:27-30`) | as cited | not inspected | MATCH |
| R-34 | Pending TTL; expired entries do not use the day | | TTL 10 s; `expire_pending` (`nifty_algo_db.py:2426-2439`); EXPIRED orders are not counted (`:2266`) | as cited | not inspected | MATCH |
| R-35 | Protective exits independent of entry locks | | `protect` job every 1 s, separate from entries (`runner.py:99-120`, `:947-956`); a SELL ignores entry locks (`paper_executor.py:203-212`) | as cited | not inspected | MATCH |
| R-36 | Approved NFO calendar required, special sessions off | | `CALENDAR_UNAPPROVED` (`paper_executor.py:242-244`, `nifty_algo_db.py:2244-2253`); `SPECIAL_SESSION_DISABLED` (`calendar.py:52-53`) | as cited | not inspected | MATCH |
| R-37 | Shadow isolated | Own ledger | `ShadowBook`, `nifty_algo_shadow_*` tables | as cited | not inspected | MATCH (F-20) |
| R-38 | Replay uses the approved settings | 20/2 and the rest | Replay uses the pinned configuration, 10/3 by default | section E | not inspected | **MISMATCH** (follows R-13) |
| R-39 | Notifications cannot expose secrets or trade | | Discord signed interactions only (`nifty_discord.py:190-244`); SMTP optional (`reports.py:539-546`). Not read end to end | grep | not inspected | UNVERIFIED |
| R-40 | Authentication and ownership | Session user only | Every route is `@check_session_validity` and keys on `session["user"]`; the socket room comes from the signed session (`nifty_algo.py:34-61`); CSRF covers everything except the signed Discord route | grep and partial read | not inspected | PARTIAL (not every route read) |

## G. Runtime execution architecture

The path, as traced in code (all wired and executable unless noted):

1. **Attach.** `POST /api/nifty-algo/runner` (`blueprints/nifty_algo.py:240-254`)
   calls `attach_runner` (`runner.py:910-1004`), which registers four
   APScheduler jobs on the Python-strategy scheduler: `protect` every 1 s,
   `entries` every 5 s, `reports` every 60 s and `capture` every 5 s. Startup
   restores them through `restore_runners` (`app.py:881-898`, `runner.py:1007-1040`).
2. **Feed.** `_native_feed` (`runner.py:447-627`) requires the OpenAlgo API key
   and an authenticated native websocket. It subscribes Depth for every option of
   the selected expiry, Quote for the nearest future and NIFTY spot, and Depth for
   held contracts, which go first. The master must match the logged-in broker.
3. **Signal.** Once per 5-minute boundary (`runner.py:162-165`), `assess_current`
   (`assessment.py:92-218`) fetches 9 calendar days of 1-minute history for the
   nearest future, keeps minutes inside the effective session window, aggregates
   to 5 and 15 minutes from the session open, reads PCR (`native_data.get_pcr`) and
   calls `Rules.evaluate` (`signal_engine.py:55-213`).
4. **Readiness.** `ready` requires no UNAVAILABLE gate, passing warmup and
   freshness, a verified master, a complete session VWAP and reconciliation
   (`runner.py:182-195`).
5. **Selection.** `_entry_candidates` (`runner.py:317-392`) runs
   `Resolver.assess` over the verified master and depth quotes, applying the ATM
   rule and the liquidity gates.
6. **Admission.** `NiftyPaperExecutor.admit` (`paper_executor.py:144-481`)
   rechecks the decision, calendar, locks, moneyness against fresh spot,
   `entry_reasons` and `plan_entry`, then `store.admit_order`
   (`nifty_algo_db.py:2212-2359`) rechecks mode, safety, calendar, daily use,
   lease, state, configuration, position, reconciliation, daily loss, cash, risk,
   cooldown and monthly locks under the lock, and runs `validate_entry`
   (re-pricing and moneyness).
7. **Fill.** The `protect` job runs `process` (`paper_executor.py:569-654`): after
   `eligible_at` (+250 ms) and inside the session window, a BUY fills at ask + 1
   tick and a SELL at bid − 1 tick. `store.fill` (`nifty_algo_db.py:2452-2806`)
   repeats the cutoff, TTL, observation proof, fees, state, mode, safety, locks,
   OTM, liquidity, planned loss, reward, daily risk and cash checks, then books the
   ledger, the protection row and the depth-use record.
8. **Protection.** `monitor_exits` (`paper_executor.py:666-750`) observes the
   fresh bid through `observe_position` (`nifty_algo_db.py:2874-2936`), which uses
   `observe_bid` (`protection.py:139-281`) to set the stop, trailing stop, profit
   lock and target, applies the mandatory exits, and admits a SELL intent. The
   evaluation job adds technical invalidation and early profit booking
   (`runner.py:202-265`).
9. **Exit and journal.** A SELL fill writes `NiftyTrade` with gross, fees and net,
   the monthly net, the cooldown, and the daily lock if breached
   (`nifty_algo_db.py:2665-2803`).
10. **Reporting.** Decisions, events and trades are served by the blueprint and
    pushed over Socket.IO in room `nifty_algo:<user>` (`runner.py:925-927`).

Test-only or disconnected: `NiftyPaperExecutor.submit` always raises
(`paper_executor.py:139-140`); `risk_manager.evaluate_premium_exit` is an adapter
for tests; `Resolver.resolve` and `Resolver.candidates` are not called by the
runner, which uses `assess`.

## H. Indicator mathematics

- **ATR and SuperTrend:** see section E. The arithmetic is correct for any period
  and multiplier. The settings are wrong (F-01, F-02). With Length 20, ATR first
  becomes valid at bar 19, well inside the 80-bar warmup.
- **MACD:** EMAs seeded with an SMA, as in Pine `ta.ema`. The histogram crossover
  uses the `previous <= 0 < hist` rule (`indicators.py:95-98`), the same
  convention as `ta.crossover`. `cross_age` is the index distance from the last
  crossover (`:112`). The gate needs the crossover direction to equal the
  SuperTrend direction, an integer age within freshness, and a histogram aligned
  with the direction (`signal_engine.py:100-107`).
- **ADX:** see section E. When smoothed TR is zero, DI is 0 here; Pine
  `fixnan` would carry the previous value forward. This can occur only on flat
  data.
- **VWAP:** the source is hlc3, accumulated per IST date. Missing volume
  invalidates the rest of the session (`indicators.py:170-171`), and zero total
  volume gives `None`, so there is no fallback. Several series tokens give
  `None` (`:164-165`).
- **PCR:** see R-18 and F-06.
- **Candle completion and alignment:** 5-minute buckets are anchored at the
  effective session open. The evaluation boundary is the UTC epoch divided by
  300, which aligns with IST 09:15 because the IST offset of 19,800 s is a
  multiple of 300.
- **SDK parity:** not re-run. The historical parity documents compare against
  the SDK at 10/3 only (F-09).

## I. Contract selector and master validation

- The expiry is the nearest one that has not expired; with `avoid_expiry_day`
  (default `True`) today's expiry is excluded (`contract_resolver.py:186-217`,
  `native_data.py:326-328`). PCR uses the same expiry unless `pcr_expiry` is set,
  and the runner filters candidates to that expiry (`runner.py:334-337`).
- **ATM D-1 rule:** implemented exactly as specified, with the 25-point limit
  tied to the 50-point weekly and monthly grid (`contract_resolver.py:74-100`).
  The selector always takes the nearest expiry, which uses that grid, so the
  assumption holds. If no ATM reference exists in ATM or ITM mode, the selection
  is refused (`:229-236`).
- Candidates are the ATM strike plus up to `candidate_strike_window` (2) adjacent
  ITM strikes. Anything else is labelled `OTM_PROHIBITED` or
  `OUTSIDE_SELECTION_WINDOW` and never becomes executable (`:299-328`).
- Identity: a token listed twice with different content is refused at
  selection, admission and fill (`:153-166`, `:209-215`; `paper_executor.py:186-192`).
- Ranking: `plan_entry` scores only risk-approved lot proposals
  (`risk_manager.py:113-146`, `selection_scoring.py:18-86`). Ties break on lower
  planned loss, then lower cash, expiry, strike, token and lots.

## J. Risk and PAPER ledger

- **Sizing and limits:** see R-07 and R-27 to R-29. Cash is reserved at
  admission from the planned cash. At fill, the cost must not exceed either the
  available balance or the reservation (`nifty_algo_db.py:2638`).
- **Fees:** the NIFTY module keeps its own charge schedule (`paper_executor.py:41-54`)
  rather than `sandbox/charges.py`. STT on the option sell side is 0.0625%, while
  the platform schedule, as of 2026-11-23, carries 0.15% (F-05).
- **Accounting:** a BUY debits `available` by the cost and `equity` by the fees.
  A SELL credits proceeds and adds gross minus sell fees to equity. Net in the
  journal deducts the entry fees in proportion (`nifty_algo_db.py:2674-2711`).
  P&L is realized only; unrealized P&L is not part of the daily-loss equity
  check.
- **Concurrency:** every ledger writer takes `_lock` (an UPDATE on the state
  row) before reading mutable state (`nifty_algo_db.py:1113-1120`). Admission is
  idempotent on `intent_id`, and a fill is idempotent on order status and
  depth-use accounting.
- **Restart:** a runner lease fences ownership (`runner.py:80-97`). `reconcile`
  runs before protection (`runner.py:109-114`). Protection payloads are durable.
- **Feasibility (spec level, F-15):** under the default fee schedule, an
  ask-premium band of roughly ₹52 to ₹64 at lot size 65, or ₹45 to ₹56 at lot 75,
  passes the ₹400 loss cap and the ₹350 net-reward floor together for one lot at
  a confidence score up to 39 (the one-lot band). Two and three lots need lower
  premiums: about ₹23 to ₹32 for two lots and ₹14 to ₹21 for three, at lot 65.

## K. Live-order isolation and security

- Searches of `services/nifty_algo/`, `database/nifty_*` and
  `blueprints/nifty_*` found no import of `place_order`, the order services,
  broker modules or the Sandbox order engine. The only outbound clients are
  history (`services.history_service.get_history`, read-only), the market-data
  websocket, Discord HTTP (`discord_bot.py:268-270`) and SMTP (`reports.py`).
- The BUY path calls `LIVE_ADAPTER.submit` when the mode is not PAPER, and that
  call raises `LIVE_NOT_READY` (`paper_executor.py:171-175`). The store refuses
  again under the lock (`nifty_algo_db.py:2242`, `:2589-2590`). A LIVE mode change
  is refused unconditionally (`:1827-1828`), and the readiness codes always
  include `LIVE_NOT_READY` (`trading_mode.py:181-182`).
- Generic OpenAlgo live trading (`/api/v1/`, the strategy module, Flow, scalping)
  stays reachable to the same user through its own surfaces. That is upstream
  behaviour and not reachable from NIFTY code paths.
- CSRF: the blueprint is not exempted (`app.py:296-480`). Only the Discord
  interaction route is exempt, and it requires an Ed25519 signature
  (`nifty_discord.py:190-244`).
- Ownership: routes key on `session["user"]`. Store methods filter on `user_id`
  in every query read. Not every store method was read.
- Logging: failures log the exception type only (`safe_logging.log_failure`,
  `runner.py:305-309`). Broker status exposes booleans only (`trading_mode.py:122-138`).

## L. Frontend and API consistency

- The structured settings show selector weights, moneyness, the monthly loss
  limit and the profit target, plus read-only facts for lots, loss, reward, lock
  and trailing (`KeySettings.tsx:35-155`). **No SuperTrend, MACD, ADX, VWAP or PCR
  input is shown or editable there.** The rest is in a raw JSON textarea
  (`Workspace.tsx:219-264`), so the effective 10/3 is visible only as JSON keys.
- `PUT /configuration` accepts the full model through `active_configuration`
  (`blueprints/nifty_algo.py:199-210`). Saving pauses entries and creates a
  version (`nifty_algo_db.py:1022-1110`). The same validator runs on both sides.
- `/indicators` returns the latest decision snapshot without the settings used
  (`blueprints/nifty_algo.py:326-343`). The settings are reachable only through
  `config_id` and `/configuration`.

## M. Replay and analytics

- Replay rebuilds candles from recorded 1-minute frames and calls the same
  `Rules.evaluate` with the configuration pinned in the manifest
  (`execution_replay.py:275-294`). Research overrides may change only indicator
  and threshold fields, never risk, cost or execution (`:37-65`).
- Look-ahead guards: frame validation refuses future candles, quotes, PCR and
  calendars (`execution_replay.py:166-249`).
- Divergence: replay's VWAP-opening check is weaker than the live one (F-11).
- Effective replay settings follow the saved configuration: 10/3 by default.

## N. Existing test coverage

| Area | Classification | Evidence |
|---|---|---|
| SuperTrend 20/2 | `NO_TEST` | no test uses `atr_period=20` with `atr_multiplier=2` in `Rules`; `test_nifty_algo_experiment_api.py:46` sets `atr_period=20` only, as an experiment |
| SuperTrend 10/3 parity | `TEST_EXPECTATION_OUTDATED` | `test_nifty_algo_sdk_241_parity.py:274-279`, `:350-356`, `:387-388`, `:912-913` compare at `period=10, multiplier=3`, and `indicators.supertrend(bars)` relies on the 10/3 defaults |
| MACD age 0 to 4 | `TESTED_AND_MATCHING` | `test_nifty_algo_macd_window.py:118-137` uses the real indicator and the real gate, both directions; forming candle `:234-263` |
| MACD 12/26/9 close | `TESTED_BUT_INSUFFICIENT` | SDK parity tests exist (not read end to end) |
| ADX DI 14 / smoothing 14 | `TESTED_BUT_INSUFFICIENT` | parity at period 14 against the single-period `ta.adx` (`test_nifty_algo_sdk_241_parity.py:443-489`); no test with two distinct periods is possible |
| VWAP session hlc3 | `TESTED_AND_MATCHING` | `test_nifty_algo_sdk_241_parity.py:492-567` compares per session against `ta.vwap(..., source="hlc3")` |
| PCR feasibility on a real chain | `UNVERIFIABLE_WITH_OFFLINE_DATA` | |
| Risk, timing, fills, exits, D-1 to D-3 | not inspected in this audit | test files exist (`test_nifty_algo_phase*.py`, `test_nifty_algo_compliance.py` and others) but were not read |

Tests that depend on the default configuration (for example `cases()` in
`test_nifty_algo_macd_window.py:82-87`) would keep passing with 10/3 even
though production is meant to run 20/2.

## O. Complete findings register

| ID | Severity | Requirement | Expected | Actual | Location | Call chain | Test evidence | PAPER impact | Confidence | Recommendation (not implemented) |
|---|---|---|---|---|---|---|---|---|---|---|
| F-01 | HIGH | Gate 1 Length | 20 | `atr_period` default 10; function default 10 | `services/nifty_algo/config.py:30` `StrategyConfig.atr_period`; `indicators.py:44` `supertrend` | `NiftyRunner.evaluate` → `assess_current` → `Rules.evaluate` → `snapshot` → `supertrend(bars, config.atr_period, ...)` (`signal_engine.py:45`) | parity tests pin 10 | Every signal, both timeframes, technical exit ATR and confidence are computed with the wrong ATR period | Confirmed | Set the approved values as the versioned default with a migration of saved configurations (stricter rules apply), and expose them in the settings UI |
| F-02 | HIGH | Gate 1 Factor | 2 | `atr_multiplier` default 3 | `config.py:31`; `indicators.py:44` | same as F-01 | parity tests pin 3 | Bands sit 1.5× wider than approved, so flips and R-ST differ | Confirmed | as F-01 |
| F-03 | HIGH | MACD age 0 to 2 | Age 3 refused | `main` admits age 3 (`crossover_freshness` default 3); HEAD is correct | `main:services/nifty_algo/config.py:25`; `main:signal_engine.py:100-101` | as R-15 | HEAD has a boundary test; `main` has none | Deploying `main` admits stale crossovers | Confirmed (git) | Merge the correction; confirm the saved-configuration migration on the target install |
| F-04 | MEDIUM | Confidence consistency | Normalization follows the configured SuperTrend | `_unit(st["duration"] / 10)` and `abs(distance) / atr / 3` are constants matching the legacy 10/3 | `confidence.py:38` `signal_strength` | `Rules.evaluate` → `signal_strength` → `target_fraction`; `plan_entry` lot thresholds | none found | With 20/2 the SuperTrend term drops systematically (distance relative to 2-ATR bands), lowering lots and targets | Confirmed in code; impact size unmeasured | Derive the constants from the configured multiplier and period, or approve them explicitly as version-pinned |
| F-05 | MEDIUM | Fees included | Current statutory rates | STT sell 0.0625% (`config.py:105`) against the platform's 0.15% for options sell (`sandbox/charges.py:206`, as of 2026-11-23); exchange charge 0.05% against 0.03553%; GST base leaves out the SEBI fee; no contract-note rounding | `paper_executor.py:41-54` `_charges` | `plan_entry`, `fill`, protection net, journal | not inspected | Planned loss, projected reward and realized net are slightly understated, by about ₹3 to ₹4 per lot at typical premiums; a second fee model drifts from the platform invariant | Confirmed values; the current law itself is not independently verified | Price through `sandbox/charges.py`, or record and approve the NIFTY schedule explicitly |
| F-06 | MEDIUM | PCR freshness | Complete chain, 90 s, skew 5 s | Every listed contract of the expiry needs `ltt` within 90 s, and `max(ltt) − min(ltt)` must be ≤ 5 s | `native_data.py:331-340`; `indicators.py:207-209` | `assess_current` → `get_pcr` → `pcr` | `UNVERIFIABLE_WITH_OFFLINE_DATA` | If deep strikes trade less than every few seconds, R-PCR is always UNAVAILABLE and no entry ever qualifies. Fails closed | Conditional, unverified | Measure on a recorded session; decide whether skew is meant on quote receipt time or on last-trade time |
| F-07 | MEDIUM | Quote age | Depth freshness | Depth age is the last-trade time (`ltt`), not the depth update | `depth_quote.py:85-89`; `paper_executor.py:526-533` | selection, admission, fill, protection | not inspected | A live book with no recent trade is refused (and a protective-exit observation is marked stale); a recent trade does not prove the book is current | Conditional | Confirm which timestamp the native feed supplies for depth, and document or adjust |
| F-08 | LOW | Tests match the approved settings | 20/2 covered | Parity tests encode 10/3; no 20/2 test | `test/test_nifty_algo_sdk_241_parity.py:279`, `:353-356`, `:388`, `:912-913` | n/a | as cited | Tests stay green while the settings are wrong | Confirmed | Add 20/2 cases after the settings are approved in code |
| F-09 | LOW | Documentation | Current settings | 10/3 stated as current | section P | n/a | n/a | Misleads reviewers | Confirmed | Update the docs after the change |
| F-10 | LOW | Signal timing | Evaluate each completed candle | One assessment per 5-minute boundary, set before the fetch; R-FRESH ≤ 30 s | `runner.py:162-165`; `signal_engine.py:78-82` | evaluate job | not inspected | If the broker publishes the boundary minute late, that candle's signal is skipped and not retried. Fails closed | Confirmed logic; real frequency unverified | Retry within the boundary until the completed candle appears or 30 s pass |
| F-11 | LOW | Replay parity | Same gates as live | Replay checks only the first minute bar against the open; live also checks the first 5-minute bucket; a missing tail of an earlier session is never detected | `execution_replay.py:291`; `assessment.py:176-184`; `signal_engine.py:27-31` | `decision_at` | not inspected | Replay may accept a session VWAP that live would refuse | Confirmed in code | Share one session-completeness function |
| F-12 | LOW | Missing OI | Never treated as zero | OI stays `None`, but the liquidity volume term becomes 0 when OI is missing (`FRESH_OI_CAPS_VOLUME_MISSING_ZERO`) | `selection_scoring.py:37` | `plan_entry` → `score_plan` | not inspected | Ranking penalizes a contract with missing OI as if its OI were zero. Documented in the payload | Confirmed | Confirm this approved policy explicitly |
| F-13 | LOW | ADX two periods | DI 14 and smoothing 14 independently | One `adx_period` drives both | `indicators.py:131`, `:143`; `config.py:40` | `snapshot` → `adx` | parity at 14 | None at 14/14; any future change moves both | Confirmed | Split into `adx_di_length` and `adx_smoothing` if independence matters |
| F-14 | LOW | Hygiene | No source-rewriting tools beside the code | `apply_nifty_safety_fixes.py` and `apply_nifty_report_recovery.py` rewrite tracked sources with `--apply` and target commit `5db10c9` | repository root (`:194`, `:313` write sites) | not imported by the application | n/a | Running them on current code could revert later fixes; they refuse unexpected text, which limits the risk | Confirmed | Retire them or move them out of the root |
| F-15 | INFO | Feasibility | Entries possible under the approved rules | Feasible ask band, 1 lot: about ₹52 to ₹64 (lot 65) or ₹45 to ₹56 (lot 75); 3 lots: about ₹14 to ₹21 | arithmetic over `risk_manager.plan_entry` and `protection.initial_protection` rules | n/a | n/a | ATM or ITM NIFTY premiums with one or more days to expiry are often above this band, so entries may be rare | Computed from the approved rules; market premiums unverified | Decide whether the ₹400 cap, ₹350 floor and 8% stop are meant to coexist |
| F-16 | INFO | Spread | One definition | Gates use (ask − bid) / ask; scoring uses mid | `contract_resolver.py:31`; `nifty_algo_db.py:2621`; `selection_scoring.py:20` | | | Marginal | Confirmed | Document or unify |
| F-17 | INFO | VWAP anchor | Session | IST date reset; `instrument_kind` is never passed, so the FUT-only guard is inert at runtime | `indicators.py:158-169`; `signal_engine.py:48` | | | None for regular sessions on a future | Confirmed | Pass the instrument kind, or anchor on the session window |
| F-18 | INFO | SuperTrend initial state | As the reference | Initial direction is close against hl2, while Pine starts in a downtrend | `indicators.py:57-58` | | parity docs | Differs only before the first reversal, inside the warmup | Confirmed | none required |
| F-19 | INFO | Calendar authority | One source | Entries use the approved calendar (`nifty_session`); exit windows use the native `market_calendar_db` | `paper_executor.py:704`; `calendar.py:41-74` | | | Disagreement could close or open the exit window differently | Confirmed | Use one authority |
| F-20 | INFO | Shadow | Same timing rules | Shadow entries skip the early-close buffer and the monthly locks, which is documented | `shadow.py:31-47` | | | Research only | Confirmed | none |
| F-21 | INFO | Inventory | Clean tree | Upstream `"openalgo": "file:.."` creates a recursive junction; the ignored `tmp/` holds 37k+ files from earlier runs | `frontend/package.json:61` | | | Tooling hazard, not runtime | Confirmed | none for NIFTY |

**Counts (first pass):** CRITICAL 0, HIGH 3, MEDIUM 4, LOW 7, INFO 7. The
second pass adds F-22 to F-31 (section U). The combined counts are CRITICAL 0,
HIGH 3, MEDIUM 5, LOW 13, INFO 10.

## P. Documentation contradictions

SuperTrend 10/3 stated as the strategy setting, which conflicts with the approved
20/2:

- `docs/nifty-algo/STRATEGY_ASSUMPTIONS.md:21` says "SuperTrend uses ATR 10 and
  multiplier 3".
- `docs/nifty-algo/STRATEGY_ASSUMPTIONS.md:106` gives the confidence
  normalization as "/ 10" and "/ (3 ATR)" (see F-04).
- `docs/nifty-algo/SDK_241_PARITY.md:35-36`, `:88` and `:299-300` give the
  parity basis as ATR(10) and SuperTrend(10,3).
- `NIFTY_INDICATOR_PARITY_AUDIT.md:27`, `:31`, `:239` and `:306` compare against
  `ta.supertrend(..., 10, 3.0)` and reason about "a 3-ATR band".

MACD freshness: `test/test_nifty_algo_offline_acceptance.py:16` and historical
documents describe `cross_age <= 3`. That is superseded by
`docs/nifty-algo/MACD_THREE_CANDLE_WINDOW_2026-11.md` on this branch only.

The historical NIFTY documents were not read end to end. Other contradictions may
exist.

## Q. Unverified external dependencies

- Completeness and accuracy of the broker instrument master: strike ladders, lot
  size and tick size. The code checks only OpenAlgo's download status and the date.
- Whether the native feed's `ltt` and `received_time` are present and meaningful
  for depth snapshots (F-06, F-07).
- Broker 1-minute history latency and completeness at each boundary (F-10).
- The current NIFTY lot size and the statutory charge rates (F-05, F-15).
- The 1,000-symbol subscription capacity for a full expiry chain
  (`runner.py:557-558`).
- That the native market calendar and the trader-approved calendar agree (F-19).
- Real fill quality: modelled fills at ask + 1 tick and bid − 1 tick on the best
  level only.

## R. Prioritized remediation roadmap (recommendations only)

1. Align SuperTrend with the approved 20/2: change the defaults through a new
   strategy version with a migration, expose both inputs in the structured
   settings, and add 20/2 tests and parity checks (F-01, F-02, F-08).
2. Merge the MACD three-candle correction to `main` (F-03).
3. Decide the confidence normalization for 20/2 and pin it in a version (F-04).
4. Reconcile the fee schedule with `sandbox/charges.py` (F-05).
5. Measure PCR and depth freshness on a recorded live session before relying on
   entries, and decide which timestamp is meant (F-06, F-07).
6. Revisit risk feasibility against real premiums (F-15).
7. Unify the session-completeness check between live and replay, and use one
   calendar authority (F-11, F-19).
8. Update the historical documentation (F-09) and retire the root hotfix scripts
   (F-14).

**Nothing here has been implemented.**

## S. Final coverage reconciliation

Tracked files, in non-overlapping categories:

```
inventoried       = 4,055
fully_reviewed    =    36   (after the second pass; 19 after the first)
binary_inspected  =     0
generated_reviewed=     0
access_blocked    =     0
not_reviewed      = 4,019
36 + 0 + 0 + 0 + 4,019 = 4,055
```

Ignored files (674,053) are inventoried by directory in C.2 and are all
`NOT_REVIEWED`. A further unknown number of files could not be listed: the
permission-denied `tmp/nifty-*` and `.pytest_cache` directories and the deep
`node_modules` paths whose names were too long.

**Not reviewed:** every tracked file whose manifest status is `NOT_REVIEWED`,
including the 10 partly read files whose ranges are in the manifest notes. That
covers all broker adapters, all shared infrastructure, all tests except part of
one, all frontend files except one, all workflows and all documentation except
targeted searches.


## U. Second pass (2026-11-24): skills and deeper reading

The trader asked for a complete check using the project's skills, with scope
limited to NIFTY plus the shared modules it calls, and the pass kept read-only.
This section records that pass. Sections A to T above remain the first-pass
record. Coverage figures in B and S were regenerated, and the manifest in C.1
reflects both passes.

### U.1 Coverage added in this pass

Every file in `services/nifty_algo/` (32 files, about 11,400 lines) has now been
read end to end, as have `blueprints/nifty_algo.py`, `blueprints/nifty_discord.py`
and `utils/db_sessions.py`. In total 36 tracked files are now
`FULL_TEXT_REVIEWED`, up from 19. `database/nifty_algo_db.py` has been read
except lines 3953 to 5095 (recording, experiment, opportunity and
report-storage methods).

Still not read end to end:

- the rest of `database/nifty_algo_db.py`
- `database/nifty_notifications.py` and `database/nifty_notification_ops.py`
- most of `database/nifty_replay_storage.py` and
  `database/nifty_research_analytics.py`
- every NIFTY frontend file except `KeySettings.tsx`
- every NIFTY test except part of one
- every historical NIFTY document

Audit coverage stays **`INCOMPLETE`**.

### U.2 `fd-audit` skill (static; nothing measured)

Resources checked and their release on success, exception and retry paths:

| Resource | Where acquired | Release | Result |
|---|---|---|---|
| NIFTY store sessions | `NiftyStore.sessions = sessionmaker(...)` (`nifty_algo_db.py:652`), over the shared main engine from `create_db_engine` | every use is `with self.sessions()` or `with self.sessions.begin()` | released on every path |
| Shared scoped sessions read from scheduler jobs (`database.symbol`, `auth_db`, `market_calendar_db`, `settings_db`, `user_db`, broker master-contract modules) | runner jobs | each job runs inside `app.app_context()` (`runner.py:930-935`); popping the context fires `teardown_appcontext` → `remove_all_scoped_sessions` (`app.py:1114-1124`, `utils/db_sessions.py:157-175`). `_load_instruments` and `_session` also remove in `finally` (`native_data.py:42-43`, `assessment.py:25-28`, `calendar.py:73-74`) | released |
| `master_contract_status_db` sessions | `SessionLocal()` per call | `session.close()` in that module | released (outside the scoped-session registry by design) |
| Worker-process engines | `create_db_engine(...)` in `notification_worker.main` and `replay_worker.main` | `engine.dispose()` in `finally` | released |
| HTTP | Discord only, through the shared `get_httpx_client()` with `timeout=5` and no redirects (`discord_bot.py:264-284`) | shared client; `cleanup_httpx_client()` on worker exit | no per-call client |
| SMTP | `utils.email_utils.send_email` with `timeout=20` (reports) or `timeout=5` (fallback) | inside that shared helper | not re-read in this pass |
| Files | calendar blob `open("xb")` in `with`, unlinked if the DB write fails (`nifty_algo_db.py:700-741`); report PDFs through `write_atomic` (`mkstemp` + `fdopen` in `with`, `os.replace`, unlink on any exception, `reports.py:88-105`); archive and report reads in `with` or `read_bytes` | context managers | released |
| Threads, executors, subprocesses | none created by NIFTY code; jobs run on the shared Python-strategy APScheduler | n/a | none |
| WebSocket callbacks and subscriptions | `register_callback` on the shared native client (`runner.py:464-472`); NIFTY-owned subscriptions tracked in `owned_subscriptions` | unregistered on client change and in `close()`; non-wanted owned subscriptions released each feed cycle (`runner.py:537-540`) | released. `close()` clears `owned_subscriptions` without unsubscribing (`runner.py:907`); it runs only at shutdown, so this is not a leak |
| Module-level state | `_ATTACH_LOCKS` (`runner.py:29`) and `app.extensions["nifty_algo_runners"]`, both keyed by user (single-user) | cleared at shutdown | bounded by the key space |
| SocketIO rooms | `join_room(nifty_algo:<session user>)` | `leave_room` on unsubscribe; Flask-SocketIO drops rooms on disconnect | bounded |
| Per-tick caches | `ReportService._sessions` (`reports.py:580`) | the service is rebuilt each tick and cleared in `due_periods` | bounded |

**Result: no descriptor or memory leak found.** The check was static only; no
descriptor counts were measured. Two growth observations follow, neither of
them a leak:

- **F-23 (INFO): durable tables grow without any retention policy.** These
  include `nifty_algo_decision` (one row per completed 5-minute assessment),
  `nifty_algo_event` (`contract_selector:*` events hold up to 100 candidate rows
  each) and the research tables. All reads are row-limited, so this is disk
  growth only.
- **F-24 (INFO): month-end and milestone reports load a full month of events,
  payloads included, into memory** (`report_inputs`, `nifty_algo_db.py:5167-5178`).
  The memory is released after the tick. Filtering on the event kinds the report
  uses would reduce the peak.

### U.3 `security-review` skill

The branch diff is empty, so the review was run over the NIFTY scope instead.
Confirmed controls:

- Every NIFTY route uses `@check_session_validity` and takes the user from
  `session["user"]`.
- Every lookup by bare primary key re-checks the owner (`trade_detail`,
  `observe_exit_study`, `observe_shadow`, `finish_notification`).
- CSRF covers everything except the Discord interaction route. That route checks
  the Ed25519 signature over the raw body before parsing, limits the timestamp
  to ±300 s and caps the body at 64 KiB (`nifty_discord.py:190-244`,
  `discord_bot.py:98-110`).
- Discord commands are read-only apart from `ack`, which never resolves an
  incident. Each command requires a configured user or role, guild, channel and
  application (`discord_bot.py:449-476`).
- Outbound Discord traffic goes to a fixed origin with no redirects.
- Report and archive paths are resolved inside their root (`reports.py:77-85`,
  `nifty_replay_storage.py:208-217`).
- Calendar uploads are capped at 2 MB, and PDFs are parsed with strict pypdf.
- Exceptions are logged with their type only (`safe_logging.py`).
- Broker status leaves the server as booleans only.

**Result: no vulnerability at confidence ≥ 8.** None was reported.

### U.4 `code-review` skill

The review ran at `high` effort on `services/nifty_algo`. Its findings are in U.6.

### U.5 New findings from the deeper reading

| ID | Severity | Finding | Evidence | Impact | Recommendation (not implemented) |
|---|---|---|---|---|---|
| F-22 | LOW | Replay expires a pending entry at the TTL or `entry_before`, whichever comes first, but omits the early-close buffer that live PAPER applies | `execution_replay.py:665-668`, compared with `paper_executor.py:396-403` | On an early-close day, replay can fill an entry admitted within 10 s of the buffer that live would have expired. Narrow, research only | Share one expiry function |
| F-23 | INFO | No retention on decision, event or research tables | U.2 | Disk growth | Define retention |
| F-24 | INFO | Month-scale report input loads every event payload | U.2 | Transient memory peak | Filter by kind |

Confirmed correct in this pass, with no finding:

- The ledger reconciliation invariant `equity == available + Σ(entry_price × qty)`
  agrees with fill accounting (`nifty_algo_db.py:1985`, `:2641-2642`,
  `:2674-2710`).
- Analytics refuse inconsistent fill evidence (`ledger_analytics.py:31-141`).
- Replay applies the same R-gates, D-1 moneyness at fill, re-pricing, cooldown
  and monthly locks as live PAPER.
- Shadow positions never write primary tables, and mirror P&L is non-additive.

### U.6 Code-review results

The `code-review` skill (effort `high`, target `services/nifty_algo`) reported
eight findings. Each was checked against the code read in this audit, and all
eight hold. The severities below are this audit's; the review's own label is in
brackets. One duplicate was merged into F-22.

| ID | Severity | Finding | Evidence | Failure scenario | Recommendation (not implemented) |
|---|---|---|---|---|---|
| F-22 | LOW [review: important] | Replay omits the early-close buffer on pending-entry expiry (also found independently in U.5) | `execution_replay.py:665-668` and `paper_executor.py:402-403` | Close at 13:00; admitted at 12:54:58 with a 10 s TTL. Paper expires it at 12:55:00; replay fills at 12:55:08 and force-exits at once, paying both sides of the charges | Add `window[1] - SESSION_EXIT_BUFFER` to the replay `min()` |
| F-25 | LOW [important] | At an exact midpoint across a gap, the D-1 ATM rule labels the upper strike ATM: the 25-point check is `<=`, and the missing lower strike is never checked | `contract_resolver.py:95-100` | Listed CE {24900, 25000}, 24950 missing, spot 24975. 25000 is labelled ATM, while on the complete grid 24950 is ATM and CE 25000 is OTM by 25 points. Selection, admission, the locked write and fill all accept it | Require the grid strike nearest spot to be listed, or treat the exact midpoint as unverified when the lower strike is missing |
| F-26 | MEDIUM [important] | The MACD recency term `1 − age/(crossover_freshness + 1)` changes meaning with the 3.2.0 narrowing (denominator 4 → 3), while `confidence_method` stays `five-indicator-v1` | `confidence.py:42`; migration `config.py:227-234` | Age 2: recency 0.5 → 0.333, about −1.67 points. A 40.5-point signal (2 lots) becomes about 38.8 (1 lot), and its target fraction falls | Normalize against a fixed constant or version the method; confirm that the effect is approved (related to F-04) |
| F-27 | LOW [pre-existing] | ITM mode quietly picks a deeper ITM strike when the adjacent one is missing | `contract_resolver.py:237-248` | CE, spot 24990, ATM 25000, 24950 missing: 24900 is selected as "adjacent" | Refuse `ITM_STRIKE_UNAVAILABLE` when the strike one interval inside ATM is not listed. ATM is the default mode, so this applies only under `selection="ITM"` |
| F-28 | LOW [pre-existing] | The pending-entry cutoff is the literal 14:45, not `config.entry_before`, at admission and in the store fill | `paper_executor.py:398`; `nifty_algo_db.py:2485-2487` | With `entry_before=14:00`, an entry admitted at 13:59:55 can fill at 14:00:05; replay expires it at 14:00:00. Matches the approved 14:45 default | Use `config.entry_before` in both places |
| F-29 | LOW [nit] | `SelectionUnavailable` (for example `ATM_REFERENCE_UNVERIFIED`) falls into the generic `except Exception`, is logged as a traceback and shown as `DATA_PIPELINE_UNAVAILABLE` | `runner.py:300-309`, `:346-373` | Each eligible boundary with spot outside the ladder logs an exception, and the trader sees a misleading data-pipeline fault | Catch `SelectionUnavailable` beside `OrderRefused` and report its code |
| F-30 | INFO [nit] | The 5-minute exit buffer is duplicated as a literal | `risk_manager.py:11`; `protection.py:295` | Changing one without the other admits entries inside the forced-exit window | Share one constant |
| F-31 | LOW [nit] | A 3.2.0 configuration with `crossover_freshness > 2` is refused with an empty field location, so the trader cannot tell which setting failed | `config.py:157-161`; `blueprints/nifty_algo.py:102-110` | `PUT /configuration` returns 400 with `fields: [[]]` | Use a field-level validator |

**Combined counts across both passes:** CRITICAL 0, HIGH 3, MEDIUM 5, LOW 13,
INFO 10.

## T. Final read-only verification

| Item | Result |
|---|---|
| Starting Git status | clean |
| Ending Git status | one new untracked file: `docs/nifty-algo/COMPLETE_STRATEGY_CODEBASE_AUDIT.md` (verified after writing) |
| Existing user changes | none existed; nothing else touched |
| Files changed by this audit | this report only |
| Code, settings, configuration or tests changed | none |
| Tests added | none |
| Commits, pushes, PRs | none |
| Trading actions, broker or notification contact | none |
| Database access | read-only, immutable row counts of the `nifty_algo_*` tables only |
| Helper scripts | written to the session scratchpad outside the repository; they read files and wrote only this report |
