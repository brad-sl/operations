#!/usr/bin/env python3
"""Print human-readable regime × USDC optimal assessment from latest scorecard."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SCORECARD = ROOT / "data/state/analyst_regime_scorecard_latest.json"
OUT = ROOT / "data/state/analyst_regime_usdc_assessment_latest.json"


def main() -> int:
    if not SCORECARD.exists():
        print(f"missing {SCORECARD}; run run_regime_scorecard.py first", file=sys.stderr)
        return 1

    sc = json.loads(SCORECARD.read_text(encoding="utf-8"))
    lines = []
    summary_rows = []

    for rg in sc.get("regimes") or []:
        opt = rg.get("usdc_optimal") or {}
        lines.append(f"## {rg.get('regime')} ({rg.get('label')})")
        lines.append(f"- Window: {rg.get('date_range')}")
        lines.append(f"- DD winner (max_drawdown): **{rg.get('winner_id')}**")
        lines.append(
            f"- **Optimal (max ann. return):** **{opt.get('optimal_strategy_id')}** "
            f"@ {opt.get('optimal_annualized_return_pct')}% ann"
        )
        lines.append(
            f"- Best alt: {opt.get('best_alt_strategy_id')} @ {opt.get('best_alt_annualized_return_pct')}% ann"
        )
        lines.append(f"- USDC carry @ {opt.get('usdc_annualized_return_pct')}% ann")
        lines.append(f"- Alt beats USDC carry: **{opt.get('alt_beats_usdc_carry')}**")
        lines.append("")

        summary_rows.append(
            {
                "regime": rg.get("regime"),
                "date_range": rg.get("date_range"),
                "dd_winner_id": rg.get("winner_id"),
                "optimal_strategy_id": opt.get("optimal_strategy_id"),
                "optimal_annualized_return_pct": opt.get("optimal_annualized_return_pct"),
                "best_alt_strategy_id": opt.get("best_alt_strategy_id"),
                "best_alt_annualized_return_pct": opt.get("best_alt_annualized_return_pct"),
                "usdc_annualized_return_pct": opt.get("usdc_annualized_return_pct"),
                "alt_beats_usdc_carry": opt.get("alt_beats_usdc_carry"),
                "recommended_action": (
                    "deploy_alt"
                    if opt.get("alt_beats_usdc_carry")
                    else "usdc_park"
                ),
            }
        )

    deploy_count = sum(1 for r in summary_rows if r["recommended_action"] == "deploy_alt")
    park_count = len(summary_rows) - deploy_count

    report = {
        "generated_from": str(SCORECARD),
        "scorecard_generated_at": sc.get("generated_at"),
        "usdc_apy_config": "config/risk_free_benchmark.json",
        "summary": {
            "regimes": len(summary_rows),
            "deploy_alt_regimes": deploy_count,
            "usdc_park_regimes": park_count,
        },
        "regimes": summary_rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("REGIME × USDC ASSESSMENT")
    print("=" * 60)
    print("\n".join(lines))
    print(f"Summary: deploy_alt={deploy_count} usdc_park={park_count} → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())