# StochRSI Parallel Trial — FINAL report

**Trial:** `STOCH-RSI-PARALLEL-20260721`  
**Generated:** 2026-08-04T16:14:35.821500+00:00  
**Recommendation:** **propose_scoped_sl_risk_experiment**  

## Intent (locked)

- Run StochRSI **in parallel** with plain longer-term RSI (instrumentation + SL risk scorer).
- Production **allocator stays plain RSI** — no core trade-logic change without evidence + Brad go.
- Close with: continue observe | extend | scoped experiment | drop | (rare) promote blend.

## History (`rsi_indicator_history.jsonl`)

- Rows in window: **1782**
- Range: `2026-07-21T22:00:54.419170+00:00` → `2026-08-04T16:00:34.152026+00:00`
- Obs with stoch: **19079** | rsi-only: **0**
- Material disagreements (RSI 40–60 vs Stoch &lt;20 or &gt;80): **5968**
- By pair: `{'AVAX-USD': 680, 'BTC-USD': 605, 'OP-USD': 576, 'UNI-USD': 574, 'LINK-USD': 524, 'DOGE-USD': 523, 'ARB-USD': 523, 'ADA-USD': 509, 'ETH-USD': 489, 'XRP-USD': 484, 'SOL-USD': 481}`

## Trades

- Trades in window: **35**
- With indicators_at_trade: **35** (stoch: **29**)
- SL exits: **15** | with stoch: **15** | stoch_k&lt;30: **12**
- Reasons: `{'stop_loss_exchange': 15, 'rebalance_buy': 7, 'dust_sweep_orphan': 5, 'preserve_disarm': 3, 'preserve_arm': 3, 'SELL': 2}`

## Decisions

- Rows: **53** | with indicator snapshot: **53**

## Caveats

- Enough SL+stoch tags to design a *shadow* SL threshold experiment — not live allocator change.

## Honest assessment

First-pass expectation remains: **not enough** to change allocator. Stoch is an *overlay signal* for risk narrative unless SL-linkage and disagreement rates are strong **and** stable across regimes.

JSON twin: `/home/brad/projects/crypto-trading-bot/reports/STOCH_RSI_TRIAL_FINAL_2026-08-04.json`
