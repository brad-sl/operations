# Handoff — ANALYST-METHOD-ROTATION-21D-20260817

**Plan ID:** `PLAN-METHOD-ROTATION-001`  
**Workstream:** `WS-METHODOLOGY`  
**Status:** QUEUED (strategy-emitted)  
**MASTER:** `docs/MASTER_TASK_TRACKING.md` → `ANALYST-METHOD-ROTATION-21D-20260817`  
**Strategy:** `docs/testing/ANALYST_TEST_STRATEGY.md`  
**Regimen:** `docs/testing/TEST_REGIMEN_E2E.md`  
**Protocol:** `docs/testing/trials/PLAN-METHOD-ROTATION-001_PROTOCOL.md`

## Hypothesis
Scorecard rotation winner still beats production path on fresh window

## Success metric
Leaderboard delta + --compare-production; honest brief

## Success criteria (frozen)
```json
{
  "primary_window": "fresh_opt_window",
  "min_n_trades": 15,
  "must_beat_baseline_ret_pp": 0.0,
  "must_beat_baseline_dd_pp": 0.0,
  "require_both_ret_and_dd": true,
  "sparse_is": "inconclusive_not_promote",
  "live_promote_allowed": false,
  "shadow_ok_if": "primary_pass_and_n_ok",
  "cr_accept_only_if": "leaderboard delta + compare-production pass honesty classes; not bags-only"
}
```

## Regime focus
bull, flat

## Kind
`offline_analysis` · family `method_rotation_21d`

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
- OPT: `analyst_opt_scenario_pack`
- Live policy fingerprint: read `config/regime_cash_policy.json` at start; record hash in report

## Done when
- Honest recommendation enum + n / uncertainty
- CR ACCEPT/REJECT logged; follow_on explicit
- Strategy roadmap item marked done after decide
