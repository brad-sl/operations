# Handoff — ANALYST-REGIME-FLAT-KNOBS-20260730

**Plan ID:** `PLAN-FLAT-KNOBS-001`  
**Workstream:** `WS-REGIME-KNOBS`  
**Status:** QUEUED (strategy-emitted)  
**MASTER:** `docs/MASTER_TASK_TRACKING.md` → `ANALYST-REGIME-FLAT-KNOBS-20260730`  
**Strategy:** `docs/testing/ANALYST_TEST_STRATEGY.md`

## Hypothesis
Under live flat option B envelope (cap $75, RSI≤55, sent≥0.25), rebalance beats rotation on real flat + live_overlap windows (Path B 2026-07-30 stress: rotation −3.5% flat / high DD; rebalance ~flat DD). A nearby cap/RSI/sent grid may improve return or DD without promoting bull-only rotation knobs.

## Success metric
Primary: rebalance_7d vs rotation_7d vs defensive_rebalance_14d under B fingerprint on flat + live_overlap OHLCV with honest RSI/sentiment notes (Path B gap). Secondary: grid cell beats live-B on return or maxDD with min n. No live write — shadow only if wins + param_audit clean.

## Regime focus
flat, live_overlap

## Kind
`offline_analysis` · family `regime_flat_knobs`

## Must
- Real data only; isolation where code changes
- Report under `reports/` + JSON
- End REPORT_READY; Brad decides via `trial_cycle.py decide`
- No live config write without Brad + promotion gates

## Must not
- Fake prices / synthetic edge when ledger empty
- Silent promote to `regime_cash_policy.json`

## Hooks
- OPT: `regime_cash_param_sweep_or_scorecard + run_reentry_knob_stress`
- Live policy fingerprint: read `config/regime_cash_policy.json` at start; record hash in report

## Done when
- Honest recommendation enum + n / uncertainty
- Strategy roadmap item marked done after decide


---

## DIG 2026-07-30 — Layered bull re-entry arm

**Spec:** `docs/research/BULL_REENTRY_LAYERED_SPEC.md`  
**Module:** `phase6/research/bull_reentry_layered.py`  
**Dig report:** `reports/REGIME_FLAT_KNOBS_DIG_LAYERED_2026-07-30.md`  
**Stress:** `data/state/analyst_breakout_reentry_stress_latest.json`

### Extended hypothesis
Bear veto + breakout ON + BTC RSI∈[50,70] → cap **$75 rebalance**; BTC 30d≥15% → size-up **$200**. Catch more short bulls than 30d/15-only without full-size breakout.

### Dig result
- Enum: `propose_scoped_experiment`
- Shadow layered: **True**
- Live: **False**

Keep flat option B rebalance (not rotation). ADD scoped shadow experiment: layered bull re-entry (bear veto + breakout + RSI 50–70 @ $75 rebalance; 30d≥15% size-up $200 only). Do NOT live-edit regime_cash_policy. Reject breakout @$200 and 5d+RSI full bull flip.
