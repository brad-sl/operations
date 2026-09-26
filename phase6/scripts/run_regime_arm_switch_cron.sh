#!/usr/bin/env bash
# BTC-regime preferred-arm switch — Hermes no_agent cron.
# Applies paper-primary flip only; live_membership_swaps always forced false.
# Stdout empty unless preferred_arm changed (Telegram hygiene).
set -euo pipefail
export PATH="${HOME}/.local/bin:${PATH}"
ROOT="/home/brad/projects/crypto-trading-bot"
cd "$ROOT"
# shellcheck disable=SC1091
if [[ -f .venv/bin/activate ]]; then
  source .venv/bin/activate
fi
export OPENBLAS_CORETYPE="${OPENBLAS_CORETYPE:-GENERIC}"
export PYTHONUNBUFFERED=1
export PYTHONPATH=.

LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR" data/state reports data/ohlcv
TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$LOG_DIR/regime_arm_switch_${TS}.log"
LATEST_LOG="$LOG_DIR/regime_arm_switch_latest.log"

# Brad GO 2026-09-25: production preferred-arm attention SSOT (still never live seats).
MODE="${REGIME_ARM_SWITCH_MODE:-production}"
APPLY="${REGIME_ARM_SWITCH_APPLY:-1}"

set +e
python - <<'PY' "$LOG" "$MODE" "$APPLY"
import json
import sys
from pathlib import Path

ROOT = Path("/home/brad/projects/crypto-trading-bot")
sys.path.insert(0, str(ROOT))

from phase6.core.regime_arm_switch import run

log_path = Path(sys.argv[1])
mode = (sys.argv[2] or "shadow").strip().lower()
apply = str(sys.argv[3] or "1").strip().lower() in {"1", "true", "yes", "on"}

try:
    result = run(mode=mode, apply=apply, use_network=True)
except Exception as e:
    log_path.write_text(f"regime_arm_switch FAILED: {e!r}\n")
    # Failures: surface short line so failure_deliver can catch if configured;
    # prefer local on failure via cron failure_deliver=local.
    print(f"regime_arm_switch FAILED: {e!r}", file=sys.stderr)
    sys.exit(1)

log_path.write_text(json.dumps(result, indent=2, default=str) + "\n")
snap = result.get("snapshot") or {}
changed = bool(result.get("changed")) and bool(result.get("decision_written"))
line = (
    f"regime_arm_switch mode={result.get('mode')} "
    f"tape={snap.get('sticky_tape')} ret7={snap.get('btc_ret_7d_pct')} "
    f"arm={result.get('after_preferred_arm')} "
    f"before={result.get('before_preferred_arm')} "
    f"changed={result.get('changed')} written={result.get('decision_written')} "
    f"live_swaps=false"
)
# Append one-liner to log
with log_path.open("a") as f:
    f.write(line + "\n")

# Telegram only on real preferred_arm flip that wrote decision
if changed:
    print(
        "🔄 Regime arm switch (paper-primary only — not live basket)\n"
        f"• tape: {snap.get('sticky_tape')} (BTC 7d={snap.get('btc_ret_7d_pct')}%)\n"
        f"• preferred_arm: {result.get('before_preferred_arm')} → {result.get('after_preferred_arm')}\n"
        f"• mode: {result.get('mode')} · live_membership_swaps: OFF"
    )
sys.exit(0)
PY
RC=$?
set -e
cp -f "$LOG" "$LATEST_LOG" 2>/dev/null || true
exit "$RC"
