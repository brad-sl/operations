#!/usr/bin/env bash
# git-daily-management.sh — Daily git + Hermes mirror hygiene (Phase 5 sustainment)
#
# Runs:
#   1) Repo health check (branch, remote, dirty/unpushed, hermes mirror age)
#   2) Hermes state mirror sync (non-secret ~/.hermes → hermes/ + commit; push if origin)
#
# Intended: Hermes cron no_agent daily. Silent when healthy; stderr on hard failures.
#
# Usage:
#   ./scripts/hermes/git-daily-management.sh
#   ./scripts/hermes/git-daily-management.sh --health-only
#   ./scripts/hermes/git-daily-management.sh --dry
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="${PROJECT_ROOT}/logs"
LOG_FILE="${LOG_DIR}/git-daily-management.log"
HEALTH_ONLY=false
DRY=false

for arg in "${@:-}"; do
  case "$arg" in
    --health-only) HEALTH_ONLY=true ;;
    --dry) DRY=true ;;
  esac
done

mkdir -p "$LOG_DIR"
exec > >(tee -a "$LOG_FILE") 2>&1

echo ""
echo "========== Git daily management @ $(date -Iseconds) =========="
echo "Project: $PROJECT_ROOT"

cd "$PROJECT_ROOT"

# --- 1) Health ---
if [[ -x "${PROJECT_ROOT}/scripts/hermes/git/git-health-check.sh" ]]; then
  bash "${PROJECT_ROOT}/scripts/hermes/git/git-health-check.sh" || HEALTH_RC=$?
  HEALTH_RC=${HEALTH_RC:-0}
else
  echo "WARN: git-health-check.sh missing"
  HEALTH_RC=1
fi

# Repo-specific signals for agents/monitors
BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
DIRTY=$(git status --porcelain 2>/dev/null | grep -vE '^.. (__pycache__|\.pyc|logs/|data/state/)' | wc -l | tr -d ' ')
UNTRACKED=$(git status --porcelain 2>/dev/null | grep '^??' | wc -l | tr -d ' ')
echo "Branch: $BRANCH | dirty (excl noise): $DIRTY | untracked: $UNTRACKED"

if ! git remote | grep -q .; then
  echo "ACTION REQUIRED: No git remote configured. Add origin for offsite backup:"
  echo "  git remote add origin https://github.com/brad-sl/operations.git"
  echo "  git push -u origin phase-6.1"
fi

if [[ "$HEALTH_ONLY" == true ]]; then
  echo "========== Health-only complete (rc=${HEALTH_RC:-0}) =========="
  exit "${HEALTH_RC:-0}"
fi

# --- 2) Hermes mirror sync ---
SYNC_ARGS=()
if [[ "$DRY" == true ]]; then SYNC_ARGS+=(--dry); fi

if [[ -x "${PROJECT_ROOT}/scripts/hermes/sync-hermes-state.sh" ]]; then
  bash "${PROJECT_ROOT}/scripts/hermes/sync-hermes-state.sh" "${SYNC_ARGS[@]}" || SYNC_RC=$?
  SYNC_RC=${SYNC_RC:-0}
else
  echo "ERROR: sync-hermes-state.sh missing"
  SYNC_RC=1
fi

# --- 3) Baseline verifier (non-fatal) ---
if [[ -f "${PROJECT_ROOT}/hermes-state/verify_baseline.py" ]]; then
  python3 "${PROJECT_ROOT}/hermes-state/verify_baseline.py" 2>&1 | tail -5 || true
fi

RC=0
if [[ "${HEALTH_RC:-0}" -ne 0 || "${SYNC_RC:-0}" -ne 0 ]]; then RC=1; fi
echo "========== Daily git management finished (rc=$RC) =========="
exit $RC