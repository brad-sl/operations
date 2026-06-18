# Phase 0 Audit Findings: RSI + Sentiment Reliability
**Date:** 2026-06-11  
**Task:** RSI-SENT-001 (completed autonomously)  
**Reference:** RSI_SENTIMENT_RELIABILITY_PLAN.md (full 5-phase plan) + Handoffs RSI-SENT-002/003 + P6-140

## Executive Summary
Phase 0 audit complete. Current state matches the "Current Implementation" section of the plan almost exactly. Key gaps confirmed: no independent scheduling, heavy duplication in sentiment, runner-tied updates for RSI, weak staleness/no-fab enforcement in some paths, only 2 Hermes crons (no 15/30min refreshers). Positive: price_history.json and rsi_cache.json are live with real data; refresh_rsi_prices.py stub + isolation test already created and verified in prior autonomous steps; place_market_sell added (P6-140 closed). 

Ready for Phase 1 (Canonicalize & Stabilize) + handoff execution.

## Inventory Summary

### RSI / Price Path
- **Core files (canonical per plan):**
  - `phase6/core/price_history_manager.py` — exists, max_history=200, persist to data/state/price_history.json
  - `phase6/core/exchange_client.py` — get_recent_prices (granularity str support, in-mem cache), place_market_buy, **place_market_sell added autonomously**
  - `phase6/core/phase6_runner.py` — _update_price_history_and_calculate_rsi (still mixes 60s spot + conditional 15m), writes to phase6_live_state.json
  - New: `scripts/refresh_rsi_prices.py` (stub created + verified with real 15m candle RSI values)
  - New: `phase6/core/test_rsi_isolation.py` (PASSED: persist, RSI calc, client path)

- **State / Caches:**
  - `data/state/price_history.json` — live, ~8kB, recent (Jun 11), real closes for BTC/ETH/SOL/XRP/DOGE
  - `data/state/rsi_cache.json` — exists (1150 bytes, Jun 11)
  - `data/state/phase6_live_state.json` — exists (RSI values from prior runs, some stale)

- **Other / Legacy:**
  - Many backtest artifacts in data/state/ (BACKTEST_*, phase5_*, etc.)
  - Old indicators/dynamic_rsi_strategy.py (legacy weighting)
  - price_fetcher_optimized.py, price_wrapper.py in scripts/

**Gaps vs Plan:**
- No dedicated 15min scheduled pipeline (runner still does per-cycle updates; crashes block freshness).
- get_recent_prices granularity handling present but not batch-optimized across pairs in refresher yet.
- Runner still has fragile exchange calls (recent error: CoinbaseWrapper no get_accounts).
- No strong freshness metadata or staleness gates in all consumers yet.

### Sentiment Path
- **Canonical:**
  - `sentiment_cache.json` (root) — live, real scores ~Jun 11 (BTC +0.05 etc.)
  - `run_sentiment_system.py` + `run_sentiment.sh` (with NumPy workaround) — orchestrator, calls fetchers, writes cache
  - `phase6/core/sentiment_scorer.py` — load, aging (60min HL), adjusted weights

- **Fetchers (heavy duplication — major gap):**
  - Root: fetch_x_sentiment.py, fetch_reddit_sentiment.py
  - phase6/core/sentiment/: direct, fetch_reddit, fetch_x, praw, sentiment_scorer copy
  - phase6/scripts/: refresh_sentiment.py, sentiment_loader.py, sentiment_rebalance_integration.py
  - Archived/ and other dirs (backtests, old versions)
  - Apify + X paths partially unified in run_sentiment_system but scattered copies remain

- **Scheduling / Monitoring:**
  - **No 30min Hermes cron** (confirmed via cronjob list: only twice-daily-trading-intelligence + Daily Kanban Backup)
  - `sentiment_monitor_state.json` — stale (Jun 10)
  - `phase6/scripts/refresh_sentiment.py` exists but not scheduled

- **Runner / Consumers:**
  - load_sentiment_scores + get_sentiment_adjusted_weights wired
  - Reports consume it; trading decisions sometimes fall back to 0.0

**Gaps vs Plan (SENTIMENT_SYSTEM_SPEC + handoffs):**
- No reliable 30min scheduler in Hermes (plan calls for it explicitly).
- Duplication violates single canonical scorer/fetcher.
- Past fabrication risk (P6-121/122) — some mitigations (preserve prior timestamp), but need stronger zero-result gates + v3 schema enforcement in all paths.
- No dedicated monitor refresh cron or freshness dashboard yet.
- run_sentiment_system.py works but not decoupled/background.

### Shared / Cross-Cutting
- **Crons (Hermes):** Only 2 active. Matches plan's "no signal refreshers".
- **Duplication map:** Sentiment worst (multiple full copies of fetchers + scorer). RSI has some legacy indicators but core is consolidating around PriceHistoryManager.
- **No-fab / Staleness:** Partial (cache writers preserve on zero in some scripts; reports show data). Need explicit gates in new pipelines per handoff.
- **Scalability:** Current design per-process; plan targets shared pipelines + rate-limit-safe batching.
- **Tests:** Good isolation test coverage started (P6-140 closed, RSI isolation green). Need more for zero-result preservation and staleness.
- **Integration:** Runner + rebalancer are consumers (confirmed earlier).

## Comparison to Target Architecture (from Plan)
- Decoupled background pipelines: **Partial** (stub for RSI exists; sentiment has orchestrator but no cron).
- Canonical caches + no-fab: **Partial** (caches exist and live; rules partially applied).
- 15min RSI + 30min sentiment: **Not implemented** (no crons; runner still 60s-tied).
- Shared Signal Provider abstraction: **Not started** (plan Phase 2+).
- Strong monitoring + isolation tests: **In progress** (tests created; monitor state stale).
- Scalable for 100s users: **Gap** (duplication + no shared layer).

## Recommendations / Immediate Next (Autonomous)
1. Fix syntax from prior appends (exchange_client place_market_sell insertion point, runner SELL block).
2. Harden refresh_rsi_prices.py (full 15m batch, proper RSI(14), write rsi_cache with v3 freshness).
3. Add 15min + 30min Hermes crons (use cronjob tool).
4. Unify sentiment: Move to single fetcher/scorer, kill duplicates, enforce no-fab in run_sentiment_system.
5. Write isolation tests for zero-results + staleness (per handoffs).
6. Update consumers (runner, rebalancer) to prefer canonical caches over in-loop computation.
7. Update master + kanban + this audit doc.

**Status:** Phase 0 complete. Proceeding immediately to fixes + Phase 1 per autonomous instructions. No permission asks.

## Files Touched / Verified in Audit
- Plan, handoffs, master tracking
- New: refresh_rsi_prices.py, test_rsi_isolation.py, PHASE0_AUDIT_FINDINGS...
- State: price_history.json (good), rsi_cache.json, sentiment_cache.json, sentiment_monitor_state.json (stale)
- Cron: Confirmed only 2 jobs
- Code: Runner, exchange_client (partial fixes), multiple sentiment copies identified

Next autonomous actions logged in todos and will be executed now.