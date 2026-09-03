# Post–basis-fix exit baseline pack — 2026-08-05

**Purpose:** Cleaner **entry / exit / sizing** evidence after invalidating polluted open-MTM and pre-reset shadow TP stats.  
**North star:** better returns **and** less loss — path to **optimal profit-taking**, not thaw-on-hope.

## Evidence hygiene (void vs replacement)

| Class | Status | Replacement |
|-------|--------|-------------|
| Open-bag unrealized % from live_state **before** lot-aware basis (e.g. BTC ~+49% @ ~$43k entry) | **VOID** | Lot basis: BTC entry ~$63k, r ~**+2.6%**; SOL ~flat (not −12%) |
| Shadow TP `would_fire_count` / promo-ready **before** 2026-08-05 ~21:37Z reset | **VOID** | Clean clock: `first_shadow_at` **2026-08-05T21:37:40Z**, would_fire **0** until new honest events |
| Exit asymmetry + TP path study (realized fills + OHLCV path) | **VALID** (trade prices, not open MTM) | Re-run stamped this pack (below) |
| Offline Analyst OPT / WF leaderboards | **VALID** unless a trial used live open % | Keep; do not mass-invalidate |

**Code anchors (basis honesty):**
- `phase6/core/position_cost_basis.py` — FIFO + LIFO-to-exchange-qty  
- Runner `_write_dashboard_cache` + `recompute_trading_positions_pnl`  
- `shadow_tp.resolve_entry` prefers tagged/`ledger_*` basis; peak sanitize on basis repair  

---

## Pack A — Exit asymmetry (30d, realized)

**Report:** `reports/EXIT_ASYMMETRY_2026-08-05.md`  
**State:** `data/state/exit_asymmetry_latest.json`

| Metric | Value |
|--------|------:|
| Realized WR | **7.5%** (5/67) |
| Sum realized PnL | **−$100.14** |
| SL exits | **56** · WR 0 · **−$137.30** |
| Rotation exits | **5** · WR 100% · **+$37.73** |
| Rebuy after SL ≤24h / 48h / 72h | **2 / 10 / 20** |
| Diagnosis | `exit_asymmetry_sl_dominated` |

**Plain English:** Almost all closed risk is **stopped out small**; almost no **banked winners**. Rotations are the only green exit class in-window. Re-entry after SL is still common (churn).

**Implication for profit-taking:** The structural hole is **missing take-profit surface**, not “SL broken.” Fixing TP without fixing **anti-rebuy / entry quality** still recycles losses.

---

## Pack B — TP / trail path study (60d, counterfactual)

**Report:** `reports/TP_TRAIL_PATH_STUDY_2026-08-05.md` (+ `.json`)  
**State:** `data/state/tp_trail_path_study_latest.json`  
**Enum:** `design_shadow` · **live writes: false**

| Metric | Value |
|--------|------:|
| Matched rounds / usable path legs | 87 / **52** |
| Loss legs | 46 |
| Baseline sum r (realized path sample) | **−1.35** |
| CF fixed TP +6% if touched (sum r) | **+1.05** (Δ ~**+2.40** vs base) |
| CF **rescue** (TP only if later loss + path hit +6%) | **+1.05** (Δ ~**+2.40**) |
| CF trail sum r | **+0.27** (Δ ~**+1.62**) |
| Path hit ≥+6% rate | **~58%** |
| Losses that still touched +6% (**rescue rate**) | **27/46 ≈ 59%** |
| Mean realized r / mean max favorable r | **−2.6%** / **+7.2%** |

**Plain English:** On many losing legs, price **did** print a +6% opportunity before the SL. That is the **profit-taking gap** — directionally supports **shadow fixed-TP / trail research**, not an instant live flip.

**Caveats:** Daily bars slightly overstate ease of banking TP; ~30 legs skipped (no OHLCV). Do **not** set live `take_profit` without Brad + clean shadow days on **honest** basis.

---

## Pack C — Clean shadow TP clock (live instrument)

| Field | Value |
|-------|------:|
| Mode | shadow |
| first_shadow_at (post-reset) | **2026-08-05T21:37:40Z** |
| would_fire_count_total | **0** (reset; junk peaks discarded) |
| Open marks | Lot basis (BTC ~+2.6%, not +49%) |
| Promo ready | **false** until days + honest events gates |

**Gate to even discuss live TP:** shadow days ≥ policy (e.g. 7) **and** ≥5 **post-reset** would-fire events with lot-tagged entries — then human review only.

---

## How this moves entry / exit / sizing (structure map)

| Layer | Current baseline signal | Cleaner structure direction | Now? |
|-------|-------------------------|----------------------------|------|
| **Exit** | SL-dominated; thin TP | Shadow fixed TP (+6% class) and/or trail; bank path opportunities | **Shadow only** — pack B supports design |
| **Entry** | Rebuy after SL common | Keep near-stop add block, SL cash-hold, regime flat $75; no force_rebal on DD | **Gates live** — do not widen |
| **Sizing** | Micro / flat B | No size-up until 14D stabilize + exit stack not SL-only | **No thaw** |
| **Scoreboard** | Was lying open MTM | Lot basis for open book + shadow r | **Fixed 2026-08-05** |

### Optimal profit-taking — go / no-go (this pack)

| Decision | Call | Why |
|----------|------|-----|
| Live take-profit / trail | **NO** | Shadow clock just reset; need honest would-fires |
| Keep shadow TP collecting | **YES** | Rescue ~59% is the best exit-side lead in this pack |
| Claim “recovery / size up” | **NO** | 14D still soft-red; exit WR ~7–11% SL-heavy |
| Treat path CF as proof of edge | **NO — design only** | Counterfactual on daily bars; use to **prioritize** shadow, not auto-promote |
| Void old open-MTM / old shadow totals | **YES** | This pack + post-reset shadow replace them |

---

## Recommended sequence (profit-taking path)

1. **Hold entry gates** (regime cash, $75, near-stop block, no force_rebal on DD).  
2. **Run clean shadow TP ≥7d** on lot basis; require real would-fire sample.  
3. **Optional next research (not live):** finer bar path study if daily overstates; pair-level rescue rates.  
4. **Sizing / OPT promote** only after exit stack shows less loss (higher exit WR or banked TP share) **and** 14D ≥ flat.  
5. **Human OK** before any `take_profit.mode=live`.

---

## Artifact index

| Artifact | Path |
|----------|------|
| This pack | `reports/POST_BASIS_FIX_EXIT_BASELINE_PACK_2026-08-05.md` |
| Pack JSON | `data/state/post_basis_fix_exit_baseline_pack_latest.json` |
| Exit asymmetry MD | `reports/EXIT_ASYMMETRY_2026-08-05.md` |
| Path study MD/JSON | `reports/TP_TRAIL_PATH_STUDY_2026-08-05.md` / `.json` |
| Shadow status | `data/state/shadow_tp_status.json` |
| MASTER stamp | `P6-EXIT-BASELINE-POST-BASIS-FIX-20260805` |
