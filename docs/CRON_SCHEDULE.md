# Phase 6 Cron Schedule

> **LEGACY cadence (2026-06-28).** Live SSOT: **`docs/HERMES_CRON_SSOT.md`**.  
> Linux user crontab is **empty of jobs** (2026-08-13). Sentiment is **08:40 free / 08:50 X** (not :04/:34).  
> Do not re-add jobs to `crontab -e`.

**Last Updated:** 2026-06-28 (banner 2026-08-13)  
**Purpose:** Historical schedule notes after migration from continuous runner.

## Philosophy
- Decompose responsibilities (no more monolithic 30-minute loop).
- Explicit triggers instead of hoping a loop hits time windows.
- Respect configured rebalance times (`09:00`, `21:00` PT) with buffers for data freshness.
- Support follow-on dependencies: fresh data → report/brief → rebalance.
- Use Hermes cron for reliability, logging, and delivery.
- All times in system local (PDT/PT). Ensure host TZ is consistent (`America/Los_Angeles`).

## Execution Sequence & Dependencies

```
:04 and :34 (optimized, ~1 min before rebalances)          : refresh_sentiment.py
    ↓ (populates sentiment_cache.json, RSI, etc.)

08:30 / 20:30         : generate_trading_intelligence_report.py
    ↓ (produces intel_strategic_brief.json + regime snapshot,
       uses recent refresh data + Polymarket overlay)

09:05 / 21:05         : cron_rebalance.py --live
    ↓ (consumes brief + latest caches + hybrid decision,
       performs _perform_daily_rebalance with ARCH-4 allocator,
       stop suspend/reattach, trade ledger, state save)

12:05 / 18:05 (opt)   : cron_rebalance.py --live   (lighter hybrid check)
03:00                 : generate_trading_intelligence_report.py (deep maintenance + brief)
Sun 04:00             : run_analyst_opt_weekly.py (scenario vs production)
06:00                 : Daily Triage (planning/kanban)
```

**Key Dependencies:**
- Sentiment/RSI refresh must precede report and rebalance (freshness guard in runner relies on mtime of caches).
- Intelligence report precedes rebalance (brief is loaded at `data/state/intel_strategic_brief.json` and wired into runner for regime/influence).
- Rebalance always saves state (prevents monitor desync).
- Midday checks are opportunistic and can run on stale-ish data if needed.

## Full Schedule Table

| Task                        | Cron Expression     | PT Time(s)       | Script/Command                                      | Hermes Job Name (suggested)              | Notes / Dependencies |
|-----------------------------|---------------------|------------------|-----------------------------------------------------|------------------------------------------|----------------------|
| Sentiment + RSI refresh     | `4,34 * * * *`     | :04 and :34 (optimized pre-rebalance) | `phase6/scripts/refresh_sentiment.py`              | Phase6 Sentiment/RSI Refresh            | ~1 min before :05 rebalances for minimal staleness at allocator. Exact same frequency (no extra charges). Staleness guard + age logging in consumers. |
| Pre-rebalance brief         | `30 8,20 * * *`    | 08:30, 20:30    | `phase6/scripts/generate_trading_intelligence_report.py` | Phase6 Pre-Rebalance Intelligence Brief | Produces intel_strategic_brief.json. Must run after recent refresh. |
| Rebalance (morning)         | `5 9 * * *`        | 09:05           | `phase6/scripts/cron_rebalance.py --live`          | Phase6 Daily Rebalance - Morning        | Main trigger. Consumes brief. 5-min buffer after 09:00. |
| Rebalance (evening)         | `5 21 * * *`       | 21:05           | `phase6/scripts/cron_rebalance.py --live`          | Phase6 Daily Rebalance - Evening        | Main trigger. 5-min buffer after 21:00. |
| Midday opportunistic        | `5 12,18 * * *`    | 12:05, 18:05    | `phase6/scripts/cron_rebalance.py --live`          | Phase6 Midday Rebalance Check           | Lighter hybrid rebalance. Follows recent refresh. |
| Deep maintenance            | `0 3 * * *`        | 03:00           | `phase6/scripts/generate_trading_intelligence_report.py` | Phase6 Deep Maintenance Brief           | Early report + opportunity for state cleanup. Extend as needed. |
| ANALYST-OPT weekly          | `0 4 * * 0`        | Sun 04:00       | `phase6/research/run_analyst_opt_weekly.py`              | Phase6 Analyst Optimization Weekly      | Path B leaderboard + production compare; feeds brief via `analyst_scenario_leaderboard_latest.json`. |
| Daily Triage                | `0 6 * * *`        | 06:00           | (existing triage prompt/job)                       | Daily Triage and Prioritization         | Planning/kanban. Keep as-is. |

## Hermes Cron Job Configuration

Jobs are managed in `~/.hermes/profiles/crypto-orchestrator/cron/jobs.json`.

Example job (script-driven, no_agent for pure execution):
```json
{
  "id": "...",
  "name": "Phase6 Sentiment/RSI Refresh",
  "script": "phase6/scripts/refresh_sentiment.py",
  "no_agent": true,
  "schedule": {"kind": "cron", "expr": "*/30 * * * *", "display": "*/30 * * * *"},
  "workdir": "/home/brad/projects/crypto-trading-bot",
  "enabled": true,
  "deliver": "origin"
}
```

**Creation:** Use `hermes cron` or the `cronjob` tool / direct edit + reload.

**Workdir:** All jobs use project root so relative paths and state files resolve correctly.

**Safety:**
- Rebalance jobs default to `--live` (matching prior continuous setup). Test with shadow first by editing script arg.
- Refresh and report are read-only (safe).
- Monitor `check_last_rebalance()` after changes.

## Why This Schedule?

- **Buffers prevent "window missed" warnings:** Cron explicitly triggers after configured times instead of polling.
- **Data freshness:** `*/15` refresh + pre-brief at :30 ensures `_should_run_full_evaluation()` and brief have current sentiment/RSI/Polymarket.
- **Clear dependencies:** Report → Rebalance chain is explicit in timing.
- **Maintainability:** Each task has one job. Easy to pause, change buffer, or add logging.
- **Observability:** Hermes delivers output; combine with existing monitor script.
- **Resource friendly:** No always-on 30-min loop.

## Future Enhancements

- Add post-rebalance health check (e.g. 15 9,21).
- Make midday use `--shadow` or a lighter hybrid-only flag.
- Add TZ=America/Los_Angeles wrapper if host TZ drifts.
- Extend deep maintenance with log rotation or state compaction.
- Monitor execution durations and alert on overruns.

## Related Files

- `config/trading_config_phase6.json` (daily_rebalance_times)
- `phase6/scripts/cron_rebalance.py`
- `phase6/scripts/refresh_sentiment.py`
- `phase6/scripts/generate_trading_intelligence_report.py`
- `phase6/core/phase6_runner.py` (_should_rebalance, _perform_daily_rebalance, freshness guard)
- `data/state/intel_strategic_brief.json`
- `data/state/phase6_runner_state.json`
- `scripts/phase6/monitor_phase6_runner.py`

See also MASTER_TASK_TRACKING.md for implementation history.
