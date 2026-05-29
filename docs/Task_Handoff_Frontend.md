# Task Handoff: Frontend - Phase 6 Dashboard UI

**Task ID:** dashboard-frontend-refactor  
**Parent Task:** t_0b501c7f  
**Assigned To:** crypto-engineer  
**Date:** 2026-05-18

### Objective
Create a clean, maintainable frontend using static HTML + JavaScript with clear API contracts for both Paper and Live modes.

### Context & Background
The current dashboard is a hybrid mess. We need proper separation: static frontend files that can be updated independently of the Python backend.

### Scope & Boundaries

**Must Do:**
- Create a `static/` or `templates/` directory structure
- Build the Phase 6 UI as static files (HTML + Tailwind + JS)
- All sections: Header, KPIs (Today/24h/7d/30d), Active Positions, Total Balance + Source, Sentiment, Recent Rebalances, Recent Trades, Win Ratio
- Clear visual mode indicator (Paper vs Live)
- JavaScript that fetches from well-defined API endpoints
- Coordinate field names with backend sub-agent

**Must Not Do:**
- Do not embed large amounts of Python logic in the HTML
- Do not modify serve_dashboard.py beyond basic static file serving

**Files to Work In:**
- /home/brad/projects/crypto-trading-bot/static/ (new)
- /home/brad/projects/crypto-trading-bot/phase6_dashboard.html (can be moved into static/)

**Files to Leave Untouched:**
- Existing production dashboard files in hermes workspace

### Expected Deliverables
- Clean static frontend in a dedicated directory
- JavaScript that expects specific JSON shapes from the backend
- Documentation of all API contracts used

### Success Criteria
- Frontend loads cleanly when served as static files
- All UI sections render with data from API
- Easy to update HTML/JS without touching Python

### Coordination Requirements
- Work closely with backend sub-agent on field naming
- Define clear JSON response formats for:
  - /api/positions
  - /api/balances  
  - /api/metrics (PnL periods)
  - /api/rebalances
  - /api/trades
  - /api/sentiment

### Validation Method
- Load the static HTML directly in browser with mock data first
- Then connect to running backend
