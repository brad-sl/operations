# Task Handoff Document

**Task ID:** IDEALOOP-005-SHADOW-AB  
**Parent Task:** IDEALOOP-005 (Shadow A/B Experimentation Loop from Trading Bot Loops doc)  
**Assigned To:** crypto-engineer (implementation) / Scotty (orchestration + review)  
**Date Assigned:** 2026-06-12  

### Objective
Implement the Shadow A/B Experimentation Loop as the foundational guardrail (Idea #5, 88/100 probability) per the detailed design in docs/IDEALOOP-005_Shadow_AB_Experimentation_Loop_Design.md. Start only after this handoff and corresponding Kanban card.

### Context & Background
From Ideas/Trading_Bot_Loops_Continuous_Improvement_Ideas_2026-06-09.md: Persistent observe→analyze→adjust→validate→apply cycles for safe experimentation. Highest-probability starting point because it enables #1 (perf optimization), #2 (pair expansion), and others with zero capital risk. Builds directly on existing shadow modes, PaperTrader, rebalance/trade logging (data/state/rebalance_history/default.jsonl, trade_activity.jsonl, phase6_live_state.json, runner logs), dashboard dual-mode, quality gates (sentiment threshold + 24h post-SL cooldown), isolation testing preference, delegation/Kanban, real-data-only rule, and MASTER tracking.

Current state from audit (2026-06-12): Recent activity shows low rebalance execution (many "executed: 0", 4 positions, total ~$613, runner cycles every ~1min with dashboard cache writes). Baselines available in price_history, rsi_cache, rebalance_history.

### Scope & Boundaries
**Must Do:**
- Follow the design document exactly (sections 1-9).
- Begin with audit of current logs/state for baseline metrics (P&L attribution, rebalance decisions, signal context, regime signals if present).
- Add minimal shadow mode support (config flag or parallel path) that produces comparable decisions on real data.
- Create standalone Code Isolation Test first (per strong preference: direct/manual test wrapper like previous coinbase_wrapper or test_isolation_*.py).
- Produce markdown comparison report.
- Create/update Kanban card entry (via MASTER + reminder cron).
- Update MASTER_TASK_TRACKING.md with progress.
- Respect all quality gates even in shadow/recovery contexts.
- Dual-write where appropriate (JSON + new shadow state) for transition safety.
- Tight handoff + MASTER as single source.

**Must Not Do / Touch:**
- Any changes to live execution paths without passing isolation test + paper validation + this handoff process.
- Automatic promotion to live (always via explicit handoff + human approval).
- Fake/synthetic data in any validation.
- Removal of existing JSON caches or logging.
- Touch unrelated files (e.g. sentiment scorer, Uphold plans) unless explicitly in scope later.

**Files / Directories to Work In:**
- docs/IDEALOOP-005_Shadow_AB_Experimentation_Loop_Design.md (reference only)
- phase6/core/phase6_runner.py (shadow mode extension)
- data/state/ (new shadow_ab_results/ or extend rebalance_history)
- scripts/ or phase6/core/ (new comparator + isolation test)
- handoffs/ideas/ (this and future)
- MASTER_TASK_TRACKING.md, docs/ (tracking)
- logs/ (new shadow logs if needed)

**Files / Directories to Leave Untouched:**
- Production trading execution (order_executor, etc.) until promotion gate passed.
- Existing crons without shadow flag.
- Dashboard HTML/JS until report surface is designed.

### Expected Deliverables
- Completed audit report (baselines from recent rebalance_history, runner logs, state files) appended to MASTER or separate AUDIT_SHADOW_BASELINES.md.
- Code Isolation Test (e.g. phase6/core/test_isolation_shadow_ab.py) that runs standalone, produces correct comparable metrics on real data, passes.
- Minimal shadow mode implementation + comparator script producing markdown report.
- Updated Kanban card (documented in MASTER) + this handoff.
- Progress entry in MASTER_TASK_TRACKING.md.
- No production code changes without passing all gates.

### Success Criteria
- Shadow decisions run in parallel on real data and produce directly comparable outputs to live/paper.
- Comparator generates usable report after a test window (e.g. 10-20 cycles) showing deltas.
- Isolation test passes with real data (compare to known recent totals ~$613, 4 positions).
- All changes traceable via MASTER, handoff, and Kanban.
- Ready for promotion of a trivial first candidate (e.g. small RSI threshold A/B) only after full validation.

### Constraints & Requirements
- Real data only (use current price_history.json, rsi_cache.json, rebalance_history/default.jsonl, live_state).
- Must pass existing quality gates (sentiment, cooldowns, recovery rules).
- Follow BACKTEST_HARNESS_DESIGN.md structural style in any extended docs.
- Use tight handoffs, single source of truth (MASTER), code isolation testing.
- Low overhead: Start minimal (one param or rule at a time).
- No regressions to prior FABLE5 closures (P0 safety items like positions, one-sided sells, reserves, pricing).

### Validation Method
- Run the new isolation test wrapper and confirm correct output on known recent data.
- Manual review of first shadow report vs actual runner logs.
- Confirm no side effects on live/paper state (diff of key files before/after test run).
- Orchestrator (or user) signs off on handoff completion before any further expansion to #1/#2.

### Notes & Warnings for Sub-Agent
- Current activity is quiet (many skipped rebalances, holdings $0 in some snapshots) — use this for realistic baselines.
- Previous FABLE5 work emphasized paper validation + "SCOTTY SIGN-OFF" before live.
- Leverage existing patterns from phase6/core/test_isolation_*.py and handoffs/phase6/ (e.g. Handoff_Runner_DB_Fact_Persistence.md).
- If in doubt on metrics, start with simple ones from logs (capital_deployed, executed/skipped, total_usd from dashboard cache).
- This is the guardrail — get it right before parallel work on perf feedback or pair expansion.