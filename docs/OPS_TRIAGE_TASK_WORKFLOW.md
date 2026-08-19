# Ops Triage → Task Workflow (Phase 6)

**Purpose:** Keep ops findings **visible**, **owned**, and **resolved** — not only a Telegram ping.  
**Owner:** Brad + Hermes agent on “proceed.”  
**Repo:** `brad-sl/operations` (crypto-trading-bot path).

---

## Layers (single source of truth per concern)

| Layer | Role | Path / tool |
|-------|------|-------------|
| **Daily snapshot** | What we saw today (≤3 findings) | `data/state/ops_triage.md` |
| **Durable queue** | Open ops work items with IDs | `data/state/ops_task_registry.jsonl` |
| **Issue loop** | Auto-assign + Kanban entry + reconcile | `scripts/phase6/ops_issue_loop.py` — **docs/OPS_ISSUE_LOOP.md** |
| **Kanban** | Execution engine (workers fix) | board `crypto-bot-project` (`ops-issue-{N}` idempotency) |
| **MASTER** | Human/agent task contract (scope, success criteria) | `docs/MASTER_TASK_TRACKING.md` (`P6-OPS-*`) |
| **GitHub Issues** | External visibility, comments, close-on-fix | `gh issue` — label `Trading Bot` + `bug`/`enhancement` |
| **Telegram** | Alert only — not the task system | Cron `phase6-ops-triage-daily` |

Analyst backlog (`analyst_proposed_backlog.json`) is **strategy**, not ops — do not merge unless live-blocking.

---

## Lifecycle

```
Discover (cron/skill phase6-ops-triage — discovery only)
  → ops_triage.md (table: priority, status)
  → Promote (medium/high, new actionable)
       → append ops_task_registry.jsonl (status: open)
       → gh issue create (if not already linked)
       → MASTER one-liner + full P6-OPS block on user/agent “turn into tasks”
  → Issue loop (cron ops-issue-loop, no_agent)
       → sync GH open P6-OPS / Trading Bot → registry
       → route assignee profile + priority (+ gh assign @me)
       → ensure Kanban card (crypto-engineer, --goal) status in_progress
       → dispatch workers
  → Work (Kanban worker / agent, isolation tests)
  → Resolve
       → close GitHub issue + kanban complete
       → loop reconcile OR ops_triage_tasks.py close
       → registry status: done + closed date
       → ops_triage.md row: done
       → MASTER: DONE + verification note
```

**Status values**

| Status | Meaning |
|--------|---------|
| `open` | Acknowledged, not fixed |
| `in_progress` | Someone actively working (optional) |
| `done` | Verified fixed or accepted risk |
| `wontfix` | Documented deferral |

---

## Promotion rules (continual improvement)

After writing `ops_triage.md`, for each row with **priority high or medium** and **status open**:

1. **Dedupe:** `python3 scripts/phase6/ops_triage_tasks.py list --open` — skip if same `finding` slug already open in registry.
2. **Register:** `python3 scripts/phase6/ops_triage_tasks.py promote --finding "..." --priority medium --evidence path1,path2`
   - Assigns `P6-OPS-YYYYMMDD-NNN`
   - Creates GitHub issue unless `--no-github`
   - Appends registry line
3. **MASTER:** On first promote or user request, add **P6-OPS-*** block at top of `MASTER_TASK_TRACKING.md` with success criteria and issue URL.
4. **Telegram:** Include registry IDs + issue links in triage summary (≤1500 chars).

**High** findings: promote **same day** without waiting for user.  
**Medium:** promote same day if capital/SL/runner safety; else within 24h.

---

## Resolution rules

When closing an ops task:

1. Verification artifact (test name, log snippet, or “accepted risk” note in issue).
2. `gh issue close <n> --comment "..."`
3. `python3 scripts/phase6/ops_triage_tasks.py close --id P6-OPS-...`
4. Update `ops_triage.md` matching row → `done`
5. MASTER entry → **DONE** with date

---

## GitHub Issues convention

- **Title:** `P6-OPS: <short symptom>`
- **Labels:** `Trading Bot` + `bug` (or `enhancement` for process/docs)
- **Body:** Source (triage date), symptom, evidence paths, expected, MASTER ref, checklist
- **Do not** auto-close from cron — only agent/user after verification

---

## Hermes skill

Skill `phase6-ops-triage` Procedure includes **Promote** step (see skill patch). Cron does **not** edit MASTER automatically unless configured — registry + GH issue is the default autonomous step; MASTER full blocks follow user “proceed” or high-severity auto-promote policy above.

---

## Current open ops tasks (2026-07-11)

| ID | Issue | MASTER |
|----|-------|--------|
| P6-OPS-20260711-001 | [#10](https://github.com/brad-sl/operations/issues/10) | P6-OPS-CAPITAL-COOLDOWN-PERSIST |
| P6-OPS-20260711-002 | [#11](https://github.com/brad-sl/operations/issues/11) | P6-OPS-ARB-SL-ATTACH |

---

## Revision history

| Date | Change |
|------|--------|
| 2026-07-11 | Initial workflow; registry + GH #10/#11; MASTER tasks |