# TP / Trail Scaffold — 2026-07-29

**Enum:** `design_shadow` · live writes: false
- Baseline Exit WR: 0.2892 n=83
- SL sum PnL: -99.5046 · rotation: 177.3992
- Blocked on: ohlcv_path_counterfactual_not_built

## Next
- For each buy→exit, load pair OHLCV high watermark max r before exit
- Counterfactual: exit at first touch of +tp OR trail stop
- Compare path DD and expectancy vs baseline ledger

Do not enable live `take_profit_pct` from this scaffold alone.
