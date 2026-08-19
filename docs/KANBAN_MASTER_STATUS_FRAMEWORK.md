# Kanban ↔ MASTER status framework (crypto-bot-project)

**Date:** 2026-08-18  
**Board:** `crypto-bot-project`  
**Rule:** MASTER remains the durable source of truth. Kanban is the **scan surface + dispatcher**. Every open scale/hygiene card must have a Kanban row you can filter.

## Why this exists
MASTER is dense. Hermes Kanban has **fixed columns** (no custom “Shadow” column). We map product states onto those columns and use **title tags** so you can scan like a real board.

## Column map (Hermes native)

Hermes has **fixed** columns — no custom “Shadow/Testing” column. We encode product state with **title tags** + the closest Hermes status.

| You want | Hermes status | How we set it | Agent dispatch? |
|----------|---------------|---------------|-----------------|
| **Parked / backlog** | `scheduled` + `[PARKED]` | create → force `schedule` · **no assignee** | No |
| **Staged next** | `scheduled` + `[STAGED]` | same · staff later via assign + promote | No until you staff |
| **Watch / soak / Testing** | `scheduled` + `[WATCH]` | same (measure-only gate) | No |
| **Shadow / offline CF** | `scheduled` + `[SHADOW]` | same | No |
| **Gated (Brad OK)** | `scheduled` + `[GATED]` / `[LIVE-OFF]` | same | No |
| **Ready to run** | `ready` | assign profile + promote from scheduled | **Yes** |
| **In process** | `running` | worker claimed | Yes |
| **Done** | `done` | complete + MASTER DONE same day | — |

### Critical safety rules
1. **Do not use `triage` for backlog tracking** — with `kanban.auto_decompose: true` (Hermes default), triage is auto-fanned into assigned child graphs.
2. **This profile sets `kanban.auto_decompose: false`** so bulk backlog ingest cannot spawn workers. Staff intentionally with BoN / Brad go.
3. **Unassigned `ready` is dangerous** — dispatcher can claim. Parked work stays **`scheduled`**, never bare ready.
4. **`blocked` alone is not enough for bulk park** — promote/watchers can thrash; prefer **`scheduled` + tags**.

### Title tags (filter these in the UI / CLI)

```
[PARKED]  [STAGED]  [WATCH]  [SHADOW]  [GATED]  [READY]  [LIVE-OFF]
```

Example titles:
- `[STAGED] GAP-03 Cap scope matrix`
- `[WATCH] GAP-05b 14d post-SL enforce`
- `[PARKED] GAP-08 Promo firedrill`
- `[SHADOW] GAP-10 Basket CF long-tape`
- `[GATED] Profit-exit live gates`

### Idempotency
Every ingested card uses `--idempotency-key master:<TASK_ID>` so re-sync will not duplicate.

## Scan commands

```bash
# Open board (non-done)
hermes kanban --board crypto-bot-project list | rg -v '✓|done'

# By tag
hermes kanban --board crypto-bot-project list | rg '\[(STAGED|WATCH|PARKED|SHADOW|GATED)\]'

# Stats
hermes kanban --board crypto-bot-project stats
```

## Lifecycle (single item)

1. **MASTER** row exists with bars / must-nots  
2. **Kanban** card created (parked/staged/watch — not assigned)  
3. When staffing: assign `crypto-engineer` or `crypto-analyst` → `ready` → worker  
4. On finish: `kanban complete` **and** MASTER status DONE + decide packet path  
5. Watches stay `[WATCH]` blocked until day-N re-score → then complete or restage  

## What not to do
- Do **not** assign parked cards (workers will thrash)  
- Do **not** treat Kanban alone as SSOT if MASTER conflicts — fix MASTER first  
- Do **not** invent custom columns in Hermes — tags + blocked/triage are the framework  
- Live order path never auto-promotes from a parked card  

## Sync helper
`scripts/phase6/sync_master_scale_to_kanban.py` — idempotent upsert of the scale/hygiene open set.

## Related
- Board: `crypto-bot-project`  
- MASTER: `docs/MASTER_TASK_TRACKING.md`  
- BoN staff-next: skill `best-of-n-verify` before multi-option staffing  
