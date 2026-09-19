# Decision packet — ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902

| Field | Value |
|-------|--------|
| Trial | `ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902` |
| Family | `polymarket_influence` |
| Decided at (UTC) | 2026-09-19T18:02:12.086035+00:00 |
| By | brad |
| Enum | `extend_trial` |
| CR | **NO_CR** |
| Follow-on | `extend` |
| Regimen | `docs/testing/TEST_REGIMEN_E2E.md` |

## Design (summary)
- Hypothesis: Post-fix Polymarket risk_on_bias has real range and joined sells show measurable bucket lift (observe-only bar).
- Primary window: `post_fix_collect`
- Success bar (frozen): min_n=15; beat ret+dd=True

## Outcome (measured)
- Primary pass: **False**
- Class: `inconclusive_sparse_N`
- N (primary): 10
- Δret vs baseline (pp): None
- ΔDD vs baseline (pp): None
- Report: `reports/POLYMARKET_INFLUENCE_RERUN_FINAL_20260919.md`
- Plain English: Sensor OK post-fix (52 stamps, range real). Edge unproven: crypto joined n=10 all LINK, risk_on n=0; no live promote.

## Decision rationale
Brad 2026-09-19: lack of trades makes window incomplete for edge relevance. Sensor OK but crypto n=10 / risk_on n=0. Extend collect until crypto-N and bucket coverage clear relevance bar (or hard stop). No live promote.

## Follow-on
- Mode: `extend`
- Detail: child ANALYST-POLYMARKET-INFLUENCE-EXT-20260919; gates: crypto_joined>=15 OR (risk_on_n>=5 AND neutral_n>=5); hard_stop final_at +21d; ex-stable sells only for edge; live_promote=false

## Notify
- Inbox: `docs/testing/inbox/DECIDED_ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902_20260919.md`
- Packet: `docs/testing/decisions/DEC_ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902_20260919.md`

## Live boundary
- Config writes this decision: **none**
