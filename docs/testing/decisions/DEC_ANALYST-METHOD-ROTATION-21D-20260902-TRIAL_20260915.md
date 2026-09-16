# Decision packet — ANALYST-METHOD-ROTATION-21D-20260902-TRIAL

| Field | Value |
|-------|--------|
| Trial | `ANALYST-METHOD-ROTATION-21D-20260902-TRIAL` |
| Family | `method_rotation_21d` |
| Decided at (UTC) | 2026-09-15T19:01:58.921109+00:00 |
| By | brad |
| Enum | `continue_observe_only` |
| CR | **NO_CR** |
| Follow-on | `none` |
| Regimen | `docs/testing/TEST_REGIMEN_E2E.md` |

## Design (summary)
- Hypothesis: QUEUED (strategy)
- Primary window: `fresh_opt_window`
- Success bar (frozen): min_n=15; beat ret+dd=True

## Outcome (measured)
- Primary pass: **False**
- Class: `inconclusive_sparse_N`
- N (primary): 14
- Δret vs baseline (pp): 18.03
- ΔDD vs baseline (pp): -0.83
- Report: `reports/METHOD_ROTATION_21D_TEST_2026-09-02.md`
- Plain English: NO GO shadow/promote. Fresh 21d rotation +19.25% ret n=14 vs idle control +1.22%; fails min_n=15 and DD gate; full-tape red -22.58%. continue_observe_only.

## Decision rationale
sparse n=14; failed DD+stability; no shadow/promote

## Follow-on
- Mode: `none`
- Detail: —

## Notify
- Inbox: `docs/testing/inbox/DECIDED_ANALYST-METHOD-ROTATION-21D-20260902-TRIAL_20260915.md`
- Packet: `docs/testing/decisions/DEC_ANALYST-METHOD-ROTATION-21D-20260902-TRIAL_20260915.md`

## Live boundary
- Config writes this decision: **none**
