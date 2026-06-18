# Handoff Document: TradeLedger Signature Fix

**Work Package**: TradeLedger Fix  
**Priority**: High (blocks clean live deployment)  
**Status**: Ready for Implementation

## Objective
Fix the `TradeLedger.log_trade()` call signature mismatch that produces the warning during shadow execution. The current implementation expects a single `trade: Dict`, but the runner is calling it with keyword arguments (`pair=...`).

## Root Cause
In `phase6/core/phase6_runner.py`, the logging call uses:
```python
TradeLedger.log_trade(pair=..., side=..., ...)
```
While `trade_ledger.py` defines:
```python
def log_trade(self, trade: Dict[str, Any]) -> None:
```

## Must Do
- Update the call site(s) in `phase6_runner.py` (and any other callers) to pass a properly constructed dict.
- Or enhance `log_trade` to accept both dict and **kwargs for backward compatibility (preferred for minimal change).
- Verify the fix in a shadow run (no more "unexpected keyword argument" warning).
- Add a simple unit test or smoke test for the logging path.
- Update `MASTER_TASK_TRACKING.md` with completion.

## Must Not Do
- Change the CSV/JSONL output format.
- Introduce new dependencies.

## Expected Deliverables
1. Fixed call site or updated `log_trade` method in `phase6/core/trade_ledger.py`
2. Clean shadow run log showing no TradeLedger warning
3. Entry in `MASTER_TASK_TRACKING.md`

## Verification
- Run `phase6_runner --mode shadow` for at least one full cycle.
- Confirm absence of the specific warning.
- All trades still logged correctly to JSONL + daily CSV.

## Git Requirements
- Commit to `phase-6.1` branch
- Reference this handoff in commit message

## Notes
This is the only known non-blocking issue preventing a clean limited live deployment on the $1000 account. Fix before code review delegation.