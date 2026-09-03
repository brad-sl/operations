# StochRSI Parallel Trial — ADHOC report

**Trial:** `STOCH-RSI-PARALLEL-20260721`  
**Generated:** 2026-09-03T16:00:25.750362+00:00  
**Recommendation:** **propose_scoped_sl_risk_experiment**  

## Intent (locked)

- Run StochRSI **in parallel** with plain longer-term RSI (instrumentation + SL risk scorer).
- Production **allocator stays plain RSI** — no core trade-logic change without evidence + Brad go.
- Close with: continue observe | extend | scoped experiment | drop | (rare) promote blend.

## History (`rsi_indicator_history.jsonl`)

- Rows in window: **4832**
- Range: `2026-07-21T22:00:54.419170+00:00` → `2026-09-03T16:00:21.797249+00:00`
- Obs with stoch: **52260** | rsi-only: **0**
- Material disagreements (RSI 40–60 vs Stoch &lt;20 or &gt;80): **16446**
- By pair: `{'AVAX-USD': 1578, 'BTC-USD': 1543, 'UNI-USD': 1506, 'DOGE-USD': 1487, 'ETH-USD': 1483, 'LINK-USD': 1480, 'ARB-USD': 1450, 'XRP-USD': 1418, 'SOL-USD': 1408, 'OP-USD': 846, 'ICP-USD': 739, 'ADA-USD': 669, 'RAVE-USD': 484, 'PENGU-USD': 282, 'PUMP-USD': 5, 'SUI-USD': 4, 'TAO-USD': 4, 'ZEC-USD': 4, 'CAP-USD': 3, 'TRUMP-USD': 3, 'ENA-USD': 3, 'STX-USD': 3, 'IMU-USD': 2, 'HYPE-USD': 2, 'AAVE-USD': 2, 'VVV-USD': 2, 'LIGHTER-USD': 2, 'DASH-USD': 2, 'SUPER-USD': 2, 'HFT-USD': 2, 'ZKC-USD': 2, 'USELESS-USD': 2, 'XLM-USD': 1, 'GRVT-USD': 1, 'NEAR-USD': 1, 'JTO-USD': 1, 'AVNT-USD': 1, 'ATOM-USD': 1, 'FET-USD': 1, 'PAXG-USD': 1, 'COW-USD': 1, 'WLD-USD': 1, 'APR-USD': 1, 'MON-USD': 1, 'ZORA-USD': 1, 'TRAC-USD': 1, 'MORPHO-USD': 1, 'VIRTUAL-USD': 1, 'BICO-USD': 1, 'POL-USD': 1, 'SWELL-USD': 1, 'CHIP-USD': 1, 'HNT-USD': 1, 'NKN-USD': 1, 'FLOCK-USD': 1, 'SKR-USD': 1}`

## Trades

- Trades in window: **101**
- With indicators_at_trade: **98** (stoch: **88**)
- SL exits: **27** | with stoch: **26** | stoch_k&lt;30: **23**
- Reasons: `{'rebalance_buy': 35, 'stop_loss_exchange': 27, 'dust_sweep_after_sl': 9, 'dust_sweep_orphan': 6, 'preserve_disarm': 3, 'preserve_arm': 3, 'rotation_exchange': 3, 'SELL': 2, 'take_profit_trail': 2, 'operator_trim_link_to_btc_30pct': 2, 'lifecycle_dual_peak:failed_high_off=0.042|mfe_stall|phase=distribution|sent_fade=0.255|cur=0.007': 2, 'take_profit_fixed_tp': 1}`

## Decisions

- Rows: **184** | with indicator snapshot: **183**

## Caveats

- Enough SL+stoch tags to design a *shadow* SL threshold experiment — not live allocator change.

## Honest assessment

First-pass expectation remains: **not enough** to change allocator. Stoch is an *overlay signal* for risk narrative unless SL-linkage and disagreement rates are strong **and** stable across regimes.

JSON twin: `/home/brad/projects/crypto-trading-bot/reports/STOCH_RSI_TRIAL_ADHOC_2026-09-03.json`
