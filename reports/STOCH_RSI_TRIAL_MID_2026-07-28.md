# StochRSI Parallel Trial — MID report

**Trial:** `STOCH-RSI-PARALLEL-20260721`  
**Generated:** 2026-07-28T16:00:59.872075+00:00  
**Recommendation:** **propose_scoped_sl_risk_experiment**  

## Intent (locked)

- Run StochRSI **in parallel** with plain longer-term RSI (instrumentation + SL risk scorer).
- Production **allocator stays plain RSI** — no core trade-logic change without evidence + Brad go.
- Close with: continue observe | extend | scoped experiment | drop | (rare) promote blend.

## History (`rsi_indicator_history.jsonl`)

- Rows in window: **1081**
- Range: `2026-07-21T22:00:54.419170+00:00` → `2026-07-28T16:00:36.950368+00:00`
- Obs with stoch: **11368** | rsi-only: **0**
- Material disagreements (RSI 40–60 vs Stoch &lt;20 or &gt;80): **3462**
- By pair: `{'AVAX-USD': 441, 'BTC-USD': 391, 'UNI-USD': 335, 'DOGE-USD': 323, 'ADA-USD': 307, 'ETH-USD': 304, 'LINK-USD': 304, 'ARB-USD': 288, 'XRP-USD': 268, 'OP-USD': 255, 'SOL-USD': 246}`

## Trades

- Trades in window: **16**
- With indicators_at_trade: **16** (stoch: **16**)
- SL exits: **12** | with stoch: **12** | stoch_k&lt;30: **9**
- Reasons: `{'stop_loss_exchange': 12, 'rebalance_buy': 2, 'SELL': 2}`

## Decisions

- Rows: **24** | with indicator snapshot: **24**

## Caveats

- Enough SL+stoch tags to design a *shadow* SL threshold experiment — not live allocator change.

## Honest assessment

First-pass expectation remains: **not enough** to change allocator. Stoch is an *overlay signal* for risk narrative unless SL-linkage and disagreement rates are strong **and** stable across regimes.

JSON twin: `/home/brad/projects/crypto-trading-bot/reports/STOCH_RSI_TRIAL_MID_2026-07-28.json`
