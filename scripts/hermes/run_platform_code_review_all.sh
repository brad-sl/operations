#!/usr/bin/env bash
# Run all Kimi platform code-review slices sequentially.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
LOG="$ROOT/data/state/code_review/run_all.log"
mkdir -p "$ROOT/data/state/code_review/out"
echo "=== platform code review all $(date -Is) ===" | tee "$LOG"
for id in S1 S2 S3 S4 S5 S6 S7 S8; do
  echo "--- $id ---" | tee -a "$LOG"
  if ! scripts/hermes/run_platform_code_review_slice.sh "$id"; then
    echo "WARN: $id failed non-zero" | tee -a "$LOG"
  fi
done
scripts/hermes/rollup_platform_code_review.sh | tee -a "$LOG"
echo "=== done $(date -Is) ===" | tee -a "$LOG"