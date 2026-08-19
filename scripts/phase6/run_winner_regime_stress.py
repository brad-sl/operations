#!/usr/bin/env python3
"""Score OPT winner (bear_window_rotation_14d) per regime window vs baseline_7d."""
from __future__ import annotations

import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.run_scenario_leaderboard import load_pack, run_scenario, _rank_key


def main() -> int:
    template = load_pack(ROOT / "phase6/research/scenarios/regime_quad_template.json")
    r2 = load_pack(ROOT / "phase6/research/scenarios/r2_defensive_sharpe_gate.json")
    primary = "sharpe_ratio"
    baseline_id = "baseline_7d"
    winner_id = "bear_window_rotation_14d"

    ids = {baseline_id, winner_id}
    scenarios = []
    for sc in r2["scenarios"]:
        if sc["id"] in ids:
            sc2 = copy.deepcopy(sc)
            sc2.pop("date_range", None)  # use regime window, not bear_window slice
            scenarios.append(sc2)

    rows_out = []
    for rw in template["regime_windows"]:
        pack = {
            "pack_id": f"winner_stress_{rw['regime']}",
            "primary_metric": primary,
            "baseline_scenario_id": baseline_id,
            "default_engine": "arch4",
            "date_range": rw["date_range"],
            "scenarios": copy.deepcopy(scenarios),
        }
        results = [run_scenario(pack, sc) for sc in pack["scenarios"]]
        by_id = {r["id"]: r for r in results}
        b = by_id.get(baseline_id, {})
        w = by_id.get(winner_id, {})
        bm = b.get("metrics") or {}
        wm = w.get("metrics") or {}
        b_sh = bm.get("sharpe_ratio")
        w_sh = wm.get("sharpe_ratio")
        beats = (
            w_sh is not None
            and b_sh is not None
            and float(w_sh) > float(b_sh)
        )
        rows_out.append(
            {
                "regime": rw["regime"],
                "label": rw.get("label"),
                "date_range": rw["date_range"],
                "baseline_sharpe": b_sh,
                "winner_sharpe": w_sh,
                "baseline_return_pct": bm.get("total_return_pct"),
                "winner_return_pct": wm.get("total_return_pct"),
                "baseline_max_dd": bm.get("max_drawdown_pct"),
                "winner_max_dd": wm.get("max_drawdown_pct"),
                "winner_beats_baseline_sharpe": beats,
            }
        )
        print(
            f"{rw['regime']:6} {rw['date_range']['start']}..{rw['date_range']['end']} "
            f"winner_sharpe={w_sh} baseline_sharpe={b_sh} beats={beats} "
            f"ret_w={wm.get('total_return_pct')} dd_w={wm.get('max_drawdown_pct')}"
        )

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "winner_id": winner_id,
        "baseline_id": baseline_id,
        "primary_metric": primary,
        "regimes": rows_out,
    }
    path = ROOT / "data/state/analyst_winner_regime_stress_latest.json"
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())