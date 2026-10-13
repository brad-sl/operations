# Analyst weekly suggestions — implementation plan (2026-10-12)

> **For Hermes:** After Brad **Go** on named workstreams, use subagent-driven-development task-by-task.  
> **This document is plan-only.** No knobs, no orders, no runner restarts until explicit Brad GO per workstream.

**Goal:** Convert the 2026-10-11 analyst weekly suggestions into a sequenced, prove-able delivery path that cuts **process tax** (ETH SL + tryout seat→eject) and unblocks **honest ballast rebuild** under flat $75 — without blowing caps, touching PAXG, or promoting Kelly/deploy_pct.

**Architecture:** Three lanes only:
1. **Measure / RCA** — ship without money GO (reports + isolation + optional shadow flags).
2. **Data honesty** — fix fail-closed unknowns that make kindling/WR unreadable.
3. **Money levers** — config/code behind explicit Brad GO + kill file + 7d anomaly watch.

**Tech stack:** Phase6 Python (`phase6/core/*`, `scripts/phase6/*`), config JSON SSOT, ledger `trades/phase6_trades.jsonl`, membership matrix, tryout scale-up / scale-window, add-risk sizer.

**North star context (from weekly):** Realized **−$22** · tax **−$22.44** · non-tax **+$0.44** · ETH SL **−$18.90** · TIA trail **+$1.22** · eject kindling **0/12** · BTC **~$55** vs target **~$407** · ETH **$0** · util **~11%** · cash **not** blocked.

---

## Preflight lock (grill synthesis — confirm or adjust)

### Objective
- **IN:** Process-tax RCA (ETH career), intake quality vs dead kindling, under-target ballast floor design, flat $75 priority design, structure_unknown fix, WR bucket split in analyst/dash.
- **OUT:** Blow flat B cap · PAXG preserve change · scale-window live_apply flip · post-proof dwell flip · perma buy_block expansion · Kelly/deploy_pct · dual_agree auto · liquidate BTC/SOL/TIA/PAXG · “edge claim” from thin N.

### Must not touch (until separate letter GO)
- Live book orders except operator paths Brad names this turn  
- `config/tryout_scale_window.json` live_apply / cooloff  
- `config/post_proof_dwell.json` live_apply  
- PAXG MICRO/E1 / scale_path=none  
- `buy_block_pairs` (RAVE/UNI)  
- Global `stop_loss_pct` 0.08 → 0.03 blanket  
- `deploy_pct` / Kelly live promote  

### Decisions locked (recommended defaults — Brad can override)
| # | Decision | Recommendation | Why |
|---|----------|----------------|-----|
| D1 | Sequence | **Measure → data → GO money** | ETH SL is 86% of week tax; don’t redesign intake blind |
| D2 | ETH SL response | **Career RCA first**; no automatic tighter ballast SL | 8% is early hypothesis; green-then-die ≠ global 3% |
| D3 | Tryout intake | **Tighten quality**, don’t freeze system seat loop | 0/12 kindling = seat quality / kindling bar, not “need more seats” |
| D4 | Ballast floor | **Shadow `would_allow_under_target_step` 14d** before live | Chop-add risk on red BTC is real |
| D5 | Flat $75 priority | **Prefer ballast rebuild when held≪target**, still inside $75 + late-run gates | 9 buys while BTC micro/ETH $0 is process mis-allocation |
| D6 | Kindling live | **Do not** force kindling live_apply as fix for 0/12 | paper_not_live×8 is mostly “bar never cleared live,” not missing GO spam |
| D7 | Claim bar | No edge / promote language until closed sample honest | Same rule as Jev CF / SL exit CF |

### Brad lock (2026-10-12)
| Q | Answer | Locked |
|---|--------|--------|
| Q1 ETH after career | **Clarify only** — default **(a) no SL knob** after career unless packet shows mis-role size/naked stop. **Not** auto-arm 3% on this ETH leg (see Q1 note below). | measure career; no global/ballast SL% change |
| Q2 Intake | **(a) eng/discipline floor** | §B2 implement |
| Q3 Ballast floor | **Shadow through next Sunday** | §C1 `live_apply: false` only |
| Q4 Flat priority | **Yes** prefer BTC/ETH rebuild under flat | §D1 shadow; live later GO |
| Q5 Scope | **Full A–F** | this sprint |

**Q1 ≠ yesterday’s 3% small-bag fuse (same family, different switch):**
- **Yesterday / `config/sl_width_arming_policy.json`:** measure-only **stop width at arm** — 3% fuse only for **unproven tryout shells** (≤~$30, not graduated/core, weak MFE); **8% default** for core/graduated/sized/green path. Does **not** change live `stop_loss_pct` until separate GO.
- **Grill Q1:** what to do **after** this week’s **ETH −$18.90 SL career** — (a) report only, (b) lean on that 3% tryout fuse, (c) ballast **re-entry size** cap, etc.
- **This ETH leg:** exchange stop on a **ballast-sized** bag (~$19 loss on ~8% path), **not** a $25 shell. Under the arming sketch, it would stay **8%**, so “do the 3% fuse” would **not** have saved this stop. 3% fuse remains the **tryout corpse** tool; ETH career may still recommend **banking/trail / rebuild priority / size-on-reentry**, not “arm 3% on ETH.”

### Proof of done (whole epic)
- [ ] `reports/E_ETH_BALLAST_SL_CAREER_2026-10-12.md` exists with entry→SL chain  
- [ ] Analyst weekly TG/report shows **WR by bucket** (tp / eject / sl / dust)  
- [ ] `structure_unknown` rate on eject cohort **down** or classified (sensor vs true unknown)  
- [ ] Isolation tests green for every code touch  
- [ ] Any money lever: kill file + receipt JSON + 7d anomaly note  
- [ ] Do-not-touch list still honored  

---

## Workstream map (analyst IDs → delivery)

| Analyst ID | P | Lane | GO needed? | Plan section |
|------------|---|------|------------|--------------|
| **W-PROCESS-TAX-ETH-SL** + **E-ETH-BALLAST-SL-CAREER** | P0 | Measure | No (RCA); Yes only if SL/size change | §A |
| **W-TRYOUT-INTAKE-VS-KINDLING** | P0 | Money + measure | **Yes** for door/discipline tighten | §B |
| **W-BALLAST-PROFIT-GATE** | P1 | Shadow → money | Shadow no; live **Yes** | §C |
| **W-FLAT-BALLAST-BEFORE-SHELL** | P1 | Money | **Yes** | §D |
| **W-KINDLING-STRUCTURE-DATA** | P1 | Data | No | §E |
| **W-WR-BUCKET-SPLIT** | P2 | Display | No | §F |

Continuity: intake / ballast floor / flat-before-shell / structure / WR were **open_reinforced** from 2026-10-05; ETH SL career is **new**.

---

## §A — P0 Measure: E-ETH-BALLAST-SL-CAREER → W-PROCESS-TAX-ETH-SL

**Objective:** One honest career packet for the week’s ETH stop so “ballast leak” is diagnosed (size path, role, attach, hold), not folklore.

### Task A1: Pull ETH career facts from ledger + state

**Files:**
- Read: `trades/phase6_trades.jsonl`
- Read: `data/state/phase6_live_state.json` (if present), SL attach logs, `logs/phase6_runner.log`
- Create: `reports/E_ETH_BALLAST_SL_CAREER_2026-10-12.md`
- Create: `scripts/phase6/run_eth_ballast_sl_career.py` (optional one-call; prefer if reused)

**Known seed (already grounded):**
- SELL `2026-10-08T04:01:49Z` ETH-USD `stop_loss_exchange` pnl **−$18.897** oid `a30b423f-…`
- Dust sweep same day **−$0.168** oid `c8e0790c-…`

**Steps:**
1. Find matching BUY(s) for that lot (qty ~0.08803): entry_ts, entry_usd, reason/source (rebalance vs tryout vs add-risk), regime stamp if any.
2. Record SL attach: `stop_loss_pct` used (expect **0.08**), stop price, reattach events near 2026-10-07/08.
3. Hold hours, MFE/MAE if OHLCV available (`scripts/phase6/run_sl_width_3v8_cf.py` patterns).
4. Classify path: `ballast_core` vs tryout shell vs first_fill vs add-risk pyramid.
5. Matrix context at stop: was ETH under/over target_w? util? flat B?

**Proof:** Report section table: entry → peak → stop → $ → role → SL% → “would 3% have helped?” (cite existing 3v8 CF if ETH leg in sample).

**Commit:** `docs: ETH ballast SL career 2026-10-08`

### Task A2: Attach career → suggestion status

**Files:**
- Modify: analyst notepad / continuity if used (`data/state/analyst_*notepad*` or job notepad path from weekly runner)
- Modify: `reports/ANALYST_WEEKLY_TRADE_REVIEW_AGENT_LATEST.md` only if re-run; else leave and link career in new report

**Steps:**
1. Mark `W-PROCESS-TAX-ETH-SL` evidence = career path link.
2. Explicit **non-recommendation** unless career shows mis-size (e.g. tryout-sized rules on ballast notional) or naked SL gap.
3. If career shows green-then-die under 8%: point to banking/trail path — **not** global SL 3%.

**Proof:** One paragraph “GO options” with default **no knob**.

---

## §B — P0: W-TRYOUT-INTAKE-VS-KINDLING

**Objective:** Fewer shells that never clear live kindling (0/12), cutting eject+fee + same-day B+S tax — without killing discovery entirely.

### Evidence lock
- E-EJECT-COHORT-CARD: n=12 · **0%** cleared live kindling · blocks `paper_would_scale_not_live×8`, `structure_unknown×4`
- Fee-aware eject net **−$4.67** on ~$5.08 RT fees
- Same-day B+S pair-days **4**
- Scale-window live already ON (do not retune cooloff as first move)

### Task B1: Funnel autopsy one-pager (measure)

**Files:**
- Read: `data/state/tryout_eject_cohort_weekly.json` (or latest card state)
- Read: `config/tryout_decision_discipline.json`, `config/quality_tryout` / trading_config tryout floors
- Read: `phase6/core/tryout_eject_cohort_card.py`, `phase6/core/tryout_scale_up_shadow.py`
- Create: `reports/TRYOUT_INTAKE_VS_KINDLING_AUTOPSY_2026-10-12.md`

**Steps:**
1. For each of 12 ejects: hold_h, phase at eject, structure block, paper would_scale?, live plan status, eng/RSI at seat.
2. Split: **never-kindleable** (structure/phase fail entire life) vs **would_scale paper only** vs **intake should never have seated**.
3. Rank top 3 intake levers with expected seat-rate impact (not vibes):
   - discipline `min_eng_absolute` / live_apply already ON?
   - composer eng-first ranker
   - RSI door / latch
   - knife live_gate
   - novelty / M1 extended_24h (membership — separate)

**Proof:** Table of 12 rows + recommended **one** primary intake tighten (GO menu).

### Task B2: Implement chosen intake tighten (AFTER Brad GO)

**Default recommendation if Brad does not pick:** raise effective **eng floor enforcement** on composer dual-clear (signal-first already documented) + keep seat loop ON; optional **shadow** “would_refuse_seat” counter for 14d before hard refuse.

**Files (depends on pick):**
- Likely: `phase6/core/rsi_event_tryout_seat_composer.py`, `config/tryout_decision_discipline.json`, `config/trading_config_phase6.json` quality_tryout
- Test: `scripts/phase6/test_isolation_tryout_seat_buy_action.py` / composer isolation
- Kill: existing seat KILL file path

**Steps (generic):**
1. Write failing isolation: weak-eng / dead-structure candidate is skipped with stable reason code.
2. Implement minimal gate; receipt field on composer latest JSON.
3. Runner restart only if import-time config (ops-one-call recipe).
4. 7d: track n_seats, n_ejects, % kindling cleared, fee net — compare to prior card.

**Must not:** freeze system seat loop without GO; flip scale-window off; pin tryout wounds into perma buy_block.

**Proof:**
```bash
cd /home/brad/projects/crypto-trading-bot
PYTHONPATH=. .venv/bin/python3 scripts/phase6/test_isolation_<touched>.py
# composer dry: expect skip reason on fixture weak eng
```

---

## §C — P1: W-BALLAST-PROFIT-GATE (under-target floor)

**Objective:** When ballast held ≪ `target_pair_weight` (BTC ~$55 vs ~$407), allow **one** flat-cap-respecting step even if profit-budget/`min_move` collapses `max_add` to $0 — without pyramid-on-red free-for-all.

### Code SSOT today
- `phase6/core/add_risk_sizer.py` → `compute_max_add_usd`  
  - `gap_below_min` → 0  
  - `zero_risk_budget` (open_upnl≤0 × k_profit) → 0  
  - then matrix/`decide_add_size` drops &lt; min_move $25  
- Empty bags use **new buy** path, not max_add (`flat_no_stack` on matrix for held=0)

### Task C1: Shadow policy sketch (no live)

**Files:**
- Create: `config/ballast_under_target_floor.json` (`live_apply: false`)
- Create: `phase6/core/ballast_under_target_floor.py` (pure function)
- Test: `scripts/phase6/test_isolation_ballast_under_target_floor.py`
- Create: `reports/BALLAST_UNDER_TARGET_FLOOR_SHADOW_2026-10-12.md`

**Policy sketch (recommended defaults):**
```json
{
  "schema": "ballast_under_target_floor_v1",
  "live_apply": false,
  "roles": ["ballast_core"],
  "pairs_allow": ["BTC-USD", "ETH-USD"],
  "max_step_usd": 75,
  "respect_flat_rebalance_cap": true,
  "min_held_pct_of_target_to_skip": 0.35,
  "require_stop_attached": true,
  "require_not_over_target": true,
  "forbid_if_open_upnl_pct_lt": -0.06,
  "min_gap_pct_override": null,
  "note": "Exception only when held << target_w; still inside flat B; not a profit-budget rewrite"
}
```

**Function contract:**
```python
def would_allow_under_target_step(*, pair, role, held_usd, equity_usd, target_w, max_add_usd, open_upnl_pct, stop_attached, flat_cap_usd, cfg) -> dict:
    """Return {allow: bool, step_usd: float, reasons: [...]} — never places orders."""
```

**Steps:**
1. Failing tests: BTC held $55, eq $2260, target 0.18, max_add 0, stop on, upnl &gt; −6% → allow step min(75, target−held, cap).
2. Reject: PAXG, tryout_shell role, upnl −8%, no stop, over target.
3. Wire **shadow log only** into membership matrix row or add-risk detail (`would_under_target_floor`).
4. Cron optional: weekly count would_allow × pairs (local deliver).

**Proof:** isolation green; matrix/check shows shadow field; `live_apply` false.

### Task C2: Live floor (AFTER Brad GO only)

**Files:**
- Modify: `phase6/core/add_risk_sizer.py` `decide_add_size` or caller after max_add=0
- Modify: `config/ballast_under_target_floor.json` → `live_apply: true`
- Kill: `data/state/ballast_under_target_floor_KILL`

**Steps:**
1. When shadow would_allow and live_apply and no kill → clip proposed add to step_usd inside flat cap.
2. Receipt on add-risk / rebalance log line.
3. Anomaly 7d: ballast add count, BTC/ETH weight path, SL hits post-add.

**Risk:** flat chop adds on red ballast — mitigated by upnl floor + stop required + max_step≤75.

---

## §D — P1: W-FLAT-BALLAST-BEFORE-SHELL

**Objective:** Under flat B $75, prefer **BTC/ETH rebuild** (empty or ≪ target) before **new tryout shells** when both compete for the same cautious deploy budget.

### Task D1: Priority policy shadow

**Files:**
- Create: `config/flat_deploy_priority.json` (`live_apply: false`)
- Create: `phase6/core/flat_deploy_priority.py`
- Test: `scripts/phase6/test_isolation_flat_deploy_priority.py`

**Recommended rule:**
1. Regime flat (or transition) + deploy cap $75 active  
2. If BTC or ETH held_usd &lt; `underfill_usd` (e.g. 35% of target_w×eq) **and** not `blocked_late_run`  
3. Then **reserve** up to `min(75, gap_to_band)` for ballast buy **before** composer `new_tryout_seat`  
4. If ballast blocked (late-run / door / SL cooloff), shells may proceed  
5. Never steal from PAXG preserve; never raise cap

**Shadow metric:** `would_prefer_ballast` vs actual seat buys (9 buys week while BTC micro / ETH $0).

### Task D2: Wire composer / deploy gate (AFTER GO)

**Files (likely):**
- `phase6/core/rsi_event_tryout_seat_composer.py` — skip/ defer shell when priority says ballast first  
- and/or rebalance deploy path that emits new buys under flat B  
- `phase6/core/run_phase_deploy.py` — keep late-run blocks  

**Proof:** isolation: empty ETH + free $75 + dual-clear alt → composer status `deferred_ballast_priority` (not silent drop without reason).

**Risk:** miss TIA-style shell TP meat — accept under flat recovery; trail TP already proved on TIA with small $; growth path is still prove→dwell→add-risk on graduated names.

---

## §E — P1 Measure: W-KINDLING-STRUCTURE-DATA

**Objective:** `structure_unknown×4` should be rare; kindling bar fail-closed on **real** structure, not null sensors.

### Task E1: Trace null structure_ok

**Files:**
- `phase6/core/tryout_scale_up_shadow.py` ~430–715 (`pair_structure_snapshot`, `structure_unknown`)
- `phase6/core/run_lifecycle.py` `classify_structure`
- `phase6/core/run_phase_deploy.py` candle fetch

**Steps:**
1. Reproduce on one historical eject pair: call structure snapshot; log `error`, candle len, exception path.
2. Fix only **data/wiring** (fetch limit, signature, cache) — do **not** set `require_structure_ok: false`.
3. Isolation: thin candles → explicit `thin_candles` reason (not generic unknown); happy path structure bool.

**Proof:**
```bash
PYTHONPATH=. .venv/bin/python3 scripts/phase6/test_isolation_tryout_scale_up*.py  # or dedicated new test
# re-run eject cohort card: structure_unknown count ↓ or relabeled
```

---

## §F — P2 Display: W-WR-BUCKET-SPLIT

**Objective:** Headline WR 36% must not mix TIA trail meat with SL/eject tax.

### Task F1: Analyst summary + TG card

**Files:**
- Modify: `phase6/core/analyst_weekly_trade_review.py` (summary already has `exit_buckets` — surface in plain English §0/§1)
- Modify: weekly telegram formatter / agent brief builder
- Test: `scripts/phase6/test_isolation_analyst_weekly_trade_review.py`

**Steps:**
1. Add `exit_wr_by_bucket`: e.g. `{tp_profit: {n, wr, pnl}, eject: {...}, sl: {...}, dust: {...}}`.
2. Plain English line: “Meat TP 2/2 green; SL+eject dominate reds — headline WR is not strategy edge.”
3. Dashboard only if cheap (`phase6-dashboard-signals` / scoreboard) — optional follow-on.

**Proof:** isolation asserts buckets present; dry weekly card contains “Meat” or bucket split line.

---

## Suggested calendar (after GO menu)

| Day | Work |
|-----|------|
| D0 | Brad answers grill round; lock GO menu |
| D0–1 | §A career + §F WR split + §E structure (no money) |
| D1–2 | §B1 autopsy → Brad picks intake lever → §B2 if GO |
| D2–3 | §C1 shadow floor + §D1 shadow priority |
| D7 | Review shadows + eject cohort %; only then consider C2/D2 live GO |
| D14 | Anomaly: tax $, kindling %, BTC/ETH weight, no PAXG drift |

---

## Do not touch (carry forward from weekly §7)

- PAXG preserve MICRO + E1 / scale_path=none  
- scale-window `live_apply` + cooloff hours (hygiene working; 0 open shells at review)  
- post_proof_dwell `live_apply` (ON since 2026-10-06)  
- flat B enforce / cap blowout / park-off thaw  
- perma buy_block expansion for tryout wounds  
- Kelly / deploy_pct live promote  
- dual_agree auto-promote  
- Liquidate remaining BTC/SOL/TIA/PAXG for “clean slate”  

---

## Grill round (answer before money implementation)

❓ **Q1 — ETH SL response after career:** After §A, default action is (a) no knob (b) tryout-only 3% fuse shadow already sketched (c) ballast size cap on re-entry (d) something else?  
➡️ **Recommendation:** (a) unless career shows mis-role size or naked stop; use banking/trail + rebuild priority instead of tighter global SL.

❓ **Q2 — Intake primary lever:** Which single tighten first — (a) eng floor / discipline enforce (b) fewer seats/day (c) longer post-eject cooloff (d) pause system seat loop 7d?  
➡️ **Recommendation:** (a). Cooloff already 24h; seat pause starves path proof; eng floor hits seat→eject root.

❓ **Q3 — Ballast floor live timing:** Ship §C1 shadow only until next weekly, or GO live same week if tests green?  
➡️ **Recommendation:** Shadow through next Sunday weekly; live only with letter GO + kill file.

❓ **Q4 — Flat priority vs shell meat:** Accept fewer alt shells under flat to rebuild BTC/ETH?  
➡️ **Recommendation:** Yes under flat/OFF_TRACK; graduated TIA still holds via dwell; shells remain when ballast band OK or ballast blocked.

❓ **Q5 — Scope this sprint:** Full A–F, or A+F+E only (measure) this week?  
➡️ **Recommendation:** **A + E + F** immediately (no GO); B1 autopsy same window; C1/D1 shadows next; B2/C2/D2 wait GO.

---

## Preflight summary

- **Objective:** Cut process tax + unblock ballast rebuild design; honest WR/kindling sensors  
- **IN scope:** §A–§F as sequenced above  
- **OUT of scope:** Cap blowout, PAXG, dwell/scale-window flips, Kelly, liquidations  
- **Must not touch:** live book default; listed do-not-touch  
- **Decisions locked:** measure-first; no global 3% SL; no kindling force as 0/12 “fix”; shadows before ballast/priority live  
- **Open:** Q1–Q5  
- **Plan path:** `docs/plans/2026-10-12-analyst-weekly-suggestions-impl.md`  
- **BoN:** skipped (single sequenced path; alternatives are GO menu items, not competing architectures)  
- **Proof of done:** career report + WR buckets + structure fix + isolation green + any money lever kill+receipt  
- **Awaiting:** Brad go / adjust on grill answers — **no implementation this turn**

---

## Execution handoff (after Go)

Say which bundle:

1. **`GO measure`** → §A + §E + §F (+ §B1 autopsy) only  
2. **`GO shadows`** → + §C1 + §D1  
3. **`GO intake <lever>`** → §B2 named lever  
4. **`GO live floor`** / **`GO live priority`** → §C2 / §D2 with kill files  

Then: subagent-driven-development per task; commit per task; no silent scope expand into do-not-touch.
