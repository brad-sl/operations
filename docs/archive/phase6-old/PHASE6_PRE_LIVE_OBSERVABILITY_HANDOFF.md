# Phase 6 Pre-Live Observability Handoff Document

**Date:** 2026-05-18  
**Status:** Ready for Execution  
**Owner:** Scotty (Hermes Agent)  
**Goal:** Harden observability so we can safely enable live trading on the Coinbase test account.

## Objective
Add persistent trade tracking, structured logging, basic anomaly detection, and Telegram alerting before switching from paper to live.

## Current State (Fresh Start)
- All positions liquidated
- $967.76 USD available
- Zero open positions
- Clean slate for live run

## Success Criteria
- Every trade (open + close) is durably logged
- Launch notification + 2× daily summaries sent via Telegram (channel 8736967053)
- Structured logs with separate error stream
- Basic drawdown and repeated failure detection
- Dashboard can read trade history
- Ready for live mode with confidence

## Scope (What’s In)
- Persistent trade ledger (JSONL + daily CSV)
- Structured logging
- Telegram alert module (launch overview + AM/PM summaries)
- Lightweight anomaly detection
- Dashboard data source updates

## Scope (What’s Out)
- Full database migration (JSONL is acceptable interim)
- Advanced ML anomaly detection
- Real-time position sync with Coinbase (Phase B)
- Backtesting framework

## Deliverables & Tasks

| ID | Task | Owner | Success Criteria | Dependencies |
|----|------|-------|------------------|--------------|
| 1 | Create persistent trade ledger writer | Main | Trades written to `trades/phase6_trades.jsonl` + daily CSV | None |
| 2 | Upgrade logging to structured + error separation | Main | JSON logs + dedicated error log file | None |
| 3 | Build Telegram alert system | Main / Sub-agent | Launch summary + 2× daily summaries to channel 8736967053 | Task 1 |
| 4 | Add basic anomaly detection | Main | Drawdown + repeated failure alerts | Task 1, 2 |
| 5 | Connect live dashboard to trade ledger | Main | Dashboard shows recent trades from ledger | Task 1 |
| 6 | Final validation + live mode prep | Main | Clean run with fresh start confirmed | All above |

## Alert Policy (Confirmed)
- **Initial launch**: Full trade status overview
- **Ongoing**: AM + PM summary only
- Details → User checks dashboard

## Files to Modify / Create
- `scripts/phase6/phase6_trading.py` (main integration point)
- `trades/phase6_trades.jsonl` (new)
- `logs/phase6_trading.log` + `logs/phase6_errors.log`
- New module: `scripts/phase6/telegram_alerts.py`
- Update `serve_dashboard.py` (optional, for ledger reading)

## Risk Notes
- Keep changes minimal and reversible while in live prep phase.
- All new logging/alert code should be behind feature flags if possible.

## Next Action
Execute tasks in priority order (1 → 3 → 2 → 4 → 5).

---
*This document is the single source of truth for this workstream.*