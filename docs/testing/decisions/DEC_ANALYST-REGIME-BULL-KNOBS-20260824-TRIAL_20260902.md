# Decision packet — ANALYST-REGIME-BULL-KNOBS-20260824-TRIAL

| Field | Value |
|-------|--------|
| Trial | `ANALYST-REGIME-BULL-KNOBS-20260824-TRIAL` |
| Family | `regime_bull_knobs` |
| Decided at (UTC) | 2026-09-02T18:38:45.508837+00:00 |
| By | brad |
| Enum | `abort` |
| CR | **REJECT** |
| Follow-on | `none` |
| Regimen | `docs/testing/TEST_REGIMEN_E2E.md` |

## Design (summary)
- Hypothesis: QUEUED (strategy)
- Primary window: `unspecified_legacy`
- Success bar (frozen): min_n=15; beat ret+dd=True

## Outcome (measured)
- Primary pass: **False**
- Class: `process_incomplete`
- N (primary): 0
- Δret vs baseline (pp): None
- ΔDD vs baseline (pp): None
- Report: `reports/REGIME_BULL_KNOBS_20260824_PROCESS_INCOMPLETE.md`
- Plain English: Zombie RUNNING: no offline arms executed; process incomplete. Free capacity. Not an edge reject.

## Decision rationale
Brad GO full-stack 2026-09-02: process incomplete zombie; free offline capacity. PLAN-BULL-KNOBS-002 stays parked for live bull.

## Follow-on
- Mode: `none`
- Detail: —

## Notify
- Inbox: `docs/testing/inbox/DECIDED_ANALYST-REGIME-BULL-KNOBS-20260824-TRIAL_20260902.md`
- Packet: `docs/testing/decisions/DEC_ANALYST-REGIME-BULL-KNOBS-20260824-TRIAL_20260902.md`

## Live boundary
- Config writes this decision: **none**
