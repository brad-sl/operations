# Kelly Sizing Test — 2026-07-21

**Trial:** `ANALYST-KELLY-SIZING-TEST-20260721-TRIAL`  
**Master:** `ANALYST-KELLY-SIZING-TEST-20260721`  
**Generated:** 2026-07-21T22:41:03.830397+00:00  
**Real data only:** True  
**Live config writes:** False

## Executive summary

- Closed sells (plausible \(r\)): **n=70**  (raw nonzero PnL sells=89, outliers dropped=3)
- Edge: **p=0.428571** (Wilson 95% {'low': 0.3194, 'high': 0.5452}), **b=1.870122** (mean win r / mean |loss r|)
- Kelly: **f_full=0.123014**, **f_half=0.061507**, **f_quarter=0.030753**
- After multi-asset haircut 0.5: f_half_eff=0.030753, f_quarter_eff=0.015377
- **Recommendation enum:** `drop`  
- **Shadow go?** **False** — recent window n=37 has non-positive Kelly (f_full=0.0, p=0.189189); full-sample f_full=0.1230 is unstable / regime-shifted. Path DD: half=39.5% vs baseline=24.0%.
- Full Kelly as live default: **REJECT**

## Tier 0 — isolation

- Article 55%/2:1 → f_full=0.32500000000000007 (expect 0.325), half=0.16250000000000003 (expect 0.1625)
- Module: `phase6/research/kelly_sizing.py`
- Tests: `PYTHONPATH=. python3 phase6/research/test_isolation_kelly_sizing.py`

## Tier 1 — ledger edge

Return definition: `r = pnl / (qty * exit_price - pnl)` (implied entry notional).
Filter: `|r| <= 0.5`, entry notional >= $1.0.

### Full plausible sample

```json
{
  "label": "full_plausible",
  "n": 70,
  "n_wins": 30,
  "n_losses": 40,
  "p": 0.428571,
  "b": 1.870122,
  "mean_win_r": 0.077985,
  "mean_loss_r": -0.041701,
  "f_full": 0.123015,
  "f_half": 0.061507,
  "f_quarter": 0.030754,
  "insufficient": false,
  "reason": null,
  "p_wilson_95": {
    "low": 0.3194,
    "high": 0.5452
  },
  "b_usd_avg_win_loss": 1.592283,
  "sum_pnl_usd": 40.4708,
  "insufficient_for_recommend": false,
  "min_n_gate": 30
}
```

### Since 2026-07-01

```json
{
  "label": "since_2026-07-01",
  "n": 37,
  "n_wins": 7,
  "n_losses": 30,
  "p": 0.189189,
  "b": 1.148835,
  "mean_win_r": 0.031926,
  "mean_loss_r": -0.02779,
  "f_full": 0.0,
  "f_half": 0.0,
  "f_quarter": 0.0,
  "insufficient": false,
  "reason": null,
  "p_wilson_95": {
    "low": 0.0948,
    "high": 0.3421
  },
  "b_usd_avg_win_loss": 2.13396,
  "sum_pnl_usd": -38.9463,
  "insufficient_for_recommend": false,
  "min_n_gate": 15
}
```

### Pair slices (n ≥ 15)

```json
[
  {
    "label": "pair:ADA-USD",
    "n": 21,
    "n_wins": 13,
    "n_losses": 8,
    "p": 0.619048,
    "b": 2.804695,
    "mean_win_r": 0.064922,
    "mean_loss_r": -0.023147,
    "f_full": 0.483221,
    "f_half": 0.24161,
    "f_quarter": 0.120805,
    "insufficient": false,
    "reason": null,
    "p_wilson_95": {
      "low": 0.4088,
      "high": 0.7925
    },
    "b_usd_avg_win_loss": 1.162107,
    "sum_pnl_usd": 7.1214,
    "insufficient_for_recommend": false,
    "min_n_gate": 15
  }
]
```

## Tier 1b — offline path compare

Sequential single-bet proxy on the same plausible return sequence. Envelopes: live deploy_pct / flat regime util / min reserve. Kelly paths use **haircutted** f. Baseline uses **1% equity risk language** per trade.

| Path | f_risk | End equity | Growth % | Max DD % | Near reserve |
|------|--------|------------|----------|----------|--------------|
| baseline_1pct_risk | 0.010000 | 913.2681 | 22.0653 | 23.9809 | False |
| quarter_kelly_capped | 0.015377 | 996.5699 | 33.1992 | 34.4854 | False |
| half_kelly_capped | 0.030753 | 1082.3677 | 44.6667 | 39.5018 | False |
| half_kelly_no_multi_haircut | 0.061507 | 1082.3677 | 44.6667 | 39.5018 | False |
| full_kelly_capped | 0.061507 | 1082.3677 | 44.6667 | 39.5018 | False |

### Production live (deposit-adjusted context)

```json
{
  "start_equity_usd": 748.18,
  "end_equity_usd": 2583.42,
  "total_return_pct_deposit_adj": -22.02,
  "trade_count": 320,
  "realized_pnl_usd": 479.61
}
```

## Risk fraction vs notional deploy_pct

- Live `deploy_pct`=0.72 (notional budget on cash/equity), SL=0.03
- Book simultaneous SL if fully deployed ≈ 0.0216
- Map half-eff f → candidate deploy_pct ≈ 0.95 (Notional deploy_pct ≈ f_risk/sl after haircut; distinct from risk fraction. Do not set live without Brad+gates.)

```json
{
  "position_usd": 387.51300000000015,
  "raw_position_usd": 2648.3053789107703,
  "f_requested": 0.030753482347943076,
  "f_effective": 0.004500000000000001,
  "binding_constraint": "regime_util_budget",
  "details": {
    "equity": 2583.42,
    "cash_usd": 1291.71,
    "already_deployed_usd": 1291.71,
    "deploy_pct": 0.72,
    "regime_target_max_util_pct": 0.65,
    "min_reserve_usd": 50.0,
    "caps": {
      "raw": 2648.305379,
      "deploy_pct_budget": 568.3524,
      "regime_util_budget": 387.513,
      "reserve_cash_room": 1241.71,
      "max_position_usd": 800.0
    }
  }
}
```

## Tier 2 — shadow

```json
{
  "status": "no_go",
  "overlay_sketch": null
}
```

## Honest assessment

```json
{
  "sample_n": 70,
  "p": 0.428571,
  "b": 1.870122,
  "p_ci_95": {
    "low": 0.3194,
    "high": 0.5452
  },
  "recent_july_edge_negative": true,
  "estimation_error_trap": "Small n and contaminated basis make p,b unstable; half-Kelly still large if p overestimated \u2014 prefer quarter + hard caps.",
  "notional_vs_risk": "Live runner sizes BUY as cash*weight*deploy_pct (notional), not loss-at-stop. Kelly f must map through /sl_pct then clamp \u2014 engineer follow-on if executor still conflates 1% notional with 1% risk.",
  "correlation_gap": "Path model is sequential independent bets; live book is concurrent and correlated \u2014 haircut 0.5 is a blunt prior, not estimated \u03a3.",
  "full_kelly_live": "REJECT \u2014 never recommend as live default."
}
```

## Decide (Brad)

```bash
python3 phase6/research/trial_cycle.py decide ANALYST-KELLY-SIZING-TEST-20260721-TRIAL drop --note 'see reports/KELLY_SIZING_TEST_2026-07-21.json'
```

## Files

- `reports/KELLY_SIZING_TEST_2026-07-21.json`
- `reports/KELLY_SIZING_TEST_2026-07-21.md`
- `phase6/research/kelly_sizing.py`
- `phase6/research/test_isolation_kelly_sizing.py`
- `phase6/research/run_kelly_sizing_test.py`

