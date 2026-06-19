# Handoff: Fix Intelligence Report Duplication (repeats ~20x)

## Context
The "twice-daily-trading-intelligence" cron (0 9,21) runs `phase6/scripts/generate_trading_intelligence_report.py` with `no_agent: true` and delivers raw stdout directly to Telegram (1617763347).

The report is verbose (per-pair blocks, coverage, recommendations, many print() statements). Starting ~yesterday (after 2x daily + intelligence hardening), the delivered post repeats the full content ~20 times.

## Symptoms
- User sees the same long report content repeated many times in Telegram.
- Cron last runs succeeded ("ok"), but delivery is noisy.
- Related crons: rsi-15min-refresher, sentiment-30min-refresh may interact.

## Root Cause Hypotheses (to validate)
1. Multiple deliveries of the same run's stdout (retries, duplicate dispatch).
2. Script or monitor calling the report multiple times per cycle.
3. Hermes cron delivery layer repeating the message when `no_agent` + long stdout.
4. No deduplication or "last posted hash/time" check.
5. Recent schedule change (support for 9am & 21:00) introduced overlapping triggers.

## Success Criteria / Acceptance
- One clean, single delivery of the intelligence report at 9:00 and 21:00.
- No duplication in Telegram for at least 2 full cycles.
- Report remains informative but not excessively long if needed (or kept as-is with proper single delivery).
- Evidence: Screenshot or log of clean Telegram posts + cron output inspection.

## Work to Do
- Inspect cron job details, output dir for job 4dcba7aa8f06, and delivery mechanism.
- Add deduplication (e.g., last delivery timestamp or content hash in state file).
- Consider switching to agent-driven delivery with "summarize the report concisely" or "post only if meaningfully different".
- Add a simple lock or guard in the script/cron.
- Validate by forcing runs or waiting for next scheduled times.
- Update related monitors if they also call the report.

## Artifacts / References
- Cron: `hermes cron show 4dcba7aa8f06` (or jobs.json)
- Script: `phase6/scripts/generate_trading_intelligence_report.py`
- Related: scripts/monitor_canonical_sentiment.py
- State: data/state/phase6_runner_state.json
- Recent commit: 2x daily rebalance + intelligence report support.

## Verification Steps
1. Run the script manually and capture length.
2. Force a cron run if possible and inspect delivered message.
3. Check Telegram for clean single posts after fix.
4. Confirm via `hermes cron` logs or output/ dir that only one delivery occurs.

## Assignee Notes
Prefer quick fix on the cron side (dedup or delivery change) before touching report content. Coordinate with ARCH work since intelligence report will be useful for validating new allocator behavior (basket coverage, aggressive entries, etc.).

Owner: Track in crypto-bot-project Kanban.
Priority: High (affects observability of the whole system, including ARCH rollout).
