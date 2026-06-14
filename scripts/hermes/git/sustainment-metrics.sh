#!/bin/bash
# Phase 5: Sustainment metrics for Hermes + git ops
# Collects simple metrics for monitoring (age of mirror, health, cron status)
# Can be called by crypto-monitor or daily report.

set -e

echo "=== Hermes Git Sustainment Metrics @ $(date) ==="

# Git mirror health
echo "1. Git Mirror Health:"
/home/brad/projects/crypto-trading-bot/scripts/hermes/git/git-health-check.sh | grep -E 'Branch|Last commit|Hermes mirror|Git health' || echo "Health script issue"

# Sync age (last commit touching hermes/)
echo ""
echo "2. Mirror Sync Age:"
LAST_SYNC=$(git -C /home/brad/projects/crypto-trading-bot log --oneline --since="1 week ago" -- hermes/ | head -1 || echo "No recent hermes commits")
echo "Last hermes/ commit: $LAST_SYNC"

# Current Hermes crons count
echo ""
echo "3. Active Hermes Crons:"
hermes cron list 2>/dev/null | grep -c '\[active\]' || echo "hermes cron list failed"

# Disk / uptime for legacy hardware
echo ""
echo "4. Hardware Snapshot (legacy risk):"
df -h /home | tail -1
uptime | cut -d',' -f1-2

# Trading bot quick status (from Phase 6 context)
echo ""
echo "5. Trading Context (if runner active):"
ls -l /home/brad/projects/crypto-trading-bot/logs/phase6/*.log 2>/dev/null | tail -1 || echo "No phase6 logs"
echo "Total portfolio (from last known): check dashboard or runner state"

echo ""
echo "Sustainment metrics complete. Log this to MASTER or Telegram periodically."
echo "Next: Schedule via cron, feed to crypto-monitor profile."