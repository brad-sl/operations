# Decision packet — TEST-SR-STRUCTURE-ENTRY-SHADOW-20260815

| Field | Value |
|-------|--------|
| Trial | `TEST-SR-STRUCTURE-ENTRY-SHADOW-20260815` |
| Family | `market_structure_sr` |
| Decided at (UTC) | 2026-08-17T19:22:00.974804+00:00 |
| By | brad |
| Enum | `drop` |
| CR | **REJECT** |
| Follow-on | `none` |
| Regimen | `docs/testing/TEST_REGIMEN_E2E.md` |

## Design (summary)
- Hypothesis: S/R bounce and break+retest as separate structure arms under REGIME-CASH allow
- Primary window: `long_tape`
- Success bar (frozen): min_n=15; beat ret+dd=True

## Outcome (measured)
- Primary pass: **False**
- Class: `unstable_or_no_edge`
- N (primary): 283
- Δret vs baseline (pp): 9.6
- ΔDD vs baseline (pp): None
- Report: `reports/SR_STRUCTURE_ENTRY_SHADOW_20260815.md`
- Plain English: Best arm SR_BREAK_RSI only less-loss vs BASE on long_tape; bounce no_go; short windows sparse. Does not clear ret+DD promote bar.

## Decision rationale
CR REJECT. Primary long_tape: no structure arm beats BASE on ret AND DD with N≥15 promote path. SR_BREAK_RSI less-loss only (unstable_or_no_edge). Bounce arms no_go. Process debt same as FIB — reconstructed design at decide. Real reject, not empty test.

## Follow-on
- Mode: `none`
- Detail: No S/R entry promote line; reopen only with full PROTOCOL_OFFLINE + WF.

## Notify
- Inbox: `docs/testing/inbox/DECIDED_TEST-SR-STRUCTURE-ENTRY-SHADOW-20260815_20260817.md`
- Packet: `docs/testing/decisions/DEC_TEST-SR-STRUCTURE-ENTRY-SHADOW-20260815_20260817.md`

## Live boundary
- Config writes this decision: **none**
