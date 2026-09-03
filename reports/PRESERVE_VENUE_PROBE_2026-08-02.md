# Preserve venue probe — 2026-08-02

**Result:** `A`
**Product:** PAXG-USD
**Execute:** True
**Price:** 4056.185
**Meta:** `{'price_increment': 0.01, 'base_increment': 1e-05}`
**T2 single:** True
**T4 two concurrent:** True
**T5 three concurrent:** True
**Order IDs:** ['6a8e484b-342f-450b-b474-234ddded799e', '21544b3b-e4bc-46e2-a295-1257b0cb65ca', '697c5b36-be4e-4d6d-9def-e055f6ed3672']
**Errors:** []

JSON: `data/state/preserve_venue_probe_latest.json`

## Meaning
- **A:** ≥2 concurrent stop-limits OK — Hold E1 + multi-leg DeRisk possible
- **B:** single stop only — Hold E1 only; DeRisk multi-leg blocked on exchange
- **C:** stops unreliable / cannot place — Preserve blocked
