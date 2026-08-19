#!/usr/bin/env bash
# Run one Kimi platform code-review slice (code-reviewer profile).
set -euo pipefail
SLICE="${1:-}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SLICES_DIR="$ROOT/data/state/code_review/slices"
OUT_DIR="$ROOT/data/state/code_review/out"
mkdir -p "$OUT_DIR"
if [[ -z "$SLICE" ]]; then
  echo "usage: $0 S1|S2|...|S8" >&2
  ls -1 "$SLICES_DIR"/*.md 2>/dev/null | xargs -n1 basename || true
  exit 2
fi
PACKET="$SLICES_DIR/${SLICE}.md"
if [[ ! -f "$PACKET" ]]; then
  echo "missing packet: $PACKET" >&2
  exit 2
fi
cd "$ROOT"
REVIEWER_BIN="${REVIEWER_BIN:-code-reviewer}"
if ! command -v "$REVIEWER_BIN" >/dev/null 2>&1; then
  hermes profile alias code-reviewer >/dev/null 2>&1 || true
fi
OUT="$OUT_DIR/${SLICE}.md"
PROMPT="$(cat <<EOF
You are the independent platform code reviewer (Kimi). Do NOT implement fixes.
Read the slice packet, inspect every listed path with read_file, run every listed test command from repo root with .venv/bin/python3 when applicable.
Apply focus questions. No fake-data tolerance on live paths.

Output MUST follow the Deliverable format in the packet exactly.
End with SLICE_STATUS: REVIEWED or SLICE_STATUS: BLOCKED (reason).

--- SLICE PACKET ---
$(cat "$PACKET")
EOF
)"
echo "[platform-review] slice=$SLICE started $(date -Is)" | tee "$OUT"
"$REVIEWER_BIN" chat -Q -t file,terminal -q "$PROMPT" 2>&1 | tee -a "$OUT"
echo "[platform-review] slice=$SLICE finished $(date -Is)" | tee -a "$OUT"