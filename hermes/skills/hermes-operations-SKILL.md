---
name: hermes-operations
description: Best practices for working with Hermes CLI, cron jobs, gateway, and persistent agent workflows. Captures execution preferences and common pitfalls.
version: 1.0.0
---

# Hermes Operations

## Execution Preference
**Strong user preference:** When possible, run commands directly using the `terminal` tool instead of telling the user to copy-paste and run them. Only give the user commands when absolutely required (e.g., long-running services like `hermes gateway start`).

## Cron Job Creation
Hermes cron creation is finicky with argument parsing. Preferred pattern:

1. Try the clean one-liner first.
2. If argument parsing fails, fall back to writing a YAML file in `~/.hermes/cron/<name>.yaml`.
3. The gateway must be running (`hermes gateway start`) for scheduled jobs to execute.

## Using the `cronjob` Agent Tool (cronjob.create)
When using the agent's `cronjob` tool (distinct from raw `hermes cron` CLI):

- **schedule is MANDATORY for action="create"**. Always pass it explicitly as a named parameter:
  - RSI refresher: schedule="*/15 * * * *"
  - Sentiment: schedule="*/30 * * * *"
- Omitting `schedule` produces the exact error "schedule is required for create" and triggers repeated-identical-call loops that hit max-iterations.
- Scripts must be placed in `~/.hermes/scripts/` (the tool resolves relative paths from there). Use `cp <project-script> ~/.hermes/scripts/` before create.
- For env-sensitive scripts (NumPy on constrained CPUs, sentiment with Apify): create a thin `.sh` wrapper in `~/.hermes/scripts/` that does `export OPENBLAS_CORETYPE=GENERIC; cd /project; python3 run_....py` and point the cron at the `.sh`.
- After create, always verify with `hermes cron list` (via terminal tool) — the list is the source of truth.
- Long-running external calls (Apify Reddit/X sentiment) can timeout in interactive verification; the cron itself will execute the script in its own context.

## Common Pitfalls
- Using `--prompt` or `--schedule` flags with `hermes cron create` often fails due to CLI parsing.
- Dropping YAML files in `~/.hermes/cron/` does not always auto-register the job.
- The gateway must be running for any cron work to fire.
- **cronjob tool loop trap**: calling create without `schedule` 50+ times in a row (identical args) triggers the exact tool-loop warning seen in max-iteration sessions. Always include the parameter on the first attempt.

## Monitoring Setup
When setting up persistent monitors (e.g. `crypto-monitor`), always:
- Create the profile in `~/.hermes/profiles/`
- Write a clean `~/.hermes/cron/<name>.yaml` with prompt and schedule
- Test manually first before relying on the schedule

## Custom Dashboards as Systemd Services
When turning a custom Python HTTP dashboard (e.g. `serve_dashboard.py`) into a reliable always-on service:

1. Create a systemd unit at `/etc/systemd/system/<name>.service` with:
   - `WorkingDirectory` set to the exact folder containing the script
   - `ExecStart` using the full path to the interpreter + script + args
   - `Restart=always` + `RestartSec=5`
   - `User` set to the non-root user

2. After `daemon-reload`, always `enable` + `start`.

3. Common failure: "Address already in use" → kill existing process on the port first (`fuser -k <port>/tcp`).

4. Firewall: `sudo ufw allow <port>/tcp` is almost always required for remote access.

5. Store the unit file in the project under `references/<dashboard-name>.service` for reproducibility.

This pattern prevents repeated "connection refused" issues across reboots and disconnects.

## Telegram Integration
Always store bot token and chat ID in the project's `.env` file. Use `load_dotenv()` with explicit path when running from outside the project directory.

## Dedicated Monitoring Agent Profiles (crypto-monitor pattern)
For long-running trading infrastructure, create isolated profiles (e.g. `crypto-monitor`) rather than overloading the default agent:

- Profile lives at `~/.hermes/profiles/crypto-monitor/`
- `profile.yaml` declares: provider/model (prefer cheaper OpenRouter model), toolsets (`file`, `terminal`, `cron`, `skills`), Telegram config, schedule, and the full monitoring prompt.
- `SOUL.md` is custom-written for the role: "Crypto Monitor Agent" with explicit mandate for process inspection, safe restarts, evidence-based escalation to primary agent, production-safety rules, and structured Telegram + Kanban handoffs.
- Cron definition at `~/.hermes/cron/crypto-monitor.yaml` (or inline in profile.yaml) uses the profile name and a prompt that encodes:
  1. `ps aux` inspection for trading/paper/bot/phase*/orchestrator processes.
  2. Log scanning for ERROR/CRASH patterns.
  3. Safe restart attempts (background python or service commands; never live trading without evidence).
  4. Escalation path: detailed evidence bundle → Telegram to main chat + Kanban task creation with "Must Do/Must Not Do".
  5. Always produce concise structured report (Status / Processes / Actions / Escalations).

This gives a dedicated, scheduled "free AI" monitor that keeps scripts alive and surfaces real problems without polluting the primary agent's context. Update both the profile prompt and the cron yaml in lockstep when evolving the behavior. See also `trading-bot-operations` for related trading-specific monitoring patterns.

## Hermes Web Dashboard (Control Panel)
To expose the Hermes Agent web dashboard to remote machines (e.g. Windows PC on the same LAN):

**Correct command:**
```bash
hermes dashboard --host 0.0.0.0 --insecure
```

- `--host 0.0.0.0` binds to all interfaces
- `--insecure` is required when not binding to localhost (acknowledges network exposure of API keys)

**Default local behavior** (`hermes dashboard`) only binds to 127.0.0.1.

**Note:** The legacy `hermes gateway run --host ... --port ...` syntax is no longer supported. Use the dedicated `dashboard` subcommand instead.

Access from remote Windows machine via:
`http://<linux-ip>:9119`

## Git-Enabled Operationalization and Resilience
When hardening Hermes on legacy hardware or building migration/resilience, treat git (operations repo) as the durable source of truth for Hermes state.

**Core Pattern (from Phase 1 baseline + plan):**
1. Before major operational work (long audits, phase kickoffs, migration planning): emit a recovery-packet (see recovery-packet skill).
2. Perform baseline inventory:
   - Use direct `hermes cron list` (source of truth), `hermes profile list` (or filesystem ls on ~/.hermes/profiles/), targeted cat of profile.yaml/SOUL.md (sanitize secrets).
   - Inspect processes (`ps aux` for gateways, runners, dashboards), hardware (uptime, df, journalctl), git status/log/ls-files for Hermes references.
3. Export sanitized artifacts to a git-tracked `hermes-state/` (or `hermes-state/` under project):
   - Subdirs: cron/, profiles/, skills/, hardware/, with README.
   - Include: full cron list output, key profile yamls, skills inventory (all + relevant like hermes-operations/ops-engineer), hardware snapshot, sanitized config.
   - Add: recovery packet, verification script (isolation test that re-runs inspections and diffs vs exports), concise PHASE_GOALS.md or equivalent.
4. Update primary record (MASTER_TASK_TRACKING.md) with detailed evidence block using ops-engineer style: real snippets, exact verify commands (`hermes cron list`, `python3 hermes-state/verify_baseline.py`, `ps aux | grep ...`), impact, suggested next.
5. Commit the hermes-state/ artifacts + updates.

**Git Mirroring & Sync (Phase 2 core):**
- Create `scripts/hermes/sync-hermes-state.sh` (selective rsync of non-secret parts + git add/commit/push).
- Run via Hermes cron (daily or on profile/cron change).
- Bidirectional: git pull + apply on recovery/start; push on changes.
- Use project-specific `.hermes/resume-packets/` (per recovery-packet skill) and git worktrees for safe experiments.
- Integrate restore into VPS_MIGRATION_PLAYBOOK: `git clone`; `./scripts/hermes/restore-hermes.sh`.

**Monitoring & Ops Integration (Phase 4):**
- Add git health to ops-engineer and crypto-monitor: "repo dirty?", "last sync age", "unpushed Hermes changes".
- Enhance verification loops with git status checks and restore drills.
- Hybrid migration: keep legacy primary; mirror critical profiles/crons to cloud via git clone + Docker; legacy as hot spare.

**Concise Phase Goals Pattern:**
When user requests delineation of phase goals (or at plan creation), produce a compact `PHASE_GOALS.md` (or section) with one high-level goal + 3-5 bullet success criteria per phase. Keep under 1 page. See hermes-state/PHASE_GOALS.md for example from this pattern.

**Verification:**
- Always run the isolation verification script post-export/commit.
- Re-verify with `hermes cron list`, profile yaml checks, `git status`, process counts.
- Append "VERIFIED" notes to MASTER.

See `references/git-operationalization-patterns.md` for condensed session transcripts, example artifacts layout, and full phase goals.

## Loaded Skills Context
This skill should be consulted whenever heavy Hermes CLI interaction or persistent agent setup is required. Consult it for any git-backed resilience, state versioning, or operational baseline work on Hermes.