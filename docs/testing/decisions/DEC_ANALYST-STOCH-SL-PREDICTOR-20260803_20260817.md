# Decision packet — ANALYST-STOCH-SL-PREDICTOR-20260803

| Field | Value |
|-------|--------|
| Trial | `ANALYST-STOCH-SL-PREDICTOR-20260803` |
| Family | `stoch_sl_predictor` |
| Decided at (UTC) | 2026-08-03T18:31:07.631174+00:00 |
| By | brad |
| Enum | `drop` |
| CR | **REJECT** |
| Follow-on | `none` |
| Regimen | `docs/testing/TEST_REGIMEN_E2E.md` |

## Design (summary)
- Hypothesis: Entry-time Stoch predicts SL better than chance (not exit-time reverse causality)
- Primary window: `entry_time_forward_sl`
- Success bar (frozen): min_n=15; beat ret+dd=False

## Outcome (measured)
- Primary pass: **False**
- Class: `unstable_or_no_edge`
- N (primary): —
- Δret vs baseline (pp): —
- ΔDD vs baseline (pp): —
- Report: `reports/STOCH_SL_PREDICTOR_DIG_2026-08-03.md`
- Plain English: no_utility_drop → decide drop. No combo-fish.

## Decision rationale
[regimen retrofit 20260817] Brad 2026-08-03: maps from dig enum no_utility_drop — no winning RSI+Stoch entry/exit/SL combo (lift inverted, no gain edge). Finish parent Stoch final only; no combo-fishing. Narrative/scorer tags OK.

## Follow-on
- Mode: `none`
- Detail: No RSI+Stoch combo fishing; parent observe path separate.

## Notify
- Inbox: `docs/testing/inbox/DECIDED_ANALYST-STOCH-SL-PREDICTOR-20260803_20260817.md`
- Packet: `docs/testing/decisions/DEC_ANALYST-STOCH-SL-PREDICTOR-20260803_20260817.md`

## Live boundary
- Config writes this decision: **none**

## Regimen retrofit
- Applied 20260817 under `docs/testing/TEST_REGIMEN_E2E.md`
- Decision enum **unchanged** (`drop`)
- Fields backfilled: success_criteria, outcome, follow_on, packet
