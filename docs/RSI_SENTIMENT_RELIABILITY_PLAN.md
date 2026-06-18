# RSI & Sentiment Signal Reliability + Scalability Plan

**Date:** 2026-06-11  
**Owner:** Scotty (crypto-orchestrator)  
**Status:** Derived from specs + live audit (ready for review & delegation)  
**Priority:** P0-Critical (foundational for all downstream: runner, rebalancing, allocation, signals, reports, dashboards)

## Executive Summary

Both RSI (price-derived) and Sentiment are **not reliably fresh** despite prior work. This breaks signal generation, rebalancing, and allocation.

- **RSI symptoms**: live_state.json RSI values stale (last ~Jun 10); runner tied to buggy exchange client; price history only seeded on startup + updated in main loop (fails when runner errors).
- **Sentiment symptoms**: Cache updates sporadically with real data, but no reliable 30min scheduler in Hermes cron; multiple legacy scripts + duplication; past fabrication issues (P6-121/122) partially mitigated but drift remains; monitor state stale.
- **Downstream impact**: Signals often use stale/0.0 placeholders; reports show data but trading loop doesn't consume fresh reliably.
- **Scalability gap**: Current per-process fetches (runner cycles + ad-hoc scripts) will not support 100s of users without rate-limit explosions and duplication. Specs emphasize batching for 5-20 pairs; we need shared production-grade signal pipelines.

This plan provides a **structured, spec-aligned, root-cause-addressing** approach instead of in-place patches. It prioritizes:
- Decoupled, scheduled background pipelines (independent of main runner).
- Canonical single sources of truth with strict no-fabrication + staleness rules.
- Query optimization + caching from day one.
- Path to a scalable "Signal Provider" service for multi-user.

All changes must produce **real data only**, pass Code Isolation Tests, and update the Master Task Tracking List.

## Root Cause Analysis (Specs vs Current Implementation)

### From Specs (Key Requirements)
- **SENTIMENT_SYSTEM_SPEC.md (2026-05-31 v1.1)**:
  - Standalone reusable system.
  - Separate X + Reddit fetchers → Sentiment Scorer (with decay) → Cache.
  - Multi-pair efficiency: batch queries, rate limiting, backoff for 5-20 pairs.
  - Max age 60min default → trigger refresh.
  - No unhandled exceptions; always return valid (even neutral) scores.
  - Native Apify fields preferred for Reddit; VADER fallback.
  - Time decay: X 15min half-life, Reddit 60min.
  - Public interface via `load_sentiment_scores()` / unified entry point.
  - Logging: posts/signals retrieved, score per pair, source used.
  - Consumers: runner, backtester, allocation, monitoring, dashboards.
  - Pipeline diagrams show sentiment aggregation **every 30 min**.

- **PHASE_5_1_REBALANCE_FEATURE_SPEC.md & PHASE_6_REBALANCING.md**:
  - Fresh price data + RSI calculation **every cycle** (~60s).
  - Historical lookback ~100 for RSI(14).
  - Prefer 15m candles for relevant signals.
  - Sentiment used in rebalance + signal gen (every cycle or 30min).
  - Rebalance every 7 cycles with correlation + sentiment weighting.
  - "Sentiment aggregation (every 30 min)" in pipeline.

- **Handoffs (evidence of prior struggles)**:
  - **FABLE5_P6-121_122_Sentiment_Fabrication.md**: Canonical writer fabricating fresh 0.0 neutrals on zero results; legacy schema drift; bad Apify `output` vs dataset iteration; must preserve prior timestamped data on no-results; add post-count + freshness gates; v3 schema; isolation tests; kill legacy writers.
  - **GAP-002_SignalGenerator.md**: Created current `phase6/core/signal_generator.py` (weighted/conservative/rsi_primary modes consuming RSI + sentiment + ATR).
  - **Signal_Quality_Investigation.md**: Need controlled backtests with/without sentiment.
  - Multiple other handoffs reference signal quality, price rounding, etc.

### Current Implementation (Live Audit Findings)
- **RSI/Prices**:
  - `phase6/core/phase6_runner.py`: `PriceHistoryManager` (in-mem rolling 100 + optional JSON persist at `data/state/price_history.json`).
  - Startup: One-time pre-seed with ~20 recent prices per pair via exchange.
  - Per-cycle (`_update_price_history_and_calculate_rsi`): `get_price()` + fallback to 15m candles (`get_recent_prices(..., granularity=900)`) if <15 points; then pure-Python `calculate_rsi`.
  - RSI values written to `live_state.json` (and used in signals/ATR/regime).
  - **Failures**: Runner loop crashes/exits on exchange client bugs (e.g., recent `phase6_runner_error.log`: CoinbaseWrapper missing `get_accounts`); state last updated Jun 10; no independent refresh.
  - Exchange: `get_recent_prices` has in-mem cache + rate-limit comment, but public endpoint calls; no true batch across pairs visible in quick audit; granularity mapping present.
  - No dedicated price fetcher script or cron.

- **Sentiment**:
  - Canonical cache: `/home/brad/projects/crypto-trading-bot/sentiment_cache.json` (flat per-pair with timestamps; recent updates with real ~0.01-0.36 scores).
  - Orchestrator: `run_sentiment_system.py` (Jun 11, calls Reddit + X fetch, combines average, writes canonical; has NumPy workaround via `run_sentiment.sh`).
  - Scorer: `phase6/core/sentiment_scorer.py` (load, aging with 60min HL, adjusted_weights 20% influence, formatters). Also copies in phase6/core/sentiment/.
  - Fetchers: Scattered — root `fetch_x_sentiment.py`/`fetch_reddit_sentiment.py`, `phase6/core/sentiment/` versions (direct_reddit, praw, etc.), archived/.
  - Scheduling: **No 30min job in Hermes cron** (only `twice-daily-trading-intelligence` report job + kanban backup). `run_sentiment_system.py` may run via external means or manually.
  - Monitor: `sentiment_monitor_state.json` stale (Jun 10).
  - Runner usage: `load_sentiment_scores` + `get_sentiment_adjusted_weights` called; but signal gen often has `sentiment = 0.0 # placeholder`.
  - Past fixes (per handoff): Some v3 schema, dataset iteration, no-fab rules applied in patches, but duplication and scheduling gaps persist.

- **Shared Issues**:
  - Signals tied to main runner health.
  - Weak staleness enforcement in consumers (reports show data; trading decisions may not).
  - Duplication violates "single source of truth" intent.
  - No strong observability (freshness minutes, post counts, quality gates) in production path.
  - Exchange client fragility blocks price data.
  - Data/state has many backtest artifacts but live price_history snapshot may be missing or not flushed reliably.

- **Scalability Evidence**:
  - Specs require batching/rate-limit respect for even 5-20 pairs.
  - Current: Every runner instance + every sentiment script hits APIs independently.
  - Coinbase public candles + Apify/X have real costs/quotas/rate limits.
  - For 100s users: Will OOM on quotas or get throttled; no shared cache layer.

**Functional Changes Completed So Far** (from master tracking + handoffs + code):
- PriceHistoryManager + persist + RSI calculator (pure Python).
- SignalGenerator abstraction (3 modes).
- Sentiment scorer canonical load/aging/adjust (some v3 support).
- Partial runner integration of per-cycle RSI update + sentiment-adjusted weights.
- Fabrication mitigations in sentiment writers (dataset iteration, preserve prior on zero).
- Hybrid rebalancer, ATR, regime detector wired in runner.
- Twice-daily intelligence report (consumes the data).
- But: Reliability (independent scheduling, strong gates, monitoring) and scale (shared pipelines) not delivered.

## Proposed Target Architecture (Spec-Aligned + Scalable)

```
Background Pipelines (Hermes cron, 30min or per-cycle as appropriate)
├── Price/RSI Pipeline
│   ├── Dedicated fetcher script (batch candles across pairs)
│   ├── Incremental update to canonical price_history (DB/JSON + time-series)
│   ├── Compute RSI(14) on 15m/1h closes
│   └── Write to canonical_rsi_cache.json + live_state (with ts, age, quality)
│
├── Sentiment Pipeline (per SENTIMENT_SYSTEM_SPEC)
│   ├── run_sentiment_system.py (canonical, or unified entry)
│   ├── X fetch (combined query, Apify or direct)
│   ├── Reddit fetch (Apify native fields preferred, batch)
│   ├── Scorer (decay X 15m / Reddit 60m HL, combine, post-count gate)
│   └── Write canonical sentiment_cache.json (v3 schema: score, posts, ts, sources, confidence)
│
└── Shared Consumers
    ├── phase6_runner.py (reads caches, enforces max_age, uses in SignalGenerator + rebalance)
    ├── Reports / Dashboards (twice-daily + live)
    ├── Backtests / Paper harness
    └── Future: Multi-user Signal Service API / shared cache

Caching & Scale Layer (for 100s users)
- In-memory + disk TTL caches (per exchange_client)
- Rate-limit aware batch clients (exponential backoff, combined queries)
- Central "signals" provider (background workers populate; consumers poll/read only)
- Optional: Redis or file-based pub/sub for fresh signals
```

**Core Principles**:
- **Real data only**. Zero-result = preserve prior timestamp + explicit "stale/error" marker (never fresh 0.0).
- **Single canonical source** per signal type (no duplication).
- **Staleness first-class**: age_minutes, post_count/volume gate, half-life decay.
- **Decoupled**: Signals refresh independently of trading loop.
- **Optimised queries**: Batch where possible (combined X keywords, parallel safe candle fetches with cache).
- **Conservative defaults**: On stale → neutral signals, reduced allocation weight.
- **Observable**: Structured logs, monitor states, isolation-testable.

## Phased Implementation Plan

### Phase 0: Audit & Inventory (1-2 hours, no code changes)
- Inventory all sentiment fetchers/scorers/caches/scripts (grep + ls).
- Inventory all price/RSI paths (runner, exchange_client.get_recent_prices, price_history files).
- Run current fetchers manually + capture logs/metrics (posts retrieved, scores, ages).
- Read full exchange_client for price methods + any rate-limit handling.
- Update MASTER_TASK_TRACKING.md with this audit summary + link to this plan.
- **Deliverable**: Audit report (append to this doc or separate).

### Phase 1: Canonicalize & Stabilize Sources (1-2 days)
- **Sentiment**:
  - Designate ONE canonical orchestrator: `run_sentiment_system.py` (or move to `phase6/core/sentiment/run_full_sentiment.py`).
  - Enforce v3 schema everywhere (schema_version, nested sentiment: {pair: {score, posts, timestamp, sources, confidence?}}).
  - Kill or archive duplicates (move legacy v1/v2/v3 to archive/, update any references).
  - In scorer + any writer: Add strict gate — if posts < N (e.g. 5) or error, preserve prior entry's timestamp + mark status="insufficient_data".
  - Update all consumers (runner, report gen, hybrid_rebalancer) to use `phase6/core/sentiment_scorer` exclusively.
- **RSI/Prices**:
  - Make `PriceHistoryManager` + `data/state/price_history.json` the canonical (ensure flush works).
  - Extract pure price/RSI logic to reusable module if needed (keep calculate_rsi in core).
- **Shared**:
  - Add `get_freshness_minutes()`, `is_stale(max_age=60)` helpers to both scorers/caches.
  - Add post-count / volume to sentiment; candle count / source to RSI.
- **Deliverables**: Clean canonical paths, schema enforcement, no more fabrication risk. Code Isolation Tests for "zero results" case (preserve prior).

### Phase 2: Decoupled Reliable Pipelines + Scheduling (1-2 days)
- Create / harden dedicated scripts:
  - `scripts/refresh_prices_rsi.py` (or enhance existing): Batch-fetch recent candles (use exchange public path), update PriceHistoryManager, compute RSI, write canonical_rsi_cache.json + update live_state fields. Support granularity 900s (15m) + fallback.
  - Make `run_sentiment_system.py` + `run_sentiment.sh` production-grade (add try/except, logging, return codes).
- **Hermes Cron** (use `cronjob` tool or edit jobs.json carefully):
  - 30min sentiment refresh: `run_sentiment.sh run_sentiment_system.py` (or direct python).
  - 5-15min price/RSI refresh (or tie to existing if runner is reliable; prefer independent for now): `python scripts/refresh_prices_rsi.py`.
  - Keep twice-daily intelligence report.
  - Add `sentiment_monitor.py` (or enhance existing) to run every 30min and alert on stale >180min.
- In runner: On startup and periodically, **read** from canonical caches instead of (or in addition to) internal updates. Add strong freshness check before using in signals/rebalance. If stale, log warning + use conservative (neutral sentiment, default RSI 50).
- **Deliverables**: Live 30min sentiment + price refresh jobs. Fresh data flowing to live_state and reports without runner dependency.

### Phase 3: Query Optimization & Caching (1 day)
- **Sentiment**:
  - Combined X queries (as in current fetch_x: "BTC OR ETH OR ...").
  - Reddit: Use Apify community actor with proper params (maxPosts ~30, batch terms if supported).
  - Parallel but rate-limited (backoff, max concurrent 2-3).
- **RSI/Prices**:
  - Leverage exchange `get_recent_prices` in-mem cache + extend to cross-pair batching where Coinbase public API allows (or sequential with sleep).
  - Incremental: Only fetch deltas since last_update (use start/end in candle calls).
  - Prefer 15m granularity for trading relevance (per runner code).
- **General**:
  - TTL caches in exchange_client and fetchers (already partial in-mem).
  - Add disk-backed cache for sentiment results (per-pair recent posts if needed for debugging, but not required).
- Update specs if batching details change.
- **Deliverables**: Measurably lower API calls per refresh (log counts); no rate-limit errors in tests.

### Phase 4: Scalability for 100s Users (2-3 days, after Phase 2 stable)
- Introduce **Signal Provider** abstraction:
  - `phase6/core/signals/provider.py` or simple `signals/` dir: `get_latest_rsi()`, `get_latest_sentiment(aged=True)`, `get_signal(pair)` etc.
  - All consumers import from provider (hides cache details).
- Background workers (the crons above) are the only things that hit external APIs.
- Shared canonical caches (files are fine for start; consider SQLite or Redis later for concurrency).
- For true multi-user:
  - One shared "signal daemon" process (or multiple Hermes crons) populates for all pairs.
  - Per-user runners read shared caches (or per-user override for custom pairs/universe).
  - Rate limits shared across the daemon (single point of control + backoff).
- Add config for universe size (start 5-10, scale to 50+ with batching).
- Cost/Quota monitoring (log Apify usage, estimate calls).
- **Deliverables**: Provider interface + docs on "how to add a new user without new API hits".

### Phase 5: Integration, Testing, Observability & Cutover (ongoing + 1-2 days)
- Wire fresh data into:
  - `phase6_runner.py` _run_cycle + signal gen (remove placeholder 0.0).
  - Hybrid rebalancer, allocation_engine.
  - Reports (already mostly good).
- **Testing (mandatory per user preference)**:
  - Code Isolation Tests for every fetcher/scorer (e.g., mock zero posts → prior data preserved; mock stale → aged/neutral).
  - E2E: Run refresh scripts → assert cache freshness + scores in [ -1,1 ] + no fab.
  - Backtests: Re-run signal quality with restored fresh sentiment (per old handoff).
  - Paper harness with forced stale scenarios.
- **Observability**:
  - Enhance monitor scripts to write actionable state (age, last posts, source counts).
  - Structured logs in fetchers (start, #posts, scores, duration).
  - Alerts via existing notifier or Telegram on stale > threshold.
- Update MASTER_TASK_TRACKING.md + create handoff docs for any sub-tasks.
- Cutover: Pause old ad-hoc runs; rely on new crons.
- **Deliverables**: Passing isolation tests, updated live data in reports + runner, plan sign-off.

## Verification & Success Criteria
- **Freshness**: Sentiment age <60min and RSI updated within last 5-15min in live_state during normal operation.
- **No Fabrication**: Zero-result sentiment run leaves prior timestamp + explicit marker (isolation test proof).
- **Reliability**: Pipelines run via Hermes cron without manual intervention for 48h+; monitor passes staleness checks.
- **Data Quality**: Scores in expected ranges; RSI labels sensible (or refined bins); signals explainable.
- **Scale Readiness**: Single refresh for 5 pairs uses <N API calls (documented); provider allows N users with 1 background worker.
- **Integration**: Runner uses fresh sentiment in >90% of cycles (logs); reports match cache.
- **Tests**: All new code has isolation tests; existing backtests still pass or improve.
- **Master Tracking**: This plan + all sub-tasks tracked in docs/MASTER_TASK_TRACKING.md.

## Risks & Mitigations
- **Exchange client fragility**: Mitigate by making price refresh use public endpoints primarily (already trending that way); fix wrapper bugs in parallel (separate task).
- **API quotas/costs on scale**: Start with conservative schedules (30min ok per spec); add usage logging + circuit breakers early.
- **Schema drift during migration**: Strict version checks in loaders; one-time migration script with backup.
- **Runner still the bottleneck**: Phase 2 decouples signals; runner becomes pure consumer.
- **Over-engineering for 100s users**: Phase 4 is "after stable"; start with file caches + provider interface (cheap win).
- **NumPy/Env issues**: Keep the OPENBLAS wrapper; document in cron jobs.

## Recommended Next Steps & Delegation Style (per user prefs)
1. **Review this plan** (you).
2. **Approve or adjust** (e.g., timelines, exact cron schedules, whether to extract full Signal Service now).
3. **Create tight Handoff Documents** for sub-phases (e.g., one for "Canonical Sentiment Refresh Cron + Tests", one for "Price/RSI Pipeline", one for "Signal Provider Abstraction").
4. **Aggressive delegation**: Spawn sub-agents via kanban or delegate_task for independent workstreams (audit, implementation, testing) with explicit success criteria from this plan.
5. **Update Master List**: Append this plan as the current active work item with status tracking.
6. **Immediate actions I can take now** (if approved):
   - Run full audit + produce detailed inventory.
   - Write the first isolation test for sentiment zero-results case.
   - Create the Hermes 30min sentiment cron job.
   - Extract a `scripts/refresh_rsi.py` stub + test it.

**References**:
- Specs: phase6/specs/SENTIMENT_SYSTEM_SPEC.md, PHASE_5_1_REBALANCE_FEATURE_SPEC.md, PHASE_6_REBALANCING.md
- Handoffs: handoffs/phase6/Handoff_FABLE5_P6-121_122_Sentiment_Fabrication.md, GAP-002, etc.
- Code: phase6/core/{phase6_runner.py, sentiment_scorer.py, price_history_manager.py, signal_generator.py, exchange_client.py}, run_sentiment_system.py, run_sentiment.sh
- Master: docs/MASTER_TASK_TRACKING.md
- Live artifacts: data/state/*.json, logs/phase6_runner_error.log, sentiment_cache.json

This plan is designed to get us from "struggling with freshness" to "reliable, observable, scalable signal foundation" without further in-place patching.

---

**Status in Master Tracking**: To be appended upon approval. (Current master head is 2026-06-10 pre-live paper sign-off.)
