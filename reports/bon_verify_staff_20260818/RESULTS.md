# BoN Staff-Next — BON-STAFF-20260818-2

**Trigger:** user “Staff next” → `best-of-n-verify` loaded  
**Question:** single scale-gap to staff next (≤7d)  
**Artifacts:** `reports/bon_verify_staff_20260818/`

## Machine scoreboard

| Rank | ID | Primary | Angle | overall |
|------|-----|---------|-------|--------:|
| 1 | **B** | **GAP-05** post-SL reentry | less_loss | **17.8** |
| 2 | BASELINE | GAP-05 (+ opt GAP-08) | single_shot | 16.8 |
| 3 | A | GAP-03 cap scope matrix | fleet_scale | 16.2 |
| 4 | C | GAP-04 hard-exit clock | evidence_clock | 12.8 |

Floors: all pass. Live book untouched.

### Script vs distinct-primary

| View | Winner | Runner | Margin | Decision |
|------|--------|--------|-------:|----------|
| Raw script (incl. baseline) | B | BASELINE | 1.0 | **escalate** |
| **Distinct primary only** | **B (GAP-05)** | A (GAP-03) | **1.6** | **pick** |

Baseline and B share primary **GAP-05** — escalate-vs-baseline is not a real staff fork.  
**Staff decision: GAP-05.**

## Why B / GAP-05

- STAGED NEXT + READY_LEDGER after GAP-06 ship  
- L3 less_loss; offline ledger; N staffable  
- Beats GAP-03 on 7d feasibility + drag (matrix is real but heavier)  
- GAP-04 correctly low: COLLECTING / immature clock → watch-not-build  

## Runner-up (stage)

**GAP-03** cap scope matrix — fleet_scale lever after GAP-05 closeout (or if GAP-05 inconclusive).

## Not this week as primary

| ID | Reason |
|----|--------|
| GAP-04 | n≈0 staged; idle week risk |
| GAP-08 | optional later hygiene |
| GAP-09/10 | fixture/long-tape; not fastest less-loss |

## Process

- Invocation path worked (skill load → pack → N=3 → score)  
- Gens clean (B/C 3 tools; A 9; no sibling contamination)  
- Baseline written **after** gens  

## Human lock

Say **execute GAP-05** (or “go”) to start offline post-SL reentry report.  
BoN will not re-run once locked.
