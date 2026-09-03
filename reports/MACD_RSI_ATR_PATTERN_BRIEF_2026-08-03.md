# MACD× + RSI&lt;40 + 2×ATR — pattern brief (plain English)

Generated: 2026-08-03T22:29:33.991665+00:00
Parent: TEST-COMBINED-INDICATOR-ABLATION-2026-08
Core universe: BTC ETH SOL LINK (AVAX/XRP/DOGE stress-tested separately)
Window: 2025-07-19 → 2026-07-30

## Bottom line

**Is there a solid standard-trading optimization pattern?** **Yes — as a structure.**

**Do we have a clean 10–20% portfolio edge to pick up right now?** **No.**

**Where a 10–20% pickup showed up:** **SOL only** (+13.7% absolute on F2). Not a basket rule yet.

**Best recipe:** `F1` — MACD× + RSI<40 + 2×ATR + MACD-death
- Mean return across core4: **4.7%** (target was 10–20%)
- Trade expectancy: **7.7% per trade** · WR ~**75%** · N=**9** (thin)
- Mean max DD: **-12.5%** vs BH basket DD **-46.7%**
- Beats equal-weight BH by **~+31pp** — mostly because alts crashed, not because we minted +15% alpha

## The pattern (standard recipe)

| Step | Rule |
|------|------|
| **Entry** | Daily bar: MACD line crosses **above** signal **and** RSI(14) **&lt; 40** |
| **Exit** | Trail stop = peak since entry − **2 × ATR(14)**; also exit on **MACD death cross** |
| **Optional** | Soft TP at +2R (2×ATR from entry) — fired often on winners in this tape |
| **Skip** | No Stoch, no Bollinger required |
| **Universe** | Prefer liquid majors; **skip** names already in deep 30d/90d collapse (AVAX-class) |
| **Sizing (test)** | 95% equity, 5 bps/side, long-only |

## Core4 scorecard (F2)

| Pair | BH | F2 ret | F2 N | Exp/trade | WR | Call |
|------|-----|--------|------|-----------|----|------|
| BTC | 7.4% | **4.2%** | 1 | 9.7% | 100% | small + |
| ETH | -12.0% | **4.2%** | 3 | 7.2% | 67% | small + |
| SOL | -43.9% | **13.7%** | 2 | 12.3% | 100% | ✅ 10%+ pickup |
| LINK | -56.4% | **-3.4%** | 3 | 4.5% | 33% | still red (but << BH) |

## What actually matters (ablation lessons)

| Knob | Finding |
|------|---------|
| **RSI filter** | **Mandatory.** MACD-only (F7) mean **−43%** — kills the edge |
| **RSI threshold** | **40 is sweet spot.** 35 = almost no trades; 45 = more trades, worse mean |
| **ATR mult** | **2× best.** 1.5× similar/slightly worse; 3× gives back gains |
| **MACD-death** | Helps a bit on LINK (F1/F2 beat F0); keep it |
| **Weak/deep-bear skip** | Neutral on core4 (same as F1); **critical when AVAX/XRP-class included** |
| **Hist&gt;0 extra** | No change (F9=F2) — skip complexity |

## Expanded stress (BTC ETH SOL LINK XRP DOGE)

Adding XRP/DOGE **dilutes** mean return toward ~0–1%. XRP F2 went **−14%** (2 SL trails). DOGE took **0** trades.
→ Pattern is **not** “trade every liquid name.” It’s **selective.**

## Can we apply this as a standard optimization?

| Question | Answer |
|----------|--------|
| Solid entry/exit **pattern**? | **Yes** — MACD× + RSI&lt;40 + 2×ATR + MACD-death |
| Ready as **live default** / allocator replace? | **No** — N≈9–11, one window, no 10% basket edge |
| Ready as **shadow / paper sleeve**? | **Yes** — watch fill quality + false crosses |
| 10–20% edge **portfolio**? | **Not on this tape** (mean ~+5% core4) |
| 10–20% edge **where we can pick one up**? | **Yes, selectively** (SOL +13.7%); not guaranteed per name |
| North star (return + less loss)? | **Less loss: strong vs alt BH. Absolute return: modest.** |

## Go / No-go

- **GO (research → shadow):** lock recipe F2 as the combined-indicator dig champion; no more A0/Stoch/BB fishing.
- **NO-GO (live size / “we have 15% edge” claims):** sample too thin; basket edge not 10–20%.
- **Next proof (if you want the 10–20% claim):** longer OHLCV **or** walk-forward on 15m/4h with pre-registered RSI∈{38,40,42} only — not a new indicator zoo.

**Recommendation code:** `standard_opt_pattern_thin_sample`

