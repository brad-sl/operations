# Scale test lanes — inventory, outcomes, gaps

**Status:** Canonical map v1 — 2026-08-16  
**Audience:** Brad, crypto-analyst, crypto-engineer, orchestrator  
**Frame:** Platform for **100s of traders / 1000s of trades/day** — robust, adaptive, resilient, overall profitable at scale.  
**Not:** Single-book short-term P&L fire drills (live sleeve left as-is unless explicit go).  
**MASTER program:** `P6-SCALE-TEST-LANE-MAP-20260816` (+ gap children)  
**Related:** `docs/testing/ANALYST_TEST_STRATEGY.md`, `docs/testing/ANALYST_TEST_CYCLE.md`, `data/state/trials/TEST_STRATEGY.json`, `reports/PLATFORM_PROFITABILITY_REVIEW_2026-08-13.md`

---

## 0. How to use this doc

| Column | Meaning |
|--------|---------|
| **Item** | Test, trial, shadow pack, or examine card |
| **Kind** | `ISO` isolation · `OFF` offline/Path-B · `SHAD` shadow collect · `TRIAL` MASTER Type:test · `EXAM` examine pack · `GATED` promote path · `OPS` live ops metric |
| **Lane** | Scale property (below) |
| **Status** | Lifecycle: LIVE / DONE / RUNNING / REPORT_READY / QUEUED / GATED / PLANNED / SHIPPED |
| **Decision (outcome)** | Closed enum or open flag — see §0.1 |
| **Flag** | Attention: `OK` · `NEEDS_DECIDE` · `NEEDS_VALIDATE` · `NEEDS_REEVAL` · `COLLECTING` · `BLOCKED` |

### 0.1 Decision vocabulary

| Decision | Meaning |
|----------|---------|
| `drop` | No promote; do not reopen without new evidence / Brad |
| `continue_observe_only` | Keep instrumentation; no allocator/live change |
| `propose_scoped_experiment` | Narrow follow-on OK; not fleet live |
| `no_utility_drop` | Child dig found no utility → drop |
| `idle-with-reason` | Examine pack: no pursue |
| `watch` | Examine lane: monitor only |
| `shipped` | Code/ops live as designed |
| `keep_shadow` | Collect only; live off |
| `keep_off` | Feature stays disabled |
| `—` / `open` | No final decision yet |
| `overdue` | Trial/running past expected close |

**Flags requiring human or agent action:**

| Flag | Action |
|------|--------|
| **NEEDS_DECIDE** | Brad (or trial_cycle decide) — report ready / enum missing |
| **NEEDS_VALIDATE** | Re-run isolation or live audit; confirm still true |
| **NEEDS_REEVAL** | Calendar or evidence clock due (e.g. Stoch ~30d) |
| **COLLECTING** | Shadow/offline clock not satisfied — do not promote |
| **BLOCKED** | Capacity, parent, or gate |

---

## 1. Scale lanes (product properties)

| # | Lane | Scale job | Primary $ / risk lever |
|---|------|-----------|------------------------|
| **L1** | **Exit stack** | Bank winners; bound losers; regime-aware exits | Expectancy (SL-only asymmetry) |
| **L2** | **Capital / regime machine** | Same park/deploy/cap/cooldown knobs for every tenant | Outer risk envelope |
| **L3** | **Manufactured-loss control** | No BUY-into-stop, same-session SL, recycle churn | Less-loss without fake alpha |
| **L4** | **Honest multi-account KPIs** | Deposit-adj truth under load; no silent N/A | Operator trust at fleet size |
| **L5** | **Promotion discipline** | Shadow → audit → one flag; never silent fleet promote | Prevent 1 bad idea × N books |
| **L6** | **Multi-tenant runtime** *(support)* | N runners, isolation, rate limits | Availability / blast radius |
| **L7** | **Signals / entry / selection** *(support)* | What gets proposed | Low priority until L1–L3 solid |

**Staffing default:** L1 → L3 fleet KPI → L2 cap semantics → L5 queue hygiene → L4 soak → L6.  
**Deprioritize:** more entry combos, Kelly live, mid-cycle enable, USDC-as-P&L-fix, single-book trims.

---

## 2. Inventory by lane

### L1 — Exit stack

| Item | Kind | Status | Decision (outcome) | Flag | Notes / artifact |
|------|------|--------|-------------------|------|------------------|
| `test_isolation_shadow_tp` | ISO | DONE | shipped | OK | Shadow TP contract |
| `test_isolation_regime_exit_shadow` | ISO | DONE | shipped | OK | Map shadow path |
| `test_isolation_tier1_exit_glide` | ISO | DONE | shipped | OK | Draft glide only |
| `test_isolation_ledger_sl_truth` | ISO | DONE | shipped | OK | Exit $ truth |
| `run_exit_asymmetry_report` | OFF/OPS | LIVE habit | watch | OK | Latest `reports/EXIT_ASYMMETRY_2026-08-16.md` — SL-dominated |
| `run_tp_trail_path_study` (+ scaffold) | OFF | DONE packs | keep_shadow | COLLECTING | Jul/Aug path studies; rescue-rate input to promote |
| `P6-EXIT-THRESHOLD-REGIME-STUDY` | OFF | DONE packs | keep_shadow | COLLECTING | Aug 6 / Aug 15 |
| `P6-EXIT-BASELINE-POST-BASIS-FIX` | OFF | DONE | keep_shadow | OK | Post-basis baseline |
| `P6-REGIME-EXIT-POLICY-MAP` | SHAD | LIVE_SHADOW | keep_shadow | COLLECTING | Need multi-regime episodes + ~60d class clock |
| `P6-EXIT-PROFIT-LIVE-GATES` | GATED | QUEUED | open | BLOCKED | Parent = map collection + Brad OK — **no live TP** |
| `P6-HARD-EXIT-AUTO-APPLY-GATES` | GATED | QUEUED | open | BLOCKED | operator_approve remains true until T1 evidence |
| `P6-OPT-EX-01-EXITS` | EXAM | Report on disk | watch | NEEDS_VALIDATE | SYNTH: watch; MASTER child row still “QUEUED” — hygiene |
| **GAP-01 Exit promote scoreboard** | OFF/OPS | **DONE** 2026-08-16 | `collecting_calendar` (live) | COLLECTING | `run_exit_promote_scoreboard.py` · ISO PASS · `reports/EXIT_PROMOTE_SCOREBOARD_LATEST.md` |

### L2 — Capital / regime machine

| Item | Kind | Status | Decision (outcome) | Flag | Notes / artifact |
|------|------|--------|-------------------|------|------------------|
| `test_isolation_regime_cash_policy` | ISO | DONE | shipped | OK | |
| `test_isolation_regime_detector_freshness` | ISO | DONE | shipped | OK | |
| `test_isolation_usdc_park_live` | ISO | DONE | shipped | OK | Executor; primary often off |
| `test_isolation_usdc_carry_regime` / `regime_adaptive_usdc` | ISO | DONE | shipped | OK | |
| `test_isolation_park_package` | ISO | DONE | shipped | OK | W0 status-only default |
| `test_isolation_preserve_hold` / `preserve_e1_and_shadow` | ISO | DONE | shipped | OK | MICRO live + E1 |
| `test_isolation_capital_controls_*` | ISO | DONE | shipped | OK | Per-account W1/W2 |
| `test_isolation_capital_disposition_cooldown` | ISO | DONE | shipped | OK | |
| `test_isolation_runner_capital_events` | ISO | DONE | shipped | OK | |
| `test_isolation_stop_exchange_disposition` | ISO | DONE | shipped | OK | SL hold-cash 72h |
| REGIME-CASH continuous + param sweep + validation | OFF/OPS | LIVE | keep_off auto-write | OK | Suggestions only |
| Regime scorecard + USDC assessment | OFF | LIVE | watch | OK | Flat research often prefers USDC hold vs option B experiment |
| `ANALYST-REGIME-FLAT-KNOBS-20260730` | TRIAL | CLOSED | **propose_scoped_experiment** | OK | Keep flat B rebalance envelope; layered paper/shadow path — not fleet loosen |
| `ANALYST-REGIME-TRANSITION-20260727` | TRIAL | CLOSED | **drop** | OK | USDC/park wins; no faster-flip |
| `ANALYST-REGIME-BULL-KNOBS-20260803` | TRIAL | **CLOSED** | **abort** (zombie) | OK | Successor PLAN-BULL-KNOBS-002 parked |
| `PLAN-BEAR-PARK-001` | TRIAL | **PARKED** planned | **hist PASS** · open live | park until **bear** live | Hist dig 2026-08-17; live confirm still required |
| USD hold contingency backtests | OFF | DONE | watch | OK | Contingency evidence |
| Smart Park #3 / USDC live enable | GATED | OFF | keep_off | COLLECTING | Gates: 14D stretch, 30D, Exit WR, trend — revisit ~2026-08-22 |
| `P6-OPT-EX-04-HOLD` | EXAM | Report on disk | watch | NEEDS_VALIDATE | Do-not-reopen holds; stoch reeval ~2026-09-03 |
| **GAP-03 Cap scope matrix** | OFF+ISO | PLANNED | open | — | Cash-only vs rotation vs max-position under flat B |
| **Liq partial redeploy** | OFF/POLICY | **DONE** study+policy 2026-08-16 | `unreliable_as_default` | OK | `LIQUIDATION_ROTATION_REDEPLOY_POLICY.md` · live_partial NO-GO · shadow QUEUED |
| **GAP-07 Bear park emit** | TRIAL | PLANNED | open | BLOCKED | Depends GAP-07a bull close |

### L3 — Manufactured-loss control

| Item | Kind | Status | Decision (outcome) | Flag | Notes / artifact |
|------|------|--------|-------------------|------|------------------|
| `test_isolation_near_stop_add_block` | ISO | DONE | shipped | OK | |
| `P6-NEAR-STOP-REBALANCE-RACE` hard [ARMED-STOP] | ISO+ship | DONE 2026-08-13 | **shipped** | NEEDS_VALIDATE | Live 7d/30d audit still required as habit |
| `test_isolation_same_session_sl` | ISO | DONE | shipped | OK | |
| SL attach / preflight / dust / insufficient fund ISOs | ISO | DONE | shipped | OK | Suite |
| `P6-OPT-EX-02-WOUNDS` | EXAM | Report on disk | watch | NEEDS_VALIDATE | SYNTH: 3d post-fix = 0 manufactured; keep watching |
| Re-entry / breakout layered stress + `test_isolation_bull_reentry_layered` | OFF/ISO | DONE packs | continue_observe_only class | OK | Flat dig path |
| Exit asymmetry rebuy 24/48/72h section | OFF | LIVE habit | watch | OK | Monitor recycle |
| **GAP-02 Fleet wound KPI** | OPS | **DONE** 2026-08-16 | `watch_pre_fix_residual` (live) | OK | `fleet_wound_kpi.py` · post_fix=0 · ISO PASS · alert on breach only |
| **GAP-05 Post-SL re-entry effectiveness** | OFF | **DONE** 2026-08-18 | **tighten** → **enforce_72h** | OK | n_re=29 · 2ndSL=0.79 · code 24h→config 72h · SL% unchanged · watch 14d |

### L4 — Honest multi-account KPIs

| Item | Kind | Status | Decision (outcome) | Flag | Notes / artifact |
|------|------|--------|-------------------|------|------------------|
| `test_isolation_kpi_truth` | ISO | DONE | shipped | OK | Re-run green 2026-08-18 with GAP-06 |
| `test_isolation_deposit_adjusted_returns` | ISO | DONE | shipped | OK | |
| `/api/performance` timeout→N/A fix + 60s cache | OPS | SHIPPED 2026-08-16 | shipped | OK | + single-flight + 15s neg-cache 2026-08-18 |
| Dashboard SQL / runner DB persist ISOs | ISO | DONE | shipped | OK | |
| `test_isolation_trend_repair` | ISO | DONE | shipped | OK | |
| Signal DQ / price freshness / RSI pipeline ISOs | ISO | DONE | shipped | OK | |
| Capital controls no cross-account bleed | ISO | DONE | shipped | OK | |
| Personalized settings W3+ | GATED | QUEUED | open | BLOCKED | Product surface; not expectancy |
| **GAP-06 Multi-account perf soak** | ISO/OPS | **DONE** 2026-08-18 | **ship** | OK | cold 6.7s · warm p95 0.11s · ×8 concurrent; `run_perf_api_soak.py` · DECIDE packet |
| L4 SLA (documented) | process | LIVE | — | OK | warm p95 &lt;1s; cold &lt;8s; never silent wrong 0 |

### L5 — Promotion discipline

| Item | Kind | Status | Decision (outcome) | Flag | Notes / artifact |
|------|------|--------|-------------------|------|------------------|
| `test_isolation_promotion_gates` | ISO | DONE | shipped | OK | |
| `test_isolation_live_param_audit_gate` / param_audit | ISO | DONE | shipped | OK | |
| `test_isolation_shadow_r4` / shadow AB (+ integration) | ISO | DONE | shipped | OK | |
| `run_shadow_drift_check` | SHAD | LIVE tooling | watch | OK | |
| ANALYST-OPT weekly + Path B + leaderboard | OFF process | LIVE | no auto-promote | OK | |
| `TEST_STRATEGY` capacity rules | process | LIVE | — | OK | 1 offline + 1 instru; review≤2 |
| `ANALYST-KELLY-SIZING-TEST-20260721` | TRIAL | CLOSED | **drop** | OK | OOS edge fail; no shadow |
| `STOCH-RSI-PARALLEL-20260721` | TRIAL | CLOSED | **continue_observe_only** | NEEDS_REEVAL | ~30d counterfactual recheck ~**2026-09-03** |
| `ANALYST-STOCH-SL-PREDICTOR-20260803` | TRIAL | CLOSED | **drop** (`no_utility_drop`) | OK | No combo-fish |
| `TEST-COMBINED-INDICATOR-ABLATION` / MACD×RSI×ATR WF | TRIAL/OFF | CLOSED | **drop** | OK | Long-tape fail |
| `TEST-FIB-DISCOUNT-ENTRY-SHADOW-20260815` | OFF SHAD | **CLOSED** | **drop** (CR REJECT) | OK | Packet 2026-08-17; long-tape no_go; follow_on none |
| `TEST-SR-STRUCTURE-ENTRY-SHADOW-20260815` | OFF SHAD | **CLOSED** | **drop** (CR REJECT) | OK | Packet 2026-08-17; less-loss ≠ edge; follow_on none |
| Pair discovery / pool cycling shadow | SHAD | SHADOW_READY | keep_shadow | OK | Live config apply OFF |
| Basket swap CF | SHAD | keep collecting | keep_shadow | OK | control_no_swap benchmark |
| `P6-MID-CYCLE-ALLOCATOR-EVAL` | GATED | QUEUED | **keep_off** (OPT_EX_03) | OK | Study only; no enable |
| `P6-OPT-EX-03-ALLOC` | EXAM | Report on disk | watch / keep_off | NEEDS_VALIDATE | |
| `P6-OPT-EXAMINE-PACK` SYNTH/REV | EXAM | Reports on disk | **idle-with-reason** | **NEEDS_VALIDATE** | MASTER header still IN_PROGRESS/QUEUED children — close hygiene |
| `PLAN-METHOD-ROTATION-001` | TRIAL | PLANNED | open | next ungated offline | BEAR/BULL parked; METHOD can emit when capacity free |
| **GAP-08 Promotion fire-drill** | ISO/OPS | PLANNED | open | — | Inject bad overlay → drift → rollback |

### L6 — Multi-tenant runtime (support)

| Item | Kind | Status | Decision (outcome) | Flag | Notes / artifact |
|------|------|--------|-------------------|------|------------------|
| `SCALING-1000-RUNTIME-SLICE` | GATED | QUEUED | open | BLOCKED | Epic deps / GHL-T0 where required |
| Capital controls multi-account ISO | ISO | DONE | shipped | OK | Partial tenancy |
| **GAP-09 N-runner isolation soak** | ISO | PLANNED | open | — | Account namespace, WAL, kill-one≠kill-fleet |

### L7 — Signals / entry / selection (support — low promote priority)

| Item | Kind | Status | Decision (outcome) | Flag | Notes / artifact |
|------|------|--------|-------------------|------|------------------|
| Stoch parallel + SL-pred | TRIAL | CLOSED | observe_only / drop | NEEDS_REEVAL | See L5 calendar |
| Combo / MACD stacks | TRIAL | CLOSED | **drop** | OK | |
| Fib / SR entry shadows | OFF | **CLOSED** | **drop** CR REJECT | OK | Regimen packets 2026-08-17 |
| RSI / sentiment / evaluation / allocator ISOs | ISO | DONE | shipped | OK | Wiring, not edge proof |
| Opportunity scanner / mid-cycle shadow ISOs | ISO | DONE | keep_off mid-cycle | OK | |
| Daily Dose ISOs + OPT_EX_05 | ISO/EXAM | DONE / watch | watch | OK | Product, not expectancy |

---

## 3. Analyst strategy board (snapshot 2026-08-16)

| plan_id | Workstream | Status | Decision | Flag |
|---------|------------|--------|----------|------|
| PLAN-SIGNAL-STOCH-001 | WS-SIGNAL | done | continue_observe_only (parent) | NEEDS_REEVAL ~2026-09-03 |
| PLAN-SIZING-KELLY-001 | WS-SIZING | done | **drop** | OK |
| PLAN-FLAT-KNOBS-001 | WS-REGIME-KNOBS | done | propose_scoped_experiment | OK |
| PLAN-TRANSITION-001 | WS-REGIME-KNOBS | done | **drop** | OK |
| PLAN-BULL-KNOBS-001 | WS-REGIME-KNOBS | **done** | abort (zombie) | OK | Successor PLAN-BULL-KNOBS-002 **parked** until bull or historical unlock |
| PLAN-BEAR-PARK-001 | WS-REGIME-KNOBS | **parked** planned | hist **PASS** | park until live=bear (shadow confirm) |
| PLAN-BULL-KNOBS-002 | WS-REGIME-KNOBS | **parked** planned | hist **PASS** | park until live=bull (shadow confirm) |
| PLAN-METHOD-ROTATION-001 | WS-METHODOLOGY | planned | open | next ungated when capacity free |

Source: `data/state/trials/TEST_STRATEGY.json`.

---

## 4. Gaps ranked by P(measurable gain at scale)

| Rank | Gap ID | Lane | Title | Why | MASTER child |
|------|--------|------|-------|-----|--------------|
| 1 | **GAP-01** | L1 | Exit promote scoreboard | **DONE** 2026-08-16 — live `collecting_calendar` (~10/60d) | `P6-SCALE-GAP-01-EXIT-PROMOTE-SCOREBOARD-20260816` |
| 2 | **GAP-02** | L3 | Fleet manufactured-loss KPI | **DONE** 2026-08-16 — live `watch_pre_fix_residual` (post_fix=0) | `P6-SCALE-GAP-02-FLEET-WOUND-KPI-20260816` |
| 3 | **GAP-03** | L2 | Rebalance cap scope matrix | $75 leaky (rotations/stacks); product law for all traders | `P6-SCALE-GAP-03-CAP-SCOPE-MATRIX-20260816` |
| 4 | **GAP-04** | L1 | Hard-exit auto-apply evidence clock | Second exit surface; won’t scale on chat approve | `P6-SCALE-GAP-04-HARD-EXIT-EVIDENCE-CLOCK-20260816` |
| 5 | **GAP-05** | L3 | Post-SL re-entry effectiveness | Cooldown ISO ≠ proven less-loss under enforce | `P6-SCALE-GAP-05-POST-SL-REENTRY-EFF-20260816` |
| 6 | **GAP-06** | L4 | Multi-account performance soak | Timeout/N/A class becomes fleet-wide | `P6-SCALE-GAP-06-PERF-API-SOAK-20260816` |
| 7 | **GAP-07** | L5/L2 | Strategy queue unstick | **DONE** 2026-08-17 — bull abort + FIB/SR decide + regimen | `P6-SCALE-GAP-07-STRATEGY-QUEUE-UNSTICK-20260816` |
| 8 | **GAP-08** | L5 | Promotion fire-drill (drift→rollback) | Gates exist; incident muscle thin | `P6-SCALE-GAP-08-PROMO-FIREDRILL-20260816` |
| 9 | **GAP-09** | L6 | N-runner runtime isolation | Scaling-1000 prerequisite | `P6-SCALE-GAP-09-NRUNNER-ISOLATION-20260816` |
| 10 | **GAP-10** | L5 | Basket/discovery long-tape CF | Keep shadow; promote only vs control_no_swap | `P6-SCALE-GAP-10-BASKET-CF-LONGTAPE-20260816` |

### Low P(gain) — do not staff as “scale wins”

- New entry indicator mashups (MACD/Stoch/Fib/SR reopen)  
- Full Kelly live  
- Mid-cycle allocator enable  
- USDC park as path fix  
- Single-account discretionary sleeve trims  

---

## 5. Items needing validation, re-exam, or final decision

### 5.1 NEEDS_DECIDE (close the loop)

| Item | Suggested action |
|------|------------------|
| `ANALYST-REGIME-BULL-KNOBS-20260803-TRIAL` | Finish report if missing → `trial_cycle.py decide` enum |
| `TEST-FIB-DISCOUNT-ENTRY-SHADOW-20260815` | Stamp **drop** (matches final_recommendation) if not on MASTER |
| `TEST-SR-STRUCTURE-ENTRY-SHADOW-20260815` | Stamp **drop** same way |
| `P6-OPT-EXAMINE-PACK` children | Align MASTER status to reports + SYNTH **idle-with-reason** |

### 5.2 NEEDS_VALIDATE (confirm still true)

| Item | Suggested action |
|------|------------------|
| Near-stop / armed-stop race | 7d + 30d ledger: 0 new add→SL after 2026-08-13 |
| OPT_EX_02 wounds | Refresh 7d/30d same-session metric |
| `test_isolation_kpi_truth` + `/api/performance` | Re-run ISO; curl cold+warm cache after dash restart |
| OPT_EX SYNTH “all watch” | Still true after scoreboard/GAP work starts |

### 5.3 NEEDS_REEVAL (calendar)

| Item | When | Action |
|------|------|--------|
| Stoch observe_only parent | ~**2026-09-03** | 30d counterfactual: would substance change? No combo-fish |
| Smart Park #3 / USDC | ~**2026-08-22** (cron) + gates | Score 5 gates; no enable without Brad |
| Regime exit map / live TP | ~60d multi-regime or episode gates | Only then touch `P6-EXIT-PROFIT-LIVE-GATES` |

### 5.4 COLLECTING (do not promote)

| Item | Gate sketch |
|------|-------------|
| Shadow TP + regime exit map | Multi-regime episodes; rescue-rate; Brad OK |
| Hard-exit auto | T1 ≥7d / ≥5 decisions quality; then staged flags |
| Basket/discovery | Beat `control_no_swap` on growth **and** DD |
| USDC / Smart Park package | 14D stretch non-red; 30D improving; Exit WR; trend |

---

## 6. Isolation corpus (reference count)

~**86** `test_isolation_*.py` files under repo (core / research / tests / scripts).  
This map does **not** list every ISO line-by-line when the cluster is “DONE / shipped / OK” — see repo glob `**/test_isolation*.py`.  
Gaps above are where **new** ISO/OFF/OPS tests are still warranted for scale.

---

## 7. Maintenance

| Event | Update |
|-------|--------|
| `trial_cycle.py decide` | Decision column + Flag → OK or follow-on row |
| Weekly analyst-test-strategy | §3 board + emit blockers |
| Exit asymmetry / TP path cron or manual | L1 rows + COLLECTING clocks |
| New MASTER Type:test | Add row under correct lane |
| Gap child DONE | Strike rank table; move to inventory DONE |

**Owner default:** crypto-orchestrator (map hygiene) · crypto-analyst (OFF/TRIAL) · crypto-engineer (ISO/OPS).

---

## 8. North-star reminder

> Better **risk-adjusted returns** and **less loss** as *system* properties — evidence before live change; platform process > bag lottery; ~5%/mo average underwritable, not 20%/mo fantasy.
