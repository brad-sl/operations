#!/usr/bin/env bash
# Rebuild analyst weekly 7d trade-review fact pack (measure-only).
# stdout is injected into the Sunday agent prompt — must not be empty
# (Hermes skips the AI call when script stdout is blank).
set -euo pipefail
export PATH="${HOME}/.local/bin:${PATH}"
export OPENBLAS_CORETYPE="${OPENBLAS_CORETYPE:-GENERIC}"
ROOT="/home/brad/projects/crypto-trading-bot"
cd "$ROOT" || exit 1
PYTHON="${ROOT}/.venv/bin/python3"
[[ -x "$PYTHON" ]] || PYTHON=python3
mkdir -p logs
TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG="logs/analyst_weekly_trade_review_${TS}.log"
{
  echo "analyst_weekly_trade_review start ${TS}"
  "$PYTHON" scripts/phase6/run_analyst_weekly_trade_review.py --days 7
  echo "analyst_weekly_trade_review end"
} >>"$LOG" 2>&1

# Optional short card mode (no_agent fallback)
if [[ "${1:-}" == "--tg-card" || "${ANALYST_WEEKLY_TG_CARD:-0}" == "1" ]]; then
  "$PYTHON" scripts/phase6/run_analyst_weekly_trade_review.py --load-latest --tg-card 2>>"$LOG"
  exit 0
fi

# Default stdout for Hermes agent injection (required)
"$PYTHON" - <<'PY'
from pathlib import Path
import json

root = Path("/home/brad/projects/crypto-trading-bot")
state = root / "data/state/analyst_weekly_trade_review_latest.json"
report = root / "reports/ANALYST_WEEKLY_TRADE_REVIEW_LATEST.md"
print("ANALYST_WEEKLY_TRADE_REVIEW fact pack ready (measure-only).")
print(f"STATE: {state}")
print(f"REPORT: {report}")
if state.exists():
    d = json.loads(state.read_text(encoding="utf-8") or "{}")
    s = d.get("summary") or {}
    ctx = d.get("context") or {}
    msm = ctx.get("membership_sizing_matrix") or {}
    nav = ctx.get("nav") or {}
    print(
        f"primary B/S={s.get('n_primary_buys')}/{s.get('n_primary_sells')} "
        f"pnl=${s.get('realized_pnl_usd')} wr={s.get('exit_wr')} tax=${s.get('process_tax_usd')}"
    )
    print(
        f"regime={ctx.get('regime')} util={nav.get('util_pct')}% "
        f"matrix_rows={msm.get('n_rows')} block_max_held={len(msm.get('block_max_held') or [])} "
        f"inconsistent={msm.get('n_inconsistent')}"
    )
    eject = ctx.get("eject_cohort_card") or {}
    if eject:
        print(
            f"eject_cohort n={eject.get('n_ejects')} "
            f"pct_cleared_kindling={eject.get('pct_cleared_live_kindling')} "
            f"net=${eject.get('pnl_net_usd')} fees=${eject.get('rt_fee_usd')} "
            f"top_blocks={eject.get('kindling_block_top')}"
        )
        if eject.get("plain"):
            print(f"eject_plain: {eject.get('plain')}")
    seeds = d.get("seed_hypotheses") or []
    if seeds:
        print("seeds:")
        for h in seeds[:6]:
            print(f"  - [{h.get('priority')}] {h.get('id')}: {str(h.get('hint') or '')[:140]}")
print("Read STATE + REPORT before writing suggestions. Matrix is rulebook not stone.")
print("E-EJECT-COHORT-CARD is live measure SSOT (do not re-propose as experiment).")
print("No knobs / no orders. Use notepad + continuity for week-over-week memory.")
PY
