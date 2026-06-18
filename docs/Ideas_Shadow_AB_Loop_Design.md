# Shadow A/B Experimentation Loop - Design Skeleton (Idea #5)

**Date**: 2026-06-12
**Source**: Ideas/Trading_Bot_Loops_Continuous_Improvement_Ideas_2026-06-09.md (prob 88/100 - highest)
**Goal**: Foundational enabler for all other loops. Safe experimentation on any candidate change (param, signal, allocation rule, new pair logic, etc.) by running shadow (paper/simulated) decisions alongside live/paper. Compare metrics over cycles. Promote only clear winners that pass isolation tests + safety gates.

**Alignment with Existing**:
- Leverages PaperTrader, shadow modes (already in runner), logging (rebalance/trade events), dashboard dual-mode, backtesting harness, isolation testing preference, delegation/Kanban/handoffs, quality gates (sentiment threshold, 24h post-SL cooldown), real-data-only rule.
- No new capital risk; paper-first.

**High-Level Loop**:
1. **Observe**: Any candidate change (from other loops or manual) is configured to run in shadow mode (e.g. via config flag or parallel runner instance). Capture decisions + context using same real data feed as live.
2. **Analyze**: After N cycles (e.g. 50-100 rebalances or 7-14 days), compare shadow vs live/paper metrics (win rate by signal, realized P&L attribution, max DD, slippage, regime performance, per-pair edge).
3. **Adjust/Validate**: Rigorous code isolation test + report (per skill). Design doc first. Backtest on recent real data + recovery scenarios. Paper run if needed.
4. **Apply**: Only if passes gates (better risk-adjusted metrics, no worse max DD, aligns with quality rules). Update config/code with diff; track in MASTER + Kanban. Log rationale durably.
5. **Repeat**: Close the loop.

**Key Components to Build/Extend**:
- Shadow runner mode or parallel instance (extend phase6_runner.py or use existing PaperTrader patterns).
- Metrics comparator script (build on existing P&L attribution in logs).
- Gating logic (reuse sentiment threshold, cooldowns, isolation test harness).
- State: Durable comparison reports in e.g. logs/shadow_ab/ or data/shadow_results.jsonl.
- Integration: Trigger from perf loop or opportunity scanner; surface results in dashboard or Telegram digest.
- Cron/automation: Weekly or event-driven analyzer (extend existing crons).

**Validation Checklist (per prefs)**:
- Real data only (no fake prices/positions).
- Isolation test first (standalone wrapper script that produces correct values).
- Paper/shadow before any live change.
- Update MASTER_TASK_TRACKING.md + Kanban + tight handoff doc.
- Quality gates enforced (even in "emergency" recovery contexts).
- No regressions to existing FABLE5 closures or safety (one-sided SELLs, reserves, etc.).

**Success Criteria**:
- Shadow runs in parallel without interfering with live.
- Automated comparison report after defined window.
- At least one candidate change promoted safely (or correctly rejected).
- Measurable improvement in tracked metrics when promoted.

**Risks & Mitigations**:
- Overfitting to past: Strict OOS + walk-forward in validation.
- Complexity creep: Start minimal (one param at a time, e.g. RSI threshold A/B).
- Logging bloat: Structured, queryable event logs.

**Immediate Next Steps**:
- Audit current logging/state for baseline metrics.
- Prototype shadow comparator script (isolation test first).
- Create tight Handoff Doc + Kanban card.
- Extend runner/config for easy shadow toggling.

**References**: Existing backtesting skill, code-isolation-testing skill, delegation patterns, PHASE6_DASHBOARD_SQL... docs, FABLE5 review, rebalance_history.jsonl, state files.

This is a skeleton. Expand with exact metrics, file paths, pseudocode, or implement the comparator first.