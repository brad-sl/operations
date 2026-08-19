# Bull re-entry — layered strategy (frozen spec)

**Status:** RESEARCH / SHADOW-CANDIDATE ONLY  
**Frozen:** 2026-07-30  
**Owner:** Crypto-Analyst  
**Related trial:** `ANALYST-REGIME-FLAT-KNOBS-20260730` (+ dig-further layered arm)  
**Stress artifact:** `data/state/analyst_breakout_reentry_stress_latest.json`  
**Code (timing + offline sim):** `phase6/research/bull_reentry_layered.py`, `scripts/phase6/run_breakout_reentry_stress.py`

---

## Problem

The live **BTC 30d ≥ +15%** rule is a **conservative size/weather gate**, not an opportunity timer.

- Typical breakout-style upside legs on our BTC tape: **~8–30 days** (median ~16d).
- Strict 30d/+15% bull labels: **~6–7%** of days — rare / late.
- Goal: catch **more** non-bear upside structure **without** full-book bull churn.

North star: **better returns and less loss.**

---

## Non-goals

- Replace REGIME-CASH with RSI-only or 5d qualify ⇒ bull.
- Breakout at **$200** as default re-entry size (full-sample stress hurt).
- Silent edits to `regime_cash_policy.json` / live runner without Brad + gates.
- Claiming Path B sleeve sim = live ARCH-4 + pair RSI/sent + SL.

---

## Layered policy (canonical)

Evaluate **once per rebalance cycle** (or daily status job). BTC is the timing asset.

| Priority | Condition | Action (crypto sleeve cap) | Mode |
|----------|-----------|----------------------------|------|
| 0 | **Bear veto:** BTC 30d return ≤ **−10%** (or detector `bear`) | **$0** — no new buys | `usdc_park` |
| 1 | **Size-up:** BTC 30d return ≥ **+15%** (detector `bull`) | **$200** (bull envelope) | deploy; prefer existing bull knobs / rotation shadow only if separately gated |
| 2 | **Re-entry:** breakout **ON** AND BTC RSI(14) ∈ **[50, 70]** AND not bear | **$75** (flat option B size) | deploy; **rebalance** not rotation |
| 3 | Else (`transition`, weak structure, RSI out of band) | **$0** (or keep current transition park) | park |
| — | Detector `flat` **without** re-entry trigger | Live **flat B** still allowed: cap **$75**, pair RSI≤55, sent≥0.25 | unchanged live flat path |

### Breakout definition (frozen)

- **ON:** daily close makes a **new 30d high** (vs prior 29 days) **and** BTC **14d return > 0**.
- **OFF:** close **&lt; 20d low** **or** BTC **14d return &lt; −5%**.
- State is sticky between ON and OFF (same machine as stress harness).

### RSI band (frozen)

- **BTC** Wilder/SMA-14 style RSI as in `bull_reentry_layered.py`.
- Band **[50, 70]** = “positive but not blow-off.”  
- RSI **&gt; 70** does **not** open re-entry (chase guard).  
- RSI **&lt; 50** does **not** open re-entry.

### Pair gates (live, when sleeve on)

When cap &gt; 0 and `allow_new_buys`:

- Keep live pair gates: **RSI ≤ 55**, **sentiment ≥ 0.25** (flat B fingerprint), lockout clear.
- Re-entry layer does **not** relax pair gates.

### Allocator

- Re-entry ($75): **`rebalance`**, not `rotation`.
- Size-up ($200): existing bull path / separate shadow (`defensive_rotation_21d`) — **not** auto-on from breakout alone.

---

## Relation to BTC 30d/+15%

| Role | Rule |
|------|------|
| Opportunity timer | **Breakout + RSI band** (layer 2) |
| Hard risk-off | **Bear veto** (layer 0) |
| Larger risk OK | **30d ≥ +15%** (layer 1) — confirmation to **size up**, not the only door |

Do **not** lower 30d bull threshold to “catch short bulls” until this layer is proven in shadow.

---

## Evidence so far (2026-07-30 stress)

Harness: EW sleeve btc/eth/sol/avax/link/doge/arb; cap = policy; idle USDC 3.5%; light fees. Gaps: no pair RSI/sent/SL.

| Finding | Implication |
|---------|-------------|
| Breakout @ **$200** full-sample **negative** | No full-size breakout flip |
| Breakout @ **$75** milder DD | Size matches flat B |
| Layered (bear + brk&RSI@$75 + 30/15@$200) **beats current** on full_sample / flat_chop / recent | Shadow candidate |
| Current REGIME-CASH still edges **live_overlap** return | No live promote yet |
| Flat trial: rebalance &gt; rotation under $75 | Re-entry uses rebalance |

---

## Success metrics (for dig / shadow)

Windows (shared): `full_sample`, `bull_ex`, `bear_stress`, `flat_chop`, `recent`, `live_overlap`.

**GO shadow** if:

1. Layered total return on **full_sample** ≥ current − 0.25pp **and** maxDD not worse by &gt; 2pp, **or** clearly better DD with ret within 0.5pp; **and**
2. **Bear** maxDD not worse than current by &gt; 3pp; **and**
3. **live_overlap** not a disaster (ret ≥ current − 1pp **or** DD clearly better); **and**
4. `live_param_audit` fail_count = 0, confidence ≥ 0.85; **and**
5. No live policy write in trial — shadow overlay only.

**GO live** only after Brad + shadow hold + promotion gates (separate).

---

## Implementation map

| Piece | Path |
|-------|------|
| Pure signals + policy caps | `phase6/research/bull_reentry_layered.py` |
| Offline multi-window stress | `scripts/phase6/run_breakout_reentry_stress.py` |
| Flat + layered dig report | `phase6/research/run_regime_flat_knobs_dig_layered.py` |
| Ready bull size-up shadow (inactive) | `config/shadow_overlays/BULL-DEFENSIVE-ROTATION-21D.ready.json` |
| Activate size-up only when gates pass | `scripts/phase6/activate_bull_defensive_rotation_shadow.py` |

Live wire (future, not this freeze): optional call from `regime_cash_policy.apply_to_runner_plan` **behind a feature flag** default off.

---

## Decision log

| Date | Decision |
|------|----------|
| 2026-07-30 | Freeze layered spec; dig-further on flat knobs trial; **no live change** |
| 2026-07-30 | 5d+RSI full bull flip rejected (offline BTC paths) |
| 2026-07-30 | 30d/+15% retained as size-up only |
| 2026-07-30 | **Paper shadow ON** (log-only). Live sleeve **deferred** until `STOCH-RSI-PARALLEL-20260721` leaves RUNNING and not before **2026-08-04** — live re-entry would change fill/SL sample and confound Stoch. Ready: `LAYERED-REENTRY-FLATB-75.ready.json`. Cron paper `746aa3a9f77c` 08:00/20:00; live gate check `9ababe2d2091` once 2026-08-04. |

---

## Change control

Edits to breakout params, RSI band, or caps require:

1. Re-run `run_breakout_reentry_stress.py` + dig script  
2. Update this doc “Frozen” date and decision log  
3. Brad OK before `enforce` path uses the layer  
