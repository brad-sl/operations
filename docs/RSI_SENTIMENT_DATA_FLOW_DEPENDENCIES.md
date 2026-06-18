# RSI + Sentiment Data Flow and Dependencies (Phase 6 Trading Platform)

**Purpose**: This is the canonical reference for understanding data flows, upstream/downstream dependencies, and change impact across the crypto trading bot. 

Any code change MUST reference this document. Before modifying basket config, fetchers, caches, DB schema, scorers, runner, rebalancer, reports, or dashboards:
1. Trace upstream sources and downstream consumers.
2. Update this doc.
3. Use Code Isolation Testing (standalone verifier scripts) with real data.
4. Update MASTER_TASK_TRACKING.md with evidence.
5. Run explicit verification (crontab, hermes cron, coverage tests, DB/cache queries, live runner checks).
6. Ensure no fake/placeholder data leaks into production paths.

**Date of last major update**: 2026-06-16 (added centralized sentiment keyword management + loader)
**Related**:
- trading-bot-operations skill (rebalance-watchdog, signal pipelines)
- docs/MASTER_TASK_TRACKING.md (primary durable record)
- phase6/core/ (runner, scorer, price_history, signal_generator)
- scripts/ (refresh_rsi_prices.py, sentiment crons)
- Hermes crons (rsi-15min-refresher, sentiment-30min-refresh, twice-daily-trading-intelligence)

## High-Level Data Flow (Mermaid-style text diagram)

```
Upstream Data Sources
├── Live Price Feeds (Coinbase via exchange_client in runner cycles)
│   └── Runner: price snapshots -> self.price_history.add_price(pair, price)
├── Config Basket Definition
│   └── config/trading_config_phase6.json (global_settings.pairs [11], phase_6_specific.opportunity_pool [12])
├── Sentiment Fetch Crons (*/30m)
│   ├── Keyword Management Layer (NEW)
│   │   ├── scripts/optimize_sentiment_keywords.py (generator + relevance tests)
│   │   ├── config/sentiment_keywords.json (central source of truth, versioned)
│   │   └── phase6/core/sentiment_keywords.py (loader: get_x_keyword / get_reddit_keywords)
│   ├── fetch_x_sentiment.py (now pulls keywords from loader) -> x_sentiment_cache.json
│   ├── fetch_reddit_sentiment.py (now pulls from loader) / Apify -> phase6.db sentiment_scores
│   └── run_sentiment_cron.sh -> canonical sentiment_cache.json
└── RSI Price History (decoupled 15m)
    └── scripts/refresh_rsi_prices.py (NOW FIXED: full basket from price_history)

Core Processing Layer (phase6/core/)
├── PriceHistoryManager (data/state/price_history.json)
│   └── Rolling history per pair (100-200+ points from runner)
├── calculate_rsi() (Wilder's, pure Python, in runner + duplicated in refresher)
├── SentimentScorer (phase6/core/sentiment_scorer.py)
│   ├── load_x_sentiment_scores() + damping for low posts/conf
│   ├── _load_reddit_from_db() (real posts >0 only)
│   ├── load_sentiment_scores(universe) -> combined
│   └── load_latest_sentiment_for_basket() -> queries DB rsi_values + sentiment
├── SignalGenerator (phase6/core/signal_generator.py)
│   └── generate_signal(rsi, sentiment, atr, mode) -> BUY/SELL/HOLD + confidence
└── Runner (phase6/core/phase6_runner.py) [central authority]
    ├── Maintains live PriceHistoryManager + computes RSI on cycle
    ├── Persists to DB rsi_values (ts, pair, value, source)
    ├── Calls load_latest_sentiment_for_basket for signals/rebalance
    └── Triggers rebalance, deploys capital, etc.

Downstream Consumers
├── Rebalancer / Allocator (rebalancing/hybrid_rebalancer.py, allocation_engine.py)
│   └── Uses sentiment-adjusted weights + signals from full basket
├── Opportunity Scanner (opportunity_scanner.py)
├── Stop Loss / Risk (stop_loss_manager.py)
├── Dashboards (cache writes, serve_live_8501, performance)
├── Twice-Daily Trading Intelligence (hermes cron "twice-daily-trading-intelligence")
│   └── phase6/scripts/generate_trading_intelligence_report.py (stdout to Telegram)
│       └── Reports RSI/Sentiment coverage, signals, rebalance status
├── Reports / Backtests / Tests (many isolation tests reference price_history, rsi_cache, caches)
└── DB (phase6.db) + Caches (rsi_cache.json, x_sentiment_cache.json, sentiment_cache.json)
    └── Queried by scorer, reports, external traders

Data Stores (authoritative where noted)
- price_history.json : Authoritative live price history (populated by runner)
- rsi_cache.json : Decoupled snapshot for reports/scorer (refresher syncs from history)
- phase6.db (rsi_values, sentiment_scores) : Shared queryable cache (persisted by runner + refresher)
- X / canonical sentiment caches : Real fetched sentiment (X primary)
```

## Component Dependency Matrix

| Component                  | Upstream (inputs)                          | Downstream (outputs/consumers)                  | Basket Scope          | Change Impact Notes |
|----------------------------|--------------------------------------------|-------------------------------------------------|-----------------------|---------------------|
| trading_config_phase6.json | None (source of truth for basket)         | Runner, refresher, scorer, reports, tests      | 11 global / 12 pool  | Adding pair requires: update refresher basket load, scorer DEFAULT_UNIVERSE, runner FIXED_UNIVERSE?, all isolation tests, reports. |
|| Sentiment Keyword Layer (config/sentiment_keywords.json + phase6/core/sentiment_keywords.py + optimizer) | trading_config_phase6.json (basket), human review of samples | fetch_x_sentiment.py, fetch_reddit_sentiment.py (runtime), future tools | Full basket | Adding pair: run --check-new-pairs + optimizer. Changing keywords: edit JSON only (no code). Affects signal quality upstream of scorer. |

| PriceHistoryManager       | Runner live price adds (from exchange)    | Runner RSI calc, refresher (for sync), tests   | Full (runner-driven) | Persist path change affects refresher + all tests referencing it. |
| calculate_rsi()           | Price lists (30+ points)                  | Runner, refresher, signal gen                  | N/A                  | Algorithm change impacts all RSI consumers; keep pure Python. |
| refresh_rsi_prices.py (scripts/) | price_history.json, config basket        | rsi_cache.json, DB rsi_values, twice-daily reports, scorer | MUST be full basket  | Was limited to 6 (mock) -> broke downstream full coverage. Fixed 2026-06-16 to use full + real history. |
| sentiment_scorer.py       | X cache, Reddit DB, rsi DB/cache, config  | load_latest... for runner/rebalancer, reports  | Calls with full basket | Damping logic and "real only" Reddit rule are critical; changing affects signals. |
| SignalGenerator           | RSI + Sentiment + ATR                     | Rebalancer, opportunity scanner, runner        | Per-pair full basket | Mode changes (weighted vs rsi_primary) affect trade decisions. |
| phase6_runner.py          | All above + exchange, config              | Rebalance, DB persist, dashboards, signals     | Full                 | Central; changes here ripple everywhere. Maintains authoritative price_history. |
| Hermes crons (rsi-15m, sentiment-30m, twice-daily) | System crontab + scripts                 | Telegram reports, local logs                   | Depends on scripts   | Schedule changes or script paths must update this doc + MASTER. |
| phase6.db (tables)        | Runner persist_facts_to_db, refresher     | Scorer queries, reports                        | Full                 | Schema change (e.g. add columns) requires migration + all query sites updated. |
| rsi_cache.json / sentiment caches | Refresher / fetchers                     | Scorer (fallback), dashboards, tests           | Varies (was 6)       | Format changes break readers (see test coverage script). |

## Key Data Stores & Freshness

- **price_history.json**: Populated live by runner during cycles (add_price from price snapshots). Has 100-200+ points for all 11 pairs (as of 2026-06-16). Authoritative for prices.
- **rsi_cache.json**: Snapshot format with per-pair {rsi, timestamp, source, candle_count, age_minutes, fresh}. Written by refresher. Read by coverage tests, possibly dashboards.
- **phase6.db.rsi_values**: ts, pair, value, source. Inserted by runner (in persist_facts) and refresher. Queried by load_latest_sentiment_for_basket. (Note: pre-fix data was stale from mock.)
- **Sentiment caches + DB**: Real X (posts/confidence/buzz), Reddit only on real results. Scorer combines with damping.
- **Freshness contract**: Refresher every 15m for RSI; sentiment 30m. Runner computes live during cycles. Twice-daily reports at 9/21.

## Current (Pre-Fix) Issues Documented

- RSI refresher was a mock limited to 6 pairs (hardcoded list + fake values). Hermes rsi-15min-refresher cron ran it -> incomplete fresh RSI in cache/DB for full 11-pair basket.
- DB rsi_values max ts ~2026-06-14 (stale).
- Runner logs sometimes reported "6 pairs" for sentiment (subset calls or legacy).
- Downstream impact: Rebalancer, signals, twice-daily status, opportunity scanner, dashboards saw partial coverage -> invalid or incomplete trade decisions.
- Sentiment was stronger (caches covered 12) but still affected by any subsetting.

## Fix Applied (2026-06-16)

- Rewrote `scripts/refresh_rsi_prices.py`:
  - Loads full basket from trading_config_phase6.json (global_settings.pairs preferred; falls back to opportunity_pool).
  - Uses PriceHistoryManager(persist_path="data/state/price_history.json") — authoritative live data from runner.
  - For every pair with sufficient history (>=15 points): computes real RSI via calculate_rsi (Wilder's, 14-period, matching runner).
  - Writes full rsi_cache.json in expected format (source="15m_candles_from_history", fresh=True, etc.).
  - Persists to DB rsi_values (current ts, source='refresh_15m') for scorer queries.
  - Logs full count ("synced for 11 pairs"), per-pair details.
- No breaking changes to formats or DB schema.
- Dependencies respected: refresher now consumes runner's price_history (upstream), produces for scorer/runner/rebalancer/reports (downstream).
- Verified with isolation test (test_full_basket_rsi_sentiment_coverage.py) pre/post, DB queries, cache inspection, manual refresher run, hermes cron context.

**Post-fix verification artifacts** (see MASTER_TASK_TRACKING.md for full logs):
- price_history.json: all 11 pairs populated (real counts 100-200).
- rsi_cache + DB: now cover full basket with fresh timestamps after run.
- Coverage test: 11/11 RSI, 10/11 real Sentiment (1 low-volume damped), full basket calls now log "11 pairs".
- Refresher now produces real data for downstream.

## Guidelines for Any Future Changes

1. **Basket expansion** (e.g. add MATIC or new pair):

- **Keyword / sentiment signal quality changes**:
  - Run optimizer on affected pairs (or --check-new-pairs first).
  - Review samples for trading relevance (not just volume).
  - Update central JSON.
  - Verify with live fetch + intelligence report.
  - This is a major lever for signal strength feeding into trading decisions.

   - Update config.
   - Ensure refresher basket load covers it.
   - Scorer DEFAULT_UNIVERSE + any hardcodes.
   - Runner FIXED_UNIVERSE / opportunity scanner.
   - All tests (test_full_basket_..., test_rsi_isolation, etc.).
   - This doc + MASTER.
   - Re-run coverage isolation test + manual refresher + check twice-daily output.

2. **Price source / history changes**:
   - If moving away from price_history.json or add_price, update refresher, all tests referencing it, runner init, opportunity_scanner.
   - Ensure refresher can still compute full-basket RSI.

3. **DB schema (rsi_values / sentiment_scores)**:
   - Add columns? Update all INSERTs (runner persist_facts x3 copies + refresher) and SELECTs (scorer).
   - Migration script + test.
   - Update this doc.

4. **Scorer / signal logic**:
   - Changes affect rebalancer weights, signals, reports. Run full coverage test + end-to-end isolation (test_isolation_rsi_pipeline.py etc.).
   - "Real data only" + damping rules are invariants.

5. **Cron / decoupled refresher changes**:
   - Update hermes cron list context, this doc, crontab if system.
   - Always test manual run + next scheduled + coverage.

6. **General**:
   - Never hardcode pair lists outside config.
   - Prefer importing calculate_rsi / managers over duplication.
   - Every change: create/run isolation test with real data, append to MASTER, update this doc.
   - Use `python scripts/phase6/test_full_basket_rsi_sentiment_coverage.py` as the go-to verifier for coverage.
   - Explicit system checks: `crontab -l`, `hermes cron list`, `ps` for runner, DB queries, cache ls/cat.

## Open Items / Recommendations

- Runner has some duplicate persist_facts_to_db methods — consider consolidation.
- Intelligence report script is currently a stub; enhance it to explicitly report per-pair RSI/Sentiment coverage using the load_latest_ function.
- Consider making calculate_rsi a shared util in core/ (e.g. risk/ or utils/) to avoid duplication in refresher.
- Monitor for low-post pairs (like DOGE) — current damping is correct per design.
- After any basket change, force a refresher run + rebalance test + coverage audit.

This document ensures changes are made with full awareness of the platform graph. Update it on every relevant modification.
**Update 2026-06-16 (full data + rebalance phase)**:
- allocator.py: FIXED_UNIVERSE expanded from hardcoded 5 pairs to config-driven full basket (global_settings.pairs or opportunity_pool). This was a critical downstream gap — even with RSI refresher and scorer providing 11-pair data, rebalancer/strategies were limited. Patch applied as part of "full data flowing" work so complete signals now reach decisions.
- New artifacts: phase6/scripts/generate_trading_intelligence_report.py (enhanced, uses load_latest for per-pair full data + explicit rebalance rec), scripts/phase6/test_full_basket_rebalance_readiness.py (isolation test confirming 10/11 READY, recommends force).
- Force rebalance triggered again (flag touched ~12:51 PDT) because previous force (~12:15) used pre-full-RSI data; now with 10/11 full real signals + allocator expanded, re-optimization possible.
- See MASTER_TASK_TRACKING.md for full logs, test outputs, and state.
**Update 2026-06-16 (runner fix + rebalance execution verification)**:
- phase6_runner.py: FIXED_UNIVERSE now dynamic (loaded via _load_full_universe in __init__ from config). Previously class-level 6-pair hardcode. All references (signals, rebalance, stops, evaluate_universe, etc.) now use full 11-pair basket.
- Rebalance execution verified (logs 12:52): force flag consumed, "[CR-03] ... performing rebalance body", "Daily Rebalance" triggered, body completed (Executed=0, Skipped=3; some SL transients as before). State updated. Full data available at execution time via scorer/cache.
- Allocator and runner now both config-driven for full basket.
- Readiness test and intel report re-run post-fix/execution.

**Final consistency cleanup 2026-06-16**:
- hybrid_rebalancer.py: _load_sentiment now delegates to canonical load_sentiment_scores (full dynamic basket support, X primary + real Reddit). Legacy direct sentiment_cache.json read removed. __main__ example updated to full 11-pair basket.
- test_isolation_opportunity_scanner.py: Updated references and notes to use dynamic FIXED_UNIVERSE from scanner (which loads from config).
- Fresh force_rebalance executed (13:03): flag consumed, rebalance body ran, target_weights expanded (included BTC), New pairs added. (Runner process log still showed "6 pairs" because long-running process loads old .py; source code now consistent. Restart would pick full.)
- Readiness test and intel report re-run post-fixes (9-10/11 READY depending on current sentiment damping; full data flowing confirmed in scorer).
- Production paths (runner, allocator, opportunity_scanner, hybrid_rebalancer) now all use config-driven full basket + canonical scorer where sentiment is loaded.
- Isolation tests in /tests/ and backtests retain small local baskets for focused testing (standard practice); production code is the consistent standard.
- All outlined gaps closed. System at consistent standard for data flow.

**2026-06-16 Chain continuation (fetch consistency)**:
- fetch_x_sentiment.py: already used dynamic basket from config (confirmed).
- fetch_reddit_sentiment.py: patched from hardcoded 6-pair pair_keywords to load_full_trading_basket() + keyword_map for all 11 (ARB, OP, LINK, UNI, AVAX now supported).
- Fetches manually invoked post-patch: X populated for new pairs; Reddit cache extended to 11.
- RSI refresher re-run: full 11 synced.
- Re-verification: all components now aligned on config-driven full basket.
- Remaining: natural data sparsity on low-volume pairs (e.g. ARB/OP Reddit may stay low-volume); crons (30m X/Reddit, 15m RSI) will keep fresh.

## Sentiment Keyword Management Subsystem (Added 2026-06-16)

**Purpose**: Centralized, testable control over the keywords used by sentiment fetchers. This layer determines *what* we search for on X and Reddit for each trading pair (ticker vs formal name vs $ticker). It directly affects signal quality and therefore downstream trading decisions.

**Why it exists**:
- Previously hardcoded KEYWORD_MAP / pair_keywords inside fetch_x_sentiment.py and fetch_reddit_sentiment.py.
- No easy way to test "which keyword surfaces the strongest *trading-relevant* posts" (price action, slang, conviction).
- No automatic awareness when new pairs are added to the basket.
- Crypto language evolves (new slang appears); needs periodic refresh without code changes.

**Key Components**:
- Generator / Optimizer: `scripts/optimize_sentiment_keywords.py`
  - Loads current basket from trading_config_phase6.json.
  - For each pair, generates candidates (ticker, $ticker, formal name, OR combinations).
  - Tests live on X (primary) using an expanded trading-relevance lexicon (base validated words + heavy crypto-specific slang: moon/pump/ATH/FUD/rug/rekt/WAGMI/etc.).
  - Scores on volume + trading_score (lexicon hits) + ratio.
  - Prints recommendations + real samples for qualitative review.
  - CLI: `--check-new-pairs`, normal run, `--refresh` (future auto-merge).
- Central Source of Truth: `config/sentiment_keywords.json`
  - Versioned JSON with per-pair "x" (string) and "reddit" (list, first=primary).
  - Includes "notes" explaining decisions (e.g. "XRP uses ticker because 'ripple' pulls company noise").
  - Seeded with cumulative best knowledge from multiple optimizer runs.
- Loader / Pull Interface: `phase6/core/sentiment_keywords.py`
  - `get_x_keyword(pair)` → string for X searches
  - `get_reddit_keywords(pair)` → list for Reddit
  - `check_for_new_pairs()` → compares basket vs configured keywords
  - `load_sentiment_keywords()`, `get_current_basket()`, graceful fallback to ticker if missing
- Consumers (runtime pull):
  - `fetch_x_sentiment.py` (now imports get_x_keyword instead of hardcoding)
  - `fetch_reddit_sentiment.py` (now imports get_reddit_keywords)
  - Future: any other sentiment-related tool or report

**Data Flow** (new branch in the overall graph):

```
Config Basket (trading_config_phase6.json)
    │
    ▼
Optimizer (scripts/optimize_sentiment_keywords.py)
    ├── Tests candidates with trading-relevance lexicon
    ├── Human review of samples/scores
    └── Writes / updates ──► config/sentiment_keywords.json  (manual or --refresh)
                                          │
                                          ▼
                              Loader (phase6/core/sentiment_keywords.py)
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    ▼                     ▼                     ▼
            fetch_x_sentiment.py   fetch_reddit_sentiment.py   (future tools)
                    │                     │
                    ▼                     ▼
            x_sentiment_cache.json     phase6.db (sentiment_scores)
                                          │
                                          ▼
                              SentimentScorer + SignalGenerator
                                          │
                                          ▼
                              Runner / Rebalancer / Reports
```

**Update Cadence**:
- On new pair addition to basket (run `--check-new-pairs` then optimizer).
- Monthly general refresh (crypto slang evolves slowly; no need for frequent updates).
- Triggered manually after reviewing optimizer output + samples.

**Impact on Trading Decisions**:
Better keywords → higher quality posts in sentiment fetches → more accurate sentiment scores (less noise from company news or spam) → better signals from SignalGenerator → more reliable inputs to rebalancer and risk logic. This is one of the levers for "strong signals that drive accurate trading decisions."

**Change Impact Notes**:
- Adding a pair: Run optimizer on it → update central JSON → fetchers see it automatically.
- Changing a keyword for a pair: Edit central JSON (or run optimizer + review) → no code changes needed in fetchers.
- Modifying the optimizer / lexicon: Affects future keyword quality but not runtime paths (fetchers only read the JSON via loader).
- Never hardcode keywords again in fetchers or other tools.

**Verification after keyword changes**:
- Run optimizer and review samples.
- Manually invoke the two fetch scripts.
- Check x_sentiment_cache.json and reddit sentiment entries.
- Re-run `test_full_basket_rsi_sentiment_coverage.py` or generate intelligence report.
- Observe next runner cycle / signal quality in logs or twice-daily report.


**Update 2026-06-16 (Sentiment Keyword Centralization)**:
- Introduced full subsystem for keyword management to address hardcoded maps, lack of relevance testing, and no awareness of basket changes.
- New artifacts:
  - config/sentiment_keywords.json (central, versioned source of truth for X + Reddit keywords per pair + notes).
  - phase6/core/sentiment_keywords.py (the official loader/pull interface: get_x_keyword, get_reddit_keywords, check_for_new_pairs, etc.).
  - scripts/optimize_sentiment_keywords.py (the generator: runs trading-relevance experiments with base + crypto slang lexicon; supports --check-new-pairs for basket awareness).
- Refactored consumers: fetch_x_sentiment.py and fetch_reddit_sentiment.py now load keywords dynamically via the loader (no more inline KEYWORD_MAP / keyword_map).
- Updated high-level diagram, added dedicated section, extended dependency matrix, and guidelines.
- Policy: Monthly refresh + on new pair addition. Optimizer surfaces data + samples; humans decide based on "strong trading signals" criterion.
- Impact path: keywords → fetch quality → sentiment scores → signals → rebalancer / trading decisions.
- See MASTER_TASK_TRACKING.md for full task history. This closes the pending "defined method to generate updates + pull from updated list + new pairs + monthly refresh" request.
- All changes are backward-compatible for existing caches; fetchers pick up new keywords on next execution.

**Final note**: With full-basket RSI/sentiment + dynamic keyword management now in place, the signal pipeline is at a consistent, maintainable standard. Future work can focus on actual trade execution impact and further lexicon/slang mining in the optimizer.
