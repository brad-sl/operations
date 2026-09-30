# NEEDLE-09: Fee / venue — research only (no switch)

**Date:** 2026-09-30  
**Place orders:** no. **Venue switch:** no. **Volume grind:** no.

## Live tier (Coinbase snapshot)

From `data/state/fee_tier_snapshot_latest.json` (2026-09-30T01:20Z):

| | |
|---|---|
| Pricing tier | **Intro** |
| Taker / maker | **0.90% / 0.50%** |
| 30d-ish volume (API) | ~$2,161 |
| Fees paid (API) | ~$15.19 |
| Next tier | Advanced 1 @ 0.75% / 0.35% |
| Threshold | **$10,000** volume |

`config_loader` COINBASE_* constants (0.40% / 0.25%) are **stale**. Prefer the snapshot.

## Last 30d ledger (`trades/phase6_trades.jsonl`)

74 fills in the window (includes USDT hops for USDC convert):

| Type | N | Notional (qty × price) |
|---|---|---|
| LIMIT | 28 | ~$4,286 |
| MARKET | 28 | ~$4,466 |
| STOP_LIMIT | 4 | ~$204 |
| UNKNOWN | 14 | ~$500 |
| **Total** | **74** | **~$9,456** |

Fee field is not stored on jsonl rows. **Estimate** at live rates (LIMIT = maker 50 bps, else taker 90 bps): **~$68**. That overstates true P&amp;L drag because USDT two-hop convert prints as extra LIMIT/MARKET notional.

Lifetime shape still matters more than this window: **82 SL vs 4 TP** under the old 3% geometry + taker exits.

## Path off Intro 0.9% (non-churn)

1. **Stay Coinbase. Maker-only entries** (`limit_first`, post-only). This is the intended path. Market rotation sells and stop-triggers still pay taker — that is why NEEDLE-04 widened stops to 8% instead of farming volume.
2. **Do not grind ~$8k extra volume** to reach Advanced 1. At 0.9% taker, farming $8k costs ~$72 in fees to maybe save 15 bps later. Negative EV vs the $2.3k book.
3. **Do not switch venues** for tryouts. A second venue is a new custody + fill + SL stack; not a fee tweak.
4. Native USDC Convert is **403** on this consumer portfolio — USDT hop is a fee tax on park/unwind, not a reason to leave Coinbase.

## Recommendation

Stay Coinbase Intro. Maker entries, structure 8% stops, capped USDC hops only when a door needs powder. Revisit Advanced 1 only if organic volume crosses ~$10k without a grind program.

**Do not churn for tier.**
