# Volatility clustering → risk sizing (Tier 1 shadow)

**Status:** SHADOW ACTIVE · no live size change · 2026-08-22  
**IDs:** `P6-VOL-RISK-SCALAR-SHADOW-20260822`  
**Code:** `phase6/core/vol_risk_scalar_shadow.py`  
**CLI:** `scripts/phase6/run_vol_risk_scalar_shadow.py`  
**Outputs:** `data/state/vol_risk_scalar_shadow_latest.json`, `reports/VOL_RISK_SCALAR_SHADOW_LATEST.md`

---

## Vocabulary (what Brad was aiming at)

| Phrase | Meaning on this platform |
|--------|---------------------------|
| Volatility clustering | Big moves tend to follow big moves; quiet tends to stay quiet (crypto strong). |
| GARCH-class idea | Forecast **size of next move**, not direction. |
| Vol targeting | Hold roughly constant **risk contribution**: cut size when σ̂ is high; fatten little when quiet. |
| Velocity + volume | **Early tape stress / participation** signal (RVOL, burst) — second dampener on risk tolerance, not a buy trigger. |
| Risk engine vs signal | Directional model proposes **side**; vol/velocity propose **how large / how wide**. |

This is the missing half of “we have signals but size like every bar is the same weather.”

---

## Core claim (accepted)

GARCH / vol clustering applies primarily to **dynamic risk management and position sizing**, not price prediction.

Standard form (institutional):

\[
w_t = \min\left(w_{\max},\; \frac{\sigma^\*}{\hat\sigma_{t+1}}\right)
\]

- \(\hat\sigma\): forecast conditional vol (we use **EWMA realized** first; optional simple IGARCH-style recursion).  
- \(\sigma^\*\): target vol (crypto-native — **not** 15% equity desk default).  
- \(w_{\max}\) / \(s_{\max}\): **hard cap on quiet-market upsize** (blow-up valve).

Also common: stop distance ∝ \(\hat\sigma\) (wider in high vol → fewer noise stops). **Stop-width CF is Tier 1b**, not live.

---

## What we already have (do not duplicate)

| Layer | Live / shadow | Role |
|-------|---------------|------|
| REGIME-CASH | live | Macro park/deploy, util envelopes |
| Add-risk sizer | live | $ risk on **adds** (upnl, heat, stop gap) |
| Kelly research | offline | edge → deploy_pct research |
| Volume-velocity | shadow | RVOL **nominator** for evaluate queue (not seat/buy) |
| Membership arms | shadow | who is in the basket |
| Smart Park | live micro | cash/gold ballast |

**Vol scalar is a new orthogonal layer:** multiplies (in shadow) *would-be* deploy/add notionals after other gates.

---

## Tier 1 design (this ship)

### Inputs
1. **BTC-USD** (primary) and **ETH-USD** (secondary) hourly closes — Coinbase public candles.  
2. EWMA variance on log returns (span ~24–48h) → annualized and daily σ̂.  
3. Long-run anchor: median daily σ over lookback (~30d) or fixed crypto target.  
4. **Velocity bridge** from `volume_velocity_shadow_latest.json` + open tracks:
   - Market stress proxy: count / strength of high-RVOL nominations, BTC own RVOL if present.
   - Dampen risk tolerance when velocity is elevated (participation shock), even if EWMA hasn’t fully caught up.

### Output scalar
```text
s_vol   = clip(σ_target / σ̂_btc, s_min, s_max)   # default s_min=0.35, s_max=1.15
s_vel   = clip(1 / (1 + k * stress), v_min, 1.0) # stress from RVOL / nomination heat
s       = s_vol * s_vel
would_notional = base_notional * s
```

**Asymmetric on purpose:** cut hard in storms; barely fatten in droughts (`s_max` ≤ ~1.15).

### What is logged (shadow only)
- `s_vol`, `s_vel`, `s_combined`, regime label (low/normal/high vs long-run).  
- Counterfactual: last known deploy/add caps × `s` vs live.  
- “Would have reduced” flag when `s < 0.85`.  
- **No orders, no config mutate, no dashboard hard $ promise.**

### Explicit non-goals (Tier 1)
- Live GARCH library dependency / EGARCH / DCC.  
- Mean-reversion vs momentum strategy switching off vol regime.  
- Per-alt full GARCH (noise).  
- Claiming black-swan protection.  
- Trader-facing “we always risk 15% vol” until live clip is real on **all** buy paths.

---

## Velocity + volume = risk tolerance (bridge)

Earlier week intent (Brad): velocity/volume help **risk tolerance and sizing**, not only “find new coins.”

| Use | Lane |
|-----|------|
| High RVOL nominates names into **evaluate** queue | `volume_velocity_shadow` (scout) |
| High RVOL / burst **stress** shrinks size scalar | `vol_risk_scalar_shadow` (risk) |
| Coil (high RVOL + modest \|ret\|) | scout flag; mild size dampen only |
| LQHV (low quality high velocity) | research label — **extra** dampen if we ever size those names |

**Hard rule (unchanged):** RVOL does **not** seat, buy, or promote membership.

---

## Success metrics (shadow go / no-go)

Promote to **Brad review for live multiply** only if all hold over a multi-week window:

1. During realized vol spikes (BTC daily σ above 80th pct), shadow `s` was `< 0.85` **before or as** the spike printed (not only after).  
2. Quiet periods: `s` does not sit at `s_max` for long stretches while subsequent 7d DD is large (failed drought detector).  
3. Combined scalar does not fight park/deploy (when park, size discussion is moot).  
4. No evidence that velocity dampener double-counts the same shock into paralysis (too many days `s < 0.5` with calm realized outcomes).

Else: **continue_observe_only** or retune spans/caps — **no live wire**.

---

## Implementation outline (platform)

1. **Data:** hourly OHLCV BTC/ETH (existing public path).  
2. **Model:** EWMA realized (Tier 1); optional later `arch` GARCH(1,1).  
3. **Risk engine (shadow):** multiply base size by `s`.  
4. **Execution:** N/A until Brad go.  
5. **Monitoring:** JSONL history + latest MD; cron 2×/day beside velocity shadow is enough.

---

## Relation to GARCH essay caveats

| Caveat | Our stance |
|--------|------------|
| Reacts to shocks, misses jumps | Accept; hard daily loss / park still own jumps |
| Overfit / costs | EWMA + wide caps; no high-freq re-fit circus |
| ATR often enough | EWMA ≈ cousin of ATR risk units — start here |
| Hybrid LSTM-GARCH | Out of scope |

---

## Next after Tier 1

- **1b:** Shadow stop width ∝ σ̂ vs live SL (WR / noise-exit CF).  
- **2:** Live multiply on **new buys/adds only** after Brad go (never continuous de-lever of open bags by default).  
- **3:** Optional light GARCH(1,1) if EWMA misses persistent clusters.

---

## References

- Internal: `phase6-risk-sizing-research`, `add_risk_sizer.py`, `volume_velocity_shadow.py`  
- Doctrine: direction ≠ size; expectation honesty on any future UI scalar  
- Related MASTER: WR stack, membership dual_agree, Smart Park (orthogonal)
