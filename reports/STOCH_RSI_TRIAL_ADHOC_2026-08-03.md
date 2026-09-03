# StochRSI Parallel Trial — ADHOC report

**Trial:** `STOCH-RSI-PARALLEL-20260721`  
**Generated:** 2026-08-03T17:23:03.329822+00:00  
**Recommendation:** **propose_scoped_sl_risk_experiment**  

## Intent (locked)

- Run StochRSI **in parallel** with plain longer-term RSI (instrumentation + SL risk scorer).
- Production **allocator stays plain RSI** — no core trade-logic change without evidence + Brad go.
- Close with: continue observe | extend | scoped experiment | drop | (rare) promote blend.

## History (`rsi_indicator_history.jsonl`)

- Rows in window: **1688**
- Range: `2026-07-21T22:00:54.419170+00:00` → `2026-08-03T17:15:35.306319+00:00`
- Obs with stoch: **18045** | rsi-only: **0**
- Material disagreements (RSI 40–60 vs Stoch &lt;20 or &gt;80): **5610**
- By pair: `{'AVAX-USD': 652, 'BTC-USD': 569, 'UNI-USD': 548, 'OP-USD': 534, 'DOGE-USD': 491, 'ARB-USD': 490, 'LINK-USD': 488, 'ADA-USD': 478, 'ETH-USD': 466, 'SOL-USD': 452, 'XRP-USD': 442}`

## Trades

- Trades in window: **34**
- With indicators_at_trade: **34** (stoch: **28**)
- SL exits: **15** | with stoch: **15** | stoch_k&lt;30: **12**
- Reasons: `{'stop_loss_exchange': 15, 'rebalance_buy': 6, 'dust_sweep_orphan': 5, 'preserve_disarm': 3, 'preserve_arm': 3, 'SELL': 2}`

## Decisions

- Rows: **50** | with indicator snapshot: **50**

## Caveats

- Enough SL+stoch tags to design a *shadow* SL threshold experiment — not live allocator change.

## Honest assessment

First-pass expectation remains: **not enough** to change allocator. Stoch is an *overlay signal* for risk narrative unless SL-linkage and disagreement rates are strong **and** stable across regimes.

JSON twin: `/home/brad/projects/crypto-trading-bot/reports/STOCH_RSI_TRIAL_ADHOC_2026-08-03.json`
