# Squeeze → regime → confirm breakout (research)

**Status:** OPEN — research + paper only  
**Opened:** 2026-08-19  
**Trigger:** Brad + Grok dialog — language for gaps in timing methodology  
**MASTER:** `P6-RESEARCH-SQUEEZE-REGIME-BREAKOUT-20260819`  
**Code:** `phase6/research/squeeze_regime_breakout.py`  
**Bake-off:** `phase6/research/run_squeeze_regime_breakout_bakeoff.py`  

---

## Plain English

We already detect **some** breakouts (BTC 30d high sticky machine) and **some** participation (B4 volume-expand greens).  
What we lacked language for:

1. **Compression / coil** before the break (setup)  
2. **Regime-conditioned direction** (bull trusts upside more; range needs stricter confirms; bear distrusts upside)  
3. **Confirmation stack** so a wick outside a range is not a signal  
4. Link from **coil → expansion** into cash re-risk / breadth (not only “already green”)

North star: better timed small deploys + fewer fake breaks — **not** a new live strategy until bake-off clears.

---

## Priority scope (frozen v1)

### High
| ID | Piece | v1 definition |
|----|--------|----------------|
| H1 | Compression | BB width (20,2) at ≤20th percentile of trailing 100 bars **or** TTM-style: BB(20,2) inside KC(20,1.5×ATR) |
| H2 | Regime gate | Same family as layered: bull / bear / flat / transition from BTC 30d |
| H3 | Confirm | Close outside prior N-bar range **and** volume ≥ 1.5× SMA20 **and** ATR(14) rising vs ATR SMA20 |

### Medium
| ID | Piece | v1 definition |
|----|--------|----------------|
| M1 | Efficiency | Break candle body / range ≥ 0.55 (reject wick-dominated) |
| M2 | Coil→B4 path | Compression within last 5 bars **then** B4-style vol-expand cluster (or B1b) — paper cash-rerisk alt trigger |

### Explicitly out of v1
Pattern zoo (flags/triangles library), open interest, multi-TF dashboards, live runner hooks, membership seat gates.

---

## Direction bias by regime

| Regime | Prefer | Flat/range extra |
|--------|--------|------------------|
| bull | Upside breaks | — |
| bear | Downside breaks; upside = trap unless exceptional confirm | — |
| flat | Either side only with **full** confirm (H3+M1); else skip | Require retest optional v2 |
| transition | Treat like flat (strict) | — |
| bear veto (30d ≤ −10%) | No long sleeve (align layered) | Shorts not in scope for book |

Squeeze alone never opens size. Confirm + regime required for a **timed entry candidate**.

---

## Arms to score (bake-off)

| Arm | Rule |
|-----|------|
| C0_breakout_sticky | Current layered breakout ON (control) |
| C0b_breakout_rsi | C0 + RSI∈[50,70] (layered re-entry) |
| H_squeeze_only | Compression ON — no trade (setup rate only) |
| S1_squeeze_break_confirm | Compression recent + upside break + H3 |
| S2_regime | S1 + regime allows direction |
| S3_regime_eff | S2 + M1 efficiency |
| S3b_regime_eff_rsi | S3 + RSI∈[50,70] |
| M2_coil_then_b4 | Coil last 5d + B4 fire → long EW liquid (Path A link) |
| BH_always_long | Always long BTC or EW liquid control |

Metrics: 1d/3d/7d mean ret vs cash, hit rate, false-break rate (break then 3d ret opposite), N, regime slice.

**exploit_ready** only if best arm beats C0b and BH on 7d with N≥40 and not only one regime.

---

## Separations

| Track | Role |
|-------|------|
| This research | Entry *timing quality* |
| B4 / cash re-risk | Participation when cash-idle + market expanding |
| Membership M0–M3 | Seat quality — **no** squeeze required |
| Pair RSI/sent | Deploy gates after sleeve on — unchanged |

---

## Paper policy (frozen Brad 2026-08-19)

| Role | Arm | Stance |
|------|-----|--------|
| **Paper primary** | **M2** coil→B4 | Small-gain Path A companion; enough N (~39) for provisional paper use vs cash — **not** live |
| **Paper challenger** | **S3** regime+eff | Higher point estimate; **challenge only** when S3 **N≥40** (prefer multi-asset) **and** 7d still ≥ M2 / stable on two slices |
| **Control** | C0 / C0b / BH | Keep scoring; do not silently replace layered live breakout |
| **Live** | — | **Off** until Brad go + exploit bar |

Do **not** swap primary to S3 on N≈10. M2 stays default paper path until challenger clears the bar.

### Anti-starvation (frozen Brad 2026-08-19)

**Lesson:** High hit-rate + tiny N (e.g. family Fib book ~12 trades / 5 mo) cannot be optimized or trusted — looks like +80%, is mostly small-sample story.

| Rule | Practice |
|------|----------|
| **Ladder filters, don’t stack all at once** | Base (coil/vol/close) stays loose enough to feed N; stricter arms (eff, RSI, retest, ATR buffer) are **siblings scored in parallel**, not nested gates that kill the parent sample |
| **Never promote on hit-rate alone** | Need **N floor** (paper challenge ≥40; live talk much higher + stability) **and** mean excess vs cash/control |
| **Retest / multi-close = optional arms** | S4-style filters must not become the only path; if they fire &lt;~1–2×/month on daily BTC, they’re diary entries not optimizers |
| **Prefer multi-asset / longer tape for N** | Before adding another AND-clause, widen universe (ETH/SOL/liquid) or horizon |
| **M2 keeps primary partly because it has N** | Don’t replace M2 with a prettier thinner arm |
| **Log fat, decide thin** | Keep permissive shadow logs; promote only arms that clear N+edge |

**Smell test:** If a “better” filter cuts N by &gt;50% and 7d mean doesn’t clearly improve vs parent, **keep parent**, park child as research.



## Non-goals

Live orders; replace layered spec silently; pattern ML; claim 60–80% fail-rate as our calibrated number.
