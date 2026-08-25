# Run-Phase Deploy Gate (P0) — 2026-08-24

## Principle

We cannot succeed if we are **late to the table** and only scraps remain — then we get stuck with the bill.

- **RSI / structure** = grounded fact  
- **Run phase** = *where we are in the move* (extension context)  
- **Sentiment** = timing reinforce only — must not open a late-run seat  

Companion: `RSI_PRIMARY_SENTIMENT_REINFORCE_2026-08-24.md`

## Problem (LINK case)

| Window | Tape | Bot |
|--------|------|-----|
| Aug 10–15 | Ignition → early trend (~8.2 → 9.5) | Not positioned |
| Aug 16–21 | Extension → climax (RSI 80–93) | Still not / wrong timing |
| Aug 22–24 | Distribution / chop after +40% run | **Full-wallet BUY on sentiment** |

Sentiment stayed hot in phase 5. Structure was spent.

## P0 scope (this change)

**Hard gate on NEW buys** (and late-phase adds) by run phase:

| Phase | Name | NEW buy |
|------:|------|---------|
| 0 | base | allow (other gates apply) |
| 1 | ignition | allow |
| 2 | trend | allow |
| 3 | extension | **BLOCK** |
| 4 | exhaustion | **BLOCK** |
| 5 | distribution | **BLOCK** |

Does **not**:
- Auto-enter ignition (that’s P1 signal work)
- Auto-trim open bags (P2 dual-peak exit)
- Replace RSI-primary ticket caps (still runs after add_risk)

## Features (daily OHLCV)

- `% from 10d / 20d low`
- Daily RSI(14)
- Volume vs 20d avg
- Days since ignition (vol expansion + range break)
- Off-peak % vs recent high (distribution)

## Code

- Pure module: `phase6/core/run_phase_deploy.py`
- Wire: `rebalance_coordinator` after `filter_trade_plan_rsi_primary_deploy`
- Config: `run_phase_deploy` in `config/trading_config_phase6.json`
- Isolation: `scripts/phase6/test_isolation_run_phase_deploy.py`
- CF: `scripts/phase6/backtest_run_phase_deploy_cf.py`  
  Report: `data/state/run_phase_deploy_cf_report.json`

## Acceptance (P0)

1. Isolation ALL PASSED  
2. LINK **2026-08-24** NEW buy **BLOCK** (1925 and 150)  
3. LINK **Aug 19–22** BLOCK  
4. At least one **ALLOW** day in Aug 10–14 (early window exists)  
5. Fail-closed if candles missing (no silent full deploy)

## Next (not P0)

- **P1** ignition scout → proactive early entries  
- **P2** dual-peak scale-out (price stall × sentiment fade)  
- OPT thresholds on multi-name walk-forward  
