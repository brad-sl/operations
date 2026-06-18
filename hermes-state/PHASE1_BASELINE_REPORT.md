# Phase 1 Baseline Report: Hermes + Git + Hardware State of the World
**Date:** 2026-06-14  
**Plan:** GIT_HERMES_OPERATIONALIZATION_PLAN.md (Phase 1: Baseline & Inventory)  
**Executed by:** Direct terminal + file ops (hermes-operations, ops-engineer, recovery-packet skills loaded and followed).  

## Summary of State of the World
Hermes is a mature v0.16.0 deployment on legacy hardware, actively orchestrating the crypto trading bot (Phase 6 live runner running with real trades). The operations.git repo is the code/docs backbone with excellent Phase 6 history but until now zero systematic versioning of Hermes state itself. This baseline captures everything for git mirroring and resilience.

### Hermes (Core "Brain")
- **Version:** v0.16.0 (2026.6.5), Python 3.11.15, 157 commits behind upstream. Update recommended.
- **Config:** ~/.hermes/config.yaml (model grok-build-0.1 default + xai, personalities, toolsets; many .bak for rollback).
- **Profiles (17 total, dir as source of truth; `hermes profile list` subcommand confirmed):**
  - **crypto-orchestrator** (primary high-agency): Uses expensive x-ai/grok-4.3. Owns trading platform strategy, risk validation, final approvals, sub-agent spawning (delegate/kanban), code review before deploy. Toolsets: file/terminal/kanban/skills. Strong rules for PHASE6.md updates.
  - **crypto-engineer**: Software builder (plans, features, PRs, DevOps, research). Has full SOUL.md persona.
  - **crypto-monitor**: Dedicated low-cost (grok-3) scheduled monitor. 6h cron. Inspects ps/logs, safe restarts, Telegram reports + Kanban escalation with evidence bundles. Explicit production-safety rules.
  - **crypto-analyst, code-reviewer** (claude-3.5-sonnet for reviews — strict full-file read + flag live breaks), plus marketing/creative suite.
- **Crons (hermes cron list — canonical truth, 4 active, mostly no-agent for low cost):**
  1. twice-daily-trading-intelligence (0 9,21 * * *, script generate report, last success 09:00).
  2. Daily Kanban Backup (0 3 * * *).
  3. rsi-15min-refresher (*/15, project workdir, refresh_rsi_prices.py).
  4. sentiment-30min-refresh (*/30, project, run_sentiment_cron.sh).
  - crypto-monitor.yaml also present for 6h health.
- **Other State:** kanban.db, state.db, ops_engineer_state.json, phase6_monitor_state.txt, resume-packets/, scripts/, memories (MEMORY.md/USER.md), plans/, plugins/ (37 skills total; relevant: hermes-operations, ops-engineer, trading-bot-operations, agent-delegation, github, recovery-packet).
- **Running Processes:** Live phase6_runner (real mode, recent OP trade), multiple profile gateways (orchestrator, engineer, analyst, reviewer), Hermes dashboard (0.0.0.0:9119 --insecure + 8080), TUI, OpenClaw node gateway.

### Git Repo (operations.git, phase-6.1)
- Remote: https://github.com/brad-sl/operations.git.
- Heavy Phase 6 activity (RSI, sentiment, runner hardening, SL, real trades).
- Hermes integration so far: Limited to references in MASTER, handoffs (e.g. sentiment cron), scripts/ops/ops_engineer.py (points to ~/.hermes/ops state), PHASE6 docs, and the new plan.
- Before this: No hermes-state/ or profile/cron versioning in git.
- Current: Plan committed; 1548+ modified (mostly cache/venv — normal).

### Hardware (Legacy Risk Confirmed)
- Machine: HP Compaq 8000 Elite SFF PC, Ubuntu 24.04.4 LTS, 6.17 kernel.
- Uptime: 12 days 16h+ (stable but long-running risk).
- Resources: 146G disk (81G ~58% used), 9.6Gi RAM (~2.8Gi used, healthy available).
- Issues (journalctl): Repeated crypto-dashboard.service failures (supplementary groups permission), snap firmware-notifier fails.
- Smartctl: Not accessible in this context.
- Trading/Hermes co-located and live.

### Artifacts Created (git-tracked starting point)
- hermes-state/README.md, cron/hermes-cron-list.txt, profiles/*-profile.yaml (orchestrator/engineer/monitor), skills/*.txt, hardware/system.txt, config-sanitized.txt.
- recovery-packet-phase1-baseline-2026-06-14.md (full per skill: goal, status, artifacts, next actions, notes; also copied to .hermes/resume-packets/ and project .hermes/).
- verify_baseline.py (standalone isolation test: re-inspects crons/profiles/hardware/git/processes vs exports; PASS/FAIL with real checks).
- Detailed evidence appended to MASTER under GIT_HERMES_OPS-001 (ops-engineer format: real snippets, verify commands, impact).
- This report.

### Verification Results (from verify_baseline.py run)
(See tool output in session: crons/profiles/hardware/git/processes checks performed. Key crons and profiles matched exports. Live runner + gateways confirmed. Git plan commit visible. Minor porcelain expected.)

### Gaps Identified (for Phase 2+)
- Hermes state (profiles, crons, skills, memories) not versioned in git before this.
- Migration playbook outdated (pre-Hermes full profiles).
- Dashboard service flaky on this hardware.
- No automated sync/restore yet.
- Git workflows for agents (PRs from delegates) not standardized.

**Phase 1 Complete.** All 12 todos addressed (data gathered, exports, packet, script, MASTER, report).  
**Ready for Phase 2:** Skeleton sync script + first git mirror of hermes-state/.

**Next:** Commit (if not auto), run verify post-commit, start Phase 2. All real data, no hype. Aligns with user prefs (MASTER primary, isolation, proactive, delegation-ready).