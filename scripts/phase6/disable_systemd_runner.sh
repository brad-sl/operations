#!/usr/bin/env bash
# One-time: stop systemd from spawning a second runner (conflicts with scripts/phase6/start_phase6_runner.sh).
set -euo pipefail
echo "Disabling system phase6-runner.service (uses /usr/bin/python3, duplicates .venv runner)..."
sudo systemctl disable --now phase6-runner.service
echo "OK. Canonical start: bash scripts/phase6/start_phase6_runner.sh"
ps -eo pid,args | grep -E '[p]ython.* -m phase6\.core\.phase6_runner' || echo "(no runners — start script if needed)"