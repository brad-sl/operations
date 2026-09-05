# Sentiment aging bugfix (2026-09-04)

## Bug
Live decision paths called `load_sentiment_scores()` and used **raw** cache values with **no exponential decay**.

That violated the tested contract:
- X / twitter is **highly transitory** (grid-optimal half-life **15 minutes**)
- Reddit was the **hour bridge** (half-life **60 minutes**, still ~0.59 weight at 45m)

Evidence:
- `config/sentiment_grid_results_20260421_151742/SUMMARY.json` → optimal `twitter 15 / reddit 60`
- Alternate merge path `phase6/core/sentiment/sentiment_scorer.py` already encoded 15/60
- Canonical helper `get_aged_sentiment_scores` existed but **almost no live caller used it**
- `docs/X_SENTIMENT_COST_CONTROL.md` assumed aging; rebalance/runner did not apply it

## Why it hurt
With X only 2×/day and Reddit Apify **OFF**, raw X sat at **full strength for ~12h**. Entry floors / sent haircuts / boosts treated hours-old social as fresh.

## Fix
Canonical `phase6/core/sentiment_scorer.py`:
- `apply_aging=True` by default on `load_sentiment_scores` / `_detailed`
- Per-source HL: X **15m**, Reddit **60m**, free **60m** (when live fallback)
- Staleness hard-zero: X 120m, Reddit 240m
- Keeps `sentiment_raw`, `decay_factor`, `age_min` on detailed rows
- Config knobs under `sentiment.*` + env `SENTIMENT_APPLY_AGING`
- Isolation: `phase6/core/test_isolation_sentiment_aging.py`

## Reddit bridge gap (still open)
Reddit Apify stays **OFF** (cost). After X ages out (~45–90m), scores correctly → near zero until next X pull. Free hybrid 2h shadow is the **cheap bridge candidate** — live mid-cycle free reinforce only after multi-day `promote_ready` + Brad GO.

## Live snapshot at fix (example)
| | LINK |
|--|--|
| raw | ~0.43 |
| age | ~69 min |
| decay (15m HL) | ~0.041 |
| aged | ~0.018 |
