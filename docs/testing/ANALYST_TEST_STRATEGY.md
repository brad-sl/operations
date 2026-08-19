# Analyst Test Strategy (portfolio driver)

**Status:** Canonical v1 — 2026-07-21; **E2E closeout:** `docs/testing/TEST_REGIMEN_E2E.md` (2026-08-17)  
**Owner:** Crypto-Analyst  
**North star:** Improve **risk-adjusted returns** and **cut losses** via evidence — not more simultaneous experiments.  
**Does not:** Auto-write live `regime_cash_policy.json` / trading config. Promotion stays gated (`docs/REGIME_GATES_AND_ANALYST_LOOP.md`).

Emit without a closed decide on `REPORT_READY` trials is blocked (`max_review_pending`). Incomplete digs that skip Design→CR→notify are process bugs — use the E2E regimen, not chat close.

---

## Why this exists

Individual trials (Stoch, Kelly) are good **instances**. Without a strategy layer they stay reactive (“something we saw on X”).

You want:

```text
Test strategy (what to learn, in what order)
    → MASTER Type:test tasks (durable queue)
    → auto-pickup → trial cycle (execute / instrument)
    → decide / promote path
    → learnings → strategy update
```

This doc + `data/state/trials/TEST_STRATEGY.json` + `phase6/research/analyst_test_strategy.py` are that layer.

---

## Objectives (ranked)

1. **Regime-conditioned knobs** — for each regime (`bull` / `flat` / `bear` / `transition` / `unknown`), find settings that beat current live policy + USDC hurdle on **real** windows without blowing DD.  
2. **Sizing / risk budget** — fractional Kelly and related (offline → shadow).  
3. **Signal quality** — RSI / Stoch / sentiment gates (instrumentation + offline).  
4. **Methodology alternatives** — rotation vs defensive, rebalance cadence, cash-park rules, etc. (ANALYST-OPT packs).  
5. **Ops reliability** — only when it blocks measurement (SL stamps, data quality).

---

## Workstreams

| ID | Focus | Primary artifacts | Typical `trial_kind` |
|----|--------|-------------------|----------------------|
| `WS-REGIME-KNOBS` | Per-regime cap, util, RSI/sentiment entry | policy/knob_map, scorecard, validation | `offline_analysis` (+ OPT pack) |
| `WS-SIZING` | Kelly / deploy_pct / risk_usd | ledger, shadow eval | `offline_analysis` |
| `WS-SIGNAL` | Stoch, RSI thresholds, sentiment | indicator history, fills | `parallel_instrumentation` or offline |
| `WS-METHODOLOGY` | Strategy families (rotation, park, cadence) | ARCH-4 packs, leaderboard | `offline_analysis` |
| `WS-PROMOTION` | Shadow → audit → operator apply | overlay, live_param_audit | gated ops (not free auto-test) |

Capacity (default): **1** parallel instrumentation + **1** offline analysis (see cycle doc). Strategy **emits** only into free slots.

---

## Strategy board (disk)

**File:** `data/state/trials/TEST_STRATEGY.json`

| Field | Role |
|-------|------|
| `north_star` | One-line objective |
| `capacity` | Caps |
| `workstreams[]` | Status, priority, notes |
| `roadmap[]` | Ordered planned tests (not yet MASTER or already linked) |
| `active_master_ids[]` | Currently in MASTER cycle |
| `completed[]` | Closed with decision enums |
| `emission_rules` | Max emit per run, require handoff template |

**Roadmap item shape:**

```json
{
  "plan_id": "PLAN-FLAT-CAP-SWEEP-001",
  "title": "Flat regime rebalance_cap / RSI grid vs live B",
  "workstream": "WS-REGIME-KNOBS",
  "priority": 10,
  "status": "planned",
  "trial_kind": "offline_analysis",
  "family": "regime_flat_knobs",
  "duration_days": 2,
  "blocked_on": [],
  "depends_on_plans": [],
  "master_id": null,
  "hypothesis": "…",
  "success_metric": "higher growth or lower DD vs live flat B on real window; n gate",
  "handoff_stub": "handoffs/analyst/templates/…",
  "regime_focus": ["flat"],
  "auto_pickup": true
}
```

Statuses: `planned` → `emitted` (on MASTER) → `running` → `done` | `dropped` | `blocked`.

---

## Emission → MASTER → pickup

```text
analyst_test_strategy.py plan     # refresh priorities from state/learnings (optional)
analyst_test_strategy.py emit     # write next N roadmap items onto MASTER as Type:test
master_test_pickup.py scan/launch # existing auto-pickup
trial cycle → decide → strategy mark done + next emit
```

**Emit rules (hard):**

1. Never emit if offline or instrumentation slots full (counts RUNNING trials + MASTER RUNNING tests).  
2. Max **1** new MASTER test per emit run (default).  
3. Skip if `master_id` already exists on MASTER.  
4. Every emitted section includes full **Type: test** contract (`ANALYST_TEST_CYCLE.md` initiation path).  
5. Hypothesis + success metric + non-goals (no live write) required.  
6. Regime tests must name **regime_focus** and compare to **current live policy fingerprint**.

---

## Regime test matrix (default backlog seed)

For each regime, strategy aims at a **thin** evidence pack (not combinatorial explosion):

| Regime | Question | First test family |
|--------|----------|-------------------|
| **flat** | Is $75 cap + RSI≤55 optimal vs tighter/looser? | `regime_flat_knobs` grid offline |
| **bull** | Util / cap / RSI 70 — leave edge on table? | `regime_bull_knobs` |
| **bear** | Park correct vs small tactical deploys? | `regime_bear_park_vs_tactical` |
| **transition** | Cap 50 park vs faster flip? | `regime_transition` |
| **cross** | Detector lag / mis-label cost | `regime_detector_sensitivity` |

Methodologies (WS-METHODOLOGY) pull from ANALYST-OPT scenario packs + scorecard winners — strategy **schedules** which pack runs next; harness stays `run_analyst_opt_*` / Path B.

---

## Feedback into strategy

On `trial_cycle.py decide`:

1. Trial → CLOSED + MASTER DONE (existing).  
2. Append `completed[]` with decision enum + report path.  
3. If `propose_scoped_experiment` / promote path → add roadmap follow-on (shadow) or promotion checklist item.  
4. Weekly strategy cron re-ranks roadmap from: open DD, current regime dwell time, learnings, leaderboard deltas.

---

## Crons / skills

| Job | Role |
|-----|------|
| `analyst-test-strategy-weekly` | Skill: review board, re-rank, emit ≤1 if slot free |
| `master-test-pickup*` | Unchanged — executes emitted MASTER tests |

Skill: `analyst-test-strategy`

---

## Relation to existing loops

| Loop | Strategy role |
|------|----------------|
| REGIME-CASH live gates | **Consumer of winners only** after promotion |
| ANALYST-OPT weekly / scorecard | **Methodology + regime pack engine** invoked by roadmap items |
| Trial cycle + MASTER pickup | **Execution factory** for strategy-emitted tests |
| `analyst_proposed_backlog.json` | Downstream proposals; strategy may promote high-priority backlog rows into roadmap |

---

## CLI

```bash
cd /home/brad/projects/crypto-trading-bot
python3 phase6/research/analyst_test_strategy.py status
python3 phase6/research/analyst_test_strategy.py seed     # idempotent default roadmap
python3 phase6/research/analyst_test_strategy.py emit --dry-run
python3 phase6/research/analyst_test_strategy.py emit
python3 phase6/research/analyst_test_strategy.py sync-active   # mark roadmap from MASTER/trials
```
