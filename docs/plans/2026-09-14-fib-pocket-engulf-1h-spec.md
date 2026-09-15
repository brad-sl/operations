# Spec: 1h Fib golden-pocket + engulf (Honest Trader skeleton)

**Date:** 2026-09-14  
**Source tweet:** https://x.com/theh0n3sttrader/status/2099543951309165012  
**Status:** LAB ONLY — frozen v0 for offline CF. **No live wire, no evaluate_buy_entry, no basket hook, no auto-promote.**  
**Runner:** `phase6/research/fib_pocket_engulf_1h.py`  
**Isolation:** `scripts/phase6/test_isolation_fib_pocket_engulf_1h.py`

## Plain English

Tweet recipe: 1h → Fib swing → wait golden pocket → engulfing → enter → protected SL → TP 1:2.  
This doc freezes every free parameter so the backtest is one strategy (plus a small pre-registered grid), not discretionary chart reading.

## Honesty bars (offline-strategy-honesty)

- Real Coinbase public OHLCV only.
- Report **after fees**, N, win rate (secondary), mean R, expectancy $/trade, max DD, vs buy-hold on same window.
- Tag classes: `HIT_*` only if abs + ΔBH clear; else `ATTENTION_ONLY` / `unstable_or_no_edge` / `EDGE_VS_BAGS_ONLY`.
- Prior fib family (`fib_discount_entry` 2026-08-15) was **drop** on long tape — this is a **different** recipe (1h impulse Fib + engulf + 1:2), still lab.

## Universe & data

| Knob | v0 default | Why (success bias) |
|------|------------|--------------------|
| Pairs | **BTC-USD**, ETH-USD (primary scoreboard = BTC) | Cleanest 1h structure; alts as secondary |
| TF | **1h** | As tweeted |
| History | ≥ **400 days** 1h (Coinbase public candles) | Enough trades for N |
| Session filter | **None** (24/7 crypto) | Crypto is not NYSE session |

## Trend filter (tweet: “if bullish / bearish”)

| Knob | v0 default | Why |
|------|------------|-----|
| Definition | **EMA(50) vs EMA(200)** on 1h close | Simple, laggy = fewer fake flips; highest *stability* among common free defs |
| Long only when | `EMA50 > EMA200` | Aligns Fib L→H with uptrend |
| Short only when | `EMA50 < EMA200` | Symmetric (spot bot may **long-only** — see flags) |
| **Live-book flag** | `long_only=true` for Phase 6 spot | We don’t short alts on Coinbase sleeve |

## Impulse swing for Fib (tweet underspecified)

| Knob | v0 default | Why |
|------|------------|-----|
| Pivot | Fractal **left=right=5** (high is max of 11 bars; low is min of 11) | Standard; 3 = noisier, 8 = fewer setups |
| Active swing (long) | Last **confirmed pivot low → later confirmed pivot high** with high after low, both in uptrend regime | Classic impulse |
| Active swing (short) | Last pivot high → later pivot low | Symmetric |
| Min impulse size | **≥ 1.5 × ATR(14)** of bar at swing end | Kill micro Fib noise |
| Stale swing | Invalidate if price closes **beyond** 1.272 extension opposite without setup, or age **> 120 bars** | Avoid ancient Fib ghosts |
| One Fib at a time | Yes — newest valid impulse only | Tweet spirit |

## Golden pocket (tweet: “golden pocket”)

| Knob | v0 default | Why |
|------|------------|-----|
| Band | **Fib retracement 0.618 – 0.650** of impulse | Classic “golden pocket”; tighter than 0.5–0.786 → higher quality, fewer trades |
| Long zone | `low_zone = high - 0.650*(high-low)` … `high_zone = high - 0.618*(high-low)` | Price pulls into upper gold band |
| Touch rule | **Wick intersects zone** (low ≤ high_zone and high ≥ low_zone for long) | More opportunities than close-only; engulf still filters |
| First touch window | Setup armed on first touch; must confirm within **6 bars** | Don’t wait forever |

### Pre-registered pocket variants (grid only; not live knobs)

- `pocket_gold`: 0.618–0.650 (**v0**)
- `pocket_wide`: 0.618–0.786
- `pocket_mid`: 0.500–0.618

## Engulfing (tweet underspecified)

| Knob | v0 default | Why |
|------|------------|-----|
| Long engulf | Close > open **and** close ≥ prior bar high **and** open ≤ prior bar open (body dominates) | Stricter than “close > prior close” — fewer fake engulfs |
| Short engulf | Mirror | |
| Location | Signal bar must **also** have low/high still interacting with pocket **or** prior bar did | Pocket + trigger coupling |
| Min body | Body ≥ **0.35 × ATR(14)** | Skip doji “engulfs” |

### Pre-registered engulf variants

- `engulf_strict`: v0  
- `engulf_loose`: close > prior close + green/red only  

## Entry / SL / TP (tweet: enter, protected SL, 1:2)

| Knob | v0 default | Why |
|------|------------|-----|
| Entry | **Next bar open** after signal bar closes | No peek; realistic |
| SL long | `min(swing_low, signal_low) - 0.15×ATR` | Beyond structure = “protected” |
| SL short | `max(swing_high, signal_high) + 0.15×ATR` | Mirror |
| Min stop distance | **≥ 0.40%** of entry | Else skip (fee domination) |
| Max stop distance | **≤ 4.0%** of entry | Else skip (1:2 TP unrealistic vs noise) |
| TP | **1:2 R:R** — `entry + 2*(entry-sl)` long | As tweeted |
| Time stop | **72 bars (3d)** → exit at close if neither SL/TP | Bounds tail risk in CF |
| Fills | Intrabar: stop and target — **conservative**: if both could hit same bar, **SL first** | Honesty under-states edge |
| Position | 1 at a time per pair; flat → next setup | No pyramid |
| Size | Fixed **1.0 risk unit** notional for R accounting; optional $75 notion for $-PnL column | Matches tryout mental model |

## Costs (non-negotiable)

| Knob | v0 default |
|------|------------|
| Fee | **0.80% entry + 0.80% exit** (Coinbase Intro 2 taker RT **1.6%**) |
| Slip | **+2 bps/side** on entry/exit mid |
| Effective | ~**1.64% RT** haircut on notional round-turn |

No maker fantasy. Report gross R and **net after fees**.

## Execution model flags

```text
long_only: true
place_orders: false
live_membership_swaps: n/a
evaluate_buy_entry: not touched
```

## Scoreboard outputs

Per pair + portfolio equal-weight trade list:

- N trades, win rate, mean R gross, mean R net, expectancy, profit factor  
- Max DD (R-space and $-space on $75 tickets)  
- % time in market  
- Buy-hold return same window (ΔBH)  
- Median bars held  
- Edge class tag  

Artifacts:

- `docs/plans/2026-09-14-fib-pocket-engulf-1h-spec.md` (this file)  
- `data/state/fib_pocket_engulf_1h_latest.json`  
- `reports/FIB_POCKET_ENGULF_1H_LATEST.md`  
- Optional grid: `reports/FIB_POCKET_ENGULF_1H_GRID.md`

## Pre-registered parameter grid (pre-tune only)

Run **once** on BTC 1h; pick winner by **mean net R** with **N≥30** and **not** anti BH disaster. No iterative fishing after see.

| Dim | Values |
|-----|--------|
| pivot | 3, **5**, 8 |
| pocket | gold, wide, mid |
| engulf | strict, loose |
| trend | ema50_200, **none** (ablation) |

Default v0 cell: pivot5 + gold + strict + ema50_200 + long_only.

## Success / kill criteria (lab)

| Result | Tag | Action |
|--------|-----|--------|
| Net mean R > 0 after fees, N≥40, PF>1.2, not crushed vs BH | `ATTENTION_ONLY` at best | Optional walk-forward; still no live |
| Net mean R ≤ 0 or N sparse or fee-dominated | `unstable_or_no_edge` | **drop** family; no refine same session |
| Looks good only on one pocket width after peeking | fishing | discard |

**Live promote:** never from this card alone. Would need multipair WF + Brad GO + fit vs recovery tryout path (unlikely fit).

## Relation to Phase 6 live book

- Does **not** open empty-funnel doors (eng/RSI/armor).  
- Does **not** cut X bill.  
- Prior daily fib discount shadow already **dropped** — treat this as separate 1h scalp/swing recipe test only.

## Rollback

Delete research runner outputs; no config knobs shipped. Spec remains historical.
