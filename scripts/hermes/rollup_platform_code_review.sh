#!/usr/bin/env bash
# Merge slice outputs into PLATFORM_REVIEW_ROLLUP.md
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT_DIR="$ROOT/data/state/code_review/out"
ROLLUP="$ROOT/data/state/code_review/PLATFORM_REVIEW_ROLLUP.md"
{
  echo "# Platform code review rollup (Kimi)"
  echo "Generated: $(date -Is)"
  echo ""
  echo "## Slice index"
  for f in "$OUT_DIR"/S*.md; do
    [[ -f "$f" ]] || continue
    echo "- $(basename "$f")"
  done
  echo ""
  echo "## Combined outputs"
  for id in S1 S2 S3 S4 S5 S6 S7 S8; do
    f="$OUT_DIR/${id}.md"
    if [[ -f "$f" ]]; then
      echo ""
      echo "---"
      echo "## Include: $id"
      cat "$f"
    fi
  done
  echo ""
  echo "## Manual triage"
  echo "1. Grep all slice outs for '### High' and 'Integration gaps'"
  echo "2. Dedupe into MASTER or docs/handoffs/"
} > "$ROLLUP"
echo "wrote $ROLLUP"