# Door package Option 2 (Brad GO 2026-09-17)

## Goal
Get A-player tryout fills under the same safety shell so promote/graduation
can leave the empty-fill choke. Not auto-promote. Not size up.

## Doors (all three)
1. **LINK doghouse exit (permanent until Brad re-blocks)**  
   Remove `LINK-USD` from static `buy_block_pairs` / `pair_buy_blocklist` in
   `config/trading_config_phase6.json` and `config/regime_cash_policy.json`.
2. **RSI proof window (expires 2026-09-19 21:00 PT)**  
   Tryout `max_rsi` effective **65** while `max_rsi_proof_window` is active.
   Baseline remains **55** after expiry. Code SSOT: tryout sleeve uses
   `quality_tryout.max_rsi` only (no `min()` with regime entry max).
3. **Sensor latch window (same expiry)**  
   After X clears floor, latch TTL **180m** (was 45m) so mid-cycle aged eng
   still seats. Written into `tryout_sent_latch.json` on X refresh.

## Caps unchanged
- `$75` abs tryout cap  
- max **2** new seats/day  
- sent floor **0.30** (tryout B1)  
- full SL + trail attach  
- **no** auto-promote / live membership swaps  

## Thaw
`basket_tryout_thaw` extended to **2026-09-19 21:00 PT** so basket A-names
stay doors under the same caps. Does **not** bypass UNI/RAVE hard block,
missfire, or ugly ledger (SOL stays closed).

## Code touch
- `phase6/core/regime_cash_policy.py` — effective max_rsi / latch TTL helpers;
  tryout max_rsi SSOT (no regime min-cap).
- `phase6/core/recovery_tryout_qualify.py` — load_v2_cfg max_rsi via helper.
- `phase6/core/tryout_sent_latch.py` — TTL from `tryout_sent_latch_ttl_min`.

## Rollback
```text
# After expiry (auto) or early:
# 1) disable max_rsi_proof_window + sensor_latch_window (or wait expires_at)
# 2) optional: basket_tryout_thaw.enabled = false
# 3) LINK stays unblocked unless Brad re-adds buy_block
# 4) rewrite scoreboard + restart runner
```

## Prove (2026-09-17 post-apply)
- buy_block = UNI + RAVE only (no LINK)  
- effective max_rsi = 65, latch TTL = 180  
- X refresh latched LINK ~0.56  
- tryout_readiness: **can_buy=True**, **LINK-USD allowed** (RSI ~57, eng clear)


## Force rebalance 2026-09-17 (~14:32 PT)

**GO executed.** Funnel bugs found and fixed so tryout tickets can reach the executor:

1. `allocator.py`: emergency `min_buy_score` now `>=` (LINK score 0.30 was losing to strict `>`).
2. `first_fill_probation.py`: already-tryout-sized tickets ($75 band) no longer double-haircut into dust (`0.4×75 < 40`).
3. `rsi_primary_deploy.py`: already-tryout-sized tickets skip `sent_only×0.35` dust-drop under min_move $50.

**Live attempt:** LINK-USD BUY $62.50 limit-first post-only (bid, 45s) → `limit_unfilled_skip` (order `a5bbf539-…`, residual cancelled). `market_fallback=False` per 2026-09-09 Brad GO. **No position opened.** NEAR blocked run-phase exhaustion; ADA lost free-cash share after LINK clip.

**Still open for Brad:** one-shot market/IOC tryout to force a filled sample, or accept limit-only and wait for a natural bid touch (incl. 21:00 slot).


## Force fill outcome (2026-09-17 ~14:46 PT)

**FILLED.** Brad GO option 2: limit retry with `price_ref=mid` + `fill_wait_s=120` (was bid/45).

| Field | Value |
|-------|-------|
| pair | LINK-USD |
| size | $75 tryout (full seat) |
| fill | $74.98 / 6.61 @ $11.344 |
| style | limit_post_only mid |
| order_id | `479ce80b-3c6f-4445-92c4-d67f7105283a` |
| SL | attached True (settlement poll OK) |
| pilot | attempts=2 filled=1 unfilled=1 |
| rebalance | Executed=1 Skipped=0 |

Prior miss (14:32): bid + 45s → `limit_unfilled_skip`. Retry filled in ~33s on mid.

**Default knobs locked:** `entry_execution.limit_first.price_ref=mid`, `fill_wait_s=120`. market_fallback still OFF.
