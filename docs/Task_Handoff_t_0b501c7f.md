# Task Delegation / Handoff Document

**Task ID:** t_0b501c7f  
**Parent Task:** t_d0439c8e  
**Assigned To:** crypto-engineer  
**Date Assigned:** 2026-05-17  

### Objective
Rebuild a clean, stable Phase 6 Dashboard with modern UI and reliable Live/Paper mode support.

### Context & Background
Previous dashboard work was corrupted by merging an old Phase 4b dashboard with new Coinbase integration logic. The result was a broken hybrid (404 on root, missing endpoints, credential loading failures). A clean rebuild is required.

### Scope & Boundaries

**Must Do:**
- Create a clean serve_dashboard.py with Phase 6 Tailwind UI
- Support --mode paper and --mode live
- Implement real Coinbase API integration for Live mode
- Show Active Positions, Total Balance, Source label, P&L periods, Win Ratio, Recent Trades/Rebalances, Sentiment
- Working root route (/) and API endpoints

**Must Not Do:**
- Do not overwrite or modify any existing production files without explicit approval
- Do not use the old Phase 4b code as base

**Files to Work In:**
- /home/brad/projects/crypto-trading-bot/serve_dashboard.py (primary)
- /home/brad/projects/crypto-trading-bot/docs/ (for any new docs)

**Files to Leave Untouched:**
- All files in /home/brad/.hermes/kanban/boards/crypto-bot-project/workspaces/

### Expected Deliverables
- Clean, working serve_dashboard.py
- Updated systemd services (if needed)
- All requested UI sections functional

### Success Criteria
- Root path serves modern Phase 6 UI
- Live mode correctly loads Coinbase credentials and displays real balances/positions
- Paper mode pulls from reports.db
- No 404s on core routes

### Constraints & Requirements
- Must use Tailwind via CDN for UI
- Must load .env from /home/brad/projects/crypto-trading-bot/.env
- Must be maintainable and well-documented

### Validation Method
- Manual testing of both dashboards (8501 and 8502)
- Verify /api/positions and /api/balances return correct data per mode
- Confirm no regression in existing functionality

### Notes & Warnings for Sub-Agent
- Previous sub-agent work overwrote a working dashboard. Be extremely careful with file operations.
- Always verify which file you are editing before making changes.
