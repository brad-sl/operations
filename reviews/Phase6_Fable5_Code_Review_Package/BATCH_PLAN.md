# Phase 6 Fable 5 Review — Tiered Batch Plan

**Goal**: Feed the model the codebase in coherent, high-signal batches (avoiding context exhaustion and hallucinated cross-references).

**Rule**: After each batch, Fable 5 should:
1. Give immediate top risks found so far (no waiting until the end).
2. Ask for the next batch (or specific additional files if needed for context).
3. Only produce the full scored report **after Tier 5 is complete**.

---

## Batch 1 — Tier 0 (Core Runtime & Decision Brain) — Highest leverage / highest risk

**Files to feed together**:
- `phase6/core/phase6_runner.py` (full — the single most important file)
- `phase6/scripts/deploy_capital.py`
- `phase6/core/signal_generator.py`

**Focus questions for the reviewer**:
- Does the main loop correctly distinguish Fresh Start vs. ongoing rebalance?
- Is `FIXED_UNIVERSE` vs. real holdings from `LivePortfolioManager` / exchange handled cleanly (sticky rebalancing principle)?
- Are sentiment + RSI signals actually wired into capital deployment with aging/staleness awareness?
- Any paths where decisions can be made with missing or stale data?
- Error handling / notify paths around execution failures?

**Reviewer action after this batch**: List the top 5-7 risks or clean areas observed. Request Batch 2.

---

## Batch 2 — Tier 1 (Risk, Safety, Stop-Loss, Execution) — Capital protection

**Files**:
- `phase6/core/stop_loss_manager.py`
- `phase6/core/stop_loss_coordinator.py`
- `phase6/core/rebalancing/hybrid_rebalancer.py`
- `phase6/core/risk/` (all 5 files in the risk/ dir)
- `phase6/core/order_executor.py`
- `phase6/core/exchange_client.py` (pairs with executor)

**Focus questions**:
- Stop-loss placement + re-attach logic (CR-03 flows): Is it deterministic and safe even after liquidation / power loss?
- Does the hybrid rebalancer respect withdrawal reserves, current holdings (no forced renorm), and the rebalance_cap_usd scope correctly?
- Correlation / regime / ATR circuit breakers actually firing on real data?
- Any silent failures in order execution that would leave the system in a bad state?
- How well does the risk layer integrate back into the runner?

**Reviewer action**: Immediate risk summary. Then request Batch 3 or any clarifications from Batch 1-2.

---

## Batch 3 — Tier 2 (Signals & Data Integrity — Sentiment + Price)

**Files**:
- `phase6/core/sentiment_scorer.py` (both root copy if different + phase6/core/sentiment/ subdir)
- `/home/brad/projects/crypto-trading-bot/run_full_sentiment_v3.py` (canonical collector)
- `phase6/scripts/generate_trading_intelligence_report.py`
- `phase6/core/price_history_manager.py`
- Relevant sentiment fetchers in `phase6/core/sentiment/` that are still imported (praw, direct, x, etc.)

**Focus questions**:
- Is there truly a *single* canonical source of truth for sentiment (cache + scorer), or are there still leaking old paths?
- Sentiment aging (half-life) correctly applied in decision paths?
- RSI computation (pure Python in runner) vs. cached state files — any desync risk?
- Freshness / staleness gates present on all consumers?
- Apify / external data paths have reasonable timeouts, error handling, and no silent 0.0 poisoning?

**Reviewer action**: Risk summary + any cross-tier observations so far.

---

## Batch 4 — Tier 3 + Tier 4 (Allocation Math, Capital, Observability, Infrastructure)

**Files** (can split if too large):
- Allocation: `phase6/core/allocation_engine.py`, `phase6/core/allocation/enhanced_allocation_engine.py`
- `phase6/scripts/capital_deployment_runner.py`, `phase6/scripts/real_capital_event_monitor.py`
- Logging & ledger: `phase6/core/rebalance_logger.py`, `phase6/core/trade_ledger.py`
- Config + error + perf: `phase6/core/config_loader.py`, `phase6/core/error_notifier.py`, performance modules
- Live servers: current dashboard serve_live_8501.py or equivalent, phase6_live_harness.py, recent monitor script

**Focus**:
- Allocation math correctness (inverse vol + sentiment adjustment) with real vs. paper paths distinguished.
- Event logging sufficient for post-mortem and loop-style continuous improvement?
- Dashboard / monitoring actually reflect the canonical state the runner uses?
- Any places where config is loaded from multiple sources creating drift?

---

## Batch 5 — Tier 5 (Backtest, Validation Harness, Evidence Quality)

**Files**:
- Entire `phase6/backtest/` tree (engine, metrics, pair_selector, recovery experiments, etc.)
- `scripts/validate_canonical_sentiment_paper.py` (the recent Code Isolation Test script)
- `phase6/scripts/phase6_live_harness.py`
- Any other `phase6/tests/` that are actively used

**Focus**:
- Gap between backtest assumptions and live reality (data sources, slippage, execution, sentiment staleness, position awareness).
- Quality of isolation tests — do they catch the exact classes of bugs the production paths are vulnerable to?
- Recovery backtesting (post stop-loss basket rebuild) — is it strong enough given user emphasis on this?
- Evidence that recent canonical sentiment + aging changes were properly validated before deploy?

---

## Batch 6 — Tier 6 (Intent vs. Reality — Docs + Config + High-Level Architecture)

**Files**:
- `docs/MASTER_TASK_TRACKING.md`
- `docs/PHASE6.md`
- `docs/PHASE_6_REBALANCING.md`
- `docs/AGENTS.md` (and any recent handoffs)
- Active config files used by the runner (trading_config_phase6.json or equivalents in phase6/config)
- ARCHITECTURE.md or any other high-level doc claiming current behavior

**Focus**:
- Documentation drift: Do the docs describe the code as it actually runs today?
- Clear capture of user preferences (sticky holdings, Fresh Start bootstrap-only, quality gates on recovery, real data only, etc.)?
- Any "future" features documented as if implemented?

---

## Final Step (after all batches)

Ask Fable 5 for the **complete structured report** in the exact schema defined in MANIFEST.md, followed by:
- Executive Summary (top risks + overall health score 1-10 for real-capital trading system)
- Systemic patterns
- What is done well
- Fully prioritized scored backlog

---

## Tips for Feeding (to keep costs and quality high)

- Paste full file contents cleanly, with header like:
  ```
  === BATCH 1 FILE 1: phase6/core/phase6_runner.py ===
  <full file>
  ```
- Remind the model occasionally of the standing constraints.
- After each batch, explicitly say: "Now summarize the top risks found so far before we continue."
- Do not feed everything in one giant message.

This batch plan was generated 2026-06-10 to support a single targeted Fable 5 (or equivalent) code review session.
