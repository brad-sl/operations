# Handoff — ANALYST-REGIME-TRANSITION-20260727

**Plan ID:** `PLAN-TRANSITION-001`  
**Workstream:** `WS-REGIME-KNOBS`  
**Status:** QUEUED (strategy-emitted)  
**MASTER:** `docs/MASTER_TASK_TRACKING.md` → `ANALYST-REGIME-TRANSITION-20260727`  
**Strategy:** `docs/testing/ANALYST_TEST_STRATEGY.md`

## Hypothesis
Transition cap/park settings drive unnecessary whipsaw or idle cash

## Success metric
Real transition slices; prefer lower whipsaw cost

## Regime focus
transition

## Kind
`offline_analysis` · family `regime_transition`

## Must
- Real data only; isolation where code changes
- Report under `reports/` + JSON
- End REPORT_READY; Brad decides via `trial_cycle.py decide`
- No live config write without Brad + promotion gates

## Must not
- Fake prices / synthetic edge when ledger empty
- Silent promote to `regime_cash_policy.json`

## Hooks
- OPT: `n/a`
- Live policy fingerprint: read `config/regime_cash_policy.json` at start; record hash in report

## Done when
- Honest recommendation enum + n / uncertainty
- Strategy roadmap item marked done after decide
