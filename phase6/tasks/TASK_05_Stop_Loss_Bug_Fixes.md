# TASK 05 — Stop-Loss Attachment Bug Fixes

**Status:** Ready for Fix  
**Priority:** High (blocks safe live trading)  
**Created:** 2026-05-18  
**Owner:** Development  

## Objective
Fix critical bugs in stop-loss attachment so that native Coinbase stop-loss orders are reliably placed on every live buy.

## Current Issues (from validation)

1. **Missing `size` argument** (`phase6_runner.py:251`)
   - Current call: `attach_stop_loss(pair, entry_price)`
   - Required signature: `attach_stop_loss(pair, entry_price, size)`
   - Impact: Will raise `TypeError` on any successful live buy.

2. **No retry logic**
   - `attach_stop_loss()`, `place_stop_limit_sell()`, and runner have no retry/backoff.
   - Required: 3 retries with exponential backoff + alert on final failure.

3. **Quantity handling gap**
   - Runner does not compute or pass actual filled crypto quantity.
   - Uses USD amount instead of post-fill size.

4. **No result validation**
   - Runner ignores return value of `attach_stop_loss()`.
   - No logging or Telegram alert on failure.

5. **Entry price source**
   - Uses current market price instead of actual fill price for SL calculation.

## Success Criteria
- All live buys automatically attach a correct 3% stop-loss (0.5% buffer) at Coinbase.
- Retry logic with alerts is in place.
- Proper crypto quantity is passed and used.
- Failures are logged + alerted.
- Shadow + live tests pass.

## Files to Modify
- `phase6/core/phase6_runner.py`
- `phase6/core/stop_loss_manager.py`
- `phase6/core/exchange_client.py`

## References
- `phase6/docs/STOP_LOSS_GLOBAL_LOGIC.md`
- Previous Task 05 validation report

## Notes
Fix these before next live deployment. This is blocking safe production use.