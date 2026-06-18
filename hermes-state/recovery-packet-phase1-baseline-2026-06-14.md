# Recovery Packet — 2026-06-14 09:30

**Session:** Telegram DM (Brad Slusher) / operations.git phase-6.1  
**Goal:** Kickoff Phase 1 of GIT_HERMES_OPERATIONALIZATION_PLAN.md — full baseline inventory ("understand the state of the world") of Hermes setup on legacy hardware + git repo strengths/gaps. Create git-tracked hermes-state/ exports, recovery packet, detailed MASTER ticket, verification script.  

**Current Status:** Phase 1 data collection complete via direct terminal (per hermes-operations skill). Hermes-state/ artifacts exported. Profiles, crons, hardware, git, processes inspected. Recovery packet + MASTER update + verification script + commit next.

## Last Known Good State
- Hermes v0.16.0 (157 commits behind) on legacy HP Compaq 8000 (Ubuntu 24.04, 12d uptime).
- Active crons (hermes cron list source of truth): twice-daily-trading-intelligence, Daily Kanban Backup, rsi-15min-refresher, sentiment-30min-refresh (all no-agent where possible).
- Key profiles: crypto-orchestrator (high-value decisions, expensive model, owns trading platform), crypto-monitor (scheduled health checks + Telegram + Kanban escalation), crypto-engineer, crypto-analyst, code-reviewer.
- Live processes: phase6 live runner (PID ~1412994), multiple profile gateways (crypto-orchestrator etc.), dashboard (9119/8080), TUI, OpenClaw.
- Git: operations.git (phase-6.1), plan just committed, heavy Phase 6 history, 1548+ porcelain (mostly venv/pycache), only recent Hermes file = this plan.
- Hardware: 146G disk 81G used, 9.6Gi RAM, journal errors on crypto-dashboard.service (groups) + snaps. No smartctl in session.
- Existing: hermes-state/ dir created with sanitized exports (cron list, key profiles yaml, skills inventory, hardware, config).

## Key Artifacts
- /home/brad/projects/crypto-trading-bot/hermes-state/ (README, cron/hermes-cron-list.txt, profiles/*-profile.yaml, skills/*.txt, hardware/system.txt, config-sanitized.txt)
- ~/.hermes/ (config.yaml + .bak, profiles/17 dirs, cron/ with jobs.json + crypto-monitor.yaml, skills/37 incl. hermes-operations/ops-engineer/trading-bot-operations/agent-delegation/github/recovery-packet, kanban/, resume-packets/, memories/, plans/, state.db, ops_engineer_state.json)
- docs/GIT_HERMES_OPERATIONALIZATION_PLAN.md (just committed)
- docs/MASTER_TASK_TRACKING.md (high-level GIT_HERMES_OPS-001 already appended; will add detailed evidence)
- Live trading: phase6_runner live with real OP trade history (order c0bb9e08-... )
- VPS_MIGRATION_PLAYBOOK.md (outdated, bot-focused Docker)

## Next Action
1. Write detailed GIT_HERMES_OPS-001 evidence block to MASTER (ops-engineer style: real snippets, verify cmds like `hermes cron list`, `ls hermes-state/`, `ps aux | grep phase6`).
2. Create standalone verification script (hermes-state/verify_baseline.py) that re-runs key inspections and diffs against exported artifacts (isolation test).
3. Git add hermes-state/ + MASTER update + script; commit with message tying to plan.
4. Update todo list, produce Phase 1 summary report.
5. (Post-commit) Verify with `git status`, `ls hermes-state/`, re-run `hermes cron list`.

## Notes / Blockers
- "profiles list" CLI failed (use `hermes profile list` or dir as source); used filesystem + targeted cat for accuracy.
- No secrets in any exports (sanitized greps).
- Aligns with loaded skills (hermes-operations for direct terminal + cron list as truth; ops-engineer for MASTER tickets + verification loops; recovery-packet for this exact packet).
- User prefs followed: MASTER primary, real data only, proactive execution, isolation testing, tight artifacts.
- Hardware risk visible (journal service fails, old SFF PC, long uptime).
- Git leverage starting: hermes-state/ now tracked for restore/mirror.

**Created by:** grok-build-0.1 (xai-oauth) per Phase 1 kickoff.  
**Resume after packet:** Continue with MASTER append + script + commit.