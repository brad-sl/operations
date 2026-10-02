# Tryout Lifecycle Process (SSOT)

| Field | Value |
|-------|--------|
| **ID** | `FEAT-TRYOUT-LIFECYCLE-PROCESS-2026-10` |
| **Status** | `ACTIVE` · living process map (operator law for *shape*; money still config + Brad GO) |
| **Class** | FEAT / PROCESS |
| **Owner** | Brad + platform |
| **Updated** | 2026-10-01 (B–G simplify ship) |
| **Mission** | Less process tax, more recycled powder on real scale paths — trust before alpha claims |
| **Companions** | [`CRYPTO_PROCESS_LIFECYCLE.md`](./CRYPTO_PROCESS_LIFECYCLE.md) (book-level) · [`Internal_Trading_Platform_FAQ.md`](../faq/Internal_Trading_Platform_FAQ.md) (glossary) · [`TRUST_FIRST_TRADING_ENGINE.md`](../sop/TRUST_FIRST_TRADING_ENGINE.md) · skill `phase6-risk-sizing-research` · cron SSOT `docs/HERMES_CRON_SSOT.md` |
| **Live config** | `config/regime_cash_policy.json` → `quality_tryout` · `config/tryout_scale_up.json` · `config/tryout_scale_window.json` · `config/exit_automation.json` · `config/trading_config_phase6.json` → `run_lifecycle.dual_peak_exit` · `config/tryout_decision_discipline.json` |
| **Supersedes for tryout bag flow** | Scattered plan notes + stale FAQ numbers ($75×2). Book-level stages still live in `CRYPTO_PROCESS_LIFECYCLE.md`. |

---

## 0. One-line product rule

A **tryout bag is a timed option on kindling** (one mid-flight add), not a mini-position to babysit until SL.

```text
Door → dual-clear seat → $shell + SL → prove scale path OR exit → recycle powder
```

If the scale window closes before a live add, **full shell exit** is the correct product move. Riding dead kindling is inventory tax.

---

## 1. Live numbers (verify config — do not trust stale prose)

| Knob | Live (2026-10-01) | Where |
|------|-------------------|--------|
| Shell size | **$25** `abs_cap_usd` | `regime_cash_policy` → quality_tryout |
| New seats / UTC day | **6** (USDT/stables excluded from burn) | same |
| Max open tryout seats | **6** | same |
| First-fill concurrent | **6**, min_move **$25** | `trading_config_phase6` → first_fill_probation |
| Sent floor (tryout) | **≥ 0.30** (quality sleeve) | qualify + latch |
| RSI door | baseline **55**; soft-up proof **65** until door expiry | quality_tryout.v2 |
| Soft-up door package | thaw + RSI65 + latch **180m** → **2026-10-06 21:00 PT** | quality_tryout.v2 windows |
| Kindling step | **+$25**, max total after step **~$100** | `tryout_scale_up.json` |
| Kindling bar (money) | hold≥**2h**, R **+0.8%…+3.5%**, phase **1–2**, structure OK, dwell **2** daily bars | profile `live_signal` |
| Scale-window eject | measure board ON; **`live_apply: false`**; operator `--go` OK | `tryout_scale_window.json` |
| Decision discipline | **shadow** (`live_apply: false`) | `tryout_decision_discipline.json` |
| Knife filter | **shadow** | luck ladder R1 |
| Trail / fixed TP | trail arm **+4%** / trail **2%**; fixed **+6%** fallback | `exit_automation.json` |
| Dual-peak | live; meat gate peak/green **≥4%**; max 1 trim/lot | `dual_peak_exit` |
| Perma-block | rare scars only (RAVE/UNI) | `buy_block_pairs` |

**Stale doc debt:** FAQ / lifecycle still mention **$75 / max 2 seats** in places. **This file + live config win.**

---

## 2. State machine (one bag)

### 2.1 States

| State | Meaning | Money |
|-------|---------|--------|
| `DOOR_ELIGIBLE` | May compete; not held | $0 |
| `CANDIDATE` | Dual-clear rank win this cycle | $0 until fill |
| `SHELL_OPEN` | Filled tryout; SL on; lot registered | ~$25 |
| `KINDLE_PENDING` | Meets live_signal bar; plan row / approval card | still ~$25 until apply |
| `KINDLED` | One live add filled (`live_scaled=true`) | ~$50 band |
| `CARE_NORMAL` | Held under SL/TP/dual-peak (tryout or kindled) | lot size |
| `WOULD_EJECT` | Scale path dead; board flags; **not yet flat** | still held |
| `EXITING` | Protected market exit in flight | transition |
| `CLOSED_*` | Flat + attributed | $0 |
| `GHOST_REGISTRY` | Lot file row without live bag | **bug / tax** — never money |

**Closed reason taxonomy (target):**

| Code | Trigger family |
|------|----------------|
| `CLOSED_SL` | Exchange stop |
| `CLOSED_TP_TRAIL` | Trail / fixed TP software |
| `CLOSED_DUAL_PEAK` | Dual-peak / extension trim→flat |
| `CLOSED_SCALE_WINDOW` | Dead kindling eject |
| `CLOSED_OPERATOR` | Manual / GO unwind |
| `CLOSED_DUST` | Residual sweep |
| `CLOSED_OTHER` | Must explain in crumb — avoid silent soup |

### 2.2 Allowed transitions

```text
DOOR_ELIGIBLE
  → CANDIDATE          [composer / first_fill qualify]
  → (stay / drop)      [gates fail]

CANDIDATE
  → SHELL_OPEN         [TryoutSeatBuy fill + SL + register_tryout_open_lot]
  → DOOR_ELIGIBLE      [limit miss / seat full / kill]

SHELL_OPEN
  → KINDLE_PENDING     [live_signal bar true]
  → CARE_NORMAL        [held; bar not yet / not forever]
  → WOULD_EJECT        [scale-window judgment]
  → CLOSED_*           [SL/TP/dual-peak/operator before scale decision]

KINDLE_PENDING
  → KINDLED            [--apply --go one step]
  → SHELL_OPEN         [bar flips off before apply]
  → WOULD_EJECT        [window dies while waiting on GO]
  → CLOSED_*

KINDLED
  → CARE_NORMAL        [default after add]
  → CLOSED_*           [exits; no second kindling under current product]
  → (no WOULD_EJECT on “never scaled”)  [already used option]

WOULD_EJECT
  → EXITING            [operator --go | future auto live_apply]
  → SHELL_OPEN         [only if judgment false on re-eval — rare]
  → CLOSED_SCALE_WINDOW

EXITING
  → CLOSED_*           [fill + mark lot + cooloff + dwell/discipline outcome]
  → CARE_NORMAL        [FAILED exit — P0 naked/partial; escalate]

GHOST_REGISTRY
  → purged             [exit hooks must clear; board must ignore]
```

### 2.3 Hard fences (all states)

1. **No naked bag** — SL missing on actively traded tryout = P0 escalate (monitor + auto-repair).
2. **Ballast never tryout-eject** — BTC/ETH/PAXG/USDC paths out of scale-window money.
3. **BookRebalance does not mint tryout seats** — seats = `TryoutSeatBuy` / first_fill intake only.
4. **Grow ≠ Open** — kindling is one add on held shell; not a new door.
5. **Money arms (Brad GO 2026-10-01 ON)** — scale-window auto-eject, scale-up autonomous kindling, discipline live_apply, knife live_gate. Kill files still freeze each path. 7d anomaly monitor through ~2026-10-08.
6. **Perma-block rare** — funnel (tier/thaw/missfire/novelty/post-SL/regime) is default toxicity filter.
7. **Paper MTM ≠ fill PnL** — no FOMO size from Paper %.
8. **`live_scaled` is money truth** — `paper_scaled` never blocks or proves live kindling alone.

---

## 3. End-to-end strip (code map)

### 3.1 Qualify → Open (intake)

```text
eligible doors (quality_tryout.v2 + thaw + force_eligible + hard/missfire)
  → RSI wash (door max_rsi; event path optional)
  → sent real (paid X / latch ≥ floor)     [knife live_gate ON — primary arm rsi_reclaim can skip seat]
  → rank / seat headroom (day + concurrent)
  → limit-first $shell
  → SL attach fail-closed
  → register_tryout_open_lot (bag identity)
```

| Piece | Module / surface | Status |
|-------|------------------|--------|
| Door scoreboard | `recovery_tryout_qualify.evaluate_pair_tryout` | LIVE |
| RSI-event + X probe + seat | `rsi_event_tryout_seat_composer` → `TryoutSeatBuyAction` | LIVE path; cron money OFF unless GO flags |
| Decision discipline | `tryout_decision_discipline` on composer candidates | **LIVE** (Brad GO 2026-10-01) |
| Knife live gate | `knife_filter` → composer skip on primary arm deny | **LIVE** (`config/knife_filter.json`) |
| First-fill size/seat cap | `first_fill_probation.filter_trade_plan_first_fill` | LIVE (rebalance ADD path) |
| Limit-first | `entry_execution.limit_first` | LIVE pilot |
| Lot register | `tryout_scale_up_shadow.register_tryout_open_lot` | LIVE on seat buy |

**Two intake mouths (honest):**

1. **Event seat** — RSI wash → composer → one-pair `TryoutSeatBuy` (preferred “system loop”).
2. **Rebalance first-fill** — plan ADD under first_fill probation caps.

Same shell economics; different clocks. Product debt: operators still see two stories.

### 3.2 Care (held shell)

| Layer | Job | Status |
|-------|-----|--------|
| Exchange SL | Hard floor | LIVE + naked auto-repair |
| Trail / fixed TP | Bank progress | LIVE (`live_market_exit`) |
| Dual-peak / extension | Structure+sent fade; **≥4% meat** | LIVE |
| Rebalance held weights | Trim/top **held** only | LIVE (no new tryout invent) |
| Post-exit cooloff | TP 24h structure-aware; SL policy; eject 6h pair | LIVE where wired |
| Dwell / discipline outcome | Attribute closed RT | PARTIAL (hooks uneven) |

### 3.3 Grow (kindling)

```text
open lot in shell band
  → live_signal bar (phase 1–2, structure, R band, hold, dwell)
  → plan row (approval cron TG)
  → Brad/CLI --apply --go --no-dry-run
  → mark live_scaled; one step only
```

| Piece | Module | Status |
|-------|--------|--------|
| Shadow CF / measure | `tryout_scale_up_shadow` profile `measure` | SHADOW measure |
| Live plan | `tryout_scale_up_live` / `live_signal` | ARMED |
| Approval cron | `phase6-tryout-scale-up-live-approval` | LIVE plan-only TG |
| Apply money | CLI `--apply --go` | ARMED · not auto |
| Auto arm ladder | `tryout_scale_up_ladder` | OPTIONAL · gated |

### 3.4 Scale-window kill (missing link — now shipped measure)

```text
open tryout lot, not live_scaled, not ballast, on-book
  → phase ≥ eject_phase (3+) OR structure break OR dead/neg sent
     OR hold ≥ max_hold_hours_no_scale OR structure unknown too long
  → would_eject
  → board TG (12h fp) · operator eject --go
  → protected_market_exit full shell · no cash-hold · cooloff · mark lot
```

| Piece | Module | Status |
|-------|--------|--------|
| Judgment + board | `tryout_scale_window` | LIVE measure |
| Board cron | `phase6-tryout-scale-window-board` (`4f523c7d2efc`) | LIVE quiet |
| Operator eject | `run_tryout_scale_window.py --eject … --go` | LIVE proven (TIA/LINK 2026-09-30) |
| Auto eject | `live_apply` | **OFF** until GO |

### 3.5 Learn / Graduate

| Piece | Status | Note |
|-------|--------|------|
| Luck ladder R0–R6 | SHADOW fleet | Controllable luck; not promote |
| Pair funnel dwell monthly | LIVE measure | Stage dwell, not auto demote |
| Decision discipline outcomes | SHADOW attach | Needs closed-loop N |
| Name/size graduate | PARTIAL | Packet + GO; no auto-promote |
| dual_agree | Signal only | ≠ membership / ≠ scale GO |

---

## 4. Cron / ops surfaces (tryout-only)

| Job | Role | Money |
|-----|------|-------|
| `phase6-rsi-event-x-tryout-shadow` | R0 would-query board | OFF |
| `phase6-rsi-event-x-probe` | Paid X on wash+stale | X spend only |
| `phase6-rsi-event-tryout-seat-composer` | System seat loop | OFF unless explicit GO flags |
| `phase6-knife-filter-shadow` | R1 knife arms | OFF |
| `phase6-tryout-scale-up-shadow` | Measure CF | OFF |
| `phase6-tryout-scale-up-live-approval` | Kindling plan TG | OFF |
| `phase6-tryout-scale-window-board` | Dead-window alarm | OFF |
| `phase6-pair-funnel-dwell-monthly` | Dwell report | OFF |
| `phase6-reentry-sl-tp-monitor` | Naked/SL/TP trust | alerts only |

Operator one-calls: skills `phase6-ops-one-call`, `phase6-risk-sizing-research` (kindling bar + scale-window).

---

## 5. Gap register (2026-10-01)

Severity: **P0** trust/money hole · **P1** process tax / false steering · **P2** complexity / doc · **P3** nice.

### P0 — trust / capital integrity

| ID | Gap | Evidence | Impact | Fix direction |
|----|-----|----------|--------|----------------|
| **TL-P0-01** | Naked bag after any dry-run/cancel path | `protected_market_exit` dry-run cancel; fixed reattach + fail-closed | Financial risk | Keep fail-closed; monitor page-on-fail (done direction) |
| **TL-P0-02** | Exit success claimed while SL unrestored | SW-03 class | Same | Dry-run must not return success if reattach fails (fixed 2026-10-01) |

### P1 — process tax / false state

| ID | Gap | Evidence | Impact | Fix direction |
|----|-----|----------|--------|----------------|
| **TL-P1-01** | Dead kindling can still ride until human eject | `scale_window.live_apply=false`; TIA/LINK sat phase-3 | Inventory tax, blocked seats | Measure N on board → arm auto eject with confirm + caps |
| **TL-P1-02** | Registry **ghosts** (e.g. ZEC `scored` after TP) | ~~open_lots~~ | Board noise | **SHIPPED 2026-10-01:** `purge_ghost_lots` on scale-window evaluate + SELL ledger close; ZEC purged live |
| **TL-P1-03** | Dual intake without one seat ledger | two counters | Ops confusion | **SHIPPED:** `phase6/core/tryout_seat_ledger.py` + `/api/pair-signals.tryout_seats` (read API; reserve/release still follow-up) |
| **TL-P1-04** | Decision discipline shadow-only | `live_apply:false` | Weak seats | **PREP only** — stays shadow until calibration N + Brad GO (no live flip) |
| **TL-P1-05** | Knife filter shadow | R1 shadow | Knife SL tax | **PREP only** — shadow until honest N + GO |
| **TL-P1-06** | Exit reason soup | partial hooks | Can’t learn tax | **SHIPPED:** `tryout_exit_taxonomy` + ledger SELL stamp + dwell/attr delegate |
| **TL-P1-07** | FAQ/lifecycle **$75×2** vs live **$25×6** | stale prose | Wrong size | **SHIPPED** in FAQ/SSOT (this file wins) |
| **TL-P1-08** | `paper_scaled` vs `live_scaled` trap | lot meta | False scaled | **SHIPPED:** Signals `·scale:` chip uses live_scaled / would_eject path labels |
| **TL-P1-09** | Soft-up door package archaeology | nested windows | Config lies | **DOC + gap** — single door_package object still follow-up (no live door rewrite mid soft-up) |
| **TL-P1-10** | Scale-up success-path tests thin | SW-04 | Regress | **PARTIAL:** `test_isolation_tryout_lifecycle_bg.py` (tax/ledger/ghost); eject happy-path still backlog |

### P2 — complexity / optimize later

| ID | Gap | Fix direction |
|----|-----|----------------|
| **TL-P2-01** | Measure profile (loose CF) vs live_signal (strict) dual mental model | Keep dual **internals**; one operator sentence: “measure ≠ money bar” |
| **TL-P2-02** | Board always hits live positions (latency) | Cache held map short TTL for measure crons |
| **TL-P2-03** | Sentiment fetch 8s urllib in window board | Reuse dashboard/cache eng |
| **TL-P2-04** | No Signals chip for `scale: live\|pending\|dead` | Surface on pair-signals from lot+window judgment |
| **TL-P2-05** | Dwell hooks config referenced in memory, file may be absent | Confirm `pair_funnel_dwell` stages config path; document |
| **TL-P2-06** | Graduate/promote still GAP (PC-08 class) | Packet template; no auto |
| **TL-P2-07** | Takeover inherited bags ≠ tryout shells | Keep separate; don’t run scale-window on inherited junk without tag |
| **TL-P2-08** | H2 `live_attach_on_buy` false | Explicit: software exit primary; don’t “half-enable” |

### P3

| ID | Gap |
|----|-----|
| **TL-P3-01** | Close-down one-call for whole book still product GAP |
| **TL-P3-02** | Multi-tenant tryout economics OUT |

---

## 6. Simplification program (less loss, more profit)

Ordered for **tax reduction first**, not feature count.

### Step A — Single process SSOT (this doc)  ✅

- One state machine + money gates + gap IDs.
- FAQ + SPECS_INDEX + lifecycle link here for **bag** flow.
- Happy-path numbers **$25×6** (config still wins if drift).

### Step B — Held shell tax  ✅ code (auto-eject still OFF)

1. Ghost purge on scale-window evaluate + SELL ledger close (`tryout_seat_ledger.purge_ghost_lots` / `close_tryout_lot`).
2. Scale-window board stays ON; **`live_apply` remains false** until Brad GO + N.
3. Signals: `·scale:open|pending|live|dead|ghost` chip + `tryout_seats` summary.

### Step C — One seat ledger  ✅ read API

- `build_seat_ledger()` merges day burn + open shells + first_fill open + ghosts + dead kindling.
- `/api/pair-signals` exposes `tryout_seats` + per-row `scale_path`.
- Follow-up: composer/rebalance `reserve_seat` / `release_seat` write path (not required for ops truth).

### Step D — Intake quality without more doors  ✅ shadow prep

- Shell stays **$25×6**.
- Discipline + knife **remain shadow** (`live_apply:false`) — no silent money veto.
- Outcomes attach via taxonomy on SELL so calibration N can accumulate honestly.

### Step E — Exit taxonomy + learn  ✅ stamp path

- `tryout_exit_taxonomy.py` → CLOSED_* on every ledger SELL (`stamp_exit_taxonomy`).
- Dwell `classify_exit_stage` + attribution `classify_exit_reason` delegate to taxonomy.
- SELL also `close_tryout_lot` + `on_tryout_exit` (best-effort).
- Weekly % board still uses attribution_rt — stop new exit *mechanisms* until N clean.

### Step F — Grow honesty  ✅ guards

- `LIVE_SAFETY.one_step_per_lot=true` + hard max total after step **$100**.
- Already-live_scaled / n_live_steps≥1 → plan blocked (`one_step_per_lot`).
- CF / INSUFFICIENT_N never auto-money (unchanged).

### Step G — Config archaeology  ✅ gap row + honesty

- Soft-up door package **not** rewritten mid-window (expires 2026-10-06) — single `door_package` still follow-up.
- `docs/SPECS_CODE_GAP.md` addendum: tryout lifecycle B–G ship.
- Discipline/knife/scale-window `live_apply` remain **false** (asserted in isolation).

---

## 7. Verification checklist (bag episode)

Use after any live tryout fill or eject — trust product.

### After BUY (shell open)

1. Ledger BUY + order id  
2. Exchange SL under entry  
3. `register_tryout_open_lot` → `status=tryout_open`, `live_scaled=false`  
4. Peak lot-bound (not stale prior bag)  
5. Seat counters burned correctly (not stable false burn)  
6. No trail fire inside minutes unless mark cleared arm  

### After KINDLE

1. One step only; `live_scaled=true`  
2. SL resized/reattached for new qty  
3. Plan crumb + capital event reason true  

### After ANY flat

1. Ledger reason ∈ taxonomy above  
2. Lot registry closed/purged (not ghost)  
3. Cooloff matches policy (TP vs SL vs eject)  
4. **No** surprise cash-hold on strategy TP/eject  
5. Dwell + discipline outcome attached when hooks on  
6. Powder free for next dual-clear door  

### After scale-window board ping

1. `would_eject` pairs **on-book** (not ghosts)  
2. Fingerprint dedupe quiet  
3. Money still OFF unless armed  

---

## 8. Anti-patterns (do not)

- Babysit flat/red shells “until SL” when phase≥3 and never kindled  
- Treat measure `would_scale` or paper_scaled as live kindling  
- Mint tryout via full rebalance “while we’re at it”  
- Grow `buy_block_pairs` to silence funnel wounds  
- FOMO size from Paper 7d or dual_agree alone  
- Half-exit on dead sent at 0R (dual-peak meat gate exists for a reason)  
- Claim promote/edge from door-open proof windows  
- Dry-run exits that cancel SL without guaranteed reattach  

---

## 9. Code / doc inventory (consolidation map)

| Concern | Canonical now | Demote to historical |
|---------|---------------|----------------------|
| Bag state + gaps | **This file** | Dated plans under `docs/plans/*tryout*` (keep as evidence) |
| Book Fresh/Takeover stages | `CRYPTO_PROCESS_LIFECYCLE.md` | — |
| Glossary wash/sent/thaw/knife | FAQ § tryout happy path | Update numbers → link here |
| Kindling bar details | skill ref `tryout-scale-up-kindling-bar.md` | — |
| Scale-window eject | `tryout_scale_window.py` + config | code review report |
| Exit taxonomy | `tryout_exit_taxonomy.py` | ad-hoc reason matching |
| Seat ledger + ghosts | `tryout_seat_ledger.py` | dual counters folklore |
| Trust both ends | `TRUST_FIRST_TRADING_ENGINE.md` | — |
| Crons | `HERMES_CRON_SSOT.md` | — |
| Luck ladder program | `docs/plans/2026-09-15-luck-ladder-platform-refine.md` + status report | — |
| B–G conformance | `reports/TRYOUT_LIFECYCLE_BG_CONFORMANCE_2026-10-01.md` | — |

---

## 10. Staff-next (recommended order)

1. ~~FAQ + SSOT $25×6~~ ✅  
2. ~~Ghost purge + isolation~~ ✅ (ZEC purged 2026-10-01)  
3. ~~Signals `scale_path`~~ ✅  
4. ~~Seat ledger read API~~ ✅ · optional: composer `reserve_seat` write  
5. After board N: decide **auto eject GO** vs stay operator-only.  
6. Discipline/knife promote only with honest closed-RT N + Brad GO.  
7. ~~Exit taxonomy stamp~~ ✅ · keep weekly process-tax board honest  
8. Soft-up end → flatten single `door_package` (G residual)

---

## 11. Revision log

| Date | Change |
|------|--------|
| 2026-10-01 | Initial consolidate from FAQ happy path, CRYPTO_PROCESS_LIFECYCLE, kindling bar, scale-window ship, decision discipline, live configs, code review SW-*, operator C eject lesson (TIA/LINK). |
| 2026-10-01 | **B–G ship:** exit taxonomy + seat ledger + ghost purge (ZEC) + Signals `·scale:` + grow one-step guards + SPECS gap addendum. Money knobs still OFF (scale-window/discipline). Conformance: `reports/TRYOUT_LIFECYCLE_BG_CONFORMANCE_2026-10-01.md`. |

---

*Not an alpha claim. Process map for less manufactured loss and faster powder recycle.*
