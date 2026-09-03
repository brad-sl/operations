# Walk-forward plain English — MACD× RSI&lt;40 2×ATR (F2)

**Generated:** 2026-08-03T22:38:13.067632+00:00  
**Data:** Coinbase public daily · **2021-01 → 2026-08** (BTC/ETH/LINK 2041 bars; SOL from 2021-06)  
**Stored:** `backtests/data/long/ohlcv_daily_{btc,eth,sol,link}.json`  
**Method:** fixed recipe, **no** in-fold parameter search · 29 OOS folds × ~120d, step 60d  

---

## Bottom line (important correction)

The **~+5% core4 result was a short-window (2025–26) artifact**, not a multi-year edge.

| Horizon | Equal-weight F2 mean | vs BH | Call |
|---------|---------------------|-------|------|
| Short tape (~1y, prior dig) | **~+5%** | much better than crashing alts | looked promising |
| **Long tape (~5y, this pass)** | **−20%** | still **+11pp vs BH** (−31%) | **fails 5% bar** |
| Walk-forward OOS mean / 120d fold | **−0.9%** | **−8pp vs BH** | unstable / no absolute edge |

**Brad’s “even 5% overall is fine” bar:** **FAIL** on the long tape.  
**Less-loss vs buy-and-hold alts over full period:** still somewhat true in aggregate (+11pp), but **BTC is a disaster** (−53% vs BH +8%) — that alone kills “standard optimization.”

---

## Per-pair full long tape

| Pair | F2 | BH | N | Exp/trade | Notes |
|------|-----|-----|---|-----------|-------|
| BTC | **−53.5%** | +7.9% | 10 | −2.2% | Pattern **hurts** the core asset |
| ETH | −23.9% | −5.8% | 6 | +1.0% | Worse than hold |
| SOL | −1.5% | −53.8% | 2 | +4.5% | Less-loss only; tiny N |
| LINK | −1.3% | −72.9% | 6–8 | +5.9% | Less-loss only |

---

## Walk-forward stability

- **29 folds**, ~120 trading days each  
- **59%** of folds ≥ 0% — many are **flat cash (0 trades)**, not skill  
- Only **3%** of folds ≥ +5%  
- Mean OOS edge vs BH **negative (−8pp)** — in bull folds, sitting out / bad entries lag hard  
- Bear folds often look “good” vs BH only because BH is worse  

---

## What this means for the “promising direction”

| Keep | Drop / reframe |
|------|----------------|
| Short-window **risk sleeve** idea (don’t hold knife-catch alts) | **Do not** standardize as portfolio return engine |
| RSI filter still beats blind MACD (prior ablation) | Multi-year F2 is **not** a +5% annuity |
| Shadow only if scoped to **alt risk-off** contexts | No live promote |

### Honest reframe
F2 is closer to a **selective participation / less-loss overlay in ugly alt tapes** than a **general 5% edge system**. Over 2021–2026 it **fails** as a standard trading optimization — mainly because it **whipsaws or misses on BTC** and stays underinvested in strong bulls (2023–24 folds show 0 trades while BH rips +30–100% per window).

---

## Recommendation

`unstable_or_no_edge` → treat as **NO-GO for standard opt / live**.  

**Suggested parent trial posture:** keep research note, decide **`drop`** or **`dig_further` only on a different hypothesis** (e.g. regime-gated: run F2 only when BTC 30d &lt; 0 or alt-universe stress — pre-register one gate, don’t freestyle).

**Not recommended:** more RSI/ATR grid search on the same stack.

---

## Artifacts
- Report: `reports/MACD_RSI_ATR_WALKFORWARD_2026-08-03.md`
- JSON: `data/state/trials/TEST_MACD_RSI_ATR_WALKFORWARD.json`
- Long OHLCV: `backtests/data/long/`
- Runner: `phase6/research/macd_rsi_atr_walkforward.py`
