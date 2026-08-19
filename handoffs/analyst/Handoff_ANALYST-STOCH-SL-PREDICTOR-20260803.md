# Handoff — Stoch entry-time → SL predictor (offline)

**Task ID:** ANALYST-STOCH-SL-PREDICTOR-20260803  
**Trial:** ANALYST-STOCH-SL-PREDICTOR-20260803  
**Parent:** STOCH-RSI-PARALLEL-20260721  
**Status:** REPORT_READY (offline + dig run 2026-08-03)  
**Suggested decide:** `no_utility_drop`  

## Intent
Test whether low Stoch %K **at buy/arm** predicts higher subsequent SL rate (leading utility), vs trailing-only usefulness.

## Result (plain)
- Launch window: n=6 with entry Stoch → `extend_collect`
- Dig 7/11→now: n=29; entry Stoch&lt;30 SL rate **lower** than ≥30 (lift 0.77x) → **`no_utility_drop`**
- Exit Stoch still often low on SL (trailing). No live SL / allocator / shadow threshold.

## Artifacts
- Protocol: `docs/testing/trials/ANALYST-STOCH-SL-PREDICTOR-20260803_PROTOCOL.md`
- Module: `phase6/research/stoch_sl_predictor.py`
- Runner: `phase6/research/run_stoch_sl_predictor.py`
- Isolation: `phase6/research/test_isolation_stoch_sl_predictor.py`
- Offline report: `reports/STOCH_SL_PREDICTOR_OFFLINE_2026-08-03.md`
- Dig report: `reports/STOCH_SL_PREDICTOR_DIG_2026-08-03.md`
- State: `data/state/trials/ANALYST-STOCH-SL-PREDICTOR-20260803.json`

## Must not
- Live SL % / allocator changes
- Close parent Stoch trial from this handoff

## Commands
```bash
cd /home/brad/projects/crypto-trading-bot
OPENBLAS_CORETYPE=GENERIC .venv/bin/python3 phase6/research/test_isolation_stoch_sl_predictor.py
OPENBLAS_CORETYPE=GENERIC .venv/bin/python3 phase6/research/run_stoch_sl_predictor.py --phase offline
OPENBLAS_CORETYPE=GENERIC .venv/bin/python3 phase6/research/run_stoch_sl_predictor.py --phase dig --start 2026-07-11T00:00:00+00:00
```

## Close
```bash
.venv/bin/python3 phase6/research/trial_cycle.py decide ANALYST-STOCH-SL-PREDICTOR-20260803 no_utility_drop --note '...'
```
