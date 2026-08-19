#!/usr/bin/env python3
"""Apply analyst_regime_scorecard_latest.json winners → config/regime_knob_map.json."""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.scenario_knobs import ScenarioKnobs
from phase6.core.usdc_benchmark import beats_usdc_hurdle

SCORECARD = ROOT / "data/state/analyst_regime_scorecard_latest.json"
KNOB_MAP = ROOT / "config/regime_knob_map.json"
SCENARIO_PACKS = [
    ROOT / "phase6/research/scenarios/r2_defensive_sharpe_gate.json",
    ROOT / "phase6/research/scenarios/regime_quad_defensive.json",
    ROOT / "phase6/research/scenarios/r1_arch4_smoke_three.json",
    ROOT / "phase6/research/scenarios/regime_quad_template.json",
]

# scorecard regime "recent" → overlay key "transition"
REGIME_KEY = {"recent": "transition"}


def load_scenario_index() -> dict:
    idx = {}
    for path in SCENARIO_PACKS:
        if not path.exists():
            continue
        pack = json.loads(path.read_text())
        for sc in pack.get("scenarios") or []:
            idx[sc["id"]] = (sc, pack)
    return idx


def knobs_for_scenario(scenario_id: str, idx: dict) -> ScenarioKnobs | None:
    hit = idx.get(scenario_id)
    if not hit:
        return None
    sc, pack = hit
    return ScenarioKnobs.from_scenario(sc, pack)


def entry_from_usdc_park(regime: str, rg: dict, optimal: dict) -> dict:
    from phase6.core.usdc_benchmark import load_usdc_apy_pct, usdc_standdown_overlay

    dr = rg.get("date_range") or {}
    ann = optimal.get("optimal_annualized_return_pct") or load_usdc_apy_pct()
    best_alt = optimal.get("best_alt_strategy_id")
    best_alt_ann = optimal.get("best_alt_annualized_return_pct")
    note = (
        f"scorecard {regime} optimal=usdc_hold ann={ann}% "
        f"best_alt={best_alt} alt_ann={best_alt_ann}% "
        f"(max annualized vs USDC carry)"
    )
    return {
        "scenario_id": "usdc_hold",
        "strategy_mode": "usdc_park",
        "note": note,
        "live_overlay": usdc_standdown_overlay(),
        "arch4_params": {"use_rotation": False, "rebal_freq": 7},
        "usdc_benchmark": {
            "beats_usdc_benchmark": True,
            "annualized_return_pct": ann,
            "usdc_apy_pct": load_usdc_apy_pct(),
            "reason": "optimal_strategy",
        },
        "scorecard": {
            "winner_id": rg.get("winner_id"),
            "optimal_strategy_id": "usdc_hold",
            "beats_baseline": rg.get("beats_baseline"),
            "date_range": dr,
            "usdc_optimal": optimal,
        },
    }


def entry_from_winner(scenario_id: str, idx: dict, regime: str, rg: dict) -> dict:
    knobs = knobs_for_scenario(scenario_id, idx)
    if not knobs:
        return {
            "scenario_id": scenario_id,
            "note": f"scorecard winner; no pack definition for {scenario_id}",
            "live_overlay": {},
            "arch4_params": {"use_rotation": True, "rebal_freq": 7},
        }

    overlay = knobs.to_live_config_overlay()
    arch4 = knobs.to_arch4_params()
    winner_row = next((s for s in rg.get("scenarios") or [] if s.get("id") == scenario_id), {})
    metrics = winner_row.get("metrics") or {}
    usdc = beats_usdc_hurdle(
        metrics.get("total_return_pct"),
        rg.get("date_range"),
    )

    note = (
        f"scorecard {regime} winner={scenario_id} "
        f"return_pct={metrics.get('total_return_pct')} max_dd={metrics.get('max_drawdown_pct')} "
        f"ann={usdc.get('annualized_return_pct')}% usdc_hurdle={usdc.get('usdc_apy_pct')}% "
        f"beats_usdc={usdc.get('beats_usdc_benchmark')}"
    )

    live = {
        "global_settings.rebalance_cap_usd": overlay["global_settings.rebalance_cap_usd"],
    }
    if regime == "bear":
        live["global_settings.rebalance_cap_usd"] = min(
            float(overlay["global_settings.rebalance_cap_usd"]), 120.0
        )
        live["risk_management.sl_max_pct"] = 0.04
    elif regime == "flat":
        live["global_settings.rebalance_cap_usd"] = min(
            float(overlay["global_settings.rebalance_cap_usd"]), 140.0
        )
    elif regime == "bull":
        live["global_settings.rebalance_cap_usd"] = float(overlay["global_settings.rebalance_cap_usd"])

    return {
        "scenario_id": scenario_id,
        "note": note,
        "live_overlay": live,
        "arch4_params": {
            "use_rotation": arch4["use_rotation"],
            "rebal_freq": arch4["rebal_freq"],
        },
        "usdc_benchmark": usdc,
        "scorecard": {
            "winner_id": scenario_id,
            "optimal_strategy_id": rg.get("optimal_strategy_id"),
            "beats_baseline": rg.get("beats_baseline"),
            "date_range": rg.get("date_range"),
            "usdc_optimal": rg.get("usdc_optimal"),
        },
    }


def main() -> int:
    if not SCORECARD.exists():
        print(f"missing scorecard: {SCORECARD}", file=sys.stderr)
        return 1

    scorecard = json.loads(SCORECARD.read_text())
    idx = load_scenario_index()
    knob_map = json.loads(KNOB_MAP.read_text()) if KNOB_MAP.exists() else {"schema_version": "1", "regimes": {}}
    regimes_out = deepcopy(knob_map.get("regimes") or {})
    preserved: list[str] = []

    for rg in scorecard.get("regimes") or []:
        regime = rg.get("regime")
        key = REGIME_KEY.get(regime, regime)
        if key not in ("bull", "bear", "flat", "transition"):
            continue
        # Operator thaw / manual latch (e.g. flat option B) — do not clobber
        existing = regimes_out.get(key) or {}
        ov = existing.get("operator_override") or {}
        if ov.get("protect", True) and ov.get("reason"):
            # Keep live overlay + mode; attach freshest scorecard under research_only
            refreshed = deepcopy(existing)
            refreshed["scorecard_research_only"] = {
                "winner_id": rg.get("winner_id"),
                "optimal_strategy_id": rg.get("optimal_strategy_id") or rg.get("winner_id"),
                "beats_baseline": rg.get("beats_baseline"),
                "date_range": rg.get("date_range"),
                "usdc_optimal": rg.get("usdc_optimal"),
                "scorecard_generated_at": scorecard.get("generated_at"),
            }
            refreshed["note"] = (
                f"{existing.get('note') or ''} | scorecard would prefer "
                f"{rg.get('optimal_strategy_id') or rg.get('winner_id')} "
                f"(operator_override protected)"
            ).strip(" |")
            regimes_out[key] = refreshed
            preserved.append(key)
            continue
        winner = rg.get("winner_id")
        strategy_id = rg.get("optimal_strategy_id") or winner
        if not strategy_id or rg.get("scenarios") and rg["scenarios"][0].get("error"):
            continue
        optimal = rg.get("usdc_optimal") or {}
        if strategy_id == "usdc_hold":
            regimes_out[key] = entry_from_usdc_park(regime, rg, optimal)
        else:
            regimes_out[key] = entry_from_winner(strategy_id, idx, regime, rg)

    knob_map["regimes"] = regimes_out
    knob_map["updated_from_scorecard_at"] = datetime.now(timezone.utc).isoformat()
    knob_map["scorecard_generated_at"] = scorecard.get("generated_at")
    knob_map["operator_overrides_preserved"] = preserved
    KNOB_MAP.write_text(json.dumps(knob_map, indent=2))
    print(f"regime_knob_map OK keys={list(regimes_out.keys())} preserved={preserved} wrote {KNOB_MAP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())