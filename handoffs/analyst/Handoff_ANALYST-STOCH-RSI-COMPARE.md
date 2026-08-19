# Handoff — Official StochRSI Parallel Trial

**Task ID:** ANALYST-STOCH-RSI-COMPARE  
**Trial:** STOCH-RSI-PARALLEL-20260721  
**Status:** RUNNING (launched 2026-07-21)  
**Assigned:** crypto-analyst  

## Intent
Parallel StochRSI instrumentation vs plain RSI; allocator unchanged; close with recommendation enum.

## Artifacts
- Protocol: docs/testing/trials/STOCH-RSI-PARALLEL-20260721_PROTOCOL.md
- Cycle: docs/testing/ANALYST_TEST_CYCLE.md
- State: data/state/trials/STOCH-RSI-PARALLEL-20260721.json
- Baseline: reports/STOCH_RSI_TRIAL_BASELINE_2026-07-21.md
- Health: phase6/research/run_stoch_rsi_trial_health.py
- Report: phase6/research/run_stoch_rsi_trial_report.py
- Refresher: scripts/refresh_rsi_prices.py (cron via ~/.hermes wrapper)

## Must not
- Live allocator / trading_config changes without Brad
- Mark CLOSED without final report + decision

## Close unblocks
ANALYST-KELLY-SIZING-TEST-20260721


## Close posture 2026-08-03
- Child SL predictor: **no_utility_drop** (CLOSED)
- No more entry/exit/SL combo experiments for RSI+Stoch
- Final cron `50ee46a3ec21` 2026-08-04 09:00 PT → REVIEW → Brad decide
- Expected lean: observe-only labels / drop promotion path; allocator plain RSI
