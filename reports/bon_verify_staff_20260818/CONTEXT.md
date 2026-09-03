# Staff-next context pack — BON-STAFF-20260818-2

**Question:** What **single** scale-gap should we staff next (≤7 days), max fleet bang, min drag?  
**Method:** best-of-n-verify N=3 · criteria_staff_priority · margin_min 1.5  
**Live book:** do not touch orders, capital, TP/SL flips, USDC, mid-cycle, sleeves.

## Already DONE (ineligible as primary)
- GAP-01 exit scoreboard · GAP-02 fleet wound KPI · GAP-06 perf API soak · GAP-07 strategy queue unstick

## Eligible primaries (pick exactly one)

| ID | Status | Lane | Notes |
|----|--------|------|-------|
| `P6-SCALE-GAP-05-POST-SL-REENTRY-EFF-20260816` | **STAGED NEXT** | L3 | READY_LEDGER; ~57 SL sells / ~18 post-SL→rebuy; prior BoN runner-up; backup rule after GAP-06 ship |
| `P6-SCALE-GAP-03-CAP-SCOPE-MATRIX-20260816` | QUEUED | L2 | rebalance_cap scope matrix before cloning option B |
| `P6-SCALE-GAP-04-HARD-EXIT-EVIDENCE-CLOCK-20260816` | QUEUED | L1 | COLLECTING — only staff if clock can mature; do not invent staged decisions |
| `P6-SCALE-GAP-08-PROMO-FIREDRILL-20260816` | QUEUED | L5 | bad overlay → detect → rollback drill |
| `P6-SCALE-GAP-09-NRUNNER-ISOLATION-20260816` | QUEUED | L6 | prefer fixture/sim first; soft block only if live multi-key required |
| `P6-SCALE-GAP-10-BASKET-CF-LONGTAPE-20260816` | QUEUED | L5 | COLLECTING precursor; long-tape CF vs control_no_swap |

## Explicit low-priority (never primary)
Kelly live · mid-cycle enable · indicator mashup reopen · USDC-as-P&L · single-book trims · OPT_EX SYNTH invention

## Hard must-nots
- No live config / order / capital writes from this packet
- No live promote without Brad
- Prefer frozen bars + existing harness
- Idle-with-reason OK for immature clocks
- Ground IDs only from this table

## Output shape (exact markdown)

```markdown
## Candidate <id> · angle=<angle>
### Primary (exactly one task id)
`P6-SCALE-GAP-...`
### Optional secondary (0–1)
`...` or none
### Why now (≤5 bullets)
- ...
### Kill / pass criteria
- Pass: ...
- Kill: ...
### Must not touch
- ...
### Effort class: S|M|L
```

## Paths
- MASTER: `docs/MASTER_TASK_TRACKING.md`
- Scale map: `docs/testing/SCALE_TEST_LANES.md`
- Write **only** your candidate file path given in the task (do not read sibling candidates)

## Rubric (frozen)
fleet_bang · feasibility_7d · live_safety (floor 14) · evidence_honesty (floor 12) · low_drag  
overall = mean · margin_min = 1.5
