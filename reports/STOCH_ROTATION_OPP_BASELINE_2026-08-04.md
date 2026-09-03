# Stoch rotation / allocator opportunity — offline

**ID:** `STOCH-ROTATION-OPP`  
**Generated:** 2026-08-04T20:07:44.233882+00:00  
**Recommendation:** **extend_collect**  
**Plain English:** Not enough forward-priced missed-buy comparisons yet. Keep logging rotation_shadow + price_snapshot on each rebalance.  

## Window

- Decisions: **57** | native rotation_shadow: **0** (0.0) | with buys: **8**
- Range: `2026-07-21T00:00:00+00:00` → `2026-08-04T20:07:44.210691+00:00`

## Decision-time flags (counts)

- `buy_stoch_oversold`: **4**
- `sell_stoch_overbought`: **2**
- `buy_stoch_overbought`: **1**

## Missed Stoch candidates (event counts)

- missed_stoch_buys: **13**
- missed_stoch_sells: **3**
- RSI mid vs Stoch extreme pair-events: **151**

## Forward 72h: bought vs Stoch alt (when both priced)

- n comparisons: **0**
- stoch alt better: **0**
- mean Δ (alt − bought): **None**

## Gates

- Allocator change: **False**
- Live rotation overlay: **False**

## Notes

- Shadow is log-only; live path stays plain RSI allocator.
- Pre-shadow rows rebuild candidates from indicator_snapshot; holdings may be tilted_plan proxy.
- Forward returns need price_snapshot on decisions — sparse until this deploy ages.
- Trade fill prices available as secondary marks; not used as primary basket marks yet.

## Recent tagged episodes (tail)

- `2026-07-23T04:01:21.311386+00:00` buys=['SOL-USD'] missed=['ETH-USD', 'XRP-USD', 'DOGE-USD'] cmp=None
- `2026-08-02T16:01:54.607252+00:00` buys=['BTC-USD'] missed=['OP-USD', 'LINK-USD'] cmp=None
- `2026-08-02T16:06:43.403173+00:00` buys=['BTC-USD'] missed=['OP-USD', 'LINK-USD'] cmp=None
- `2026-08-03T04:01:32.489871+00:00` buys=['BTC-USD'] missed=['ETH-USD', 'SOL-USD'] cmp=None
- `2026-08-03T04:06:32.918927+00:00` buys=['BTC-USD'] missed=['ETH-USD', 'SOL-USD'] cmp=None
- `2026-08-04T04:01:11.476867+00:00` buys=['LINK-USD'] missed=['UNI-USD', 'OP-USD'] cmp=None
