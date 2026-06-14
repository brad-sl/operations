# Git-Enhanced Handoff Document Template (Phase 3 Addition)

Use this in addition to the base agent-delegation/SKILL.md template.

## Git Commands for Apply / Verify / Rollback (MANDATORY SECTION)

**Branch to use:** `git checkout -b feat/<TASK-ID>-<kebab-desc>`

**Apply this work:**
- `git cherry-pick <COMMIT-SHA>`
- Or `git apply <patch-file>`

**Verify:**
- `git log --oneline -3`
- `git show <COMMIT-SHA> --stat`
- Run isolation test: `python3 hermes-state/verify_baseline.py` (or specific test)

**Rollback if needed:**
- `git revert <COMMIT-SHA>`
- Or `git checkout phase-6.1 -- <affected-files>`

**Commit style used in this handoff:**
`hermes: <action> (Phase 3 / <TASK-ID>)`

**PR / Review:**
- Create PR via `gh pr create --title "..." --body "See MASTER GIT_HERMES_OPS-XXX and this handoff"`
- Or delegate review to code-reviewer profile.

**Files touched in this task (from handoff scope):**
- (List exactly)

**Integration with MASTER:**
- All evidence (commit, diffs, test output) must be appended to docs/MASTER_TASK_TRACKING.md under the relevant GIT_HERMES_OPS-XXX ticket.

**Notes for agent:**
- Always start on a feature branch.
- Link every commit to the durable MASTER record.
- For Hermes state changes, also update the hermes/ mirror and consider running the sync script.

This template ensures every delegated task produces auditable, git-native output.