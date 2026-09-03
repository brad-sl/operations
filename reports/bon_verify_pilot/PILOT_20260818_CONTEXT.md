# BoN Verify Pilot — context pack (2026-08-18)

**Pilot ID:** `BON-STAFF-PRIORITY-20260818`  
**Domain:** staff / priority (read-only)  
**N:** 3 generators + 1 single-shot baseline  
**Live book:** DO NOT TOUCH  

## Goal for each generator

Write one **staffing priority packet** (≤400 words, structured) answering:

> What is the single best **primary** scale-gap (or ACTIVE collect task) to staff in the next 7 days for fleet bang-for-buck, plus at most one optional secondary?

## Hard constraints

- Primary MUST be a real id from the eligible list below.
- No live TP / hard-exit auto-apply / mid-cycle / USDC park / capital rewrite / sleeve trim.
- Idle-with-reason is valid if nothing beats “keep collecting.”
- Prefer frozen success bars already on MASTER.
- Platform scale (100s traders) > single-book P&amp;L cosplay.
- OPT_EX SYNTH (2026-08-13/15): **idle-with-reason** — do not invent pursue from that pack.

## Eligible primaries (choose one)

| ID | Status | Lane | Notes |
|----|--------|------|-------|
| `P6-SCALE-GAP-03-CAP-SCOPE-MATRIX-20260816` | QUEUED | L2 | Cap scope matrix offline; live rewrite gated |
| `P6-SCALE-GAP-04-HARD-EXIT-EVIDENCE-CLOCK-20260816` | QUEUED | L1 | T1 evidence clock; collection quality dependent |
| `P6-SCALE-GAP-05-POST-SL-REENTRY-EFF-20260816` | QUEUED | L3 | Post-SL reentry efficiency offline ledger |
| `P6-SCALE-GAP-06-PERF-API-SOAK-20260816` | QUEUED | L4 | Perf API soak; NEEDS_VALIDATE post cache fix |
| `P6-SCALE-GAP-08-PROMO-FIREDRILL-20260816` | QUEUED | L5 | Promo fire-drill ISO |
| `P6-SCALE-GAP-09-NRUNNER-ISOLATION-20260816` | QUEUED | L6 | N-runner isolation |
| `P6-SCALE-GAP-10-BASKET-CF-LONGTAPE-20260816` | QUEUED | L5 | Basket CF long-tape |
| `P6-LIQ-REDEPLOY-SHADOW-20260816` | ACTIVE collecting | L2/L3 | Shadow only; live_partial NO-GO |
| `P6-SCALE-GAP-01-EXIT-PROMOTE-SCOREBOARD-20260816` | DONE/COLLECTING | L1 | Already shipped scoreboard — only if “ops habit” not new build |

**Done / do not re-staff as new primary:** GAP-01 shipped, GAP-02 shipped, GAP-07 DONE (2026-08-17).

## Staffing default from map

L1 exits → L3 fleet wounds → L2 cap semantics → L5 hygiene → L4 soak → L6.

## Recent honesty anchors

- Liq redeploy: `unreliable_as_default`; live_partial NO-GO; shadow collecting.
- Exit promote scoreboard: collecting calendar (~10/60d); multi-regime thin.
- Fib/SR entry shadows: CR REJECT drop.
- Bull knobs zombie aborted; successor parked until bull/historical unlock.

## Required output shape

```markdown
## Candidate <ID> · angle=<angle>
### Primary (exactly one task id)
### Optional secondary (0–1)
### Why now (≤5 bullets)
### Kill / pass criteria
### Must not touch
### Effort class: S|M|L
```
