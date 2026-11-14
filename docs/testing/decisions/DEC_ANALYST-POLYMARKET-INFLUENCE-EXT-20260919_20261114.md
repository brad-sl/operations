# Decision packet — ANALYST-POLYMARKET-INFLUENCE-EXT-20260919

| Field | Value |
|-------|--------|
| Trial | `ANALYST-POLYMARKET-INFLUENCE-EXT-20260919` |
| Family | `polymarket_influence` |
| Decided at (UTC) | 2026-11-14T01:55:37.899860+00:00 |
| By | brad |
| Enum | `drop` |
| CR | **REJECT** |
| Follow-on | `none` |
| Regimen | `docs/testing/TEST_REGIMEN_E2E.md` |

## Design (summary)
- Hypothesis: With longer post-fix collect + ex-stable sells only, risk_on vs neutral bias buckets show measurable mean-PnL lift OR we honestly drop for sparse forever.
- Primary window: `extend_collect_until_relevance`
- Success bar (frozen): min_n=15; beat ret+dd=True

## Outcome (measured)
- Primary pass: **False**
- Class: `unstable_or_no_edge`
- N (primary): 59
- Δret vs baseline (pp): None
- ΔDD vs baseline (pp): None
- Report: `reports/POLYMARKET_INFLUENCE_EXT_20260919.md`
- Plain English: Hard stop long past (final_at 2026-10-10). Fresh 2026-11-13 re-run: sensor OK, relevance cleared (crypto_joined=59, risk_on_n=6, neutral_n=41). Edge SSOT crypto buckets all lose money; risk_on mean_pnl − neutral ≈ +0.01 with risk_on WR=0. No lift bar for promote. Recommend drop; no live knobs.

## Decision rationale
Brad GO drop 2026-11-13. Hard stop long past; fresh extend re-run: sensor OK, relevance cleared (crypto 59 / risk_on 6 / neutral 41), edge SSOT buckets all lose (risk_on WR 0, lift ~+0.01 noise). unstable_or_no_edge. No live promote. No knobs.

## Follow-on
- Mode: `none`
- Detail: —

## Notify
- Inbox: `docs/testing/inbox/DECIDED_ANALYST-POLYMARKET-INFLUENCE-EXT-20260919_20261114.md`
- Packet: `docs/testing/decisions/DEC_ANALYST-POLYMARKET-INFLUENCE-EXT-20260919_20261114.md`

## Live boundary
- Config writes this decision: **none**
