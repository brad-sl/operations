# Handoff — ANALYST Kelly sizing test (fractional risk budget)

**Task ID:** `ANALYST-KELLY-SIZING-TEST-20260721`  
**Parent / epic:** ANALYST-OPT (sizing / risk-budget layer; not a new entry signal)  
**Assigned To:** Crypto-Analyst (`crypto-analyst` / analyst role)  
**Date Assigned:** 2026-07-21  
**Status:** **CLOSED / DROP** (2026-07-21) — dig-further OOS fail; no shadow

**Prior Status:** **REPORT_READY / REVIEW_PENDING** — offline complete 2026-07-21; awaiting Brad `decide` (proposed `drop`, no shadow)  
**Source:** User + tigerfl0w Kelly / Bell Labs thread (2026-07-20); Scotty applicability review 2026-07-21  
**MASTER:** `docs/MASTER_TASK_TRACKING.md` → `ANALYST-KELLY-SIZING-TEST-20260721`

---

### Objective

Test whether a **fractional Kelly risk-budget** (half/quarter Kelly + hard caps), estimated from **real closed-trade edge** \(p, b\), improves growth rate and/or drawdown vs current fixed knobs (`deploy_pct`, per-trade risk, regime util) — **research + shadow-ready recommendation only**, no live config write without Brad.

---

### Context & Background

- Thesis (external): blown accounts are usually **right of the Kelly curve** (size), not entries. Formula \(f^* = p - (1-p)/b\); practitioners use **≤ half-Kelly** because inputs are wrong.
- Live stack today sizes via **inv-vol + sentiment + `deploy_pct=0.72` + REGIME-CASH util/caps + reserve** — not from measured edge. Closest cousin: `DEPLOY-PCT-078-LEAN-IN` shadow + `run_deploy_pct_shadow_eval.py`.
- Platform is **multi-asset concurrent / correlated**, not sequential single bets → pure full Kelly is a poor drop-in; **fractional Kelly as risk-at-stop budget**, then clamp to existing envelopes, is the testable form.
- **Notional ≠ risk:** with SL ~3%, Kelly \(f\) applies to **capital at risk if SL hits**; `position_usd ≈ (f * equity) / sl_pct`, then min with max_position, rebalance_cap, deploy_pct, regime `target_max_util_pct`, withdrawal reserve.
- Stoch RSI is a **separate** signal/scorer instrumentation track; Kelly is sizing math on the ledger — **no hard dependency**.

---

### Dependency

| ID | Role |
|----|------|
| `ANALYST-STOCH-RSI-COMPARE` | **Soft only** — different surface (signal vs size). **Cleared to run in parallel** (2026-07-21). |

Do **not** wait for Stoch DONE to start Tier 0/1/1b. Still must not write live config without Brad.

---

### Scope & Boundaries

**Must Do:**

1. **Tier 0 — pure math + isolation**
   - Module (suggested): `phase6/research/kelly_sizing.py` (or `phase6/core/risk/kelly.py` if analyst prefers shared lib — keep research-first).
   - API: `kelly_fraction(p, b) -> f_full`, `fractional_kelly(p, b, frac=0.5)`, `risk_budget_to_notional(f, equity, sl_pct)`, `clamp_to_envelopes(...)`.
   - Isolation tests: article numbers (55% WR, 2:1 → full ≈ 0.325, half ≈ 0.1625); bad \(p\) overestimate; zero/negative edge → \(f≤0\); clamps never exceed regime/reserve/max_position.

2. **Tier 1 — real ledger edge (mandatory real data)**
   - Estimate \(p\), avg win / avg loss (or R-multiple vs configured SL) from:
     - `trades/phase6_trades_*.csv`
     - `TradeLedger` / since-go-live window
   - Prefer **exit WR style** consistent with lean-in guard (`scripts/audit_live_exit_wr.py` pattern): non-zero PnL sells; document sample size and CI / uncertainty.
   - Min-sample gate: if \(n\) too small, **report insufficient** — do not invent \(p,b\).
   - Optional slices: by pair, by regime (if tagged), SL exits vs rotation exits — only if \(n\) supports it.

3. **Tier 1b — counterfactual sizing paths (offline)**
   Compare growth / max DD / ruin-near-reserve on the same trade sequence or equity path proxy:
   - **Baseline:** current live knobs (`deploy_pct=0.72`, 1% risk language, 3% SL, regime util)
   - **Full Kelly** risk budget (expect: reject for live)
   - **Half-Kelly** + hard caps
   - **Quarter-Kelly** + hard caps
   - **Half-Kelly then map → `deploy_pct` / risk_usd** candidate knobs only

4. **Tier 2 — shadow/OPT path (only if Tier 1 shows non-trivial signal)**
   - Map recommended fraction → candidate knobs (prefer existing levers):
     - `risk_management.deploy_pct` and/or explicit **risk_usd per BUY**
     - never bypass REGIME-CASH / withdrawal reserve
   - Prefer shadow overlay pattern (`activate_deploy_pct_shadow.py` / new overlay JSON) + eval script sibling to `run_deploy_pct_shadow_eval.py`
   - If using scenario pack: real OHLCV via `./run_backtest.sh`; always `--compare-production` when ARCH-4; honest brief with `run_id`
   - Proposals → `analyst_proposed_backlog.json` **shadow only**

5. **Honest assessment** (Crypto-Analyst personality): cite sample sizes, estimation error trap, multi-asset correlation gap, notional-vs-risk bug class if still present in executor.

**Must Not Do / Touch:**

- Live `trading_config_phase6.json` / `regime_cash_policy.json` writes without Brad + gates
- Full Kelly as recommended live default
- Fake/placeholder prices, fabricated trades, synthetic \(p,b\) when ledger empty
- Replacing RotationStrategy / sentiment entries with “Kelly signal”
- Starting before handoff is READY (cleared 2026-07-21; Stoch is not a hard gate)
- Silent auto-promote of deploy_pct

**Files / Directories to Work In:**

- `phase6/research/` (module, eval, optional scenario pack)
- `phase6/tests/` or `phase6/research/test_isolation_kelly_*.py`
- `reports/` (final markdown + JSON results)
- `handoffs/analyst/` (this handoff + completion note)
- `data/state/analyst_proposed_backlog.json` (proposal only if gated)
- `docs/MASTER_TASK_TRACKING.md` (status/evidence)

**Files / Directories to Leave Untouched (unless Brad gre-lights after gates):**

- Live runner production config, secrets, systemd units
- REGIME-CASH operator thaw (flat B) without explicit promote
- Marketing / SEO docs (`PROJECT_BOUNDARY`)

---

### Expected Deliverables

| # | Artifact |
|---|----------|
| 1 | `kelly_sizing` module + isolation tests PASS |
| 2 | `reports/KELLY_SIZING_TEST_YYYY-MM-DD.md` + matching `.json` (p, b, n, f*, clamps, path metrics) |
| 3 | Explicit go / no-go for shadow trial; if go, overlay sketch + eval command |
| 4 | Optional backlog proposal id `ANALYST-YYYYMMDD-KELLY-*` shadow-only |
| 5 | MASTER entry → **DONE** with commands + key numbers |

---

### Success Criteria

- [ ] Stoch predecessor closed before start
- [ ] Real ledger-derived \(p,b\) (or explicit “insufficient n” stop) — no placeholders
- [ ] Isolation tests cover article example + clamp safety
- [ ] Baseline vs half/quarter Kelly comparison on growth **and** max DD (and reserve stress if available)
- [ ] Recommendation distinguishes **risk fraction** vs **notional deploy_pct**
- [ ] No live config mutation
- [ ] MASTER + this handoff updated with evidence paths

---

### Constraints & Requirements

- **Real data only** (platform rule)
- NumPy-safe runs: `./run_backtest.sh` or `OPENBLAS_CORETYPE=GENERIC` when harness touches numpy
- Persona: `docs/research/CRYPTO_ANALYST_PERSONALITY.md` — honest, no overclaim sim≠live
- Align with ANALYST-OPT gates: promotion_gates, live param audit if shadow path
- Prefer extending deploy_pct shadow eval pattern over new parallel decision path in runner

---

### Validation Method

```bash
cd /home/brad/projects/crypto-trading-bot
# isolation
PYTHONPATH=. python3 phase6/research/test_isolation_kelly_sizing.py   # or pytest path chosen
# report exists + JSON keys: p, b, n_trades, f_full, f_half, recommendation
# if shadow proposed:
python3 phase6/research/run_deploy_pct_shadow_eval.py   # or kelly-specific eval
# MASTER block Status: DONE
```

Orchestrator/Brad: skim report executive summary; reject any full-Kelly live recommend without extreme evidence.

---

### Suggested procedure (analyst)

1. Confirm MASTER: `ANALYST-STOCH-RSI-COMPARE` = DONE; flip Kelly → `in_progress`.
2. Implement Tier 0 + tests.
3. Pull ledger / trades; compute edge table; stop if \(n\) weak.
4. Offline compare sizing paths; write `reports/KELLY_SIZING_TEST_*.md`.
5. If half-Kelly-capped beats baseline on DD-adjusted growth **or** similar return lower DD → draft shadow knob map; else **no-go** with numbers.
6. Ingest proposal only if gates-shaped; update MASTER + handoff status.

---

### Notes & Warnings

- Live Exit WR (~66% on prior lean-in window) ≠ backtest ~55% — do not mix metrics without labeling.
- Concurrent correlated book → simultaneous Kelly / corr haircut; at minimum **document** that single-bet Kelly overstates safe \(f\).
- `order_executor` 1% path may be **notional** not loss-at-stop — call this out if still true; fix is engineer follow-on, not silent assume.
- REGIME-CASH remains outer envelope; Kelly lives **inside** util/cap, not instead of park in bear/unknown.
- Cost: keep offline/local; no new paid API burn.

---

### Queue position

```
… → ANALYST-STOCH-RSI-COMPARE (finish) → ANALYST-KELLY-SIZING-TEST-20260721 (this) → optional shadow trial / engineer wiring
```
