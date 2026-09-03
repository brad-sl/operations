# Fills / MARKET path dig

**As of:** 2026-08-31T17:29:51.774110+00:00  
**NAV snapshot:** None  
**Mode:** read-only · **no live order/config changes**

## Plain English

**GO/NO-GO live maker path:** `NO — do not wire live maker without design + shadow + Brad GO`  
**Why MARKET-only:** OrderExecutor and ExchangeClient only implement market IOC for entries/exits; config hardcodes order_type=market; no place_limit_buy on live client. Not a fill-label bug.  
**Fee read:** Live tier **Intro 2**: taker **0.8%** / maker **0.4%**. Realized median **0.8% = taker**. `config_loader` 0.25/0.40 is **stale** (closer to next tier Advanced 1). Round-trip taker/taker ≈ **1.6%**.

### Bottom line

MARKET-only is intentional code path, not a bug. Account is Intro 2 (0.8% taker). No `place_limit_buy` on live client — maker path = new eng. Even maker entries only cut buy leg 0.8→0.4; exits still taker. Do not churn volume just to reach Advanced 1. Highest EV: fewer round-trips + C stand-down; maker is gated design work, **not a money printer**.


## Live fee tier (API ground truth)

- **Tier:** `Intro 2`
- **Taker:** **0.8%** · **Maker:** **0.4%**
- **~30d volume (API):** $20,332
- **Next:** `Advanced 1` at $25000 → taker 0.5% / maker 0.25%
- **Realized median fee 0.8% = live taker** (not a mystery 2× overcharge)
- **config_loader 0.25%/0.40%:** stale vs this account

### Maker savings upper bound (30d buys only)

- BUY fees 30d: $79.73
- If all those buys had been maker @0.4%: save ~**$39.86** (fantasy ceiling)
- Full book still pays taker on SL/market exits

### Volume-tier chase?

- Scaling all 30d fees to Adv1 taker 0.5% ≈ save ~**$52.08** — but **paying 0.8% to grind volume is usually negative EV**. Not recommended.

## Code path (source of truth)

- **BUY:** `OrderExecutor.execute_buy → exchange.place_market_buy → market_market_ioc (quote_size)`
- **SELL:** `OrderExecutor.execute_sell → protected_market_exit → place_market_sell → market_market_ioc (base_size)`
- **Config order_type:** hardcoded `config_loader.get_config → order_type="market" (not read from JSON)`
- **exchange_client place_* methods:** `['place_market_buy', 'place_buy_with_bracket', 'place_stop_limit_sell', 'place_market_sell']`
- **place_limit_buy on live ExchangeClient?** `False`
- **Legacy place_limit_buy exists off-path?** `True`
- **TP attach can be LIMIT post_only?** `True` (protective exit, not entry)
- **Implication:** MARKET-only on verified entry/exit path is by design of current Phase6 executor, not a mysterious regression of a live maker path. Legacy place_limit_buy lives outside phase6/core/exchange_client.py and is not called by OrderExecutor.

## Realized fills

### 30d

- n=54 · fees=$138.8867 · notional=$16765.82 · fee/notional=0.8284%
- fee_pct median/p25/p75/mean: 0.8 / 0.8 / 0.8 / 0.8118
- order_types: `[('MARKET', 41), ('STOP_LIMIT', 13)]`
- liq class: `[('taker_market', 41), ('taker_stop', 13)]`
- LIMIT (non-stop) count: **0**
- BUY fee median %: 0.8 · SELL fee median %: 0.8
- fees by side: `{'SELL': 59.1581, 'BUY': 79.7286}`
- top reasons: `[('rebalance_buy', 35), ('stop_loss_exchange', 13), ('rotation_exchange', 6)]`

### 90d

- n=175 · fees=$217.9019 · notional=$25452.14 · fee/notional=0.8561%
- fee_pct median: 0.8 · order_types: `[('MARKET', 95), ('STOP_LIMIT', 80)]` · LIMIT count: **0**

### Top fee samples (30d)

- 2026-08-16T16:01:01.024352+00:00 **BTC-USD** SELL MARKET notional=$1994.46 fee=$15.9556 (0.8%) · rotation_exchange
- 2026-08-24T16:00:30.828124+00:00 **LINK-USD** BUY MARKET notional=$1909.87 fee=$15.2789 (0.8%) · rebalance_buy
- 2026-08-21T18:30:08.645804+00:00 **LINK-USD** BUY MARKET notional=$1016.25 fee=$12.195 (1.2%) · rebalance_buy
- 2026-08-01T18:31:10.228469+00:00 **LINK-USD** SELL STOP_LIMIT notional=$1132.74 fee=$9.0619 (0.8%) · stop_loss_exchange
- 2026-08-25T20:47:30.828514+00:00 **LINK-USD** SELL STOP_LIMIT notional=$1023.03 fee=$8.1842 (0.8%) · stop_loss_exchange
- 2026-08-23T18:04:41.899120+00:00 **UNI-USD** BUY MARKET notional=$973.55 fee=$7.7884 (0.8%) · rebalance_buy
- 2026-08-24T00:45:11.274322+00:00 **UNI-USD** SELL STOP_LIMIT notional=$932.44 fee=$7.4595 (0.8%) · stop_loss_exchange
- 2026-08-04T04:00:51.417814+00:00 **LINK-USD** BUY MARKET notional=$631.86 fee=$5.0549 (0.8%) · rebalance_buy

## Fee tier gap

- config constants: maker **0.25%** / taker **0.40%** (config_loader; may be stale vs account)
- gap block: `{"realized_median_fee_pct": 0.8, "vs_config_taker_0_40": 0.4, "vs_config_maker_0_25": 0.55, "round_trip_taker_taker_est_pct": 1.6, "round_trip_if_maker_entry_taker_exit_est": 1.05, "note": "If median ~0.8% is true all-in commission/notional, it is ABOVE config_loader's 0.40% taker constant \u2014 either tier is worse than assumed, fee field includes extra, or notional denominator is partial. Live transaction_summary is ground truth."}`
- maker-buy savings upper bound (fantasy): `{'assumption': '30d BUY fees scaled by (realized_med - 0.25%)/realized_med if all buys were maker @0.25%', 'buy_fees_30d': 79.7286, 'hypothetical_save_usd': 54.81, 'caveat': 'Ignores unfilled limits, adverse selection, delayed entry; upper-bound fantasy not a plan'}`
- live tier probe ok=True fee_related=`{'total_volume': 20332.19713527856, 'total_fees': 167.4446588022281, 'fee_tier': {'pricing_tier': 'Intro 2', 'usd_from': '', 'usd_to': '', 'taker_fee_rate': '0.008', 'maker_fee_rate': '0.004', 'aop_from': '1000000', 'aop_to': '5000000', 'perps_vol_from': '', 'perps_vol_to': '', 'futures_vol_from': '', 'futures_vol_to': '', 'volume_types_and_range': [{'volume_types': ['VOLUME_TYPE_SPOT', 'VOLUME_TYPE_US_DERIVATIVES'], 'vol_from': '10000', 'vol_to': '25000'}]}, 'margin_rate': None, 'advanced_trade_only_volume': 20332.19713527856, 'advanced_trade_only_fees': 167.4446588022281, 'coinbase_pro_volume': 0, 'coinbase_pro_fees': 0, 'has_promo_fee': False, 'volume_breakdown': [{'volume_type': 'VOLUME_TYPE_SPOT', 'volume': 20332.19713527856}, {'volume_type': 'VOLUME_TYPE_US_DERIVATIVES', 'volume': 0}], 'fee_tier_without_promotion': {'pricing_tier': '', 'qualification_type': 'FEE_TIER_QUALIFICATION_TYPE_COMBINED_VOLUME', 'current_value': '20332.19713527856', 'next_tier_threshold': '25000', 'current_tier': {'pricing_tier': 'Intro 2', 'usd_from': '', 'usd_to': '', 'taker_fee_rate': '0.008', 'maker_fee_rate': '0.004', 'aop_from': '1000000', 'aop_to': '5000000', 'perps_vol_from': '', 'perps_vol_to': '', 'futures_vol_from': '', 'futures_vol_to': '', 'volume_types_and_range': [{'volume_types': ['VOLUME_TYPE_SPOT', 'VOLUME_TYPE_US_DERIVATIVES'], 'vol_from': '10000', 'vol_to': '25000'}]}, 'next_tier': {'pricing_tier': 'Advanced 1', 'usd_from': '', 'usd_to': '', 'taker_fee_rate': '0.005', 'maker_fee_rate': '0.0025', 'aop_from': '5000000', 'aop_to': '15000000', 'perps_vol_from': '', 'perps_vol_to': '', 'futures_vol_from': '', 'futures_vol_to': '', 'volume_types_and_range': [{'volume_types': ['VOLUME_TYPE_SPOT', 'VOLUME_TYPE_US_DERIVATIVES'], 'vol_from': '25000', 'vol_to': '75000'}]}, 'current_tier_threshold': '10000'}, 'next_fee_tier': {'pricing_tier': 'Advanced 1', 'usd_from': '', 'usd_to': '', 'taker_fee_rate': '0.005', 'maker_fee_rate': '0.0025', 'aop_from': '5000000', 'aop_to': '15000000', 'perps_vol_from': '', 'perps_vol_to': '', 'futures_vol_from': '', 'futures_vol_to': '', 'volume_types_and_range': [{'volume_types': ['VOLUME_TYPE_SPOT', 'VOLUME_TYPE_US_DERIVATIVES'], 'vol_from': '25000', 'vol_to': '75000'}]}, 'next_tier_threshold': '25000'}` err=`None`

## What would a maker path require (design only — not building)

1. `place_limit_buy` (post_only optional) on `ExchangeClient`
2. OrderExecutor branch: limit-first with timeout → cancel/reprice or market fallback
3. Settlement/fill polling already partially exists for market; must handle partial/unfilled
4. Rebalance SL attach must wait for real fill (already sensitive)
5. Shadow + isolation + Brad GO before any live switch
6. Even perfect maker entry does **not** fix STOP_LIMIT exit taker or churn rate

## Caveats

- liquidity maker/taker flag often absent — class from order_type heuristic
- fee/notional can mis-state if filled_value incomplete
- live tier probe may fail if keys/env not available in this shell
- maker savings upper bound is not a promote case
- no live changes in this dig

## Artifacts

- `reports/FILLS_MARKET_PATH_DIG.json`
- `reports/FILLS_MARKET_PATH_DIG.md`
- `scripts/phase6/dig_fills_market_path.py`

