# Phase 6 Crypto Bot — Complete Code + Docs Review Package (For Fable 5 or Equivalent Strong Reviewer)

**Purpose**: One-time, high-quality external review of the entire Phase 6 production codebase.
- Scope: Architecture, correctness, bugs, performance, reliability, production safety, suggested features, debt.
- Rating: Every finding must be scored (Priority × Severity).
- Output: Structured, deduplicated, actionable list ready to paste into MASTER_TASK_TRACKING.md or Kanban.

**Date prepared**: 2026-06-10
**Requested by**: Brad (via Telegram)
**Target Reviewer Model**: Fable 5 (or any top-tier 200k+ context model such as Claude 3.5/4 / Grok equivalent). The reviewer should treat this as a senior crypto-systems engineer performing a production audit.

---

## Review Scope (ALL IN-SCOPE)

- All active (non-archive) Phase 6 Python code
- Key supporting scripts outside phase6/ that are live (run_full_sentiment_v3.py, phase6_runner.py top-level orchestration, dashboards, sentiment flow)
- Configuration + state schemas
- Risk, rebalancing, allocation, stop-loss, execution, sentiment, data, logging paths
- Architecture & dataflow consistency
- Production safety, no-fake-data rules, rate-limit discipline, rollback readiness
- Backtesting harness maturity
- Suggested features that would meaningfully improve reliability or edge

**OUT OF SCOPE for this run**: Legacy phase4/phase5 code (unless referenced by active Phase 6 paths), pure marketing/docs, old backtest results.

---

## Tiered File Manifest (Prioritized for Review Order)

### Tier 0 — Core Runtime & Decision Loop (Read first, highest leverage)
- phase6/core/phase6_runner.py (859 lines — the brain)
- phase6/core/signal_generator.py
- phase6/scripts/deploy_capital.py
- phase6/core/allocation_engine.py (and allocation/enhanced_allocation_engine.py)
- phase6/core/live_portfolio_manager.py
- phase6/core/exchange_client.py

### Tier 1 — Risk, Safety, Execution (Critical for capital protection)
- phase6/core/stop_loss_manager.py
- phase6/core/stop_loss_coordinator.py
- phase6/core/rebalancing/hybrid_rebalancer.py
- phase6/core/risk/ (all files: regime_detector.py, atr_calculator.py, correlation_circuit_breaker.py, rolling_correlation.py)
- phase6/core/order_executor.py

### Tier 2 — Signals & Data Integrity (Sentiment + Price + RSI)
- phase6/core/sentiment_scorer.py (root + phase6/core/sentiment/)
- run_full_sentiment_v3.py (canonical collector)
- phase6/scripts/generate_trading_intelligence_report.py
- phase6/core/price_history_manager.py
- phase6/core/sentiment/* (direct_reddit_fetcher.py etc. if still referenced)

### Tier 3 — Allocation, Capital, Portfolio Math
- phase6/core/allocation/...
- phase6/scripts/capital_deployment_runner.py
- phase6/scripts/real_capital_event_monitor.py
- phase6/core/rebalance_logger.py
- phase6/core/trade_ledger.py

### Tier 4 — Supporting Infrastructure & Observability
- phase6/core/config_loader.py
- phase6/core/error_notifier.py
- phase6/core/performance_calculator.py + performance_api.py
- serve_live_8501.py (or current dashboard server)
- phase6/scripts/phase6_live_harness.py
- scripts/monitor_canonical_sentiment.py (recent addition)

### Tier 5 — Backtest, Validation, Harness (Quality of evidence)
- phase6/backtest/ (entire tree)
- scripts/validate_canonical_sentiment_paper.py (isolation test)
- phase6/scripts/phase6_live_harness.py
- Any test_*.py under phase6/tests/

### Tier 6 — Configuration, State Schemas, High-Level Docs (for consistency check)
- config/trading_config_phase6.json (if present) or root equivalents
- phase6/config/...
- docs/MASTER_TASK_TRACKING.md
- docs/PHASE6.md
- docs/PHASE_6_REBALANCING.md
- docs/AGENTS.md (agent guidance)
- docs/ARCHITECTURE.md or PHASE_* docs that describe current intent vs. implementation

**Total active Phase 6 Python files (non-archive, non-__pycache__)**: ~53

---

## Required Output Format (Strict — Fable 5 must follow exactly)

For each finding produce:

```markdown
**ID**: P6-XXX (sequential)
**Title**: Short descriptive name
**Category**: Architecture | Bug | Correctness | Performance | Reliability | Security/Risk | Maintainability | Suggestion/Feature | Documentation/Drift
**Priority**: High | Medium | Low   (business/operational impact)
**Severity**: P0-Critical (would lose money or crash) | P1-Major (bad decisions, silent errors, hard to recover) | P2-Moderate | P3-Nit
**File(s)**: list with line ranges where possible
**Evidence**: Direct quote or description from code + why it's a problem
**Impact on live system**: 1-2 sentences (real capital exposure)
**Recommended Fix**: Concrete, actionable (code sketch or behavior change). Note any back-compat or migration needed.
**Confidence**: High | Medium | Low
**Estimated Effort**: XS | S | M | L
**Dependencies / Preconditions**: what else must be true
**Suggested Backlog Placement**: (e.g., "Immediate — before next live rebalance", "Next milestone", "Nice to have")
```

At the end provide:
1. Executive Summary (top 5-8 issues, overall architecture health score 1-10 for a crypto trading system handling real capital)
2. Systemic / recurring patterns observed (e.g., "multiple sources of truth for sentiment still leaking in", "state written without atomicity")
3. Positive observations (what is done well — keep the good)
4. Prioritized master list (High first, then Medium, grouped by category)
5. Recommended immediate next actions + any gating review steps (e.g., "do not touch rebalancer until X is isolated-tested")

---

## How to Run This Review (for user or Fable 5 session)

1. Feed `MANIFEST.md` + this file + the rubric above to the model.
2. Model requests files one Tier at a time (start with Tier 0).
3. You (or the reviewing agent) paste the content of the requested files.
4. After all Tiers, ask for the complete scored report in the exact format.
5. Take the final report → paste findings into `docs/MASTER_TASK_TRACKING.md` under a new section "Fable5 External Review 2026-06-10" and create individual Kanban cards or handoff docs for High items.
6. Run Code Isolation Tests (per standing user preference) on any proposed patches.

**Context Packing Tip for Large Context Models**: Give Tier 0 + 1 first, get findings, then Tier 2+ as needed. Avoid dumping the entire repo at once to prevent hallucinated line numbers.

---

## Standing Constraints the Reviewer Must Internalize

- Real data only. No fake prices, positions, or sentiment in any execution path.
- Fresh Start is bootstrap-only.
- Rebalancing is sticky / starts from current observed holdings.
- Withdrawal reserve must always be respected.
- Sentiment aging + staleness awareness required on all decision paths.
- Strong quality gates (especially post stop-loss cooldown + sentiment thresholds) even in recovery.
- Code Isolation Testing discipline before promoting changes.
- Durable file-based tracking preferred over flaky databases.

---

**Prepared by**: Scotty (Hermes primary agent on 2026-06-10)
**Next step after report received**: Add scored items to MASTER_TASK_TRACKING.md as a dedicated one-time review block, turn High items into tight handoff documents.

---

**Files in this package**:
- `MANIFEST.md` (this file)
- `REVIEW_RUBRIC_AND_PROMPT.md` (exact system instructions for Fable 5)
- `BATCH_PLAN.md` (suggested order + per-batch questions)
- `review_driver.py` (helper script to generate per-file prompt bundles if feeding manually)
<path>home/brad/projects/crypto-trading-bot/reviews/Phase6_Fable5_Code_Review_Package/REVIEW_RUBRIC_AND_PROMPT.md
# FABLE 5 REVIEW PROMPT (Copy this entire section as the system prompt when starting the review)

You are an elite, no-nonsense senior engineer and risk manager specializing in production cryptocurrency trading systems. You have been hired for a one-time, high-stakes thorough review of the Phase 6 crypto trading bot codebase.

Your standards are extremely high because real capital is being risked. You favor clarity, correctness, production resilience, and explicit safety over cleverness. You are suspicious of hidden state, duplicated logic, missing freshness gates, and any path that can silently use stale or fabricated data.

You have been given a tiered manifest. Work through it systematically. For every file (or small group), highlight:
- Correctness bugs
- Architecture mismatches with stated goals (sticky rebalancing, Fresh Start bootstrap-only, real-holdings awareness, withdrawal reserves, quality gates)
- Reliability / observability gaps
- Performance or rate-limit risks
- Safety / capital-protection issues (especially around stop-loss, re-attach, allocation math)
- Sentiment + signal handling correctness and staleness handling
- Backtest-to-live gap risks
- Maintainability and future expansion concerns
- Missed opportunities for robustness or edge

Use the exact output schema defined in MANIFEST.md.

After finishing each tier, summarize the top risks discovered so far before moving on.

At the very end deliver the full structured report with executive summary and scored prioritized backlog.

Never invent files or line numbers. Quote code when possible. Distinguish between "this will cause immediate harm" vs. "this is technical debt that will accumulate pain".

Internalize these non-negotiables:
- Real market data only in live paths.
- No forced renormalization that ignores actual holdings.
- Fresh Start only when there are truly zero positions.
- Sentiment must be aged or gated when deciding capital deployment.
- Stop-loss and protective logic must be reliable and re-attach safely.
- Every decision path must have observable evidence (logs + durable events).

Be direct. If something is good, say it is good and why. If it is dangerous, say it clearly with potential loss scenarios.

Begin by requesting the Tier 0 files.
