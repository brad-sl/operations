# Handoff — ANALYST-REGIME-BULL-KNOBS-20260824

**Plan ID:** `PLAN-BULL-KNOBS-002`  
**Workstream:** `WS-REGIME-KNOBS`  
**Status:** QUEUED (strategy-emitted)  
**MASTER:** `docs/MASTER_TASK_TRACKING.md` → `ANALYST-REGIME-BULL-KNOBS-20260824`  
**Strategy:** `docs/testing/ANALYST_TEST_STRATEGY.md`  
**Regimen:** `docs/testing/TEST_REGIMEN_E2E.md`  
**Protocol:** `docs/testing/trials/PLAN-BULL-KNOBS-002_PROTOCOL.md`

## Hypothesis
Bull live knobs under-deploy or over-trade vs scorecard winner

## Success metric
Beat live bull + USDC hurdle on bull windows; DD bound

## Success criteria (frozen)
```json
{
  "primary_window": "bull_windows",
  "min_n_trades": 15,
  "must_beat_baseline_ret_pp": 0.0,
  "must_beat_baseline_dd_pp": 0.0,
  "require_both_ret_and_dd": true,
  "usdc_hurdle": true,
  "sparse_is": "inconclusive_not_promote",
  "live_promote_allowed": false,
  "shadow_ok_if": "primary_pass_and_n_ok",
  "cr_accept_only_if": "beats live bull + USDC on primary; DD bound; N>=15"
}
```

## Regime focus
bull

## Kind
`offline_analysis` · family `regime_bull_knobs`

## Must
- Real data only; isolation where code changes
- Freeze success_criteria **before** scoring
- Report under `reports/` + JSON with `outcome.class` + N
- `finalize-report` → REVIEW → Brad `decide` + `--follow-on` + decision packet
- No live config write without Brad + promotion gates

## Must not
- Fake prices / synthetic edge when ledger empty
- Silent promote to `regime_cash_policy.json`
- Promote on sparse N or EDGE_VS_BAGS_ONLY alone
- Close as drop without evidence if this is a real planned test (not zombie)

## Hooks
- OPT: `n/a`
- Live policy fingerprint: read `config/regime_cash_policy.json` at start; record hash in report

## Done when
- Honest recommendation enum + n / uncertainty
- CR ACCEPT/REJECT logged; follow_on explicit
- Strategy roadmap item marked done after decide
