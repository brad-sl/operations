# Limit-first fill evidence (PC-05)

**As of:** 2026-09-12T04:39:40.325664+00:00
**Schema:** `limit_first_evidence_v1`

## Policy (must not enable market fallback without Brad GO)

- mode=`limit_first_v1` enabled=`True` post_only=`True`
- market_fallback=`False` max_usd=**0.0**
- pilot caps: buys/day=3 usd/day=300

## Counters (honest zeros OK)

- Limit attempts: **7**
- Filled: **5** · Unfilled: **2** · Errors: **0**
- Fill rate: **71%**
- Market fallback events: **1** (expect 0 while max_usd=0)
- USD attempted / filled: **$500.00** / **$373.64**
- First/last attempt: `2026-08-31T19:39:54.533914+00:00` → `2026-09-09T16:01:42.364313+00:00`

## Drought / denominator honesty

- Drought flag: **False**
- Days since last attempt: **2.53**
- Promote-talk bar (≥30 attempts): **False**
- Reasons: ok_collecting
- PC-03 link can_buy: `None`

## Fee tier (context only)

- maker=None taker=None tier=`{'pricing_tier': 'Intro 2', 'taker_fee_rate': 0.008, 'maker_fee_rate': 0.004, 'taker_fee_pct': 0.8, 'maker_fee_pct': 0.4, 'total_volume': 16647.22002934524, 'total_fees': 136.7660380947613, 'next_pricing_tier': 'Advanced 1', 'next_taker_fee_rate': 0.005, 'next_maker_fee_rate': 0.0025, 'next_tier_threshold': '25000', 'config_loader_maker_constant': 0.0025, 'config_loader_taker_constant': 0.004, 'config_loader_stale': True, 'note': 'Prefer these live rates over config_loader COINBASE_* constants'}`

## Shadow CF note

- shadow feeΔ upper-bound only (n_buys=8); not realized maker savings until pilot attempts accumulate.

State: `data/state/limit_first_evidence_latest.json`
