#!/usr/bin/env python3
"""TG-04 scaffold: offline TP / trail-after-green research (no live writes).

Uses closed ledger sells with implied r. Compares:
  - baseline (as realized)
  - hypothetical: cap loss at SL only (already mostly true)
  - hypothetical: bank at +tp if final r was lower after a greener path — NOT available without bars
  - simple: classify exits that finished >= tp vs <0

Writes reports/TP_TRAIL_SCAFFOLD_YYYY-MM-DD.{md,json}
Real data only. Enum: continue_observe | design_shadow | drop
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.research.run_exit_asymmetry_report import analyze  # noqa: E402


def main() -> int:
    base = analyze(days=45)
    totals = base["totals"]
    by = base["by_reason"]
    sl = by.get("stop_loss_exchange") or {}
    rot = by.get("rotation_exchange") or {}

    # Without path data we cannot honest-trail. Gate: need OHLCV path study next.
    n_realized = (totals.get("realized_wins") or 0) + (totals.get("realized_losses") or 0)
    enum = "design_shadow" if n_realized >= 30 and (totals.get("exit_wr") or 0) < 0.35 else "continue_observe"
    if n_realized < 15:
        enum = "continue_observe"

    payload = {
        "schema": "tp_trail_scaffold_v1",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "live_config_writes": False,
        "take_profit_pct_live": None,
        "baseline_from_exit_asymmetry": {
            "exit_wr": totals.get("exit_wr"),
            "sum_pnl": totals.get("sum_pnl_realized_usd"),
            "sl_sum_pnl": sl.get("sum_pnl_usd"),
            "rotation_sum_pnl": rot.get("sum_pnl_usd"),
            "n": n_realized,
        },
        "hypothesis": (
            "Fixed TP 6% or trail after +4% to BE+fees would raise WR and cut giveback; "
            "must verify on bar paths before live attach."
        ),
        "blocked_on": "ohlcv_path_counterfactual_not_built",
        "next_build": [
            "For each buy→exit, load pair OHLCV high watermark max r before exit",
            "Counterfactual: exit at first touch of +tp OR trail stop",
            "Compare path DD and expectancy vs baseline ledger",
        ],
        "candidates": [
            {"name": "fixed_tp_06", "tp": 0.06, "trail": None},
            {"name": "trail_after_04_to_be", "arm_at": 0.04, "trail_to": 0.005},
            {"name": "fixed_tp_08", "tp": 0.08, "trail": None},
        ],
        "recommendation_enum": enum,
        "note": "Scaffold only — do not set live take_profit_pct until path study + shadow.",
    }

    day = payload["as_of"][:10]
    out_j = ROOT / "reports" / f"TP_TRAIL_SCAFFOLD_{day}.json"
    out_m = ROOT / "reports" / f"TP_TRAIL_SCAFFOLD_{day}.md"
    out_j.parent.mkdir(parents=True, exist_ok=True)
    out_j.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md = "\n".join(
        [
            f"# TP / Trail Scaffold — {day}",
            "",
            f"**Enum:** `{enum}` · live writes: false",
            f"- Baseline Exit WR: {totals.get('exit_wr')} n={n_realized}",
            f"- SL sum PnL: {sl.get('sum_pnl_usd')} · rotation: {rot.get('sum_pnl_usd')}",
            f"- Blocked on: {payload['blocked_on']}",
            "",
            "## Next",
            *[f"- {x}" for x in payload["next_build"]],
            "",
            "Do not enable live `take_profit_pct` from this scaffold alone.",
            "",
        ]
    )
    out_m.write_text(md, encoding="utf-8")
    print(md)
    print(f"wrote {out_j}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
