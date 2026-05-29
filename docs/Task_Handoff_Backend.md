# Task Handoff: Backend - Phase 6 Dashboard API

**Task ID:** dashboard-backend-refactor  
**Parent Task:** t_0b501c7f  
**Assigned To:** crypto-engineer  
**Date:** 2026-05-18

### Objective
Build a clean backend with proper static file serving + well-defined API endpoints that support both Paper and Live modes.

### Context & Background
We need to separate concerns: the Python server should serve static files and provide JSON APIs. The frontend should be fully static and updatable independently.

### Scope & Boundaries

**Must Do:**
- Modify serve_dashboard.py to serve static files from a `static/` directory
- Implement or update these endpoints with clear JSON shapes:
  - GET /api/positions → returns active positions + total_balance + mode + source
  - GET /api/balances → returns account balances (Live = Coinbase, Paper = derived)
  - GET /api/metrics → returns PnL for Today / 24h / 7d / 30d + Win Ratio
  - GET /api/rebalances (optional but nice)
  - GET /api/trades (optional but nice)
  - GET /api/sentiment (optional)
- Load .env from /home/brad/projects/crypto-trading-bot/.env
- Support --mode paper and --mode live

**Must Not Do:**
- Do not put large HTML strings back into the Python file
- Do not break existing /health or other simple endpoints

**Files to Work In:**
- /home/brad/projects/crypto-trading-bot/serve_dashboard.py
- /home/brad/projects/crypto-trading-bot/static/ (new directory for frontend assets)

### Expected Deliverables
- Updated serve_dashboard.py that serves static files + APIs
- Clear, documented JSON response formats
- Coordination with frontend sub-agent on field names

### Success Criteria
- Frontend can be loaded as pure static files
- All required data endpoints return consistent, mode-aware data
- Paper mode uses reports.db, Live mode uses Coinbase

### Coordination Requirements
- Agree on field names with frontend sub-agent before finalizing
- Use consistent keys across endpoints (e.g. "pair", "balance", "pnl", "source", "mode")

### Validation Method
- Test both Paper and Live modes
- Verify static HTML loads and fetches data correctly
