"""Synthetic USDC carry scenario for Path B regime / leaderboard comparisons."""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

from phase6.core.usdc_benchmark import annualize_return_pct, load_usdc_apy_pct


def _window_days(date_range: Optional[Dict[str, str]]) -> int:
    if not date_range:
        return 30
    try:
        start = date.fromisoformat(str(date_range["start"])[:10])
        end = date.fromisoformat(str(date_range["end"])[:10])
        return max(1, (end - start).days)
    except (KeyError, ValueError, TypeError):
        return 30


def usdc_window_total_return_pct(
    date_range: Optional[Dict[str, str]],
    *,
    apy_pct: Optional[float] = None,
) -> float:
    """Compound USDC APY over the backtest window (no trading risk)."""
    apy = apy_pct if apy_pct is not None else load_usdc_apy_pct()
    days = _window_days(date_range)
    factor = (1.0 + float(apy) / 100.0) ** (days / 365.0)
    return round((factor - 1.0) * 100.0, 4)


def usdc_carry_metrics(
    date_range: Optional[Dict[str, str]],
    *,
    initial_capital: float = 1000.0,
    apy_pct: Optional[float] = None,
) -> Dict[str, Any]:
    apy = apy_pct if apy_pct is not None else load_usdc_apy_pct()
    days = _window_days(date_range)
    total_ret = usdc_window_total_return_pct(date_range, apy_pct=apy)
    ann = annualize_return_pct(total_ret, days)
    final = round(initial_capital * (1.0 + total_ret / 100.0), 2)
    # Sharpe on constant daily yield — use annualized/ vol proxy for ranking only
    daily = (1.0 + apy / 100.0) ** (1.0 / 365.0) - 1.0
    sharpe_proxy = round((daily * 365) / 0.001, 3) if daily > 0 else 0.0

    return {
        "final_equity": final,
        "total_return_pct": total_ret,
        "annualized_return_pct": ann,
        "max_drawdown_pct": 0.0,
        "sharpe_ratio": sharpe_proxy,
        "total_trades": 0,
        "rebalance_count": 0,
        "avg_pairs_held": 0.0,
        "engine": "usdc_carry",
        "strategy": "usdc_hold",
        "usdc_apy_pct": apy,
        "window_days": days,
        "avg_exposure_pct": 0.0,
    }


def usdc_carry_scenario_row(date_range: Dict[str, str]) -> Dict[str, Any]:
    return {
        "id": "usdc_hold",
        "label": "USDC carry (Coinbase APY)",
        "engine": "usdc_carry",
        "metrics": usdc_carry_metrics(date_range),
        "basket_size": 0,
        "simulation_window": date_range,
    }