# Handoff: CW-3 Threshold surgery evidence packet

**Epic:** `REGIME-CLIMATE-WEATHER-REMAINING-20260921`  
**Card:** CW-3 · P1 evidence (parents: CW-1)  
**Assignee:** crypto-analyst  
**Plan:** `docs/plans/2026-09-21-climate-weather-remaining-four.md`

## Goal
Evidence-only sweep of climate band alternatives (−10 / ±8 / +15 family). Recommend keep vs scoped shadow. **Never write live detector thresholds on this card.**

## Depends on
- **CW-1 done** (honest OHLCV) — do not sweep on gapped tape
- Climate/weather crumbs useful but not hard-block if long tape is clean

## Must do
1. Offline grid on long BTC tape: bear ∈ {−12,−10,−8}, flat half-width ∈ {6,8,10}, bull ∈ {12,15,18} (prune if too large; document chosen grid).
2. Metrics per grid point: dwell mean/med/p90, flip rate, forward 5/10/30d under park baseline; optional tag “would B micro” from layered rules as counterfactual column only.
3. Report: `reports/REGIME_THRESHOLD_SWEEP_LATEST.md` + json
4. Decision-shaped packet: enum `keep` | `propose_scoped_shadow_only` | `inconclusive_N` with `live_promote_allowed: false`
5. Inbox-style summary for Brad — no auto decide

## Must not
- Patch `config/regime_cash_policy.json`
- Claim live edge from one green week
- Promote B or open buys

## Done when
- Report + packet on disk; MASTER notes REVIEW; Kanban complete

## Skills
`regime-premise-and-basket`, `offline-strategy-honesty`, `analyst-test-strategy` (packet hygiene)
