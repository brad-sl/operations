# E-EJECT-COHORT-CARD — eject cohort card

**As of:** 2026-10-05T02:06:44.434791+00:00  
**Schema:** `tryout_eject_cohort_card_v1`  
**Lookback days:** 14.0  
**Measure-only / no knobs:** True / True  
**Edge claim:** False  

## Plain English

0/8 eject shells ever cleared live kindling (0%). No edge claim — measure funnel only.

## Headline

| Metric | Value |
|--------|-------|
| Ejects | 8 |
| Cleared live kindling | 0 |
| **% cleared kindling** | **0.0%** |
| Paper-scaled, never live | 6 |
| Structure false / unknown | 0 / 2 |
| Hold h mean / median | 61.507 / 72.747 |
| Gross PnL | $0.299341 |
| RT fees | $3.284719 |
| **Net PnL** | **$-2.985378** |
| Fee-aware green | 0 |
| Gross→net wipe | 6 |

**Product rule:** Tryout shell = timed option on kindling. Headline = % ejects that cleared live_signal kindling before death. Fee-aware net only for profit language.

## Kindling block (top)

| block | n |
|-------|---|
| paper_would_scale_not_live | 6 |
| structure_unknown | 2 |

## Cohort rows

| exit | pair | hold_h | phase | struct | paper | live | block | gross | fee | net |
|------|------|--------|-------|--------|-------|------|-------|-------|-----|-----|
| 2026-10-04T16:45:46 | SOL-USD | 72.747 | 2 | Y | Y |  | paper_would_scale_not_live|earned_mid_fl | 0.371344 | 0.448742 | -0.077398 |
| 2026-10-03T22:45:44 | LINK-USD | 162.744 | 3 | Y | Y |  | paper_would_scale_not_live|earned_mid_fl | 0.32041 | 0.353319 | -0.032909 |
| 2026-10-02T22:45:43 | HYPE-USD | 5.253 | None | — |  |  | structure_unknown | -0.35687 | 0.446546 | -0.803416 |
| 2026-10-02T04:45:43 | HYPE-USD | 24.719 | None | — |  |  | structure_unknown | 0.17984 | 0.450364 | -0.270524 |
| 2026-10-01T14:41:54 | TIA-USD | 4.689 | 3 | Y | Y |  | paper_would_scale_not_live|earned_mid_fl | -0.656307 | 0.444015 | -1.100322 |
| 2026-10-01T14:41:49 | LINK-USD | 106.679 | 3 | Y | Y |  | paper_would_scale_not_live|earned_mid_fl | 0.11725 | 0.349031 | -0.231781 |
| 2026-10-01T05:29:58 | LINK-USD | 97.481 | 3 | Y | Y |  | paper_would_scale_not_live|earned_mid_fl | 0.11591 | 0.347128 | -0.231218 |
| 2026-10-01T05:29:54 | TIA-USD | 17.74 | 3 | Y | Y |  | paper_would_scale_not_live|earned_mid_fl | 0.207764 | 0.445574 | -0.23781 |

## Notes

- cleared_live_kindling = ledger buy with tryout_scale_up/kindling reason in the lot window, or lot live_scaled.
- paper_scaled / would_scale is NOT live kindling clearance.
- phase/structure prefer ghost lot close meta, else nearest shadow crumb ≤36h before eject.
- Thin N: no promote / no knob advice from this card alone.
