#!/usr/bin/env bash
# sync-hermes-state.sh
# Phase 2: Selective rsync of non-secret Hermes state from ~/.hermes into git-tracked hermes/ mirror,
# then atomic git commit + push.
#
# Usage:
#   ./scripts/hermes/sync-hermes-state.sh          # normal sync + commit
#   ./scripts/hermes/sync-hermes-state.sh --dry    # dry-run only
#
# Intended to be run manually or via Hermes cron (daily or on profile/cron change).
# Follows hermes-operations patterns: source of truth is ~/.hermes (live), git mirror is durable backup.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HERMES_HOME="${HOME}/.hermes"
MIRROR_DIR="${PROJECT_ROOT}/hermes"
DRY_RUN=false
TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)

if [[ "${1:-}" == "--dry" ]]; then
  DRY_RUN=true
  echo "=== DRY RUN MODE ==="
fi

echo "=== Hermes State Sync (Phase 2) @ ${TIMESTAMP} ==="
echo "Live source: ${HERMES_HOME}"
echo "Git mirror : ${MIRROR_DIR}"

if [[ ! -d "${HERMES_HOME}" ]]; then
  echo "ERROR: ${HERMES_HOME} not found. Exiting."
  exit 1
fi

mkdir -p "${MIRROR_DIR}"/{profiles,cron,skills,plans,config,hardware,restore}

# --- Selective rsync (non-secret only) ---
# Profiles: full yaml + SOUL.md (strip any embedded secrets in prompt if needed)
RSYNC_OPTS="-av --delete --exclude='*.bak' --exclude='auth.*' --exclude='*.lock' --exclude='state.db*' --exclude='*.env' --exclude='gateway.*' --exclude='*.json'"

if $DRY_RUN; then RSYNC_OPTS="$RSYNC_OPTS --dry-run"; fi

echo "--- Syncing profiles (crypto-* + code-reviewer) ---"
for profile in crypto-orchestrator crypto-engineer crypto-monitor crypto-analyst code-reviewer; do
  if [[ -d "${HERMES_HOME}/profiles/${profile}" ]]; then
    rsync $RSYNC_OPTS "${HERMES_HOME}/profiles/${profile}/profile.yaml" "${MIRROR_DIR}/profiles/${profile}-profile.yaml" 2>/dev/null || true
    rsync $RSYNC_OPTS "${HERMES_HOME}/profiles/${profile}/SOUL.md" "${MIRROR_DIR}/profiles/${profile}-SOUL.md" 2>/dev/null || true
  fi
done

echo "--- Syncing cron definitions ---"
rsync $RSYNC_OPTS "${HERMES_HOME}/cron/"*.yaml "${MIRROR_DIR}/cron/" 2>/dev/null || true
# Also capture current live cron list
hermes cron list 2>&1 > "${MIRROR_DIR}/cron/hermes-cron-list.txt" || true

echo "--- Syncing relevant skills (names only + key SKILL.md excerpts) ---"
ls "${HERMES_HOME}/skills/" > "${MIRROR_DIR}/skills/all-skills.txt" 2>/dev/null || true
ls "${HERMES_HOME}/skills/" | grep -E 'hermes-operations|ops-engineer|trading-bot-operations|agent-delegation|github|recovery-packet|kanban|project-cleanup' > "${MIRROR_DIR}/skills/relevant-skills.txt" 2>/dev/null || true

# Copy key skill files if they exist in project skills (or note they live in ~/.hermes)
for skill in hermes-operations ops-engineer trading-bot-operations; do
  if [[ -f "${HERMES_HOME}/skills/${skill}/SKILL.md" ]]; then
    cp "${HERMES_HOME}/skills/${skill}/SKILL.md" "${MIRROR_DIR}/skills/${skill}-SKILL.md" 2>/dev/null || true
  fi
done

echo "--- Syncing hardware snapshot + plans + PHASE_GOALS ---"
uname -a > "${MIRROR_DIR}/hardware/system.txt" 2>/dev/null || true
df -h >> "${MIRROR_DIR}/hardware/system.txt" 2>/dev/null || true
free -h >> "${MIRROR_DIR}/hardware/system.txt" 2>/dev/null || true
uptime >> "${MIRROR_DIR}/hardware/system.txt" 2>/dev/null || true

# Plans and goals
cp "${PROJECT_ROOT}/hermes-state/PHASE_GOALS.md" "${MIRROR_DIR}/" 2>/dev/null || true
# Add any new plans from ~/.hermes/plans/
rsync -av --include='*.md' --exclude='*' "${HERMES_HOME}/plans/" "${MIRROR_DIR}/plans/" 2>/dev/null || true

echo "--- Sanitized config excerpt ---"
grep -v -E '(key|secret|token|password|auth|api_key)' "${HERMES_HOME}/config.yaml" | head -80 > "${MIRROR_DIR}/config/config-sanitized.txt" 2>/dev/null || true

# Update README timestamp
echo "Hermes state mirror (sanitized, non-secret only). Last sync: ${TIMESTAMP}" > "${MIRROR_DIR}/README.md"

if $DRY_RUN; then
  echo "=== DRY RUN COMPLETE (no git changes) ==="
  exit 0
fi

# --- Atomic git commit + push ---
cd "${PROJECT_ROOT}"

echo "--- Git add & commit ---"
git add hermes/ scripts/hermes/sync-hermes-state.sh scripts/hermes/restore-hermes.sh .hermes/resume-packets/ 2>/dev/null || git add hermes/

if git diff --cached --quiet; then
  echo "No changes to commit."
else
  git commit -m "hermes: sync state mirror ${TIMESTAMP}

- Updated profiles (crypto-orchestrator, crypto-engineer, crypto-monitor, etc.)
- Cron list + definitions
- Relevant skills inventory + excerpts
- Hardware snapshot
- Sanitized config
- PHASE_GOALS.md

Source: live ~/.hermes via selective rsync (no secrets).
Follows Phase 2 of GIT_HERMES_OPERATIONALIZATION_PLAN."
  echo "Committed."

  if git remote | grep -q origin; then
    echo "--- Pushing ---"
    git push || echo "Push failed (check auth/remote). Continuing."
  fi
fi

echo "=== Sync complete ==="
# Empty grep under pipefail was exit 1 after a clean mirror (false daily-cron fail).
mapfile -t _hs < <(git status --short 2>/dev/null | grep -E 'hermes/|scripts/hermes' || true)
if ((${#_hs[@]})); then
  printf '%s\n' "${_hs[@]:0:5}"
else
  echo "(hermes/ mirror clean in worktree)"
fi
echo "Verify with: python3 hermes-state/verify_baseline.py (or re-run sync --dry)"