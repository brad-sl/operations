# Stoch rotation / allocator opportunity — offline

**ID:** `STOCH-ROTATION-OPP`  
**Generated:** 2026-09-03T16:00:26.325502+00:00  
**Recommendation:** **no_clear_edge**  
**Plain English:** No clear Stoch missed-opportunity edge on allocator/rotation decisions yet.  

## Window

- Decisions: **186** | native rotation_shadow: **125** (0.672) | with buys: **33**
- Range: `2026-07-21T00:00:00+00:00` → `2026-09-03T16:00:26.147768+00:00`

## Decision-time flags (counts)

- `buy_stoch_oversold`: **17**
- `sell_stoch_overbought`: **6**
- `buy_stoch_overbought`: **4**

## Missed Stoch candidates (event counts)

- missed_stoch_buys: **66**
- missed_stoch_sells: **5**
- RSI mid vs Stoch extreme pair-events: **534**

## Forward 72h: bought vs Stoch alt (when both priced)

- n comparisons: **29**
- stoch alt better: **13**
- mean Δ (alt − bought): **0.003002**

## Gates

- Allocator change: **False**
- Live rotation overlay: **False**

## Notes

- Shadow is log-only; live path stays plain RSI allocator.
- Pre-shadow rows rebuild candidates from indicator_snapshot; holdings may be tilted_plan proxy.
- Forward returns need price_snapshot on decisions — sparse until this deploy ages.
- Trade fill prices available as secondary marks; not used as primary basket marks yet.

## Recent tagged episodes (tail)

- `2026-08-21T18:30:28.670904+00:00` buys=['LINK-USD'] missed=['RAVE-USD', 'ICP-USD', 'XRP-USD'] cmp={'mean_bought': -0.002019, 'mean_stoch_alt': -0.013317, 'delta_alt_minus_bought': -0.011298, 'stoch_alt_better': False}
- `2026-08-23T04:01:18.211596+00:00` buys=['RAVE-USD'] missed=['ARB-USD', 'SOL-USD'] cmp={'mean_bought': -0.008493, 'mean_stoch_alt': 0.004506, 'delta_alt_minus_bought': 0.012999, 'stoch_alt_better': True}
- `2026-08-23T16:01:16.472802+00:00` buys=['UNI-USD', 'BTC-USD'] missed=['XRP-USD', 'DOGE-USD', 'LINK-USD'] cmp={'mean_bought': -0.031836, 'mean_stoch_alt': -0.062701, 'delta_alt_minus_bought': -0.030865, 'stoch_alt_better': False}
- `2026-08-23T18:05:01.900105+00:00` buys=['UNI-USD'] missed=['ARB-USD', 'RAVE-USD', 'BTC-USD'] cmp={'mean_bought': -0.07414, 'mean_stoch_alt': -0.05073, 'delta_alt_minus_bought': 0.02341, 'stoch_alt_better': True}
- `2026-08-24T16:00:50.858509+00:00` buys=['LINK-USD'] missed=['ETH-USD', 'UNI-USD'] cmp={'mean_bought': 0.029143, 'mean_stoch_alt': 0.029674, 'delta_alt_minus_bought': 0.000532, 'stoch_alt_better': True}
- `2026-08-28T04:03:24.928715+00:00` buys=['ICP-USD'] missed=['BTC-USD', 'ETH-USD', 'LINK-USD'] cmp={'mean_bought': -0.019847, 'mean_stoch_alt': -0.033655, 'delta_alt_minus_bought': -0.013808, 'stoch_alt_better': False}
- `2026-08-29T04:01:06.583149+00:00` buys=['ICP-USD'] missed=['BTC-USD', 'ETH-USD', 'DOGE-USD'] cmp={'mean_bought': -0.002599, 'mean_stoch_alt': 0.003773, 'delta_alt_minus_bought': 0.006372, 'stoch_alt_better': True}
- `2026-09-01T21:51:20.773138+00:00` buys=['LINK-USD'] missed=['ICP-USD'] cmp={'mean_bought': 0.002281, 'mean_stoch_alt': 0.003849, 'delta_alt_minus_bought': 0.001568, 'stoch_alt_better': True}
