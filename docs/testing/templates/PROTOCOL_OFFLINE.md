# Protocol — <TRIAL_ID>

**Master task:** `<MASTER_ID or none>`  
**Kind:** `offline_analysis`  
**Family:** `<family>`  
**Regimen:** `docs/testing/TEST_REGIMEN_E2E.md`

## 1. Hypothesis
<one falsifiable sentence>

## 2. Non-goals
- No live trading config / regime policy writes without Brad + promotion gates
- Real data only
- Short windows are context only; primary window decides

## 3. Design
| Item | Value |
|------|--------|
| Control / baseline | |
| Arms | |
| Data | Coinbase public daily / ledger path |
| Primary window | long_tape \| … |
| Context windows | last_14d, last_90d |
| Fees | |
| Runner | `phase6/research/run_….py` |

## 4. Success criteria (frozen before run)

| Gate | Value |
|------|--------|
| primary_window | <PRIMARY_WINDOW> |
| min_n_trades | ≥ 15 (or justify) |
| must_beat_baseline_ret_pp | ≥ 0 |
| must_beat_baseline_dd_pp | ≥ 0 |
| require_both_ret_and_dd | true |
| sparse_is | inconclusive_not_promote |
| live_promote_allowed | false |
| sensor_preflight_ok | true (outcome `sensor_ok`) |

**CR accept only if** primary window passes all gates above AND `sensor_preflight.outcome_class == "sensor_ok"`.

## 5. Outcome recording
Report must set `outcome.class` ∈  
`HIT_CRITERIA` | `EDGE_VS_BAGS_ONLY` | `inconclusive_sparse_N` | `unstable_or_no_edge` | `process_incomplete` | `sensor_broken` | `sensor_degenerate` | `sensor_thin` | `method_invalid`

## 6. Decision path
1. `trial_cycle.py finalize-report …` → REPORT_READY  
2. `trial_cycle.py review-request <ID>` → REVIEW_PENDING + inbox  
3. Brad: `trial_cycle.py decide <ID> <enum> --note ‘…’ --follow-on …`

## 7. Follow-on policy
| If | Then |
|----|------|
| HIT_CRITERIA | propose_scoped_experiment or promote_* via gates |
| sparse | extend_trial with longer tape / lower TF **or** drop |
| no_edge / bags-only | drop; follow_on none unless Brad opens one door |
| process_incomplete | abort or re-run under full regimen |

## 8. Notify
Decision packet under `docs/testing/decisions/` + DECIDED inbox (+ TG when agent/cron delivers).

