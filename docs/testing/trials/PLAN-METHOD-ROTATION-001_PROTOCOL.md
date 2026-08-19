# Protocol — PLAN-METHOD-ROTATION-001

**Status:** PLANNED (regimen-ready design; not launched)  
**Master task:** _(emit creates MASTER)_  
**Kind:** `offline_analysis`  
**Family:** `method_rotation_21d`  
**Regimen:** `docs/testing/TEST_REGIMEN_E2E.md`

## 1. Hypothesis
Scorecard rotation winner still beats production path on fresh window

## 2. Non-goals
- No auto-apply OPT winner to live
- No fishing new packs without stale scorecard trigger

## 3. Design
| Item | Value |
|------|--------|
| Control / baseline | production_path |
| Arms | defensive_rotation_21d, production_path, control_no_swap |
| Data | ANALYST-OPT scenario pack + compare-production |
| Primary window | **fresh_opt_window** |
| Context windows | prior_scorecard |
| Runner | `phase6/research (analyst_opt_scenario_pack / compare-production)` |

## 4. Success criteria (frozen before run)
| Gate | Value |
|------|--------|
| primary_window | fresh_opt_window |
| min_n_trades | 15 |
| beat baseline ret+dd | True |
| usdc_hurdle | False |
| sparse_is | inconclusive_not_promote |
| live_promote_allowed | False |
| CR accept only if | leaderboard delta + compare-production pass honesty classes; not bags-only |

## 5. Outcome classes
`HIT_CRITERIA` | `EDGE_VS_BAGS_ONLY` | `inconclusive_sparse_N` | `unstable_or_no_edge` | `process_incomplete`

## 6. Decision path
1. Emit → MASTER Type:test → pickup → runner  
2. `finalize-report` with outcome block  
3. `review-request` → Brad `decide` + `--follow-on`  
4. Packet under `docs/testing/decisions/`

## 7. Emit gates
Emit when scorecard stale or capacity free after higher prio; real OPT pack test.  
`emit_only_when_regime`: —

## 8. Placeholder policy
This is a **real** future test design, not a stub to close. Do **not** `decide drop/abort` until a run produces outcome evidence (or genuine process zombie after launch).
