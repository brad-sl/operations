# Task Handoff Document

**Task ID:** `P6-OPT-EX-01-EXITS-20260813`  
**Parent Task:** `P6-OPT-EXAMINE-PACK-20260813`  
**Assigned To:** crypto-analyst  
**Date Assigned:** 2026-08-13  

### Objective
Answer: is the **regime exit shadow map** ready even to *discuss* a live profit-exit flip, or still in the 1–2 month observe window?

### Context
`P6-REGIME-EXIT-POLICY-MAP-20260806` is LIVE_SHADOW. Live TP gated on 60d / ≥5 unique would-fire episodes per regime + Brad OK. Weekly SL counterfactual cron exists. User asked not to thaw live profit-exit early.

### Must Do
- Read `data/state/regime_exit_shadow_status.json`, `…_collection.json`, `docs/REGIME_EXIT_POLICY_MAP.md`, latest `reports/SL_EXIT_COUNTERFACTUAL_LATEST.md`
- Count unique episodes by regime (30m gap ≠ tick spam)
- Calendar days since 2026-08-06
- Plain-English call: `watch` (default if thin) / `pursue` (only if gates met) / `drop` (if map is junk) / `blocked_on_brad` (gates met, needs human)
- Write `reports/OPT_EX_01_EXITS_2026-08-13.md`

### Must Not
- Flip take_profit.mode or map auto_promote
- Propose a new global TP%
- Telegram would-fire spam
- Invent episode counts

### Files
- Read: `config/regime_exit_policy_map.json`, `phase6/core/regime_exit_shadow.py`, state JSON above
- Write: report only + optional MASTER note under this task id

### Success
Report has: days elapsed, episode counts by regime, gate table vs MASTER gates, one call enum, “not a live flip” explicit.

### Validation
`rg -n "pursue|watch|drop|blocked_on_brad" reports/OPT_EX_01_EXITS_2026-08-13.md`

### Skills
`offline-strategy-honesty`, `phase6-exit-profit-shadow`, `phase6-exit-automation`
