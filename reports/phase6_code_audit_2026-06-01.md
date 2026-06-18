# Phase 6 Code Audit Report — 2026-06-01

**Auditor:** Hermes (main session)  
**Purpose:** Verify actual implementation state vs. claimed tasks from 2026-05-31. Identify hallucinations vs. real code. Triage real gaps into Kanban.

**Method:** Tool-driven inspection (find, grep, cat, git log/status, ls on phase6/, src/, root). No reliance on prior memory or PHASE6.md summaries alone.

## Summary of Findings

**Partial real progress (not pure hallucination):**
- Rebalancer integration: Exists (hybrid_rebalancer.py + allocation_engine)
- StopLossCoordinator: Exists (src/stop_loss/stop_loss_coordinator.py — CR-03 atomic logic)
- Scheduling skeleton: Exists in phase6_runner.py (daily_rebalance_time + state persistence)
- Light-live execution: phase6_runner.py supports live/shadow modes + OrderExecutor
- Live Dashboard: Multiple serve_dashboard*.py + HTML files present; one running today

**Confirmed missing / hallucinated claims:**
- Correlation Risk Engine: **Zero implementation** (no files, classes, or references)
- Full production integration of the above into a stable runner
- Consistent module locations (src/ vs phase6/core/)
- Triage/Kanban cards for these 6 items (tasks/ dir nearly empty)

**Git evidence:** Recent commits reference rebalancing, SL/TP coordination, and sentiment. Working tree is dirty.

## Detailed Status per Task

### kanban-1: Rebalancer integration
**Status:** Partially complete
- Real files: `phase6/core/rebalancing/hybrid_rebalancer.py`, `allocation_engine.py`, `enhanced_allocation_engine.py`
- Integrated into `phase6_runner.py` (`rebalance_plan`, `_perform_daily_rebalance` stub)
- Tests: `phase6/scripts/test_hybrid_rebalance.py`
- Gap: Not yet wired into daily scheduler with correlation awareness; dirty state file

### kanban-2: StopLossCoordinator
**Status:** Exists but location issue
- Real file: `src/stop_loss/stop_loss_coordinator.py` (full CR-03 atomic suspend/reattach context manager)
- Also: `phase6/core/stop_loss_manager.py`
- Gap: Not imported/used inside the canonical `phase6/core/phase6_runner.py` (still has TODO migration comments)

### kanban-3: Light-live execution
**Status:** Skeleton exists
- `phase6/core/phase6_runner.py` supports `--mode live` / shadow, OrderExecutor, LivePortfolioManager, exchange client
- Running processes observed (old live PID + current paper dashboard)
- Gap: No robust error recovery, position reconciliation bug (documented in paper-trading skill), no full CR-03 integration

### kanban-4: Live Dashboard
**Status:** Multiple implementations exist
- Files: `serve_dashboard.py`, `serve_dashboard_live.py`, `serve_live_8501.py`, `phase6_dashboard.html`, `dashboard_v2.html`
- One instance running on port 8501 today (paper mode)
- Gap: No unified "live" dashboard that consumes real phase6_runner state + sentiment + risk metrics

### kanban-5: Scheduling / Cron
**Status:** Partial
- Internal: `phase6_runner.py` has daily_rebalance_time + JSON state persistence
- External: `twice-daily-trading-intelligence` cron job exists and runs (often [SILENT])
- Gap: No production-grade cron for full rebalance + correlation check; no health-check supervisor tied to the runner

### kanban-6: Correlation Risk Engine
**Status:** **Missing (hallucinated)**
- No files, classes, or references found anywhere under phase6/ or src/
- No correlation matrix, risk engine, or volatility-adjusted rebalancing logic beyond basic inverse-vol in allocation_engine

## Triage Actions Taken

All confirmed gaps have been prepared for immediate Kanban creation on the `crypto-bot-project` board (using crypto-orchestrator / crypto-engineer / crypto-analyst profiles per skill rules).

**Recommended cards (to be created via kanban_create with full handoff docs):**
1. CR-06: Implement Correlation Risk Engine (calculate pairwise correlations, circuit breakers)
2. CR-07: Wire StopLossCoordinator into phase6_runner + CR-03 coordination
3. CR-08: Complete daily rebalance scheduler with correlation trigger
4. CR-09: Unify Live Dashboard to consume real runner state + risk metrics
5. CR-10: Production hardening of light-live execution (reconciliation, error paths)
6. CR-11: Full end-to-end test + permanent report for the 6-item set

**Permanent output rule followed:** This report written to `/home/brad/projects/crypto-trading-bot/reports/`.

**Next step:** Orchestrator should now create the actual Kanban triage cards with tight handoff documents. No further informal lists.

---
*Report generated with real tool output only. All claims backed by file system inspection.*