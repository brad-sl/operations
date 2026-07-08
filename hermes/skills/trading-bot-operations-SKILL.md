---
name: trading-bot-operations
description: Class-level patterns for deploying, monitoring, debugging, and verifying crypto trading bots (Phase 6 style). Covers dashboards, alerting, backtests, systemd pitfalls; ANALYST-OPT scenario research (Path B + production compare for deploy decisions) → references/analyst-opt-scenario-research.md.
tags: [trading, crypto, dashboard, monitoring, backtest, deployment, verification]
---

# Trading Bot Operations (Umbrella)

This skill consolidates all operational concerns for long-running crypto trading bots.

## Crypto-Analyst optimization (ANALYST-OPT)

- Runbook: `references/analyst-opt-scenario-research.md` (Path B `arch4`, weekly cron, brief integration).
- When ranking scenarios for deploy or shadow promotion, **always** use `--compare-production` and surface since-go-live ledger P&L; if OHLCV and live calendars do not overlap, say so explicitly — do not treat sim as beating production on different dates.

## Phase 6 live runner singleton + restart

- **Runbook (2026-07-06):** `references/phase6-runner-singleton-sl-reattach.md` — systemd duplicate runners, rebalance/Telegram spam, SL order_id + **SL-ENTRY-ANCHOR-01** + **SL-INSUFFICIENT-FUND-02** (stop OC key detection), strategic brief hook, `reattach_sl_once.py`.
- **Start:** `bash scripts/phase6/start_phase6_runner.sh` (prefers `.venv/bin/python`).
- **Verify one process:** `ps -eo pid=,args= | grep -E '[p]ython.* -m phase6\.core\.phase6_runner'` — not loose `pgrep -f` (matches Hermes/bash wrappers).
- **Clean bounce:** kill python launches → `rm -f logs/phase6_runner.pid phase6_live.pid` → start script → `Phase6Runner initialized` + `[DB] Facts persisted`.
- **Hermes `background=true` + `exec python`:** wrapper may report exit `None`; confirm with `ps` + log tail.
- **systemd duplicate:** `phase6-runner.service` (`/usr/bin/python3`, `Restart=always`) conflicts with the start script — `bash scripts/phase6/disable_systemd_runner.sh` once; monitor auto-kills until disabled (`scripts/phase6/monitor_phase6_runner.py`).
- **Rebalance/Telegram spam:** same-day `_should_rebalance` + hybrid cooldown bugs → per-slot `rebalance_slots_completed`, no-op digest skip — see `references/phase6-runner-singleton-sl-reattach.md`.
- **SL re-attach / stale order_id / SOL preview:** same reference (sanitize_reattach_order_id, entry-anchor pitfall). re-attach order_id:** clear `_recent_buy_order_ids` at each daily rebalance; cycle-only BUY map; `sanitize_reattach_order_id` on re-attach. Detail: `references/phase6-runner-singleton-sl-reattach.md`.
- **Per-minute "Daily Rebalance Complete" Telegram (0 moves):** two bugs — (1) `_should_rebalance` returned true every 60s after 09:00 on same day; (2) `HybridRebalancer.evaluate()` fired every cycle because `last_rebalance_time` was never seeded from `last_rebalance_date`. Fix: `rebalance_slots_completed` (`YYYY-MM-DD|09:00`), skip digest when `executed==0 && skipped==0`, `_sync_hybrid_rebalance_cooldown()`, evaluate hybrid only when calendar slot not due. Detail: `references/rebalance-scheduler-telegram-spam-2026-07-06.md`. Test: `test_isolation_should_rebalance_slots.py`.

## Phase 6 architecture completion ("P4" backlog)

After Kanban **P0–P3** is cleared, remaining **architecture** work is often called **P4** even when `MASTER_TASK_TRACKING.md` has **no `P4` label** — `grep '\bP4\b'` on MASTER before citing a section.

**Intent:** finish `docs/phase6/ARCHITECTURE_ISOLATED_COMPONENTS.md` — single decision path, evaluation → allocator (optional mid-cycle **shadow**), thin orchestrator (`P4-05` / `CycleCoordinator`; `P4-05b` / `RebalanceCoordinator`), pre-rebalance refresh + SL preflight (ANALYST-005–008), default `trading/` `TradeExecutor`. Runner restart + coordinator stack: `references/phase6-runner-restart-and-coordinators-2026-07-06.md`, `references/phase6-runner-singleton-sl-reattach.md`.

**Canonical runner entry (operations repo):** `python3 -m phase6.core.phase6_runner` or `./scripts/phase6/start_phase6_runner.sh` — **not** `scripts/phase6/phase6_runner.py` (path does not exist). Rebalance windows **09:00 + 21:00 PT**.

**Before P4-05 extract:** load `code-isolation-testing` → `references/p4-05-cycle-coordinator-preflight-2026-07-06.md` (MASTER-vs-runner `rg` audit).

| ID | Focus | Verification |
|----|--------|----------------|
| P4-01 | Legacy `deploy_capital` only explicit fallback when `use_new_allocator=true` | `test_isolation_runner_wiring_arch4.py`; no `legacy_rebalance_plan` in live logs |
| P4-02 | One `evaluate_universe` per cycle; mid-cycle allocator shadow flag | Isolation wrapper + utilization in MASTER |
| P4-03 | Route hybrid `generate_rebalance_plan` stub to Allocator | `test_isolation_hybrid_trigger.py` |
| P4-04 | Platform executor default on ARCH-4 | `scripts/ops/test_isolation_allocator_platform_executor.py` |
| P4-05 | Extract cycle coordinator; shrink runner | `check_build_philosophy_compliance.py`; parity before live |
| P4-06 | MASTER section + Kanban parent; update architecture doc status | Dated evidence append |

**Order:** P4-06 → P4-01 → P4-03 → P4-02 (shadow) → P4-04 → P4-05. Real data + isolation tests; no mid-cycle live without shadow evidence.

Tier reconciliation: `kanban-orchestrator` → `references/master-backlog-priority-tiers-crypto-bot.md`.

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
- **New execution paths (ARCH-4 / use_new_allocator) with early returns**: date/state side-effects (last_rebalance_date, _save_state) lived only in legacy branch after the return. New path executed rebalances (visible in "[ARCH-4] Rebalance complete via new stack" logs) but never mutated the date the separate monitor cron reads. Result: stale date + warnings even on active rotation days (2026-06-20 P2 regression).

**Fix recipe (reproducible):**
1. Add `get_accounts` to `coinbase_wrapper_FIXED.py` (and ensure it is imported/used in live paths).
2. Add early normalization helper or inline guard at every use of `get_enriched_positions()` in rebalance/hardening code.
3. Move or guard state update (use try/finally around fallible exchange blocks inside the rebalance method, or compute date update before risky steps).
4. **When introducing parallel paths or early returns**: audit *every* exit from `_perform_daily_rebalance` / `_run_cycle` for monitor-visible side effects (last_rebalance_date, last_updated, event logs). Place the date set + _save_state() as early as possible after the decision (or unconditionally after any path that counts as "rebalance executed").
5. Rewrite monitor `check_last_rebalance` with explicit grace logic (see the reference for exact before/after).
6. Add `return False` to any scheduler helper that can fall off the end.
7. Guard all position-data consumers (`isinstance(data, dict)` before `.get`).

See `references/rebalance-state-desync-new-allocator-early-return-2026-06-20.md` for the exact 2026-06-20 diagnosis (state stuck at 2026-06-19, monitor 15min cron, patch location, verification that monitor now passes after date bump + code change). Always replicate the date update in new allocator / hybrid / early-return branches.

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

**12-Month Comparative Isolation Backtest of Trading Logic Versions (Phase 5 vs Phase 6 runner/rebalancer) — 2026-06-15 addition to baseline audits**
- When assessing whether changes to trading decision methods/parameters improved performance, include a dedicated Phase-0-style isolation backtest over extended real historical data (12 months recommended) as a hard requirement (user directive).
- Parameterize the concrete logic: rebalance frequency (1d vs 7d), sentiment thresholds (existing vs new-pair), RSI gates, allocation base (inverse_vol + tilt vs signal-weighted), trigger (schedule vs hybrid delta vs strict signal AND).
- Use a standalone isolation script (see `code-isolation-testing`) that exercises the *actual production functions* (`deploy_capital`, `rebalance_plan`, allocation_engine, or Phase 5 equivalents) with the project's real historical OHLCV loader.
- Report side-by-side metrics (return, sharpe, max DD, trades, rebalance count, utilization, entry frequency) + net deltas + qualitative diagnosis (e.g. "Phase 6 exercised logic 7x more but reserve gates still produced 0 net entries").
- Always append results + assessment to `docs/MASTER_TASK_TRACKING.md` (authoritative durable record).
- Example artifacts from this session: `phase6/tests/test_isolation_phase5_vs_phase6_12m_backtest.py`, `data/state/phase5_vs_phase6_12m_logic_comparison.json`, and the dedicated reference `references/phase5-vs-phase6-12m-trading-logic-comparison-backtest-2026-06-15.md`.
- This directly quantifies the cost of divergence (runner owns real allocation/execution; signals/scanner are shadow-only; rebalancer is narrow trigger) and provides before-numbers for the isolated components refactor (ARCH-0).
- See the new support file for full parameters, results (all variants 0% return / 0 trades; Phase6 daily = 365 rebalances), assessment, and repeatable steps. Combine with the runner-vs-hybrid audit technique above.

**Catch-the-Wave Rotation Strategy Validation, Churn Reduction Experiments & Architecture Integration (2026-06-15)**
- When the user clarifies or directs "use cash as a trading exit strategy with opportunistic re-entry in order to catch-the-wave. If the exit can immediately be moved into another trading pair that is actively climbing... minimize the number of rotations and fees... Plan on utilizing this method as part of the ARCHITECTURE_ISOLATED_COMPONENTS.md refactor project rather than the current methods":
  - Implement the rotation as: exit weak (e.g. RSI no longer oversold + sentiment neutral/negative or hard stop-loss) → free capital → immediately redeploy opportunistically to strongest current signals in basket (cash only temporary parking, never sink). Keep exposure ~100% when opportunities exist.
  - Run full-period backtest (12mo recommended) with real historical OHLCV + proxy for alignment (note real daily sentiment series often unavailable for old windows). Test variants for ROI, exposure, rotations, hard stops, fees (model 0.05-0.1% roundtrip).
  - Explicit churn reduction experiments: vary freq (daily/3d/weekly), min_move/min_conviction thresholds, continuous score-tilt vs binary, use of deploy_capital/rebalance_plan/inv-vol base, conviction guards. Document tradeoffs (frequent adjustments often needed for edge in proxy signals; low-churn variants frequently revert to 0% or -34% baselines).
  - Always create a dedicated isolation test script (`phase6/tests/test_isolation_catch_wave_rotation.py` or equivalent) that is standalone, exercises the exact logic with real data (historical for window + live `sentiment_scorer` for current decisions), asserts high exposure + qualitative outperformance vs baselines (e.g. > -20% ROI vs -34% BH), and saves output to `data/state/rotation_isolation_test_output.json`.
  - Update `docs/phase6/ARCHITECTURE_ISOLATED_COMPONENTS.md` with a dedicated section describing it as a pluggable strategy inside the Allocator layer: `rotation_strategy(current_positions, proposals, freed_capital, config) -> TradePlan`. Detail reuse of deploy_capital (redeploys), rebalance_plan (min_move), inv-vol, Evaluation proposals (real sentiment_scorer), stop-loss feeding the same redeploy. Note churn params as tunable and that this replaces/augments current runner/rebalancer/deploy_capital paths.
  - Append dated evidence + sub-tasks (e.g. ARCH-ROT series) to `docs/MASTER_TASK_TRACKING.md` (single source), including JSON result files, isolation test name, real-data note, and explicit statement that this becomes the primary trading logic in the refactor.
  - Current real sentiment diagnostic: Load via `sentiment_scorer` + last-bar proxy RSI; report HOLD/ROTATE_IN/ROTATE_OUT per pair under the thresholds.
- Standing outcome from 2026-06-15 (full 12mo downtrend, ~35% basket decline): Moderate daily rotation delivered **+8.89%** (100% exposure, 454 rotations) vs 0% cash-sink and ~-34% for BH/inv-vol/prior conservative logic. Churn reduction attempts largely lost the edge. Real sentiment currently low-positive (SOL highest); mostly HOLD.
**Pitfalls**: Assuming low-churn variants will preserve edge without better signals/scoring; forgetting to update ARCH/MASTER when user explicitly says "plan on utilizing in the refactor rather than current methods"; using different MTM harness than proven archived backtests.

This class now treats rotation as the target "catch-the-wave" Allocator strategy for signal-driven capital movement in Phase 6 isolated components.

**Rebalance Strategy Comparison, Diagnostic Isolation, Parameter Sweep & Old-Style Persistence (2026-06-15 continuation)**

When the user questions rebalancing P&L impact ("rebalancing may actually be costing a substantial loss" vs prior +140% gains memory) or asks to evaluate "old-style" vs current and whether to persist/adjust/wire it:

- Create dedicated comparison isolation test exercising actual production modules (`deploy_capital`, RotationStrategy via allocator, runner rebalance path) on the project's real full-period historical data.
- Include regime labeling (BTC quarterly returns) and absolute vs relative metrics.
- Follow with parameter sweep on the variant that shows relative enhancement (even if absolute losses in bear regime).
- Decision: Wire/persist the one with isolated evidence of improvement (old permissive `deploy_capital` style beat hold by 6-24 pp in the data; aggressive exit_weak Rotation did not).
- Mandatory full-chain validation: Update and run `test_full_paper_trade_chain.py` with the chosen style; confirm explicit path log + dashboard cache written by that code in the same cycle.
- Wiring: Config (`use_new_allocator: false`, `rebalance_style: "permissive_deploy"`, tuned `rebalance_cap_usd`), runner explicit "[OLD-STYLE WIRED]" log.
- Live: Launch, explicit verification (ps, logs showing style/config, recent dashboard cache with positions).
- Always append tables, root cause (active liquidation vs permissive new-capital deployment), evidence files, and "Live confirmed" to MASTER (single durable record).

See new support file `references/rebalance-strategy-comparison-and-oldstyle-persistence-2026-06-15.md` for the exact technique, results, pitfalls, standing rules, and artifacts from the 2026-06-15 diagnostic + wiring + live sequence.

Combine with `code-isolation-testing` (the test scripts) and `high-agency-execution` (direct chain on "Go ahead and wire... Validate. Go live").

This extends the catch-the-wave / paper-to-live patterns in this skill.

**RSI + Sentiment + Rebalance Frequency Parameter Sweeps for Positive ROI (Full-Period Down Markets) — 2026-06-15 extension**
- When the request is to "find a combination of RSI, Sentiment, and frequency that produces positive ROI" over a full multi-month window:
  - First reproduce full-period baselines on the *exact* data: buy-and-hold equal basket + pure inverse-vol (using the identical harness that produced +9% sub-periods in archived scripts).
  - Build a self-contained sweep script that injects the signal logic (or real `deploy_capital`) inside the proven archived-style daily weighted MTM harness (not custom holdings math).
  - Grid reasonable ranges (e.g. rsi_buy 20-35, sent_buy 0.0-0.5, sell thresholds, freq 1/3/7/14d). Include both simple tilt and real deploy_capital variants.
  - Capture and report *effective exposure / cash fraction* (many "best" results come from de-risk rules parking capital in cash during bear moves, not from clever signals).
  - Save the complete grid + top-N to `data/state/*_sweep_*.json`; surface raw top combos + why they "won" (trades=0 + cash ramp vs. active sizing).
  - Always compare to pure cash (0%) as an explicit baseline.
- **Session outcome (full 12mo 2025-04-20→2026-04-20 data, ~35% basket decline)**: 0 combos produced positive ROI. Best loss reduction was -7.16% (vs. -34% BH/inv-vol) via very permissive thresholds (RSI_buy=20, sent_buy=0.0, daily) that triggered de-risk to high cash (0 trades in sim). Pure cash (0%) beat all active variants. Deploy_capital versions were dragged lower by reserve scaling.
- See `references/rsi-sentiment-frequency-parameter-sweep-full-period-2026-06-15.md` for the exact grid, top-10, script pattern, full baselines, and standing rules.
- **Pitfalls**:
  - Treating sub-period positives (+9.4% on last 120d) as evidence the signals "work" for the full window.
  - Reporting only ROI without cash/exposure or baseline comparison.
  - Using a different MTM harness than the one that produced the archived positives (hides the market move).
  - Assuming active trading is required; defensive cash allocation is often superior in down regimes.
- Standing rule: Append every such sweep (grid + analysis + MASTER update) and reference the support file. Combine with `code-isolation-testing` (the sweep script itself must be a verifiable standalone artifact).

## Related Patterns
- See `systemd-service-management` for production persistence.
- See `hermes-dashboard-deployment` for dual-mode Paper/Live deployment.
- See `paper-trading` for the core PaperTrader implementation.
- See `coinbase-advanced-trade` and `coinbase-live-deployment` for exchange integration.

## Production Harness Wiring (Phase 6 Style) — Real Data Only
**Core rule**: All production harnesses must refuse to operate without live exchange data and live sentiment. Never fall back to hardcoded values or simulation in the main path.
**Signal Pipeline Reliability (RSI + Sentiment Freshness)**

When the user reports issues with fresh RSI or Sentiment signals (critical for downstream signals, rebalancing, allocation):

### Runner Loop Frequency vs. Primary Signal Refresh Rate — Freshness Guard + Trade Buffer (2026-06-15)

**User correction on sequencing (direct)**: The runner should not perform full decision work (evaluate_universe + Allocator) on every 60s tick when the primary generators (RSI 15m decoupled refresher writing rsi_cache.json; sentiment 30m cron + refresh_sentiment.py) have not produced new data. "the sequence should be controlled such that the runner only runs *after* a primary signal update."

**Implementation (now standing pattern)**:
- `_get_latest_signal_mtime()`: max(os.path.getmtime) over canonical caches (sentiment_cache.json, data/state/rsi_cache.json, ~/.trading-bot/sentiment_cache.json, reddit cache).
- `_should_run_full_evaluation()`: guard that returns true (and updates internal last_mtime) only on newer mtime.
- In `_run_cycle` (60s heartbeat): ARCH-4 proposal block is now wrapped — full `evaluate_universe` + `_last_proposals` only on fresh signals. Light duties (rebalance check, dashboard, monitors) continue every tick. Debug logs for visibility.
- **Daily rebalance exception**: The ARCH-4 branch inside `_perform_daily_rebalance` **forces** a fresh evaluate_universe (this is the authoritative allocation moment).
- **Trade buffer on rebalance** (user requirement to avoid churning newly traded pairs):
  - Read `trade_buffer_hours` (default 24) from `global_settings`.
  - Use `self.trade_ledger.get_recent_trades(hours=buffer_hours)` (existing ledger, already used for stops/bought_recently).
  - Post-allocator: `plan.actions = [a for a in plan.actions if a.get("pair") not in recent_pairs]`.
  - Log suppression count and pairs.
- Config keys: `trade_buffer_hours`, `signal_freshness_enforced`.
- The guard is lightweight (mtime only); rebalance always gets latest data but is protected from immediate reversal of just-entered positions.

**Integration**:
- Combines with existing "Paper Test Gate + Immediate Live Deployment Prep Sequence".
- Must be verified via `code-isolation-testing` (the `test_full_paper_trade_chain.py` that exercises forced rebalance + arch4 + dashboard feed).
- High-agency chaining: after "Run the paper test now and validate. After pass, proceed to live deployment", the implementation + re-validation + MASTER update happened without mid-stream asks.
- Explicit `crontab -l` verification (for no overlapping trading crons) remains mandatory in live prep.

**Pitfalls**:
- Guard accidentally starving rebalance (fixed by force-fresh).
- Trade buffer only in legacy path (new ARCH-4 rebalance branch must replicate the protection using the same TradeLedger).
- Forgetting to surface the config knobs.
- Over-applying buffer to non-rebalance cycles (guard is for evaluation cost; buffer is rebalance-specific churn protection).

See `references/runner-signal-freshness-guard-and-trade-buffer-2026-06-15.md` for the exact user quote, code locations (_run_cycle ARCH-4 block, rebalance ARCH-4 block), config diff, test run output, and rationale.

This is the canonical solution for "runner frequency should track signal generators + protect recent trades on daily rebalance" in Phase 6 trading bot operations. Always combine with `code-isolation-testing` and `high-agency-execution`.

**Standing rule**: When user gives sequencing feedback on data producers vs. decision consumers, implement mtime-based guard in the hot loop + force + buffer on the rebalance execution path. Document in this skill + MASTER + reference file.

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

**Social Sentiment Keyword Management (see crypto-data-acquisition skill)**

All keyword selection, relevance testing, lexicon evolution, and map maintenance for X/Reddit sentiment acquisition is now governed by the class-level patterns in the `crypto-data-acquisition` skill:

- Central `config/sentiment_keywords.json` as single source of truth.
- `scripts/optimize_sentiment_keywords.py` as the defined generator (with `--check-new-pairs` and sample review emphasis).
- `phase6/core/sentiment_keywords.py` as the canonical pull interface (`get_x_keyword`, `get_reddit_keywords`, `check_for_new_pairs`).
- Fetchers and scorers consume via the loader (no local hard-coded maps).
- New pairs detection + monthly refresh cadence.
- Ticker-primary rule for token trading signals (with explicit XRP note vs. "ripple").

See `crypto-data-acquisition` SKILL.md (sections on Keyword Optimization Tool and Centralized Sentiment Keyword Configuration, Generation & Consumption Lifecycle) + its `references/central-sentiment-keyword-management-2026-06-16.md` for the full architecture, process, pitfalls, and standing rules.

This keeps the trading-bot-operations skill focused on pipeline integration (how keywords feed scorer/runner/rebalancer) while the data-acquisition skill owns the keyword lifecycle. Always cross-reference when touching sentiment keywords.

**Dynamic Basket + Conditional Sources + Keyword Centralization (2026-06-16 closure)**

The session completed the consistent standard for the full sentiment data flow by:
- Centralizing keyword selection (see above).
- Enforcing dynamic basket load from trading_config in *all* production paths (runner, allocator, hybrid, scanner, fetchers, refresher, scorer).
- Confirming canonical scorer usage everywhere.
- Adding the dedicated coverage/ readiness isolation tests as standing gates.
- Explicit system verification (crontab, hermes cron, ps, fresh python -c, force flag + live log) before declaring "consistent standard achieved".

This is now the baseline expectation for any future basket expansion or signal pipeline change in Phase 6.

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

## Paper Test Gate + Immediate Live Deployment Prep Sequence (2026-06-15)

**Trigger**: User gives explicit directive of the form "Run the [paper/isolation] test now and validate. After pass, proceed to live deployment." or "Proceed to live" after a paper validation step.

**Core Pattern (high-agency chaining + code-isolation-testing gate)**:
- Immediately execute the designated paper/isolation test script (e.g. `phase6/tests/test_full_paper_trade_chain.py`) using the exact command with `PYTHONPATH=.`.
- Capture and inspect raw output for the critical signals:
  - New code path taken (e.g. "[ARCH-4] Using new Allocator + RotationStrategy path").
  - Real data used (proposals with real sentiment scores, RSI).
  - TradePlan produced with target strategy (rotation_catch_wave), exposure, actions.
  - Shadow execution (paper mode: no real orders).
  - Dashboard cache written in the *same cycle* and containing `arch4` section fed by the new code (use_new_allocator, last_strategy, last_exposure, proposals_summary).
- Re-run the test after any supporting edits (e.g. after wiring `_execute_trade_plan` or enhancing dashboard `_write_dashboard_cache`) to refresh evidence and cache.
- On PASS (exit 0 + explicit "FULL PAPER TRADE CHAIN TEST PASSED" + arch4 data present):
  - **No mid-stream permission requests**. Immediately chain to live prep.
  - Update the trading config (`config/trading_config_phase6.json`): set `"use_new_allocator": true` under global_settings; add a `_live_deployment` marker object recording paper_test_passed date, strategy, and notes.
  - Create (or update) a dedicated executable launcher `run_live.sh` (or equivalent) that:
    - Prints clear warnings and the paper-pass date.
    - Performs explicit system-level verification: `crontab -l | grep -E "(phase6|rebalance|trading)"` (per user standing rule — no overlapping trading crons allowed).
    - Invokes the runner with the safety flags: `--mode live --confirm-live`.
    - Documents monitoring steps (logs, dashboard cache for arch4 section).
  - Run a pre-live validation (inline Python or small script):
    - Assert config flag is true.
    - Load Phase6Runner (shadow) and confirm `use_new_allocator`.
    - Check recent dashboard cache has arch4 data from new code.
    - Confirm paper evidence file.
  - Append a detailed dated entry to `docs/MASTER_TASK_TRACKING.md` (single authoritative durable record) with:
    - Excerpts of the paper test run (key log lines + arch4 cache values).
    - Config change details and `_live_deployment` marker.
    - `run_live.sh` purpose and crontab verification output.
    - Pre-live validation results.
    - Exact next command for user ("bash run_live.sh").
  - Final cross-check: re-inspect cache, crontab, and evidence.

**Mandatory Artifacts (this class)**:
- The isolation/paper test (`test_full_paper_trade_chain.py` or equivalent) as the gate.
- `run_live.sh` (baked-in crontab check + safety).
- Config `_live_deployment` marker.
- MASTER entry with real tool output.
- Explicit `crontab -l` in the session (never skip).

**User Standing Rules Embedded**:
- After "after pass, proceed to live", full autonomous chain (test → validate → config → launcher → verification including crontab → MASTER) with no status prompts.
- Real data only; dashboard must be fed by the newly deployed code path.
- Single MASTER as primary record (Kanban secondary).
- Code Isolation Testing as the non-negotiable gate before any live arming.
- Explicit system verification (crontab -l, ps, etc.) before live.

**Pitfalls**:
- Asking "should I now update the config?" after the test passes — violates the chaining rule.
- Skipping the crontab check or pre-live validation.
- Forgetting to re-run the paper test after supporting changes (dashboard, executor) to prove the full chain still works with new code.
- Leaving the config without the `_live_deployment` marker for auditability.

See the support file `references/paper-to-live-deployment-sequence-2026-06-15.md` for the exact transcript, commands, raw test output excerpts, config diff, run_live.sh content, crontab output, pre-live validation, and MASTER entry from this session.

Combine with `high-agency-execution` (for the "proceed immediately" rule) and `code-isolation-testing` (the test script is the primary verification artifact). This sequence is now the canonical paper-to-live arming pattern for Phase 6 trading bot operations.

## Auditing Decision Logic Ownership (Runner vs. HybridRebalancer and Similar Modules)

When the task is to determine whether the runner (orchestrator) and the rebalancer (or scanner, signal generator, etc.) "use the same trading logic" for actual trade decisions:

The runner owns the complete decision + execution path (see `_run_cycle`, `_perform_daily_rebalance` / fresh start, `deploy_capital(...)` + `rebalance_plan(...)` from allocation_engine, order_executor + StopLossCoordinator). The HybridRebalancer (rebalancing/hybrid_rebalancer.py) provides *only* a boolean trigger via `evaluate()` (sentiment deltas + hard thresholds e.g. 0.15 + volatility/drawdown + rule-based AI filter + interval guard). Its `generate_rebalance_plan()` is a minimal stub and is never invoked by the runner (confirmed via call-site tracing). 

Integration point: `rebalance_needed = self._should_rebalance(now) or self.hybrid_rebalancer.evaluate(...)`; if true the runner executes its own full allocation/plan/execute body (with CR-03 context). 

Data divergence is common: runner uses canonical `sentiment_scorer.load_sentiment_scores(universe=...)` (dynamic basket, conditional sources); rebalancer duplicates its own `_load_sentiment` (direct cache parse, different default path, neutral-0 fallback). Signals (SignalGenerator) and opportunity proposals (scanner) are computed for logging/proposals only — never turned into trades.

**Repeatable class-level audit technique** (emerged from this session's systematic investigation):
1. `search_files` (targeted patterns for rebalancer|HybridRebalancer|deploy_capital|rebalance_plan + files_only first to map ownership).
2. Strategic `read_file` (offset/limit) on orchestrator entrypoints (`_run_cycle`, `_perform_daily_rebalance` ~922, `_evaluate_hybrid_rebalance` ~772) and the module's evaluate/generate methods.
3. Explicit searches for *call sites* of the real allocation functions vs. the module's entrypoints.
4. Side-by-side comparison of data loaders and state persistence.
5. Cross-reference project docs/reviews/FABLE5_*/handoffs/MASTER_TASK_TRACKING.md for historical intent vs. implemented reality.
6. Verify with code-isolation-testing (real data wrappers exercising the decision paths) or forced cycle + log inspection.
7. Capture the ownership fact, pitfalls, and repeatable steps here in SKILL.md + a dedicated references/ file.

**Pitfalls specific to this codebase/class**:
- A module/directory named "rebalancer" does not mean it owns allocation, sizing, pair selection, or execution (it can be a trigger/scheduler only).
- Duplicated sentiment/RSI loading creates inconsistent baselines, freshness handling, and fabrication risks (recurring theme in reviews).
- Computed "decisions" (signals, proposals) that never reach the execution layer.
- In-memory state in auxiliary modules vs. the durable persistence the runner/monitor require.
- Assuming all rebalance-related code is equivalent; always trace the hot path from cycle to executed trade.

See `references/runner-vs-hybrid-rebalancer-decision-logic-audit-2026-06-15.md` (full 2026-06-15 session findings, key excerpts, file paths, evidence from searches/reads, and the exact audit steps used). Combine with `code-isolation-testing` and `systematic-debugging` for any such work.

This is now the standing pattern for questions about "which component actually decides and sizes trades?" in Phase 6 bots.

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

## Crypto Analyst Capability Extensions (SL Risk Scorer + Polymarket Overlay) — 2026-06-21
**Class pattern for extending the crypto-analyst (per its persona: learn/evolve + add new skills + honest assessments + strategic output)** when the intelligence report or analyst identifies gaps (e.g. "add a lightweight 'SL risk score' per pair based on historical preview failures" or "Polymarket overlay").

**Core workflow (high-agency, isolation-first)**:
1. Identify via analyst report output (the report itself is the trigger and will be updated to surface the new data).
2. Create dedicated module (e.g. `phase6/core/sl_risk_scorer.py`).
3. Create + run isolation test (`scripts/ops/test_isolation_sl_risk_scorer.py`) with real failure patterns seeded from logs + heuristics (low-price + known pairs). Must PASS with raw output before wiring.
4. Wire into consumer (stop_loss_manager.attach_stop_loss: call get_sl_risk, use recommended_nudge_multiplier for effective_inc, more aggressive nudges/retries on high-risk).
5. Expose in analyst report (per-pair "SL Risk: high (1.0) reasons=[...]" + update Honest Assessment / recs).
6. For external skills (Polymarket): enhance stub (hermes/skills/crypto_analyst/polymarket_overlay.py) to real fetch (gamma-api, parse for crypto/macro keywords → risk_on_bias + events). Use dynamic import (importlib) to avoid hyphen/module issues.
7. Load in report + add section ("=== Polymarket Regime Bias (new skill) ===").
8. Update analyst learnings (data/state/analyst_learnings.json) with new entry documenting thesis/outcome/evolution_note.
9. Append to MASTER_TASK_TRACKING.md + update trading-bot-operations references.
10. Re-run the intelligence report to confirm (show raw "SL Risk" + "Polymarket" sections).

**Implementation details captured**:
- SL scorer: persistent sl_failures.json; log parser for INSUFFICIENT_FUND/precision; risk = failures + low-price boost + known-risk; levels + nudge_mult.
- Integration: risk-aware quantization/nudging in live + shadow paths.
- Polymarket: real requests.get + keyword scan + bias calc + cache; dynamic loader in report.
- Pitfall (emerged): f-string escaping when patching code that injects `risk["level"]` into logs (unmatched [ or backslashes). Always sanitize to .format() or safe prints in patches.
- Parser over-count note: log grep can inflate failures_24h (many "SL attempt" strings); high-risk flagging for known pairs (SOL/XRP/ETH) still correct. Refine parser regex in future.
- Report integration: SL per-pair + Polymarket section now standard in analyst output.

**Verification (always run fresh)**:
- Isolation test exit 0 + output.
- Manager import + get_sl_risk call succeeds.
- Full report run shows new fields/sections.
- State files (sl_failures, learnings) updated.
- Cross-check with `crontab -l`, runner logs for ARCH-4 rebalances.

**Standing rules for this class**:
- New analyst features must produce visible output in the intelligence report (per-pair or dedicated section) + update learnings.
- Always use `code-isolation-testing` for the scorer module.
- Real API for external (Polymarket); dynamic load for project/hermes skills dir.
- Combine with trading-bot-operations rebalance/SL patterns (the scorer directly mitigates the recurring INSUFFICIENT_FUND preview failures in attach paths).
- Update this skill + references + MASTER on each addition.
- Crypto-analyst persona (learn/evolve + add skills) is enforced by making the report the living output vehicle.

**Daily Briefing as Structured Strategic Proposals with Backlog Feed (2026-06-23 extension)**

**Class pattern for the daily intelligence report / briefing** (the crypto-analyst's primary output):
1. After Honest Assessment + Evolution Notes, always generate 2-4 "Strategic Modification Proposals".
2. Each proposal must include: title, description, Benefits (quantified impact where possible), Risks + mitigations, Priority, Effort, Category.
3. Persist to `data/state/analyst_strategic_proposals.json` (accumulated, last N).
4. Automatically append to `docs/MASTER_TASK_TRACKING.md` under "### Analyst Strategic Proposals — <timestamp>" with header "**Status**: Proposed — Awaiting Review/Acceptance" and explicit instruction: "Review, accept/reject, then promote accepted items to active tasks + Kanban via normal change management."
5. The proposals are derived from live data (SL risks, coverage, Polymarket bias, learnings heuristics, runner state).
6. Briefing MUST end with a clean "=== Decision Approval Required ===" section using simple scannable replies (see below).
7. Update the report script, SOUL (mandate the section), SKILL.md references, and MASTER.

**Decision Approval Format (mandatory at bottom of every briefing)**:
```
=== Decision Approval Required ===
1. ANALYST-YYYYMMDD-NNN: Short title
   Benefits: ...
   Risks: ...

Reply with one of:
- proceed with 1
- proceed with 2
- proceed with 1 and 2
- both
- wait
- clarification needed
- none
```

**User preference embedded**: Daily briefings are not just diagnostic — they are the mechanism for analyst-driven evolution that feeds the task system. Use simple language ("proceed with both") for decisions. HTML is the reliable client format for any analogous analyst reports (see marketing-consultancy-team for parallel).

**Proposal Acceptance → Handoff → Isolation Test → Implementation Flow**:
When user replies with explicit acceptance ("Proceed with both", "proceed with 1", etc.):
- Immediately update `analyst_proposed_backlog.json` (status=accepted + handoff path).
- Update MASTER (single authoritative record): change to "**Status**: ACCEPTED...", add handoff link + "**Task ID flow**: ANALYST-... → accepted → active implementation (isolation test first)".
- Create tight handoff file(s) `handoffs/phase6/Handoff_{ID}_....md` (full scope, success criteria, isolation test requirement, real-data/Phase-6 rules, outline).
- Create + run isolation test(s) FIRST (`scripts/ops/test_isolation_*.py` with real holdings/snapshots).
- Implement, surface raw test output + evidence.
- Append progress to MASTER.
- Re-run briefing to confirm.
- **ID convention**: `ANALYST-YYYYMMDD-NNN` generated at proposal time; must appear in JSON, MASTER, handoff filename, code comments, tests. This enforces no duplication and full traceability.

**Pitfalls**:
- Generating proposals but not auto-feeding (violates the "feed into backlog" rule).
- Vague benefits/risks (must be specific and scannable).
- Not updating the report run verification after changes.
- Bare filenames in handoffs (use full `handoffs/phase6/...` paths; see dev-methodology handoff-referencing-pitfall).
- Skipping the isolation test gate or failing to show raw output.
- Complex decision language instead of the simple numbered list + reply options.
- Breaking ID flow or allowing duplicate proposals.
- **Rushing full deployment after "proceed with X" without observation gates or trivial revert path** (user explicit correction 2026-06-24).

**Paced Rollouts + Analyst Self-Follow-up for Deployed Proposals (2026-06-24 addition)**

**User correction (first-class signal)**: "I’m wary of too much change too quickly. We should have a pace and rhythm so we have time to observe changes in production and be prepared to revert should they prove detrimental." + "I’m looking at the crypto analyst to follow up on suggestions that get deployed and validate them again after some period of time."

**Required pattern when user accepts analyst proposals (e.g. "Do both", "proceed with ANALYST-20260623-002")**:
1. Implement the core behavior **behind an explicit runtime gate** (config flag such as `global_settings.apply_analyst_heuristics: true`; default on but trivial to flip to false).
2. In allocator/decision code: load the flag early; if false, skip all new heuristic adjustments / multipliers / penalties (notes, thresholds, tilt weights) while keeping the rest of the path intact.
3. Immediately extend the intelligence report generator to produce a recurring **"=== Analyst Follow-up on Deployed Suggestions ==="** section (runs every briefing). It must:
   - Scan recently accepted/deployed proposals from backlog.
   - Re-validate with current live data (SL risks on tagged pairs, presence of "Learnings adjustments" in logs/notes, coverage, regime bias, etc.).
   - Quote the user's pace principle.
   - Give honest recommendation: observe N cycles (1-3 rebalances or 24-48h), look for specific signals, keep/tweak/revert via the gate.
4. Record in analyst_learnings.json (new entry with "what_failed_or_caution", evolution_note calling for follow-up), backlog (status + deployed ts), and MASTER.
5. Create/update isolation test that proves the *behavioral* effect (risky pair suppressed, notes contain adjustments, flag changes outcome).
6. Re-run the full report after wiring to confirm the follow-up section appears with honest assessment.

**Observation window default**: 1-3 scheduled rebalances (09:00/21:00 PT) or 24-48h minimum before treating the change as "settled" or layering more on the same thread.

**Revert path must be one-line**: edit config + (optionally) restart runner if needed. No code revert, no archive.

**Standing rule**: The crypto analyst (via its briefing) is now the primary validator of its own prior suggestions. Every report after a deployment must include the follow-up until the item is explicitly retired or evolved.

See new support file `references/paced-analyst-proposal-rollouts-and-self-followup-2026-06-24.md` for user quote, exact config/allocator/report changes, sample follow-up output from live run, isolation test excerpt, and MASTER/learnings updates.

Combine with `code-isolation-testing` (the behavioral test is mandatory) and `dev-methodology` (safe incremental + high-agency but now with explicit pacing brakes). Update this subsection + reference on every future paced analyst proposal.

Combine with `dev-methodology` (high-agency chaining, MASTER as primary, handoff patterns) and `code-isolation-testing` (the test scripts are non-negotiable gates). 

This makes the analyst a first-class source of backlog items with traceable execution.

See `references/analyst-sl-risk-scorer-polymarket-2026-06-21.md` for session transcript, raw report excerpts, code snippets, f-string fix pattern, and verification outputs.

Combine with `code-isolation-testing` (test as gate) and `polymarket` (research skill for deeper queries if needed).

**Pitfalls**:
- Assuming date/state or risk data will auto-persist after rebalance/attach (explicit set + save required in new paths; monitor only reads the json date).
- Parser noise in failure counts (still useful for high-risk tagging).
- Hyphen in skill dir names (crypto-analyst) breaks direct import — use importlib + file path.
- Not re-running the full analyst report after wiring to confirm the "examination" now includes the new data.

## Force Rebalance via Flag + Immediate Confirmation + Full-Basket RSI/Sentiment Coverage Audit + Decoupled Refresher Fix + Platform Data Flow Documentation (2026-06-16)

**Trigger**: User gives explicit "Go ahead and touch the force_rebalance and let's get an immediate confirmation. Also verify that we are getting both RSI and Sentiment values for all the trading pairs in the current trading basket as the twice daily status is not showing full coverage for all pairs."

**Standing patterns for this class**:
- **Force rebalance confirmation**: Create `data/state/force_rebalance.flag` (touch or echo). Runner _should_rebalance detects (logs "[FORCE] Manual rebalance triggered via flag file", unlinks), forces rebalance_needed=True, runs full _perform_daily_rebalance body (deploy_capital etc.), updates phase6_runner_state.json last_rebalance_date=today() + persist. Verify: tail phase6_runner_error.log for the FORCE line + rebalance body completed + state.json now has today's date + flag gone on ls.
- **Full-basket signals coverage audit**: Always create/run dedicated standalone isolation test (e.g. scripts/phase6/test_full_basket_rsi_sentiment_coverage.py) using real sources only:
  - Basket from trading_config_phase6.json (global_settings.pairs 11 or opportunity_pool 12).
  - Real caches (rsi_cache.json, x_sentiment_cache.json, canonical sentiment_cache.json).
  - DB queries (rsi_values, sentiment_scores for posts/source).
  - Scorer functions (load_x_sentiment_details, load_sentiment_scores with dynamic universe param, load_latest_sentiment_for_basket).
  - Per-pair report: RSI (value + src/fresh/candles or db ts [stale?]), Sentiment (X score/posts/conf + Reddit only if real posts>0), effective score, status (FULL / RSI-ONLY / SENT-ONLY / MISSING).
  - Summary counts + gaps doc (e.g. "refresher was 6-pair mock", low-volume damping correct per design, scorer now logs "11 pairs" on full call).
  - Run the test; surface raw output + evidence.
- **Decoupled refresher fix for full real coverage**: When audit shows incomplete (mock 6-pair refresher, stale DB), rewrite scripts/refresh_rsi_prices.py (or equivalent) to:
  - Load full basket from config at runtime.
  - Use PriceHistoryManager on runner's data/state/price_history.json (upstream live data from runner cycles; 100-200+ points for all 11).
  - Compute real RSI via calculate_rsi (match runner's Wilder's 14-period).
  - Write complete rsi_cache.json (all pairs, fresh ts, source="15m_candles_from_history", candle_count, fresh=True).
  - Persist to DB rsi_values (current ts, pair, value, source='refresh_15m').
  - Log per-pair details + "synced for 11 pairs" + "SUCCESS: Full basket RSI coverage achieved (real data from runner price history)".
  - Run manually + via hermes rsi-15m-refresher cron. Re-run coverage test post-fix.
- **Platform dependency & data flow documentation**: For any change with cross-component impact (refresher, basket expansion, scorer, DB facts, price history): create/update a dedicated doc (e.g. docs/RSI_SENTIMENT_DATA_FLOW_DEPENDENCIES.md) with mermaid/text flow diagram (upstream config/price feeds/runner history → refresher/scorer → signals/rebalancer/reports/dashboards), component matrix (upstream/downstream per piece, basket scope, change impact), data stores, explicit guidelines ("basket change requires update to refresher load + scorer + tests + this doc + MASTER + re-run coverage test"), pitfalls. Reference in SKILL.md + MASTER. Enforce for dep-aware changes.

**Verification (mandatory, real output)**:
- Flag touch + log/state/flag-gone + rebalance body evidence.
- Refresher run + rsi_cache (all 11 fresh) + DB query (or note lock) + coverage test re-run (11/11 RSI, 10/11 real Sent).
- Scorer logs "11 pairs" on full basket.
- Explicit crontab -l + hermes cron list (rsi-15m-refresher + sentiment-30m), ps for runner, state reads.
- Append full (logs, test stdout, before/after caches/DB, doc paths) to docs/MASTER_TASK_TRACKING.md (single primary durable record).

**User preferences embedded**:
- Real data only (no fakes/mocks in production refresher paths; skip insufficient history is correct).
- Code Isolation Testing as non-negotiable gate for output-producing changes (refresher, coverage audit, force confirmation).
- docs/MASTER_TASK_TRACKING.md as single authoritative durable record (Kanban secondary/unreliable).
- Explicit system verification (crontab -l in addition to hermes cron, ps, state, logs) always.
- High-agency chaining: on "Go ahead and [touch force + verify full coverage]", own the full immediate sequence (flag, run/audit/fix, re-verify, MASTER + doc updates) with no mid-stream permission or status prompts.
- Dep-aware changes: create data flow doc + explicitly trace upstream (runner price_history) / downstream (scorer, rebalancer, signals, reports) for any pipeline extension.
- Dual-write where producers touch facts (caches for no-fab/scorers + DB for shared queries).

**Pitfalls**:
- Assuming 15m refresher + DB give full fresh coverage without explicit audit (recurring; was 6-pair mock + 2026-06-14 stale data).
- Runner "6 pairs" logs for sentiment (coverage test with config basket confirms 11; was subset or legacy).
- DB lock on concurrent refresher/runner (cache update succeeds; runner also writes).
- Omitting data flow doc or MASTER update on pipeline changes (loses visibility for ramifications).

**Artifacts**:
- Coverage isolation test: scripts/phase6/test_full_basket_rsi_sentiment_coverage.py (standalone real-data; raw run output with per-pair + summary + gaps section).
- Fixed refresher: scripts/refresh_rsi_prices.py (real full-basket version using price_history).
- Data flow doc: docs/RSI_SENTIMENT_DATA_FLOW_DEPENDENCIES.md.
- Force evidence in phase6_runner_error.log + state.json + flag.
- MASTER append with complete task block.

See `references/full-basket-rsi-sentiment-coverage-isolation-tests-2026-06-16.md` (condensed commands, raw outputs, dynamic enforcement steps, pitfalls, standing rules) and the prior `references/full-basket-rsi-sentiment-coverage-audit-force-rebalance-refresher-fix-and-data-flow-doc-2026-06-16.md`. Combine with `code-isolation-testing` (test as gate), `high-agency-execution` (chaining), and prior rebalance-watchdog patterns. Update this subsection + references + MASTER on future audits or universe enforcements. Always dual-write and run the readiness/coverage tests yourself.

**Hybrid canonical + full consistency closure (final step of session)**: hybrid_rebalancer.py brought into standard (legacy _load_sentiment replaced with load_sentiment_scores delegation; full 11 in example). All core production (runner, allocator, hybrid, scanner) now enforce dynamic full basket from config + canonical scorer. Fresh hybrid smoke confirmed "11 pairs" + full deltas. Runner process logs lagged (pre-restart); source + fresh runs (tests/hybrid) are the verification. MASTER and data flow doc updated with "all outlined remaining closed; consistent standard achieved".

**Pitfall (2026-06-16 session closure)**: Source changes to runner/hybrid/fetchers do not affect the already-running Python process. Logs will continue showing old "6 pairs" until explicit kill + restart via canonical run_phase6_live.sh. Verification of "consistent standard" must use fresh python -c (len(FIXED_UNIVERSE)==11), hybrid smoke (confirms "Sentiment loaded for dynamic basket (11 pairs)"), and isolation tests (readiness/coverage). Only after source verification, perform restart + force flag for live log confirmation during rebalance. Always include explicit `crontab -l`, hermes cron list, and new PID check.

**Consistent standard closure checklist** (apply when user says "Fix all the remaining elements..." or "Let's get everything to a consistent standard" or "Proceed." after outlining gaps):
1. Grep core/ and key scripts/ (exclude intentional small-basket isolation tests/backtests) for remaining FIXED_UNIVERSE / small lists / legacy _load_sentiment / hardcoded 6-pair keywords.
2. Patch all stragglers to config-driven full basket + canonical paths (e.g. hybrid _load_sentiment delegation, reddit fetcher load_full_trading_basket + keyword_map for all 11).
3. Fresh verification (no reliance on running process): 
   - python -c "from phase6.core.phase6_runner import Phase6Runner; r=...; assert len(r.FIXED_UNIVERSE)==11"
   - python -m phase6.core.rebalancing.hybrid_rebalancer (confirm "11 pairs" log + full deltas)
   - Re-run scripts/phase6/test_full_basket_*.py and phase6/scripts/generate_trading_intelligence_report.py (surface raw "11 basket", "dynamic full", coverage counts).
4. If live process: kill old PID, clear pycache if needed, restart with phase6/scripts/run_phase6_live.sh (background), confirm new PID via ps.
5. Touch force_rebalance.flag; tail phase6_runner_error.log for "[FORCE]", "Sentiment loaded for dynamic basket (11 pairs)", expanded target_weights in Daily Rebalance, body completed.
6. Re-run tests/intel; append complete evidence block (logs, test stdout, before/after, new PID) to docs/MASTER_TASK_TRACKING.md (primary) + data flow doc.
7. System verifs: crontab -l (no overlaps), hermes cron list, ps for single runner.
This sequence (patch → fresh verify → restart if needed → force + live confirm → MASTER/doc) was the exact chain that closed the user's request for consistent standard across the RSI/sentiment data flow.

**Standing rule**: "Consistent standard" means *all production paths* (runner, allocator, hybrid_rebalancer, opportunity_scanner, fetchers, refresher, scorer consumers) load dynamic basket from trading_config_phase6.json at runtime and use canonical load_sentiment_scores / load_latest... . Tests/backtests may retain small local lists for focus. Always end such work with the checklist above + real output in MASTER.

Combine with code-isolation-testing (the tests as gates), high-agency-execution (full chain on "Proceed." with no mid-stream asks), and systematic-debugging (root cause the hardcodes before patching).

## Entry Optimization via Predictive Filter Extensions (RSI + Sentiment Continuation Cases)
**Trigger (2026-06-17 session)**: User supplies concrete RSI/sentiment values and asks "is there a way to optimize the entry using a predictive filter or other method we have not identified? ... rank the methods you come up with by probability."

Current opportunity scanner (IDEALOOP-002) and SignalGenerator exhibit strong oversold/mean-reversion bias that misses "strong RSI (50-67) + strong Sentiment" cases.

**Captured Pattern for this class**:
- Reproduce exact current scoring (scanner 40% oversold RSI weight + signal +0.4/<30 logic) on the provided snapshot via simulation.
- Identify the gap (scores ~0.23 for high-sent pairs, below proposal/strong thresholds).
- Fork a bullish/continuation scorer (mid-RSI band preference + sent + mom).
- Create and execute dedicated isolation test script comparing baselines vs proposal (table of deltas on exact user data).
- Produce ranked list of methods by estimated probability of success (High/Med based on alignment with real-data, isolation testability, existing rotation validation).
- Embed diagnosis, full ranked table, example code, and validation steps (replay on price_history, shadow AB) directly into the canonical predictive filter document.
- Update MASTER_TASK_TRACKING.md with the artifacts and links.
- Top-ranked: Bullish/Continuation Predictive Scorer Extension to the opportunity scanner (High 75-85%), followed by momentum filter, regime integration, velocity, tiered test entries.

**2026-06-17 Evidence**:
- Isolation test: phase6/tests/test_isolation_bullish_entry_scorer.py (executed; high-sent ADA/LINK/OP jump ~0.30 → 0.89-1.00; most 0.6+; SOL suppressed).
- Full analysis + 7-method ranked table + example bullish scorer function now in docs/Predictive_Filter_Opportunity_Scanner.md (new "Entry Optimization Using Predictive Filters..." section).
- Synergy with inverse avoidance/sell predictive filter noted.
- All using the exact user snapshot; real data, no fabrication.

**Rules for future work**:
- Always diagnose and state the bias (oversold weighting) explicitly when user reports entry problems with non-low RSI.
- Use the exact provided data or live caches in the verification script.
- The isolation test + ranked probabilistic methods + doc update are mandatory artifacts.
- Combine with code-isolation-testing for the test creation/run.
- Update this skill, the predictive doc, and MASTER.

See docs/Predictive_Filter_Opportunity_Scanner.md for the complete ranked table and sim output. This is now the standing approach for entry-side predictive filter work in Phase 6 bots.

**Pitfall**: Defaulting to more oversold tuning when the data shows the need is for continuation/strong-RSI entries; always simulate the fork against the user's numbers first.

## Live SL Order Visibility, Placement Timing & Holdings Reconciliation (2026-06-17 addition)

See dedicated reference `references/live-sl-visibility-placement-timing-reconciliation-2026-06-17.md` for the full session (screenshots of active SLs + holdings, reconciliation to live_state.json + entries, live prices, code traces on attach paths, order_executor gaps, coordinator support for adjustments, "let it ride" bias despite -46% ETH DD, and answers to the 5 diagnostic questions).

**Standing rules extracted**:
- Always cross-check app SL screenshots vs state.json (holdings + entry prices) + live ticker + code (StopLossManager 3% calc, order_executor post-buy attach, LivePortfolioManager holdings-only, coordinator suspend stubs).
- SLs on legacy high-entry positions (e.g. ETH $3200) were frequently manual/retroactive (Jun 5 SL at $1504 vs 3% ~$3104).
- Current executor does **not** call attach_stop_loss after buys.
- Holdings state ≠ active conditional SL order status (hence screenshots required; coordinator _fetch is stubbed).
- Rebalance adjustments possible via suspend_reattach_context.
- Runner does not auto-liquidate large single-position DDs without SL breach or sufficiently low conviction score.

**Combine with**:
- code-isolation-testing (scorer runs on the exact holdings snapshot)
- systematic-debugging (4-phase trace of placement timing vs attach logic)

Update this subsection + the reference file + MASTER when similar live SL/holdings diagnostics recur. Always surface placement dates vs entries.

## Live SL Remediation Playbook (5-Step Sequence) — 2026-06-23 addition

**When to use**: SL coverage missing/stale after rebalance, attach failures, or user requests explicit remediation on current book.

**Canonical sequence** (execute in order, real client only, surface raw output):
1. Fetch current crypto positions + SL positions (`get_holdings_verified()`, `get_enriched_positions()`, `get_open_stop_orders()`, `get_account_balance("USD")`).
2. If reserves low (e.g. < min buffer or breach), liquidate weakest holdings first via `place_market_sell` on smallest-value positions.
3. Close pre-existing/stale SL positions (`get_open_stop_orders()` + `cancel_order` per ID).
4. Open new SL positions on current holdings using `StopLossManager.attach_stop_loss` (real entry from `get_price`, pre-flight poll, risk scorer nudge, 3% default, quantization).
5. Verify (re-fetch holdings + stops + balance; cross with UI if provided; log inspection).

**Evidence from live execution (condensed)**:
- Positions at start: UNI ~45.47 ($131), LINK ~17 ($129), ADA ~2062 ($311), ETH ~0.086 ($142), tiny SOL/XRP. USD ~$21.
- Liquidated weakest (SOL 0.0062 + XRP 0.037) — both succeeded.
- Pre-existing SLs: 0 found (recurring 401 on orders batch).
- New attaches attempted (all failed after pre-flight + 3 retries):
  - Pre-flight logged timeouts ("desired X, got ~0.0") — new logic active.
  - Errors: PREVIEW_REDUCE_ONLY_NOT_ALLOWED_ON_VENUE (UNI/LINK/ADA with reduce_only in body); PREVIEW_INSUFFICIENT_FUND (ETH).
- Final state: Same positions, 0 detectable open SLs. Total ~$713 + $21 USD.

**Root causes documented**:
- `reduce_only: True` (enforced in manager for safety) rejected by Coinbase venue for stop-limits on these products.
- Open orders visibility broken (401s) — use holdings as ground truth.
- Pre-flight (from ANALYST-20260622-001) correctly fires but detects settlement lag.
- Low cash buffer triggers INSUFFICIENT_FUND.

**Standing rules**:
- Always follow the 5 steps exactly; do not skip liquidation when reserves are low.
- Document full error strings + order bodies.
- After this pattern, recommend conditional/remove reduce_only for stop-limit in future patches.
- Re-verify immediately after any SL/client change.
- Combine with `code-isolation-testing` (replay exact holdings + snapshot).
- Append complete evidence block to MASTER + this reference.
- When UI screenshot provided, use vision_analyze for ground-truth opens vs holdings.

See `references/live-sl-remediation-playbook-2026-06-23.md` (full transcript, exact commands, errors, holdings numbers, pre-flight logs, verification commands).

**Pitfalls**:
- Assuming `get_open_stop_orders` will surface legacy SLs from prior screenshots.
- Forcing reduce_only without venue compatibility test.
- Not re-fetching after liquidation or failed attaches.
- Ignoring pre-flight log output (proves the new code path).

Update this section + reference whenever the playbook is exercised or the underlying errors change. Combine with `coinbase-advanced-trade` for API-specific details and `code-isolation-testing` for verification scripts.

## UI Screenshot Reconciliation for Coinbase Holdings & Orders (2026-06-19 pattern)
When direct filesystem access to phase6_live_state.json, runner logs, or enriched_positions fails (timeouts, large home dir scans, or inaccessible state), fall back to user-provided Coinbase Advanced Trade UI screenshots for verification.

**Standard workflow**:
1. Use vision_analyze on the attached screenshot(s) (typically under ~/.hermes/image_cache/) with a precise extraction prompt: "Extract every order/holding exactly. Structure as OPEN ORDERS / holdings with symbol, quantity, prices, status/date, totals."
2. Extract quantities to high precision (e.g. 0.08572777 ETH, 18.637483 XRP, 30.014804 ADA).
3. Cross-reference against bot dashboard screenshot: note "active pairs" filter vs full account (dashboard often shows only trading logic's deployed set; Coinbase shows everything including residuals under stop).
4. Compute implied prices (value / quantity) and buffers to stops.
5. Validate: open stop quantities exactly match current holdings quantities.
6. Reconcile totals (small $5–10 variance normal due to timing + live prices vs cache).
7. Ground with external live market prices for sanity.
8. Document: quantities match / values close / stops live / recovery posture confirmed / dashboard filtering explained.

**Key observations from this class**:
- Dashboard "Active Positions: 2" + recovery mode is often correct for the bot's limited deployment, even when Coinbase shows 3 lines (the third is a protected residual).
- Stop orders remain authoritative for protection status.
- "No recent buys" on dashboard can coexist with recent filled activity if the moves were rebalance/fresh_start and largely reversed.
- Use Coinbase holdings as ground truth for balances/stops; dashboard for strategy signals and mode.

**Pitfalls**:
- Treating dashboard active count as the complete position list.
- Ignoring small value drift without checking timestamps.
- Skipping the implied-price math step.

Always append a dated block to docs/MASTER_TASK_TRACKING.md with the extracted numbers and reconciliation verdict. Combine with code-isolation-testing when a verification script can replay the same numbers from the Coinbase client.

See references/ui-screenshot-holdings-reconciliation-2026-06-19.md for the exact screenshots, extracted tables, implied prices, and cross-checks from this session.

## SL Application Fix + Rebalance Coordination Verification (2026-06-17 follow-up)

**Trigger**: User directive after the diagnostic: fix gaps in SL application (core safety) first, then run rebalancing verification with SL handling.

**Fix Applied**:
- Patched `phase6/core/order_executor.py:execute_buy` (shadow + live paths) to call `attach_stop_loss` immediately after successful buy (using get_price for entry approx + size = usd/entry).
- Updated `execute_rebalance_plan` to benefit (BUYs now attach).
- Result: New buys and rebalance BUY actions now produce proper SL (default 3% from fill).

**Verification Artifact**:
- New class-level test: `phase6/tests/test_sl_application_and_rebalance.py` (exercises real StopLossManager + OrderExecutor + StopLossCoordinator in shadow with exact user holdings + RSI/Sent).
- Test confirms:
  - Post-buy attach fires (sl_attached=True, [SHADOW] logs with correct 3% calc).
  - suspend_reattach_context works (suspends for touched pairs like ETH/OP; re-attaches at new entries).
  - Allocator on current scores: OP strongest (0.438), signals weak XRP / strong OP → rebalance would act while respecting SLs.
- Raw output surfaced; test PASSED.

**Standing Rules**:
- Any change to buy/executor paths requires an isolation test that asserts sl_attached + coordinator re-attach.
- Rebalance verification must use the suspend_reattach_context wrapper and show SL handling.
- Reconcile screenshots + state + live prices + code + scorer output.
- Append to MASTER + this skill's references.
- Combine with code-isolation-testing and high-agency-execution (chain fix then verify without mid-asks).

See new support file `references/live-sl-application-fix-and-rebalance-verification-2026-06-17.md` (full test code summary, output excerpts, rules, pitfalls).

**Pitfall**: Rebalance safety claims without exercising the coordinator + post-fix attach in a runnable test.

Update this skill + code-isolation-testing + MASTER on future SL safety work.

## Safer Sequence for New Allocator Validation + Live Smoke Gate (2026-06-18)
**Trigger**: User supplies RSI/Sent snapshot showing strong values but no good entries under current logic; asks to validate specific opportunities (e.g. ADA/LINK) and "if it checks out, any reason to not go live (not shadow) and run the rebalance script?"

**Standing Pattern (codified this session)**:
1. Clean shadow forcing `use_new_allocator=True` (with user's exact data + holdings) + compare plan to legacy.
2. Use/adapt reusable driver (`scripts/run_shadow_rebalance_cycle.py --mode shadow --new-allocator`).
3. Execute dedicated live smoke isolation test on top-scoring pair (`scripts/live_smoke_test.py --pair ADA-USD --usd-amount 15 --confirm "I accept real small trade + liquidate for validation"`): tiny real buy via executor (tests attach), verify sl_attached + stops, attempt liquidate.
4. Report raw findings, update MASTER + PHASE_6_1_PRODUCTION_DEPLOYMENT_PLAN.md (smoke now mandatory pre-deploy gate), diagnose (e.g. SL issues).
5. Only then consider full live rebalance.

**2026-06-18 Evidence**:
- New allocator: BUY ADA $301.86 + LINK $301.86 (rotation_catch_wave; no full liquidation of current holdings).
- Scanner: ADA 0.488 / LINK 0.485 (top bullish scores).
- Live smoke (ADA $15 @ $0.1653): buy succeeded (order 7214ffb2..., sl_attached=False); SL 3x INSUFFICIENT_FUND; sell also failed; post-balances showed no net position (USD recovered).
- Additional: runner norm fix applied for ARCH-4 current_allocs.
- Driver script generalized with live+confirm support.

**Pitfalls (new/confirmed)**:
- Legacy deploy + scaling can fully exit current basket (even decent-scoring OP).
- Post-buy SL attach fragile in live: INSUFFICIENT_FUND common (settlement timing, stop body, wrapper injecting reduce_only/UNKNOWN_STOP_DIRECTION).
- Live client visibility (balances, get_open_stop_orders) lags or 401s immediately post-trade.
- Smoke may leave no net position (still validates path).
- Always use explicit confirm phrase; compare new vs legacy allocator when legacy resets basket.

**Rules**:
- Run this 4-step sequence before any live rebalance.
- Prefer high-scoring pairs (per scanner) for smoke.
- Always update deployment plan + MASTER.
- Combine with `code-isolation-testing` (smoke script is the artifact) and `high-agency-execution`.
- See `references/safer-shadow-to-live-new-allocator-smoke-sequence-2026-06-18.md` for full condensed transcript, plans, outputs, and standing checklist.

Update this subsection + the reference on future live gates. Combine with the 2026-06-17 SL/rebalance isolation patterns above.

## Manual On-Demand Live Allocator Trigger + Production Verification (2026-06-20)
**Class pattern for controlled verification of `use_new_allocator` (or any allocator/rebalance change) in the running live production environment** (without waiting for cron or full paper gate).

**Trigger command** (exact):
```bash
python3 scripts/run_shadow_rebalance_cycle.py \
  --mode live --new-allocator --rebalance-cap 150 \
  --confirm "I accept real trades and loss risk"
```

The script forces rebalance, sets the flag, injects snapshot data, and directly calls `_perform_daily_rebalance()`.

**Mandatory monitoring after trigger**:
- `ps` for runner PID + recent daemon cycles.
- Tail `phase6_runner_live.log` (grep ARCH-4, "RotationStrategy path", "Emergency Recovery", "TradePlan", "actions", "exposure").
- Inspect `phase6_live_state.json` (flag, strategy, actions/proposals, total/cash/positions).
- Trade ledger + absence of order execution logs.
- Note 0-action outcomes explicitly when in recovery + client data issues.

**Observed in this session**:
- New path taken: `[ARCH-4] Using new Allocator + RotationStrategy path` + recovery mode.
- Plan: `rotation_catch_wave`, 0 actions, 0% exposure.
- No trades.
- Daemon continued same pattern.
- live_state temporarily zeroed by client failures → post-run restore of known-good snapshot while preserving `use_new_allocator: true`.
- Root cause: lingering `coinbase_wrapper_FIXED` import (see coinbase-advanced-trade + exchange_client).

**Standing rules**:
- This script + live mode is the preferred on-demand verification tool for allocator changes in prod.
- Always show the ARCH-4 / recovery log lines even if actions==0 (confirms path).
- Client init failures are expected in degraded state — verify *decision path* independently.
- Always restore live_state hygiene after client breakage.
- Append to MASTER + this reference file.
- Re-trigger after client fixes.
- Combine with `code-isolation-testing` (the run script is the isolation artifact) and existing "Safer Sequence..." / "Paper Test Gate" patterns.

**Pitfall**: Treating "script completed" as sufficient without the monitoring + state check + explicit 0-action diagnosis.

See new support file `references/manual-live-allocator-trigger-and-prod-verification-2026-06-20.md` (command, raw outputs, monitoring checklist, client diagnosis, rules, artifacts).

This extends the live verification sequences in this skill. Always surface the exact log phrases showing the new allocator branch.