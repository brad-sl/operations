# Crypto Trading Bot – Team Policy & Workflow

## Agent Roles

- **orchestrator** (you / main session)  
  Strategic direction, final approvals, high-risk changes.

- **engineer**  
  Implements core logic (runner loops, order execution, risk engine).

- **code-reviewer** (Claude 3.5 Sonnet)  
  **Mandatory independent review** on any trading-critical code.  
  Reviews for correctness, edge cases, safety, and maintainability.  
  Never implements — only reviews.

- **crypto-monitor** (Grok-3)  
  Scheduled health checks and reporting (runs every 6 hours).  
  Produces monitor reports and can send Telegram summaries.

- **crypto-orchestrator** (Grok-4.3)  
  Expensive strategic agent. Only assigned to high-impact or high-risk tasks.  
  Must review all `code-reviewer` output before live deployment.

## Kanban Workflow Rules

1. **Code changes** touching live trading, risk, or execution **must** go through `code-reviewer`.
2. After `code-reviewer` finishes, the card can only move to `Done` once `crypto-orchestrator` (or human) has reviewed the findings.
3. `crypto-monitor` runs autonomously via cron and appends reports to `data/logs/`.
4. Any task that affects real money (live mode, SL/TP logic, position sizing) requires explicit `crypto-orchestrator` approval before merge/deployment.

## Cost Control

- Cheap models (`code-reviewer`, `crypto-monitor`) handle the majority of work.
- Expensive model (`crypto-orchestrator`) is reserved for final review of risky components only.
- Monitor runs on a 6-hour schedule to avoid unnecessary token burn.

## Update Policy

After any merged change that affects trading behavior, the responsible agent **must** append a one-line entry to `docs/PHASE6.md` under “Maintenance Schedule”.

Last updated: 2026-05-14 (team profiles + policy created)