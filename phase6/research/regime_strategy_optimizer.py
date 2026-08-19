"""Per-regime strategy choice: max(alt scenarios, USDC carry) on annualized return."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from phase6.core.usdc_benchmark import annualize_return_pct


def annualized_from_row(row: Dict[str, Any], date_range: Optional[Dict[str, str]]) -> Optional[float]:
    m = row.get("metrics") or {}
    if m.get("simulation_skipped"):
        return None
    if m.get("annualized_return_pct") is not None:
        return float(m["annualized_return_pct"])
    tr = m.get("total_return_pct")
    if tr is None:
        return None
    days = int(m.get("window_days") or 30)
    if date_range and not m.get("window_days"):
        from phase6.research.usdc_carry_backtest import _window_days

        days = _window_days(date_range)
    return annualize_return_pct(float(tr), days)


def pick_optimal_strategy(
    scenario_rows: List[Dict[str, Any]],
    date_range: Dict[str, str],
) -> Dict[str, Any]:
    """
    Choose strategy with highest annualized return among valid rows (includes usdc_hold).
    """
    candidates: List[Tuple[str, float, Dict[str, Any]]] = []
    for row in scenario_rows:
        if row.get("error"):
            continue
        ann = annualized_from_row(row, date_range)
        if ann is None:
            continue
        candidates.append((row["id"], ann, row))

    if not candidates:
        return {
            "optimal_strategy_id": None,
            "optimal_annualized_return_pct": None,
            "optimal_is_usdc": False,
            "reason": "no valid scenarios",
        }

    candidates.sort(key=lambda x: x[1], reverse=True)
    best_id, best_ann, best_row = candidates[0]
    usdc_row = next((r for r in scenario_rows if r.get("id") == "usdc_hold"), None)
    usdc_ann = annualized_from_row(usdc_row, date_range) if usdc_row else None

    alt_candidates = [c for c in candidates if c[0] != "usdc_hold"]
    best_alt = alt_candidates[0] if alt_candidates else None

    return {
        "optimal_strategy_id": best_id,
        "optimal_annualized_return_pct": round(best_ann, 4),
        "optimal_is_usdc": best_id == "usdc_hold",
        "optimal_metrics": best_row.get("metrics"),
        "usdc_annualized_return_pct": usdc_ann,
        "best_alt_strategy_id": best_alt[0] if best_alt else None,
        "best_alt_annualized_return_pct": round(best_alt[1], 4) if best_alt else None,
        "alt_beats_usdc_carry": bool(best_alt and usdc_ann is not None and best_alt[1] > usdc_ann),
        "comparison_metric": "annualized_return_pct",
    }