# Handoff: REGIME-CASH foundation (2026-07-17)

## Summary

Implemented **REGIME-CASH** epic foundation so bull/bear/flat/transition drive **cash park vs deploy** and **BUY entry** requires **regime budget + RSI + sentiment + lockout**. Parameters live in `config/regime_cash_policy.json` for continuous OPT.

## Live effect (after runner restart)

- Detector currently → **flat** (BTC ~+0.3% / 30d on OHLCV)
- Policy + knob_map → **usdc_park**, `allow_new_buys=false`, `rebalance_cap_usd=0`
- Next rebalance: **new BUYs blocked**; **SELLs still allowed**
- Status: `data/state/regime_cash_status.json`

## Files

| Path | Role |
|------|------|
| `docs/epics/REGIME_CASH_EPIC.md` | Epic vision |
| `docs/plans/2026-07-17-regime-cash.md` | Slice plan |
| `config/regime_cash_policy.json` | Optimizable params |
| `phase6/core/regime_cash_policy.py` | Resolve + filter |
| `phase6/core/test_isolation_regime_cash_policy.py` | Isolation |
| `phase6/core/rebalance_coordinator.py` | Live wire |

## Verify

```bash
cd /home/brad/projects/crypto-trading-bot
PYTHONPATH=. .venv/bin/python3 phase6/core/test_isolation_regime_cash_policy.py
```

## Remaining

- RC-03 dashboard/brief line
- RC-04 param sweep
- RC-05 fresher BTC for detector
- RC-06 continuous optimize loop
- **Restart runner** to load coordinator change

## Emergency disable

Edit `config/regime_cash_policy.json`: `"enforce": false` or `"enabled": false`, restart runner.


## RC-03..RC-06 completion (2026-07-17)

| Slice | Artifact | Verify |
|-------|----------|--------|
| RC-03 | Dashboard Regime tile; `/api/metrics.regime_cash`; brief REGIME-CASH line | curl metrics → flat/usdc_park |
| RC-04 | `run_regime_cash_param_sweep.py` | PASS, sweep_latest.json |
| RC-05 | Live BTC merge in `regime_detector` | window_end=today, isolation PASS |
| RC-06 | `run_regime_cash_continuous.py` + weekly shell hook | optimization_latest + learnings.jsonl |

**No auto-promote.** Runner restart still needed for rebalance filter in-process.
