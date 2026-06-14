#!/usr/bin/env bash
# restore-hermes.sh
# Phase 2 companion: Restore Hermes state from the git-tracked hermes/ mirror back to ~/.hermes.
#
# Usage:
#   ./scripts/hermes/restore-hermes.sh          # apply mirror to live ~/.hermes (with backup)
#   ./scripts/hermes/restore-hermes.sh --dry    # show what would happen
#
# Safety: Always creates timestamped backup of target files before overwrite.
# Use after `git pull` or on new machine (git clone operations.git; ./scripts/hermes/restore-hermes.sh).

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HERMES_HOME="${HOME}/.hermes"
MIRROR_DIR="${PROJECT_ROOT}/hermes"
DRY_RUN=false
TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)
BACKUP_DIR="${HERMES_HOME}/backups/restore-${TIMESTAMP}"

if [[ "${1:-}" == "--dry" ]]; then
  DRY_RUN=true
  echo "=== DRY RUN MODE ==="
fi

echo "=== Hermes Restore from Git Mirror @ ${TIMESTAMP} ==="
echo "Mirror source: ${MIRROR_DIR}"
echo "Target:        ${HERMES_HOME}"

if [[ ! -d "${MIRROR_DIR}" ]]; then
  echo "ERROR: ${MIRROR_DIR} not found. Run from project root or git clone first."
  exit 1
fi

mkdir -p "${HERMES_HOME}/backups"

# Create backup of key live files before restore
if ! $DRY_RUN; then
  mkdir -p "${BACKUP_DIR}"
  echo "Creating backup in ${BACKUP_DIR}"
  for item in profiles cron config.yaml skills; do
    if [[ -e "${HERMES_HOME}/${item}" ]]; then
      cp -r "${HERMES_HOME}/${item}" "${BACKUP_DIR}/" 2>/dev/null || true
    fi
  done
fi

# --- Apply mirror (selective, non-destructive where possible) ---
echo "--- Restoring profiles ---"
for f in "${MIRROR_DIR}/profiles/"*-profile.yaml; do
  [[ -f "$f" ]] || continue
  profile=$(basename "$f" -profile.yaml)
  target_dir="${HERMES_HOME}/profiles/${profile}"
  if $DRY_RUN; then
    echo "Would mkdir -p ${target_dir} && cp $f ${target_dir}/profile.yaml"
  else
    mkdir -p "${target_dir}"
    cp "$f" "${target_dir}/profile.yaml"
    # Also restore SOUL if present
    soul_src="${MIRROR_DIR}/profiles/${profile}-SOUL.md"
    [[ -f "$soul_src" ]] && cp "$soul_src" "${target_dir}/SOUL.md" || true
  fi
done

echo "--- Restoring cron yamls ---"
if $DRY_RUN; then
  echo "Would rsync ${MIRROR_DIR}/cron/*.yaml -> ${HERMES_HOME}/cron/"
else
  mkdir -p "${HERMES_HOME}/cron"
  rsync -av "${MIRROR_DIR}/cron/"*.yaml "${HERMES_HOME}/cron/" 2>/dev/null || true
fi

echo "--- Restoring skills inventory (names only; full skills live in ~/.hermes/skills) ---"
if $DRY_RUN; then
  echo "Would copy skills/*.txt to ${HERMES_HOME}/ (for reference)"
else
  mkdir -p "${HERMES_HOME}/skills"
  cp "${MIRROR_DIR}/skills/"*.txt "${HERMES_HOME}/" 2>/dev/null || true
fi

echo "--- Restoring plans + PHASE_GOALS ---"
if $DRY_RUN; then
  echo "Would rsync plans/ and PHASE_GOALS.md"
else
  mkdir -p "${HERMES_HOME}/plans"
  rsync -av "${MIRROR_DIR}/plans/" "${HERMES_HOME}/plans/" 2>/dev/null || true
  cp "${MIRROR_DIR}/PHASE_GOALS.md" "${HERMES_HOME}/" 2>/dev/null || true
fi

# Note: We do NOT blindly overwrite full config.yaml or state.db.
# The sanitized config is for reference only. Full restore of secrets must be manual or via separate secret store.

echo "=== Restore ${DRY_RUN:+DRY RUN }complete ==="
echo "Live Hermes may need 'hermes gateway restart' or profile re-use after changes."
echo "Backup saved to: ${BACKUP_DIR:-<dry-run>}"
echo "Verify: hermes profile list; hermes cron list; ls ~/.hermes/profiles/"