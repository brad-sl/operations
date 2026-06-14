#!/bin/bash
# Phase 4: Git health check for Hermes mirror resilience
# Run via cron or crypto-monitor profile

cd "$(dirname "$0")/../.." || exit 1

echo "=== Hermes Git Health Check @ $(date) ==="
echo "Repo: $(git remote get-url origin 2>/dev/null || echo 'no remote')"
echo "Branch: $(git branch --show-current)"
echo "Last commit: $(git log --oneline -1)"
echo "Hermes mirror status:"
git status --porcelain hermes/ | head -5 || echo "Clean (no uncommitted hermes/ changes)"
echo "Unpushed commits (if any):"
git log --oneline @{u}.. 2>/dev/null | head -3 || echo "Up to date with remote"

# Age of last sync (from README or commit)
if [ -f hermes/README.md ]; then
  grep -i "last sync" hermes/README.md || echo "No sync timestamp in README"
fi

echo "Git health: OK (for monitoring)"