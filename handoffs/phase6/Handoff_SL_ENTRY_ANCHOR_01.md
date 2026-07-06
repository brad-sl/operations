# Handoff: SL-ENTRY-ANCHOR-01

**Status:** Done (2026-07-06)

## Problem
Live SOL-USD stop re-attach failed with `PREVIEW_STOP_PRICE_ABOVE_LAST_TRADE_PRICE` when ledger/original entry (~$141) was far above last trade (~$82).

## Fix
- `phase6/core/sl_preflight.py`: `resolve_stop_calc_base`, `ensure_stop_below_market`
- `phase6/core/stop_loss_manager.py`: market fetch + rebase before `place_stop_limit_sell`

## Verify
```bash
.venv/bin/python phase6/tests/test_isolation_sl_preflight.py
# Live one-off re-attach (after runner restart):
.venv/bin/python scripts/phase6/reattach_sl_once.py --mode live --confirm-live
```

## Success
Log shows `[SL-ANCHOR-REBASE]` and `Stop-loss successfully attached for SOL-USD` (no PREVIEW_STOP_PRICE_ABOVE_LAST_TRADE_PRICE).