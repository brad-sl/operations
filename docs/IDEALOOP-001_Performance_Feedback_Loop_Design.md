# IDEALOOP-001: Performance Feedback + Parameter Optimization Loop Design (Starter)

**Status:** Design Phase (Skeleton)  
**Date:** 2026-06-12  
**Owner:** Scotty  
**Related Documents:**  
- Ideas/Trading_Bot_Loops_Continuous_Improvement_Ideas_2026-06-09.md (Idea #1, prob 82/100)  
- docs/IDEALOOP-005_Shadow_AB_Experimentation_Loop_Design.md (guardrail dependency)  
- docs/BACKTEST_HARNESS_DESIGN.md (style)  
- handoffs/ideas/Handoff_IDEALOOP-001_Perf_Feedback.md (to be created)  
- MASTER_TASK_TRACKING.md  

## 1. Purpose
Weekly (or post-N cycle) analyzer that observes rich runner logs (rebalances, trades with signals/context, P&L attribution per pair, events). Computes metrics (win rate by signal, realized vs backtest gap, per-pair edge, drawdown attribution, regime correlation). Identifies levers (RSI threshold, sentiment tilt weight, allocation pct, SL/TP levels). Proposes 2-3 variants. Validates via design doc + isolation backtest on recent real data + recovery scenarios. Applies only if passes gates.

## 2. High-Level Requirements
- Leverage existing rebalance_history, trade_activity, phase6_live_state, runner logs, price_history.
- Metrics collector for win rate by signal, P&L per pair/signal, turnover, max DD.
- Proposal generator for param variants.
- Validation: isolation test + paper/shadow (via #5 once ready) + recovery scenarios.
- Dual-write for safety; update via handoff + MASTER + Kanban only.

## 3. Architecture (High Level)
Logs/State → Analyzer (cron or post-cycle) → Metrics + Proposals → Validator (isolation + backtest harness patterns) → Gate Check (quality + risk-adjusted) → Promotion (handoff/MASTER).

## 4. Core Components (Starter)
- Analyzer script (extend ops_engineer or new in scripts/ideas/).
- Metrics from existing logs (see audit: recent rebalances with capital_deployed, executed/skipped, totals ~$613).
- Config for levers.
- Report + proposal output.

## 5. Success Criteria (Starter)
- First weekly report generated from real recent data.
- At least one param proposal with isolation test passing.
- Tracked in MASTER.

**Note:** Full implementation only after #5 Shadow A/B guardrail + explicit handoff for this task. Start with audit + simple analyzer skeleton. 

See full loops doc for details. This is the parallel track #1.