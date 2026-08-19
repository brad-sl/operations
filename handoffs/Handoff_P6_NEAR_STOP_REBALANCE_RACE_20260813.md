# Task Handoff Document

**Task ID:** `P6-NEAR-STOP-REBALANCE-RACE-20260813`  
**Parent Task:** `P6-NEAR-STOP-ADD-BLOCK-20260805` (DONE — soft gap/unrealized gate; this is the **race** follow-on)  
**Assigned To:** crypto-engineer  
**Reviewer:** crypto-orchestrator  
**Date Assigned:** 2026-08-13  
**Kanban:** `t_4b5f3741` · review `t_bbcb9333`  
**GitHub:** https://github.com/brad-sl/operations/issues/22  
**Ops:** `P6-OPS-20260813-001`  
**Source:** `reports/PLATFORM_PROFITABILITY_REVIEW_2026-08-13.md` §8 #1  
**Priority:** P0 (manufactured SL inventory)

### Objective
Stop the runner from **adding size to a pair that already has an armed exchange stop** when a fill is imminent or a rebalance BUY can race the stop (same session / seconds–minutes). Existing near-stop filter is not enough.

### Context & Background
- Soft gate `filter_trade_plan_near_open_stop` / `evaluate_near_stop_add_block` shipped 2026-08-05 (`near_stop_min_gap_pct` 2%, `near_stop_max_unrealized_pct` −1%). Isolation: `scripts/phase6/test_isolation_near_stop_add_block.py`.
- Live still saw **same-session BUY then SL** (RAVE 2026-08-11; BTC 2026-08-12) — rebalance vs open-stop **timing race**, not “SL ignored.”
- 30d exit asymmetry: 39 `stop_loss_exchange` @ −$99; Exit WR ~12%. Extra adds into stops are free losses.
- Review thesis: close manufactured-loss loop **before** hunting alpha or live TP.

### Scope & Boundaries

**Must Do:**
- Trace ARCH-4 rebalance + mid-cycle (even if mid-cycle is off) + any allocator BUY path vs `stop_loss_manager` / open Coinbase stops.
- Block BUY/add when: (a) pair has a live protective stop, **and** (b) price is inside configured gap **or** a stop is already triggered/pending cancel-replace **or** last BUY on that pair is inside a short race window.
- Cover **second add** to an existing position (not only new pairs).
- Isolation test with real ledger-shaped fixtures reproducing RAVE/BTC class (buy then SL same pair <2h, ideally <5m).
- 7d ledger audit script or one-shot report: count same-session BUY→SL after the fix (baseline vs post).
- Restart runner only if code path is on the live cycle; document restart.
- Update MASTER verification when done.

**Must Not Do / Touch:**
- Do **not** widen SL, thaw REGIME-CASH, flip live TP, enable mid-cycle allocator, or change basket.
- Do **not** shorten 72h SL rebuy / clear the $460 cash hold.
- Do **not** rewrite historical ledger rows silently.
- Do **not** treat dashboard pair % as stop truth — use exchange/open-stop + ledger.

**Files / Directories to Work In:**
- `phase6/core/runner_capital_events.py` (existing near-stop filter)
- Rebalance coordinator / `phase6/core/phase6_runner.py` / allocation execute path
- `scripts/phase6/test_isolation_near_stop_add_block.py` (extend or sibling test)
- Optional: `scripts/phase6/audit_same_session_sl.py` (can share with metric task)
- `docs/MASTER_TASK_TRACKING.md` (this block only)

**Files / Directories to Leave Untouched:**
- `config/regime_cash_policy.json`, `config/exit_automation.json` live knobs
- Basket / discovery / OPT promote paths
- Dashboard KPI math except a one-line comment if you surface a count

### Expected Deliverables
1. Code: rebalance/add cannot race an armed stop (named function + call site on **live** execute path).
2. Isolation test **PASS** (new cases + old LINK 1.11% gap still blocked).
3. Short report: `reports/NEAR_STOP_REBALANCE_RACE_2026-08-13.md` (or dated) with before/after ledger counts.
4. MASTER block → DONE with evidence commands.

### Success Criteria
- Isolation covers: gap block (existing), **in-flight stop**, **BUY then SL same pair < N minutes** would have been blocked.
- 7d (or available) ledger: same-session add→SL count documented; target **0 new events** after deploy.
- Runner still attaches SL on legitimate new BUYs (`sl_attached` finalize path unchanged).
- No live config risk-knob change.

### Constraints & Requirements
- Real data / fixtures only. No fake prices in prod.
- Isolation wrappers; `OPENBLAS_CORETYPE=GENERIC` if numpy tests flake.
- Permanent paths under repo (not Kanban scratch).

### Validation Method
```bash
cd /home/brad/projects/crypto-trading-bot
PYTHONPATH=. python3 scripts/phase6/test_isolation_near_stop_add_block.py
# plus any new test file
pgrep -af phase6.core.phase6_runner
# ledger audit output in reports/
```
Orchestrator re-runs tests and traces the **runner execute path**, not only the helper.

### Notes & Warnings for Sub-Agent
- Soft gate already exists — this ticket is the **race / second-add / stop-pending** hole.
- Same-session **metric** is a **sibling** task (`P6-SAME-SESSION-SL-METRIC-20260813`); share a small auditor if useful, do not block on the brief UI.
- Reviewer card must not complete on “tests passed in worker” alone.
