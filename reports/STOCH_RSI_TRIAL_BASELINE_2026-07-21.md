# StochRSI Parallel Trial — BASELINE report

**Trial:** `STOCH-RSI-PARALLEL-20260721`  
**Generated:** 2026-07-21T21:55:10.387543+00:00  
**Recommendation:** **extend_trial**  

## Intent (locked)

- Run StochRSI **in parallel** with plain longer-term RSI (instrumentation + SL risk scorer).
- Production **allocator stays plain RSI** — no core trade-logic change without evidence + Brad go.
- Close with: continue observe | extend | scoped experiment | drop | (rare) promote blend.

## History (`rsi_indicator_history.jsonl`)

- Rows in window: **899**
- Range: `2026-07-11T05:28:28.408393+00:00` → `2026-07-21T21:54:54.159715+00:00`
- Obs with stoch: **9888** | rsi-only: **0**
- Material disagreements (RSI 40–60 vs Stoch &lt;20 or &gt;80): **4447**
- By pair: `{'XRP-USD': 884, 'LINK-USD': 878, 'UNI-USD': 878, 'SOL-USD': 876, 'ETH-USD': 874, 'OP-USD': 11, 'DOGE-USD': 10, 'AVAX-USD': 10, 'BTC-USD': 9, 'ADA-USD': 9, 'ARB-USD': 8}`

## Trades

- Trades in window: **92**
- With indicators_at_trade: **77** (stoch: **17**)
- SL exits: **36** | with stoch: **2** | stoch_k&lt;30: **1**
- Reasons: `{'BUY': 42, 'stop_loss_exchange': 36, 'SELL': 5, 'rotation_exchange': 5, 'rebalance_buy': 3, 'OPS_CORRECTION': 1}`

## Decisions

- Rows: **27** | with indicator snapshot: **27**

## Caveats

- Disagreement exists but outcome link weak — extend collection another 7–14d.

## Honest assessment

First-pass expectation remains: **not enough** to change allocator. Stoch is an *overlay signal* for risk narrative unless SL-linkage and disagreement rates are strong **and** stable across regimes.

JSON twin: `/home/brad/projects/crypto-trading-bot/reports/STOCH_RSI_TRIAL_BASELINE_2026-07-21.json`
