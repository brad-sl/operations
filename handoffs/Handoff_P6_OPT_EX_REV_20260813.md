# Task Handoff Document

**Task ID:** `P6-OPT-EX-REV-20260813`  
**Parent Task:** `P6-OPT-EX-SYNTH-20260813`  
**Assigned To:** crypto-orchestrator  
**Date Assigned:** 2026-08-13  

### Objective
Honesty / scope review of the examine-pack. Confirm no live writes, no fake edge, SYNTH matches the five reports.

### Must Do
- Confirm five reports + scorecard exist on disk
- Grep workers didn’t flip `mid_cycle_allocator_enabled`, `take_profit.mode`, USDC, basket
- Reject SYNTH if it promotes a live flip or 10–20% claim without numbers
- MASTER note: REV pass/fail + date
- Kanban complete with summary pointing at scorecard

### Must Not
- Re-do the research
- Nod through a pursue-live-TP

### Validation
```bash
ls reports/OPT_EX_0{1,2,3,4,5}_*.md reports/OPT_EX_SYNTH_SCORECARD_*.md
rg -n "mid_cycle_allocator_enabled|take_profit" config/ phase6/ --glob '!*.md' | head
```
