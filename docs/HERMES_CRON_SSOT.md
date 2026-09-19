# Hermes cron SSOT (Phase 6 + host)

**Updated:** 2026-09-09  
**Law:** **Do not put Phase 6 / sentiment / X / Apify / runner monitors on Linux `crontab`.**  
User crontab is comment-only. Backup: `~/.hermes/cron/linux-crontab.bak.20260813`.

Verify: `crontab -l` (no executable lines) + `hermes cron list` (default profile only).

## Status / settings authority (2026-08-29)

| Role | SSOT | Who may write |
|------|------|----------------|
| Policy knobs (TP/SL/hard-exit/map) | `config/*.json` | Human / explicit promote only |
| TP runtime book | `data/state/shadow_tp_status.json` | **Only** `phase6/core/shadow_tp.py` runner (`persist=True`) |
| Outcomes | ledger + `shadow_tp_live_exits.jsonl` | Executor |
| Dashboard / crons / `reports/*` | surfaces | **Read** SSOTs → metrics. **Never** write config or runtime SSOT |

**Archived:** `shadow-tp-validation-daily` (`e7fe6faeebe6`, paused). Reporter is forensic-only; cannot `--start-window` or write `shadow_tp_status`.

Full audit: `reports/CRON_ARCHIVE_AND_SSOT_2026-08-29.md`.

## Cutover (2026-08-13)

| Was Linux | Hermes job | Schedule (PT) | Notes |
|-----------|------------|---------------|--------|
| `refresh_sentiment.py` 0 9,21 | `phase6-x-sentiment-live-2x` `e17a43bfbed6` | 09:00 / 21:00 | X live + free fallback |
| `run_adanos_shadow.sh` 35 8,20 | `phase6-adanos-reddit-shadow-2x` `539424468b36` | 08:35 / 20:35 | Adanos Reddit free shadow + multi-corr; **not** live |
| `run_free_sentiment_shadow.sh` 40 */2 | `phase6-free-sentiment-shadow-2h` `655188d1df61` | every 2h @:40 (incl 08:40/20:40) | Free shadow denser samples; **not** live |
| `monitor_phase6_runner.py` */15 | `phase6-runner-monitor-15m` `f14dc4b04e34` | */15 | Watchdog |
| `ops_engineer.py` */30 | `ops-engineer-30m` `3c83e4d2232c` | */30 | Deterministic |
| `backup-kanban-frequent.sh` */15 | `kanban-backup-frequent-15m` `387e688fc854` | */15 | + daily `a93067255b66` @ 03:00 |
| `phase6_rebalance_monitor.sh` */20 | **DROPPED** | — | Dead send flags |
| `/tmp/fable5_reminder.py` Mon 09:00 | **DROPPED** | — | Stale |

## Keep active (default gateway) — classes

### A — Live trading spine
Rebalance 09:05/21:05 · RSI */15 · X 09:00/21:00 · Adanos Reddit shadow **08:35/20:35** · free sentiment **every 2h @:40** (shadow) · runner monitor */15 · reentry SL/TP monitor */10 · dashboard live */5

### B — Ops / hygiene
ops-triage 06:00 TG **only when actionable** (empty stdout on OK) · **pre-ship quality nightly 04:15 TG fail-only** · ops-issue-loop 07/13/19 local · ops-engineer */30 · kanban backup */15 + daily 03:00 · git-daily 04:30 · llm-token rollup 05:05 · master-test pickup/scan TG only when work · analyst-test-strategy Mon 10:00

### C — Operator briefs (read-only surfaces)
daily-dose 08:00 · **analyst-daily-review 10:15 TG (material only)** · analyst-daily-scoreboard 08:30 local · intel **local** 09:00/21:00 (facts still run; TG demoted 2026-09-02 — no HOLD filler) · deep maint 03:00 local · OPT weekly Sun 04:00 · SL exit CF weekly Sun 08:30

### D — Shadow / research still active (own state only — **not** config writers)
| Job | Why still on |
|-----|----------------|
| `phase6-discovery-pipeline-shadow` | Funnel scout on disk only — **deliver=local**, no TG (Brad 2026-08-30) |
| `phase6-discovery-retro-board-daily` | Lookback: gainers × frozen contenders + T-7 forward book (research only) |
| `phase6-basket-pick-metrics-refresh` | Open promote pick still `status=open` |
| `phase6-platform-metrics-spine` `63cc2c821018` | Full pair lifecycle + runner ops board · **07:45 PT daily** · TG short board · measure-only · never auto-promote/eject |
| `phase6-rsi-event-x-tryout-shadow` `36a4ade79e1c` | RSI-wash + stale eng → top-2 would-query/tryout shadow · **07:20/11:20/15:20/19:20 PT** · quiet TG · **no orders / no paid X** · ATTENTION_ONLY |
| `phase6-knife-filter-shadow` `5bd102bfd07e` | Luck ladder R1 knife vs wash arms CF · **07:30/19:30 PT** · TG one-liner · **no orders / no live block** · ATTENTION_ONLY |
| `phase6-promote-graduation-chart` `af423d285b52` | P2 promote funnel SVG + claim bar · **12:40 PT daily** (after pick-metrics) · TG short · dash `/api/promote-graduation` |
| `phase6-regime-arm-switch-metrics` `5036cfdbc289` | P3 flip success join · after switch cron · TG short · dash `/api/regime-arm-metrics` · claim OFF until N |
| `phase6-basket-seat-idle-refresh` | Soft idle flags; observe_only |
| `phase6-basket-swap-cf-shadow` | TG only on dual_agree / preferred-arm new write / hard CF; preferred from decision file (regime switch may flip) →2026-09-28 |
| `phase6-regime-arm-switch` `353a8ca93150` | BTC 7d tape → paper-primary arm (`up/chop→rel_btc_stable`, `down→risk_adj_mom`) · **11:40/23:40 PT** · apply shadow · TG **only on flip** · live swaps forced OFF |
| `phase6-tcs-shadow-would-block` `dd16da710656` | Trade-comparison CF + would-block replay · **12:25 PT daily** · local · own state only · live cooldown OFF |
| `phase6-vol-risk-scalar-shadow` | Keep collecting (not enough data for promote) |
| `bear-ladder-promote-watch` | **Not** done — 1 bear day / 0 episodes (need real bear) |
| free-sentiment **2h** `655188d1df61` | Shadow RSS+funding+F&G denser mid-cycle samples vs X (Brad 2026-09-04 lag thesis); live still X 2× |
| Adanos Reddit **2×** `539424468b36` | True-Reddit free shadow @ **08:35/20:35** pre-X · multi-corr vs RSS/free/X · ~2 calls/run · **not** live wire |

### E — One-shot still scheduled
| Job | When | Note |
|-----|------|------|
| `stoch-30d-reeval` | 2026-09-03 09:00 PT | remove after fire |
| `phase6-rsi-event-x-shadow-observe-close` `17289c281af6` | **2026-09-17 19:35 PT** | R0 extended observe closeout; remove after fire; paid X still OFF |
| `basket-swap-30d-revisit` | 2026-09-28 09:00 PT | preferred arm vs dual_agree re-score |

### F — Paused / ARCHIVED (reactivate with `hermes cron resume <id>` when needed)
| Job | Id | Why paused |
|-----|-----|-----|
| `sentiment-30min-refresh` | `8612a817fe55` | Cost; 2×/day X is SSOT |
| `ARCHIVED shadow-tp-validation-daily` | `e7fe6faeebe6` | TP live; dual-writer retired |
| `ARCHIVED Phase6 Shadow Drift Monitor` | `bf79baababb0` | No active overlay since 2026-07-15 |
| `ARCHIVED bull-reentry-layered-paper-shadow` | `746aa3a9f77c` | Deferred on stoch; after 09-03 reeval if needed |
| `BUST phase6-volume-velocity-shadow` | `da86b4b8e222` | Brad NO-GO 2026-08-29 (seat/buy bust) |
| `ARCHIVED regime-boundary-layer-shadow-2x` | `160eaa8dae79` | Design shipped; indefinite cream paused |
| `ARCHIVED mover-not-in-bag-watchlist-2x` | `71970acbd4dc` | Optics; discovery covers |

## Agent rules

1. New schedules → `cronjob` / `hermes cron` on **default** gateway only.  
2. `no_agent` scripts: `export PATH=$HOME/.local/bin:$PATH`; **never** bare `hermes`.  
3. `hermes send` = stdin + `-t telegram` only. Prefer stdout + `deliver=telegram` for no_agent.  
4. Do **not** re-enable Linux lines “as backup.”  
5. `sentiment-30min-refresh` stays **paused**. Reddit Apify **OFF**.  
6. **Reporting NEVER writes production settings** (`config/*`) or runtime SSOT owned by the runner.  
7. Dead profile crons (crypto-orchestrator / code-reviewer) stay **disabled** — not SSOT.

## Dashboard

Live UI: user systemd `phase6-dashboard-8502.service` → `:8502` (venv). Not Linux cron. Surfaces read SSOTs; do not invent mode.

## phase6-rsi-event-x-probe (Brad GO validate 2026-09-18)
- Schedule: `25 7,11,15,19 * * *` America/Los_Angeles (5m after shadow tick)
- Script: `~/.hermes/scripts/run_rsi_event_x_probe.sh` (PROBE_GO=1)
- Behavior: paid X only if RSI wash + stale eng + budget; no orders; quiet if idle
- Caps: rsi lane ≤2 pair-queries/day; total ≤6; per-pair cooldown 6h
- Companion measure: `run_rebalance_x_candidates.py` (held∪plan X universe; full-book replace still OFF)

## phase6-jev-lab-shadow (Brad GO lab 2026-09-18)
- Schedule: `30 7,11,15,19 * * *` America/Los_Angeles (job_id `172f3773f8b9`)
- Script: `~/.hermes/scripts/run_jev_lab_shadow.sh` → `phase6/scripts/run_jev_lab_shadow_cron.sh`
- Model: OpenRouter `~typesafe/jev-latest` via `POST /api/alpha/decisions`
- Behavior: measure-only decision packets (BTC/ETH default); crumbs + budget; **no orders**
- Cap: lab max 24 calls/day (`data/state/jev_lab_budget.json`); quiet logs under state/
- Delivery: local (no TG spam); isolation `scripts/phase6/test_isolation_jev_lab.py`

## phase6-jev-lab-calibration (L4 measure-only 2026-09-19)
- Manual / after shadow ticks: `python3 scripts/phase6/run_jev_lab_calibration.py`
- Optional quiet cron later at `35 7 * * *` PT once crumbs accumulate
- Artifacts: `data/state/jev_lab_calibration_latest.json` + `reports/JEV_LAB_CALIBRATION_LATEST.md`
- Guardrails: measure-only, honest N (`N_INSUFFICIENT` until n_ok≥20), no orders / no promote
- Isolation: `scripts/phase6/test_isolation_jev_lab_calibration.py`

## phase6-daily-dose-jev-ranker (Brad GO shadow 2026-09-18)
- Schedule: `15 7 * * *` America/Los_Angeles (before `daily-dose-telegram` 08:00)
- Script: `~/.hermes/scripts/run_daily_dose_jev_ranker.sh` → `phase6/scripts/run_daily_dose_jev_ranker_cron.sh`
- Behavior: Jev judges RSS shortlist; compare vs baseline top-N; **shadow only**
- Does **not** overwrite `daily_dose_latest` / publish_ready / live TG body
- Not a trade signal; no allocator / tryout wiring
- Artifacts: `data/state/daily_dose_jev_{latest,compare,preview,crumbs,budget}.*`
- Cap: max ~80 Jev calls/day budget file; default max_judge 16/run
- Isolation: `scripts/phase6/test_isolation_daily_dose_jev_ranker.py`
- Delivery: local (skim compare.md; promote Jev order only after multi-day quality)

## phase6-free-rss-jev-materiality (Brad GO shadow 2026-09-18)
- Schedule: `50 */2 * * *` America/Los_Angeles (after free-sentiment @:40)
- Script: `~/.hermes/scripts/run_free_rss_jev_materiality.sh` → `phase6/scripts/run_free_rss_jev_materiality_cron.sh`
- Behavior: RSS pair-tag + TextBlob → Jev materiality weights → `sentiment_cache_free_jev.json`
- Does **not** write live `sentiment_cache.json`; no floors / aging / X primary change
- Artifacts: `sentiment_cache_free_jev.json`, `rss_sentiment_cache_jev.json`, `free_rss_jev_{compare,latest,crumbs,budget}.*`
- Cap: ≤96 Jev calls/day; default max_judge 24/run
- Isolation: `scripts/phase6/test_isolation_free_rss_jev_materiality.py`
- Delivery: local · multi-day board before any mid-cycle wire talk
- Job id: `5e2dd4ddfa96`
