# FABLE 5 — PHASE 6 DELTA RE-GATE REPORT
**Date:** 2026-06-10 | **Scope:** Targeted re-gate of P6-152 / P6-153 / P6-154 + 60-tick artifact + isolation tests | **Prior verdict:** Paper CONDITIONAL GO (3 conditions), Live NO-GO

---

## 1. Executive Summary

The three paper conditions from the previous re-gate were addressed with real structural changes, not telemetry patches. Evidence quality is good but not perfect:

- **P6-152 (max_deployable cap): MET.** Clamp logic, config sourcing, isolation test (both branches), and visible `(capped)` enforcement on every telemetry line of the 60-tick run.
- **P6-153 (post-fill telemetry): MET — structurally, with an evidence caveat.** The recompute-after-`execute_rebalance` restructure is the correct fix and the low-cash branch of the P6-152 test indirectly confirms dynamic sourcing. However, because the cap was active on **every** tick of the 60-tick run ($6500 cash → $800 capped, always), the artifact itself never *displays* a dynamically changing post-fill deployable. The fix is accepted; the artifact alone would not have proven it.
- **P6-154 (executed rebalance counter): PARTIALLY MET → accepted with a new finding.** The counter is wired and the isolation test passes. But the run shows **60/60 rebalances with 1 error tick (tick 2)** — meaning the error tick still incremented the "executed" counter. The stated semantics (`len(plan) > 0 OR executed fills`) are ambiguous and contradict the word "executed." This is logged as **P6-159** and must be resolved in the next routine artifact (not a re-gate).

**P6-156 injections** were exercised and visible in the artifact (stale ages at ticks 7/25/42, cooldown simulation at tick 35), which improves G3/G9 paper coverage — with the caveat that injection-driven coverage proves the harness path, not necessarily the runner's organic path (noted as P6-162).

**Verdicts:**
- **Paper: GO** — the 60-tick artifact is accepted as gate evidence. Two verification riders (P6-159, P6-160) must appear resolved in the *next standard paper artifact*; no special re-gate required.
- **Live: NO-GO** — unchanged. P6-127 remains the top live blocker; P6-155, P6-157, P6-158, CR-03 untouched this wave, as declared.

---

## 2. Condition-by-Condition Verdict

| Condition | Evidence | Verdict |
|---|---|---|
| **P6-152** max_deployable cap | Isolation test PASS (clamp-to-$800 high-cash + min-reserve low-cash branches); `(capped)` on all 60 telemetry lines; config-sourced; handoff doc | ✅ **MET** |
| **P6-153** post-fill telemetry state | Structural recompute after `execute_rebalance`; counter test logic; handoff doc. Caveat: 60-tick run cannot visually distinguish post-fill vs static because cap saturates every line | ✅ **MET** (structural; artifact visibility masked — see P6-160) |
| **P6-154** executed rebalance counter | Isolation test PASS; end-of-run counter present and non-zero. Caveat: error tick (tick 2) still counted → semantics violate "executed" | ⚠️ **PARTIALLY MET — accepted with rider P6-159** |

---

## 3. Updated Gate Table (G1–G9)

| Gate | Area | Prior | Now (Paper) | Now (Live) | Notes |
|---|---|---|---|---|---|
| G1 | Config / keys / startup | PASS | **PASS** | PASS | No regressions; reserve config loader extended cleanly |
| G2 | Holdings / state integrity | PASS | **PASS** | CONDITIONAL | Tick-2 injected failure handled correctly; only 1 error in 60 ticks; no erroneous Fresh Start |
| G3 | Sentiment pipeline | CONDITIONAL | **PASS (paper)** | CONDITIONAL | Canonical v3 + 60min aging active; stale decay now *demonstrated* via injections (ticks 7/25/42). Live freshness path still unverified |
| G4 | Reserve / funding constraints | **FAIL (paper cond.)** | **PASS** | CONDITIONAL | P6-152 closed with test + artifact evidence. Live funding-constraint tightness still open |
| G5 | Plan generation / rebalance logic | CONDITIONAL | **CONDITIONAL** | NO-GO | 60/60 rebalance rate suggests no hold/no-trade path was exercised (P6-161); P6-157 live paths unaudited |
| G6 | Execution / quantization | CONDITIONAL | **CONDITIONAL** | **NO-GO** | P6-127 (2dp price rounding) untouched; P6-155 ADA increments prep-only; P6-157 open |
| G7 | Telemetry / observability | **FAIL (paper cond.)** | **PASS** | CONDITIONAL | P6-153 structural fix accepted; counter telemetry present but semantics rider P6-159 |
| G8 | Durability / persistence | CONDITIONAL | CONDITIONAL | NO-GO | CR-03 / P6-158 unchanged this wave (declared out of scope) |
| G9 | Guards / cooldown / recovery | CONDITIONAL | **PASS (paper)** | CONDITIONAL | Cooldown-recovery injection at tick 35 visible with guard note; organic runner-path coverage caveat (P6-162) |

---

## 4. Scored Findings

### 4.1 Verified Closures (this delta)

| ID | Title | Prior Sev | Status | Evidence |
|---|---|---|---|---|
| P6-152 | Deployable ignores max_deployable cap | High | **CLOSED** | Isolation test PASS (both branches); `(capped)` on 60/60 telemetry lines; clamp `min(cash − min_reserve, max_deployable)` confirmed in harness |
| P6-153 | Telemetry computed from pre-fill/static state | High | **CLOSED** | Recompute moved after `execute_rebalance`; reserve enforcement + plan generation consume updated state; low-cash test branch confirms dynamic sourcing |
| P6-154 | Rebalance counter never incremented / mismatched | Medium | **CLOSED (with rider P6-159)** | Isolation test PASS; counter present in summary; semantics rider below |
| P6-156 | Stale-aging + cooldown recovery untested in artifact | Medium | **PARTIALLY CLOSED (paper)** | Injections at ticks 7/25/42 + tick 35 visible in log. Runner-organic-path caveat → P6-162 |

### 4.2 Remaining Open (carried, unchanged this wave — as declared)

| ID | Title | Sev | Scope | Status |
|---|---|---|---|---|
| P6-127 | Live `get_price` 2dp rounding | **Critical (live)** | Live | OPEN — top live blocker |
| P6-155 | ADA `base_increment` full live metadata + test | High (live) | Live | OPEN — harness prep only |
| P6-157 | Buy/sell rebalance path quantization (order_executor / exchange_client) | High (live) | Live | OPEN — only stop path fixed |
| P6-158 | (carried) | Medium | Live | OPEN |
| CR-03 | Durability / crash-recovery | Medium-High (live) | Live | OPEN |
| G4-live | Funding constraint tightness in live runner | Medium | Live | OPEN |

---

## 5. New Findings (P6-159 → P6-162)

**P6-159 — "Executed" rebalance counter increments on error tick (Medium, paper).**
60 ticks, 60 rebalances, 1 error. The intentional tick-2 G2 holdings failure tick still contributed to the executed count. Combined with the stated semantics (`len(plan) > 0 OR executed fills`), the counter can count *planned-but-not-filled* or *errored* ticks as "executed." This makes the headline metric unreliable as an execution KPI. **Fix:** increment only on ≥1 confirmed fill (or successful `execute_rebalance` return), and report `plans_generated` separately. Extend `test_fable5_p6_154_rebalance_counter.py` with an error-tick case and a plan-but-zero-fill case.

**P6-160 — Cap saturation masks post-fill telemetry visibility (Low, evidence-quality).**
Every line shows `$800.00 (capped)`, so the artifact cannot visually demonstrate dynamic post-fill deployable (P6-153). **Fix:** next routine run should include a segment where `cash − min_reserve < max_deployable` (lower starting cash or raised cap) so deployable visibly moves post-fill.

**P6-161 — 100% rebalance rate; hold/no-trade path unexercised (Medium, paper).**
Every tick produced a plan. Either drift thresholds are effectively bypassed in dry-run, or harness allocations guarantee perpetual drift. Either way, the no-trade path — and proof that the counter does *not* increment on a hold tick — is absent from the artifact. **Fix:** include at least a few hold ticks in the next run (e.g., post-convergence steady state).

**P6-162 — Injections exercise harness paths, not necessarily runner-organic paths (Low-Medium).**
The tick-35 cooldown event is a harness-side simulation (`Simulating stop-out + 24h cooldown recovery`). Confirm the artifact shows a *consequence* (e.g., DOGE-USD excluded from plans for ticks ≥35, or a recovery-quality-gate decision logged), not just the injection banner. If only the banner is present, P6-156 paper coverage is announcement-level, not behavioral.

**No regressions detected** in previously closed items (sentinel, key normalization, private-key newline, stop `reduce_only` removal) based on the declared diff scope and clean 60-tick run (1 intentional error, no unhandled crashes).

---

## 6. Top Remaining Items (Priority Order)

1. **P6-127** — live price rounding (Critical, live blocker #1)
2. **P6-157** — live buy/sell quantization audit
3. **P6-155** — ADA base_increment live metadata + test
4. **P6-159** — counter semantics (paper rider — resolve in next routine artifact)
5. **CR-03 / P6-158** — durability
6. **P6-161 / P6-160 / P6-162** — paper artifact quality riders (fold into next routine run)
7. **G4 live funding-constraint tightness**

---

## 7. Final Recommendations

### PAPER: **GO** ✅
The three conditions from the prior CONDITIONAL GO are satisfied: P6-152 fully, P6-153 structurally (evidence masked by cap saturation but corroborated by tests), P6-154 functionally with a semantics rider. The 60-tick artifact is **accepted as gate evidence**. Paper trading may continue and extend duration.

**Riders (next routine artifact, no special re-gate):**
1. Fix P6-159 counter semantics (fill-confirmed increments; separate `plans_generated`), extend the isolation test.
2. Include a non-cap-saturated segment (P6-160) and at least one hold/no-trade tick (P6-161).
3. Show a behavioral consequence of the tick-35 cooldown injection, not just the banner (P6-162).

### LIVE: **NO-GO** ❌ (unchanged)
Nothing in this wave touched the live blockers, as honestly declared. Minimum bar before a live gate review: **P6-127 closed with isolation test + evidence**, P6-157 rebalance-path quantization audit complete, P6-155 ADA metadata pull verified, and a durability story for CR-03. The paper-side discipline shown in this delta is the right pattern — replicate it for the live closures.

— Fable 5