# Basket swap — winner-picking confidence board
As of `2026-09-03T18:30:25.521702+00:00`

## Plain English

Brad preferred paper arm: **risk_adj_mom** (not live membership). dual_agree continues through revisit 2026-09-28. High-confidence arm(s) present: ['anti_pump', 'rel_btc_stable', 'risk_adj_mom']. Still not live — Brad review required before any promote.

## Brad preferred arm (paper only)

- **Preferred:** `risk_adj_mom`
- **Live membership swaps:** **NO**
- **Revisit:** 2026-09-28
- Decision file: `/home/brad/projects/crypto-trading-bot/data/state/basket_swap_brad_decision.json`
- Write-up: `reports/BASKET_SWAP_BRAD_GO_2026-08-29.md`

## Decision point (when we stop saying “keep collecting”)

**Promote-to-Brad-review (still not live)** when **any arm** hits all of:

1. **7d N ≥ 12** matured ADD-vs-REMOVE swaps
2. **7d mean excess > 0%** (add beats remove on average)
3. **7d hit rate ≥ 45%**
4. **Paper sleeve $ to-now > $0** vs stay-on-remove

**Modify / drop arm family** when 7d N ≥ 12 **and** mean excess < 0 **and** hit < 45% (or sleeve deeply negative).

**Statistical significance:** we do **not** claim p-values yet. At thin 7d N, a t-test is underpowered. Operational bar above is the decision point.

**Any arm high-confidence right now?** **YES**

## Scoreboard (from current CF)

| Arm | 1d | 3d | 7d | Sleeve Δ$ | HC? | Missing |
|-----|----|----|----|-----------|-----|---------|
| `risk_adj_mom` | N=29 -0.17% hit=44% | N=27 +2.62% hit=51% | N=24 +14.59% hit=66% | $+593.08 | yes | — |
| `anti_pump` | N=27 -0.26% hit=33% | N=25 +4.18% hit=52% | N=23 +11.74% hit=52% | $+394.67 | yes | — |
| `rel_btc_stable` | N=35 -0.18% hit=42% | N=31 +0.55% hit=54% | N=25 +6.44% hit=48% | $+153.67 | yes | — |
| `dual_agree` | N=12 -1.81% hit=25% | N=10 +1.62% hit=50% | N=10 +11.23% hit=60% | $+163.19 | no | n7 |
| `baseline_hybrid` | N=38 -0.29% hit=42% | N=35 +11.45% hit=42% | N=27 -0.05% hit=40% | $+67.87 | no | ex7,hit7 |

## Read of current tape

- **`risk_adj_mom`:** 3d excess +2.62% (N=27); sleeve $+593; 7d N=24 → missing none.
- **`anti_pump`:** 3d excess +4.18% (N=25); sleeve $+395; 7d N=23 → missing none.
- **`rel_btc_stable`:** 3d excess +0.55% (N=31); sleeve $+154; 7d N=25 → missing none.
- **`dual_agree`:** 3d excess +1.62% (N=10); sleeve $+163; 7d N=10 → missing ['n7'].
- **`baseline_hybrid`:** 3d excess +11.45% (N=35); sleeve $+68; 7d N=27 → missing ['ex7', 'hit7'].

Bottom line: Brad paper-primary = `risk_adj_mom`. Continue dual_agree + CF collection through 2026-09-28. **No live basket swaps** until explicit promote of a specific swap.

Co-leader dual-agree log: `/home/brad/projects/crypto-trading-bot/data/state/basket_select_arms/dual_agree/proposals.jsonl` (arms: anti_pump, risk_adj_mom).

CF: `reports/BASKET_SWAP_SHADOW_CF_LATEST.md`
JSON: `data/state/basket_swap_confidence_board_latest.json`

