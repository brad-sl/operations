# GIT_HERMES_OPERATIONALIZATION_PLAN — Concise Phase Goals

**Overall Objective**  
Leverage the strengths of operations.git to version, backup, and operationalize the Hermes Agent setup on legacy hardware, mitigating risk while enhancing agent workflows, code management, and resilience. Aligns with existing skills (hermes-operations, ops-engineer, etc.) and user preferences (MASTER primary, tight handoffs, isolation testing, real data, proactive execution).

## Phase 1: Baseline & Inventory (Immediate)
**Goal:** Establish a complete, verifiable snapshot of the current "state of the world" as the foundation for all subsequent work.  
- Capture sanitized Hermes state (profiles, crons, skills, config, processes) into git-tracked artifacts under hermes-state/.  
- Audit git repo references, hardware health, and existing mitigations/gaps.  
- Document findings with real evidence in MASTER_TASK_TRACKING.md (GIT_HERMES_OPS-001) using ops-engineer format.  
- Create recovery packet and standalone isolation verification script.  
**Success:** All critical current state exported, verified against live system, and committed. Phase 1 complete (2026-06-14).

## Phase 2: Git Versioning & Mirroring of Hermes Artifacts (Core Leverage)
**Goal:** Turn Hermes state into a first-class, versioned citizen of the git repo for durability and portability.  
- Add selective, sanitized mirror of ~/.hermes (profiles, crons, key skills, plans, configs) to the operations repo.  
- Implement sync script (`scripts/hermes/sync-hermes-state.sh`) with atomic commits, bidirectional pull/push, and git worktrees for safe experiments.  
- Establish git as primary backup/restore mechanism (integrated with VPS playbook and recovery-packets).  
- Version Hermes artifacts alongside bot code (phase6/) with tags for stable releases.  
**Success:** Hermes state tracked in git + pushed to remote; restore path works from `git clone` + script; no reliance on local .bak only.

## Phase 3: Enhanced Git Workflows for Hermes Agents (Operational Leverage)
**Goal:** Make agents git-native to improve traceability, collaboration, auditability, and management of code/tasks.  
- Standardize agent-driven git operations: branches for changes, `gh` PRs via delegation skills, git commands in all handoffs/plans.  
- Add git hooks, webhooks, and CI triggers that invoke Hermes profiles/crons on commits.  
- Tie MASTER/Kanban entries to GitHub issues; use `codebase-inspection` and `project-cleanup` for audits and hygiene.  
- Treat git pull on VPS as deployment source for runners/agents.  
**Success:** At least one full agent-driven branch + PR workflow executed; git commands embedded in handoffs; improved audit trail for agent work.

## Phase 4: Resilience, Monitoring & Migration (Risk Mitigation)
**Goal:** Directly mitigate legacy hardware single-point-of-failure risk using git as the portable "brain backup," while advancing migration.  
- Automate git pushes + encrypted snapshots via cron; enhance `ops-engineer` and `crypto-monitor` with git health checks (dirty repo, sync age, unpushed changes).  
- Update VPS_MIGRATION_PLAYBOOK.md with full Hermes restore steps (git clone + profile/cron restore + gateway start).  
- Execute hybrid ops: mirror critical profiles/crons to cloud (VPS/Droplet via git clone + Docker); test full restore drills and isolation tests.  
- Cutover path: legacy as hot spare; critical workloads (trading runner, monitors) moved to reliable infra.  
**Success:** Documented + tested restore <30 min from git alone; git health in monitoring; migration playbook updated and exercised; hardware risk demonstrably reduced.

## Phase 5: Sustainment & Continuous Improvement
**Goal:** Institutionalize git-Hermes practices for long-term reliability and evolution.  
- Add Hermes crons for ongoing sync, state health checks, and routine auto-PR generation (via delegation).  
- Maintain living documentation (this plan, MASTER, AGENTS.md, VPS playbook); track metrics (restore time, sync success rate, agent PRs, hardware incidents).  
- Evolve tools/skills (e.g., contribute git enhancements back via hermes-agent skill); create dedicated Kanban lane for "Git-Hermes Ops".  
**Success:** Automated daily/periodic syncs running; metrics visible in MASTER; process is self-sustaining with clear iteration path.

**Cross-Phase Principles (apply to all)**  
- Real data and tool-verified evidence only.  
- Isolation testing before claiming success.  
- MASTER_TASK_TRACKING.md as primary record; GitHub secondary.  
- Tight handoffs and delegation via kanban-orchestrator when scope allows.  
- Leverage existing skills rather than reinventing.  

**Overall Success Criteria** (from plan)  
- Critical Hermes artifacts tracked in git + remote.  
- Restore path works from git clone (tested).  
- Agent-driven git workflows in use.  
- Migration playbook current + ops monitoring includes git health.  
- No data loss on hypothetical hardware failure (recoverable quickly via git).  

**Status:** Phase 1 complete and committed. Phases 2–5 ready for execution.  
See full plan: docs/GIT_HERMES_OPERATIONALIZATION_PLAN.md and hermes-state/ artifacts.