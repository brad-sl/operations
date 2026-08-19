# Decision packet — TEST-COMBINED-INDICATOR-ABLATION-20260803-TRIAL

| Field | Value |
|-------|--------|
| Trial | `TEST-COMBINED-INDICATOR-ABLATION-20260803-TRIAL` |
| Family | `combined_indicator_ablation` |
| Decided at (UTC) | 2026-08-03T22:40:52.038506+00:00 |
| By | brad |
| Enum | `drop` |
| CR | **REJECT** |
| Follow-on | `none` |
| Regimen | `docs/testing/TEST_REGIMEN_E2E.md` |

## Design (summary)
- Hypothesis: MACD×RSI×ATR confluence beats BASE on long tape
- Primary window: `long_tape`
- Success bar (frozen): min_n=15; beat ret+dd=True

## Outcome (measured)
- Primary pass: **False**
- Class: `unstable_or_no_edge`
- N (primary): —
- Δret vs baseline (pp): —
- ΔDD vs baseline (pp): —
- Report: `reports/COMBINED_INDICATOR_ABLATION_MULTIPAIR_2026-08-03.md`
- Plain English: Long-tape WF fail; drop — no standard opt.

## Decision rationale
[regimen retrofit 20260817] Brad 2026-08-03: drop. Short-window ~+5% F2 did not survive Coinbase long-tape walk-forward (2021-2026 EW mean -20%, BTC F2 -53%). No standard opt / no live. Keep lessons: kill 4-way AND stack; RSI filter > MACD-only; no Stoch/BB required entry. Residual regime-gate idea only if Brad reopens.

## Follow-on
- Mode: `none`
- Detail: No combo-fish reopen without Brad one-door.

## Notify
- Inbox: `docs/testing/inbox/DECIDED_TEST-COMBINED-INDICATOR-ABLATION-20260803-TRIAL_20260817.md`
- Packet: `docs/testing/decisions/DEC_TEST-COMBINED-INDICATOR-ABLATION-20260803-TRIAL_20260817.md`

## Live boundary
- Config writes this decision: **none**

## Regimen retrofit
- Applied 20260817 under `docs/testing/TEST_REGIMEN_E2E.md`
- Decision enum **unchanged** (`drop`)
- Fields backfilled: success_criteria, outcome, follow_on, packet
