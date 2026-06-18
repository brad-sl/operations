# PHASE 6 — FABLE 5 RE-GATE REVIEW (POST-FIX + 50-TICK PAPER RUN)
**Date:** 2026-06-10 | **Reviewer:** Fable 5 | **Scope:** Batch 4 closures + non-criticals #1/#2 + 50-tick paper artifact

---

## 1. Executive Summary

The fix cluster (P6-125/142/143/144/145/146/148/151) is **substantively verified** by the isolation tests, E2E completion doc, and the 50-tick paper run. The sentinel contract, projected-reserve enforcement, key normalization, private-key newline handling, stop quantization, and `reduce_only` removal are all evidenced as closed. The G2 injected-failure test on tick 2 behaved exactly as required (no erroneous Fresh Start flip; harness continued).

However, the 50-tick artifact itself surfaces **three anomalies that the fix work introduced or exposed**, and the run leaves **two coverage gaps** that prevent full gate closure:

1. **`max_deployable_usd: 800.0` is in config but telemetry shows `deployable_after_reserve=$6300.00`** — the deployable cap appears unenforced in the projection path. This is a G4 partial regression/gap (P6-152).
2. **Telemetry is static across 50 ticks** (`cash=$6500.00 total=$6500.50` every tick) **while PaperTrader accumulates BTC/ETH positions** — the reserve telemetry is reading stale or non-integrated state (P6-153).
3. **`Rebalances attempted: 0` while plans were generated and positions accumulated** — counter/semantics mismatch; the *execution* leg of the rebalance path was never counted (or never exercised) in this run (P6-154).

**Verdicts:**
- **Paper continuation: CONDITIONAL GO** — continue, with 3 conditions (below) to be fixed before the run is treated as gate-closing evidence.
- **Live: NO-GO** — 5 remaining blockers (P6-127 carried + P6-152/153/154/157).

---

## 2. Updated Gate Scores (G1–G9)

| Gate | Definition | Prior | Now | Evidence |
|---|---|---|---|---|
| **G1** | Fresh Start = bootstrap-only on *verified* zero (tri-state) | CONDITIONAL | **PASS** | E2E Fresh Start scenario on verified-zero; tick-2 injected failure did NOT flip to Fresh Start; harness note confirms tri-state respected. |
| **G2** | Never promote on API error / unverified `{}` — structured sentinel everywhere | FAIL | **PASS** | Sentinel fix in exchange_client + LPM full rewrite; `test_fable5_p6_151_sentinel_leak.py` PASS; tick-2 simulated `get_holdings` failure handled with no phantom positions. |
| **G3** | Enriched positions: always `-USD` keys + numeric `value_usd`; key-shape normalization in rebalance_plan | FAIL | **PASS** | `rebalance_plan` normalizes `{"value_usd"}`, `{"usd_value"}`, bare float (test PASS); mixed shapes normalized across all 50 ticks without error. |
| **G4** | Withdrawal reserve enforced in **every** path incl. projected post-allocation targets | FAIL | **CONDITIONAL** | `enforce_withdrawal_reserve(..., target_allocations_usd=projected)` wired and telemetry on every tick — good. **But** `max_deployable_usd=800` not reflected in `deployable_after_reserve=$6300` (P6-152), and telemetry values are static despite position accumulation (P6-153). Min-reserve leg passes; cap leg unproven/likely unenforced. |
| **G5** | Sentiment: canonical v3 + 60min half-life aging + queues + 24h cooldown in recovery + quality gates | CONDITIONAL | **CONDITIONAL** | v3 + aging active every tick (raw + aged printed; SOL non-zero aged). **But** "ages sampled: [0 ... 0] (all fresh)" — stale-aging decay never exercised in-run; 24h cooldown path has zero evidence in this artifact (E2E doc covers aging but not cooldown-in-recovery explicitly) (P6-156). |
| **G6** | Sticky holdings + proportional rebalancing | CONDITIONAL | **CONDITIONAL** | Plans generated every tick; E2E "sticky + reserve projection" scenario claimed. But with `Rebalances attempted: 0` and static cash, the *execution-side* sticky behavior over repeated cycles is not demonstrated by this run (P6-154). |
| **G7** | Live order safety: no `reduce_only`, full quantization via product metadata on sizes/prices/stops | FAIL | **CONDITIONAL** | `place_stop_limit_sell` now uses `_quantize_size`/`_quantize_price`, `reduce_only` removed (E2E stop test verified). **But** quantization on non-stop order paths (market/limit buys/sells) is not evidenced in the provided artifacts (P6-157). |
| **G8** | Credentials + metadata correctness (private_key newline, ADA metadata) | FAIL | **CONDITIONAL** | Newline `replace("\\n","\n")` in `_ensure_live_client` "and similar init path" — test PASS, but the vague "similar path" phrasing leaves coverage of *all* key-load paths unconfirmed (P6-158). ADA-USD `price_increment: 0.0001` added; **`base_increment` (size step) not mentioned** — `_quantize_size` for ADA stops is unproven (P6-155). |
| **G9** | Stability/durability over extended cycles | FAIL | **PASS (paper) / CONDITIONAL (live)** | 50 ticks, 1 error (intentional), 0 crashes, 0 unhandled exceptions. Durability/CR-03 items remain carried for live. |

**Gate tally: 4 PASS, 5 CONDITIONAL, 0 FAIL** (prior: 0/3/6).

---

## 3. Scored Findings

### 3a. Verified Closures (no further action; retained for audit trail)

| ID | Title | Closure Evidence |
|---|---|---|
| P6-125/151 | Bare `{}` sentinel leak / unverified promotion | Structured sentinel `{positions, verified, error, value_usd}` enforced; isolation test PASS; tick-2 injection clean. **CLOSED.** |
| P6-142 | rebalance_plan key mismatch | Normalization of 3 value shapes; test PASS; 50 ticks clean. **CLOSED.** |
| P6-143/148 | Reserve projected no-op / bypass | Projected targets via inverse-vol passed to `enforce_withdrawal_reserve`; per-tick telemetry. **CLOSED** (min-reserve leg; cap leg → P6-152). |
| P6-144 | private_key `\n` literal | Replace applied in init; test PASS. **CLOSED** (residual coverage question → P6-158). |
| P6-145 | `reduce_only` + unquantized stop params | Removed + quantized; E2E DOGE/ADA stop test. **CLOSED** (ADA size step → P6-155). |
| P6-146 | Missing ADA metadata | ADA-USD entry added. **PARTIALLY CLOSED** → P6-155. |

### 3b. Open / New Findings

---

**P6-152 — `max_deployable_usd` cap not enforced in deployable computation**
- **Category:** Risk Controls / G4
- **Priority:** 0 | **Severity:** High
- **Evidence:** `config/trading_config_phase6.json` sets `max_deployable_usd: 800.0`. Every-tick telemetry: `deployable_after_reserve=$6300.00` (= 6500 cash − 200 min reserve). Expected: `min(cash − min_reserve, max_deployable) = $800.00`.
- **Impact:** In live, the system would deploy up to ~8× the configured deployable ceiling. Defeats the purpose of staged capital exposure. This is a live-blocker.
- **Recommended Fix:** In `phase6_runner._perform_daily_rebalance` (and harness telemetry), clamp deployable to `max_deployable_usd` before building projected targets; add isolation test asserting cap binds when `cash − reserve > max_deployable`.
- **Effort:** Small (0.5d incl. test)
- **Dependencies:** None
- **Backlog:** Immediate — pre-live blocker; fix before next gate-closing paper run.

---

**P6-153 — Reserve telemetry static across 50 ticks despite accumulating positions**
- **Category:** Observability / State Integrity / G4
- **Priority:** 1 | **Severity:** Medium (High if it reflects projection inputs, not just display)
- **Evidence:** Identical line all 50 ticks: `cash=$6500.00 total=$6500.50 deployable_after_reserve=$6300.00`. Yet summary JSON shows BTC-USD + ETH-USD positions accumulated via PaperTrader. If positions were bought, cash should decrease and/or total should move with prices. Also `total − cash = $0.50` is inconsistent with material holdings.
- **Impact:** Either (a) telemetry reads a static initial snapshot — observability defect, masking real reserve breaches; or (b) the reserve enforcement itself is computing against stale state — a G4 correctness defect. Cannot distinguish from the artifact; must assume worst case until proven otherwise.
- **Recommended Fix:** Source telemetry and `enforce_withdrawal_reserve` inputs from the *post-execution* PaperTrader/LPM state each tick; add a test asserting telemetry cash decreases after a simulated fill.
- **Effort:** Small–Medium (1d)
- **Dependencies:** P6-154 (shared root cause likely)
- **Backlog:** Immediate — condition for paper continuation evidence validity.

---

**P6-154 — `Rebalances attempted: 0` contradicts generated plans + accumulated positions**
- **Category:** Execution Path / Telemetry Semantics / G6
- **Priority:** 1 | **Severity:** Medium
- **Evidence:** Summary: "Rebalances attempted: 0 (paper mode; plans generated but no live execution)" yet "Final positions accumulated via PaperTrader". Either PaperTrader fills came from a path that bypasses the rebalance counter, or positions arrived via a non-rebalance path (bootstrap?), or the counter is miswired.
- **Impact:** The 50-tick run does **not** demonstrate the rebalance *execution* leg (sticky behavior under repeated executed rebalances, reserve enforcement post-fill). Weakens G4/G6 evidence; also means run metrics can't be trusted for live-readiness sign-off.
- **Recommended Fix:** Define counter semantics (plan-generated vs. plan-executed vs. orders-placed); wire PaperTrader executions through the same counted path the live runner uses; re-run 50 ticks with non-zero executed rebalances.
- **Effort:** Small (0.5–1d)
- **Dependencies:** P6-153
- **Backlog:** Immediate — condition for paper continuation evidence validity.

---

**P6-155 — ADA-USD metadata: `base_increment` unverified**
- **Category:** Live Safety / Metadata / G7-G8
- **Priority:** 1 | **Severity:** Medium
- **Evidence:** Fix notes mention only `price_increment: 0.0001` for ADA-USD. `_quantize_size` requires the size step (`base_increment`); no artifact shows it present or tested for ADA. (Coinbase ADA-USD `base_increment` must come from real product metadata — do not hardcode without verification.)
- **Impact:** ADA stop/order sizes may be unquantized or wrongly quantized → live order rejections at exactly the moment a protective stop is needed.
- **Recommended Fix:** Pull full product metadata (price + base increments, min size) from the live API for all traded pairs; add assertion test that every pair in config has both increments.
- **Effort:** Small (0.5d)
- **Dependencies:** None
- **Backlog:** Pre-live blocker batch.

---

**P6-156 — Paper run coverage gap: stale-aging decay + 24h cooldown unexercised**
- **Category:** Test Coverage / G5
- **Priority:** 2 | **Severity:** Medium
- **Evidence:** "Sentiment ages sampled: [0 ... 0] (all fresh in this run)". No tick exercised half-life decay on stale data in-run; no evidence of 24h cooldown on recently-stopped pairs during recovery in this artifact.
- **Impact:** G5 cannot be promoted to PASS on this run alone. Cooldown-in-recovery was a prior explicit requirement; an untested cooldown means a stopped-out pair could be re-entered immediately in live.
- **Recommended Fix:** Add harness injection: (a) pre-aged sentiment timestamps (e.g., 90/180 min old) to verify decay math in-loop; (b) simulate a stop-out + recovery cycle and assert 24h cooldown blocks re-entry.
- **Effort:** Medium (1–2d)
- **Dependencies:** Harness injection framework (exists — reuse G2 pattern)
- **Backlog:** Next paper run requirements.

---

**P6-157 — Quantization coverage limited to stop path; buy/sell order paths unverified**
- **Category:** Live Safety / G7
- **Priority:** 1 | **Severity:** High (live), N/A (paper)
- **Evidence:** Fix notes and E2E cover `place_stop_limit_sell` quantization only. No artifact demonstrates `_quantize_size`/`_quantize_price` on market/limit buy and sell paths used by rebalance execution.
- **Impact:** First live rebalance could submit unquantized sizes → rejected orders → partial/skewed allocations while reserve math assumes fills.
- **Recommended Fix:** Audit every order-construction site in exchange_client; route all through a single quantizing builder; isolation test per order type per pair.
- **Effort:** Medium (1–2d)
- **Dependencies:** P6-155 (metadata completeness)
- **Backlog:** Pre-live blocker batch.

---

**P6-158 — Private-key newline normalization: "similar init path" coverage unconfirmed**
- **Category:** Live Safety / Credentials / G8
- **Priority:** 2 | **Severity:** Low-Medium
- **Evidence:** Fix description: applied "in `_ensure_live_client` **and similar init path**" — imprecise. Test PASS covers at least one path.
- **Impact:** If any client-construction path (e.g., a one-off script, stop-attachment path, or reconnect path) loads the key without normalization, live auth fails intermittently and confusingly.
- **Recommended Fix:** Centralize key loading in one helper; grep for all `private_key` reads; test each entry point.
- **Effort:** Small (0.5d)
- **Dependencies:** None
- **Backlog:** Pre-live hardening.

---

**P6-127 (CARRIED) — Live `get_price` rounds to 2dp**
- **Category:** Live Safety / Pricing | **Priority:** 1 | **Severity:** High (live)
- **Evidence:** Listed as carried-open in MASTER; no fix claimed in this bundle.
- **Impact:** For sub-cent assets (DOGE ~$0.xx, ADA, SHIB-class), 2dp rounding destroys sizing/stop math — up to 100% relative error.
- **Fix:** Return full-precision Decimal/str from API; quantize only at order construction. **Effort:** Small. **Backlog:** Pre-live blocker batch.

---

**Carried, unaddressed (unchanged scores):** G4 funding-constraint tightness analysis; durability/CR-03 items; wrapper-tail questions (now partially subsumed by P6-157).

---

## 4. New Issues Introduced/Exposed by the Fixes

1. **P6-152** — the new explicit `withdrawal_reserve` config block introduced a `max_deployable_usd` key that the new projection code apparently ignores (config–code contract drift created by the fix itself).
2. **P6-153** — the new per-tick telemetry, while welcome, reads static state — added observability that currently *misleads*.
3. **P6-154** — the harness augmentation surfaced (or created) a counter-semantics mismatch between plan generation and execution.

No regressions detected in the sentinel, normalization, newline, or stop-path fixes themselves.

---

## 5. Top Remaining Items (priority order)

| # | ID | Item | Blocks |
|---|---|---|---|
| 1 | P6-152 | Enforce `max_deployable_usd` cap | Live + gate-closing paper |
| 2 | P6-153 | Telemetry/enforcement reading static state | Paper evidence validity |
| 3 | P6-154 | Rebalance counter vs. PaperTrader fills mismatch | Paper evidence validity |
| 4 | P6-127 | Live get_price 2dp rounding | Live |
| 5 | P6-157 | Quantization on non-stop order paths | Live |
| 6 | P6-155 | ADA `base_increment` verification | Live |
| 7 | P6-156 | Stale-aging + 24h cooldown coverage in paper | G5 closure |
| 8 | P6-158 | Key-load path centralization | Live hardening |
| 9 | — | Durability/CR-03 carried items | Live |
| 10 | — | G4 funding-constraint tightness analysis | Live |

---

## 6. Final Recommendation

### Paper Continuation: **CONDITIONAL GO**
Continue paper trading immediately. Conditions (must land before the *next* run is accepted as gate-closing evidence):
1. **P6-153** — telemetry/enforcement sourced from live post-fill state each tick.
2. **P6-154** — rebalance execution counted and demonstrably exercised (non-zero executed rebalances in next 50-tick run).
3. **P6-152** — `max_deployable_usd` clamp wired (this is cheap and changes paper behavior materially; do not accumulate paper history under an uncapped deployable).
Recommended for same run: P6-156 injections (stale ages + cooldown scenario).

### Live Readiness: **NO-GO**
Remaining live blockers: **P6-127, P6-152, P6-153 (worst-case interpretation), P6-155, P6-157**, plus G5 cooldown evidence (P6-156) and carried durability/CR-03 items. Substantial progress — 6 of the prior live defects are closed with verified tests — but the deployable-cap gap and unverified buy-path quantization are exactly the class of defect that causes real capital loss on day one. Re-gate for live after the next instrumented 50-tick run plus the pre-live blocker batch.

— Fable 5