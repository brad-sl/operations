#!/usr/bin/env python3
"""Run regime windows from regime pack → scorecard JSON."""
from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.run_scenario_leaderboard import load_pack, run_scenario, _rank_key
from phase6.research.usdc_carry_backtest import usdc_carry_scenario_row
from phase6.research.regime_strategy_optimizer import pick_optimal_strategy


def main() -> int:
    parser = argparse.ArgumentParser(description="Regime scorecard with USDC carry leg")
    parser.add_argument(
        "--pack",
        type=Path,
        default=ROOT / "phase6/research/scenarios/regime_quad_defensive.json",
        help="Regime pack with regime_windows + scenarios (default: regime_quad_defensive)",
    )
    args = parser.parse_args()
    template_path = args.pack
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

        rows.append(usdc_carry_scenario_row(rw["date_range"]))

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

        optimal = pick_optimal_strategy(rows, rw["date_range"])

        scorecard["regimes"].append(
            {
                "regime": rw["regime"],
                "label": rw.get("label"),
                "date_range": rw["date_range"],
                "winner_id": winner,
                "beats_baseline": beats_baseline,
                "ranking": [r["id"] for r in rows],
                "scenarios": rows,
                "usdc_optimal": optimal,
                "optimal_strategy_id": optimal.get("optimal_strategy_id"),
            }
        )

    out = ROOT / "data/state/analyst_regime_scorecard_latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(scorecard, f, indent=2)
    print(f"ANALYST-OPT regime scorecard OK regimes={len(scorecard['regimes'])} wrote {out}")
    for rg in scorecard["regimes"]:
        opt = rg.get("optimal_strategy_id") or "?"
        usdc = rg.get("usdc_optimal") or {}
        print(
            f"  {rg['regime']}: dd_winner={rg['winner_id']} "
            f"optimal={opt} ann={usdc.get('optimal_annualized_return_pct')}% "
            f"alt_beats_usdc={usdc.get('alt_beats_usdc_carry')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())