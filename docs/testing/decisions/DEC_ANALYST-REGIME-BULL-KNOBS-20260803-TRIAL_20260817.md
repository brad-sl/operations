# Decision packet — ANALYST-REGIME-BULL-KNOBS-20260803-TRIAL

| Field | Value |
|-------|--------|
| Trial | `ANALYST-REGIME-BULL-KNOBS-20260803-TRIAL` |
| Family | `regime_bull_knobs` |
| Decided at (UTC) | 2026-08-17T18:56:16.196007+00:00 |
| By | brad |
| Enum | `abort` |
| CR | **REJECT** |
| Follow-on | `extend` |
| Regimen | `docs/testing/TEST_REGIMEN_E2E.md` |

## Design (summary)
- Hypothesis: Bull live knobs under-deploy or over-trade vs scorecard winner
- Primary window: `bull_windows`
- Success bar (frozen): min_n=15; beat ret+dd=True

## Outcome (measured)
- Primary pass: **False**
- Class: `process_incomplete`
- N (primary): —
- Δret vs baseline (pp): —
- ΔDD vs baseline (pp): —
- Report: `—`
- Plain English: No dig landed (reports=[]). Abort frees slot. Real bull test is PLAN-BULL-KNOBS-002.

## Decision rationale
[regimen retrofit 20260817] Zombie close 2026-08-17: execute cron 7d76d0b4123b never produced reports (reports=[]). Abort frees offline slot. NOT a market drop — re-emit PLAN-BULL-KNOBS when live regime=bull (BTC 30d ≥ +15% or detector bull). Until then layered bull re-entry stays paper-only; no live regime_cash_policy writes.

## Follow-on
- Mode: `extend`
- Detail: PLAN-BULL-KNOBS-002 planned; emit_only_when_regime=bull

## Notify
- Inbox: `docs/testing/inbox/DECIDED_ANALYST-REGIME-BULL-KNOBS-20260803-TRIAL_20260817.md`
- Packet: `docs/testing/decisions/DEC_ANALYST-REGIME-BULL-KNOBS-20260803-TRIAL_20260817.md`

## Live boundary
- Config writes this decision: **none**

## Regimen retrofit
- Applied 20260817 under `docs/testing/TEST_REGIMEN_E2E.md`
- Decision enum **unchanged** (`abort`)
- Fields backfilled: success_criteria, outcome, follow_on, packet
- Successor real test: `PLAN-BULL-KNOBS-002` (not closed as placeholder)
