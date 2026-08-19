# Regime × USDC optimization (research path 2)

## Goal

Treat **USDC carry** as a first-class strategy leg in backtests. Per regime window, pick:

`optimal = argmax(annualized_return)` over **alt scenarios + `usdc_hold`**.

Config: `config/risk_free_benchmark.json` (`usdc_apy_pct`, default **3.5**).

## Pipeline

Default pack: `phase6/research/scenarios/regime_quad_defensive.json` (r2 defensive scenarios per regime window).

```bash
cd /home/brad/projects/crypto-trading-bot
.venv/bin/python phase6/research/run_regime_scorecard.py
# legacy 2-scenario quad:
.venv/bin/python phase6/research/run_regime_scorecard.py --pack phase6/research/scenarios/regime_quad_template.json
.venv/bin/python scripts/phase6/run_regime_usdc_assessment.py
.venv/bin/python phase6/research/apply_regime_knob_map_from_scorecard.py
.venv/bin/python phase6/research/activate_regime_adaptive_from_scorecard.py --force
```

Artifacts:

| File | Content |
|------|---------|
| `data/state/analyst_regime_scorecard_latest.json` | `usdc_optimal`, `optimal_strategy_id` per regime |
| `data/state/analyst_regime_usdc_assessment_latest.json` | `deploy_alt` vs `usdc_park` summary |
| `config/regime_knob_map.json` | Uses **optimal** (not DD-only winner) |

## Interpretation

- **DD winner** (`winner_id`) can be `usdc_hold` (0% drawdown) — still useful for risk view.
- **Optimal** drives knob map: `usdc_hold` → `strategy_mode=usdc_park`, `rebalance_cap_usd=0`.
- **Live park** (sell alts + USD→USDC): opt-in per account — **`docs/LIVE_USDC_PARK.md`** (toggle transitions + redeploy runbook), `live_usdc_park.enabled` in `config/trader_accounts.json`.
- `phase6/core/usdc_park_transitions.py` — off→on, on→off, park→redeploy FSM

## Code

- `phase6/research/usdc_carry_backtest.py` — synthetic carry metrics
- `phase6/research/regime_strategy_optimizer.py` — max annualized picker
- `phase6/research/test_isolation_usdc_carry_regime.py`