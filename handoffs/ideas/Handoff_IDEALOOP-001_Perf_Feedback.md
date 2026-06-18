# Task Handoff Document

**Task ID:** IDEALOOP-001-PERF-FEEDBACK  
**Parent Task:** IDEALOOP-001 (Performance Feedback Loop)  
**Assigned To:** crypto-engineer  
**Date Assigned:** 2026-06-12  

### Objective
Draft and validate the Performance Feedback + Parameter Optimization Loop design and initial analyzer (per Ideas doc #1), after Shadow A/B (#5) guardrail is in place. Focus on audit + skeleton first.

### Context & Background
See docs/IDEALOOP-001_Performance_Feedback_Loop_Design.md and Ideas/Trading_Bot_Loops...md. Depends on #5 for safe experimentation. Current logs show quiet activity (rebalances with executed=0, 4 pairs, totals ~$613 from recent runner).

### Scope & Boundaries
**Must Do:**
- Audit recent rebalance_history/default.jsonl, trade_activity, phase6_live_state, runner logs for baselines (P&L attribution, signal context, win rates).
- Create simple analyzer that computes win rate by signal, per-pair edge, etc.
- Produce first report.
- Follow design skeleton.
- Update MASTER and Kanban docs.
- Use isolation test patterns.

**Must Not Do:**
- Apply any param changes to live without full #5 shadow validation + handoff.
- Touch execution code.

**Files to Work In:** docs/, scripts/ideas/ (new analyzer), data/state/ (for baselines), MASTER_TASK_TRACKING.md.

### Expected Deliverables
- Audit summary in MASTER or separate file.
- Analyzer skeleton + first report.
- Handoff completion note.

### Success Criteria
- Report generated from real data matching recent snapshots (4 positions, ~$613 total).
- Ready for shadow A/B testing of proposals.

### Validation Method
- Run analyzer on recent data; compare output to raw logs.
- Orchestrator review of report + baselines.