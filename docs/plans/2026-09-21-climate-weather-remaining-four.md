# Climate/Weather Remaining Four — Doldrum Staffing Pack

> **For Hermes:** Staff via Kanban + MASTER. Implement only after each card's gates. **No live money knobs without Brad GO.**

**Goal:** During the 30d climate doldrum (bear park), finish the four GO-E residual lanes so sensors and rules are ready when weather turns — catch a strong breeze without rewriting climate from a green day.

**Parent:** `docs/plans/2026-09-21-regime-climate-weather-boundaries.md` (spine shipped `07098d8c`)  
**Epic ID:** `REGIME-CLIMATE-WEATHER-REMAINING-20260921`

**Heinlein law:** Climate = expect (30d REGIME-CASH). Weather = get (7d/14d + breakout/RSI B). Ready for both; weather never silently rewrites climate.

---

## Dependency graph (safe order)

```
CW-1 OHLCV backfill  ─────────────────────────────┐
                                                  ├─→ CW-3 Threshold evidence sweep
CW-2 Hysteresis design (doc)  ────────────────────┤
         │                                        │
         └─→ (optional code later, Brad GO)       │
                                                  │
CW paper B crumbs (already cron)  ────────────────┼─→ CW-4 Live B micro (ARMED path only)
                                                  │      money OFF until Brad GO
```

| ID | Title | Priority | Start | Live knobs? | Assignee |
|----|-------|----------|-------|-------------|----------|
| **CW-1** | BTC daily OHLCV backfill + freshness watch | **P0** | **now** | No | crypto-engineer |
| **CW-2** | Hysteresis rules bear→soft_down→flat (doc) | P1 | **now** (parallel) | No | crypto-analyst |
| **CW-3** | Threshold surgery evidence (−10 / ±8 / +15) | P1 | after CW-1 green | **No write** — evidence packet only | crypto-analyst |
| **CW-4** | Live B micro sleeve path (armed, money OFF) | P1 | after CW-2 + paper B N | Path yes; **orders OFF** | crypto-engineer |

---

## CW-1 — OHLCV daily backfill (sensor hygiene)

**Why first:** Climate/weather board already showed ~18d gap (last full bar 2026-09-02 + live append). Calendar 7d/14d collapsed until bar-preferred fix. Doldrum is the right time to fix the sensor, not during a breeze.

**Done when:**
1. BTC-USD daily cache continuous through today (Coinbase public candles or existing long tape merge).
2. `regime_detector._load_btc_closes` / `regime_climate_weather` report `gap_days_tail ≤ 2` (or honest flag if venue lag).
3. Quiet cron or ops one-call refresh ≥1×/day; isolation test for gap detect.
4. No change to `bear_return_pct` / bands.

**Likely files:**
- `phase6/research/regime_detector.py` (`_load_btc_closes`)
- `data/ohlcv/BTC-USD_1d_coinbase.json` and/or `backtests/data/long/ohlcv_daily_btc.json`
- New: `scripts/phase6/run_btc_ohlcv_daily_backfill.py` + `test_isolation_btc_ohlcv_backfill.py`
- Optional cron wrapper + `docs/HERMES_CRON_SSOT.md`

**Must not:** rewrite REGIME-CASH thresholds; force rebalance; invent prices.

---

## CW-2 — Hysteresis design (doc first)

**Why:** Pure edge flips (−10.0 → soft_down next bar) invite thrash. Design confirm/dwell **before** code.

**Done when:**
1. Doc at `docs/plans/2026-09-21-regime-hysteresis-design.md` with concrete rules for:
   - bear exit confirm (e.g. r > −10 for N days **or** 14d not making LL)
   - soft_down → flat deploy gate
   - what still uses instantaneous band (display) vs money gate
2. Explicit: hysteresis does **not** open full book on green day; B micro remains separate.
3. Table of false-positive / false-negative tradeoffs vs current edge classifier.
4. **NO code** on this card unless Brad GO follow-on.

**Skills:** `regime-premise-and-basket`, `phase6-bull-reentry-timing`

---

## CW-3 — Threshold surgery evidence (measure packet)

**Why:** −10 / ±8 / +15 are convenient, not sacred. Touch only with sweep evidence — never vibe.

**Depends on:** CW-1 (honest horizons) + climate/weather crumbs accumulating.

**Done when:**
1. Offline sweep report comparing alternate bands (e.g. bear −12/−10/−8; flat ±6/±8/±10; bull +12/+15/+18) on long tape:
   - episode dwell mean/med/p90
   - forward 5d/10d/30d path under park vs micro-B counterfactual tags
   - whipsaw count (label flips / 30d)
2. Recommendation enum: `keep` | `propose_scoped_shadow_only` | `no_change_insufficient_N`
3. **`live_promote_allowed: false`** hard in packet
4. Decision shelf only — Brad decides later

**Must not:** patch `config/regime_cash_policy.json` detector bands on this card.

---

## CW-4 — Live B micro sleeve path (armed, money OFF)

**Why:** Job B is the breeze-catcher. Engineering gap = no safe live path even when climate still soft; product gap ≠ “flip climate early.”

**Depends on:** CW-2 design locked; layered paper cron collecting; preferably CW-1 sensors clean.

**Done when (engineering):**
1. Module/CLI mirroring tryout scale-up pattern: dry-run default, `--apply --go --no-dry-run` for money.
2. Hard constraints from frozen spec:
   - bear climate veto still blocks **unless** explicit soft_down/B rules from CW-2
   - cap = $75-class (or current tryout shell), not full ticket
   - breakout ON + RSI ∈ [50,70] (spec SSOT)
   - `live_apply: false` in brad decision state by default
3. Isolation tests; approval ping pattern optional
4. **Zero live orders** without separate Brad GO on decision JSON

**Must not:** auto-promote B; weaken 30d park on this card; open seats from green day alone.

**Spec:** `docs/research/BULL_REENTRY_LAYERED_SPEC.md`

---

## Doldrum framing (operator)

| Metaphor | Meaning |
|----------|---------|
| **30d doldrum** | Climate still bear / park — low FOMO pressure; ideal for sensor + rule work |
| **Strong breeze** | Weather structure + (later) capped B — not “declare flat” |
| **Hurricane law** | Climate park still wins if 30d ≤ −10 |

North star unchanged: fewer wasted park days **and** less process tax — not more green-day buys.

---

## Exit of this pack

Pack complete when CW-1..CW-4 cards **done** (or CW-4 **armed path shipped, money OFF**) and MASTER epic marked ready for Brad GO menu on:
- hysteresis code (optional)
- threshold shadow (optional)
- B money arm (explicit)
