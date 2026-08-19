# Protocol — PLAN-BULL-KNOBS-002

**Status:** PLANNED (regimen-ready design; not launched)  
**Master task:** _(emit creates MASTER)_  
**Kind:** `offline_analysis`  
**Family:** `regime_bull_knobs`  
**Regimen:** `docs/testing/TEST_REGIMEN_E2E.md`

## 1. Hypothesis
Bull live knobs under-deploy or over-trade vs scorecard winner

## 2. Non-goals
- No live util loosen without Brad + gates
- No run while regime≠bull (emit_only_when_regime=bull)
- Not a placeholder for 001 — 001 was zombie process abort; 002 is the real test

## 3. Design
| Item | Value |
|------|--------|
| Control / baseline | live_bull_fingerprint |
| Arms | live_bull_fingerprint, scorecard_bull_winner, USDC_hurdle |
| Data | bull OHLCV windows + scorecard |
| Primary window | **bull_windows** |
| Context windows | btc_30d_ge_15 |
| Runner | `phase6/research/run_regime_bull_knobs_test.py` |

## 4. Success criteria (frozen before run)
| Gate | Value |
|------|--------|
| primary_window | bull_windows |
| min_n_trades | 15 |
| beat baseline ret+dd | True |
| usdc_hurdle | True |
| sparse_is | inconclusive_not_promote |
| live_promote_allowed | False |
| CR accept only if | beats live bull + USDC on primary; DD bound; N>=15 |

## 5. Outcome classes
`HIT_CRITERIA` | `EDGE_VS_BAGS_ONLY` | `inconclusive_sparse_N` | `unstable_or_no_edge` | `process_incomplete`

## 6. Decision path
1. Emit → MASTER Type:test → pickup → runner  
2. `finalize-report` with outcome block  
3. `review-request` → Brad `decide` + `--follow-on`  
4. Packet under `docs/testing/decisions/`

## 7. Emit gates (PARKED) + historical validation 2026-08-17
**Historical premise:** **PASS** (`HIT_CRITERIA`) on long BTC tape — see `reports/REGIME_BEAR_BULL_HISTORICAL_2026-08-17.md`.  
**Still parked** for live-regime shadow confirm. No live writes. Layered re-entry paper-only.

Unpark paths (either):
1. **Live transition** — detector bull (e.g. BTC 30d ≥ +15%) → weekly `emit`  
2. **Historical dig** — already run 2026-08-17:
   ```bash
   OPENBLAS_CORETYPE=GENERIC .venv/bin/python3 phase6/research/run_regime_bear_bull_historical_dig.py
   ```

`emit_only_when_regime`: **bull**  
`allow_historical_backtest`: **true**  
Do **not** auto-emit into flat/bear/transition.

## 8. Placeholder policy
This is a **real** future test design, not a stub to close. Do **not** `decide drop/abort` until a run produces outcome evidence (or genuine process zombie after launch).
