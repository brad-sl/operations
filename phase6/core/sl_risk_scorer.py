#!/usr/bin/env python3
# See docs/DATA_FLOW_AND_LOCATIONS.md and phase6/core/paths.py for paths, state, config hygiene and drift prevention.
# All code must derive PROJECT_ROOT via paths.py and avoid absolute hardcodes.

"""
Phase 6 SL Risk Scorer (minimal implementation to support intelligence report + planning).

Provides get_all_sl_risks(basket, price_map) and get_sl_risk(pair) for use by
generate_trading_intelligence_report.py and potentially stop_loss_manager.

Heuristic (real-data based where possible):
- Prefers RSI from rsi_cache.json (low RSI => higher SL risk due to potential reversal/vol)
- Falls back to LOW if no data.
- Future: can incorporate price volatility, ATR, funding, etc.

This unblocks the twice-daily intelligence cron and analyst proposals.
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional

# Canonical cache location (relative to project root)
RSI_CACHE_PATH = Path("data/state/rsi_cache.json")
LIVE_STATE_PATH = Path("data/state/phase6_live_state.json")

def _load_rsi_map() -> Dict[str, float]:
    try:
        if RSI_CACHE_PATH.exists():
            data = json.loads(RSI_CACHE_PATH.read_text())
            rsi_section = data.get("rsi", {}) or data.get("data", {}).get("rsi", {})
            out = {}
            for k, v in rsi_section.items():
                if isinstance(v, dict):
                    val = v.get("rsi") or v.get("value")
                else:
                    val = v
                if val is not None:
                    try:
                        out[k] = float(val)
                    except (TypeError, ValueError):
                        pass
            return out
    except Exception:
        pass
    return {}


def _load_stoch_map() -> Dict[str, Optional[float]]:
    """Load StochRSI %K values when available (longer-term data)."""
    try:
        if RSI_CACHE_PATH.exists():
            data = json.loads(RSI_CACHE_PATH.read_text())
            section = data.get("rsi", {}) or data.get("data", {}).get("rsi", {})
            out: Dict[str, Optional[float]] = {}
            for k, v in section.items():
                if isinstance(v, dict):
                    sk = v.get("stoch_k")
                    if sk is not None:
                        try:
                            out[k] = float(sk)
                        except (TypeError, ValueError):
                            out[k] = None
                    else:
                        out[k] = None
            return out
    except Exception:
        pass
    return {}

def get_sl_risk(pair: str, current_price: Optional[float] = None, **kwargs) -> Dict[str, Any]:
    """Return standardized risk dict for one pair.
    Supports longer-term (100-point) RSI + StochRSI %K when available.
    Low Stoch %K (<20-30) boosts reversal risk (oversold extreme in recent range).
    """
    rsi_map = _load_rsi_map()
    stoch_map = _load_stoch_map()
    rsi = rsi_map.get(pair)
    stoch_k = stoch_map.get(pair)

    if rsi is not None or stoch_k is not None:
        # Base from RSI if present
        if rsi is not None:
            if rsi < 25:
                level = "CRITICAL"
                score = 0.85
                reason = f"very low RSI ({rsi:.1f}) — high reversal / SL trigger risk"
            elif rsi < 35:
                level = "HIGH"
                score = 0.65
                reason = f"low RSI ({rsi:.1f}) — elevated SL risk"
            elif rsi > 75:
                level = "MEDIUM"
                score = 0.45
                reason = f"very high RSI ({rsi:.1f}) — potential pullback"
            elif rsi > 65:
                level = "MEDIUM"
                score = 0.35
                reason = f"high RSI ({rsi:.1f})"
            else:
                level = "LOW"
                score = 0.2
                reason = f"neutral RSI ({rsi:.1f}) (longer-term 100pt window)"
        else:
            level = "LOW"
            score = 0.25
            reason = "neutral (stoch only)"

        # StochRSI boost for reversal risk (low stoch_k = oversold in recent window)
        if stoch_k is not None:
            if stoch_k < 20:
                level = "HIGH" if level in ("LOW", "MEDIUM") else level
                score = max(score, 0.75)
                reason += f" | very low Stoch %K ({stoch_k:.1f}) — strong reversal risk (longer-term)"
            elif stoch_k < 30:
                if level == "LOW":
                    level = "MEDIUM"
                score = max(score, 0.55)
                reason += f" | low Stoch %K ({stoch_k:.1f}) (longer-term)"

            reason += f" stoch_k={stoch_k:.1f}"

        return {
            "level": level,
            "risk_score": round(score, 2),
            "rsi": round(rsi, 1) if rsi is not None else None,
            "stoch_k": round(stoch_k, 1) if stoch_k is not None else None,
            "reason": reason,
            "source": "rsi_cache_longer_stoch"
        }

    # No RSI data
    return {
        "level": "LOW",
        "risk_score": 0.25,
        "rsi": None,
        "stoch_k": None,
        "reason": "no RSI/Stoch data available (default LOW)",
        "source": "default"
    }


def get_adaptive_sl_pct(
    pair: str,
    base_pct: float = 0.03,
    regime_bias: float = 0.5,
    risk_data: Optional[Dict[str, Any]] = None,
    min_pct: float = 0.015,
    max_pct: float = 0.05,
) -> float:
    """
    Compute risk-aware / adaptive stop loss percentage.
    - Tighter stops for HIGH/CRITICAL risk (from RSI) or risk-off regime.
    - Slightly wider for LOW risk / risk-on.
    - Anchors to base_pct from config (default 3%).
    Used by StopLossManager to avoid fixed 3% always.
    """
    if risk_data is None:
        risk_data = get_sl_risk(pair)

    level = risk_data.get("level", "LOW")
    risk_score = risk_data.get("risk_score", 0.25)

    multiplier = 1.0

    # Risk level adjustment (tighter on danger)
    if level == "CRITICAL":
        multiplier *= 0.60
    elif level == "HIGH":
        multiplier *= 0.75
    elif level == "MEDIUM":
        multiplier *= 0.90
    # LOW keeps ~1.0 or slight widen

    # Regime bias (from intelligence brief / Polymarket)
    # <0.4 = risk-off / conservative -> tighter protection
    if regime_bias < 0.4:
        multiplier *= 0.85
    elif regime_bias > 0.6:
        multiplier *= 1.10  # allow a bit more room in strong risk-on

    # Blend with risk_score for finer control
    multiplier = multiplier * (1.0 - (risk_score - 0.2) * 0.5)  # slight damp

    adaptive = base_pct * max(0.5, min(1.5, multiplier))
    adaptive = max(min_pct, min(max_pct, adaptive))
    return round(adaptive, 4)

def get_all_sl_risks(basket: List[str], price_map: Optional[Dict[str, float]] = None) -> Dict[str, Dict[str, Any]]:
    """
    Return risk assessment for entire basket.
    price_map currently unused (reserved for price/vol based enhancement).
    """
    if price_map is None:
        price_map = {}
    return {pair: get_sl_risk(pair, price_map.get(pair)) for pair in basket}

# Convenience for other consumers
__all__ = ["get_sl_risk", "get_all_sl_risks", "get_sl_risks"]  # alias

def get_sl_risks(basket: List[str], price_map: Optional[Dict[str, float]] = None) -> Dict[str, Dict[str, Any]]:
    """Alias for get_all_sl_risks (some older references)."""
    return get_all_sl_risks(basket, price_map)

if __name__ == "__main__":
    # Self test
    test_basket = ["BTC-USD", "ETH-USD", "SOL-USD"]
    risks = get_all_sl_risks(test_basket)
    print("SL Risk Scorer self-test:")
    for p, r in risks.items():
        print(f"  {p}: {r['level']} (score={r['risk_score']}) | {r.get('reason')}")
    print("OK")
