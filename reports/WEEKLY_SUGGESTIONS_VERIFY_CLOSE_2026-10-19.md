# WEEKLY SUGGESTIONS VERIFY-CLOSE — 2026-10-19

**Task:** t_d73918fd (crypto-engineer)  
**Source:** WEEKLY-SUGGESTIONS-20261018 carries from reverse-stack GO 2026-10-17 + Analyst weekly  
**Objective:** Prove already-live (or career/measure) so no re-implement. Smoke + tests + receipt + MASTER append.

## Verified per ID

| Analyst ID | Status | Evidence Path | Notes |
|------------|--------|---------------|-------|
| **W-TRYOUT-INTAKE-VS-KINDLING** | LIVE | `config/tryout_decision_discipline.json` (live_apply:true, min_eng_absolute:0.4, min_setup_score:1.7, min_setup_confidence:0.6); `data/state/tryout_decision_discipline_latest.json` (STAND_DOWN on eng=0.3767<0.4); `data/state/rsi_event_tryout_seat_composer_latest.json` (discipline ran live_apply=true); brad_go_intake_hygiene 2026-10-17 raise from lower bars | Matches expected: eng≥0.40 / setup≥1.7 / conf≥0.60; live_apply on discipline path. Recent run blocked weak eng seat. |
| **W-FLAT-BALLAST-BEFORE-SHELL** | LIVE | `config/flat_deploy_priority.json` (live_apply:true, as_of:2026-10-17, brad_go:2026-10-17_brad_go_d2..., reserve_before_shell:true, deploy_cap_usd:75); `data/state/rsi_event_tryout_seat_composer_latest.json` (d2_flat_deploy: live_apply true, block_shell true, prefer ballast, shells_ok false); `data/state/soft_down_reverse_stack_go_latest.json` (lane1 D2 live) | D2 blocks new tryout shells in flat/transition while ballast gap. |
| **W-BALLAST-PROFIT-GATE** | LIVE | `config/ballast_under_target_floor.json` (live_apply:true, as_of:2026-10-17, brad_go:2026-10-17_brad_go_c2..., max_step_usd:75, pairs:BTC/ETH, roles:ballast_core); membership_sizing_matrix dig_out_shadow (would step 75 on BTC/ETH); composer + soft_down confirm; matrix rows show current gap but C2 unblocks max_add on apply path (analyst notes BTC now $75 via c2) | C2 floor inject (~$75) on BTC/ETH under target. |
| **W-PROCESS-TAX-ETH-SL** | CAREER_DONE | `reports/E_ETH_BALLAST_SL_CAREER_2026-10-12.md` (ETH ~$240 ballast_core two-lot, -18.90 8% SL after +3.95% MFE green-then-die; explicit **no SL knob**); `config/sl_width_arming_policy.json` (live_apply:false for W2, W3_never_tighten_after_green, default 0.08); `config/trading_config_phase6.json` (stop_loss_pct:0.08); soft_down (no_go_global_8_to_3); demoted in MASTER 2026-10-12 | Career shipped 2026-10-12; **no** new SL knob. 3% remains tryout-only. |

## Isolation Tests (re-run)

- `scripts/phase6/test_isolation_ballast_under_target_floor.py` → **11 OK** (PASS)
- `scripts/phase6/test_isolation_flat_deploy_priority.py` → **8 OK** (PASS)

## Residual Gaps (explicit — no silent all-green)

- Bank-trail-while-green still **MEASURE_ONLY** (sunday gate N_INSUFFICIENT; see soft_down lane2)
- W2 shell-only 3% fuse **WIRED_SHADOW_PENDING_14D** (live_apply:false until >=14d; kill ready)
- Ballast still micro: BTC ~$53 vs ~$403 target, ETH $0 (C2 unblocks max_add but no fill yet; next rebalance)
- Under-target floor / profit-gate active but held low; tryout intake now stricter (good) but no new shells per D2
- Alt-shell SL RCA (ADA/TIA/LINK this week) is separate card (t_7560d64d / t_fe8ec847); not touched
- No change to PAXG, global SL%, scale-window, dwell, etc. per must-not

## Receipts / State

- This report: `reports/WEEKLY_SUGGESTIONS_VERIFY_CLOSE_2026-10-19.md`
- Machine: `data/state/weekly_suggestions_verify_close_latest.json`
- Soft-down reference: `reports/SOFT_DOWN_REVERSE_STACK_GO_LATEST.md` + `data/state/soft_down_reverse_stack_go_latest.json`
- Analyst: `reports/ANALYST_WEEKLY_TRADE_REVIEW_AGENT_LATEST.md`

## MASTER Update

Appended disposition + verified table under WEEKLY-SUGGESTIONS-20261018 (see git diff or section).

**All four IDs now have explicit LIVE / CAREER_DONE status with paths. No re-implementation performed.**

as_of: 2026-10-19T20:xx (post smoke + tests)
Task: t_d73918fd
