# Rebalance = book only · RSI-event = new buys · X sparse — Switch Plan


**Status:** VALIDATE SHIPPED (Brad GO 2026-09-18) — Task 1 helper + budget + measure CLI live.
Full replace of 2× full-book X still needs explicit cutover GO (`x_query_split.rebalance_candidates_only=true`).
RSI paid probe is ON under hard caps (track 1); place_orders still false.
> **For Hermes:** After R0 RSI-event shadow **passes** closeout, staff this plan task-by-task. **No live knobs until Brad GO on cutover.** Use subagent-driven-development if implementing.

**Status:** **PROPOSED — ARMED FOR POST-R0 SWITCH**  
**Brad GO to save plan:** 2026-09-16  
**Switch gate:** R0 observe closeout **2026-09-17 19:35 PT** completes **and passes** reliability bar  
**Mode until GO:** measure-only · current 2× full-book X stays · no paid event X · no orders from this plan alone

---

## Goal

Once RSI-event shadow proves a **reliable pattern**, switch the platform so:

1. **Rebalance** is strictly **book maintenance** (weights, cash/powder, protectives, trims) — **not** new tryout / new-buy seats.
2. **New buys** are driven by the **RSI wash → (knife) → fresh X → tryout** path only.
3. **X queries** shrink to **RSI-filtered prospects** + **rebalance candidates** only — replace full-pool 2× spray, do **not** stack on top of it.

**Architecture:** Two clocks, one scarce sensor.

| Job | Clock | Does | Does not | X spend |
|-----|-------|------|----------|---------|
| **Rebalance** | 09:00 / 21:00 PT (or existing slots) | Held book: drift fix, cash/powder, SL/E1, trims, weight targets | Open new tryout seats; full-universe Sent | **Rebalance candidates only** (held + names actually in the rebalance plan) |
| **New buys** | RSI-event (gated) | Wash → knife OK → top-K X → $75 tryout + full safety stack | Hitchhike on rebalance Sent; spray pool | **RSI-filtered top-K** (≤1–2 pairs/day, cooldown ≥6h) |

**Tech stack:** Phase 6 runner / hybrid rebalancer / `regime_cash_policy` / tryout stack / `rsi_event_x_tryout_shadow` (promote from shadow) / `fetch_x_sentiment` + refresh path / Hermes cron.

**North star:** Cut manufactured sensor-clock luck + X bill; keep process-tax fences ($75 / 1–2 seats / SL / blocks). month_path still ~5%/mo deposit-adj — this is reliability, not alpha claim.

---

## Why (locked 2026-09-16)

- Empty funnel was largely **new-buy decisions hitchhiked on rebalance X** + eng aging.
- Full-book 2× X (~12–19 pairs, ~2 batches/slot) pays every day whether anyone can buy.
- R0 shadow (extended ~48h) shows event path **fires when wash exists** and **goes quiet when structure is gone** — viable cheaper sensor *if* it replaces book spray for buys.
- Per decision: top-K pair query ≪ one full rebalance Sent pull. **Total bill only drops if 2× full-pool is cut**, not if event X is added on top.

---

## Hard constraints (do not weaken)

- **No live cutover** until R0 closeout **PASS** + explicit Brad GO on this plan’s cutover step.
- **Replace X, don’t stack:** kill or shrink full-pool 2× when event + rebalance-candidate X goes live.
- **Tryout caps stay:** missfire / buy_block / $75 / max 2 seats / post-SL blocks.
- **`live_membership_swaps` = false**; dual_agree ≠ promote; free/Adanos stay shadow primary.
- **PAXG / Preserve:** rebalance must never treat ballast as a basket rebalance buy; E1 path untouched by buy split.
- **No auto-promote** from RSI+X green days.
- Claims: `ATTENTION_ONLY` / measure N tags until live GO packet.

---

## R0 pass bar (switch arming)

Closeout job: `phase6-rsi-event-x-shadow-observe-close` `17289c281af6` @ **2026-09-17 19:35 PT**.

**PASS (minimum to *staff cutover*, not auto-flip):**

- Observe window completed (extended ~48h).
- ≥3 shadow ticks with non-empty candidate scoring.
- ≥2 ticks with trigger_hits > 0 (wash + stale eng pattern real).
- ≥2 ticks with top-K selection (ranker not always empty/noise).
- Quiet ticks when RSI left wash band (sensor doesn’t spam).
- No requirement for paid X or live fills in the observe window.

**FAIL →** do **not** switch; extend observe or fix shadow; keep current 2× X.

**PASS →** this plan becomes **implementation queue**; cutover still needs **Brad GO** on Task “Live cutover” (can be same day as closeout if Brad says go).

---

## Target X policy (post-switch)

### A) Buy-path X (event)

- Universe: tryout-eligible doors only (v1/v2 + thaw while active) — **not** full opportunity pool.
- Trigger: RSI wash band (default 0–40) + eng stale/under floor + not buy_block.
- Rank + **top-K ≤ 2**; daily budget **≤1–2 pair queries**; per-pair cooldown **≥6h**.
- Kill switch: same-session SL spike or X spend spike → disable spend_x, keep shadow.

### B) Rebalance-path X (book)

- Universe: **held positions** ∪ **pairs with non-zero target delta in this rebalance plan**.
- Never: full `opportunity_pool` / scout universe “just in case.”
- If rebalance plan is empty / no drift: **0** X on that slot is OK.

### C) Explicitly retired

- 2×/day full-basket X as **buy decision fuel**.
- Using aged eng=0 between slots as a hard buy block without event refresh opportunity.
- Mid-cycle “wait for next rebalance Sent” as the only way into a tryout.

### D) Display / free

- Non-held, non-wash names may stay free/aged for dashboard **display only** — not live buy SSOT.
- Free + Adanos remain shadow; not primary.

---

## Target buy vs rebalance behavior

### Rebalance slot

- Runs hybrid / allocation / powder / protective reattach as today for **book**.
- **Refuses new tryout seats** and **refuses new-buy legs** tagged as opportunity/tryout entry.
- May still **trim / add-to-held** only if policy explicitly allows **existing seat** maintenance (document in cutover; default = no size-up from rebalance without separate GO).
- Sentiment tilt on rebalance, if any, uses **B) candidate X** only.

### New buy path

- Armed from RSI-event (and knife filter when R1 evidence allows).
- Spend X only for top-K; then `evaluate_buy_entry` + full gates.
- Seat via existing tryout path only ($75, 1–2 seats, SL attach A1, bag_id A2).
- Must work **mid-cycle** (not only inside rebalance window) — latch / `can_buy_before_next_rebalance` / cycle coordinator aligned.

---

## Implementation tasks (bite-sized; post-PASS + GO)

### Task 0: Closeout gate packet

**Objective:** Record R0 pass/fail and arm or block this plan.

**Files:**
- Read: `data/state/rsi_event_x_tryout_shadow_observe_24h.json` (or successor closeout artifact)
- Write: `reports/RSI_EVENT_X_OBSERVE_CLOSEOUT_LATEST.md`
- Update: `reports/LUCK_LADDER_STATUS_LATEST.md`, this plan status line

**Steps:** Run closeout (cron) → if PASS, set plan status `ARMED — AWAITING CUTOVER GO`; if FAIL, `BLOCKED — EXTEND R0`.

---

### Task 1: Define rebalance-candidate set (measure-only)

**Objective:** Pure function: held ∪ plan-delta pairs; never full pool.

**Files:**
- Create: `phase6/core/rebalance_x_candidates.py`
- Test: `scripts/phase6/test_isolation_rebalance_x_candidates.py`

**Behavior sketch:**
```python
def rebalance_x_candidates(*, held_pairs: set[str], plan_pairs: set[str], pool: set[str]) -> set[str]:
    # held ∪ plan only; intersect pool for safety; never expand to full pool
    return (set(held_pairs) | set(plan_pairs)) & set(pool)
```

**Verify:** isolation proves full pool of 19 → candidates ≤ held+plan; empty plan + one held → {held}.

---

### Task 2: Shadow score X spend CF (book vs full 2×)

**Objective:** Days of counterfactual: “candidate-only X call count vs full-book batches.”

**Files:**
- Create: `phase6/core/x_spend_split_shadow.py` (or extend platform metrics)
- Cron optional quiet daily board
- Report: `reports/X_SPEND_SPLIT_SHADOW_LATEST.md`

**No live API change yet.** Measure only.

---

### Task 3: Rebalance refuses new tryout buys

**Objective:** At rebalance boundary, strip/block BUY legs that are new tryout seats.

**Files (likely):**
- Modify: `phase6/core/regime_cash_policy.py` (entry filter / allow_new_buys scoping)
- Modify: `phase6/core/rebalancing/hybrid_rebalancer.py` and/or `phase6/core/rebalance_coordinator.py`
- Modify: `phase6/core/phase6_runner.py` rebalance path
- Test: isolation — rebalance plan with tryout new-buy → rejected; trim held → allowed per policy

**Default policy:** `rebalance_allow_new_tryout_buys = false` (new knob, default false on cutover).

---

### Task 4: Promote RSI-event path to gated spend_x (still capped)

**Objective:** Optional live **sensor** only after Brad GO: top-K paid X with hard daily budget.

**Files:**
- Modify: `phase6/core/rsi_event_x_tryout_shadow.py` → split or promote to `rsi_event_x_tryout.py` with `spend_x` fence
- Wire: single-pair fetch helper (reuse `fetch_x_sentiment` batch of 1)
- Test: spend_x false never calls network; spend_x true respects top_k + daily budget + cooldown

**Still no orders until Task 5.**

---

### Task 5: Mid-cycle tryout buy wire

**Objective:** When event X clears floor + full gates, buy via **existing tryout executor path**, not rebalance plan injection.

**Files:**
- Cycle coordinator / runner entry path / tryout latch
- Test: isolation + dry-run; live only with GO

**Safety stack:** $75, seats, SL attach, bag_id, post-SL block, missfire — unchanged.

---

### Task 6: Cut full-pool 2× X to candidate + event policy

**Objective:** Replace refresh universe.

**Files:**
- Modify: `fetch_x_sentiment.py` / `phase6/scripts/refresh_sentiment.py`
- Cron: `phase6-x-sentiment-live-2x` becomes rebalance-candidate refresh at slots; event path owns prospect X
- Update: `docs/HERMES_CRON_SSOT.md`, `phase6-sentiment-pipeline` skill

**Verify:** one refresh log shows N_pairs = |candidates| ≪ pool; event log shows ≤2 when fired.

---

### Task 7: Kill switches + docs + FAQ

**Objective:** Operator-visible rollback and glossary.

**Files:**
- Config flags: `x_policy.mode = full_book | split_event_rebalance` (default stay full_book until cutover)
- Rollback: set mode full_book; disable spend_x; restart runner
- Update: `docs/faq/Internal_Trading_Platform_FAQ.md` (rebalance vs buy clocks)
- Update: luck ladder R0 → **SWITCHED** or **PARTIAL**

---

## Cutover checklist (single Brad GO moment)

- [ ] R0 closeout PASS recorded  
- [ ] Task 1–2 green (candidate set + spend CF)  
- [ ] Task 3 green in isolation (rebalance no new tryout)  
- [ ] Task 4 spend_x caps isolation green  
- [ ] Brad GO cutover  
- [ ] Task 5 dry-run then live micro path  
- [ ] Task 6 X policy flip (`split_event_rebalance`)  
- [ ] 24–48h watch: X spend, same-session SL, empty-funnel rate  
- [ ] Kill switch ready  

**Rollback:** `x_policy.mode=full_book`, `spend_x=false`, re-enable prior 2× cron shape, runner restart. No basket membership changes required.

---

## Out of scope (this plan)

- Auto-promote / live_membership_swaps  
- Dropping tryout $75 / 2-seat caps  
- Free/Adanos as live primary  
- Cover-style CRP / new scout research  
- Changing 09:00/21:00 **rebalance time** (only **job** of the slot)  
- R2–R6 luck ladder work (parallel tracks stay separate)

---

## Related artifacts

| Artifact | Role |
|----------|------|
| `docs/plans/2026-09-15-rsi-event-x-tryout-shadow.md` | R0 shadow design |
| `docs/plans/2026-09-15-luck-ladder-platform-refine.md` | Parent ladder |
| `docs/plans/2026-09-13-empty-funnel-sent-clock-mitigation.md` | A1/A2/B1 clock fixes |
| `phase6/core/rsi_event_x_tryout_shadow.py` | Event sensor (shadow) |
| `phase6/core/knife_filter_shadow.py` | R1 structure (parallel) |
| `fetch_x_sentiment.py` / `phase6/scripts/refresh_sentiment.py` | Live X today |
| Cron closeout `17289c281af6` | Gate timestamp 2026-09-17 19:35 PT |

---

## Decisions log

- **2026-09-16 Brad:** Save as **proposed plan to switch to after Shadow RSI test completes and passes.** Rebalance → book only; new buys → RSI path; X → RSI prospects + rebalance candidates only (replace full-pool 2×).
- **Not GO yet:** live cutover, paid event X, or disabling 2× full-book before PASS + cutover GO.

---

## Staff next (after 2026-09-17 19:35 PT)

1. Ingest closeout → PASS/FAIL on this plan header.  
2. If PASS: ping Brad with one-screen cutover ask (Tasks 1–3 first vs full).  
3. If FAIL: propose observe extend length only — **do not** partial-flip X.
