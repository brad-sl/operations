# Decision packet — ANALYST-REGIME-FLAT-KNOBS-20260730-TRIAL

| Field | Value |
|-------|--------|
| Trial | `ANALYST-REGIME-FLAT-KNOBS-20260730-TRIAL` |
| Family | `regime_flat_knobs` |
| Decided at (UTC) | 2026-07-30T22:11:59.188362+00:00 |
| By | brad |
| Enum | `propose_scoped_experiment` |
| CR | **ACCEPT** `CR-regime-flat-knobs-20260817` |
| Follow-on | `scoped_shadow` |
| Regimen | `docs/testing/TEST_REGIMEN_E2E.md` |

## Design (summary)
- Hypothesis: Under flat option B, rebalance beats rotation; nearby grid may improve without bull rotation knobs
- Primary window: `flat_live_overlap`
- Success bar (frozen): min_n=15; beat ret+dd=True

## Outcome (measured)
- Primary pass: **True**
- Class: `HIT_CRITERIA`
- N (primary): —
- Δret vs baseline (pp): —
- ΔDD vs baseline (pp): —
- Report: `reports/REGIME_FLAT_KNOBS_DIG_LAYERED_2026-07-30.md`
- Plain English: Scoped experiment proposed (not full promote). CR ACCEPT scoped only.

## Decision rationale
[regimen retrofit 20260817] flat B rebalance keep; layered paper shadow now; live shadow after Stoch final (REGIME_FLAT_KNOBS_DIG_LAYERED_2026-07-30)

## Follow-on
- Mode: `scoped_shadow`
- Detail: propose_scoped_experiment — shadow/param_audit only; no live write

## Notify
- Inbox: `docs/testing/inbox/DECIDED_ANALYST-REGIME-FLAT-KNOBS-20260730-TRIAL_20260817.md`
- Packet: `docs/testing/decisions/DEC_ANALYST-REGIME-FLAT-KNOBS-20260730-TRIAL_20260817.md`

## Live boundary
- Config writes this decision: **none**

## Regimen retrofit
- Applied 20260817 under `docs/testing/TEST_REGIMEN_E2E.md`
- Decision enum **unchanged** (`propose_scoped_experiment`)
- Fields backfilled: success_criteria, outcome, follow_on, packet
