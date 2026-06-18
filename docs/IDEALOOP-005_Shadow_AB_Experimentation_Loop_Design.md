# IDEALOOP-005: Shadow A/B Experimentation Loop Design

**Status:** Design Phase  
**Date:** 2026-06-12  
**Owner:** Scotty (orchestrator) / crypto-engineer (implementation)  
**Related Documents:**  
- Ideas/Trading_Bot_Loops_Continuous_Improvement_Ideas_2026-06-09.md (Idea #5, prob 88/100)  
- docs/Ideas_Shadow_AB_Loop_Design.md (initial skeleton)  
- docs/BACKTEST_HARNESS_DESIGN.md (style reference)  
- handoffs/ideas/Handoff_IDEALOOP-005_Shadow_AB.md (explicit handoff)  
- MASTER_TASK_TRACKING.md (loop portfolio section)  
- phase6/core/phase6_runner.py, data/state/phase6_live_state.json, data/state/rebalance_history/default.jsonl, logs/phase6_runner*.log (existing shadow/logging patterns)

---

## 1. Purpose

Create a foundational "Shadow A/B Experimentation Loop" as the guardrail and enabler for all other continuous improvement and opportunity expansion loops in the trading bot platform.

The loop allows any candidate change (parameter tweak, new signal, allocation rule, pair logic, etc.) to run safely in parallel "shadow" mode (paper or simulated decisions using the same real data feed as live) alongside the live or paper runner. Metrics are compared over a defined window. Only changes that demonstrate clear improvement on risk-adjusted metrics (while passing all quality gates) are promoted to production via controlled updates.

**Guiding Principle:** Shadow by default for experimentation. Real data only. Isolation testing + paper validation before any live change. No capital risk from experiments. This multiplies the value of Ideas #1, #2, #3, etc. while respecting existing safety (sentiment thresholds, 24h post-SL cooldowns, recovery rules, no fake data).

---

## 2. High-Level Requirements

- Support configurable "shadow" execution for candidate variants without interfering with live/paper paths.
- Capture rich, comparable decision context and outcomes using existing logging/state (rebalances, trades, P&L attribution, signals).
- Automated comparison after N cycles or time window (e.g. 50-100 rebalances or 7-14 days).
- Strict gating: Better risk-adjusted metrics (Sharpe, max DD, win rate by signal), no regressions on quality gates.
- Design doc + Kanban card + explicit handoff before any code (per user directive).
- Integration points with existing runner, PaperTrader, dashboard (dual-mode), crons, delegation.
- Console + markdown reports (initially; later dashboard/Telegram digest).
- Recoverable and auditable — this document is the single source of truth.

---

## 3. Architecture Overview

```
Candidate Change Definition (config/flag or handoff)
        ↓
Shadow Runner Instance (or parallel mode in phase6_runner)
    (uses same real data: price_history, rsi_cache, sentiment, exchange snapshots)
        ↓
Live/Paper Runner (unchanged primary path)
        ↓
Parallel Logging (rebalance_history, trade_activity, phase6_live_state, shadow_ab_results.jsonl)
        ↓
Shadow Comparator / Analyzer (periodic cron or post-cycle)
    ├── Metrics Collector (win rate by signal, P&L attribution, max DD, turnover, regime performance)
    └── Comparison Engine (shadow vs baseline deltas)
        ↓
Report Generator + Gate Evaluator
        ↓
Promotion Decision (only if passes isolation test + quality gates)
        ↓
Controlled Apply (config/code patch + MASTER/Kanban update + dual-write if needed)
```

---

## 4. Core Components

### 4.1 Candidate Change Interface
- Simple config-driven or handoff-based definition (e.g. "RSI_threshold=55 vs baseline 50", "add_sentiment_tilt=0.2").
- Flag in runner or separate shadow runner invocation.

### 4.2 Shadow Execution Layer
- Extend or parallelize phase6_runner.py with shadow mode (reuse PaperTrader patterns, shadow modes already present).
- Same real data feeds (no synthetic for production experiments).
- Decision logging must be comparable (same fields as live).

### 4.3 Metrics Collector
Collect per-window and comparative metrics (build on existing P&L attribution and logs):

| Category          | Metrics |
|-------------------|---------|
| Returns           | Total P&L, realized vs unrealized |
| Risk              | Max drawdown, Sharpe/Sortino (if computable from logs) |
| Activity          | Rebalance count, turnover %, avg pairs held, capital deployed |
| Signal Performance| Win rate by signal type (RSI, sentiment), per-pair edge |
| Shadow Specific   | Decision divergence rate, promotion success rate, time-to-promotion |

### 4.4 Comparison & Gate Engine
- Side-by-side deltas.
- Automatic pass/fail against thresholds (e.g. Sharpe +5% with max DD no worse, sentiment gate compliance).
- Structured output to shadow_ab_results.jsonl or DB.

### 4.5 Reporting & Promotion
- Markdown report (console + file).
- Integration with dashboard (new /api/shadow or section) or Telegram digest.
- Promotion only via explicit handoff + Kanban + MASTER update (no auto-apply to live).

---

## 5. Data & Configuration

- **Primary data:** Real historical + live snapshots from price_history.json, rsi_cache.json, sentiment caches, phase6_live_state.json, rebalance_history/default.jsonl.
- **State:** New durable dir e.g. data/shadow_ab/ or logs/shadow_ab_results.jsonl.
- **Config-driven:** 
  - shadow_mode_enabled
  - shadow_candidate (description or param diff)
  - comparison_window (cycles or days)
  - promotion_gates (dict of thresholds)
- Frequency: Event-driven (after rebalance) + periodic analyzer cron (extend existing rsi/sentiment crons or new weekly).

---

## 6. Implementation Phases

### Phase 1 – Foundation (Audit + Minimal Shadow)
- Audit current logs/state (rebalance_history, runner logs, phase6_live_state) for baseline metrics.
- Add minimal shadow mode flag + parallel decision path (no side effects on live).
- Basic comparator script (standalone, with Code Isolation Test first).
- Markdown report generation.

### Phase 2 – Full Loop & Gating
- Integrate with existing quality gates (sentiment threshold, 24h cooldown, recovery rules).
- Structured metrics + comparison engine.
- Periodic analyzer (cron or heartbeat).
- Dashboard/Telegram surface for reports.

### Phase 3 – Promotion & Orchestration
- Promotion workflow tied to handoff + Kanban + MASTER.
- Support for multiple concurrent shadows (A/B/C).
- Link to other loops (#1 perf tuning, #2 scanner) as consumers.

### Phase 4 – Hardening (Future)
- Regime-stratified comparisons.
- Automated isolation test generation.
- Long-term data flywheel tie-in (#6).

---

## 7. Non-Goals (for initial implementation)

- No live trading from shadow paths.
- No automatic code changes (promotion always via human + handoff).
- No full ML model training (simple param/signal A/B first).
- No short-side or complex multi-regime until foundation is proven.

---

## 8. Success Criteria

A successful implementation will allow us to answer:
1. Can we run safe parallel shadow experiments on real data without interfering with live?
2. Do shadow decisions produce comparable, actionable metrics?
3. Can we gate and promote improvements reliably (e.g. one RSI threshold change or sentiment tilt)?
4. Does the loop reduce manual review time while increasing experiment velocity?

**Measurable:** At least one candidate change audited, compared, and either correctly rejected or promoted with full documentation trail.

---

## 9. Open Decisions

- Exact comparison window and metrics thresholds (start conservative).
- Whether to use separate shadow runner process or in-process mode flag.
- Storage for long-term shadow history (JSONL vs extend existing DB).
- How tightly to couple with dashboard (new API vs log-based).

---

*This document is the single source of truth for the Shadow A/B Experimentation Loop. Any implementation must reference this document to avoid drift. Start only after explicit handoff and Kanban card.*

**Next per user directive:** Kanban card entry (documented in MASTER), explicit handoff (see handoffs/ideas/Handoff_IDEALOOP-005_Shadow_AB.md), then (and only then) skeleton code + isolation test.