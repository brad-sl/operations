---
name: trading-bot-operations
description: Class-level patterns for deploying, monitoring, debugging, and verifying crypto trading bots (Phase 6 style). Covers dashboards, lightweight alerting, backtesting/reality checks, systemd services, and common live-mode pitfalls.
tags: [trading, crypto, dashboard, monitoring, backtest, deployment, verification]
---

# Trading Bot Operations (Umbrella)

This skill consolidates all operational concerns for long-running crypto trading bots.

## Dashboard Deployment & Maintenance (from trading-bot-dashboards)
- Use minimal stable HTTP server when socketserver fails with invalid fd.
- Separate ports: 8501 (live) / 8502 (paper).
- Specific formatting: USD with 2 decimals + $, Value column, last 3 days trades.
- Real data wiring for live positions with known open positions fallback.
- Per-pair sentiment integration.

**2026-06-12 Dashboard Cache Positions Fix + Holdings Balance Diagnostic**: The live state writer must always unwrap the `LivePortfolioManager` / `get_enriched_positions` return value (the `{"positions": {...}, "verified": bool, "error": ...}` wrapper or error sentinel) before the `for key, data in ...items()` loop that builds the positions list for `phase6_live_state.json`. Failure produces exactly the observed garbage (`positions-USD`, `verified-USD` etc.) in the dashboard. 

Additionally, `get_account_balance(currency)` (used for cash + any per-asset checks in runner) must compute `total = available + hold`. Coinbase brokerage/wallet accounts put the owned crypto quantity in the "hold" field for "XXX Wallet" accounts (available often 0 for holdings; USD cash is in available). The raw wrapper always shows both.

See `references/dashboard-positions-wrapper-leak-2026-06-12.md` and the companion `references/holdings-balance-manual-wrapper-diagnostic-2026-06-12.md` (raw wrapper output from direct `CoinbaseWrapper.get_accounts()`, comparison to client abstractions, the get_account_balance patch, manual cache rebuild script used for immediate correct dashboard view, and verification that manual wrapper + live client now agree on real ~$778 total with ETH/XRP positions).

Apply the same "manual wrapper first → compare raw shape (especially available vs hold) → fix abstraction(s) → re-verify with same manual script + cache hygiene if needed" pattern for any balance/holdings/positions source. This is now standing diagnostic practice (user directive).

This is the dashboard + balance source integrity instance of the wrapper normalization + real-data verification rule.

## 2026-06-12 Dashboard Display Corrections from Live User Review (Post-SQL + Launch)

After the DB views backend + persistent launch delivered clean positions (2 pairs: ETH 0.0857 $142.89, XRP 18.637 $21.08, total ~777.68, "Live (DB view)" source, active=2), user reviewed the rendered UI (screenshot) and gave precise corrections:

- Last Updated: include short date + time (e.g. "Jun 12, 12:18 PM") from the API `last_updated` (ISO-ish string).
- Total Portfolio Value: round to 2 decimals (`$777.68`).
- Recent Rebalances: repeating; "4 pairs $500" was not actually executed (rebal data: "executed": 0, "skipped": 2, "reason": "daily_rebalance", capital 500) — shouldn't show. Need a more relevant status message.
- Recent Trades: "21:22" (should be short date, e.g. "Jun 6 21:22").
- Recovery Status: Should be "in recovery" since only two pairs active.

**Implemented in `phase6_dashboard.html` (updateDashboard, trades/rebal rendering, updateRecoveryStatus, init):**

- Header/last-updated + total: parse `balData.last_updated` (or pos), `new Date(...).toLocaleDateString('en-US', {month:'short', day:'numeric'}) + ', ' + time`; `parseFloat(total).toFixed(2)` (and `.toFixed(2)` in init for total-balance).
- Trades: `if (t.timestamp) { const d = new Date(t.timestamp); timeStr = d.toLocaleDateString('en-US', {month:'short', day:'numeric'}) + ' ' + d.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'}); }` (replaced slice(11,16)).
- Rebalances: `let goodRebals = rebalData.rebalances.filter(r => (r.executed || 0) > 0 || (r.capital_deployed_usd || 0) > 10);` then if (!goodRebals.length) show `'No executed rebalances (recovery mode - 2 pairs active, capital preserved)'` else render the good ones (with time/reason/pairs/cap).
- Recovery: `const res = await fetch('/api/recovery'); ... let mode = data.mode || 'normal'; ... if (posDataForRec && (posDataForRec.active_positions || 0) <= 2) { mode = 'recovery'; cooldown = 'Limited deployment (capital preservation)'; }` (also fixed the fetch from broken `/data/state/recovery_state.json` to the proper API). Called from updateDashboard(posData) for sync; interval falls back.

These are now canonical patterns for Phase 6 dashboard *display layer* maintenance: derive UI state/formatting from live API metrics (active_positions for mode, rebal.executed flag for relevance), consistent short-date + 2dp formatting from the ISO timestamps/totals the SQL views produce, and relevant messages when data indicates recovery/limited execution.

See `references/phase6-dashboard-display-corrections-2026-06-12.md` for the exact user feedback transcript, before/after JS blocks, and verification that served HTML contains the new strings while APIs remain clean "Live (DB view)" + 2 pairs.

## Locating Canonical serve_dashboard.py and Endpoint History (DASH-001 style tasks)
When the task asks for "changes made to serve_dashboard.py during DASH-XXX work" and no exact path is given:
1. First run discovery: `find $HOME -name serve_dashboard.py 2>/dev/null` (or equivalent) to surface all copies.
2. Identify the authoritative version by presence of `.git` at the project root (usually `projects/crypto-trading-bot/` or equivalent main repo). Ignore temporary copies under `.hermes/kanban/boards/.../workspaces/` and `.openclaw/workspace/...` unless the task explicitly targets a workspace.
3. Use targeted git commands on the discovered main path:
   - `git log --oneline -S <endpoint> -- serve_dashboard.py`
   - `git show <commit> -- serve_dashboard.py | grep -A 30 -E '(/api/sentiment|/api/performance)'`
4. If read_file fails on a path that `ls` confirms exists, fall back to terminal with absolute commands (`/usr/bin/cat`, `/usr/bin/sed -n '/pattern/,+N p'`).
5. Focus extraction on the requested endpoints only; do not dump entire file diffs unless asked.

Pitfall: Never assume the file lives in the current working directory or a fixed path like `/workspace/...`. Always discover first.

## Lightweight Monitoring & Alerting (from trading-bot-monitoring)
- Log-based detection of rebalance/trade events.
- Concise Telegram alerts via cron (every 15-30 min).
- State file to avoid duplicate alerts.
- Script location: `~/.hermes/scripts/`.

## Rebalance Watchdog, Cron Monitors & Daily State Persistence
**Core pattern (2026-06-12 session):** Daily rebalance (scheduled ~09:00 via `scheduler.daily_rebalance_time` in runner) must update a persistent `phase6_runner_state.json` (`last_rebalance_date`). A separate cron monitor (`monitor_phase6_runner.py`) polls it + runner liveness and sends Telegram on gaps.

**Required invariants:**
- Runner: calendar check in `_should_rebalance` (date > last and time >= target) OR force/hybrid must reach the `last_rebalance_date = date.today(); _save_state()` **after** all exchange/calc steps.
- Live client: `CoinbaseExchangeClient` + `LivePortfolioManager` must return verified positions (requires `get_accounts()` on wrapper).
- Monitor: must incorporate schedule grace (post-10:00) + same-day or yesterday-before-grace = healthy; only warn on true missed windows.
- All numeric paths on `get_enriched_positions()` / `get_positions()` returns must normalize the LPM wrapper (`{"positions":..., "verified":..., "error":...}`) vs flat dict before any `float(p.get...)` or `.values()` iteration.

**Key pitfalls captured:**
- Sentinel `"Unverified or error"` (or bare error strings) leaking into `sum( float(...) for p in ...values() )` or `for k,v in .items()` inside `_perform_daily_rebalance` (reserve block + norm + CR-03 context) → ValueError before state save.
- Monitor using pure date-diff without `daily_rebalance_time` awareness → spam at 00:xx–08:xx on day+2 even when 9am window pending.
- Partial wrapper ports (only order methods + _request) break verification even if auth works.
- Dashboard cache and other callers doing unconditional `.get()` on whatever `enriched` returns.

**Fix recipe (reproducible):**
1. Add `get_accounts` to `coinbase_wrapper_FIXED.py` (and ensure it is imported/used in live paths).
2. Add early normalization helper or inline guard at every use of `get_enriched_positions()` in rebalance/hardening code.
3. Move or guard state update (use try/finally around fallible exchange blocks inside the rebalance method, or compute date update before risky steps).
4. Rewrite monitor `check_last_rebalance` with explicit grace logic (see the reference for exact before/after).
5. Add `return False` to any scheduler helper that can fall off the end.
6. Guard all position-data consumers (`isinstance(data, dict)` before `.get`).

**Verification (isolation-first):**
- Standalone script exercising monitor with injected state dates at different wall times.
- Cycle log + state.json diff after a forced rebalance.
- Confirm no "Unverified" strings reach arithmetic when client succeeds.
- Cross-check with `journalctl`, `phase6_runner_error.log`, `crontab -l`, `ps`.

See `references/rebalance-watchdog-and-state-persistence.md` for full symptom transcripts, exact error lines, code diffs applied, and related session artifacts.

This class of watchdog + live verification + state persistence bug is recurring in Phase 6 live ops.

## Strategy Verification & Backtesting (from trading-strategy-verification)
- Replay logged price + sentiment data.
- Compare against current regime/sentiment/rebalance rules.
- Lightweight on-demand runner (`phase6_backtest.py`).
- Sensitivity analysis and Markdown reports.
- Avoid overfitting and ignore slippage gap.

## Related Patterns
- See `systemd-service-management` for production persistence.
- See `hermes-dashboard-deployment` for dual-mode Paper/Live deployment.
- See `paper-trading` for the core PaperTrader implementation.
- See `coinbase-advanced-trade` and `coinbase-live-deployment` for exchange integration.

## Production Harness Wiring (Phase 6 Style) — Real Data Only
**Core rule**: All production harnesses must refuse to operate without live exchange data and live sentiment. Never fall back to hardcoded values or simulation in the main path.
**Signal Pipeline Reliability (RSI + Sentiment Freshness)**

When the user reports issues with fresh RSI or Sentiment signals (critical for downstream signals, rebalancing, allocation):

**Mandatory pre-fix workflow (user-enforced, from 2026-06-11 session):**
1. Review specs in `phase6/specs/` (SENTIMENT_SYSTEM_SPEC.md, PHASE_5_1_REBALANCE_FEATURE_SPEC.md, PHASE_6_REBALANCING.md, etc.) to recall intended architecture (batch queries, 30min aggregation, per-cycle RSI with 15m candles, decay, no-fab rules, max age 60min).
2. Review completed tasks via `handoffs/phase6/` (especially sentiment fabrication handoffs like P6-121/122) + `docs/MASTER_TASK_TRACKING.md` to determine exactly which functional changes were previously delivered vs. current gaps.
3. Derive a **comprehensive structured plan** (see `writing-plans` + `systematic-debugging` skills) before any code changes or patches. The plan must:
   - Identify root causes (e.g., runner-coupled updates, missing independent crons, duplication, weak staleness gates).
   - Avoid "in-place patching" — user explicitly dislikes this pattern as it leads to repeated thrashing without addressing roots.
   - Explicitly address scalability for 100's of users: query optimization (combined/batched X/Reddit queries, incremental candles, shared caches), rate-limit safety, centralized Signal Provider abstraction so background workers (not per-runner) hit external APIs.
   - Mandate Code Isolation Testing (real data only, zero-result cases preserve prior timestamps + explicit markers, freshness gates).
   - Include independent refresh pipelines (Hermes cron for 30min sentiment + RSI), observability (age_minutes, post counts), conservative fallbacks (neutral on stale).
4. Produce the plan as a durable artifact in `project/docs/RSI_SENTIMENT_RELIABILITY_PLAN.md` (or equivalent) and append a tracking entry to `docs/MASTER_TASK_TRACKING.md`.
5. Only then proceed to implementation, with handoff docs for delegation.

**Pitfall to avoid**: Jumping straight to editing `run_sentiment_system.py`, `refresh_sentiment.py`, runner `_update_price_history_and_calculate_rsi`, or exchange_client without the spec + completed-tasks review. This was the exact frustration signal in the 2026-06-11 session ("fixing things in-place without a structured plan, patching the wrong things and never getting to the root").

**Scalability requirements (non-negotiable for this class)**: 
- Batch wherever possible (combined X keywords "BTC OR ETH...", Apify multi-term if supported).
- Shared background signal workers + canonical caches (file or better) consumed by all runners/dashboards.
- In-mem + TTL disk caches in fetchers/clients.
- Monitor and log API call volume per refresh.

See the 2026-06-11 plan for full phased breakdown (audit, canonicalize, decoupled crons, optimization, provider abstraction, integration + tests).

**References**:
- `references/rsi-sentiment-reliability-2026-06-11.md` (condensed session learnings, gaps identified, key plan excerpts).
- Project plan: `projects/crypto-trading-bot/docs/RSI_SENTIMENT_RELIABILITY_PLAN.md`
- Related handoffs: `handoffs/phase6/Handoff_FABLE5_P6-121_122_Sentiment_Fabrication.md`
- Existing sentiment scripts already under this skill: `scripts/monitor_canonical_sentiment.py`, `scripts/refresh_sentiment.py`

**Parallel Pipeline Data Contract Alignment (RSI/Sentiment Refreshers + DASH-SQL Shared Tables) — 2026-06-12 Lesson**

When running parallel tracks (decoupled reliability refreshers for RSI/Sentiment + DASH-SQL views for dashboard facts), the "shared tables" contract (prices, rsi_values, sentiment_scores in phase6.db) must be enforced at the *producers*.

**Per-Pair RSI Display from Decoupled 15m Refresher (DASH-RSI-001, 2026-06-12)**:
After dual-writes were in place, added user-requested "Per Pair RSI with the text notation (same as twice daily status)" to the dashboard using most recent fetch.
- New `/api/rsi` endpoint (DB `rsi_values` latest per-pair preferred; fallback to `data/state/rsi_cache.json`).
- HTML: New "RSI (15m)" grid card parallel to Sentiment.
- Render: `RSI=52.96 (Neutral)` (or Oversold <30 emerald, Overbought >70 red) — exactly matching refresher prints ("RSI=50.94 (from 30 closes, Wilder)") and legacy twice-daily status style ("RSI=50.0 (neutral)").
- Source attribution in the response for transparency.
- Verified via manual refresher run + sqlite + API responses with real 15m values (BTC ~50.94, ETH ~52.96, etc.).

This is now the standing pattern for surfacing momentum indicators from the independent 15m refresher pipeline in the Phase 6 dashboard. See references/phase6-dashboard-display-corrections-2026-06-12.md for the broader display layer work (short dates, toFixed(2), executed-only rebalances, recovery forcing).

**The conflict diagnosed in-session**:
- DASH-SQL created tables + views (v_latest_prices, v_enriched_positions, v_phase6_dashboard) assuming refresh scripts + runner would populate them.
- RSI refresher (`scripts/refresh_rsi_prices.py`) only wrote JSON (`data/state/rsi_cache.json`, price_history.json, live_state "rsi").
- Sentiment writer (`run_full_sentiment_v3.py`) only wrote the canonical cache.
- `persist_facts_to_db` (in phase6_runner) only executed during trading cycles (not from independent no-agent crons).
- Result (verified by direct sqlite query): `rsi_values` and `sentiment_scores` empty; prices had only runner snapshots. Dashboard SQL views could not deliver dynamic RSI/sentiment.
- `/api/sentiment` in serve_dashboard still read the old cache path (not the DB table).

**Standing rule for this class**:
Refresh pipelines (the source of fresh dynamic values) **must dual-write**:
- Their canonical JSON caches (for reliability, no-fab, scorer consumption, live_state).
- The phase6.db fact tables (prices/rsi_values/sentiment_scores) using INSERT OR REPLACE with ts, pair, value/score, source (e.g. "15m_refresher", "run_full_sentiment_v3").

Runner persist continues for trading-snapshot facts (balances, holdings, price snapshots during rebalance).

**Fix pattern applied**:
- Added dual-write block in `refresh_rsi_prices.py` (after JSON + live_state write): sqlite connect, INSERT rsi_values (and optionally latest prices from closes/history).
- Added dual-write block in `run_full_sentiment_v3.py` (after write_canonical_cache in the results path): INSERT into sentiment_scores (score, posts, source, ts).
- Updated `serve_dashboard.py` /api/sentiment handler to first query the DB table (latest per-pair from sentiment_scores) and return with source "phase6_db.sentiment_scores (dynamic)" if rows present; fallback to old cache path.
- Re-ran migration for safety.
- Verified by manual run of refresher + sentiment writer + sqlite queries showing populated rows with correct source + timestamps + the no-fab 0.0 + posts=0 behavior preserved.

**Verification discipline (mandatory)**:
After any dual-write change:
1. Manually trigger the refresher/writer (python scripts/... or the cron wrapper).
2. Query both sides side-by-side: `SELECT * FROM rsi_values ORDER BY ts DESC LIMIT 3` vs `cat data/state/rsi_cache.json | jq '.rsi | to_entries[0:2]'`.
3. Hit the dashboard APIs (`curl localhost:8502/api/positions`, `/api/sentiment`) and confirm source strings and real values.
4. Confirm no fabrication (0 posts → score 0.0 with status marker).

See `references/parallel-pipeline-shared-db-contract-2026-06-12.md` for the exact diagnosis transcript (DB query vs JSON), the code blocks added, the terminal outputs from the verification runs, and the commands to re-verify in future sessions.

This pattern prevents the exact "refresher is live but dashboard SQL sees stale/empty dynamic data" failure mode when tracks share a fact contract. Always make the independent producers own the dual-write.

## Dynamic Trading Pool Selection & Opportunity Pool Expansion (2026-06-13)

**Core pattern for pair management in Phase 6 bots**:
- **Active Trading Pool / Dynamic Trading Pool**: Limited selection (hard cap via expansion_rules.max_pairs=12) kept for runner performance, rebalancing cost, and live execution stability. The runner and hybrid_rebalancer operate only on this pool.
- **Opportunity Pool / Candidate Pool**: Larger set (target 10-12+) that the opportunity scanner scores and filters for "most opportune" next investments (test allocations, tilts, or expansions). The scanner's job is to rank from the full opportunity pool and produce a small number of high-conviction proposals.

**Why the separation**:
- Small active pool keeps the live loop performant and the rebalance decision space manageable.
- Larger opportunity pool lets the composite scorer (40% RSI-momentum, 20% sentiment, 25% vol-adj edge, 15% diversification) actually exercise filtering, diversification bonuses, and rejection of most candidates — critical in lackluster or down markets where you want to surface the relatively strongest signals from a broader set.

**Implementation rules (enforced in this session)**:
- Define OPPORTUNITY_POOL explicitly in scanner and refresher (back-compat via FIXED_UNIVERSE alias).
- Refresher (`scripts/refresh_rsi_prices.py`): Extend FIXED_UNIVERSE / OPPORTUNITY_POOL, fetch real 15m candles for all. Skip pairs with insufficient closes (no fabrication) — this is correct behavior.
- Scanner: Use OPPORTUNITY_POOL for scoring/ranking. Keep CURRENT_BASKET / active trading pool as the limited deployed set. Proposals are always small test sizes and explicitly gated.
- Isolation test: Must be updated to assert scale ("ranked 12 pairs") + selectivity (still only 1-2 proposals). Run it; surface raw output.
- Config: Add `opportunity_pool` key for the large set; keep `global_settings.pairs` and `expansion_rules.max_pairs` for the active trading pool.
- Tracking: Append to scanner_origins.jsonl with "pool_type": "opportunity_pool_expanded", "dynamic_trading_pool_selection" tag, pairs_scored count. Update MASTER_TASK_TRACKING.md with evidence + sign-off (durable primary record).
- All proposals remain shadow-only until #5 AB + paper gates.

**Future extension (explicitly noted)**: A separate **Pool Cycling script** (not in the runner) that consumes scanner scores + additional search criteria to propose swaps into/out of the limited Active Trading Pool. This keeps the cycling logic decoupled from the hot trading path.

**Verification discipline**:
- After expanding the opportunity pool: run refresher → run updated isolation test → inspect ranked count and proposal selectivity → append tracking entries → update MASTER.
- Real data only at every step.

See `references/dynamic-trading-pool-selection-2026-06-13.md` for the session transcript, exact code diffs, refresher output (11/12 pairs populated), scanner run showing "ranked 12 pairs", isolation test output, and tracking appends.

This pattern (limited active + scored opportunity pool + separate future cycler) is now the standing approach for pair expansion work in the bot.

**Dynamic Per-Trader Basket Sentiment & RSI Sourcing with Conditional Multi-Source (X Primary + Reddit Only on Real Results) + Shared DB Cache (2026-06-13 continuation)**

**User clarification signal**: After "This was supposed to be fixed yesterday" on sentiment neutrality, explicit rule update: "If the Apify/Reddit return result is empty don't use it. Otherwise if there are values returned DO use it." (Backtest ROI benefit when Reddit contributed real signal.) Also required dynamic basket support so runner/rebalancer can promote/liquidate and RSI/Sentiment are queryable per-trader with shared cache benefit for similar baskets.

**Batching for statistical significance + Volume/Post-Count Scaling (2026-06-13 user query follow-up)**

User noted: With 100-result cap on X recent search, single combined query for 12-pair basket yields many pairs with <10 posts (not statistically significant). High-volume ("buzz") pairs (e.g. LINK 42 posts, OP 26 in one run, later OP 92) dominate and indicate stronger signal.

**Standing pattern for X (and similar external) sentiment acquisition in large/dynamic baskets** (updated per explicit user preference):
- When basket size > 5-6 pairs, automatically use batched mode: split into groups of ~5 pairs, each gets its own API call (up to 100 results per batch). This is now the default in the clean fetcher implementation.
- This increases average posts-per-pair significantly vs one mixed 100-post query (statistical significance).
- In `calculate_sentiment`, return rich dict: `{"sentiment": base, "post_count": n, "confidence": scaled_by_posts}`. Do **not** apply a buzz multiplier to the stored `sentiment` value itself (user concern: transient/short-lived effects will mis-target the infrequently-running opportunity scanner; post-count scaling in the scorer is adequate weighting).
- Store the full rich fields (`post_count`, `confidence`) in `x_sentiment_cache.json`.
- In scorer `load_x_sentiment_scores`: damp sentiment toward 0 (conservative scaling, e.g. max 0.6 factor or lower) for pairs with `post_count < min_posts` (e.g. 8-10) or low `confidence`. This prevents noisy low-volume signals from affecting opportunity scores (20% sentiment component etc.).
- Expose `load_x_sentiment_details(basket)` for scanner/runner to inspect volume when needed.
- Update fetcher main to use the batched helper; keep single-query for small baskets.
- Always run with current dynamic basket from config; verify post counts in output and cache.
- Pitfall: Combined-query distribution favors "hot" keywords; batching + explicit post_count makes volume actionable and statistically sound. Never treat 0-post rows as usable neutral signal.

**Verification**: Re-run fetcher with dynamic basket → inspect per-pair posts/conf in print + cache → call scorer details + damped scores → confirm high-volume pairs surface real signal while low-volume are appropriately damped → append to MASTER + rebalance history.

See `references/phase6-runner-rebalance-force-direct-live-trade-2026-06-13.md` and the prior `references/batched-x-sentiment-buzz-factor.md` (the latter predates the "no sentiment-value multiplier" clarification).

This completes the data acquisition contract for dynamic multi-trader baskets: conditional real-results only, volume-aware (post-count scaling only on the value), statistically powered sampling, shared DB facts.

**Core rules (embed in all future sourcing work for this class)**:
- **X primary**: Real fetched X data (from x_sentiment_cache or equivalent) is always used when present for a pair.
- **Reddit/Apify conditional**: Only consume the Reddit value if the actor/fetch returned a **non-empty real result** (posts > 0 in DB row or meta["posts_analyzed"] > 0, with actual data). If empty (0 posts, below threshold, or preservation-only), **drop entirely** — return 0.0 as "no signal" (never as fake "Neutral"). When real Reddit values are present, use them (do not suppress).
- **Dynamic basket input**: All sentiment/RSI "queries" (load_sentiment_scores, scorers, scanners, fetchers) must accept the trading basket as a parameter (list of pairs). Never rely on module-level hardcoded FIXED_UNIVERSE / OPPORTUNITY_POOL / PAIRS at import time.
- **Source of basket**: Load at runtime from the trader's config (`config/trading_config_phase6.json`: `global_settings.pairs` or `phase_6_specific.opportunity_pool`). This is the authoritative "total trading pairs available in the trading basket for each trader".
- **Shared DB cache**: RSI and Sentiment facts are stored pair-level in `phase6.db` (`rsi_values`, `sentiment_scores` with ts/pair/value/score/posts/source). Any trader can query the pairs in their basket; similar baskets reuse the cache without re-scrape. Producers (refresher, v3 writer) must dual-write both canonical files (for no-fab, scorers) **and** the DB tables.
- **Real data enforcement (standing for this class)**: 0.0 only means "no signal from available sources after conditional filtering". Never fabricate neutral or use empty results as data. Code Isolation Testing + real DB/file side-by-side verification required after changes.
- **Runner/rebalancer impact**: With dynamic basket, the opportunity scanner produces proposals from the full opportunity set; rebalancer/runner can now use the full list to decide promotes, liquidations, or tilts within the limited active pool (max_pairs cap).

**Implementation pattern (applied this session)**:
- Fetchers: `run_full_sentiment_v3.py` and `scripts/refresh_rsi_prices.py` load PAIRS / FIXED_UNIVERSE dynamically from config at startup (with fallback keyword map for Apify).
- Scorer: `phase6/core/sentiment_scorer.py` exposes `load_sentiment_scores(universe=basket)`, `_load_reddit_from_db(universe)` (only non-zero posts), `load_x_sentiment_scores`, and `load_latest_sentiment_for_basket(basket)` (DB + X overlay for runner/rebal use). File canonical fallback only for transition, with "data" vs "sentiment" key tolerance.
- Scanner: Load OPPORTUNITY_POOL from config; pass dynamic universe to load functions; derive CURRENT_BASKET from it.
- DB dual-writes + verification: After run, query `SELECT pair, score, posts, source FROM sentiment_scores...` + call the loader + run scanner to confirm conditional logic and real X values surface.
- Config is the single source for the trader basket; DB provides the queryable shared facts.

**Verification discipline (always)**:
1. Re-run fetchers with the dynamic basket from current config.
2. DB inspection for posts/source (confirm 0-post rows exist but are ignored by loader).
3. Loader call with exact basket list from config → assert X values used where present, Reddit only on posts>0 cases, honest 0.0 elsewhere.
4. Scanner run confirms "Scanned universe" size matches basket and uses the conditional scores.
5. Side-by-side JSON cache vs DB; no fabrication.

**Pitfalls to avoid**:
- Hardcoding lists prevents dynamic promote/liquidate and per-trader flexibility.
- Treating all Reddit 0.0 as usable neutral (even from empty fetches) pollutes scoring and contradicts backtest learnings.
- Relying only on file caches loses the shared DB benefit for multiple baskets.
- Partial updates (fetcher dynamic but scorer still hardcoded) leave expansion pairs at fake 0.0.
- Applying buzz/volume multipliers directly to the stored sentiment value (transient high-buzz days will mis-target the scanner; use for confidence/damping only).

See `references/dynamic-basket-conditional-sentiment-2026-06-13.md` for the full session transcript, exact diffs to scorer/fetcher/scanner, loader/DB outputs from the run (X values like BTC +0.234 / DOGE +0.300 used; all Reddit posts=0 correctly dropped; 12-pair dynamic basket; DB rows), and the `load_latest_sentiment_for_basket` helper.

This extends the Dynamic Trading Pool pattern with the data sourcing contract required for runner/rebalancer decision-making and cross-trader cache reuse. Combine with `code-isolation-testing` for all changes. Real data + conditional sources + dynamic basket + DB facts is the durable contract for this class.

## One-Time Expensive External Model Review + Paper Gate + Live Arming Process
The canonical remediation path for high-stakes audits (Fable 5 class via OpenRouter) on the trading bot is:
1. Tiered review package + constraints (real data, verified-zero Fresh Start, sticky holdings + proportional, withdrawal reserve with projected targets in **every** allocation, mandatory Code Isolation Testing).
2. Small-batch ingest into `docs/MASTER_TASK_TRACKING.md` (authoritative) + tight handoffs (`handoffs/phase6/Handoff_FABLE5_P6-...md` with explicit isolation test name + success criteria). Kanban for visibility only.
3. Per-finding: standalone real-data isolation test (`scripts/test_fable5_...py`), shadow verification, "SCOTTY SIGN-OFF" (crypto-orchestrator reviewer) comment on card + MASTER before promotion.
4. **Always prefer Option A**: After "CONDITIONAL GO for paper", instrument paper harness with forced telemetry + mid-cycle error injection for every remaining gate/guard. Run extended paper (50-100+ ticks). Capture log + `.paper_summary.json` (rebalances executed, reserve values, ages, final positions, injected errors respected).
5. Delta bundle only for any targeted re-gate.
6. Riders from re-gate go to the *next routine paper run* (no new expensive call unless user explicitly requests).
7. Final paper GO → live arming: executable launcher script that sources Hermes env for keys, then `phase6/core/phase6_runner.py --mode live --confirm-live` (runner hard-enforces the safety flag). Document exact command + schedule in `docs/`. Wire to Hermes cron (0 9/21 * * *) with Telegram delivery if desired. Provide `docs/LIVE_DEPLOY_COMMAND_*.txt` and `docs/PHASE6_LIVE_SCHEDULE_*.md`.

All of the above must respect the user's explicit "expensive model = targeted case-by-case only" constraint. See `code-isolation-testing` skill + its `references/expensive-model-review-to-paper-to-live-gate.md` for the complete class process and 2026-06-10 artifacts.

**Required components in a Phase 6 harness**:
1. `CoinbaseAdvancedClient` (or equivalent real client) with `get_accounts()` / balance methods.
2. `LivePortfolioManager` initialized with the real client (no dummy clients in production code).
3. `RealCapitalEventMonitor` that detects actual balance deltas.
4. `CapitalDeploymentRunner` (shadow by default) wired to the monitor.
5. `sentiment_loader` that reads from the live sentiment cache/pipeline.

**Strict enforcement patterns**:
- Runner must call `set_sentiment_and_candidates()` with real data before processing events.
- Monitor must raise or log loudly if no real `portfolio_manager` is provided.
- Test/simulation files (`dry_run_*`, `example_*`, `test_*`) must live in `phase6/tests/`, never in `scripts/`.
- Any code path that could reach live trading must have an explicit "real data only" guard.

**Migration pattern (Phase 5 → 6.0)**:
- Extend the Phase 5 client with any missing balance methods.
- Create a new `phase6_live_harness.py` that wires the four core components.
- Add sentiment integration as step 5 in `create_harness()`.
- Keep the new harness in shadow mode by default (`live=False`).

Session-specific details, scripts, and references live under `references/`, `templates/`, and `scripts/`.