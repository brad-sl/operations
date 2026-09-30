#!/usr/bin/env bash
# Monthly class×lifecycle digest — always emits a short card for delivery.
set -euo pipefail
ROOT="${PHASE6_ROOT:-/home/brad/projects/crypto-trading-bot}"
cd "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
PY="${ROOT}/.venv/bin/python3"
if [[ ! -x "$PY" ]]; then
  PY=python3
fi
"$PY" scripts/phase6/run_pair_lifecycle_by_class.py >/tmp/pair_lifecycle_by_class_monthly.out 2>/tmp/pair_lifecycle_by_class_monthly.err || {
  echo "PAIR_LIFECYCLE_BY_CLASS monthly FAILED"
  tail -20 /tmp/pair_lifecycle_by_class_monthly.err 2>/dev/null || true
  exit 1
}
# Short TG card from latest JSON
"$PY" - <<'PY'
import json
from pathlib import Path
p = Path("data/state/pair_lifecycle_by_class_latest.json")
if not p.exists():
    print("Pair lifecycle by class — no artifact yet")
    raise SystemExit(0)
d = json.loads(p.read_text())
print("📊 Pair lifecycle by class (monthly)")
print(d.get("plain_english") or "")
print(f"as_of {d.get('as_of')} · lookback {d.get('lookback_days')}d · n_rt={d.get('n_rt')} · edge_claim={d.get('edge_claim_allowed')}")
print("")
print("by class:")
for c in d.get("by_class") or []:
    print(
        f"  {c.get('key')}: n={c.get('n_rt')} win={float(c.get('win_rate') or 0):.0%} "
        f"sl={float(c.get('sl_rate') or 0):.0%} tp={float(c.get('tp_rate') or 0):.0%} "
        f"tax={float(c.get('process_tax_rate') or 0):.0%} pnl={c.get('pnl_sum')} [{c.get('claim_level')}]"
    )
print("")
for n in (d.get("hypothesis_notes") or [])[:4]:
    print(f"• {n}")
print("")
print("report: reports/PAIR_LIFECYCLE_BY_CLASS_LATEST.md")
print("measure-only · no auto thresholds · soft-up door RTs feed N")
PY
