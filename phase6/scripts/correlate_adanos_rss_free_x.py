#!/usr/bin/env python3
"""
Multi-way shadow correlation: Adanos (Reddit) vs RSS vs free hybrid vs live X.

SHADOW only — does not change live gates.
Writes:
  data/state/adanos_rss_free_x_correlation_latest.json
  data/state/adanos_rss_free_x_correlation_history.jsonl
  reports/ADANOS_RSS_FREE_X_CORR_LATEST.md
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
    ADANOS_MULTI_CORR,
    ADANOS_SENTIMENT_CACHE,
    FREE_SENTIMENT_CACHE,
    PROJECT_ROOT,
    RSS_SENTIMENT_CACHE,
    SENTIMENT_CACHE,
    X_SENTIMENT_CACHE,
    load_trading_basket,
)

HISTORY = ADANOS_MULTI_CORR.parent / "adanos_rss_free_x_correlation_history.jsonl"
REPORT = PROJECT_ROOT / "reports" / "ADANOS_RSS_FREE_X_CORR_LATEST.md"
EPS = 1e-6


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


def _pair_score(entry: Any) -> Optional[float]:
    if entry is None:
        return None
    if isinstance(entry, (int, float)):
        return float(entry)
    if isinstance(entry, dict):
        for k in ("sentiment_score", "sentiment", "score"):
            if k in entry and entry[k] is not None:
                try:
                    return float(entry[k])
                except (TypeError, ValueError):
                    return None
    return None


def _load_map(path: Path, kind: str) -> Tuple[Dict[str, float], Dict[str, Any]]:
    meta: Dict[str, Any] = {"path": str(path), "exists": path.exists(), "kind": kind}
    if not path.exists():
        return {}, meta
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        meta["error"] = str(e)
        return {}, meta
    meta["timestamp"] = data.get("timestamp")
    meta["status"] = data.get("status")
    out: Dict[str, float] = {}

    if kind == "adanos":
        sent = data.get("sentiment") or {}
        for p, e in sent.items():
            s = _pair_score(e)
            if s is not None:
                out[p] = s
        meta["source"] = data.get("source")
        meta["n_scored"] = len(out)
    elif kind == "rss":
        # flat pair keys or nested sentiment
        block = data.get("sentiment") if isinstance(data.get("sentiment"), dict) else data
        for p, e in (block or {}).items():
            if p in ("timestamp", "schema_version", "meta"):
                continue
            s = _pair_score(e)
            if s is not None:
                out[p] = s
    elif kind == "free":
        sent = data.get("sentiment") or {}
        for p, e in sent.items():
            s = _pair_score(e)
            if s is not None:
                out[p] = s
    elif kind == "x":
        for p, e in data.items():
            if p in ("timestamp", "schema_version", "meta", "pairs"):
                continue
            s = _pair_score(e)
            if s is not None:
                out[p] = s
        if not out and isinstance(data.get("sentiment"), dict):
            for p, e in data["sentiment"].items():
                s = _pair_score(e)
                if s is not None:
                    out[p] = s
    elif kind == "canonical":
        sent = data.get("sentiment") or {}
        for p, e in sent.items():
            s = _pair_score(e)
            if s is not None:
                out[p] = s
    return out, meta


def _pair_metrics(
    a: Dict[str, float], b: Dict[str, float], basket: List[str], name_a: str, name_b: str
) -> Dict[str, Any]:
    a_nz = [p for p in basket if abs(a.get(p, 0.0)) > EPS]
    b_nz = [p for p in basket if abs(b.get(p, 0.0)) > EPS]
    overlap = [p for p in basket if abs(a.get(p, 0.0)) > EPS and abs(b.get(p, 0.0)) > EPS]
    sign_agree = 0
    sign_n = 0
    for p in overlap:
        av, bv = a[p], b[p]
        sign_n += 1
        if abs(av) < 0.05 or abs(bv) < 0.05:
            if av * bv >= 0:
                sign_agree += 1
        elif av * bv > 0:
            sign_agree += 1
    xs_all = [a.get(p, 0.0) for p in basket]
    ys_all = [b.get(p, 0.0) for p in basket]
    sp_all = spearman(xs_all, ys_all)
    sp_ov = (
        spearman([a[p] for p in overlap], [b[p] for p in overlap]) if len(overlap) >= 5 else None
    )
    sign_rate = (sign_agree / sign_n) if sign_n else None
    gates = {
        f"coverage_{name_a}_ge_0_5": (len(a_nz) / max(1, len(basket))) >= 0.5,
        f"coverage_{name_b}_ge_0_5": (len(b_nz) / max(1, len(basket))) >= 0.5,
        "overlap_ge_3": len(overlap) >= 3,
        "sign_agreement_ge_0_55": sign_rate is not None and sign_rate >= 0.55,
        "not_anti_spearman": sp_all is None or sp_all > -0.2,
        "spearman_ge_0_25_if_n": sp_ov is None or sp_ov >= 0.25 or len(overlap) < 5,
    }
    proxy_ready = (
        gates[f"coverage_{name_a}_ge_0_5"]
        and gates["not_anti_spearman"]
        and (gates["sign_agreement_ge_0_55"] or len(overlap) < 3)
        and gates["overlap_ge_3"]
    )
    return {
        "a": name_a,
        "b": name_b,
        "n_a_nz": len(a_nz),
        "n_b_nz": len(b_nz),
        "n_overlap": len(overlap),
        "coverage_a": round(len(a_nz) / max(1, len(basket)), 4),
        "coverage_b": round(len(b_nz) / max(1, len(basket)), 4),
        "sign_agreement": round(sign_rate, 4) if sign_rate is not None else None,
        "spearman_all": round(sp_all, 4) if sp_all is not None else None,
        "spearman_overlap": round(sp_ov, 4) if sp_ov is not None else None,
        "gates": gates,
        "proxy_ready_snapshot": proxy_ready,
        "pairs": {
            p: {
                name_a: round(a.get(p, 0.0), 4),
                name_b: round(b.get(p, 0.0), 4),
                "sign_match": (
                    (a.get(p, 0.0) * b.get(p, 0.0) > 0)
                    if abs(a.get(p, 0.0)) > 0.05 and abs(b.get(p, 0.0)) > 0.05
                    else None
                ),
            }
            for p in basket
        },
    }


def main() -> int:
    basket = load_trading_basket()
    adanos, m_ad = _load_map(ADANOS_SENTIMENT_CACHE, "adanos")
    rss, m_rss = _load_map(RSS_SENTIMENT_CACHE, "rss")
    free, m_free = _load_map(FREE_SENTIMENT_CACHE, "free")
    x, m_x = _load_map(X_SENTIMENT_CACHE, "x")
    canon, m_c = _load_map(SENTIMENT_CACHE, "canonical")
    live = {p: x.get(p, canon.get(p, 0.0)) for p in basket}
    # fill missing as 0 for live map completeness
    live = {p: float(live.get(p, 0.0) or 0.0) for p in basket}
    rss_f = {p: float(rss.get(p, 0.0) or 0.0) for p in basket}
    free_f = {p: float(free.get(p, 0.0) or 0.0) for p in basket}
    adanos_f = {p: float(adanos.get(p, 0.0) or 0.0) for p in basket}

    comparisons = {
        "adanos_vs_x": _pair_metrics(adanos_f, live, basket, "adanos", "x"),
        "adanos_vs_rss": _pair_metrics(adanos_f, rss_f, basket, "adanos", "rss"),
        "adanos_vs_free": _pair_metrics(adanos_f, free_f, basket, "adanos", "free"),
        "rss_vs_x": _pair_metrics(rss_f, live, basket, "rss", "x"),
        "free_vs_x": _pair_metrics(free_f, live, basket, "free", "x"),
        "rss_vs_free": _pair_metrics(rss_f, free_f, basket, "rss", "free"),
    }

    adanos_ready = bool(adanos) and m_ad.get("status") not in (None, "missing_api_key", "error")
    # Prefer Adanos as Reddit stand-in if it beats RSS vs X on sign+spearman this tick
    ranking = []
    for name in ("adanos_vs_x", "rss_vs_x", "free_vs_x"):
        c = comparisons[name]
        ranking.append(
            {
                "pair": name,
                "sign": c.get("sign_agreement"),
                "spearman_all": c.get("spearman_all"),
                "proxy_ready_snapshot": c.get("proxy_ready_snapshot"),
                "n_overlap": c.get("n_overlap"),
            }
        )
    ranking_sorted = sorted(
        ranking,
        key=lambda r: (
            0 if r["sign"] is None else r["sign"],
            0 if r["spearman_all"] is None else r["spearman_all"],
        ),
        reverse=True,
    )

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "basket": basket,
        "adanos_available": adanos_ready,
        "sources": {
            "adanos": m_ad,
            "rss": m_rss,
            "free": m_free,
            "x": m_x,
            "canonical": m_c,
        },
        "comparisons": comparisons,
        "ranking_vs_x": ranking_sorted,
        "product_read": {
            "live_still": "X 2×/day + aging (15m HL)",
            "adanos_role": "true Reddit shadow candidate (bridge-shaped if multi-day gates pass)",
            "rss_role": "free Reddit-shaped text already in free hybrid",
            "free_role": "RSS+funding hybrid shadow @ 2h",
            "last30days_role": "research briefs only — not in this numeric bakeoff unless probe run",
            "promote_rule": "multi-day streak + Brad GO; never single-tick",
        },
        "note": "SHADOW only — missing Adanos key → adanos_* metrics are zeros / not informative",
    }

    ADANOS_MULTI_CORR.parent.mkdir(parents=True, exist_ok=True)
    ADANOS_MULTI_CORR.write_text(json.dumps(report, indent=2), encoding="utf-8")
    with HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps({k: report[k] for k in report if k != "comparisons"}, separators=(",", ":")) + "\n")
        # also store compact comparison metrics
        compact = {
            "timestamp": report["timestamp"],
            "adanos_available": adanos_ready,
            "metrics": {
                k: {
                    "sign": v.get("sign_agreement"),
                    "spearman_all": v.get("spearman_all"),
                    "overlap": v.get("n_overlap"),
                    "ready": v.get("proxy_ready_snapshot"),
                }
                for k, v in comparisons.items()
            },
        }
        f.write(json.dumps(compact, separators=(",", ":")) + "\n")

    # Markdown brief
    lines = [
        "# Adanos vs RSS vs Free vs X — shadow correlation",
        "",
        f"**When:** {report['timestamp']}",
        f"**Adanos available:** {adanos_ready}",
        f"**Basket n:** {len(basket)}",
        "",
        "## Ranking vs live X (this tick)",
        "",
        "| Compare | Sign agree | Spearman | Overlap | Snapshot ready |",
        "|---------|------------|----------|---------|----------------|",
    ]
    for r in ranking_sorted:
        lines.append(
            f"| {r['pair']} | {r['sign']} | {r['spearman_all']} | {r['n_overlap']} | {r['proxy_ready_snapshot']} |"
        )
    lines += [
        "",
        "## Cross checks",
        "",
        "| Compare | Sign | Spearman | Overlap | Ready |",
        "|---------|------|----------|---------|-------|",
    ]
    for k, v in comparisons.items():
        lines.append(
            f"| {k} | {v.get('sign_agreement')} | {v.get('spearman_all')} | {v.get('n_overlap')} | {v.get('proxy_ready_snapshot')} |"
        )
    lines += [
        "",
        "## Product",
        "",
        "- Live path unchanged (X + aging).",
        "- Adanos = true Reddit free-tier candidate for hour bridge.",
        "- RSS already free inside free hybrid (2h shadow).",
        "- last30days = research briefs — separate probe if desired.",
        "- **No live wire** without multi-day streak + Brad GO.",
        "",
        f"JSON: `{ADANOS_MULTI_CORR}`",
        "",
    ]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")

    print(
        f"MULTI-CORR adanos_avail={adanos_ready} "
        f"rank0={ranking_sorted[0]['pair'] if ranking_sorted else None} "
        f"→ {ADANOS_MULTI_CORR}"
    )
    for r in ranking_sorted:
        print(
            f"  {r['pair']}: sign={r['sign']} sp={r['spearman_all']} "
            f"ov={r['n_overlap']} ready={r['proxy_ready_snapshot']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
