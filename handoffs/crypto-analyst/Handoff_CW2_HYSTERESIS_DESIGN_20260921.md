# Handoff: CW-2 Regime hysteresis design (doc only)

**Epic:** `REGIME-CLIMATE-WEATHER-REMAINING-20260921`  
**Card:** CW-2 · P1 design  
**Assignee:** crypto-analyst  
**Plan:** `docs/plans/2026-09-21-climate-weather-remaining-four.md`

## Goal
Design hysteresis / confirm rules for bear → soft_down → flat **on paper** so climate money gates don’t thrash on single-bar edge crosses. No code unless Brad GO follow-on.

## Context
- Live classifier: `phase6/research/regime_detector.py` `classify_regime_layer` — edge thresholds, **no** multi-day confirm today.
- Bands: bear r≤−10; soft_down −10<r<−8; flat |r|≤8; bull r≥+15.
- Job split: A/C = climate 30d; B = weather micro (layered spec). Green day ≠ flat.
- Dwell board already in `regime_climate_weather` (mean bear/flat/bull ~7–8d on long tape).

## Must do
1. Read `docs/research/BULL_REENTRY_LAYERED_SPEC.md` + climate/weather plan.
2. Write `docs/plans/2026-09-21-regime-hysteresis-design.md` with:
   - Proposed N-day / structure confirms per transition
   - What stays instantaneous (dashboard label) vs money SSOT
   - Interaction with Job B (B must not wait for full hysteresis if cap rules allow — or must; pick one and justify)
   - Whipsaw vs bench-time tradeoff table
   - Explicit non-goals (no green-day open; no full-book on climb)
3. Recommend: doc-only accept vs “staff code card later.”
4. No live config writes.

## Must not
- Implement hysteresis in detector on this card
- Propose weakening bear park without evidence packet (that’s CW-3)

## Done when
- Design doc committed; Brad can GO/NO-GO a later code card
- Kanban complete with path to doc

## Skills
`regime-premise-and-basket`, `phase6-bull-reentry-timing`, `offline-strategy-honesty`
