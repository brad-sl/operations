# Regime Transition Test — 2026-07-27

**Trial:** `ANALYST-REGIME-TRANSITION-20260727-TRIAL`  
**Master:** `ANALYST-REGIME-TRANSITION-20260727`  
**Generated:** 2026-07-27T17:09:33.099420+00:00  
**Real data only:** True  
**Live config writes:** False

## Executive summary

- Hypothesis: Transition cap/park settings drive unnecessary whipsaw or idle cash
- Transition-labeled days (BTC lookback detector): **n=66**  episodes=40
- Whipsaw flip_rate: **0.2057**  (into_t=40, out_t=39)
- Scorecard (recent {'start': '2026-02-01', 'end': '2026-07-07'}): winner **usdc_hold**  alt_beats_usdc=False
- Live ledger on transition days: trades=2 buys=0 sells=2 sell_pnl_usd=-17.9711
- Path proxy (transition days): park ret%=0.6349 dd%=0.0 | util0.45 ret%=1.0067 dd%=8.0818 | util0.65 ret%=0.9978 dd%=11.6146
- DD penalty residual vs park (pp): **8.0818**  return gap residual−park (pp): **0.3718**
- **Recommendation enum:** `drop`  
- **Shadow go?** **False** — Real transition/recent scorecard + BTC transition-day proxy favor park/USDC over faster flip or higher util. Hypothesis that cap/park causes costly idle cash is NOT supported — whipsaw/DD cost of deploy dominates. Drop faster-flip / raise-cap change for transition.
- Confidence: medium-high

## Tier 0 — isolation

- Overall pass: **True**
- Live detect: `transition` btc_ret=11.475

```json
[
  {
    "name": "test_isolation_regime_detector_freshness",
    "pass": true,
    "rc": 0,
    "stdout_tail": "  (detect also uses fresh end)\nregime_detector freshness isolation PASS\n"
  },
  {
    "name": "transition_band_classify",
    "pass": true,
    "detail": [
      {
        "ret_pct": 11.0,
        "expect": "transition",
        "got": "transition",
        "ok": true
      },
      {
        "ret_pct": -9.0,
        "expect": "transition",
        "got": "transition",
        "ok": true
      },
      {
        "ret_pct": 16.0,
        "expect": "bull",
        "got": "bull",
        "ok": true
      },
      {
        "ret_pct": -12.0,
        "expect": "bear",
        "got": "bear",
        "ok": true
      },
      {
        "ret_pct": 3.0,
        "expect": "flat",
        "got": "flat",
        "ok": true
      },
      {
        "ret_pct": -5.0,
        "expect": "flat",
        "got": "flat",
        "ok": true
      }
    ]
  },
  {
    "name": "live_detect_known_set",
    "pass": true,
    "regime": "transition"
  }
]
```

## Policy fingerprint (start-of-run)

- `regime_cash_policy.json` sha256: `24d2f0b95f63700239b7943ae4fb054ffe9570ba00e23868a85dd7e96a0370bd`
- `regime_knob_map.json` sha256: `a3f43f75f013df0839587f0a24ebf731d8ab612969251d19becd26e9af39081b`

```json
{
  "transition_policy_json": {
    "strategy_mode": "usdc_park",
    "allow_new_buys": false,
    "target_max_util_pct": 0.45,
    "rebalance_cap_usd": 50.0,
    "min_cash_reserve_pct": 0.45
  },
  "live_status_snapshot": {
    "regime": "transition",
    "strategy_mode": "usdc_park",
    "allow_new_buys": false,
    "rebalance_cap_usd": 0.0,
    "target_max_util_pct": 0.45,
    "knob_map_scenario": "usdc_hold",
    "as_of": "2026-07-27T16:10:51.167353+00:00"
  },
  "knob_map_transition": {
    "scenario_id": "usdc_hold",
    "strategy_mode": "usdc_park",
    "live_overlay": {
      "global_settings.rebalance_cap_usd": 0.0,
      "global_settings.risk_free_preference": "USDC",
      "global_settings.risk_free_apy_pct": 3.5
    },
    "note": "scorecard recent optimal=usdc_hold ann=3.5001% best_alt=defensive_rebalance_14d alt_ann=2.1185% (max annualized vs USDC carry)"
  },
  "note": "Policy JSON has transition rebalance_cap_usd=50 park; live status/knob_map effective cap=0 usdc_hold \u2014 fingerprint both; no writes performed."
}
```

## Tier 1 — real transition slices

- Detector thresholds: `{"lookback_days": 30, "bull_return_pct": 15.0, "bear_return_pct": -10.0, "flat_abs_pct": 8.0}`
- Series days: 419; regime counts: `{'flat': 245, 'transition': 66, 'bear': 78, 'bull': 30}`
- Sample gates met: **True** (min_days=14, min_episodes=3)

### Episodes

```json
{
  "n_episodes": 40,
  "n_short_le3": 39,
  "n_long_ge7": 1,
  "median_days": 1,
  "mean_days": 1.65,
  "mean_btc_ret_short": -9.7e-05,
  "mean_btc_ret_long": 0.023708,
  "episodes_tail": [
    {
      "start": "2026-02-03",
      "end": "2026-02-05",
      "days": 3,
      "btc_compound_return": 0.009071,
      "btc_max_dd": 0.020568,
      "n_day_returns": 3
    },
    {
      "start": "2026-02-20",
      "end": "2026-02-20",
      "days": 1,
      "btc_compound_return": -0.027291,
      "btc_max_dd": 0.027291,
      "n_day_returns": 1
    },
    {
      "start": "2026-03-01",
      "end": "2026-03-01",
      "days": 1,
      "btc_compound_return": 0.009309,
      "btc_max_dd": 0.0,
      "n_day_returns": 1
    },
    {
      "start": "2026-03-04",
      "end": "2026-03-04",
      "days": 1,
      "btc_compound_return": -0.027552,
      "btc_max_dd": 0.027552,
      "n_day_returns": 1
    },
    {
      "start": "2026-03-07",
      "end": "2026-03-09",
      "days": 3,
      "btc_compound_return": 0.03752,
      "btc_max_dd": 0.005638,
      "n_day_returns": 3
    },
    {
      "start": "2026-03-11",
      "end": "2026-03-12",
      "days": 2,
      "btc_compound_return": 0.045557,
      "btc_max_dd": 0.0,
      "n_day_returns": 2
    },
    {
      "start": "2026-03-14",
      "end": "2026-03-14",
      "days": 1,
      "btc_compound_return": 0.001182,
      "btc_max_dd": 0.0,
      "n_day_returns": 1
    },
    {
      "start": "2026-04-04",
      "end": "2026-04-05",
      "days": 2,
      "btc_compound_return": 0.008683,
      "btc_max_dd": 0.003769,
      "n_day_returns": 2
    },
    {
      "start": "2026-04-16",
      "end": "2026-04-16",
      "days": 1,
      "btc_compound_return": -0.003686,
      "btc_max_dd": 0.003686,
      "n_day_returns": 1
    },
    {
      "start": "2026-04-19",
      "end": "2026-04-19",
      "days": 1,
      "btc_compound_return": 0.00114,
      "btc_max_dd": 0.0,
      "n_day_returns": 1
    },
    {
      "start": "2026-06-01",
      "end": "2026-06-01",
      "days": 1,
      "btc_compound_return": -0.030727,
      "btc_max_dd": 0.030727,
      "n_day_returns": 1
    },
    {
      "start": "2026-07-27",
      "end": "2026-07-27",
      "days": 1,
      "btc_compound_return": 0.047663,
      "btc_max_dd": 0.0,
      "n_day_returns": 1
    }
  ]
}
```

### Whipsaw

```json
{
  "n_days": 419,
  "flips": 86,
  "flip_rate": 0.2057,
  "flip_into_transition": 40,
  "flip_out_of_transition": 39,
  "regime_counts": {
    "flat": 245,
    "transition": 66,
    "bear": 78,
    "bull": 30
  }
}
```

## Tier 1b — offline path compare (transition days)

On days labeled transition by live detector thresholds, blend real BTC 1d returns with USDC daily yield at fixed util. Proxy for residual risk / limited deploy — not full multi-asset ARCH-4 (see scorecard for that).

| Path | util | n_days | Return % | Max DD % |
|------|------|--------|----------|----------|
| usdc_park_util0 | 0.0 | 66 | 0.6349 | 0.0 |
| live_effective_status_park_cap0 | 0.0 | 66 | 0.6349 | 0.0 |
| half_live_util0_225 | 0.225 | 66 | 0.8883 | 3.9952 |
| live_policy_util0_45 | 0.45 | 66 | 1.0067 | 8.0818 |
| faster_flip_util0_65 | 0.65 | 66 | 0.9978 | 11.6146 |
| full_btc_util1 | 1.0 | 66 | 0.7228 | 17.5736 |

### Whipsaw cost lens

```json
{
  "definition": "Proxy: transition flip_rate * (max_dd of residual util0.45 \u2212 max_dd of park) on transition-day BTC series; plus short-episode count share.",
  "flip_rate": 0.2057,
  "short_episode_share": 0.975,
  "dd_penalty_residual_vs_park_pp": 8.0818,
  "return_gap_residual_minus_park_pp": 0.3718
}
```

## Scorecard multi-asset (recent → transition map)

```json
{
  "available": true,
  "regime_key": "recent",
  "date_range": {
    "start": "2026-02-01",
    "end": "2026-07-07"
  },
  "winner_id": "usdc_hold",
  "alt_beats_usdc": false,
  "usdc_hold": {
    "id": "usdc_hold",
    "total_return_pct": 1.4812,
    "max_drawdown_pct": 0.0,
    "annualized_return_pct": 3.5001,
    "total_trades": 0,
    "sharpe_ratio": 34.403,
    "engine": "usdc_carry"
  },
  "best_alt": {
    "id": "defensive_rebalance_14d",
    "total_return_pct": 0.9,
    "max_drawdown_pct": 3.34,
    "annualized_return_pct": null,
    "total_trades": 3,
    "sharpe_ratio": 1.196,
    "engine": "arch4"
  },
  "top_scenarios": [
    {
      "id": "usdc_hold",
      "total_return_pct": 1.4812,
      "max_drawdown_pct": 0.0,
      "annualized_return_pct": 3.5001,
      "total_trades": 0,
      "sharpe_ratio": 34.403,
      "engine": "usdc_carry"
    },
    {
      "id": "defensive_rebalance_14d",
      "total_return_pct": 0.9,
      "max_drawdown_pct": 3.34,
      "annualized_return_pct": null,
      "total_trades": 3,
      "sharpe_ratio": 1.196,
      "engine": "arch4"
    },
    {
      "id": "rebalance_7d",
      "total_return_pct": 0.9,
      "max_drawdown_pct": 3.41,
      "annualized_return_pct": null,
      "total_trades": 3,
      "sharpe_ratio": 0.856,
      "engine": "arch4"
    },
    {
      "id": "bear_window_rebalance_21d",
      "total_return_pct": 0.68,
      "max_drawdown_pct": 2.48,
      "annualized_return_pct": null,
      "total_trades": 3,
      "sharpe_ratio": 1.136,
      "engine": "arch4"
    },
    {
      "id": "baseline_7d",
      "total_return_pct": -1.03,
      "max_drawdown_pct": 6.35,
      "annualized_return_pct": null,
      "total_trades": 61,
      "sharpe_ratio": -0.458,
      "engine": "arch4"
    },
    {
      "id": "defensive_rotation_21d",
      "total_return_pct": -2.01,
      "max_drawdown_pct": 2.01,
      "annualized_return_pct": null,
      "total_trades": 10,
      "sharpe_ratio": -10.96,
      "engine": "arch4"
    }
  ]
}
```

## Live ledger by regime (detector day tag)

```json
{
  "trades_total": 334,
  "unlabeled_day_trades": 0,
  "by_regime": {
    "bear": {
      "n": 69,
      "buys": 39,
      "sells": 30,
      "pnl_usd_sells": 61.5986,
      "top_pairs": [
        [
          "ADA-USD",
          22
        ],
        [
          "XRP-USD",
          10
        ],
        [
          "OP-USD",
          8
        ],
        [
          "SOL-USD",
          7
        ],
        [
          "ETH-USD",
          5
        ]
      ]
    },
    "flat": {
      "n": 143,
      "buys": 129,
      "sells": 14,
      "pnl_usd_sells": -18.6209,
      "top_pairs": [
        [
          "BTC-USD",
          22
        ],
        [
          "SOL-USD",
          20
        ],
        [
          "OP-USD",
          14
        ],
        [
          "ETH-USD",
          13
        ],
        [
          "XRP-USD",
          13
        ]
      ]
    },
    "bull": {
      "n": 36,
      "buys": 22,
      "sells": 14,
      "pnl_usd_sells": 432.9718,
      "top_pairs": [
        [
          "SOL-USD",
          9
        ],
        [
          "XRP-USD",
          7
        ],
        [
          "BTC-USD",
          6
        ],
        [
          "DOGE-USD",
          6
        ],
        [
          "ETH-USD",
          5
        ]
      ]
    },
    "unknown_unlabeled": {
      "n": 84,
      "buys": 33,
      "sells": 50,
      "pnl_usd_sells": 3.4879,
      "top_pairs": [
        [
          "DOGE-USD",
          11
        ],
        [
          "ARB-USD",
          11
        ],
        [
          "AVAX-USD",
          10
        ],
        [
          "ADA-USD",
          10
        ],
        [
          "LINK-USD",
          10
        ]
      ]
    },
    "transition": {
      "n": 2,
      "buys": 0,
      "sells": 2,
      "pnl_usd_sells": -17.9711,
      "top_pairs": [
        [
          "ADA-USD",
          1
        ],
        [
          "SOL-USD",
          1
        ]
      ]
    }
  },
  "transition": {
    "n": 2,
    "buys": 0,
    "sells": 2,
    "pnl_usd_sells": -17.9711,
    "top_pairs": [
      [
        "ADA-USD",
        1
      ],
      [
        "SOL-USD",
        1
      ]
    ]
  }
}
```

## Validation / production context

```json
{
  "validation_latest": {
    "run_id": "RCV-20260726T110055Z-555e07",
    "verdict": "pass",
    "live_setup_regime": "transition",
    "modeled_winner": "usdc_hold",
    "alt_beats_usdc_carry": false
  },
  "production_live_metrics": {
    "id": "production_live",
    "label": "Production (live ledger)",
    "engine": "live",
    "initial_capital": 1000.0,
    "total_return_pct": -23.43,
    "realized_pnl_usd": 461.47,
    "net_buy_usd": 1440.0,
    "trade_count": 334,
    "live_rebalances_executed": 25,
    "end_equity_usd": 2556.3,
    "sharpe_ratio": null,
    "max_drawdown_pct": null,
    "start_equity_usd": 726.44,
    "net_external_flows_usd": 2000.07,
    "total_return_pct_unadjusted": 251.89,
    "deposit_adjusted": true
  }
}
```

## Honest assessment

```json
{
  "north_star": "returns AND less loss \u2014 prefer lower whipsaw cost over chasing transition upside",
  "policy_vs_effective": "JSON transition cap=$50.0 allow_buys=False mode=usdc_park; status cap=0.0 allow_buys=False mode=usdc_park scenario=usdc_hold",
  "idle_cash_claim": "Idle cash in transition is intentional USDC carry. Opportunity cost exists only if deploy edge beats USDC after DD \u2014 scorecard recent window does not show that.",
  "whipsaw_claim": "Residual util 0.45 on transition BTC days adds DD vs pure park; short episodes amplify label flip cost if strategy toggles deploy aggressively.",
  "limitations": [
    "BTC-blend path is a single-asset proxy; live book is multi-pair and concurrent.",
    "OHLCV gap filled only at live end day \u2014 mid-gap days not interpolated.",
    "Ledger regime tags use detector as-of trade day (lookback ending that day).",
    "No live config write; promote only via Brad + gates."
  ]
}
```

## Decide (Brad)

```bash
python3 phase6/research/trial_cycle.py decide ANALYST-REGIME-TRANSITION-20260727-TRIAL drop --note 'see reports/REGIME_TRANSITION_TEST_2026-07-27.json'
```

## Files

- `reports/REGIME_TRANSITION_TEST_2026-07-27.json`
- `reports/REGIME_TRANSITION_TEST_2026-07-27.md`
- `phase6/research/run_regime_transition_test.py`
- `phase6/research/regime_detector.py`
- `config/regime_cash_policy.json` (read-only fingerprint)

