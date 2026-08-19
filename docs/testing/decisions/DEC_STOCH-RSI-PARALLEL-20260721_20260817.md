# Decision packet — STOCH-RSI-PARALLEL-20260721

| Field | Value |
|-------|--------|
| Trial | `STOCH-RSI-PARALLEL-20260721` |
| Family | `stoch_rsi` |
| Decided at (UTC) | 2026-08-04T19:50:11.510682+00:00 |
| By | brad |
| Enum | `continue_observe_only` |
| CR | **NO_CR** |
| Follow-on | `extend` |
| Regimen | `docs/testing/TEST_REGIMEN_E2E.md` |

## Design (summary)
- Hypothesis: Stoch adds SL/risk timing edge beyond RSI alone
- Primary window: `parallel_instrumentation_window`
- Success bar (frozen): min_n=15; beat ret+dd=False

## Outcome (measured)
- Primary pass: **False**
- Class: `inconclusive_sparse_N`
- N (primary): —
- Δret vs baseline (pp): —
- ΔDD vs baseline (pp): —
- Report: `/home/brad/projects/crypto-trading-bot/reports/STOCH_RSI_TRIAL_FINAL_2026-08-04.md`
- Plain English: continue_observe_only — not promote; ~30d re-eval calendar.

## Decision rationale
[regimen retrofit 20260817] Brad 2026-08-04: continue_observe_only — keep 15m Stoch logging; no allocator/SL change. Child dig no_utility_drop (entry lift inverted). Final script propose_scoped_sl_risk superseded. Plan ~30d counterfactual recheck: would decisions of substance change. No combo-fishing.

## Follow-on
- Mode: `extend`
- Detail: NEEDS_REEVAL ~2026-09-03 counterfactual (continue_observe_only)

## Notify
- Inbox: `docs/testing/inbox/DECIDED_STOCH-RSI-PARALLEL-20260721_20260817.md`
- Packet: `docs/testing/decisions/DEC_STOCH-RSI-PARALLEL-20260721_20260817.md`

## Live boundary
- Config writes this decision: **none**

## Regimen retrofit
- Applied 20260817 under `docs/testing/TEST_REGIMEN_E2E.md`
- Decision enum **unchanged** (`continue_observe_only`)
- Fields backfilled: success_criteria, outcome, follow_on, packet
