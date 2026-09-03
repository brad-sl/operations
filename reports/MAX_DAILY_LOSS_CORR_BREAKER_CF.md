# Max Daily Loss + Correlation Breaker — Contribution CF

**STATUS: PARKED (Brad 2026-08-31)** — complexity > return. No wire / no promote.


**As of:** 2026-08-31T21:16:20.892831+00:00
**NAV (live):** ~$2,295
**Ledger:** 47 days with realized SELL PnL · ['2026-05-01', '2026-08-30']
**Total realized (SELL lots):** $400.98
**Sum of negative days:** $-290.71

## Semantics (what these knobs actually do)

| Knob | Design | Live Phase 6 |
|------|--------|--------------|
| `max_daily_loss_pct=0.02` | Config → `$20` on `total_capital=1000` (or ~`$46` if % of live NAV). Legacy: **block NEW buys** after day realized loss hits threshold. **Does not auto-flatten.** | **Not enforced** in `phase6/core` (theater load) |
| Correlation circuit breaker | corr ≥ **0.85** → flag **30% reduce** + 15% reserve redeploy | Module exists; **not on runner** |

## A. Max daily loss — do we have fire evidence?

### End-of-day realized fires

| Threshold | Fire days | Days |
|-----------|-----------|------|
| cfg $20 (2% of $1k capital) | **4** | 2026-06-05 ($-70), 2026-07-11 ($-37), 2026-08-01 ($-36), 2026-08-25 ($-30) |
| 2% of live NAV (~$46) | **1** | 2026-06-05 ($-70) |
| $50 hard | **1** | 2026-06-05 ($-70) |
| $100 hard | **0** | — |
| 5% of live NAV | **0** | — |

### Counterfactual: block buys after intraday cumulative loss

- **cfg $20:** fire_days=4, blocked_buys=3, blocked_notional=**$29.64**, sell_pnl_after_breach=**$-32.50**, fantasy buy-leg fee @0.8% ≈ **$0.24**
- **live 2% (~$46):** fire_days=1, blocked_buys=3, blocked_notional=**$29.64**, sell_pnl_after=**$-0.47**

### Pre vs post breach (cfg $20) — where the damage sat

| Day | Pre-breach sell PnL | Post-breach sell PnL | Day total |
|-----|---------------------|----------------------|-----------|
| 2026-06-05 | $-45.02 | $-24.87 | $-69.89 |
| 2026-07-11 | $-30.69 | $-6.47 | $-37.15 |
| 2026-08-01 | $-35.58 | $-0.57 | $-36.15 |
| 2026-08-25 | $-29.67 | $-0.59 | $-30.26 |
| **TOTAL** | **$-140.96** | **$-32.50** | |

**Read:** Almost all damage is **already locked in SL/exits before/at breach**. A buy-block after the fact is a **pile-on brake**, not a loss eraser. Post-breach residual sells are small on this sample.

**Class:** `ATTENTION_ONLY_less_loss_path_weak` — honesty/safety rail, not a ~5% edge lever on this book.

## B. Correlation breaker — fire rate + fantasy save

- Rolling 30d any-core-pair corr ≥ 0.85: **101/101** sample days (100%)
- Aligned OHLCV dates in window: **131** · core=['BTC', 'ETH', 'SOL', 'XRP', 'LINK', 'AVAX', 'DOGE']

### Latest pairwise corrs (sample end)

| Pair | Corr |
|------|------|
| ETH-LINK | 0.953 **FIRE** |
| BTC-SOL | 0.885 **FIRE** |
| BTC-XRP | 0.884 **FIRE** |
| XRP-DOGE | 0.883 **FIRE** |
| BTC-ETH | 0.878 **FIRE** |
| ETH-XRP | 0.872 **FIRE** |
| BTC-LINK | 0.862 **FIRE** |
| ETH-SOL | 0.86 **FIRE** |
| SOL-LINK | 0.858 **FIRE** |
| XRP-LINK | 0.846 |
| ETH-DOGE | 0.809 |
| SOL-XRP | 0.808 |

### Multi-pair loss days (2+ pairs each < −$2 realized)

n=**5** · sum day PnL = **$-79.76**

| Day | Day PnL | Losers | Loser-pair corrs | Fantasy 30% save |
|-----|---------|--------|-----------------|------------------|
| 2026-06-05 | $-69.89 | XRP-USD, SOL-USD | XRP-SOL=0.853 | $20.97 |
| 2026-07-11 | $-37.15 | DOGE-USD, AVAX-USD, SOL-USD, OP-USD | DOGE-AVAX=0.491, DOGE-SOL=0.702, AVAX-SOL=0.687 | $0.00 |
| 2026-07-16 | $-4.68 | AVAX-USD, SOL-USD | AVAX-SOL=0.667 | $0.00 |
| 2026-07-20 | $-10.29 | ADA-USD, DOGE-USD | n/a | $0.00 |
| 2026-08-23 | $42.26 | RAVE-USD, UNI-USD | n/a | $0.00 |

**Fantasy upper bound** (30% of co-loser losses on days where loser-pair corr ≥ 0.85 **and** cut assumed *before* dump): **$20.97** over 1 applicable days.

**Read:** Several worst days are **single-name** (LINK −$36, LINK −$30, ICP −$14) — corr cut does nothing. Multi-name days exist but OHLCV gaps + sparse ≥0.85 among *actual co-losers* keep fantasy small. High *market* corr can still be common (BTC–ETH etc.) without matching our simultaneous SL cluster.

**Class:** `ATTENTION_ONLY_less_loss_path_sparse` — not a promote-to-live edge on this sample.

## C. Rank vs known levers (same book)

| Lever | Approx contribution | Class |
|-------|---------------------|-------|
| Fee drag (30d) | ~$139 NAV tax | house cut (cost) |
| C stand-down elevated process (90d CF) | ~$89 avoided | less-loss filter |
| Limit-first buy (if rests) | ~0.4% of buy notional | cost cut |
| max_daily_loss buy-block CF | blocked notional $30; post-breach residual $-32; fee fantasy tiny | weak safety rail |
| Corr 30% reduce fantasy | ~$21 sparse | weak / sparse less-loss |

## D. Recommendation

1. **Do not sell either as a P&L unlock.** Data does not support a material expectancy lift.
2. **max_daily_loss:** still worth **honesty** — wire a real enforcer *or* delete/rename the knob so config is not theater. If wired: use **% of live equity** (not stale $1k capital), buy-block only, no panic flatten, log fires.
3. **Corr breaker:** keep **shadow/LEGACY** unless a longer multipair board shows clustered same-session SL damage that predates high corr. Default OFF. Redeploy leg is a second risk.
4. Priority stays: **fewer RTs · C stand-down observe · limit-first pilot evidence · exit promote gates.**

## Honest limits

- Realized SELL ledger only — no mark-to-market intraday equity curve
- max_daily_loss CF assumes chronological fills within day; no open unrealized
- corr CF fantasy assumes 30% size already cut BEFORE the loss day
- OHLCV alignment may miss some alt pairs (OP/ICP/PENGU) → undercount multi-day corr
- Does not model redeploy risk after corr cut or opportunity cost of blocked buys

JSON: `reports/MAX_DAILY_LOSS_CORR_BREAKER_CF.json`

---
*Research only. No live changes.*
