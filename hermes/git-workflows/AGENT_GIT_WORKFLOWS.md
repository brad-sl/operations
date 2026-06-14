# Agent Git Workflows for Hermes (Phase 3)

**Purpose:** Standardize how Hermes agents (via delegation, kanban, or direct) use git for traceability, collaboration, rollback, and auditability. This turns agents into git-native operators.

**Branching Strategy**
- Feature / task branches: `feat/<short-task-id>-<kebab-description>` e.g. `feat/phase3-git-workflows-demo`
- Bugfix: `fix/<id>-<desc>`
- Ops / hermes state: `hermes/<profile>-<change>`
- Never commit directly to `phase-6.1` or `main` for agent work.

**Commit Messages**
- Conventional: `type(scope): short summary`
  - Examples:
    - `hermes: add agent git workflows doc (Phase 3)`
    - `feat(phase6): integrate stop-loss with rebalance (P6-XXX)`
    - `ops: update hermes mirror after profile change`
- Body: Link to MASTER ticket, handoff, or Kanban card ID.
- Always reference the durable record (MASTER_TASK_TRACKING.md or GitHub issue).

**Agent-Driven Workflow (Standard Pattern)**
1. **Receive task** (via kanban, delegation handoff, or prompt).
2. **Create branch**: `git checkout -b feat/<id>-<desc>`
3. **Work in isolation**: Only touch files listed in "Files / Directories to Work In" from handoff.
4. **Update artifacts**:
   - Add git commands to any handoff or deliverable (e.g. "To apply: git cherry-pick <commit>").
   - Update MASTER_TASK_TRACKING.md with evidence (commit hash, diffs).
   - For code changes: run isolation tests before commit.
5. **Commit frequently** with clear messages.
6. **Open PR** (when gh available):
   - `gh pr create --title "..." --body "See MASTER GIT_HERMES_OPS-XXX and handoff.md"`
   - Or via terminal + delegation to code-reviewer profile.
7. **Review & merge**: Use code-reviewer profile or github-code-review skill. Require reviewer sign-off for high-risk (trading logic).
8. **Cleanup**: Delete branch after merge. Update any linked Kanban card.

**Handoff Document Integration (from agent-delegation skill)**
Every handoff must include a "Git Commands" section:

**Git Commands for Apply / Verify**
- Branch: `git checkout -b feat/<id>`
- Apply changes: `git cherry-pick <commit-sha>` or `git apply <patch>`
- Verify: `git log --oneline -3; git diff HEAD~1`
- Rollback: `git revert <commit>`

**Hooks & Automation Recommendations**
- Pre-commit: Run isolation tests (`python hermes-state/verify_baseline.py`), lint, update MASTER.
- Post-commit: Trigger Hermes cron or specific profile (e.g. `hermes -p crypto-monitor` for report).
- Use `webhook-subscriptions` skill for GitHub events → Hermes profile.

**Task & Kanban Integration**
- Create GitHub issues from MASTER entries: `gh issue create --title "GIT_HERMES_OPS-003" --body "See docs/MASTER..."`
- Kanban cards should reference branch/PR.
- Use `github-code-review` skill for PR reviews.
- For delegation: Assign git-heavy tasks to `crypto-engineer` or `code-reviewer`.

**Code & Management Tasks**
- Use `codebase-inspection` (pygount) + `git blame/log` for audits.
- `project-cleanup` for repo hygiene during agent work.
- Git as deployment: On VPS, `git pull; ./scripts/hermes/restore-hermes.sh` for Hermes state; `git pull && restart runner` for Phase 6.

**Example Agent Workflow (Demonstrated)**
See commit on branch `feat/phase3-git-workflows` for a live example of this document being added by the primary agent following the pattern.

**Success Criteria for Phase 3**
- At least one agent-driven branch + commit (or PR) executed with full documentation.
- All new handoffs include git commands section.
- MASTER entries reference commits.
- Workflow doc committed to `hermes/git-workflows/`.

**Skills Used**
- agent-delegation (for handoff templates)
- kanban-orchestrator (routing)
- github (via terminal/gh when available)
- hermes-operations (for integration with crons/profiles)
- project-cleanup (structure)

**Next Evolution (Phase 4+)**
- Pre-commit hooks in repo.
- GitHub Actions for isolation test on PRs.
- Agent profiles that can call `gh` directly via terminal tool.

This document lives in the `hermes/` mirror so it is versioned and restorable.