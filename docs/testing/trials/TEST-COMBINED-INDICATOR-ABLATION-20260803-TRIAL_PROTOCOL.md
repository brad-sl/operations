# Protocol — TEST-COMBINED-INDICATOR-ABLATION-20260803-TRIAL

## Identity
- **MASTER:** `TEST-COMBINED-INDICATOR-ABLATION-2026-08`
- **trial_id:** `TEST-COMBINED-INDICATOR-ABLATION-20260803-TRIAL`
- **family:** `combined_indicator_ablation`
- **trial_kind:** offline_analysis
- **Role:** crypto-analyst

## Scope
Multi-pair offline ablation + methodology enhancements for MACD/RSI/Stoch/BB entry/exit/SL.
**Not** a live RSI+Stoch combo reopen (Brad lock 2026-08-03).

## Universe
BTC, ETH, SOL, LINK, AVAX — project `backtests/data/backtest_historical_ohlcv_*.json` (real daily).

## Arms
- A0–A9 original ablations
- E0–E8 entry/exit/SL enhancements
- BH buy-hold reference

## Runner
```bash
cd /home/brad/projects/crypto-trading-bot
OPENBLAS_CORETYPE=GENERIC .venv/bin/python3 phase6/research/combined_strategy_backtest.py \
  --pairs btc,eth,sol,link,avax
```

## Schedule
- T0 execute: immediate offline (this protocol)
- Dig window: optional +3d if longer OHLCV lands
- No live instrumentation cron required

## Decision enums
`dig_further` | `drop` | `propose_scoped_shadow_study` (maps via trial_cycle decide; shadow needs Brad OK)

## Pass-2 result (2026-08-03)
See `reports/COMBINED_INDICATOR_ABLATION_MULTIPAIR_2026-08-03.md` — recommendation `dig_further`.
