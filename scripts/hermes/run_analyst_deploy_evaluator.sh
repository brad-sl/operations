#!/usr/bin/env bash
# Analyst deploy evaluator — separate model from parent delegate_task implementers.
set -euo pipefail
PACKET="${1:-}"
if [[ -z "$PACKET" || ! -f "$PACKET" ]]; then
  echo "usage: $0 data/state/evaluator_packet.md" >&2
  exit 2
fi
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
REVIEWER_BIN="${REVIEWER_BIN:-code-reviewer}"
if ! command -v "$REVIEWER_BIN" >/dev/null 2>&1; then
  hermes profile alias code-reviewer >/dev/null 2>&1 || true
fi
# Optional one-off overrides (else uses code-reviewer profile model in its config.yaml):
EVAL_MODEL="${EVAL_MODEL:-}"
EVAL_PROVIDER="${EVAL_PROVIDER:-}"
EXTRA=()
if [[ -n "$EVAL_MODEL" ]]; then
  EXTRA+=(-m "$EVAL_MODEL")
fi
if [[ -n "$EVAL_PROVIDER" ]]; then
  EXTRA+=(--provider "$EVAL_PROVIDER")
fi
PROMPT="$(cat <<EOF
You are the deploy evaluator only. Never implement fixes. ASSUME BROKEN.
Read the packet below, run every listed isolation command, inspect git diff on touched paths.
Output exactly one verdict block:

VERDICT: PASS | REJECT
REASONS:
- ...
TESTS:
- cmd → exit N

--- PACKET ---
$(cat "$PACKET")
EOF
)"
"$REVIEWER_BIN" chat -Q "${EXTRA[@]}" -t file,terminal \
  -q "$PROMPT"