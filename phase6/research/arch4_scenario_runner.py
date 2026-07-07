"""
Run a single ANALYST-OPT scenario through Path B (ARCH-4 isolation harness).
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from phase6.backtest.metrics import calculate_max_drawdown, calculate_sharpe
from phase6.research.scenario_knobs import ScenarioKnobs

for _lg in ("phase6.core.allocator", "phase6.scripts.deploy_capital", "phase6.core.evaluation"):
    logging.getLogger(_lg).setLevel(logging.ERROR)


def _bar_date(ts: str) -> Optional[date]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
    except Exception:
        try:
            return date.fromisoformat(ts[:10])
        except Exception:
            return None


def clip_ohlcv_data(
    data: Dict[str, List[Dict]],
    start: Optional[date],
    end: Optional[date],
) -> Tuple[Dict[str, List[Dict]], Optional[dict]]:
    """Filter bars to [start, end]. Returns (clipped, window_meta)."""
    if start is None and end is None:
        return data, None
    clipped: Dict[str, List[Dict]] = {}
    for pair, bars in data.items():
        kept = []
        for b in bars:
            d = _bar_date(str(b.get("timestamp", "")))
            if d is None:
                continue
            if start and d < start:
                continue
            if end and d > end:
                continue
            kept.append(b)
        if kept:
            clipped[pair] = kept
    meta = {
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "bars_min": min(len(v) for v in clipped.values()) if clipped else 0,
    }
    return clipped, meta


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
        "rebalance_count": int(m.get("trade_count", 0)),
        "avg_pairs_held": round(float(m.get("avg_exposure_pct", 0)) / 20.0, 2),
        "engine": "arch4",
        "strategy": m.get("strategy", ""),
        "avg_exposure_pct": m.get("avg_exposure_pct"),
    }


def run_arch4_scenario(
    knobs: ScenarioKnobs,
    window_start: Optional[date] = None,
    window_end: Optional[date] = None,
) -> Dict[str, Any]:
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
    data, window_meta = clip_ohlcv_data(data, window_start, window_end)
    if window_meta and window_meta.get("bars_min", 0) < 30:
        return {
            "raw": {"error": "insufficient OHLCV in requested window"},
            "metrics": {
                "engine": "arch4",
                "total_return_pct": None,
                "sharpe_ratio": None,
                "max_drawdown_pct": None,
                "simulation_skipped": True,
                "reason": f"OHLCV bars in window: {window_meta.get('bars_min')}",
            },
            "basket": basket,
            "simulation_window": window_meta,
        }

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
    if window_meta:
        metrics["simulation_window"] = window_meta
    return {"raw": raw, "metrics": metrics, "basket": basket, "simulation_window": window_meta}