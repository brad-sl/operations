# Lab park: ATR coil + buy-stop breakout (ATR20/30)

**Date:** 2026-09-17  
**Status:** **PARKED — possible future test only.** No live wire, no `evaluate_buy_entry`, no basket hook, no auto-promote, no runner hook.  
**Brad:** Saved on ask after comparing to live Phase 6 path (not already running this recipe).  
**Code seed:** `phase6/research/atr_coil_buystop_breakout.py`  
**Isolation (when staffed):** `scripts/phase6/test_isolation_atr_coil_buystop_breakout.py`  
**Related (cousins, not the same):**  
- `docs/research/SQUEEZE_REGIME_BREAKOUT_RESEARCH.md` — BB/TTM coil + range/vol confirm (paper)  
- `phase6/research/squeeze_regime_breakout.py` — compression helpers  
- Luck ladder R0/R1 — RSI wash / knife (live-adjacent shadow, different entry geometry)

---

## Plain English

Futures-style **volatility coil → breakout stop** recipe adapted for 24/7 crypto:

1. **Coil gate:** ATR(20) &lt; ATR(30) (short-term vol compressed vs longer ATR).  
2. **Entry:** buy-**stop** at `bar_open + 2.5 × ATR(20)` — price must trade through; not a market chase.  
3. **Stop:** `entry − 0.5 × ATR(20)`.  
4. No Friday session exit (crypto continuous).

This is **not** the live Phase 6 tryout path (RSI + sentiment + $75 + ~3% SL / trail TP). It is a **different risk shape** (stop-entry breakouts, ATR-scaled stops).

---

## Why park (not staff now)

| Reason | Note |
|--------|------|
| Empty-funnel / prove current config | Priority is fills under **existing** gates, not new entry arms |
| Cousin already exists | Squeeze research covers coil→break on paper with different defs |
| Live mismatch | Runner is limit/market tryout + exchange SL; no ATR buy-stop placer |
| Honesty | Needs fee+slippage CF on exact pairs/TF before any promote talk |

**Staff only after:** Brad GO + offline bake-off clears N/edge bars (mirror fib / squeeze honesty). Prefer after Luck Ladder R0 closeout noise settles.

---

## Frozen v0 knobs (do not retune mid-test)

| Knob | v0 | Notes |
|------|-----|--------|
| `ATR_FAST` | 20 | Coil short leg + stop/entry scale |
| `ATR_SLOW` | 30 | Coil long leg |
| Coil | `atr20 < atr30` | Strict less-than; equal = not coiling |
| `ENTRY_MULT` | 2.5 | `open + ENTRY_MULT * atr20` |
| `STOP_MULT` | 0.5 | stop distance from entry |
| ATR of TR | SMA of true range | Classic Wilder optional later as grid arm only |
| TF candidates | **4h primary**, daily secondary | Sample suggested BTC 4h/d; freeze one TF per run |
| Universe v0 | BTC-USD, ETH-USD | Expand only after N floor |
| Long only | true | Spot book |
| Fees | ≥ live maker/taker RT (use fee snapshot) | Report net only |
| Slippage | +1 tick or bps grid | Buy-stops fill worse than mid |

### Pre-registered grid only (not live knobs)

- Entry mult: 2.0 / **2.5** / 3.0  
- Stop mult: 0.5 / 1.0  
- ATR: SMA vs Wilder  
- Coil: atr20&lt;atr30 vs atr20&lt;0.9*atr30  

---

## Honesty bars (offline-strategy-honesty)

- Real Coinbase (or project OHLCV SSOT) only — no synthetic tape.  
- Report **after fees**, N, hit rate (secondary), mean R, expectancy, max DD, vs buy-hold same window.  
- Tag: `HIT_*` only if abs + ΔBH clear; else `ATTENTION_ONLY` / `unstable_or_no_edge`.  
- **exploit_ready=false** until N and stability bars met (prefer N≥40 on primary TF).  
- Do not claim edge from one green week or one pair.

---

## Separation from live / other arms

| Track | Role |
|-------|------|
| This lab | Optional future **entry geometry** CF |
| Squeeze M2/S3 | Coil via BB/TTM + breadth/regime — paper |
| Live tryout | RSI ≤55 + sent ≥0.30 + $75 + trail/SL |
| R0 RSI-event X | Sensor clock — not breakout stops |
| Membership dual_agree | Seats only — no this entry |

**Never** use this as membership gate or auto-buy without Brad GO.

---

## Build order when staffed (not now)

1. Isolation: TR, ATR, coil flag, entry/stop levels on fixture bars.  
2. Offline CF runner: 4h BTC/ETH, fees, fill model (stop touched vs close-through).  
3. Report `reports/ATR_COIL_BUYSTOP_BREAKOUT_LATEST.md` + grid.  
4. Compare vs squeeze S1 and buy-hold; no live hook.  
5. Only if exploit bar + Brad GO → shadow arm design (separate plan).

---

## Sample logic (canonical seed)

See `phase6/research/atr_coil_buystop_breakout.py` — same numbers as the 2026-09-17 drop-in sample (ATR20/30, 2.5 entry, 0.5 stop, coil filter).

---

## Non-goals (v0)

- Live runner / Coinbase stop-entry placement  
- Replacing RSI/sent tryout  
- Friday flat / session calendar  
- Short side on spot sleeve  
- Auto-promote from one bake-off
