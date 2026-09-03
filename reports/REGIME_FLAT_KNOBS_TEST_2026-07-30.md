# Regime Flat Knobs Test — 2026-07-30

**Trial:** `ANALYST-REGIME-FLAT-KNOBS-20260730-TRIAL`  
**Master:** `ANALYST-REGIME-FLAT-KNOBS-20260730`  
**Generated:** 2026-07-30T20:52:29.584962+00:00  
**Real data only:** True  
**Live config writes:** False

## Executive summary (plain English)

Keep flat option B as-is (rebalance-style small cap, not rotation). Evidence: on real flat and live-overlap OHLCV, rotation under the same $75 envelope takes much more drawdown for little/no extra return. Nearby Path B cap grid does not clearly beat live B. Do not promote bull rotation knobs into flat. RSI/sent not proven in harness — leave gates. Live is not in flat right now anyway.

- **Recommendation enum:** `continue_observe_only`  
- **Shadow go?** **False**  
- **Confidence:** medium-high  
- **Primary hyp (rebalance > rotation under B):** **True**  
- Sample windows: `{"flat": {"date_range": {"start": "2026-01-01", "end": "2026-03-31"}, "approx_days": 90, "gate_met": true, "n_ok_scenarios": 4}, "live_overlap": {"date_range": {"start": "2026-04-20", "end": "2026-07-30"}, "approx_days": 102, "gate_met": true, "n_ok_scenarios": 4}}`

### Reasons

- Primary hyp SUPPORTED: rebalance under B envelope beats rotation on DD/Sharpe on flat + live_overlap (Path B real OHLCV)
- Scorecard flat winner remains usdc_hold (true APY) — risk styles do not beat cash on flat window
- Nearby cap/freq grid does not materially beat live-B rebalance_7d cap75; cap differentiation often weak at low Path B exposure
- RSI/sentiment grid NOT testable in Path B — leave live B gates (RSI≤55, sent≥0.25) unchanged
- Live detector is `transition` (not flat) — flat B knobs are latent until flat returns; no live apply regardless
- No live regime_cash_policy / knob_map writes in this trial

## Tier 0 — isolation

- Overall pass: **True**

```json
[
  {
    "name": "test_isolation_scenario_knob_parity",
    "pass": true,
    "rc": 0,
    "stdout_tail": "97286}\nDEBUG: eligible pairs=['DOGE-USD', 'BTC-USD', 'ETH-USD', 'SOL-USD', 'XRP-USD']\nDEBUG: after reserve available=701.3627976238747 weight=548.6027978705675 adjusted={'DOGE-USD': 167.12784813353682, 'BTC-USD': 95.15981533700108, 'ETH-USD': 95.16034417023354, 'SOL-USD': 95.98783926545381, 'XRP-USD': 95.1669509643423}\nr1b arch4 runner OK id=baseline_7d sharpe=-3.004\nANALYST-OPT R1 isolation PASS\n",
    "stderr_tail": "No eligible pairs for deployment (source=allocator_fallback)\nNo eligible pairs for deployment (source=allocator_fallback)\n"
  },
  {
    "name": "test_isolation_live_param_audit_gate",
    "pass": true,
    "rc": 0,
    "stdout_tail": "live_param_audit_gate isolation PASS\n",
    "stderr_tail": ""
  },
  {
    "name": "flat_cap_75",
    "pass": true,
    "got": 75.0
  },
  {
    "name": "flat_max_rsi_55",
    "pass": true,
    "got": 55.0
  },
  {
    "name": "flat_min_sent_0_25",
    "pass": true,
    "got": 0.25
  },
  {
    "name": "flat_deploy_buys",
    "pass": true,
    "got": {
      "strategy_mode": "deploy",
      "allow_new_buys": true
    }
  }
]
```

## Policy fingerprint (start-of-run)

- `regime_cash_policy.json` sha256: `28da3576c5415c5315e5bc3303c78ab53eea8fa7afbe3c5ae979103bee0a0a9e`
- `regime_knob_map.json` sha256: `a3f43f75f013df0839587f0a24ebf731d8ab612969251d19becd26e9af39081b`

```json
{
  "flat_policy_json": {
    "strategy_mode": "deploy",
    "allow_new_buys": true,
    "target_max_util_pct": 0.65,
    "rebalance_cap_usd": 75.0,
    "min_cash_reserve_pct": 0.35,
    "entry": {
      "min_sentiment": 0.25,
      "min_sentiment_new_pair": 0.35,
      "max_rsi": 55.0,
      "require_lockout_clear": true
    },
    "exit": {
      "overbought_rsi": 65.0,
      "max_sentiment_hold": -0.15
    },
    "label": "Flat \u2014 cautious gated deploy (operator thaw 2026-07-18 B)"
  },
  "knob_map_flat": {
    "scenario_id": "flat_cautious_deploy_b",
    "strategy_mode": "deploy",
    "live_overlay": {
      "global_settings.rebalance_cap_usd": 75.0,
      "global_settings.risk_free_preference": "USDC",
      "global_settings.risk_free_apy_pct": 3.5
    },
    "note": "Operator thaw 2026-07-18 option B: cautious gated deploy under flat. NOT usdc_park. Cap $75. Scorecard may later re-park if USDC beats \u2014 only via promotion gates + Brad. | scorecard would prefer usdc_hold (operator_override protected) | sco"
  },
  "live_status_snapshot": {
    "regime": "transition",
    "strategy_mode": "usdc_park",
    "allow_new_buys": false,
    "rebalance_cap_usd": 0.0,
    "target_max_util_pct": 0.45,
    "knob_map_scenario": "usdc_hold",
    "as_of": "2026-07-30T20:51:50.520468+00:00"
  },
  "note": "Flat option B is policy+knob_map when regime=flat. Live status may be transition/park \u2014 fingerprint both; no writes performed."
}
```

## Tier 1 — primary paths (flat + live_overlap)

Method: ARCH-4 Path B real OHLCV. Live B envelope = rebalance 7d cap $75 (RSI/sent **not** in harness).

### flat

- flat_b_rebalance_7d: `ret=-0.12 sh=-0.614 dd=1.09 tr=3 exp=9.2`
- flat_b_rotation_7d: `ret=-3.48 sh=-2.697 dd=8.28 tr=36 exp=84.5`
- defensive_rebalance_14d: `ret=-0.12 sh=-0.631 dd=1.09 tr=3 exp=9.2`
- usdc_hold_proxy: `ret=-0.12 sh=-0.614 dd=1.09 tr=3 exp=9.2`
- Verdict: `{"rebalance_beats_rotation_dd": true, "rebalance_beats_rotation_sharpe": true, "rotation_material_return_edge": false, "primary_hypothesis_supported": true, "defensive_vs_live_b_dd_delta_pp": 0.0, "defensive_vs_live_b_ret_delta_pp": 0.0}`

### live_overlap

- flat_b_rebalance_7d: `ret=0.41 sh=3.891 dd=0.32 tr=2 exp=6.6`
- flat_b_rotation_7d: `ret=0.42 sh=0.53 dd=3.34 tr=45 exp=80.9`
- defensive_rebalance_14d: `ret=0.02 sh=0.37 dd=0.22 tr=2 exp=6.9`
- usdc_hold_proxy: `ret=0.41 sh=3.891 dd=0.32 tr=2 exp=6.6`
- Verdict: `{"rebalance_beats_rotation_dd": true, "rebalance_beats_rotation_sharpe": true, "rotation_material_return_edge": false, "primary_hypothesis_supported": true, "defensive_vs_live_b_dd_delta_pp": -0.1, "defensive_vs_live_b_ret_delta_pp": -0.39}`

## Tier 1b — nearby grid vs live-B

Path B expressible only: strategy × freq × cap. **RSI/sentiment grid gap.**

```json
{
  "flat": {
    "live_b_baseline": {
      "total_return_pct": -0.12,
      "sharpe_ratio": -0.614,
      "max_drawdown_pct": 1.09,
      "total_trades": 3,
      "avg_exposure_pct": 9.2,
      "strategy": "rebalance"
    },
    "n_beaters": 0,
    "top_beaters": [],
    "rebalance_7d_cap_slice": {
      "grid_rebalance_7d_cap50": {
        "ret": -0.12,
        "dd": 1.09,
        "exp": 9.2,
        "tr": 3
      },
      "grid_rebalance_7d_cap75": {
        "ret": -0.12,
        "dd": 1.09,
        "exp": 9.2,
        "tr": 3
      },
      "grid_rebalance_7d_cap100": {
        "ret": -0.12,
        "dd": 1.09,
        "exp": 9.2,
        "tr": 3
      },
      "grid_rebalance_7d_cap150": {
        "ret": -0.12,
        "dd": 1.09,
        "exp": 9.2,
        "tr": 3
      }
    },
    "cap_differentiation_weak": true,
    "date_range": {
      "start": "2026-01-01",
      "end": "2026-03-31"
    },
    "n_ok": 16
  },
  "live_overlap": {
    "live_b_baseline": {
      "total_return_pct": 0.41,
      "sharpe_ratio": 3.891,
      "max_drawdown_pct": 0.32,
      "total_trades": 2,
      "avg_exposure_pct": 6.6,
      "strategy": "rebalance"
    },
    "n_beaters": 0,
    "top_beaters": [],
    "rebalance_7d_cap_slice": {
      "grid_rebalance_7d_cap50": {
        "ret": 0.41,
        "dd": 0.32,
        "exp": 6.6,
        "tr": 2
      },
      "grid_rebalance_7d_cap75": {
        "ret": 0.41,
        "dd": 0.32,
        "exp": 6.6,
        "tr": 2
      },
      "grid_rebalance_7d_cap100": {
        "ret": 0.41,
        "dd": 0.32,
        "exp": 6.6,
        "tr": 2
      },
      "grid_rebalance_7d_cap150": {
        "ret": 0.41,
        "dd": 0.32,
        "exp": 6.6,
        "tr": 2
      }
    },
    "cap_differentiation_weak": true,
    "date_range": {
      "start": "2026-04-20",
      "end": "2026-07-30"
    },
    "n_ok": 16
  }
}
```

## Scorecard multi-asset (flat)

```json
{
  "available": true,
  "date_range": {
    "start": "2026-01-01",
    "end": "2026-03-31"
  },
  "winner_id": "usdc_hold",
  "ranking": [
    "usdc_hold",
    "bear_window_rebalance_21d",
    "rebalance_7d",
    "defensive_rebalance_14d",
    "defensive_rotation_21d",
    "defensive_rotation_14d",
    "bear_window_rotation_14d",
    "baseline_7d"
  ],
  "top_scenarios": [
    {
      "id": "usdc_hold",
      "total_return_pct": 0.8424,
      "annualized_return_pct": 3.5002,
      "max_drawdown_pct": 0.0,
      "sharpe_ratio": 34.403,
      "engine": "usdc_carry"
    },
    {
      "id": "bear_window_rebalance_21d",
      "total_return_pct": -0.42,
      "annualized_return_pct": null,
      "max_drawdown_pct": 0.41,
      "sharpe_ratio": -52.058,
      "engine": "arch4"
    },
    {
      "id": "rebalance_7d",
      "total_return_pct": -0.12,
      "annualized_return_pct": null,
      "max_drawdown_pct": 1.09,
      "sharpe_ratio": -0.614,
      "engine": "arch4"
    },
    {
      "id": "defensive_rebalance_14d",
      "total_return_pct": -0.12,
      "annualized_return_pct": null,
      "max_drawdown_pct": 1.09,
      "sharpe_ratio": -0.631,
      "engine": "arch4"
    },
    {
      "id": "defensive_rotation_21d",
      "total_return_pct": -2.51,
      "annualized_return_pct": null,
      "max_drawdown_pct": 2.46,
      "sharpe_ratio": -30.687,
      "engine": "arch4"
    },
    {
      "id": "defensive_rotation_14d",
      "total_return_pct": -5.16,
      "annualized_return_pct": null,
      "max_drawdown_pct": 7.7,
      "sharpe_ratio": -5.208,
      "engine": "arch4"
    }
  ],
  "scorecard_generated_at": "2026-07-26T11:01:00.254609+00:00"
}
```

## Prior reentry stress (focus)

```json
[
  {
    "regime": "flat",
    "date_range": {
      "start": "2026-01-01",
      "end": "2026-03-31"
    },
    "best_id": "flat_option_b_rebalance_7d",
    "flat_b_reb": {
      "total_return_pct": -0.12,
      "sharpe_ratio": -0.614,
      "max_drawdown_pct": 1.09,
      "total_trades": 3,
      "avg_exposure_pct": 9.2,
      "strategy": "rebalance"
    },
    "flat_b_rot": {
      "total_return_pct": -3.48,
      "sharpe_ratio": -2.697,
      "max_drawdown_pct": 8.28,
      "total_trades": 36,
      "avg_exposure_pct": 84.5,
      "strategy": "rotation_catch_wave"
    },
    "def_reb": {
      "total_return_pct": -0.12,
      "sharpe_ratio": -0.631,
      "max_drawdown_pct": 1.09,
      "total_trades": 3,
      "avg_exposure_pct": 9.2,
      "strategy": "rebalance"
    }
  },
  {
    "regime": "live_overlap",
    "date_range": {
      "start": "2026-04-20",
      "end": "2026-07-30"
    },
    "best_id": "flat_option_b_rebalance_7d",
    "flat_b_reb": {
      "total_return_pct": 0.41,
      "sharpe_ratio": 3.891,
      "max_drawdown_pct": 0.32,
      "total_trades": 2,
      "avg_exposure_pct": 6.6,
      "strategy": "rebalance"
    },
    "flat_b_rot": {
      "total_return_pct": 0.42,
      "sharpe_ratio": 0.53,
      "max_drawdown_pct": 3.34,
      "total_trades": 45,
      "avg_exposure_pct": 80.9,
      "strategy": "rotation_catch_wave"
    },
    "def_reb": {
      "total_return_pct": 0.02,
      "sharpe_ratio": 0.37,
      "max_drawdown_pct": 0.22,
      "total_trades": 2,
      "avg_exposure_pct": 6.9,
      "strategy": "rebalance"
    }
  }
]
```

## Path B gaps

- ARCH-4 Path B does not apply live RSI/sentiment/lockout REGIME-CASH entry filters
- cap0 usdc_hold_proxy has no USDC APY (~0); scorecard usdc_hold uses ~3.5% APY
- live rebalance clock != day stride; basket/allocator differs from live book
- do not promote from Path B alone — gates + Brad required

## Honest assessment

```json
{
  "what_worked": "Rebalance under $75 envelope dominates rotation on maxDD/Sharpe for flat and live_overlap \u2014 matches Path B 2026-07-30 stress narrative.",
  "what_did_not": "Nearby Path B cap grid rarely separates from live-B at low exposure; RSI/sent cannot be validated here. Scorecard flat still prefers USDC hold on true APY.",
  "uncertainty": "Harness exposure/trade counts are low for rebalance cells; live book + gates differ. Current live regime is not flat."
}
```

## Decide (Brad)

```bash
cd /home/brad/projects/crypto-trading-bot
python3 phase6/research/trial_cycle.py decide ANALYST-REGIME-FLAT-KNOBS-20260730-TRIAL continue_observe_only \
  --note 'see reports/REGIME_FLAT_KNOBS_TEST_2026-07-30.json'
```

## Files

- `reports/REGIME_FLAT_KNOBS_TEST_2026-07-30.json`
- `reports/REGIME_FLAT_KNOBS_TEST_2026-07-30.md`
- `phase6/research/run_regime_flat_knobs_test.py`
- `scripts/phase6/run_reentry_knob_stress.py` (prior stress artifact)
- `config/regime_cash_policy.json` (read-only fingerprint)

