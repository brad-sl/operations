# Task Tracker DB (MASTER → SQLite)

**Date:** 2026-10-21  
**Card:** `t_68534359`  
**DB:** `data/task_tracker.db`  
**CLI:** `python scripts/ops/task_tracker.py`

## Why
`docs/MASTER_TASK_TRACKING.md` (~14k lines / ~840KB) is too large for reliable agent `patch` / full-file rewrite. Status updates burned tokens and failed on exact-match edits.

## Policy
| Layer | Role |
|-------|------|
| **`data/task_tracker.db`** | **Live SSOT** for section status, notes, kanban id links |
| **`docs/MASTER_TASK_TRACKING.md`** | **Historical archive** — do not bulk-rewrite; optional short appends OK |
| **Hermes Kanban** | **Dispatcher** (workers); link ids on section rows |
| **`docs/TASK_TRACKER_OPEN.md`** | Generated human scan surface (`export-md`) |

## Schema (v1)
- `sections` — one row per MASTER `##` heading (id slug, status, body, kanban_ids_json, line range, sha1)
- `events` — audit (import, set_status, note, create)
- `artifacts` — paths mentioned in body
- `meta` — schema_version, last_import_*

## Commands
```bash
cd /home/brad/projects/crypto-trading-bot

python scripts/ops/task_tracker.py init
python scripts/ops/task_tracker.py import-master
python scripts/ops/task_tracker.py stats
python scripts/ops/task_tracker.py list --status not_done --limit 40
python scripts/ops/task_tracker.py search WEEKLY-SUGGESTIONS
python scripts/ops/task_tracker.py get WEEKLY-SUGGESTIONS-20261018
python scripts/ops/task_tracker.py set-status WEEKLY-SUGGESTIONS-20261018 done --note 'CR closed'
python scripts/ops/task_tracker.py add --title 'MY-EPIC-20261021' --status open --body '...'
python scripts/ops/task_tracker.py export-md --status not_done -o docs/TASK_TRACKER_OPEN.md
```

## Agent rules
1. Prefer **`set-status` / `note` / `add`** over editing MASTER for live tracking.
2. Do **not** `write_file` the entire MASTER file.
3. Re-`import-master` after rare large MASTER appends; manual `set-status` is preserved when a prior `set_status` event exists.
4. Kanban create/complete still required for worker dispatch; put `t_*` ids in section body or `--kanban` on add.
5. `data/task_tracker.db` may be gitignored like other runtime DBs — treat as local SSOT; export-md is the shareable snapshot.

## Related
- Framework: `docs/KANBAN_MASTER_STATUS_FRAMEWORK.md`
- Scale sync (separate): `scripts/phase6/sync_master_scale_to_kanban.py`
- Phase6 profile seed: `scripts/ops/seed_phase6_profile_skills.py`
