# Luck Ladder — Platform Refine While Idle (2026-09-15)

> **For Hermes:** Execute rungs per schedule on Kanban `crypto-bot-project`. Measure-only until Brad GO. No live knobs, no auto-buy, no auto-promote.

**Goal:** While the book sits idle / armor-closed, systematically remove *manufactured* luck (clock, knife entries, SL-default exits, fee path, seat lottery, size ladder, regime mismatch) so higher-quality tryouts and an evidence-backed TP path become possible — without pretending variance disappears.

**Architecture:** Seven rungs (R0–R6). Each is shadow/CF first, isolation-tested, cron or one-shot scheduled, MASTER + Kanban tracked. Graduation between rungs is **evidence gates**, not calendar alone. Live path only after explicit Brad GO with N tags and offline-strategy-honesty.

**Tech stack:** Phase 6 core modules, existing tryout/exit/PC-0x spines, Hermes cron + Kanban, isolation tests under `scripts/phase6/`.

**North star link:** month_path ~5%/mo deposit-adj; process tax = manufactured SL leakage, not missing alpha.

**Philosophy (Brad):** Cannot delete tape variance. *Can* stop requiring luck on when we look, whether the wash is a knife, whether exit is only SL, and whether house fee eats the tryout.

---

## Constraints (hard)

- **No live orders** from any rung until Brad GO.
- **No paid X** until R0 high bar passes **and** separate GO for X probe.
- **No knob / recovery thaw / force_eligible changes** from this epic alone.
- **live_membership_swaps** stays false.
- Free/Adanos remain shadow primary; dual_agree ≠ promote.
- Claims: `ATTENTION_ONLY` / `LESS_LOSS` / `N_INSUFFICIENT` — never edge without N.
- Tryout caps stay: missfire / buy_block / $75 / max 2 seats.

---

## Luck stack map

| Rung | Luck factor | “Get lucky” today | Controllable | Primary metric |
|------|-------------|-------------------|--------------|----------------|
| **R0** | Sensor clock | Structure up, eng aged to 0 | High | Would-trigger ticks; top-K stability |
| **R1** | Knife vs wash | RSI wash → continuation down → fast SL | High | SL-72h / mean R net on would-buys by arm |
| **R2** | Exit geometry | SL fires; TP almost never | High | TP bank vs SL bank; CF net $ after fees |
| **R3** | Fee / path tax | Every RT ~1.6% before edge | High | Realized fee_bps; limit fill vs skip |
| **R4** | Seat lottery | Wrong name of 1–2 doors/day | Medium | Mark@H / MAE after fees by ranker |
| **R5** | Size ladder | $75 green once → full sleeve coin flip | Medium | Scale-rule CF vs stay-micro |
| **R6** | Regime alignment | Alt wash into BTC soft-down | Medium | Would-buy SL rate by BTC regime bucket |

**Out of scope / anti-goals:** more rebalance slots, free sentiment as primary, new indicator religion, auto-promote best paper pair.

---

## Schedule (execution calendar)

Times America/Los_Angeles. Adjust only with Brad note.

| When | Rung | Action | Gate to next |
|------|------|--------|--------------|
| **2026-09-15 → 09-16 15:21** | R0 | 24h observe (cron 4×/day + closeout) | High bar: ≥3 ticks, ≥2 trigger>0, ≥2 top-K |
| **2026-09-15 start (parallel)** | R1 | Knife-filter shadow + offline CF on would-buys / hist tryouts | Isolation green; 7d shadow crumbs |
| **2026-09-17 19:35 after R0 closeout** | R0→decision | Pass → arm switch plan `2026-09-16-rebalance-book-vs-rsi-buy-x-split.md`; fail → extend observe | Brad GO for cutover + any X spend |
| **2026-09-16–17** | R2 | Exit CF scoreboard v2 (extend PC-02): sl_only / shadow_tp / time / trail | Honest board; no live_apply |
| **2026-09-17–18** | R3 | Limit-first counters refresh (PC-05 spine); tryout-path focus | Cost evidence only |
| **After R1 ≥7d crumbs OR clear knife winner** | R4 | Rank quality shadow (last_x_ok, ledger, beta, post-SL age) | Beats RSI-depth-only on mark@H |
| **After ≥N live tryout fills (or rich hist)** | R5 | Size graduation packet shadow | CF scale vs micro |
| **After R1 arms stable** | R6 | Regime-conditioned tryout allow shadow (not membership swap) | SL rate by regime; live gate OFF |

**Parallel allowed:** R0∥R1; R2∥R3 after R0 decision; R4 waits on R1 signal; R5/R6 later.

**Recurring crons (quiet / no_agent):**

| Job | Schedule | Role |
|-----|----------|------|
| `phase6-rsi-event-x-tryout-shadow` | `20 7,11,15,19 * * *` | R0 collector |
| `phase6-rsi-event-x-shadow-observe-24h-close` | one-shot ~+24h from 2026-09-15 15:21 | R0 closeout |
| `phase6-knife-filter-shadow` | TBD on R1 ship (`30 7,19 * * *` proposed) | R1 collector |
| `phase6-exit-luck-cf` | TBD on R2 ship (`45 12 * * *` proposed) | R2 daily board |
| Existing PC-05 / attribution / platform spine | keep | R3/R2 feeds |

---

## R0 — Sensor clock (IN FLIGHT)

**Status:** SHIPPED shadow + 24h observe window.

**Artifacts:**
- `phase6/core/rsi_event_x_tryout_shadow.py`
- `scripts/phase6/run_rsi_event_x_tryout_shadow.py`
- `scripts/phase6/test_isolation_rsi_event_x_tryout_shadow.py`
- `docs/plans/2026-09-15-rsi-event-x-tryout-shadow.md`
- State: `data/state/rsi_event_x_tryout_shadow_*.json`
- Crumbs: `data/state/rsi_event_x_tryout_shadow_crumbs.jsonl`
- Observe: `data/state/rsi_event_x_tryout_shadow_observe_24h.json`

**Behavior:** Tryout-eligible (+ thaw) universe; RSI≤40 + eng stale; rank top-2; sim buy gates; **no orders, no paid X**.

**High bar (probe discussion only):**
- ≥3 shadow ticks in window
- ≥2 ticks with `trigger_pool_n > 0`
- ≥2 ticks with top-K selected

**Ladder:**
1. Observe would-trigger (now)
2. If bar passes → budgeted single-pair X probe (GO)
3. If X proves → promote path with evidence (GO)

---

## R1 — Knife vs wash filter

**Objective:** On RSI-event / tryout would-buys, score arms that reduce fast-SL knives without killing all entries.

**Arms (initial):**
1. `rsi_only` — baseline (current event trigger)
2. `rsi_reclaim` — require close back above prior 1h low or simple reclaim rule within N bars
3. `rsi_delay_1_3` — wait 1–3 bars, no new low
4. `rsi_standdown_c` — stand-down when standdown filter C / r24 hot adverse (wire existing shadow if present)

**Deliverables:**
- Create: `phase6/core/knife_filter_shadow.py`
- Create: `scripts/phase6/run_knife_filter_shadow.py`
- Create: `scripts/phase6/test_isolation_knife_filter_shadow.py`
- Create: `phase6/scripts/run_knife_filter_shadow_cron.sh`
- Reports: `reports/KNIFE_FILTER_SHADOW_LATEST.md`
- State: `data/state/knife_filter_shadow_latest.json` + crumbs

**Success (shadow):** Isolation green; offline CF table with N, mean R net, SL-72h rate per arm; plain_english; no live gate.

**Must not:** Auto-block live buys; change RSI cap in policy.

---

## R2 — Exit geometry CF scoreboard

**Objective:** Make exit luck measurable: actual RT vs counterfactual exits.

**Arms:** `sl_only` (actual/default), `shadow_tp`, `time_stop_72h`, `trail_x` (params from existing shadow TP / exit stack).

**Build on:** `phase6/core/exit_stack_proof.py` (PC-02), `phase6/core/shadow_tp.py`, attribution weekly.

**Deliverables:**
- Create/extend: `phase6/core/exit_luck_cf.py` (or extend exit_stack_proof with CF arms table)
- CLI + isolation + daily report `reports/EXIT_LUCK_CF_LATEST.md`
- Dashboard optional later (read-only)

**Success:** Lot-matched CF net $ after fees; MAE/MFE; N tags; explicit **no promote** until gates.

**Must not:** `live_apply` TP/hard_exit without Brad GO.

---

## R3 — Fee / path tax (limit-first)

**Objective:** Quantify self-inflicted tax; prefer unfilled skip over taker when edge thin.

**Build on:** PC-05 `limit_first_evidence.py`.

**Deliverables:**
- Refresh tryout-path slice of limit-first counters
- Report join: would-buy (R0/R1) × limit attempt/fill/skip × fee_bps
- Cron hygiene if missing

**Success:** Cost board honest; CF limit-rest vs market on same signals = **cost cut claim only**.

---

## R4 — Seat lottery / rank quality

**Objective:** Rank top-K doors with more than RSI depth + last X.

**Features:** last_x clears floor, ledger quality / missfire, novelty class, BTC beta / soft-down haircut, hours since last SL on pair.

**Deliverables:**
- `phase6/core/tryout_door_rank_shadow.py`
- Compare rankers: `rsi_depth`, `last_x_ok_first`, `composite_v1`, `random_eligible`
- Forward mark@H + max excursion honesty

**Depends:** R1 so rank ≠ sharper knives only.

---

## R5 — Size ladder graduation

**Objective:** Explicit packet before $75 → larger sleeve.

**Packet sketch:** +1R or time-boxed MFE, SL not hit, sent still ok → seat2 / +$X; else stay micro or eject.

**Deliverables:**
- `phase6/core/tryout_size_graduation_shadow.py`
- CF: always $75 vs scale-after-rule on hist tryouts

**Depends:** Real fills or rich hist N.

---

## R6 — Regime-conditioned tryout allow

**Objective:** Reduce alt-wash buys into BTC soft-down continuation.

**Behavior:** Shadow **tryout allow** overlay (not basket membership swap):
- soft_down → reclaim-only / smaller / or deny
- chop/up → current rules

**Build on:** `regime_arm_switch` BTC buckets; **live_membership_swaps false**.

**Deliverables:**
- `phase6/core/regime_tryout_allow_shadow.py`
- SL rate / mean R by regime × arm

---

## Evidence → promote ladder (global)

```text
Shadow crumbs → isolation green → 7d/21d board with N
  → Brad GO for next sensor (X probe) or live gate
  → Never dual_agree / paper-green alone as promote
```

**X probe (post-R0 only, separate GO):** ≤1–2 pair queries/day, per-pair cooldown ≥6h, floor 0.30, still no auto-buy until further GO.

---

## Kanban / MASTER

| ID | Title | Priority |
|----|-------|----------|
| LUCK-LADDER-20260915 | Epic hub | P0 |
| LUCK-R0-SENSOR-CLOCK | R0 observe + decision | P0 |
| LUCK-R1-KNIFE-FILTER | R1 knife shadow | P0 |
| LUCK-R2-EXIT-CF | R2 exit luck CF | P1 |
| LUCK-R3-LIMIT-TAX | R3 limit-first tax | P1 |
| LUCK-R4-DOOR-RANK | R4 rank quality | P2 |
| LUCK-R5-SIZE-GRAD | R5 size graduation | P2 |
| LUCK-R6-REGIME-TRYOUT | R6 regime tryout allow | P2 |

Board: `crypto-bot-project`. Handoffs under `handoffs/platform/`.

---

## Tracking board (plain English)

Update `reports/LUCK_LADDER_STATUS_LATEST.md` on each rung ship and on R0 closeout.

| Rung | Status | Next check |
|------|--------|------------|
| R0 | OBSERVE 24h | 2026-09-16 ~15:21 PT closeout |
| R1 | BUILD | This session → ship shadow |
| R2 | SCHEDULED | After R0 decision |
| R3 | SCHEDULED | With/after R2 |
| R4 | BLOCKED on R1 crumbs | ~+7d R1 |
| R5 | BLOCKED on fills/N | when tryouts exist |
| R6 | BLOCKED on R1 arms | after R1 stable |

---

## Task checklist (implementation)

### Epic setup
1. This plan on disk ✓
2. MASTER section + status report
3. Kanban hub + R0–R6 cards, schedule/block as above
4. Commit plan + tracking

### R1 first build (execute now)
1. Isolation test skeleton (arms, labels)
2. `knife_filter_shadow.py` core
3. CLI + cron wrapper
4. Wire optional join to R0 latest would-buys
5. Run offline hist slice if OHLCV available
6. Isolation green + commit + Kanban comment

### Later rungs
Follow deliverables above when schedule unlocks; do not skip evidence gates.

---

## References

- Empty funnel / sent clock: `docs/plans/2026-09-13-empty-funnel-sent-clock-mitigation.md`
- R0 plan: `docs/plans/2026-09-15-rsi-event-x-tryout-shadow.md`
- Platform metrics: `docs/plans/2026-09-14-platform-metrics-spine.md`
- PC-02 exit stack, PC-05 limit-first handoffs
- Skills: `offline-strategy-honesty`, `phase6-exit-profit-shadow`, `phase6-sentiment-pipeline`, `code-isolation-testing`
