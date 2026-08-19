# Handoff — ANALYST-REGIME-BULL-KNOBS-20260803

**Plan ID:** `PLAN-BULL-KNOBS-001`  
**Workstream:** `WS-REGIME-KNOBS`  
**Status:** CLOSED — decision `abort` 2026-08-17 (zombie; no report). Successor `PLAN-BULL-KNOBS-002` gated to live regime=bull.  
**MASTER:** `docs/MASTER_TASK_TRACKING.md` → `ANALYST-REGIME-BULL-KNOBS-20260803`  
**Strategy:** `docs/testing/ANALYST_TEST_STRATEGY.md` + `data/state/trials/TEST_STRATEGY.json`

## Hypothesis
Bull live knobs under-deploy or over-trade vs scorecard winner

## Success metric
Beat live bull + USDC hurdle on bull windows; DD bound

## Regime focus
bull

## Kind
`offline_analysis` · family `regime_bull_knobs`

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
