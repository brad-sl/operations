# Regime-adaptive optimization knobs

When **regime detection** is accurate enough and **per-regime scenarios** are validated (scorecard), the runner can **swap knob sets** on regime change without editing `trading_config_phase6.json`.

## Components (R4)

| Piece | Path |
|-------|------|
| Detector | `phase6/research/regime_detector.py` (BTC 30d return → bull/bear/flat/transition) |
| Knob map | `config/regime_knob_map.json` |
| Overlay merge | `phase6/core/config_overlay.py` |
| Activation | `activate_regime_adaptive_from_scorecard.py` (scorecard map) or `activate_shadow_trial.py --regime-adaptive` |

## USDC hurdle (Coinbase)

- Config: `config/risk_free_benchmark.json` (`usdc_apy_pct`, default **3.5**).
- Scorecard winners get `usdc_benchmark` in `regime_knob_map.json` (annualized window return vs APY).
- If a regime winner **does not** beat USDC, runtime sets `rebalance_cap_usd=0` and `risk_free_preference=USDC` (stand down deploy).

## Flow

1. Weekly **regime scorecard** picks best scenario per regime window (offline).
2. Populate `regime_knob_map.json` with those winners (not placeholders).
3. Shadow trial with `regime_policy.enabled: true`.
4. Each runner cycle: `detect_regime()` → if regime ≠ `current_regime`, swap `live_overlay` + `arch4_params`.
5. **Drift monitor** still applies — bad swap rolls back entire overlay.

## Accuracy requirements (honest)

- Single-asset BTC momentum is a **proxy**, not ground truth for your 11-pair basket.
- **Transition** bucket avoids whipsaw swaps; require `confidence >= 0.5` before swap (future gate).
- Regime-specific SL tuning belongs in `risk_management.*` overlays for **bear** first (your -80% lesson).

## Optimization loop

```
scorecard per regime → knob_map → shadow + regime_adaptive → monitor vs backtest → learnings
```

See also `REGIME_SCENARIO_PROCEDURE.md`.