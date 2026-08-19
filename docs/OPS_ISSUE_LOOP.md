# Ops Issue Loop

**Purpose:** Once an ops problem is identified (triage, GH issue, audit), it must
**enter a single pipeline**: triage → auto-assign → Kanban work → verify → close.

**Primary work engine:** Hermes Kanban board `crypto-bot-project`  
**Durable IDs:** `data/state/ops_task_registry.jsonl` + GitHub `brad-sl/operations`  
**Glue script:** `scripts/phase6/ops_issue_loop.py`

Related: `docs/OPS_TRIAGE_TASK_WORKFLOW.md` (lifecycle layers), skill `phase6-ops-triage` (discovery only).

---

## Loop diagram

```
Discover (ops_triage_discover no_agent / ops_engineer / human)
    │
    ▼
Promote GH issue + registry row   (ops_triage_tasks.py promote)
    │
    ▼
ops_issue_loop.py run   ◄── cron 3×/day (no_agent)
    ├─ sync      open GH Trading Bot / P6-OPS → registry
    ├─ route     assignee profile + priority + skills (+ gh assign @me)
    ├─ ensure-kanban   idempotent card ops-issue-{N} on crypto-bot-project
    │                  default: NO --goal (Phase1 cost); --goal only rank≤1 max 12
    ├─ dispatch  hermes kanban dispatch (gateway workers)
    └─ reconcile kanban done | GH closed → registry done + close peer
    │
    ▼
Kanban worker (crypto-engineer profile, single-shot unless --goal)
    fix → isolation/verify → MASTER + close GH + registry close
```

---

## Commands

```bash
cd /home/brad/projects/crypto-trading-bot

# Full tick (what cron runs)
.venv/bin/python3 scripts/phase6/ops_issue_loop.py run --gh-assign --dispatch

# Pieces
.venv/bin/python3 scripts/phase6/ops_issue_loop.py sync
.venv/bin/python3 scripts/phase6/ops_issue_loop.py route --gh-assign
.venv/bin/python3 scripts/phase6/ops_issue_loop.py ensure-kanban
.venv/bin/python3 scripts/phase6/ops_issue_loop.py reconcile
.venv/bin/python3 scripts/phase6/ops_issue_loop.py status

# Board
hermes kanban --board crypto-bot-project list
```

State dumps:

| File | Role |
|------|------|
| `data/state/ops_issue_loop_latest.json` | Open queue snapshot |
| `data/state/ops_issue_loop_history.jsonl` | Tick history |
| `data/state/ops_task_registry.jsonl` | Durable task rows |

---

## Routing rules (auto-assign)

| Pattern | Profile | Priority rank |
|---------|---------|---------------|
| missing SL / stop_loss / protective | `crypto-engineer` | 1 |
| deferred slot / AttributeError / missed rebalance | `crypto-engineer` | 1 |
| runner / dashboard PnL / price stale | `crypto-engineer` | 2 |
| analyst OPT / regime validation / param audit | `crypto-engineer` | 2 |
| sentiment / cron / X API | `crypto-engineer` | 3 |
| docs / MASTER / boundary | `crypto-orchestrator` | 4 |
| default | `crypto-engineer` | 3 |

Kanban cards use `--idempotency-key ops-issue-{github_number}` so re-runs do not duplicate.

### Goal mode (Phase1 cost 2026-07-20)

**Default: off.** Expensive 25-turn goal loops removed.

| Flag | Effect |
|------|--------|
| (none) | No `--goal` on create |
| `--goal` | Goal only if `priority_rank <= 1`, max **12** turns |
| `--force-goal` | Goal any rank (avoid) |
| `--goal-max-turns N` | Cap when goal on |

Cron `run_ops_issue_loop.sh` does **not** pass `--goal`.

---

## What stays human / discovery-only

- **Morning triage cron** still **discovers** only (no auto-fix in that skill).
- After promote/GH create, **this loop** owns assignment + Kanban entry.
- Strategy / ANALYST-OPT promotions stay on the analyst path — not this loop.

---

## Cron

Hermes job `ops-issue-loop` (script `phase6/run_ops_issue_loop.sh`, `no_agent`):

- Schedule: `15 7,13,19 * * *` America/Los_Angeles-ish wall via host cron TZ  
- Deliver: `local` (silent unless stdout error)

Sync hermes copy after edits:

```bash
mkdir -p ~/.hermes/scripts/phase6
cp scripts/phase6/run_ops_issue_loop.sh ~/.hermes/scripts/phase6/
cp scripts/phase6/ops_issue_loop.py ~/.hermes/scripts/phase6/  # optional; script uses project path
```

---

## Success criteria for a ticket in the loop

1. Registry row `status=in_progress` with `kanban_task_id`
2. GH issue assigned + comment linking Kanban id
3. Worker completes with real verification
4. `reconcile` or worker close → registry `done` + GH closed
5. MASTER one-liner DONE

---

## Document control

| Version | Date | Note |
|---------|------|------|
| 1.0 | 2026-07-20 | Initial Kanban-centered issue loop |
