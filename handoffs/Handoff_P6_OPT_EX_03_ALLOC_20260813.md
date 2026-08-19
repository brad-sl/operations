# Task Handoff Document

**Task ID:** `P6-OPT-EX-03-ALLOC-20260813`  
**Parent Task:** `P6-OPT-EXAMINE-PACK-20260813`  
**Assigned To:** crypto-analyst  
**Date Assigned:** 2026-08-13  

### Objective
Study-only: would **mid-cycle allocator** have deployed anything useful vs slot-only (09:00/21:00), under current flat caps? Recommend keep-off / shadow-log / (not enable).

### Context
`P6-MID-CYCLE-ALLOCATOR-EVAL-20260807` is QUEUED. Flag `global_settings.mid_cycle_allocator_enabled` is **false**. Enable needs Brad OK. This card is the **eval**, not the enable.

### Must Do
- Find any existing `reports/MID_CYCLE_ALLOCATOR_EVAL_*` — if a good one exists, assess it; do not redo a grid
- If none: counterfactual from real logs/scores last N days (state if N thin)
- Risk notes: $75 flat-B, util 65%, RSI/sentiment gates, fees, interaction with armed-stop gate
- Call: `drop` (keep off, not worth it) / `watch` (need more tape) / `pursue` (propose Type:test shadow-log only)
- Write `reports/OPT_EX_03_ALLOC_2026-08-13.md`

### Must Not
- Set mid_cycle_allocator_enabled true
- Standard_opt / combo-fish
- Claim 10–20% edge from a short window

### Files
- Read: `phase6/core/cycle_coordinator.py`, MASTER mid-cycle section, configs
- Write: report only

### Success
One page: would-deploys count, rough turnover/risk, enum call. If data insufficient, say inconclusive.

### Skills
`offline-strategy-honesty`, `phase6-risk-sizing-research`
