# Market breadth / multi-pair momentum breakout — research project

**Status:** OPEN — research + paper shadow only  
**Opened:** 2026-08-19  
**Trigger case:** Broad green day (BTC/ETH/SOL/XRP/LINK/… + outsiders ZEC/HYPE) while book ~83% cash; only LINK (+UNI) rode size. BTC rotation exit 2026-08-16 left ~$168 MTM on table into the bounce.  
**MASTER:** `P6-RESEARCH-BREADTH-MOMENTUM-BREAKOUT-20260819`  
**Related:** `docs/research/BULL_REENTRY_LAYERED_SPEC.md` (BTC-only timer), `docs/research/CASH_RERISK_AFTER_ROTATION_SHADOW_RULE.md` (deploy gate shadow), `phase6-pair-discovery` (membership vs capital)

---

## Plain English problem

When **many high-value pairs move up together**, that is usually **market momentum / breakout**, not a single-name fluke.

We missed most of one of those days because:

1. **Capital** was in cash after rotations (BTC Aug 16, SOL earlier), not because those names left the basket.  
2. **Membership** never promoted shadow winners (ZEC/HYPE paper arms) — but even *inside* the basket we did not re-risk.  
3. Existing **BTC 30d/+15%** and **layered breakout** tools are **single-asset timers**. They do not explicitly say: “breadth is on across majors — sitting 80% cash is the mistake.”

**North star:** better returns and less loss — catch **shared** upside structure without chasing every pump.

---

## Research questions

| # | Question | Success looks like |
|---|----------|-------------------|
| Q1 | What **indicator family** would have flagged this multi-pair run **in time** to matter (same day / prior session)? | Clear ON/OFF on historical episodes; not only this one day |
| Q2 | Can we **exploit** it with small, gated size — or is it mostly hindsight beta? | Shadow EV > cash / control on long tape; N mature; less-loss OK |
| Q3 | How does this interact with **basket rotation** (ZEC/HYPE-class adds) vs **cash re-risk into existing majors**? | Two levers scored separately; no conflation |
| Q4 | Failure modes? | Blow-off tops, single-name pumps, bear rallies, fee drag on tiny sleeves |

---

## Indicator candidates (to rank offline)

Do **not** pick a winner from the case study alone. Score each on: hit rate on breadth days, false alarms in chop, lead/lag vs BTC, implementability on our free data.

| ID | Family | Sketch | Data cost |
|----|--------|--------|-----------|
| **B1 Breadth thrust** | Count of majors with 24h ret > +X% (or > BTC) | e.g. ≥4 of {BTC,ETH,SOL,XRP,LINK,AVAX,DOGE} green > +3% | Free candles/stats |
| **B2 Median basket ret** | Median 24h/3d ret of active basket (or liquid 10) | Median > +Y% and BTC 14d > 0 | Free |
| **B3 BTC breakout + breadth confirm** | Existing layered breakout ON **and** breadth ≥ k | Reduces lone-BTC false breaks | Free |
| **B4 Volume expansion cluster** | ≥k names with 24h vol > 1.5× 7d median vol **and** ret > 0 | “Participation” not just price | Free `/stats` |
| **B5 Risk-on vs stables** | Majors up while USDT/USDC dominance flat; optional BTC.D down | Regime texture | Partial |
| **B6 Discovery energy cluster** | ≥2 promote-eligible contenders with quality > q same run | Ties to rotation policy | Already have pipeline |
| **C0 Control** | No signal — stay cash policy | Baseline | — |

**Out of scope for v1:** paid sentiment on 300 names, order-book micro, leverage funding as primary (optional later sleeve).

**Explicitly weak alone (already stressed):** 5d+RSI full bull; breakout @$200; 30d/+15% as sole door.

---

## Two exploit paths (score separately)

### Path A — Cash re-risk (capital, same basket)

When breadth ON and cash fraction high and majors **not** 72h blocked → paper **partial deploy** into sticky/core or top in-basket scores (rebalance, small cap).

→ Shadow rule: `docs/research/CASH_RERISK_AFTER_ROTATION_SHADOW_RULE.md`

### Path B — Rotation into winners (membership)

When outsiders (ZEC/HYPE/…) clear discovery + cycler gates on a breadth day → paper **1:1 swap** vs weak flat active (existing pool_cycling + select arms CF).

→ Feeds `GAP-10` basket CF long-tape + select arms; **no live promote** until arms beat `control_no_swap`.

**Encouraging signal from this episode:** shadow arms already named **HYPE** and **ZEC** while live stayed put — rotation *policy surface* is alive; need CF proof, not vibes.

### Path B realism ladder (do not skip layers)

**Bag policy (Brad 2026-08-19):** optimize fixed bag via 1:1 swap — **not** expand.  
Inbound needs **heightened potential**, **not** buy-today (RSI+sent).  
Canonical: `docs/research/MEMBERSHIP_HEIGHTENED_POTENTIAL_BOUNDARY.md` · `phase6/core/membership_potential_gate.py`

| Layer | Question | Role |
|-------|----------|------|
| **M0–M3** | Bag + inbound potential + eject + delta | **Membership boundary (code)** |
| **L1 path CF** | ADD price vs REMOVE if held | Evidence for selector skill |
| **D0 deploy** | RSI/sent/block/cash buy now | **Not** a seat requirement |

Cash-idle BTC (already in basket) = capital miss. ZEC/HYPE paper = membership surface until M0–M3 + CF mature.  
**Anti-pattern:** require deploy-ready to optimize the bag; treat promote as a fill.

---

## Case study seed (2026-08-19 tape)

| Fact | Value |
|------|--------|
| Book | ~$2.43k NAV, ~$2.03k cash (~83%) |
| Risk held | LINK ~$246, UNI ~$77, PAXG ~$80 |
| BTC exit | 2026-08-16 rotation @ ~$63.1k, +$2.18 realized; mark ~$68.4k → ~**$168** missed on that clip |
| Live swaps | **none** |
| Paper arms | ARB→VVV; RAVE→HYPE; RAVE→ZEC; XRP→HYPE |
| Discovery promote-eligible | PUMP, HBAR, APR, VVV (PRCL braked) |

Artifacts: `data/state/breadth_cash_rerisk_case_20260819.json`, runner `scripts/phase6/run_breadth_cash_rerisk_case_20260819.py`

---

## Method (honest)

1. **Define episodes** on Coinbase daily/hourly: “breadth day” labels from B1–B4 candidates (no peek at our PnL when labeling).  
2. **Counterfactuals** equal-notional: cash hold vs Path A sleeve vs Path B paper swap; horizons 1d/3d/7d.  
3. **Gates:** bear veto (reuse layered −10% 30d), 72h buy block, max sleeve $75 first (align flat B), fees.  
4. **Decide:** modify / kill / shadow-continue — N floors like basket CF (e.g. 7d N≥8).  
5. **Live:** Brad only after paper + no trial interference.

Less-loss and “did not die in chop” matter as much as catch-rate.

---

## Deliverables checklist

- [x] Research charter (this doc)  
- [x] Cash re-risk shadow rule (paper)  
- [x] Case JSON for 2026-08-19 miss  
- [ ] Offline indicator bake-off report (`reports/BREADTH_MOMENTUM_BAKEOFF_*.md`)  
- [ ] Paper watcher cron (log-only would-fire) — after bake-off picks a primary  
- [ ] Link results into bull layered paper shadow / basket arms scoreboard  

---

## Non-goals

- Auto-buy on green Coinbase homepage  
- Live basket promote from discovery scores alone  
- Replacing layered BTC re-entry — **breadth is a confirm / cash-idle alarm**, not a full regime rewrite on day one  

---

## Owner notes

Brad 2026-08-19: treat as missed opportunity on multi-pair run; want **shadow rule + research** (“what indicator, can we exploit”); rotation of two winning outsiders is **encouraging** for membership policy even though live did not fire.
