"""
Run a single ANALYST-OPT scenario through Path B (ARCH-4 isolation harness).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from phase6.backtest.metrics import calculate_max_drawdown, calculate_sharpe
from phase6.research.scenario_knobs import ScenarioKnobs

# Quiet allocator/deploy during batch leaderboard runs
for _lg in ("phase6.core.allocator", "phase6.scripts.deploy_capital", "phase6.core.evaluation"):
    logging.getLogger(_lg).setLevel(logging.ERROR)


def resolve_basket(knobs: ScenarioKnobs, load_ohlcv, pair_map: dict) -> List[str]:
    core = ["btc", "eth", "sol", "xrp", "doge"]
    basket: List[str] = []
    for short in core:
        p = pair_map.get(short)
        if p and load_ohlcv(p):
            basket.append(p)
    if knobs.enable_pair_expansion and knobs.candidate_universe:
        for p in knobs.candidate_universe:
            if load_ohlcv(p) and p not in basket:
                basket.append(p)
    return basket


def arch4_metrics_from_result(raw: Dict[str, Any], initial: float) -> Dict[str, Any]:
    m = raw.get("metrics") or {}
    curve = raw.get("equity_curve") or []
    max_dd = m.get("max_dd_pct")
    if max_dd is None and curve:
        max_dd = calculate_max_drawdown(curve)
    sharpe = calculate_sharpe(curve) if len(curve) > 2 else 0.0
    return {
        "final_equity": round(float(raw.get("final_equity", m.get("final", initial))), 2),
        "total_return_pct": round(float(m.get("return_pct", 0)), 2),
        "max_drawdown_pct": round(float(max_dd or 0), 2),
        "sharpe_ratio": round(sharpe, 3),
        "total_trades": int(raw.get("trade_count", m.get("trade_count", 0))),
        "rebalance_count": int(m.get("trade_count", 0)),  # step trades proxy
        "avg_pairs_held": round(float(m.get("avg_exposure_pct", 0)) / 20.0, 2),  # display proxy
        "engine": "arch4",
        "strategy": m.get("strategy", ""),
        "avg_exposure_pct": m.get("avg_exposure_pct"),
    }


def run_arch4_scenario(knobs: ScenarioKnobs) -> Dict[str, Any]:
    from phase6.scripts.backtest_arch4_isolation_harness import (
        PAIR_MAP,
        load_all_data,
        load_ohlcv,
        run_arch4_backtest,
    )

    basket = resolve_basket(knobs, load_ohlcv, PAIR_MAP)
    if len(basket) < 3:
        raise RuntimeError(f"arch4: insufficient OHLCV for scenario {knobs.scenario_id}")

    data = load_all_data(basket)
    params = knobs.to_arch4_params()
    raw = run_arch4_backtest(
        data,
        initial=params["initial_capital"],
        rebal_freq=params["rebal_freq"],
        use_rotation=params["use_rotation"],
    )
    if raw.get("error"):
        raise RuntimeError(raw["error"])
    metrics = arch4_metrics_from_result(raw, params["initial_capital"])
    return {"raw": raw, "metrics": metrics, "basket": basket}