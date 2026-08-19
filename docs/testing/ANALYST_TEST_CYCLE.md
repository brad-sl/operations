# Analyst / Platform Test Cycle

**Status:** Canonical (v2 — loop-engineered)  
**Date:** 2026-07-21 (v2 same day); **E2E regimen:** 2026-08-17  
**Strategy layer:** `docs/testing/ANALYST_TEST_STRATEGY.md` + `analyst_test_strategy.py` (what to test → MASTER emit → pickup).  
**Adoption-grade process (design → CR → notify):** **`docs/testing/TEST_REGIMEN_E2E.md`** — required for any trial that can drive promote/drop.

**Why v1 existed:** StochRSI sat as “monitor someday” + a reminder cron — never a closed test.  
**Why v2:** v1 was a solid **product lifecycle checklist** but incomplete as a **loop** (weak exit wiring, wall-of-prompt crons, no auto-kill, no skeptical review door, no registry).  
**Why E2E regimen (2026-08-17):** Offline digs (FIB/SR) reached `REPORT_READY` with thin JSON, no frozen success bar, no decide/packet/notify — blocking strategy emit without an adoption decision. States alone ≠ thorough testing.

**Rule:** No experiment is “launched” until Design→Launch artifacts exist **and** monitor + final exit signals are scheduled.

---

## Loop map (where this cycle lives)

| Layer | How this cycle uses it | Exit signal |
|-------|------------------------|-------------|
| **Execution** | Refresher, health script, report script, isolation tests | Process exit codes, cache fields, report files |
| **Task (Ralph-ish)** | Mid/final: same skill + protocol each time; fresh agent context | `reports/*_{MID,FINAL}_*` + recommendation enum |
| **Product** | Trial lifecycle on disk + MASTER + backlog unblock | `status=CLOSED` + dependents unblocked |
| **System** | Shared cycle doc, `trial_cycle` helpers, hermes wrapper pattern | Reuse on next trial without reinventing |
| **Oversight** | Brad decision on promote/drop/extend; live config never auto | `decision` on trial JSON + MASTER |

```text
Primary loop: product (trial lifecycle) + execution (health) + task (scheduled reports)
Exit signal: final report + human decision → CLOSED (not agent "done")
Human at: oversight (decision); boundaries on live config; sample mid/final read
Not building: MapReduce-only fan-out; Blind Loop (you re-assign daily); Nodding Loop (self-grade promote)
```

**Trading outcome note:** Instrumentation trials (this cycle) are *not* the ANALYST-OPT scenario harness. When the recommendation is a knob experiment, hand off to **system harness** (scenario pack → leaderboard → shadow) before live.

---

## Anti-patterns we refuse (five-move)

| Anti-pattern | Symptom we hit before | Guard in this cycle |
|--------------|----------------------|---------------------|
| **Blind Loop** | Daily “what should we do about Stoch?” | Discovery is scheduled milestones + health; work is pre-registered |
| **Nodding Loop** | Report agent grades its own promote | Final → `REVIEW_PENDING` only; optional second-pass evaluator; Brad decides |
| **Tangled Loop** | Parallel half-finished experiments | One RUNNING trial per signal family; `blocked_on` for dependents |
| **Amnesiac Loop** | Context compaction loses trial | Disk: trial JSON + reports + MASTER (not chat memory) |
| **Manual Loop** | Forgot to close for two weeks | Final cron + `stale_open` detector in health/registry |
| **Wall-of-prompt cron** | 40-line prompt drifts | Skill `analyst-trial-report` + thin cron prompt |
| **Stale hermes script** | Cron ran 6-pair no-Stoch fork | Thin wrapper → absolute project script; health checks `stoch_k` |

---

## State machine (only these transitions)

```
REGISTERED → INSTRUMENTED → RUNNING → REPORT_READY → REVIEW_PENDING → CLOSED
                │                │
                │                ├→ DEGRADED (health fails; still collecting if soft)
                │                └→ KILLED (kill criteria / Brad abort)
                └→ KILLED
CLOSED and KILLED are terminal.
extend_trial decision: CLOSED(reason=extend) → new trial ID (never reopen same ID as RUNNING forever).
```

| Status | Meaning |
|--------|---------|
| `REGISTERED` | Protocol + trial JSON exist |
| `INSTRUMENTED` | Isolation + live sample green |
| `RUNNING` | Baseline + crons live; collecting |
| `DEGRADED` | Health failing; clock still runs; alerts on |
| `REPORT_READY` | Final report written |
| `REVIEW_PENDING` | Awaiting Brad `decision` |
| `CLOSED` | Decision recorded; crons paused; unblocks applied |
| `KILLED` | Abort; document why; unblocks only if explicit |

Helpers: `phase6/research/trial_cycle.py` (`load`, `transition`, `record_decision`, `reindex`).

---

## The cycle (mandatory phases)

| # | Phase | Done when | Artifact | Loop move |
|---|--------|-----------|----------|-----------|
| 1 | **Design** | Hypothesis, non-goals, sources, success/fail, duration, kill, sample gates | `docs/testing/trials/<ID>_PROTOCOL.md` | Spec (task) |
| 2 | **Register** | JSON + INDEX row | `data/state/trials/<ID>.json` + `INDEX.json` | Persistence |
| 3 | **Instrument** | Isolation PASS + live sample (e.g. stoch on cache) | test log / launch_notes | Execution |
| 4 | **Launch** | Baseline report; health+mid+final scheduled; MASTER LAUNCHED; status RUNNING | `reports/*_BASELINE_*`, cron_ids | Scheduling |
| 5 | **Monitor** | Health green **or** DEGRADED with alert; consecutive-fail → KILLED per protocol | `health_log[]` on trial JSON | Discovery (Read/Judge/Stop) |
| 6 | **Mid-report** | Skillized analysis ~50% | `reports/*_MID_*` | Task + verify |
| 7 | **Final report** | Full analysis + enum → REPORT_READY **only via** `finalize-report` completeness gate | `reports/*_FINAL_*` + trial `outcome` | Task |
| 8 | **Review** | Skeptical pass (optional) + Brad decision → REVIEW_PENDING then decided | `decision` + packet + inbox | Verification + oversight |
| 9 | **Close** | CLOSED; pause trial crons; MASTER; unblock; **follow_on** explicit; notify | MASTER DONE + `docs/testing/decisions/` | Product exit |

**Recommendation enum (final report proposes; human confirms):**  
`continue_observe_only` | `extend_trial` | `propose_scoped_*_experiment` | `drop` | `promote_blend` | `promote_primary` | `abort`

**CR mapping:** promote_*/propose_scoped_* = **ACCEPT CR** · drop/abort = **REJECT** · observe/extend = **NO_CR** (see TEST_REGIMEN_E2E).

**Close command:**  
`python3 phase6/research/trial_cycle.py decide <ID> <enum> --note '…' --follow-on none|extend|scoped_shadow|promotion_queue`

---

## Five moves (how each turn works)

1. **Discovery** — Health script *reads* cache/history/trades coverage; *judges* OK vs issues; *stops* (no live config edits). Empty stdout if OK.
2. **Handoff** — Mid/final load skill `analyst-trial-report` (not inline novel logic). Heavy analysis stays in Python report script.
3. **Verification** — Isolation at instrument; health continuous; final does **not** auto-CLOSED; optional evaluator cron/skill assumes report is over-confident.
4. **Persistence** — Trial JSON, reports/, MASTER, INDEX.json. Never “we’ll remember in chat.”
5. **Scheduling** — Hermes cron with caps: mid/final once; health daily (or hourly if flaky); stale detector if `final_at` passed and status still RUNNING.

**Caps (declare on every trial):**
- Duration + mid/final timestamps  
- Max consecutive health failures before `KILLED` (default **3** daily fails ≈ kill after alert streak)  
- No live promote without Brad  
- Max 1 RUNNING trial per family (`stoch_rsi`, `kelly_sizing`, …)

---

## Hard rules

- Real data only (no placeholder prices/trades).
- Live config / allocator changes require Brad + gates — reports may only *propose*.
- `no_agent` health: **empty stdout when OK**.
- Hermes `script:` resolves under `~/.hermes/scripts/` — prefer **wrapper → project absolute path**, not full script copies that drift.
- MASTER is durable human record; Kanban optional.
- **Close is a function call** (`trial_cycle.record_decision`) not a vibe.

---

## Checklist template (copy into protocol)

```
[ ] Hypothesis + non-goals
[ ] Data sources listed (paths)
[ ] Sample-size gates for recommendation confidence
[ ] Isolation test path + command
[ ] Baseline command
[ ] Health cron (schedule + job id) + consecutive-fail kill N
[ ] Mid cron / date (skill-backed)
[ ] Final cron / date (skill-backed)
[ ] Stale detector: final_at + 48h still open → alert
[ ] MASTER block ID
[ ] Dependent tasks (unblocks)
[ ] Kill criteria (automated + Brad abort)
[ ] Decision inbox path
[ ] Close-out owner
[ ] Caps: duration, max parallel, no auto-merge/promote
```

---

## Minimal tooling

| Tool | Role |
|------|------|
| `docs/testing/ANALYST_TEST_CYCLE.md` | This spec |
| `data/state/trials/<ID>.json` | Lifecycle state |
| `data/state/trials/INDEX.json` | All trials registry |
| `phase6/research/trial_cycle.py` | Transitions, decision, reindex, stale scan |
| `phase6/research/run_*_trial_health.py` | Monitor (+ degrade/kill hooks) |
| `phase6/research/run_*_trial_report.py` | Baseline/mid/final |
| `docs/testing/inbox/` | Uncertain items for Brad |
| Hermes skill `analyst-trial-report` | Thin scheduled report turn |
| `docs/MASTER_TASK_TRACKING.md` | Human-visible status |

---

## Launch gate (definition of launched)

All must be true:

1. Protocol on disk  
2. Trial JSON status `RUNNING` with `start_at`, `mid_at`, `final_at`, `cron_ids`  
3. INDEX.json lists trial  
4. Baseline report path set  
5. Health job enabled (`hermes cron list`)  
6. Final job enabled with `next_run_at`  
7. MASTER shows LAUNCHED/RUNNING  
8. Instrumentation sample green within last hour at launch  

If any missing → **not launched** (still designing).

---

## First production use

**Trial:** `STOCH-RSI-PARALLEL-20260721`  
**Protocol:** `docs/testing/trials/STOCH-RSI-PARALLEL-20260721_PROTOCOL.md`  
**v2 upgrades applied to this trial:** registry INDEX, health consecutive-fail → DEGRADED/KILLED, skillized mid/final prompts, decision inbox, trial_cycle helpers.

---

## Initiation path (MASTER auto-pickup)

**Goal:** Marking a MASTER task as a test is enough for the loop to notice it — no chat kickoff required once fields are valid.

### MASTER contract (required on the task section)

```markdown
**Type:** test
**Status:** QUEUED
**auto_pickup:** true
**blocked_on:** `OTHER-ID`    # or none
**trial_kind:** offline_analysis   # or parallel_instrumentation
**family:** kelly_sizing
**duration_days:** 14
**Handoff:** `handoffs/analyst/Handoff_....md`
**Role:** crypto-analyst
```

- Only `**Type:** test` (or trial/experiment) is eligible — plain tasks are ignored.  
- `auto_pickup: false` = tracked as test but human-launched (Stoch after manual launch).  
- `blocked_on` resolves when blocker MASTER status ∈ DONE/CLOSED/… **or** linked trial `CLOSED`.

### Automatic wiring

| Job | Schedule | Role |
|-----|----------|------|
| `master-test-pickup-scan` | every 6h | `no_agent` → `master_test_pickup.py scan` (silent if nothing launchable) |
| `master-test-pickup` | daily 09:30 PT | skill `analyst-test-pickup` → `launch` (cap 1) |

### Launch behavior

1. Scan MASTER → `data/state/trials/PICKUP_QUEUE.json`  
2. If slot free (`max_running_auto=1` for `source=master_auto_pickup`) and task READY:  
   - register trial JSON  
   - scaffold protocol if missing  
   - schedule crons (`offline_analysis` → one-shot `analyst-test-execute`; `parallel_instrumentation` → health/mid/final)  
   - patch MASTER **Status** → RUNNING  
   - inbox `PICKED_UP_*.md`  
3. Execute skill runs handoff tiers → REPORT_READY → Brad `trial_cycle.py decide`

### CLI

```bash
cd /home/brad/projects/crypto-trading-bot
python3 phase6/research/master_test_pickup.py scan
python3 phase6/research/master_test_pickup.py launch --dry-run
python3 phase6/research/master_test_pickup.py launch
```

