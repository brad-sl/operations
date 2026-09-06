#!/usr/bin/env python3
"""Same-session Reddit (Adanos) cross-check: rank which cheap/other source lands closest.

SHADOW research only — does not change live sentiment path.
  PYTHONPATH=. python scripts/phase6/run_reddit_crosscheck_closest.py
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

EPS = 1e-6
REPORT = ROOT / "reports" / "REDDIT_CROSSCHECK_CLOSEST_LATEST.md"
OUT_JSON = ROOT / "data" / "state" / "reddit_crosscheck_closest_latest.json"


def pair_score(entry: Any) -> Optional[float]:
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


def load_map(path: Path, kind: str) -> Dict[str, float]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out: Dict[str, float] = {}
    if kind in ("adanos", "free"):
        block = data.get("sentiment") or {}
        for k, e in block.items():
            s = pair_score(e)
            if s is not None:
                out[str(k)] = s
        return out
    # rss / x: pair keys often top-level
    for k, v in data.items():
        if not isinstance(k, str) or "USD" not in k:
            continue
        s = pair_score(v)
        if s is not None:
            out[k] = s
    if not out and isinstance(data.get("sentiment"), dict):
        for k, e in data["sentiment"].items():
            s = pair_score(e)
            if s is not None:
                out[str(k)] = s
    return out


def rankdata(xs: List[float]) -> List[float]:
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
    rx, ry = rankdata(xs), rankdata(ys)
    n = len(xs)
    mx = sum(rx) / n
    my = sum(ry) / n
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    dx = math.sqrt(sum((rx[i] - mx) ** 2 for i in range(n)))
    dy = math.sqrt(sum((ry[i] - my) ** 2 for i in range(n)))
    if dx < 1e-12 or dy < 1e-12:
        return None
    return num / (dx * dy)


def compare(a: Dict[str, float], b: Dict[str, float], name: str) -> Dict[str, Any]:
    pairs = sorted(set(a.keys()).intersection(b.keys()))
    xs: List[float] = []
    ys: List[float] = []
    signs: List[float] = []
    maes: List[float] = []
    for p in pairs:
        va, vb = a[p], b[p]
        xs.append(va)
        ys.append(vb)
        maes.append(abs(va - vb))
        if abs(va) >= EPS and abs(vb) >= EPS:
            signs.append(1.0 if (va > 0) == (vb > 0) else 0.0)
    sign = (sum(signs) / len(signs)) if signs else None
    sp = spearman(xs, ys) if len(xs) >= 5 else None
    xo: List[float] = []
    yo: List[float] = []
    for p in pairs:
        if abs(a[p]) >= EPS and abs(b[p]) >= EPS:
            xo.append(a[p])
            yo.append(b[p])
    sp_nz = spearman(xo, yo) if len(xo) >= 5 else None
    mae = (sum(maes) / len(maes)) if maes else None
    sign_f = sign if sign is not None else 0.5
    sp_f = sp_nz if sp_nz is not None else (sp if sp is not None else 0.0)
    mae_f = mae if mae is not None else 1.0
    mae_score = max(0.0, 1.0 - mae_f / 0.5)
    closeness = 0.40 * sign_f + 0.35 * max(sp_f, -0.5) + 0.25 * mae_score
    return {
        "name": name,
        "n_overlap": len(pairs),
        "n_sign": len(signs),
        "sign_agreement": sign,
        "spearman_all": sp,
        "spearman_both_nz": sp_nz,
        "mae": mae,
        "closeness": closeness,
        "n_a_nz": sum(1 for v in a.values() if abs(v) > EPS),
        "n_b_nz": sum(1 for v in b.values() if abs(v) > EPS),
    }


def main() -> int:
    ad = load_map(ROOT / "data/state/adanos_sentiment_cache.json", "adanos")
    rss = load_map(ROOT / "data/state/rss_sentiment_cache.json", "rss")
    free = load_map(ROOT / "data/state/sentiment_cache_free.json", "free")
    x = load_map(ROOT / "data/state/x_sentiment_cache.json", "x")

    comps = [
        compare(ad, x, "x"),
        compare(ad, rss, "rss"),
        compare(ad, free, "free"),
    ]
    comps_sorted = sorted(comps, key=lambda c: c["closeness"], reverse=True)

    wins = {"x": 0, "rss": 0, "free": 0, "tie": 0}
    pair_rows: List[Dict[str, Any]] = []
    for p in sorted(ad.keys()):
        a = ad[p]
        cands: List[Tuple[str, float, float]] = []
        for name, m in (("rss", rss), ("free", free), ("x", x)):
            if p in m:
                cands.append((name, m[p], abs(m[p] - a)))
        if not cands:
            best, d = "n/a", None
        else:
            cands.sort(key=lambda t: t[2])
            best, _bv, d = cands[0]
            tied = [t for t in cands if abs(t[2] - d) < 1e-12]
            if len(tied) > 1:
                wins["tie"] += 1
                best = "tie:" + ",".join(t[0] for t in tied)
            else:
                wins[best] = wins.get(best, 0) + 1
        pair_rows.append(
            {
                "pair": p,
                "adanos": a,
                "rss": rss.get(p),
                "free": free.get(p),
                "x": x.get(p),
                "closest": best,
                "abs_err": d,
            }
        )

    hist_path = ROOT / "data/state/rss_vs_reddit_correlation_latest.json"
    hist_note = json.loads(hist_path.read_text()) if hist_path.exists() else None

    def fmt(v: Any, nd: int = 3) -> str:
        if v is None:
            return "—"
        try:
            return f"{float(v):.{nd}f}"
        except (TypeError, ValueError):
            return "—"

    def fmt_s(v: Any) -> str:
        if v is None:
            return "—"
        return f"{float(v):+.3f}"

    lines: List[str] = []
    lines.append("# Reddit cross-check — closest source scoreboard")
    lines.append("")
    lines.append(f"**When (UTC):** {datetime.now(timezone.utc).isoformat()}")
    lines.append(
        "**Ground truth:** Adanos Reddit-crypto API (true Reddit scores, free tier) — same-session pull"
    )
    lines.append(
        "**Also refreshed same session:** RSS (9 feeds) + free hybrid (RSS+funding+F&G)"
    )
    lines.append(
        "**X:** last paid pull (morning cache — not re-billed for this check)"
    )
    lines.append(
        "**Apify Reddit:** OFF (cost policy) — Jul 29 one-shot kept as historical anchor only"
    )
    lines.append("")
    lines.append("## Ranking: closest to Reddit (Adanos) this session")
    lines.append("")
    lines.append(
        "| Rank | Source | Sign agree | Spearman (all) | Spearman (both nz) | MAE | Overlap | Closeness |"
    )
    lines.append(
        "|------|--------|------------|----------------|--------------------|-----|---------|-----------|"
    )
    for i, c in enumerate(comps_sorted, 1):
        lines.append(
            f"| {i} | **{c['name']}** | {fmt(c['sign_agreement'])} (n={c['n_sign']}) | "
            f"{fmt(c['spearman_all'])} | {fmt(c['spearman_both_nz'])} | {fmt(c['mae'], 4)} | "
            f"{c['n_overlap']} | {c['closeness']:.3f} |"
        )
    lines.append("")
    lines.append(f"**Winner this session:** `{comps_sorted[0]['name']}`")
    lines.append("")
    lines.append("## Per-pair (who lands nearest Adanos by |Δ|)")
    lines.append("")
    lines.append("| Pair | Adanos | RSS | Free | X raw | Closest |")
    lines.append("|------|--------|-----|------|-------|---------|")
    for row in pair_rows:
        lines.append(
            f"| {row['pair']} | {row['adanos']:+.3f} | {fmt_s(row['rss'])} | "
            f"{fmt_s(row['free'])} | {fmt_s(row['x'])} | {row['closest']} |"
        )
    lines.append("")
    lines.append(
        f"**Pair wins (nearest |Δ|):** x={wins.get('x', 0)} · rss={wins.get('rss', 0)} · "
        f"free={wins.get('free', 0)} · ties={wins.get('tie', 0)}"
    )
    lines.append("")
    lines.append("## Read (honest)")
    w = comps_sorted[0]["name"]
    if w == "x":
        lines.append(
            "- **X is closest to Reddit (Adanos) on this tick** on composite sign/rank/MAE — not free/RSS."
        )
    elif w == "rss":
        lines.append(
            "- **RSS is closest to Reddit** this tick — best free text stand-in among cheap stack."
        )
    else:
        lines.append("- **Free hybrid is closest to Reddit** this tick.")
    lines.append(
        "- Free hybrid includes funding/F&G, so it can **drift from pure social Reddit** even when RSS text is fine."
    )
    lines.append(
        "- RSS↔free can track each other tightly (text-dominated); that ≠ either tracks Reddit."
    )
    lines.append(
        "- **One session ≠ promote.** Multi-day Adanos↔candidate streak still required before mid-cycle live wire."
    )
    lines.append(
        "- Live path **unchanged** (X 2×/day + aging). This is shadow research only."
    )
    lines.append("")
    lines.append("## Historical Apify Reddit anchor (2026-07-29 one-shot)")
    if hist_note:
        rv = hist_note.get("rss_vs_reddit") or {}
        fv = hist_note.get("free_hybrid_vs_reddit") or {}
        lines.append(
            f"- RSS vs Apify Reddit: sign **{rv.get('sign_agreement')}** · Spearman **{rv.get('spearman_all')}** · "
            f"n_overlap **{rv.get('n_overlap')}**"
        )
        lines.append(
            f"- Free vs Apify Reddit: sign **{fv.get('sign_agreement')}** · Spearman **{fv.get('spearman_all')}**"
        )
        lines.append(
            "- That day RSS looked like a decent **Reddit-shaped** candidate; **today’s Adanos pull does not reproduce that** "
            "if RSS/free rank below X or show weak/negative Spearman."
        )
    else:
        lines.append("- No Jul 29 artifact on disk.")
    lines.append("")
    lines.append("## Source timestamps")
    for path in (
        "adanos_sentiment_cache.json",
        "rss_sentiment_cache.json",
        "sentiment_cache_free.json",
        "x_sentiment_cache.json",
    ):
        p = ROOT / "data/state" / path
        lines.append(
            f"- `{path}`: {datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat()}"
        )
    lines.append("")
    lines.append("## Artifacts")
    lines.append("- This report: `reports/REDDIT_CROSSCHECK_CLOSEST_LATEST.md`")
    lines.append("- JSON: `data/state/reddit_crosscheck_closest_latest.json`")
    lines.append("- Multi-corr: `data/state/adanos_rss_free_x_correlation_latest.json`")
    lines.append("")

    text = "\n".join(lines)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(text, encoding="utf-8")
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(
            {
                "schema": "reddit_crosscheck_closest_v1",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "ground_truth": "adanos_reddit",
                "ranking": comps_sorted,
                "pair_wins": wins,
                "pair_rows": pair_rows,
                "live_path_changed": False,
                "apify_used": False,
                "nz_counts": {
                    "adanos": sum(1 for v in ad.values() if abs(v) > EPS),
                    "rss": sum(1 for v in rss.values() if abs(v) > EPS),
                    "free": sum(1 for v in free.values() if abs(v) > EPS),
                    "x": sum(1 for v in x.values() if abs(v) > EPS),
                },
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(text)
    print(
        "RANK",
        [
            (
                c["name"],
                round(c["closeness"], 3),
                c["sign_agreement"],
                c["spearman_all"],
                c["mae"],
            )
            for c in comps_sorted
        ],
    )
    print("WINS", wins)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
