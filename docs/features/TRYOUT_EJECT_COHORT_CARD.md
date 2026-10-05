# E-EJECT-COHORT-CARD

**Status:** measure-only SSOT (shipped)  
**Experiment id:** `E-EJECT-COHORT-CARD`  
**No knobs / no orders.**

## Purpose

Per scale-window **eject** shell, record:

- hold hours
- phase
- structure_ok
- paper_scaled / live_scaled
- kindling block reason
- fee-aware PnL

Headline:

**% of ejected shells that ever cleared live kindling**

So weekly analysis can separate:

- dead probes (seat → eject)
- probes that proved and still died (seat → kindling → later exit)
- fee drag on $25 shells

## Cleared kindling (definition)

`cleared_live_kindling = true` if **any** of:

1. Ledger BUY with scale-up reason (`tryout_scale_up*`, kindling/mid-flight tags) between seat and eject
2. Ghost/lot `live_scaled=true`
3. Live decision crumb `would_scale` / `scaled` / `live_apply` in the hold window

Paper-only scale (`paper_scaled` without live) counts as **not cleared**.

## Artifacts

| Path | Role |
|------|------|
| `phase6/core/tryout_eject_cohort_card.py` | Builder |
| `scripts/phase6/run_tryout_eject_cohort_card.py` | CLI |
| `data/state/tryout_eject_cohort_weekly.json` | Latest JSON |
| `reports/TRYOUT_EJECT_COHORT_CARD_LATEST.md` | Latest markdown |
| Weekly analyst fact pack `context.eject_cohort_card` | Auto on Sunday |

## CLI

```bash
PYTHONPATH=. python scripts/phase6/run_tryout_eject_cohort_card.py --days 14
PYTHONPATH=. python scripts/phase6/run_tryout_eject_cohort_card.py --days 7 --plain
```

## Product rules

- Measure only — does not change cooloff, seats, floors, or live_apply.
- Eject “green” remains **fee-aware net** (see fee audit).
- Thin N → no edge claim.
- Do **not** re-propose this as a new weekly experiment; it is live SSOT.

## Related

- Fee audit: `phase6/core/tryout_eject_fee_audit.py`
- Scale window: `phase6/core/tryout_scale_window.py`
- Weekly review: `phase6/core/analyst_weekly_trade_review.py`
