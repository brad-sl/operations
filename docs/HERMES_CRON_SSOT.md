# Hermes cron SSOT (Phase 6 + host)

**Updated:** 2026-08-13  
**Law:** **Do not put Phase 6 / sentiment / X / Apify / runner monitors on Linux `crontab`.**  
User crontab is comment-only. Backup: `~/.hermes/cron/linux-crontab.bak.20260813`.

Verify: `crontab -l` (no executable lines) + `hermes cron list`.

## Cutover (2026-08-13)

| Was Linux | Hermes job | Schedule (PT) | Notes |
|-----------|------------|---------------|--------|
| `refresh_sentiment.py` 50 8,20 | `phase6-x-sentiment-live-2x` `e17a43bfbed6` | 08:50 / 20:50 | X live + free fallback |
| `run_free_sentiment_shadow.sh` 40 8,20 | `phase6-free-sentiment-shadow-2x` `655188d1df61` | 08:40 / 20:40 | Free warm only |
| `monitor_phase6_runner.py` */15 | `phase6-runner-monitor-15m` `f14dc4b04e34` | */15 | Watchdog |
| `ops_engineer.py` */30 | `ops-engineer-30m` `3c83e4d2232c` | */30 | Deterministic |
| `backup-kanban-frequent.sh` */15 | `kanban-backup-frequent-15m` `387e688fc854` | */15 | + daily `a93067255b66` @ 03:00 |
| `phase6_rebalance_monitor.sh` */20 | **DROPPED** | — | Dead `hermes send --target/--message`; redundant vs runner monitor + rebalance crons |
| `/tmp/fable5_reminder.py` Mon 09:00 | **DROPPED** | — | Stale Jun review list in `/tmp` |

Already on Hermes (unchanged): intel v2, rebalance 09:05/21:05, daily dose, discovery, basket CF, OPT weekly, ops-triage, etc.

## Agent rules

1. New schedules → `cronjob` / `hermes cron` on **default** gateway only.  
2. `no_agent` scripts: `export PATH=$HOME/.local/bin:$PATH`; **never** bare `hermes`.  
3. `hermes send` = stdin + `-t telegram` only (no `--target` / `--message`). Prefer stdout + `deliver=telegram` for no_agent.  
4. Do **not** re-enable Linux lines “as backup.”  
5. `sentiment-30min-refresh` stays **paused**. Reddit Apify **OFF**.

## Dashboard

Live UI: user systemd `phase6-dashboard-8502.service` → `:8502` (venv). Not Linux cron.
