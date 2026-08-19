"""USDC / risk-free hurdle for deploy vs stand-down (Coinbase USDC APY)."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

from phase6.core.paths import PROJECT_ROOT

DEFAULT_USDC_APY_PCT = 3.5
BENCHMARK_PATH = PROJECT_ROOT / "config/risk_free_benchmark.json"


def load_usdc_apy_pct() -> float:
    if BENCHMARK_PATH.exists():
        try:
            data = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
            return float(data.get("usdc_apy_pct", DEFAULT_USDC_APY_PCT))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return DEFAULT_USDC_APY_PCT


def _window_days(date_range: Optional[Dict[str, str]]) -> int:
    if not date_range:
        return 30
    try:
        start = date.fromisoformat(str(date_range["start"])[:10])
        end = date.fromisoformat(str(date_range["end"])[:10])
        return max(1, (end - start).days)
    except (KeyError, ValueError, TypeError):
        return 30


def annualize_return_pct(total_return_pct: float, window_days: int) -> float:
    """Compound annualized return from window total return %."""
    window_days = max(1, int(window_days))
    factor = 1.0 + float(total_return_pct) / 100.0
    if factor <= 0:
        return -100.0
    ann = (factor ** (365.0 / window_days) - 1.0) * 100.0
    return round(ann, 4)


def beats_usdc_hurdle(
    total_return_pct: Optional[float],
    date_range: Optional[Dict[str, str]],
    *,
    apy_pct: Optional[float] = None,
) -> Dict[str, Any]:
    hurdle = apy_pct if apy_pct is not None else load_usdc_apy_pct()
    if total_return_pct is None:
        return {
            "beats_usdc_benchmark": False,
            "annualized_return_pct": None,
            "usdc_apy_pct": hurdle,
            "reason": "missing return",
        }
    days = _window_days(date_range)
    ann = annualize_return_pct(float(total_return_pct), days)
    beats = ann >= hurdle
    return {
        "beats_usdc_benchmark": beats,
        "annualized_return_pct": ann,
        "window_days": days,
        "window_total_return_pct": float(total_return_pct),
        "usdc_apy_pct": hurdle,
        "reason": "ok" if beats else "annualized below USDC APY",
    }


def usdc_standdown_overlay() -> Dict[str, Any]:
    """Overlay keys: minimal deploy — treat as USDC-preferred period."""
    return {
        "global_settings.rebalance_cap_usd": 0.0,
        "global_settings.risk_free_preference": "USDC",
        "global_settings.risk_free_apy_pct": load_usdc_apy_pct(),
    }