#!/usr/bin/env python3
"""
Correlate free hybrid shadow vs live X / canonical sentiment (read-only gates).

Gates (shadow promote readiness):
  - coverage_free: fraction pairs |score|>eps >= 0.5
  - coverage_overlap: pairs both free and x non-zero
  - sign_agreement: among overlap, fraction same sign (or either ~0)
  - spearman: if scipy available and n>=5; else pearson on ranks manual
  - not_anti: spearman > -0.2 (reject if strong anti-signal)

Writes data/state/free_vs_x_correlation_latest.json
Appends data/state/free_vs_x_correlation_history.jsonl
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from phase6.core.paths import (  # noqa: E402
    FREE_SENTIMENT_CACHE,
    FREE_VS_X_CORRELATION,
    SENTIMENT_CACHE,
    X_SENTIMENT_CACHE,
    load_trading_basket,
)

HISTORY = FREE_VS_X_CORRELATION.parent / "free_vs_x_correlation_history.jsonl"
EPS = 1e-6


def _load_scores(path: Path, kind: str) -> Dict[str, float]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    out: Dict[str, float] = {}
    if kind == "free":
        sent = data.get("sentiment") or {}
        for p, e in sent.items():
            if isinstance(e, dict):
                out[p] = float(e.get("sentiment_score") or 0.0)
            else:
                out[p] = float(e or 0.0)
    elif kind == "canonical":
        sent = data.get("sentiment") or data
        if isinstance(sent, dict) and "sentiment_score" not in str(list(sent.values())[:1]):
            # schema3
            if data.get("schema_version"):
                for p, e in (data.get("sentiment") or {}).items():
                    if isinstance(e, dict):
                        out[p] = float(e.get("sentiment_score") or 0.0)
                    else:
                        out[p] = float(e or 0.0)
            else:
                for p, e in sent.items():
                    if p in ("timestamp", "schema_version", "meta"):
                        continue
                    if isinstance(e, dict):
                        out[p] = float(e.get("sentiment_score", e.get("sentiment", 0.0)) or 0.0)
        else:
            for p, e in (data.get("sentiment") or {}).items():
                out[p] = float(e.get("sentiment_score") or 0.0) if isinstance(e, dict) else float(e or 0.0)
    else:  # x rich
        for p, e in data.items():
            if p in ("timestamp", "schema_version", "meta", "pairs"):
                continue
            if isinstance(e, dict) and ("sentiment" in e or "score" in e):
                out[p] = float(e.get("sentiment", e.get("score", 0.0)) or 0.0)
    return out


def _rankdata(xs: List[float]) -> List[float]:
    n = len(xs)
    order = sorted(range(n), key=lambda i: xs[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(xs: List[float], ys: List[float]) -> Optional[float]:
    if len(xs) < 5:
        return None
    rx, ry = _rankdata(xs), _rankdata(ys)
    n = len(xs)
    mx = sum(rx) / n
    my = sum(ry) / n
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    dx = math.sqrt(sum((rx[i] - mx) ** 2 for i in range(n)))
    dy = math.sqrt(sum((ry[i] - my) ** 2 for i in range(n)))
    if dx < 1e-12 or dy < 1e-12:
        return None
    return num / (dx * dy)


def main() -> int:
    basket = load_trading_basket()
    free = _load_scores(FREE_SENTIMENT_CACHE, "free")
    x = _load_scores(X_SENTIMENT_CACHE, "x")
    canon = _load_scores(SENTIMENT_CACHE, "canonical")
    # prefer X; fall back to canonical as "live"
    live = {p: x.get(p, canon.get(p, 0.0)) for p in basket}
    free_s = {p: free.get(p, 0.0) for p in basket}

    free_nz = [p for p in basket if abs(free_s[p]) > EPS]
    live_nz = [p for p in basket if abs(live[p]) > EPS]
    overlap = [p for p in basket if abs(free_s[p]) > EPS and abs(live[p]) > EPS]

    sign_agree = 0
    sign_n = 0
    for p in overlap:
        fs, ls = free_s[p], live[p]
        if abs(fs) < 0.05 or abs(ls) < 0.05:
            # weak — count as agree if same side or either near 0
            if fs * ls >= 0:
                sign_agree += 1
            sign_n += 1
        else:
            sign_n += 1
            if fs * ls > 0:
                sign_agree += 1

    xs = [free_s[p] for p in basket]
    ys = [live[p] for p in basket]
    # all-basket spearman including zeros
    sp_all = spearman(xs, ys)
    sp_ov = spearman([free_s[p] for p in overlap], [live[p] for p in overlap]) if len(overlap) >= 5 else None

    cov_free = len(free_nz) / max(1, len(basket))
    cov_live = len(live_nz) / max(1, len(basket))
    sign_rate = (sign_agree / sign_n) if sign_n else None

    gates = {
        "coverage_free_ge_0_5": cov_free >= 0.5,
        "overlap_ge_3": len(overlap) >= 3,
        "sign_agreement_ge_0_55": (sign_rate is not None and sign_rate >= 0.55),
        "not_anti_spearman": (sp_all is None) or (sp_all > -0.2),
        "spearman_ge_0_25_if_n": (sp_ov is None) or (sp_ov >= 0.25) or (len(overlap) < 5),
    }
    # promote_ready requires core safety; spearman soft if sparse overlap
    promote_ready = (
        gates["coverage_free_ge_0_5"]
        and gates["not_anti_spearman"]
        and (gates["sign_agreement_ge_0_55"] or len(overlap) < 3)
    )

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "basket": basket,
        "coverage_free": round(cov_free, 4),
        "coverage_live": round(cov_live, 4),
        "n_free_nz": len(free_nz),
        "n_live_nz": len(live_nz),
        "n_overlap": len(overlap),
        "sign_agreement": round(sign_rate, 4) if sign_rate is not None else None,
        "spearman_all": round(sp_all, 4) if sp_all is not None else None,
        "spearman_overlap": round(sp_ov, 4) if sp_ov is not None else None,
        "gates": gates,
        "promote_ready": promote_ready,
        "pairs": {
            p: {
                "free": round(free_s[p], 4),
                "live": round(live[p], 4),
                "sign_match": (free_s[p] * live[p] > 0)
                if abs(free_s[p]) > 0.05 and abs(live[p]) > 0.05
                else None,
            }
            for p in basket
        },
        "paths": {
            "free": str(FREE_SENTIMENT_CACHE),
            "x": str(X_SENTIMENT_CACHE),
            "canonical": str(SENTIMENT_CACHE),
        },
        "note": "SHADOW metrics only — do not cut X until promote_ready over multiple days",
    }

    FREE_VS_X_CORRELATION.parent.mkdir(parents=True, exist_ok=True)
    FREE_VS_X_CORRELATION.write_text(json.dumps(report, indent=2), encoding="utf-8")
    with HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(report, separators=(",", ":")) + "\n")

    print(
        f"CORR free_nz={len(free_nz)} live_nz={len(live_nz)} overlap={len(overlap)} "
        f"sign={sign_rate} spearman_all={sp_all} promote_ready={promote_ready}"
    )
    print(f"→ {FREE_VS_X_CORRELATION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
