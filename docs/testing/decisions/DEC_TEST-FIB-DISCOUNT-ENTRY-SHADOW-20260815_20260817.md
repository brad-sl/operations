# Decision packet — TEST-FIB-DISCOUNT-ENTRY-SHADOW-20260815

| Field | Value |
|-------|--------|
| Trial | `TEST-FIB-DISCOUNT-ENTRY-SHADOW-20260815` |
| Family | `fib_discount_entry` |
| Decided at (UTC) | 2026-08-17T19:22:00.892187+00:00 |
| By | brad |
| Enum | `drop` |
| CR | **REJECT** |
| Follow-on | `none` |
| Regimen | `docs/testing/TEST_REGIMEN_E2E.md` |

## Design (summary)
- Hypothesis: Fib discount as add-on to regime+RSI, not RSI replacement
- Primary window: `long_tape`
- Success bar (frozen): min_n=15; beat ret+dd=True

## Outcome (measured)
- Primary pass: **False**
- Class: `unstable_or_no_edge`
- N (primary): 504
- Δret vs baseline (pp): -7.98
- ΔDD vs baseline (pp): -1.12
- Report: `reports/FIB_DISCOUNT_ENTRY_SHADOW_20260815.md`
- Plain English: Long-tape Fib AND worse than RSI-only BASE (~-8pp ret). Short windows sparse/bags-only. Reject promote.

## Decision rationale
CR REJECT. Primary long_tape: RSI_FIB_AND vs BASE Δret -7.98pp ΔDD -1.12pp (class unstable_or_no_edge, N=504). Report enum drop matches. Process debt: launched without protocol/success_criteria on trial JSON; reconstructed at decide. Not sparse-no-data — real reject.

## Follow-on
- Mode: `none`
- Detail: No fib entry refine until new protocol with frozen bar + WF; memory: fib shadow drop 20260815.

## Notify
- Inbox: `docs/testing/inbox/DECIDED_TEST-FIB-DISCOUNT-ENTRY-SHADOW-20260815_20260817.md`
- Packet: `docs/testing/decisions/DEC_TEST-FIB-DISCOUNT-ENTRY-SHADOW-20260815_20260817.md`

## Live boundary
- Config writes this decision: **none**
