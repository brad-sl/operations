# Hermes cron SSOT (Phase 6 + host)

**Updated:** 2026-08-29  
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
| `refresh_sentiment.py` 50 8,20 | `phase6-x-sentiment-live-2x` `e17a43bfbed6` | 08:50 / 20:50 | X live + free fallback |
| `run_free_sentiment_shadow.sh` 40 8,20 | `phase6-free-sentiment-shadow-2x` `655188d1df61` | 08:40 / 20:40 | Free warm only |
| `monitor_phase6_runner.py` */15 | `phase6-runner-monitor-15m` `f14dc4b04e34` | */15 | Watchdog |
| `ops_engineer.py` */30 | `ops-engineer-30m` `3c83e4d2232c` | */30 | Deterministic |
| `backup-kanban-frequent.sh` */15 | `kanban-backup-frequent-15m` `387e688fc854` | */15 | + daily `a93067255b66` @ 03:00 |
| `phase6_rebalance_monitor.sh` */20 | **DROPPED** | — | Dead send flags |
| `/tmp/fable5_reminder.py` Mon 09:00 | **DROPPED** | — | Stale |

## Keep active (default gateway) — classes

### A — Live trading spine
Rebalance 09:05/21:05 · RSI */15 · X 08:50/20:50 · free sentiment 08:40/20:40 · runner monitor */15 · reentry SL/TP monitor */10 · dashboard live */5

### B — Ops / hygiene
ops-triage 06:00 · ops-issue-loop 07/13/19 · ops-engineer */30 · kanban backup */15 + daily 03:00 · git-daily 04:30 · llm-token rollup 05:05 · master-test pickup/scan · analyst-test-strategy Mon 10:00

### C — Operator briefs (read-only surfaces)
daily-dose 08:00 · intel TG 09:00/21:00 · deep maint 03:00 · OPT weekly Sun 04:00 · SL exit CF weekly Sun 08:30

### D — Shadow / research still active (own state only — **not** config writers)
| Job | Why still on |
|-----|----------------|
| `phase6-discovery-pipeline-shadow` | Funnel scout on disk only — **deliver=local**, no TG (Brad 2026-08-30) |
| `phase6-discovery-retro-board-daily` | Lookback: gainers × frozen contenders + T-7 forward book (research only) |
| `phase6-basket-pick-metrics-refresh` | Open promote pick still `status=open` |
| `phase6-basket-seat-idle-refresh` | Soft idle flags; observe_only |
| `phase6-basket-swap-cf-shadow` | TG only on dual_agree / preferred-arm new write / hard CF; preferred=`risk_adj_mom` →2026-09-28 |
| `phase6-vol-risk-scalar-shadow` | Keep collecting (not enough data for promote) |
| `bear-ladder-promote-watch` | **Not** done — 1 bear day / 0 episodes (need real bear) |
| free-sentiment 2× | Warm cache for X fallback (ops spine-adjacent) |

### E — One-shot still scheduled
| Job | When | Note |
|-----|------|------|
| `stoch-30d-reeval` | 2026-09-03 09:00 PT | remove after fire |
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
