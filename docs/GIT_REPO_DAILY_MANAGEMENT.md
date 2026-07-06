# Git Repository & Hermes Mirror — Daily Management

**Canonical reference** for how this project uses git, what runs automatically, and what agents must do.

**Related:**
- `docs/GIT_HERMES_OPERATIONALIZATION_PLAN.md` — multi-phase resilience plan
- `hermes/git-workflows/AGENT_GIT_WORKFLOWS.md` — agent branching/commits/handoffs
- `hermes/git-workflows/HANDOFF_GIT_ENHANCED.md` — handoff template
- Skill: `git-repo-management` (load via `skill_view(name='git-repo-management')`)
- Skill: `hermes-operations` — cron + Hermes sync patterns

---

## Repository role

| Layer | Path | Purpose |
|-------|------|---------|
| **Trading code** | `phase6/`, `trading/`, `config/` | Phase 6 live logic; feature branches + conventional commits |
| **Task record** | `docs/MASTER_TASK_TRACKING.md` | Durable status (preferred over Kanban alone) |
| **Hermes mirror** | `hermes/` | Sanitized backup of profiles/cron/skills snapshots from `~/.hermes` |
| **Baseline export** | `hermes-state/` | Phase 1 inventory + `verify_baseline.py` |
| **Ops scripts** | `scripts/hermes/` | sync, restore, health, **daily management** |

**Canonical branch:** `phase-6.1` (merge feature branches here after isolation tests).

**Remote (planned):** `https://github.com/brad-sl/operations.git` — configure when credentials available:

```bash
cd /home/brad/projects/crypto-trading-bot
git remote add origin https://github.com/brad-sl/operations.git   # if missing
git push -u origin phase-6.1
```

---

## Daily automation (Hermes cron)

| Job | Schedule | Script | Mode |
|-----|----------|--------|------|
| **Daily Git + Hermes management** | `30 4 * * *` (04:30 local) | `scripts/hermes/git-daily-management.sh` | `no_agent` → `deliver: local` |
| Daily Kanban backup | `0 3 * * *` | `backup-kanban.sh` | existing |

**What the daily git job does:**
1. `git-health-check.sh` — branch, remote, unpushed, `hermes/` mirror status
2. `sync-hermes-state.sh` — rsync non-secret `~/.hermes` → `hermes/`, commit, push if `origin` exists
3. Optional tail of `hermes-state/verify_baseline.py`

**Logs:** `logs/git-daily-management.log` (gitignored; inspect on host).

**Verify registration (mandatory after changes):**
```bash
hermes cron list
crontab -l | grep -i git || true   # system crontab should NOT duplicate unless intentional
```

**Manual run:**
```bash
cd /home/brad/projects/crypto-trading-bot
./scripts/hermes/git-daily-management.sh --health-only
./scripts/hermes/git-daily-management.sh --dry
./scripts/hermes/git-daily-management.sh
```

---

## Agent obligations (every significant change)

1. **Branch:** `git checkout -b feat/<id>-<kebab-desc>` from `phase-6.1`
2. **Commit:** conventional message + MASTER/Kanban id (e.g. `feat(phase6): P4-04 … (t_975d32ca)`)
3. **Test:** run relevant `phase6/tests/test_isolation_*.py` before merge
4. **MASTER:** append evidence block (commands, exit codes, commit SHA)
5. **Merge:** back to `phase-6.1`; leave user on canonical branch
6. **Handoffs:** include Git apply/verify/rollback section (`HANDOFF_GIT_ENHANCED.md`)

Do **not** commit: `.env`, `*.pem`, `data/state/*.json`, logs, `__pycache__`, live credentials.

---

## Troubleshooting

| Symptom | Action |
|---------|--------|
| Git cron YAML in `~/.hermes/cron/*.yaml` but job not in `hermes cron list` | YAML drop-in does **not** auto-register — use `cronjob` tool or `hermes cron create` with `schedule` |
| `Push failed` in sync | Add/configure `origin`; SSH or HTTPS auth |
| Hourly `git-mirror-sync.yaml` unused | Superseded by **daily** `git-daily-management.sh` (less noise) |
| Dirty repo forever | Expected for runtime files; daily job reports *meaningful* dirty count excluding logs/data/pyc |

---

## Last verified

- **2026-07-06:** Daily Hermes cron registered; scripts and this doc added; `git-repo-management` skill created.