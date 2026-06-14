# Git-Enabled Hermes Operationalization & Resilience Plan

**Date:** 2026-06-14  
**Context:** Hermes Agent (v0.16.0) running on legacy HP Compaq 8000 Elite SFF PC (Ubuntu 24.04, ~12d uptime, 9.6GB RAM, 146GB disk). Primary work in `https://github.com/brad-sl/operations.git` (branch `phase-6.1`). Heavy use of Hermes for crypto trading bot (Phase 6 live runner, delegation, crons, profiles like crypto-orchestrator/crypto-engineer).  
**Goals:** 
- Leverage git repo strengths (versioning, remote backup, workflows, restores, GitHub integration) to harden Hermes against hardware risk.
- Fill gaps in state management, backup, migration readiness, and agent-enhanced git workflows.
- Operationalize using existing skills (hermes-operations, ops-engineer, trading-bot-operations, agent-delegation, github tools, recovery-packet, kanban-orchestrator, project-cleanup, etc.).
- Align with user preferences: tight handoffs, MASTER_TASK_TRACKING.md as primary record, code isolation testing, real data, proactive execution, Kanban delegation, no mid-stream asks.

**Current State (from inspection 2026-06-14):**
- **Hermes:** ~/.hermes/ with config.yaml (grok-build-0.1 + xai-oauth, multiple personalities, toolsets), profiles/ (crypto-orchestrator, crypto-engineer, code-reviewer, etc.), skills/ (hermes-operations, ops-engineer, trading-bot-operations, delegation, github, etc.), cron/, memories/, plans/, plugins/. Many config.yaml.bak. Gateway/TUI processes running. Update available (157 commits behind).
- **Git Repo (operations.git):** Central source of truth for bot code (phase6/), extensive docs/ (MASTER_TASK_TRACKING.md, handoffs/, reviews/, PHASE6_*, VPS_MIGRATION_PLAYBOOK.md, AGENTS.md), scripts/. Active branch phase-6.1. Recent commits on Phase 6 runner hardening, RSI, sentiment. .env and some state gitignored. Existing patterns: atomic backups, git restores for code, decision logs committed, git clone in migration playbook.
- **Hardware Risks:** Single old SFF PC. Disk pressure (81G/146G used). Long uptime but legacy (potential failure, no easy redundancy). Hermes state (~/.hermes) local-only beyond manual .bak.
- **Existing Mitigations:** VPS_MIGRATION_PLAYBOOK.md (Docker-focused for bot, git clone, monitoring). Hermes crons for trading-intel + kanban backup. ops-engineer skill with MASTER + GitHub tickets. recovery-packet skill. Git used for code/state restores in docs.
- **Gaps:** 
  - Hermes configs/skills/profiles/memories/crons not systematically versioned or remotely backed (beyond local).
  - Limited git-native workflows for agents (e.g., no standard PR creation by delegates, hooks for agent triggers).
  - Migration playbook outdated (pre-Phase 6, bot-focused, not full Hermes + profiles).
  - Operational risk: Hardware failure = loss of delegation brain, crons, persistent agents. Slow recovery.
  - Workflow gaps: Task tracking (MASTER) strong but could tie tighter to git issues/PRs. Agent code changes not always isolated via git branches/PRs.

## Phase 1: Baseline & Inventory (Immediate, 1-2 days)
1. **Capture current Hermes state into git-tracked artifacts** (in operations repo under `hermes/` or `docs/hermes/`):
   - Export non-secret parts: `hermes profiles list`, `hermes cron list`, copy key profile.yaml/SOUL.md/prompts (strip secrets).
   - Scripted dump of skills/ (names + versions), cron yamls, config.yaml (sanitized).
   - Use `recovery-packet` skill to create a "Hermes Resume Packet" markdown before changes.
2. **Inventory & audit**:
   - Run `hermes config list`, profile details, `hermes cron list`, process inspection (via ops-engineer patterns).
   - Git status of operations repo; identify all Hermes-related files (handoffs, plans referencing Hermes).
   - Hardware health: `smartctl`, disk usage, `journalctl` for past crashes (if any).
3. **Update MASTER_TASK_TRACKING.md** with "GIT_HERMES_OPS-001: Baseline inventory" ticket (use ops-engineer format: evidence, verify command, impact).
4. **Verification:** `git status`, compare exported state vs live. Isolation test: standalone script to diff.

**Owner:** Primary agent (or delegate via kanban-orchestrator). Use `hermes-operations` skill.

## Phase 2: Git Versioning & Mirroring of Hermes Artifacts (Core Leverage)
Leverage git as single source of truth and offsite backup (GitHub remote mitigates legacy hardware).

1. **Add Hermes state mirror to operations repo** (new `hermes/` dir or `docs/hermes-state/`):
   - Track: Sanitized config excerpts, profile yamls (crypto-*, code-reviewer), key skills (or symlinks/references), cron definitions (as .yaml), plans/.
   - `.gitignore` extensions for secrets (auth.json, .env refs, keys). Use git-crypt or separate secret store if needed.
   - Commit strategy: Atomic commits on changes (e.g., "hermes: update crypto-orchestrator profile for Phase 6 SL attachment").
   - Script: `scripts/hermes/sync-hermes-state.sh` (rsync selective + git add/commit/push). Run via Hermes cron (e.g., daily or on profile change).
2. **Bidirectional sync patterns**:
   - Pull: On Hermes start/recovery, `git pull` then apply to ~/.hermes (with backup).
   - Push: Cron or post-change hook to commit changes back.
   - Use git worktrees or subdirs for isolated "agent workspaces" (e.g., experiment with new profile on branch without affecting main).
3. **Git as durable backup/restore**:
   - Recovery: `git checkout -- hermes/profiles/crypto-orchestrator/` then copy to ~/.hermes.
   - Integrate with existing VPS playbook: On new droplet, `git clone operations.git; ./scripts/hermes/restore-hermes.sh`.
   - Leverage `recovery-packet` before risky ops; store packets in git.
4. **Version Hermes code/configs alongside bot**:
   - Track changes to phase6/ + Hermes delegation patterns in same commits (already partially happening).
   - Use git tags for stable "Hermes + Phase 6" releases.

**Benefits filled:** Hardware risk → remote git history + easy restore. No more relying only on local .bak.

**Skills to use:** `hermes-operations`, `project-cleanup`, `recovery-packet`, `ops-engineer`.

## Phase 3: Enhanced Git Workflows for Hermes Agents (Operational Leverage)
Use git tools (via terminal + github skill) to make agents more effective and auditable.

1. **Agent-driven git operations**:
   - Standardize: Delegates (via `delegate_task` or kanban) create branches for changes (`git checkout -b feat/hermes-profile-update-xxx`).
   - Code gen: Use `github-code-review` + `claude-code`/`codex` skills for PRs. Agents propose diffs, open PRs via `gh` CLI (in terminal).
   - Handoffs/plans: Store in git (already in docs/handoffs/, docs/plans/). Enforce via `writing-plans` skill.
2. **Git hooks & triggers for Hermes**:
   - Pre-commit: Validate skills (lint prompts), run isolation tests for trading code, update MASTER.
   - Post-commit / webhook: Trigger Hermes cron or specific profile (e.g., on Phase 6 commit, run `crypto-monitor` or sentiment refresh). Use `webhook-subscriptions` skill.
   - CI (GitHub Actions if enabled): On PR, run code-isolation tests, `hermes` dry-runs if possible, or simulation of delegation.
3. **Task & Kanban integration**:
   - Tie MASTER_TASK_TRACKING.md entries to GitHub issues (ops-engineer already does this partially). Use `gh issue create` in tickets.
   - Kanban-orchestrator: Route git-related tasks (e.g., "refactor runner using git branch isolation").
   - Handoff Documents: Always include git commands for apply/verify (e.g., "git cherry-pick <commit>").
4. **Code & Management Tasks**:
   - Use `codebase-inspection` (pygount) + git blame/log for audits.
   - `project-cleanup` for repo hygiene (e.g., clean pycache, consolidate hermes scripts).
   - For trading bot: Git as deployment source (git pull on VPS + restart runner).

**Benefits filled:** Workflows enhanced — agents become git-native (better traceability, collaboration, rollback). Fills "management tasks" gap.

**Skills:** `github-code-review`, `agent-delegation`, `kanban-orchestrator`, `writing-plans`, `spec-driven-feature-development`.

## Phase 4: Resilience, Monitoring & Migration (Risk Mitigation)
1. **Hardware resilience via git**:
   - Daily/ hourly cron (via hermes-operations): `git push` of state mirror + `rsync` or git bundle for full ~/.hermes snapshot (encrypted).
   - Recovery playbook: Update VPS_MIGRATION_PLAYBOOK.md with Hermes-specific steps (clone repo, restore profiles/skills/cron from git, `hermes gateway start`, profile crons).
   - Hybrid: Run core Hermes on legacy for now; mirror critical profiles/crons to VPS/Droplet for failover (Docker as in playbook + git clone).
2. **Ops integration**:
   - Enhance `ops-engineer` + `trading-bot-operations`: Add git checks (e.g., "repo dirty?", "last sync age", "unpushed Hermes changes").
   - Monitoring: `crypto-monitor` profile + cron inspects git status alongside processes/logs. Escalate via Telegram + MASTER + GitHub.
   - Use `delegation-sanity-check` on any git-involved claims.
3. **Migration path** (build on existing playbook):
   - Phase A: Git-mirror everything (this plan).
   - Phase B: Provision VPS (per playbook specs), `git clone`, restore Hermes state, run parallel gateway on cloud (Tailscale for access).
   - Phase C: Cutover critical crons/profiles (trading runner, monitors) to cloud; legacy as hot spare or decommission.
   - Dockerize Hermes where possible (or use existing s6 supervision from hermes-s6 skill).
   - Test: Full restore drill (git checkout + apply) + isolation test of restored trading runner.
4. **Verification loops**:
   - Every change: Isolation test script (e.g., `test_hermes_git_sync.py` using `code-isolation-testing`).
   - Post-deploy: `ops_engineer.py --verify GIT_HERMES-xxx`.
   - Real data: Always use actual git log/status in reports.

**Benefits filled:** Legacy risk reduced via git as portable, versioned, remote-backed "brain backup". Fills migration/operational gaps.

**Skills:** `ops-engineer`, `hermes-operations`, `trading-bot-operations`, `reliable-service-hosting`, `recovery-packet`, `hermes-s6-container-supervision`.

## Phase 5: Sustainment & Continuous Improvement
- **Cron & Automation:** Add Hermes crons for git sync, state health checks, auto-PR for routine updates (via delegation).
- **Documentation:** Keep this plan + links in MASTER, AGENTS.md, VPS playbook. Update on changes.
- **Measurement:** Track in MASTER: restore time, sync success rate, agent PRs opened/merged, hardware incident count (hopefully 0).
- **Tools Evolution:** Contribute improvements back to Hermes (use `hermes-agent` skill). E.g., native git toolset or better profile versioning.
- **Kanban:** Create dedicated lane for "Git-Hermes Ops" using kanban-orchestrator. Tight handoffs for any sub-tasks.

## Immediate Next Actions (Proactive Execution)
1. Create this plan file in git (done).
2. Open MASTER ticket: GIT_HERMES_OPS-001 Baseline (append via ops patterns).
3. Run baseline inventory (Phase 1) using terminal + delegate if needed.
4. Create `scripts/hermes/sync-hermes-state.sh` skeleton + test commit.
5. Update VPS_MIGRATION_PLAYBOOK.md with Hermes sections (reference this plan).
6. Test restore drill on a temp dir/branch.
7. Schedule via Hermes cron: daily git sync + ops check.

**Success Criteria:**
- All critical Hermes artifacts (profiles, key skills, crons, plans) tracked in git + pushed to remote.
- Documented restore path that works from git clone alone (tested via isolation script).
- At least one agent-driven git workflow (e.g., branch + PR for a profile tweak) executed.
- Updated migration playbook + ops monitoring including git health.
- No data loss on hypothetical hardware failure (recoverable in <30min via git).

**Risks & Mitigations (per existing decision log patterns):**
- Secret leakage: Strict .gitignore + explicit load paths only (project + ~/.hermes .env as documented).
- Sync drift: Atomic scripts + verification in ops-engineer.
- Legacy hardware during transition: Keep local running; use git for quick parallel deploys.
- Over-engineering: Start minimal (mirror + sync script), iterate with real usage data.

**References:**
- Existing: VPS_MIGRATION_PLAYBOOK.md, hermes-operations/SKILL.md, ops-engineer/SKILL.md (and references/), trading-bot-operations, docs/MASTER_TASK_TRACKING.md, AGENTS.md, phase6/ code + handoffs.
- Git: operations.git (phase-6.1), GitHub for issues/PRs.
- Skills to load for execution: hermes-operations, ops-engineer, agent-delegation, kanban-orchestrator, github-code-review, recovery-packet, project-cleanup.

This plan turns the git repo from "code storage" into the backbone for Hermes resilience and supercharged agent workflows. Execute via delegation where scope is clear; use tight handoffs.

**Status:** Draft complete. Ready for Phase 1 kickoff. Append updates to MASTER. 

(Plan committed to git as part of creation.)