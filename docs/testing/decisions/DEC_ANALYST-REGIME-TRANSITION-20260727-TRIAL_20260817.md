# Decision packet — ANALYST-REGIME-TRANSITION-20260727-TRIAL

| Field | Value |
|-------|--------|
| Trial | `ANALYST-REGIME-TRANSITION-20260727-TRIAL` |
| Family | `regime_transition` |
| Decided at (UTC) | 2026-07-27T19:16:47.129430+00:00 |
| By | brad |
| Enum | `drop` |
| CR | **REJECT** |
| Follow-on | `none` |
| Regimen | `docs/testing/TEST_REGIMEN_E2E.md` |

## Design (summary)
- Hypothesis: Transition cap/park settings drive unnecessary whipsaw or idle cash
- Primary window: `transition_slices`
- Success bar (frozen): min_n=10; beat ret+dd=True

## Outcome (measured)
- Primary pass: **False**
- Class: `unstable_or_no_edge`
- N (primary): —
- Δret vs baseline (pp): —
- ΔDD vs baseline (pp): —
- Report: `reports/REGIME_TRANSITION_TEST_2026-07-27.md`
- Plain English: Drop — no transition knob promote from this dig.

## Decision rationale
[regimen retrofit 20260817] offline regime transition: USDC/park wins; no faster-flip

## Follow-on
- Mode: `none`
- Detail: No transition promote line from this trial.

## Notify
- Inbox: `docs/testing/inbox/DECIDED_ANALYST-REGIME-TRANSITION-20260727-TRIAL_20260817.md`
- Packet: `docs/testing/decisions/DEC_ANALYST-REGIME-TRANSITION-20260727-TRIAL_20260817.md`

## Live boundary
- Config writes this decision: **none**

## Regimen retrofit
- Applied 20260817 under `docs/testing/TEST_REGIMEN_E2E.md`
- Decision enum **unchanged** (`drop`)
- Fields backfilled: success_criteria, outcome, follow_on, packet
