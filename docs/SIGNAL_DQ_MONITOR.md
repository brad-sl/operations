# Signal data-quality monitor

**Purpose:** Catch silent rebalance blocks (e.g. OP-USD RSI history collapse) without spamming every cycle.

## What runs

| Hook | Schedule | Action |
|------|----------|--------|
| `scripts/phase6/monitor_phase6_runner.py` | cron `*/15` | Defer-streak check + coverage KPI; Telegram on alert |
| `scripts/ops/ops_engineer.py` | cron `*/30` | Same module; opens OPS ticket if alert (deduped) |

Module: `phase6/core/signal_dq_monitor.py`  
State: `data/state/signal_dq_monitor.json`

## Rules

- **Alert** when ≥ **3** consecutive `[REBALANCE DEFER]` with the **same** `slot|reasons` fingerprint (no intervening gate-allow / rebalance-complete).
- **Cooldown** 60 minutes per fingerprint (no Telegram spam).
- Includes live coverage: RSI n/11, sentiment n/11, `missing_rsi`.
- Soft log-only warn if coverage incomplete but no defer streak.

## Related regression

- `phase6/tests/test_isolation_rsi_flat_candles.py` — flat/equal 15m closes must still yield RSI (OP class).
- `phase6/tests/test_isolation_signal_dq_monitor.py` — streak + cooldown.

```bash
.venv/bin/python3 phase6/tests/test_isolation_rsi_flat_candles.py
.venv/bin/python3 phase6/tests/test_isolation_signal_dq_monitor.py
.venv/bin/python3 scripts/phase6/monitor_phase6_runner.py
```
