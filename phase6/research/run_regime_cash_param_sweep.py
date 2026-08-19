#!/usr/bin/env python3
"""
RC-04: Param sweep over regime_cash_policy detector + util knobs.

Uses real BTC OHLCV (optional live merge). Scores each candidate by:
  - fraction of days park vs deploy
  - proxy return: park days * USDC daily + deploy days * scorecard bull alt daily proxy
  - risk days (days classified bear while allow_new_buys would be true — should be 0 for good policies)

Does NOT write live config. Writes data/state/regime_cash_param_sweep_latest.json
and optional suggestions only.
"""
from __future__ import annotations

import itertools
import json
import sys
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.usdc_benchmark import load_usdc_apy_pct
from phase6.research.regime_detector import _load_btc_closes, _merge_live_close, detect_regime

OUT = ROOT / "data/state/regime_cash_param_sweep_latest.json"
POLICY = ROOT / "config/regime_cash_policy.json"
USDC_APY = load_usdc_apy_pct()


def _classify(ret_pct: float, bull: float, bear: float, flat: float) -> str:
    if ret_pct >= bull:
        return "bull"
    if ret_pct <= bear:
        return "bear"
    if abs(ret_pct) <= flat:
        return "flat"
    return "transition"


def _rolling_returns(closes: List[Tuple[date, float]], lookback: int) -> List[Tuple[date, float]]:
    """For each end day with enough history, (end, ret_pct)."""
    if len(closes) < lookback + 2:
        return []
    out: List[Tuple[date, float]] = []
    by_d = {d: c for d, c in closes}
    days = [d for d, _ in closes]
    for i in range(lookback, len(days)):
        end = days[i]
        start = end - timedelta(days=lookback)
        window = [(d, by_d[d]) for d in days if start <= d <= end]
        if len(window) < 5:
            continue
        p0, p1 = window[0][1], window[-1][1]
        ret = (p1 / p0 - 1.0) * 100.0 if p0 > 0 else 0.0
        out.append((end, ret))
    return out


def score_thresholds(
    rolling: List[Tuple[date, float]],
    bull: float,
    bear: float,
    flat: float,
    park_regimes: set,
    usdc_daily: float,
    deploy_daily: float,
) -> Dict[str, Any]:
    n = len(rolling) or 1
    counts = {"bull": 0, "bear": 0, "flat": 0, "transition": 0}
    park_days = 0
    deploy_days = 0
    risk_deploy_in_bear = 0
    for _, ret in rolling:
        r = _classify(ret, bull, bear, flat)
        counts[r] = counts.get(r, 0) + 1
        if r in park_regimes:
            park_days += 1
        else:
            deploy_days += 1
            if r == "bear":
                risk_deploy_in_bear += 1

    proxy_return = park_days * usdc_daily + deploy_days * deploy_daily
    # Prefer higher proxy, fewer risk days, more park in non-bull
    non_bull = counts["bear"] + counts["flat"] + counts["transition"]
    park_on_non_bull = park_days  # park_regimes covers non-bull by default
    score = proxy_return - 0.5 * risk_deploy_in_bear  # heavy penalty
    return {
        "bull_return_pct": bull,
        "bear_return_pct": bear,
        "flat_abs_pct": flat,
        "counts": counts,
        "park_days": park_days,
        "deploy_days": deploy_days,
        "risk_deploy_in_bear": risk_deploy_in_bear,
        "proxy_return_pct_window": round(proxy_return * 100, 4),
        "score": round(score * 100, 4),
        "non_bull_days": non_bull,
        "park_fraction": round(park_days / n, 4),
    }


def main() -> int:
    pol = json.loads(POLICY.read_text()) if POLICY.exists() else {}
    det = pol.get("detector") or {}
    lookback = int(det.get("lookback_days") or 30)

    closes = _load_btc_closes()
    closes, live_meta = _merge_live_close(closes)
    rolling = _rolling_returns(closes, lookback)

    usdc_daily = (USDC_APY / 100.0) / 365.0
    # Proxy deploy edge: modest positive only when truly bull; use 12% ann ≈ scorecard-ish mid
    deploy_ann = 12.0
    deploy_daily = (deploy_ann / 100.0) / 365.0

    # Grid (bounded for continuous runs)
    bulls = [10.0, 12.0, 15.0, 18.0]
    bears = [-8.0, -10.0, -12.0, -15.0]
    flats = [5.0, 8.0, 10.0]
    park_regimes = {"bear", "flat", "transition", "unknown"}

    rows: List[Dict[str, Any]] = []
    for bull, bear, flat in itertools.product(bulls, bears, flats):
        if bear >= 0 or bull <= 0 or flat <= 0:
            continue
        rows.append(
            score_thresholds(rolling, bull, bear, flat, park_regimes, usdc_daily, deploy_daily)
        )

    rows.sort(key=lambda r: (r["risk_deploy_in_bear"], -r["score"]))
    best = rows[0] if rows else {}

    # Current live detection with policy thresholds
    live = detect_regime(
        lookback_days=lookback,
        bull_return_pct=float(det.get("bull_return_pct", 15)),
        bear_return_pct=float(det.get("bear_return_pct", -10)),
        flat_abs_pct=float(det.get("flat_abs_pct", 8)),
        use_live_price=True,
    )

    # Suggestions: only if best clearly safer and better than current on score
    current = score_thresholds(
        rolling,
        float(det.get("bull_return_pct", 15)),
        float(det.get("bear_return_pct", -10)),
        float(det.get("flat_abs_pct", 8)),
        park_regimes,
        usdc_daily,
        deploy_daily,
    )
    suggestions: Dict[str, Any] = {
        "auto_apply": False,
        "reason": "manual/gate review required — never auto-write policy from sweep alone",
        "candidate_detector": {
            "bull_return_pct": best.get("bull_return_pct"),
            "bear_return_pct": best.get("bear_return_pct"),
            "flat_abs_pct": best.get("flat_abs_pct"),
        }
        if best
        else {},
        "improves_score": bool(best and best.get("score", 0) > current.get("score", 0)),
        "current_score": current.get("score"),
        "best_score": best.get("score"),
    }

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_days": lookback,
        "usdc_apy_pct": USDC_APY,
        "deploy_proxy_ann_pct": deploy_ann,
        "live_merge": live_meta,
        "rolling_points": len(rolling),
        "live_detection": live,
        "current_policy_score": current,
        "best": best,
        "top5": rows[:5],
        "suggestions": suggestions,
        "schema": "regime_cash_param_sweep_v1",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(
        f"REGIME-CASH sweep OK points={len(rolling)} best_score={best.get('score')} "
        f"live_regime={live.get('regime')} btc_ret={live.get('btc_return_pct')} → {OUT}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
