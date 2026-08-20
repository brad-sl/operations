# Regime boundary layers — flat→bull gap design

**Date:** 2026-08-20  
**Status:** Option **1 shipped** (labels + shadow) — **no live park thaw**  
**Live money:** unchanged (`transition` → `usdc_park` cap $0 until Brad promote)  
**Trigger:** Operator: huge flat→bull residual park band is counterproductive while path trends up; OK with **narrow** true-transition; want **layers** + cash deploy only where win probability is defensible.

---

## 1. Plain English

| Claim | Verdict |
|-------|---------|
| One fat **transition** bucket from ~+8% to +15% BTC/30d that **only parks** is a blunt product | **Agree** — residual design, not a fitted band |
| “Trending the right way” ⇒ high-probability deploy in that gap | **Not supported** on long BTC tape — only **bull** (≥ cut) shows clear forward WR lift |
| Keep a **narrow** “predictability gone” park strip | **Agree** |
| Allow **some** cash out in upper gap with **strict** gates / small caps | **Reasonable product** — as **micro/climb sleeves**, not full bull util; needs shadow before live |

**Live today (session):** detector often ~**+9% / transition / park / cap $0**. That is exactly the soft-up / early-climb zone this note targets.

---

## 2. What the gap is today

```
bear ≤ −10% | soft residual −10…−8 | flat |r|≤8 | **** UPSIDE RESIDUAL +8…+15 **** | bull ≥ +15%
                                              \________ all labeled "transition" → PARK ________/
```

- Transition is **not** sized; it is **else**.
- Upside residual ≈ **7 pp**; downside residual ≈ **2 pp** (asymmetric).
- Jul 27 trial: **full** transition deploy/faster-flip **dropped** (park beat higher util on DD). That rejects “open the whole blob,” not “name layers inside it.”

---

## 3. Evidence (real BTC daily, long tape)

**Source:** `backtests/data/long/ohlcv_daily_btc.json` (~2020-11 → 2026-08), rolling **30d** return, forward **price** outcomes (not basket PnL, not fees).

### 3.1 Layered occupancy (cutpoints bull=15, bear=−10, flat=8; soft_up = +8…+10; climb = +10…+14; pre_bull = +14…+15)

| Layer | Days (n≈) | Role |
|-------|-----------|------|
| bear | 442 | risk-off |
| soft_down | 75 | thin downside residual |
| flat | 882 | range / option-B today |
| soft_up | 75 | just above flat |
| climb | 145 | “trending up but not bull” |
| pre_bull | 29 | last step into bull |
| bull | 415 | full deploy regime |

### 3.2 Forward BTC path (honesty bar for “high WR”)

| Layer | WR 7d | avg 7d | WR 14d | avg 14d | WR 30d | avg 30d | p10 30d (tail) |
|-------|------:|-------:|-------:|--------:|-------:|--------:|---------------:|
| **bull** | **61%** | **+2.6** | **65%** | **+4.9** | **59%** | **+6.2** | −10.6 |
| flat | 50% | +0.3 | 51% | +0.7 | 53% | +3.0 | −19.7 |
| soft_up | 48% | +0.7 | 47% | +0.1 | 43% | +0.7 | −18.2 |
| climb | 50% | +0.5 | 46% | +0.8 | 40% | −0.3 | −20.8 |
| pre_bull | 52% | +0.5 | 38% | +1.7 | 41% | +2.4 | −17.4 |
| bear | 49% | −0.0 | 48% | −0.1 | 49% | −1.2 | −19.6 |

**Read:**

1. **Bull is the only band** with a clear WR and mean lift on this tape.  
2. **Climb / soft_up are ~coin-flip** on 7–14d; 30d climb mean slightly **negative** with **fat left tail** (~−20% p10).  
3. Therefore: **direction ≠ high-probability win rate.** Deploy in the gap must be **small + gated**, not “bull-lite util.”  
4. Short recent window (2025–26 only) was even worse in the upside residual (thin n, weak/negative forwards) — do not promote off that alone.

**Not measured here (required before live sleeve):** basket/ledger expectancy, fees, SL recycle, pair coincidence (ETH/SOL vs XRP-class). BTC path is **posture**, not fill quality.

---

## 4. Proposed boundary architecture

### 4.1 Named layers (replace one transition blob)

| Layer | BTC 30d (defaults; knobs) | Predictability | Cash stance (proposed product) |
|-------|---------------------------|----------------|--------------------------------|
| **bear** | ≤ bear_cut (−10) | bad | **PARK** cap 0 |
| **soft_down** | (bear_cut, −flat] e.g. (−10, −8] | low | **PARK** (narrow; optional) |
| **flat** | \|r\| ≤ flat_cut (8) | range | **Flat-B** already: deploy cap ~$75, tight RSI/sent |
| **soft_up** | (flat, flat+soft_w] e.g. (8, 10] | low–med | **Flat-B or tighter** (same or smaller cap); **not** park-only by default |
| **climb** | (flat+soft_w, bull−pre_w) e.g. (10, 14) | med path, **not** high WR | **Micro climb sleeve**: small cap, **stricter** entry than flat-B, util ceiling |
| **pre_bull** | [bull−pre_w, bull) e.g. [14, 15) | approaching bull | **Step-up micro** (cap between climb and bull); still gated |
| **bull** | ≥ bull_cut (15) | best WR on tape | **Deploy** (existing bull map) |
| **transition_core** (optional residual) | only if cuts leave a hole | **unpredictable** | **PARK** — keep **narrow** |

Operator preference encoded: **narrow** true park-transition; **do not** treat entire +8…+15 as one park.

### 4.2 “High probability of win rate” — operational definition

Do **not** use “BTC 30d > 0” as WR. Use **stacked gates** so cash only moves when multiple filters agree:

| Gate | Climb / pre_bull suggestion (starting point) | Why |
|------|-----------------------------------------------|-----|
| Regime layer | climb or pre_bull only | posture |
| Cap | climb **$40–75**; pre_bull **$75–100**; ≪ bull | kill DD from Jul 27 full-util fail |
| Max util add | climb ≤ **flat util** (e.g. 0.45–0.55); no catch-up spikes | idle cash ≠ mandate to fill |
| RSI | **≤ 55** (stricter than transition policy 58; flat-B uses 55) | avoid chase |
| Sentiment | held ≥ **0.30**; new pair ≥ **0.40** | quality |
| Already-held | prefer **add-to-winner / rank** over new names | reduces |
| Block list | 72h post-SL etc. unchanged | churn |
| Breadth / BTC structure (optional v2) | e.g. BTC above 20d mid or breadth not collapsing | cut failed climbs |
| Shadow bar before live | ≥ **N** climb-day paper fills, Exit WR / expectancy vs park | promote gate |

If gates fail → **hold cash** (correct outcome).  
**Target:** fewer trades, higher **conditional** WR — not higher time-in-market in the gap.

### 4.3 Two structural ways to shrink the “huge band”

| Approach | Mechanism | Pros | Cons |
|----------|-----------|------|------|
| **L1 — Widen flat** | e.g. flat_abs 8 → **10–12** | Absorbs soft-up into known Flat-B path; tiny residual | Flat becomes “mild uptrend” too; dilutes flat meaning |
| **L2 — Lower bull cut** | e.g. bull 15 → **12** | Earlier full deploy; less gap | Bull stats dilute (long tape still OK-ish WR but weaker than 15); more false bulls |
| **L3 — Layers (recommended core)** | keep cuts; **split residual** into soft_up / climb / pre_bull | Matches operator mental model; park only narrow core | More policy surface; needs detector + dashboard labels |
| **Combo** | flat **10** + bull **15** + climb **10–14** + pre_bull **14–15** | Soft-up disappears into flat; climb is the only “up gap” product | Still need climb sleeve design |

**Recommended default product path:** **L3 + mild L1** (flat **10**, soft band absorbed; climb **10→14**, pre_bull **14→15**, bull **15**). True park residual → ~**0–1 pp** if any.

---

## 5. Cogent cash distribution (policy sketch — not applied)

| Layer | strategy_mode | allow_new_buys | rebalance_cap_usd | target_max_util | entry max_rsi | min_sent / new |
|-------|---------------|----------------|-------------------|-----------------|---------------|----------------|
| bear / soft_down | usdc_park | false | 0 | 0.25 | — | — |
| flat | deploy | true | 75 | 0.65 | 55 | 0.25 / 0.35 |
| soft_up | deploy | true | 50–75 | 0.55 | 55 | 0.28 / 0.38 |
| climb | deploy | true | **40–75** | **0.45–0.55** | **52–55** | **0.30 / 0.40** |
| pre_bull | deploy | true | 75–100 | 0.60–0.70 | 55–58 | 0.25 / 0.35 |
| bull | deploy | true | 100–200 | 0.85 | policy bull | policy bull |
| transition_core | usdc_park | false | 0 | 0.30 | — | — |

**Knob map rule:** climb/pre_bull must **not** inherit transition `usdc_hold` cap 0. Today’s bug-class: policy may allow research cap; **knob forces $0**. Layer promote = **policy + knob** together.

**SELLs:** always allowed (unchanged).

---

## 6. What would make this “high WR” vs hope

| Must pass before live climb sleeve | Bar |
|------------------------------------|-----|
| Shadow / paper on climb-labeled days | Expectancy ≥ 0 after fees; DD vs park penalty **≪** Jul 27 util0.45–0.65 fail |
| Conditional Exit WR on climb fills | Report wins/N; no promote on N≪15 |
| vs USDC / park | Beats park on **risk-adjusted** metric, not raw “bought the rip” |
| No auto-promote | `auto_apply: false` until Brad + gates |
| Pair set | BTC posture ≠ auto XRP; use basket gates |

If shadow **fails**, keep park on climb and only ship **labels** (observability) — still better than one blob.

---

## 7. Implementation slices (when staffed)

| ID | Work | Live money? |
|----|------|-------------|
| BL-01 | Detector emits `regime` + `regime_layer` (soft_up/climb/pre_bull/…) | No |
| BL-02 | Policy schema `regimes.climb` / `pre_bull` / `soft_up` + knob keys | No until enforce |
| BL-03 | Dashboard / brief: `transition · climb · MICRO` not only `PARK` | No |
| BL-04 | Shadow runner: log would-buy under climb gates | No |
| BL-05 | Isolation tests for layer boundaries | No |
| BL-06 | Promote climb sleeve (enforce) | **Yes — Brad go** |

Jul 27 trial remains valid for **“deploy whole transition hard” → drop**. This design is **orthogonal**: thin park core + **bounded** climb.

---

## 8. Decision options for Brad

| Option | Action | Fits “narrow trans + some cash when trending”? |
|--------|--------|--------------------------------------------------|
| **A. Labels only** | BL-01+03 — see climb vs soft_up; keep park | Observability first |
| **B. Design + shadow** | A + BL-02/04/05 — measure conditional WR | **Recommended next** |
| **C. Mild cut change only** | flat 8→10 or bull 15→12, still one transition | Shrinks band; no true layers |
| **D. Live climb micro now** | Policy+knob climb cap>0 this week | Fastest powder deploy; **highest risk** without shadow |

**Agent stance:** Prefer **B**. Do **not** set climb = bull util. Do **not** claim high WR in the gap from direction alone — long tape says **bull** is the WR regime; climb is **optionality with a tight leash**.

---

## 9. Numbers to remember

- Live gap width flat→bull: **~7 pp** (8→15).  
- Long-tape climb days: **~145**; soft_up **~75**; pre_bull **~29**.  
- Climb forward WR ~**50% / 46% / 40%** (7/14/30d) — not a high-probability band.  
- Bull forward WR ~**61% / 65% / 59%** — deploy bias belongs here.  
- Prior full transition util raise: **dropped** (DD).  

---

## 10. Related

- Epic defaults: `docs/epics/REGIME_CASH_EPIC.md`  
- Transition drop: `reports/REGIME_TRANSITION_TEST_2026-07-27.md`, DEC 2026-08-17  
- Param sweep candidate (unpromoted): bull10 / bear−8 / flat5  
- Live status: `data/state/regime_cash_status.json`  
- Honesty: offline-strategy-honesty, regime-premise-and-basket  
