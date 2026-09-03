# Method Rotation 21d Test — 2026-09-02

**Trial:** `ANALYST-METHOD-ROTATION-21D-20260902-TRIAL`  
**Master:** `ANALYST-METHOD-ROTATION-21D-20260902`  
**Plan:** `PLAN-METHOD-ROTATION-001`  
**Generated:** 2026-09-02T19:38:48Z (OPT) / report finalize same day  
**Real data only:** True  
**Live config writes:** False  
**OPT run_id:** `OPT-20260902-193848`

## Go / no-go (plain English)

**NO GO** — do not shadow, do not promote.

Candidate `defensive_rotation_21d` is green on the **fresh** slice (+19.25% ret, 0.83% DD, n=14) and beats idle `control_no_swap` on return (+18.03 pp), but it **fails frozen success criteria**:

1. **n=14 < min_n_trades=15** → `inconclusive_sparse_N`
2. **DD not ≤ control** (cand DD 0.83 vs control 0.0; Δdd=−0.83 pp)
3. **Full-tape context is red** (−22.58% ret, 34.57% DD) — not window-stable
4. Control is **near-idle** (exposure≈3.6%, n=1) so return edge is partly exposure, not pure swap skill
5. `--compare-production` “beats production” uses deposit-adjusted live % vs fixed-$1k sim — **not** CR-grade honesty alone

**Recommendation enum:** `continue_observe_only`  
**Shadow go?** **False**  
**Live promote?** **False**  
**outcome.class:** `inconclusive_sparse_N`  
**primary_pass:** **false**

## Hypothesis

Scorecard rotation winner still beats production path on fresh window.

## Success criteria (frozen before scoring)

```json
{
  "primary_window": "fresh_opt_window",
  "fresh_opt_window": {"start": "2026-05-01", "end": "2026-09-02"},
  "min_n_trades": 15,
  "must_beat_baseline_ret_pp": 0.0,
  "must_beat_baseline_dd_pp": 0.0,
  "require_both_ret_and_dd": true,
  "sparse_is": "inconclusive_not_promote",
  "live_promote_allowed": false,
  "shadow_ok_if": "primary_pass_and_n_ok",
  "cr_accept_only_if": "leaderboard delta + compare-production pass honesty classes; not bags-only",
  "baseline_arm": "control_no_swap",
  "candidate_arm": "defensive_rotation_21d"
}
```

## Tier 0 — isolation

- `./run_backtest.sh phase6/research/test_isolation_scenario_knob_parity.py` → **PASS** (`ANALYST-OPT R1 isolation PASS`)
- No live `trading_config` / `regime_cash_policy` writes
- Policy fingerprint (read-only): `781f0f0112fad43c…`
- Knob map fingerprint (read-only): `f0d91ccfda82bc60…`
- OHLCV data_end: `2026-09-02`

## Tier 1 — fresh OPT window (primary)

**Window:** 2026-05-01 → 2026-09-02 (bars_min≈125)  
**Pack:** `phase6/research/scenarios/method_rotation_21d_20260902.json`  
**Command:**

```bash
./run_backtest.sh phase6/research/run_scenario_leaderboard.py \
  --pack phase6/research/scenarios/method_rotation_21d_20260902.json \
  --compare-production --skip-live-param-audit-gate
```

| Arm | Role | Return % | Max DD % | Sharpe | n trades | Exposure % |
|-----|------|----------|----------|--------|----------|------------|
| defensive_rotation_21d | candidate | 19.25 | 0.83 | 8.964 | 14 | 81.0 |
| control_no_swap | baseline (rebalance, no rotation swaps) | 1.22 | 0.0 | 10.747 | 1 | 3.6 |
| baseline_7d_fresh | context weekly rotation | 14.33 | 2.83 | 5.155 | 38 | 63.6 |

### Gate score

| Gate | Value | Pass? |
|------|-------|-------|
| n_primary ≥ 15 | 14 | **False** |
| beat control ret (Δret≥0) | +18.03 pp | **True** |
| beat control DD (Δdd≥0, lower DD better) | −0.83 pp | **False** |
| require both ret+dd | true | **False** |

**primary_pass = false**

## Tier 1b — context windows

| Scenario | Window | Return % | Max DD % | n |
|----------|--------|----------|----------|---|
| defensive_rotation_21d_prior_bull | 2025-10-01..2025-12-31 | 5.5 | 0.0 | 8 |
| control_no_swap_prior_bull | same | 0.46 | 0.01 | 2 |
| defensive_rotation_21d_full_tape | 2025-04-20..2026-09-02 | −22.58 | 34.57 | 95 |
| control_no_swap_full_tape | full tape | 0.47 | 2.91 | 3 |

Prior scorecard (2026-08-30): **bull** optimal=`defensive_rotation_21d`; **recent/flat** optimal=`usdc_hold`.

Context note: on fresh window, candidate also beats weekly `baseline_7d_fresh` on ret (+4.92 pp) and DD (+2.0 pp better) — interesting but **does not override** frozen baseline=`control_no_swap` + n gate.

## Production compare (honesty)

- Overlap coverage: `partial` window `2026-04-20..2026-09-02`
- Live deposit-adjusted return: **−58.78%** (unadjusted NAV Δ **+163.48%** — deposits inflate raw NAV)
- Candidate vs that metric: beats_production=True, delta≈+78.03 pp
- **Do not treat as CR accept** — different capital path, flows, and fees; sim is fixed $1k ARCH-4 isolation.

## Outcome

```json
{
  "class": "inconclusive_sparse_N",
  "primary_pass": false,
  "n_primary": 14,
  "delta_ret_pp": 18.03,
  "delta_dd_pp": -0.83
}
```

## CR / decide

Suggest **REJECT** promote and shadow. Optional follow-on: `extend` same frozen arms until n≥15, or `none` and keep scorecard as research-only.

```bash
python3 phase6/research/trial_cycle.py decide ANALYST-METHOD-ROTATION-21D-20260902-TRIAL continue_observe_only \
  --note 'sparse n=14; failed DD+stability; no shadow' --follow-on none
```

## Artifacts

- JSON: `reports/METHOD_ROTATION_21D_TEST_2026-09-02.json`
- MD: `reports/METHOD_ROTATION_21D_TEST_2026-09-02.md`
- Leaderboard: `data/state/analyst_scenario_leaderboard_latest.json` (run `OPT-20260902-193848`)
- Pack: `phase6/research/scenarios/method_rotation_21d_20260902.json`
- Protocol: `docs/testing/trials/PLAN-METHOD-ROTATION-001_PROTOCOL.md`
- Handoff: `handoffs/analyst/Handoff_ANALYST-METHOD-ROTATION-21D-20260902.md`
