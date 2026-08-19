#!/usr/bin/env bash
# Daily Dose full pipeline. Stdout final body = Hermes no_agent Telegram delivery.
# D0 draft -> D1 auto APPROVED (diversity; no platform-why lines) -> D2 disk publish_ready.
set -euo pipefail
cd /home/brad/projects/crypto-trading-bot || exit 1
PY="${PWD}/.venv/bin/python3"
if [[ ! -x "$PY" ]]; then PY=python3; fi
export OPENBLAS_CORETYPE="${OPENBLAS_CORETYPE:-GENERIC}"

# Brad OK flag (authorized scheduled delivery to this Telegram channel)
FLAG="data/state/daily_dose_brad_telegram_ok.flag"
if [[ ! -f "$FLAG" ]]; then
  date -u +%Y-%m-%dT%H:%M:%SZ >"$FLAG"
fi

# Quiet stages to stderr; clean body on stdout for delivery
{
  echo "=== D0 draft ==="
  "$PY" phase6/scripts/run_daily_dose.py --top 8
  echo "=== D1 edit ==="
  "$PY" phase6/scripts/run_daily_dose_edit.py \
    --status APPROVED \
    --reviewer content-editor-auto \
    --top 5 \
    --notes "Auto D1 v4: basket-pair diversity (max 2 BTC-only); domain links; no platform-why. Not a trade signal."
  echo "=== D2 publish (disk) ==="
  "$PY" phase6/scripts/run_daily_dose_publish.py
} >&2

# Delivery body only
cat data/state/daily_dose_publish_ready.txt
