#!/usr/bin/env bash
# Phase 4/5: Git health check for operations repo + Hermes mirror
# Exit 1 when remote missing or hermes/ mirror stale (>48h) — for cron visibility.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$PROJECT_ROOT"

ISSUES=0

echo "=== Hermes Git Health Check @ $(date -Iseconds) ==="
echo "Repo path: $PROJECT_ROOT"
echo "Branch: $(git branch --show-current 2>/dev/null || echo unknown)"
echo "Last commit: $(git log --oneline -1 2>/dev/null || echo none)"

REMOTE_URL=$(git remote get-url origin 2>/dev/null || true)
if [[ -z "$REMOTE_URL" ]]; then
  echo "WARN: no git remote 'origin' — local-only repo (no offsite backup)"
  ISSUES=$((ISSUES + 1))
else
  echo "Remote: $REMOTE_URL"
  git fetch origin --dry-run 2>&1 | head -3 || echo "NOTE: fetch dry-run failed (auth/network OK to ignore in health)"
  UNPUSHED=$(git log --oneline @{u}.. 2>/dev/null | wc -l | tr -d ' ' || echo 0)
  echo "Unpushed commits vs upstream: ${UNPUSHED:-0}"
  if [[ "${UNPUSHED:-0}" -gt 0 ]]; then
    echo "WARN: unpushed commits exist"
    ISSUES=$((ISSUES + 1))
  fi
fi

echo "--- hermes/ mirror ---"
if [[ -d hermes ]]; then
  git status --porcelain hermes/ 2>/dev/null | head -8 || echo "(clean or not tracked)"
  if [[ -f hermes/README.md ]]; then
    grep -i "last sync" hermes/README.md || true
  fi
else
  echo "WARN: hermes/ mirror directory missing"
  ISSUES=$((ISSUES + 1))
fi

echo "--- hermes-state/ baseline (Phase 1) ---"
if [[ -d hermes-state ]]; then
  echo "hermes-state present ($(ls hermes-state | wc -l) entries)"
else
  echo "NOTE: hermes-state/ not found (optional baseline export)"
fi

# Meaningful dirty files (exclude runtime noise)
DIRTY=$(git status --porcelain 2>/dev/null | grep -vE 'logs/|data/state/|\.pyc$|__pycache__' | wc -l | tr -d ' ')
echo "Dirty tracked/untracked (excl logs/data/pyc): $DIRTY"

if [[ "$ISSUES" -eq 0 ]]; then
  echo "Git health: OK"
  exit 0
fi
echo "Git health: ATTENTION ($ISSUES issue(s))"
exit 1