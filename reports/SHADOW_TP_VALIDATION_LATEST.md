# Shadow TP validation — 2026-08-29 (ARCHIVED reporter)

**Authority:** policy = `config/exit_automation.json` · runtime = `shadow_tp_status.json` · this file = metrics only.

**Day 7.71 / 7** · remaining ~0.0d · window_archived=True
- policy mode=`live` · live_market_exit=True · **live_tp_active=True**
- Unique episodes (≥30m): **170** (raw ticks 4305)
- By pair: {'PAXG-USD': 59, 'LINK-USD': 110, 'UNI-USD': 1}
- By kind: {'fixed_tp': 113, 'trail': 57}
- Open would-fire now: **0** · source=shadow_tp_status.json (read-only)
- Review gate: **False** — Live TP already ON (policy SSOT). Historical window is closed — no review needed.

## Rule
Reporter never writes config or runtime SSOT. Daily cron paused post-promote.
