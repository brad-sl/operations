# Handoff: Observability & Alerting Improvements

**Date:** 2026-06-01  
**Status:** Incomplete  
**Owner:** TBD

## Objective
Improve monitoring, logging, and alerting so the live Phase 6 runner is production-grade.

## Must Do
- Add structured JSON logging for key events (rebalance, order, sentiment update, error).
- Integrate with existing `error_notifier.py` or create a Phase 6 notifier.
- Expose basic metrics (cycle count, last rebalance, open positions, P&L) via the dashboard or a `/status` endpoint.
- Set up Telegram alerts for critical events (liquidation risk, repeated failures, large drawdown).
- Update `PHASE6_CURRENT_STATUS.md` with new observability status.

## Must Not Do
- Do not add heavy dependencies (keep it lightweight).
- Do not log sensitive data (API keys, full order details).

## Files to Touch
- `phase6/core/phase6_runner.py`
- `logs/` directory structure
- `phase6/core/trade_ledger.py`
- Existing `error_notifier.py` (if reusable)

## Files to Protect
- Current dashboard (`serve_dashboard.py`)

## Success Criteria
- Critical errors trigger immediate Telegram notification.
- Key metrics are visible without digging through raw logs.
- Logs are queryable and timestamped consistently.

## Validation Method
- Trigger a simulated error and confirm alert is received.
- Review 24h of logs for readability.
- Confirm dashboard still functions after changes.