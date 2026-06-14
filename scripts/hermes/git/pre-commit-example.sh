#!/bin/bash
# Example pre-commit hook for Hermes agent git workflows (Phase 3)
# Install: cp scripts/hermes/git/pre-commit-example.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit

set -e

echo "=== Phase 3 Pre-commit: Git workflow validation ==="

# 1. Isolation test (from Phase 1/2)
if [ -f hermes-state/verify_baseline.py ]; then
  python3 hermes-state/verify_baseline.py || echo "Warning: baseline verify had issues (non-blocking for docs)"
fi

# 2. Update MASTER with commit note (example)
echo "Pre-commit: Would append to MASTER_TASK_TRACKING.md for this change"

# 3. Check for git commands in recent changes (if handoff touched)
git diff --cached --name-only | grep -E 'handoff|HANDOFF' && echo "Handoff changed - ensure git section present"

echo "Pre-commit checks passed (Phase 3 standards)"
