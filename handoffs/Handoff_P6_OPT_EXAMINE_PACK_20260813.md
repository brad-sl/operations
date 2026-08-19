# Task Handoff Document

**Task ID:** `P6-OPT-EXAMINE-PACK-20260813`  
**Parent Task:** none (program)  
**Assigned To:** crypto-orchestrator (decompose only; lanes are separate cards)  
**Date Assigned:** 2026-08-13  

### Objective
Examine remaining platform-optimization opportunities as five independent read-only lanes, then synthesize one ranked scorecard. No live risk changes.

### Context & Background
Aug 13 closed P0 race + same-session SL metric + Dose v4 + intel dedup. User found the leftover “optimization ideas” overwhelming and asked for discrete assignable tasks with assessed results.

Existing MASTER already has gated children (`P6-EXIT-PROFIT-LIVE-GATES`, `P6-HARD-EXIT-AUTO-APPLY`, `P6-MID-CYCLE-ALLOCATOR-EVAL`). This pack **assesses** those; it does not enable them.

### Scope & Boundaries

**Must Do:**
- Fan-out EX-01…EX-05 + SYNTH + REV on `crypto-bot-project`
- Each EX writes a permanent report under `reports/`
- SYNTH ranks at most two next actions
- REV checks honesty + no live writes

**Must Not Do / Touch:**
- Live trading_config / exit_automation / mid-cycle flag
- New indicator grids
- Marketing/SEO profiles
- Linux crontab Phase6 jobs

### Expected Deliverables
- Plan: `docs/plans/2026-08-13-platform-opt-examine-pack.md`
- Five EX reports + SYNTH scorecard
- MASTER program block updated as lanes complete

### Success Criteria
Brad can read SYNTH alone and know what (if anything) to do next.

### Validation Method
Kanban parent links: SYNTH waits on five EX; REV waits on SYNTH. Reports exist on disk with `pursue|watch|drop|blocked_on_brad`.
