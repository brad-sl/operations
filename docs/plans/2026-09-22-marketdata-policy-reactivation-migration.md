# Marketdata + Policy Reactivation Migration Plan

> **For Hermes:** Execute only after explicit Brad GO on each **policy** wave. Sensor/cutover waves may proceed under this plan without money-path writes.
>
> **Status:** PLAN ONLY — no knobs applied this turn  
> **Date:** 2026-09-22  
> **Owner (orchestration):** Scotty / Hermes default  
> **Related:** `docs/plans/2026-09-22-marketdata-ohlcv-schema-design.md` · MASTER `MARKETDATA-OHLCV-*` · `REGIME-CLIMATE-WEATHER-REMAINING-20260921`

---

## Goal

Get the book **honest and active again**: finish market-data migration debt that still feeds false climate, then **unlock the already-approved transition deploy path** so tryout doors can produce qualified fills under the existing `$25 × ≤4 seats / SL+trail / no auto-promote` shell — before the door package expires **2026-09-26 21:00 PT**.

---

## Ground truth (2026-09-22, post D1–D4 thin)

| Fact | Value |
|------|--------|
| Detector (marketdata.db) | **`transition` / `climb`** · BTC30d **~+11.0%** · `fresh_ok=true` · tip ~$86.4k |
| Policy JSON `regimes.transition` | **deploy** · `allow_new_buys=true` · **cap $75** (Brad thaw 2026-08-24) |
| Live resolve snapshot | **`usdc_park`** · `allow_new_buys=false` · **cap $0** · scenario **`usdc_hold`** |
| Root choke | `config/regime_knob_map.json` → `regimes.transition` still **scorecard `usdc_hold` / cap 0**; `_merge_knob_map` forces park. Only **`flat`** is in `operator_overrides_preserved`. Scorecard last wrote map **2026-09-20**. |
| Shadow stance | `transition_deploy` (detector) — money path ignores it while knob map parks |
| Book | Cash ~**$175** · PAXG MICRO ~**$80** · total ~**$2.29k** · seats used today **0** |
| Tryout shell | `quality_tryout_v2` · abs_cap **$25** · max seats **4** · floor sent **0.30** · door/thaw **expires 2026-09-26 21:00 PT** |
| Eligible tryout (membership) | ADA, ETH, HYPE, LINK, SUI, TIA, ZEC (+ doors) — **no eng-cleared door** yet; free/RSS ≠ green |
| Tryout readiness artifact | Still labels `regime=bear` / `can_buy=false` — **stale consumer**, not detector |
| Climate/weather board | Still **false bear −14%** / sparse tail / old live ~$66.8k — **not on marketdata.db** |
| Marketdata thin | **13/13** pairs @ 1d · 5030 bars · freshness ok |
| Standing NO-GOs | `live_membership_swaps=false` · no auto-promote · no unpark without Brad GO · PAXG E1 protect · hard blocks RAVE/UNI only |

**Plain English:** Sensors finally say climb. Policy JSON already allows gated transition deploy. The **knob map scorecard overlay re-parked transition** and is winning the merge. Fixing that is the ASAP money-path unlock — not more pair scouts.

---

## Architecture (migration spine)

```
[A SENSOR TRUTH] marketdata.db 1d thin universe
        ↓
[B LIVE READERS] detector → regime_cash resolve → climate/weather → arm-switch → run_phase
        ↓
[C POLICY LAW]  regimes.* JSON  ⟂  knob_map overlay  ⟂  recovery tryout shell
        ↓
[D FUNNEL]      eng-X clear → latch → RSI band → seats/cap → fill → SL/trail → RT measure
        ↓
[E PROMOTE]     shadow evidence → Brad GO only (never dual_agree alone)
```

**Money path stays Python-hard.** Jev/shadows stay measure-only.

---

## Must not touch (until named GO)

- Live orders / force-rebalance / runner restart **except** after Wave P1 GO + verify
- `live_membership_swaps` → true
- Auto-promote any paper arm
- Raise tryout beyond door shell without GO (`$25` / max seats / sent floor)
- Delete `backtests/data/*` research JSON
- Perma-block new pairs into `buy_block_pairs` (funnel-first)
- CW-4 **money ON** (B micro live capital) — separate GO after path proof
- Full Coinbase universe ingest / 1h bars (deferred D3b)

---

## Priority waves (ASAP → later)

| Wave | Name | Priority | Money? | Owner default | ETA if GO |
|------|------|----------|--------|---------------|-----------|
| **P0** | Policy unlock packet (decision + dry-run) | **P0 ASAP** | Decision only | Scotty | **same session** |
| **P1** | Apply transition knob-map operator override + status refresh | **P0 ASAP** | **YES (cap unlock)** | crypto-engineer + Brad GO | **<1h** |
| **P2** | Funnel sensor board honesty (tryout readiness + X latch path) | P0 | No knobs | crypto-engineer | **same day** |
| **P3** | D4 residual: climate/weather + any live climate fossil readers | P0/P1 | No | crypto-engineer | **same day** |
| **P4** | Door package extend-or-graduate decision | P0 (calendar) | Policy | Brad + Scotty | **by 2026-09-25** |
| **P5** | CW-2 hysteresis design (doc) | P1 | No | crypto-analyst | 1–2d |
| **P6** | CW-3 threshold evidence (measure) | P1 | No | crypto-analyst | after P3 |
| **P7** | CW-4 Live B micro path **money OFF** | P1 | Arm only | crypto-engineer | after P5 |
| **P8** | Marketdata D3b optional 1h thin + research readers port | P2 | No | crypto-engineer | later |
| **P9** | Scorecard writer guard (stop silent transition re-park) | P1 | Guard | crypto-engineer | with/after P1 |

**Critical path to “active again”:** **P0 → P1 → P2 → (natural X/rebalance)** · P3 parallel · P4 calendar hard stop.

---

## Wave P0 — Policy unlock packet (ASAP, no live write)

**Objective:** One operator card Brad can GO/NO-GO without re-litigating climate.

### Why this is the unlock

| Layer | Says | Wins today? |
|-------|------|-------------|
| `regime_detector` + marketdata | transition/climb +11% | truth |
| `regime_cash_policy.json` `regimes.transition` | deploy / buys on / **$75** | **overridden** |
| `regime_knob_map.json` `regimes.transition` | **usdc_hold / park / $0** | **YES** via `_merge_knob_map` |
| Recovery tryout shell | $25×4 / doors open | latent until park lifts |

Brad 2026-08-24 product call already: transition residual is **not** special park; flat-like gated deploy. Scorecard **2026-09-20** rewrote transition to usdc_hold and did **not** preserve it (only `flat` preserved).

### Recommended GO package (default)

**Name:** `TRANSITION-KNOB-MAP-RESTORE-20260922`

| Knob | Value | Rationale |
|------|-------|-----------|
| `regime_knob_map.regimes.transition.strategy_mode` | **`deploy`** | Match policy JSON + 2026-08-24 thaw |
| `live_overlay.global_settings.rebalance_cap_usd` | **75.0** (or **50** if Brad wants tighter) | Policy default 75; recovery may still clamp |
| `scenario_id` | `transition_gated_deploy_75` (or restore prior deploy id) | Stop labeling usdc_hold |
| `operator_overrides_preserved` | include **`transition`** (+ keep `flat`) | Stop scorecard silent re-park |
| Recovery shell | **unchanged** | $25 tryout / max 4 / sent≥0.30 / door expiry |
| Membership swaps | **OFF** | standing |
| Auto-promote | **OFF** | standing |
| PAXG | MICRO hold + E1 only | no scale |

**Optional tighter GO (if Brad wants climb-only micro first):**

- Cap **$50** rebalance + tryout still **$25×2** until first clean RT week  
- Or: allow_new_buys only via **quality_tryout path** (already true under recovery) while rebalance_cap **$25**

**NO-GO options (explicit):**

- Stay park until BTC30d ≥ +15% bull (wastes climb band; fights 2026-08-24 thaw)
- Full flat util 0.65 / $75 basket rotation (too wide; swaps still off)
- CW-4 money on day one

### P0 deliverables

1. This plan on disk (done).  
2. One-screen GO card in Telegram/plain English (below in session).  
3. Dry-run script output: **before/after** `resolve_regime_cash()` if map patched in a temp copy (no write).  
4. Kanban card + MASTER block ready to flip on GO.

### P0 verification

```bash
cd /home/brad/projects/crypto-trading-bot
PYTHONPATH=. .venv/bin/python3 - <<'PY'
from phase6.research.regime_detector import detect_regime
from phase6.core.regime_cash_policy import load_policy, resolve_regime_cash
d=detect_regime(use_live_price=True)
s=resolve_regime_cash(policy=load_policy(), detection=d)
print(d['regime'], d.get('regime_layer'), d.get('btc_return_pct'), d.get('data_source'))
print(s.strategy_mode, s.allow_new_buys, s.rebalance_cap_usd, s.knob_map_scenario)
PY
```

**Expect pre-GO:** `transition climb ~11 marketdata_db` + `usdc_park False 0.0 usdc_hold`  
**Expect post-P1:** `deploy True 75.0 <deploy scenario>` (recovery may clamp cap ≤ bull max)

### Assignment

| Role | Who |
|------|-----|
| Author packet | **Scotty** |
| Decide GO/NO-GO | **Brad** |
| Do not implement P1 until GO | all agents |

---

## Wave P1 — Apply transition deploy restore (Brad GO required)

**Objective:** Make live resolve match policy law for upside transition.

### Task breakdown

#### Task P1.1 — Isolation: knob_map merge respects operator-preserved transition deploy

**Files:**
- Test: `phase6/core/test_isolation_regime_cash_policy.py` (extend `test_transition_allows_gated_deploy`)
- Or: `scripts/phase6/test_isolation_transition_knob_map_restore.py` (new)

**Steps:**
1. Failing test: policy transition deploy + knob_map usdc_hold → today parks; after fix with preserved override → deploy.
2. Implement map edit **or** code: if `operator_overrides_preserved` contains regime, skip park force from scorecard usdc_hold (prefer **data fix + preserve list** over clever code unless writer fights back).
3. Run isolation green.

**Verify:**
```bash
PYTHONPATH=. .venv/bin/python3 phase6/core/test_isolation_regime_cash_policy.py
# and/or
PYTHONPATH=. .venv/bin/python3 scripts/phase6/test_isolation_transition_knob_map_restore.py
```

#### Task P1.2 — Patch `config/regime_knob_map.json` transition block

**Files:**
- Modify: `config/regime_knob_map.json`

**Patch intent (exact fields):**
```json
"transition": {
  "scenario_id": "transition_gated_deploy_75",
  "strategy_mode": "deploy",
  "note": "Brad GO 2026-09-22: restore 2026-08-24 transition thaw. Scorecard usdc_hold must not silent-park climb. operator_overrides_preserved.",
  "live_overlay": {
    "global_settings.rebalance_cap_usd": 75.0,
    "global_settings.risk_free_preference": "USDC",
    "global_settings.risk_free_apy_pct": 3.5
  },
  "arch4_params": { "use_rotation": false, "rebal_freq": 7 },
  "usdc_benchmark": {
    "beats_usdc_benchmark": false,
    "reason": "operator_transition_thaw_not_scorecard"
  },
  "scorecard": {
    "note": "Operator product sleeve; scorecard may prefer usdc_hold offline — preserved."
  }
}
```
- Set `"operator_overrides_preserved": ["flat", "transition"]`

**Rollback:**
```bash
git checkout -- config/regime_knob_map.json
PYTHONPATH=. .venv/bin/python3 -c "from phase6.core.regime_cash_policy import persist_policy_state; persist_policy_state()"
# runner restart only if cap was applied live
```

#### Task P1.3 — Guard scorecard writer

**Files:**
- Modify: `phase6/research/apply_regime_knob_map_from_scorecard.py`
- Ensure `transition` (and `flat`, `soft_down`) stay in preserve list when operator-marked
- Isolation: re-run apply on fixture → transition not clobbered

#### Task P1.4 — Persist status + runner load

**Steps:**
1. `persist_policy_state()` / normal continuous path refresh `data/state/regime_cash_status.json`
2. Confirm `allow_new_buys=true`, `rebalance_cap_usd` > 0, `strategy_mode=deploy`
3. **Brad GO** for runner restart if process holds old global_settings cap (use `trading-bot-operations` restart runbook)
4. **No** force-rebalance unless Brad asks; next natural slot (~21:05 PT) is enough if doors still sentiment-blocked

#### Task P1.5 — Commit + MASTER

```bash
git add config/regime_knob_map.json phase6/research/apply_regime_knob_map_from_scorecard.py \
  scripts/phase6/test_isolation_transition_knob_map_restore.py docs/MASTER_TASK_TRACKING.md
git commit -m "fix(regime): restore transition deploy knob-map; preserve vs scorecard re-park"
```

### P1 verification checklist (must all pass before “active”)

- [ ] `detect_regime` still `transition/climb` + `marketdata_db` + fresh_ok
- [ ] `resolve_regime_cash` → `allow_new_buys=True`, `strategy_mode=deploy`, cap ≥ tryout abs_cap
- [ ] `regime_cash_status.json` matches resolve (not stale bear)
- [ ] Recovery tryout still abs_cap $25 / seats ≤4 / hard blocks intact
- [ ] `live_membership_swaps` still false
- [ ] Isolation tests green
- [ ] Tryout readiness `can_buy_before_next_rebalance` reflects park lift (may still false if sent/RSI — OK)
- [ ] No unintended basket-wide buys (rebalance candidates = held∪plan only doctrine)

### Assignment P1

| Task | Assignee |
|------|----------|
| P1.1–P1.3 code/config | **crypto-engineer** (or Scotty if single-session GO) |
| P1.4 runner | **ops / Scotty** after Brad GO |
| Accept risk | **Brad** |

---

## Wave P2 — Funnel honesty so qualified trades are visible

**Objective:** After park lifts, don’t lose fills to stale boards or dead sensors.

### Task P2.1 — Tryout readiness regime source

**Problem:** `tryout_readiness_latest.json` still shows `regime=bear` while detector is transition.

**Files:** `phase6/core/tryout_readiness.py`, `scripts/phase6/run_tryout_readiness.py`

**Fix:** Read regime from `resolve_regime_cash` / status SSOT (post-marketdata), never fossil.

**Verify:** rebuild → `regime` matches status; plain_english mentions park vs sent choke accurately.

### Task P2.2 — Eng-X path for eligible set (budget intact)

**Standing:** paid X 2×/day primary + aging; RSI-event probe budget caps; latch 180m door window.

**Steps:**
1. Confirm cron `phase6-x-sentiment-live-2x` still **09:00 / 21:00 PT**
2. On next refresh: eligible doors get X; latch write if ≥0.30
3. Do **not** cut aging or promote free/RSS to live floor
4. Optional: one **Brad GO** mid-tape refresh for top-2 eligible if seats idle and RSI in band (existing probe rules)

**Verify:**
- `data/state/tryout_sent_latch.json` updates on clear
- Readiness pairs show eng_sent + age, not only free
- `can_buy` true only when park off **and** pair clears stack

### Task P2.3 — Seat counter / day hygiene

- Confirm stables still excluded from seat count
- Seats used today 0 — OK
- No day_clear wipe unless Brad GO

### Task P2.4 — Signals pane vs live gates

- Dashboard Signals must show ·blocked reasons including former park vs sent
- Wrong #s = bugs (fix board, don’t loosen gates)

### Assignment P2

| Task | Assignee |
|------|----------|
| P2.1 code | **crypto-engineer** |
| P2.2 ops confirm | **Scotty** / phase6-ops-triage |
| P2.3–P2.4 | **Scotty** |

---

## Wave P3 — D4 residual cutover (climate honesty)

**Objective:** Kill remaining false-bear boards that will confuse GO decisions.

### Task P3.1 — `regime_climate_weather` → marketdata.db

**Files:** `phase6/core/regime_climate_weather.py`, CLI, cron `phase6-regime-climate-weather`

**Steps:**
1. Load BTC 1d closes via marketdata store port (same as detector)
2. Drop dependence on gapped research JSON + undated live append for climate row
3. Re-run CLI → climate **transition/climb ~+11%**, weather horizons bar-honest
4. Isolation update

**Verify:** `data/state/regime_climate_weather_latest.json` climate matches detector; plain_english not “bear −14%”.

### Task P3.2 — Audit live climate fossils

**Search & classify:**
```bash
rg -n "price_cache_|backtest_historical_ohlcv_btc|fetch_btc_daily|get_recent_prices" phase6 --glob '*.py'
```
- **Live climate path** → store first (cut over)
- **Offline research/backtest** → leave JSON
- Already done: detector, arm_switch, run_phase_deploy (thin D4)

### Task P3.3 — L2 deployability refresh (read-only)

- Stale L2 board still `regime=flat` / Sep 12 — regenerate measure-only after P1 so promote attention isn’t lying

### Assignment P3

| Task | Assignee |
|------|----------|
| P3.1–P3.2 | **crypto-engineer** (`t` new or extend marketdata) |
| P3.3 | **Scotty** measure cron |

**Kanban:** new card `MARKETDATA-D4-CLIMATE-WEATHER-PORT` or attach to CW residual.

---

## Wave P4 — Door package calendar (hard date)

**Deadline:** **2026-09-26 21:00 PT**

| Option | When | Action |
|--------|------|--------|
| **A Extend 7d** | No fills yet but path green | Brad GO extend thaw+RSI65+latch same shell |
| **B Graduate thin** | ≥1–2 clean tryout RT | Keep shell; document graduation packet rules; no auto-promote |
| **C Expire** | Path still broken | Let expire; stay funnel-first; don’t perma-block wounds |

**Owner:** Brad decide by **2026-09-25 12:00 PT**; Scotty preps patch diff both ways.

---

## Wave P5 — CW-2 Hysteresis design (doc only)

**Kanban:** `t_a8aafce3` · Handoff exists  
**Assignee:** **crypto-analyst**  
**Out:** Design doc bear→soft_down→flat dwell/hysteresis — **no live threshold write**  
**Depends:** honest climate board (P3) preferred but can draft in parallel  
**Verify:** design answers flip-flop cost vs 2026-08-24 signed residual; recommend code touch points only

---

## Wave P6 — CW-3 Threshold surgery evidence

**Kanban:** `t_defaaee0`  
**Assignee:** **crypto-analyst**  
**Depends:** marketdata BTC history (done) + P3 preferred  
**Out:** Evidence pack on −10 / ±8 / +15 — measure-only, N tags, no live write  
**Verify:** walk-forward honesty skill; no “promote thresholds” language

---

## Wave P7 — CW-4 Live B micro path (money OFF)

**Kanban:** `t_6af749f2`  
**Assignee:** **crypto-engineer**  
**Depends:** P5 design + P1 path proof (tryout funnel working)  
**Out:** Armed paper/micro path wiring, **orders OFF** until separate Brad GO  
**Verify:** isolation would_order=false; no seat consumption

---

## Wave P8 — Deferred marketdata (not on critical path)

| ID | Item | Notes |
|----|------|-------|
| D3b | 1h thin universe | Optional; RSI already has paths |
| D5 | Research `_load_btc` callers → store | Convenience; not live P&L |
| D6 | Spot tick table consumers | Later |
| D7 | Multi-venue | Out of scope |

---

## Wave P9 — Prevent regression (ship with P1)

| Guard | Implementation |
|-------|----------------|
| Scorecard cannot un-preserve transition | P1.3 |
| Cron `apply_regime_knob_map_from_scorecard` logs skip | explicit |
| Pre-ship test: transition climb fixture → deploy | isolation |
| Ops triage: if status park while detector transition/climb → **high** finding | `ops_triage_discover` rule |

---

## End-to-end “active again” acceptance

**Definition of active (honest, not degen):**

1. Climate SSOT + status + tryout board agree: **transition/climb**, not false bear  
2. `allow_new_buys=true` with **cap > 0** under operator shell  
3. ≥1 eligible pair can reach **eng-cleared** latch without free-feed cheat  
4. A tryout BUY is **possible** at next rebalance if RSI+sent+seats clear (not guaranteed fill)  
5. Any fill: SL attach A1 path + seat count correct + no auto-promote  
6. Door expiry decision recorded before 2026-09-26  

**Not required for “active”:** bull climate, membership swaps, CW-4 money, beating USDC offline on transition scorecard.

---

## Staffing matrix (summary)

| Who | Owns |
|-----|------|
| **Brad** | P0 GO/NO-GO; P1 risk accept; P4 door extend; any cap≠75; runner restart GO; CW-4 money later |
| **Scotty (Hermes default)** | Orchestration; P0 packet; P2 ops; P3.3; MASTER/Kanban; verification boards; no silent knobs |
| **crypto-engineer** | P1 implement; P2.1; P3.1–P3.2; P7; P9 guards |
| **crypto-analyst** | P5 CW-2; P6 CW-3; optional transition path CF note (N-tagged) |
| **Kanban board** | `crypto-bot-project` — create/update cards per wave on GO |

### Suggested Kanban cards (create on Brad GO P0/P1)

| Card | Title | Priority | Status seed |
|------|-------|----------|-------------|
| NEW | `[P1] Restore transition knob-map deploy + preserve` | P0 | ready→in progress on GO |
| NEW | `[P2] Tryout readiness regime SSOT + funnel board` | P0 | ready |
| NEW | `[P3] Climate/weather marketdata port` | P0 | ready |
| NEW | `[P4] Door package 2026-09-26 extend/grad/expire` | P0 | todo due 09-25 |
| existing | CW-2 / CW-3 / CW-4 | P1 | keep |

---

## Execution order (clock)

```
NOW     P0 packet → Brad GO?
+0–1h   P1 map+guard+status (+ runner if GO)
parallel P3 climate port (no money)
same day P2 readiness + X confirm
tonight  Natural X 21:00 + rebalance ~21:05 — watch for first door clear
+24–72h Measure fills / blocks; do not loosen floors on empty
by 09-25 P4 door decision
then     P5→P6→P7 as capacity
```

---

## Risk register

| Risk | Mitigation |
|------|------------|
| Scorecard was “right” and deploy loses to USDC on transition | Accepted 2026-08-24; cap small; tryout shell; measure RT; rollback map git |
| Climb fails → soft_down/bear | Detector + signed residual already maps downside; bear parks |
| Sentiment still blocks all doors | Expected; unlock park ≠ invent eng scores; keep X 2× + latch |
| Seat pile-on | max seats 4 / $25; run_phase FOMO armor stays |
| Stale boards cause bad GO | P2+P3 before size-up stories |
| CR-03 class reattach on PAXG | preserve skip + E1 only |

---

## Proof commands (operator cheat sheet)

```bash
# Climate truth
PYTHONPATH=. .venv/bin/python3 scripts/phase6/run_marketdata_btc_1d.py status
PYTHONPATH=. .venv/bin/python3 -c "from phase6.research.regime_detector import detect_regime; import json; print(json.dumps(detect_regime(use_live_price=True), indent=2, default=str)[:1200])"

# Money law
PYTHONPATH=. .venv/bin/python3 -c "from phase6.core.regime_cash_policy import load_policy,resolve_regime_cash; s=resolve_regime_cash(policy=load_policy()); print(s.regime,s.regime_layer,s.strategy_mode,s.allow_new_buys,s.rebalance_cap_usd,s.knob_map_scenario)"

# Funnel
PYTHONPATH=. .venv/bin/python3 scripts/phase6/run_tryout_readiness.py
# Door expiry
rg -n "expires_at" config/regime_cash_policy.json | head
```

---

## Preflight summary

- **Objective:** Honest climate + restore transition deploy law + funnel visible so qualified tryouts can fire under existing shell  
- **IN scope:** knob_map transition restore, preserve vs scorecard, readiness/climate cutover, door calendar, CW-2/3/4 sequencing  
- **OUT of scope:** auto-promote, membership swaps ON, bull size-up, full universe 1h, Jev money path, perma-block expansion  
- **Must not touch:** live book until P1 GO; PAXG scale; door floors without GO  
- **Decisions locked (technical):** choke = knob_map usdc_hold overlay; detector already fixed  
- **Open:** Brad GO on P1 package (cap 75 vs 50 vs stay park); P4 in 3 days  
- **Plan path:** `docs/plans/2026-09-22-marketdata-policy-reactivation-migration.md`  
- **BoN:** skipped — single choke, single restore path matches prior Brad thaw  
- **Proof of done (P1):** resolve shows deploy+buys+cap>0 on transition/climb; isolation green; status file matches  
- **Awaiting:** **Brad go / adjust on Wave P0 package**

---

## Plain-English GO card (copy for Brad)

**Sensor:** BTC climate is **transition/climb (~+11% 30d)** on `marketdata.db` — the false bear is fixed.

**Blocker:** Scorecard **knob map** still forces **transition → USDC park / $0**, overriding the 2026-08-24 policy that transition should be **gated deploy ~$75**.

**Doors:** Tryout shell already on (`$25` / up to 4 seats / sent 0.30) but **expires 2026-09-26**. Membership open on several names; eng-X still has to clear — park lift won’t invent sentiment.

**Ask:** GO restore **transition deploy** on `regime_knob_map.json`, add **transition** to operator preserve (so nightly scorecard can’t silent-park again), keep swaps OFF / no auto-promote / PAXG micro only.

**Rollback:** git checkout knob map + refresh status (+ runner if needed).
