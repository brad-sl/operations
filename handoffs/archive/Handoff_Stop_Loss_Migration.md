# Handoff: Stop-Loss Migration into Phase 6 Runner

**Date:** 2026-06-01  
**Status:** Incomplete / High Priority  
**Owner:** TBD  
**Related:** phase6/core/phase6_runner.py, phase6/core/stop_loss_manager.py, src/stop_loss/

## Objective
Fully migrate stop-loss logic into the canonical `phase6/core/` structure so the live runner uses only Phase 6 modules.

## Must Do
- Move relevant logic from `src/stop_loss/stop_loss_coordinator.py` into `phase6/core/stop_loss_manager.py` or a new `stop_loss/` subpackage.
- Update `phase6_runner.py` to import and use the local `StopLossManager` instead of the `src/` version (remove the TODO).
- Ensure stop-loss decisions are logged via `TradeLedger`.
- Add configuration for stop-loss parameters in the Phase 6 config loader.
- Write or update tests in `phase6/tests/` or `tests/`.

## Must Not Do
- Do not modify `src/stop_loss/` — treat it as legacy.
- Do not change the external behavior of stop-loss calculations without explicit approval.
- Do not introduce new external dependencies.

## Files to Touch
- `phase6/core/phase6_runner.py`
- `phase6/core/stop_loss_manager.py`
- `phase6/core/trade_ledger.py` (if needed for logging)
- `phase6/core/config_loader.py`

## Files to Protect
- `src/stop_loss/stop_loss_coordinator.py` (read-only reference)
- Any existing paper trading results or backtest data

## Success Criteria
- `phase6_runner.py` runs in live mode with no import from `src/stop_loss/`
- Stop-loss triggers are correctly applied and logged during a test cycle
- All existing stop-loss behavior is preserved (verified via shadow mode comparison)

## Validation Method
1. Run the runner in shadow mode for 10+ cycles.
2. Compare stop-loss decisions before/after migration.
3. Confirm no errors in `logs/phase6_runner_error.log`.
4. Update `PHASE6_CURRENT_STATUS.md` when complete.