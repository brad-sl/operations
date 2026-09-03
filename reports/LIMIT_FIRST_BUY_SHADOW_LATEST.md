# Limit-first buy shadow (Phase C)

**As of:** 2026-09-03T18:40:10.809991+00:00  
**Live gate:** OFF  
**place_orders:** False  

## Honesty

- This is a **counterfactual upper bound** on buy-leg fee if every market buy
  had instead **rested and filled as maker**.
- **Fill rate at post_only bid is unknown** until Phase D pilot.
- Not alpha. Not a money printer. Cost-cut engineering only.
- Edge class: `ATTENTION_ONLY_cost_cut`

## Fee tier

- Tier: **Intro 2** (source=fee_tier_snapshot)
- Taker 0.008 / Maker 0.004

## Lookback 72h market buys

- N buys: **2**
- Notional: **$484.5**
- Actual fees (used/imputed): **$3.876**
- Maker if rested: **$1.938**
- **Fee Δ upper bound: $1.938** (avg $0.969/buy)

Do **not** read Δ as money already saved.

State: `data/state/limit_first_buy_shadow_latest.json`  
Events: `data/state/limit_first_buy_shadow_events.jsonl`
