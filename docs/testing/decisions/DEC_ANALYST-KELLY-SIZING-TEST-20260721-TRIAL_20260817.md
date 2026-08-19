# Decision packet — ANALYST-KELLY-SIZING-TEST-20260721-TRIAL

| Field | Value |
|-------|--------|
| Trial | `ANALYST-KELLY-SIZING-TEST-20260721-TRIAL` |
| Family | `kelly_sizing` |
| Decided at (UTC) | 2026-07-22T03:22:47.294307+00:00 |
| By | brad |
| Enum | `drop` |
| CR | **REJECT** |
| Follow-on | `none` |
| Regimen | `docs/testing/TEST_REGIMEN_E2E.md` |

## Design (summary)
- Hypothesis: Half/quarter Kelly risk-at-SL improves growth/DD vs fixed knobs
- Primary window: `ledger_oos`
- Success bar (frozen): min_n=15; beat ret+dd=True

## Outcome (measured)
- Primary pass: **False**
- Class: `unstable_or_no_edge`
- N (primary): —
- Δret vs baseline (pp): —
- ΔDD vs baseline (pp): —
- Report: `reports/KELLY_SIZING_TEST_2026-07-21.md`
- Plain English: OOS edge fail; drop — no shadow promote.

## Decision rationale
[regimen retrofit 20260817] Brad close 2026-07-21: dig-further OOS edge fail; no shadow. KELLY_SIZING_TEST_DIG_2026-07-21 + base report.

## Follow-on
- Mode: `none`
- Detail: No Kelly promote line; sizing research stays gated.

## Notify
- Inbox: `docs/testing/inbox/DECIDED_ANALYST-KELLY-SIZING-TEST-20260721-TRIAL_20260817.md`
- Packet: `docs/testing/decisions/DEC_ANALYST-KELLY-SIZING-TEST-20260721-TRIAL_20260817.md`

## Live boundary
- Config writes this decision: **none**

## Regimen retrofit
- Applied 20260817 under `docs/testing/TEST_REGIMEN_E2E.md`
- Decision enum **unchanged** (`drop`)
- Fields backfilled: success_criteria, outcome, follow_on, packet
