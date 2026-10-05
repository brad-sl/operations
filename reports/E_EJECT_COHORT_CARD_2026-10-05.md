# E-EJECT-COHORT-CARD — shipped (measure-only)

**Date:** 2026-10-05  
**Status:** live SSOT · no knobs · no orders

## Why

Weekly analyst proposed a funnel scorecard so we stop guessing whether ejects die before kindling or after. Fee audit alone was not enough.

## What shipped

| Piece | Path |
|-------|------|
| Core | `phase6/core/tryout_eject_cohort_card.py` |
| CLI | `scripts/phase6/run_tryout_eject_cohort_card.py` |
| Tests | `scripts/phase6/test_isolation_tryout_eject_cohort_card.py` |
| Docs | `docs/features/TRYOUT_EJECT_COHORT_CARD.md` |
| State | `data/state/tryout_eject_cohort_weekly.json` |
| Report | `reports/TRYOUT_EJECT_COHORT_CARD_LATEST.md` |
| Weekly hook | `analyst_weekly_trade_review` → `context.eject_cohort_card` |

## First live read (14d, 2026-10-05)

- **n ejects:** 8  
- **% cleared live kindling:** **0%** (0/8)  
- **Paper-scaled, never live:** 6  
- **Structure unknown:** 2  
- **Hold h mean / median:** ~61.5 / ~72.7  
- **Gross PnL:** +$0.30 · **RT fees:** $3.28 · **Net:** **−$2.99**  
- **Fee-aware green:** 0 · **Gross→net wipe:** 6  

### Top kindling blocks

1. `paper_would_scale_not_live` ×6 — paper path said scale; live kindling never fired  
2. `structure_unknown` ×2 — no structure verdict at eject (HYPE short holds)

### Plain English

Every eject this window died **before** a live kindling add. Most had paper “would scale” crumbs but **no live scale buy**. Funnel is still seat→eject, not seat→prove→add. Fees dominate. No edge claim (thin N).

## Product law

- Measure only.  
- Do not re-propose E-EJECT-COHORT-CARD as a new experiment — it is SSOT.  
- Cleared kindling = **live** only (ledger scale-up buy or `live_scaled`). Paper ≠ cleared.

## Next use

Sunday weekly auto-includes the snapshot. Manual refresh:

```bash
PYTHONPATH=. python scripts/phase6/run_tryout_eject_cohort_card.py --days 14 --plain
```
