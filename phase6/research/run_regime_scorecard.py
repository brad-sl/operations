#!/usr/bin/env python3
"""Run regime windows from regime_quad_template.json → scorecard JSON."""
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
    template_path = ROOT / "phase6/research/scenarios/regime_quad_template.json"
    template = load_pack(template_path)
    primary = template["primary_metric"]
    baseline_id = template["baseline_scenario_id"]
    scorecard = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pack_id": template["pack_id"],
        "primary_metric": primary,
        "regimes": [],
    }

    for rw in template.get("regime_windows", []):
        pack = copy.deepcopy(template)
        pack["pack_id"] = f"{template['pack_id']}_{rw['regime']}"
        pack["date_range"] = rw["date_range"]
        del pack["regime_windows"]

        rows = []
        for sc in pack["scenarios"]:
            try:
                rows.append(run_scenario(pack, sc))
            except Exception as e:
                rows.append(
                    {
                        "id": sc["id"],
                        "error": str(e),
                        "metrics": {},
                    }
                )

        rows.sort(key=lambda r: _rank_key(primary, r.get("metrics") or {}), reverse=True)
        winner = rows[0]["id"] if rows else None
        baseline = next((r for r in rows if r.get("id") == baseline_id), None)
        beats_baseline = False
        if winner and baseline:
            wv = (rows[0].get("metrics") or {}).get(primary)
            bv = (baseline.get("metrics") or {}).get(primary)
            if wv is not None and bv is not None:
                if primary == "max_drawdown_pct":
                    beats_baseline = float(wv) < float(bv)
                else:
                    beats_baseline = float(wv) > float(bv)

        scorecard["regimes"].append(
            {
                "regime": rw["regime"],
                "label": rw.get("label"),
                "date_range": rw["date_range"],
                "winner_id": winner,
                "beats_baseline": beats_baseline,
                "ranking": [r["id"] for r in rows],
                "scenarios": rows,
            }
        )

    out = ROOT / "data/state/analyst_regime_scorecard_latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(scorecard, f, indent=2)
    print(f"ANALYST-OPT regime scorecard OK regimes={len(scorecard['regimes'])} wrote {out}")
    for rg in scorecard["regimes"]:
        print(f"  {rg['regime']}: winner={rg['winner_id']} beats_baseline={rg['beats_baseline']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())