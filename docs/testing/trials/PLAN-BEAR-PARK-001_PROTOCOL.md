# Protocol — PLAN-BEAR-PARK-001

**Status:** PLANNED (regimen-ready design; not launched)  
**Master task:** _(emit creates MASTER)_  
**Kind:** `offline_analysis`  
**Family:** `regime_bear_park`  
**Regimen:** `docs/testing/TEST_REGIMEN_E2E.md`

## 1. Hypothesis
Strict park minimizes loss vs any tactical bear deploy on real bears

## 2. Non-goals
- No live regime_cash_policy write without Brad + gates
- No bull/flat knob fishing under bear label

## 3. Design
| Item | Value |
|------|--------|
| Control / baseline | live_bear_or_tactical_default |
| Arms | USDC_full_park, tactical_small_deploy, live_bear_fingerprint |
| Data | Coinbase public OHLCV + scorecard bear windows |
| Primary window | **bear_historical_slices** |
| Context windows | last_bear_episode, long_tape_bear_mask |
| Runner | `phase6/research/run_regime_bear_park_test.py` |

## 4. Success criteria (frozen before run)
| Gate | Value |
|------|--------|
| primary_window | bear_historical_slices |
| min_n_trades | 15 |
| beat baseline ret+dd | True |
| usdc_hurdle | True |
| sparse_is | inconclusive_not_promote |
| live_promote_allowed | False |
| CR accept only if | park beats tactical on maxDD and terminal on primary; N>=15 |

## 5. Outcome classes
`HIT_CRITERIA` | `EDGE_VS_BAGS_ONLY` | `inconclusive_sparse_N` | `unstable_or_no_edge` | `process_incomplete`

## 6. Decision path
1. Emit → MASTER Type:test → pickup → runner  
2. `finalize-report` with outcome block  
3. `review-request` → Brad `decide` + `--follow-on`  
4. Packet under `docs/testing/decisions/`

## 7. Emit gates (PARKED) + historical validation 2026-08-17
**Historical premise:** **PASS** (`HIT_CRITERIA`) on long BTC tape — see `reports/REGIME_BEAR_BULL_HISTORICAL_2026-08-17.md`.  
**Still parked** for live-regime shadow confirm. No live writes.

Unpark paths (either):
1. **Live transition** — detector `regime=bear` → weekly `emit` auto-includes this plan  
2. **Historical backtest** — already run 2026-08-17; re-run:
   ```bash
   OPENBLAS_CORETYPE=GENERIC .venv/bin/python3 phase6/research/run_regime_bear_bull_historical_dig.py
   ```

`emit_only_when_regime`: **bear**  
`allow_historical_backtest`: **true**  
Do **not** auto-emit into flat/bull/transition.

## 8. Placeholder policy
This is a **real** future test design, not a stub to close. Do **not** `decide drop/abort` until a run produces outcome evidence (or genuine process zombie after launch).
