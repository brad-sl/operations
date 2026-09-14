"""P2 — Promote + graduation chart (measure-only).

Builds a dashboard-ready board from basket pick ledger + seat graduation:
  seat → signal → fill → win/loss

Artifacts
---------
- data/state/promote_graduation_chart_latest.json
- data/state/promote_graduation_crumbs.jsonl   (one snapshot/day)
- reports/PROMOTE_GRADUATION_CHART_LATEST.md
- reports/charts/promote_graduation_funnel_latest.svg
- reports/charts/promote_graduation_outcomes_latest.svg
- reports/charts/promote_graduation_paper_latest.svg

Rules
-----
- No live writes to membership / knobs.
- Thin N → claim_allowed=false / promote_talk_ok=false.
- Paper MTM ≠ filled PnL — keep separate.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "data" / "state"
REPORTS = ROOT / "reports"
CHARTS = REPORTS / "charts"

PICK_LEDGER = STATE / "basket_pick_metrics.jsonl"
PICK_SUMMARY = STATE / "basket_pick_metrics_summary.json"
GRAD_LATEST = STATE / "basket_seat_graduation_latest.json"
IDLE_LATEST = STATE / "basket_seat_idle_latest.json"

LATEST_JSON = STATE / "promote_graduation_chart_latest.json"
CRUMBS = STATE / "promote_graduation_crumbs.jsonl"
REPORT_MD = REPORTS / "PROMOTE_GRADUATION_CHART_LATEST.md"
FUNNEL_SVG = CHARTS / "promote_graduation_funnel_latest.svg"
OUTCOMES_SVG = CHARTS / "promote_graduation_outcomes_latest.svg"
PAPER_SVG = CHARTS / "promote_graduation_paper_latest.svg"

SCHEMA = "promote_graduation_chart_v1"
CLAIM_MIN_N = 20
CLAIM_MIN_HIT7 = 0.40
CLAIM_MIN_FILLS = 10


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(ts: Any) -> Optional[datetime]:
    if ts is None:
        return None
    try:
        s = str(ts).strip().replace("Z", "+00:00")
        if not s:
            return None
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        d = json.loads(path.read_text())
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _f(x: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if x is None or x == "":
            return default
        return float(x)
    except (TypeError, ValueError):
        return default


def _i(x: Any, default: int = 0) -> int:
    try:
        if x is None or x == "":
            return default
        return int(x)
    except (TypeError, ValueError):
        return default


def _stage_of(g: Mapping[str, Any]) -> str:
    st = str(g.get("stage") or "").strip().lower()
    if st:
        return st
    if g.get("filled"):
        pnl = _f(g.get("realized_pnl_sum"))
        if pnl is None:
            return "filled_open"
        return "filled_win" if pnl > 0 else "filled_loss"
    if g.get("signaled"):
        if _i(g.get("n_run_phase_blocks")) > 0 or g.get("first_block"):
            return "blocked_no_fill"
        return "signaled"
    if g.get("seated"):
        return "seated"
    return "unknown"


def _outcome_class(stage: str, paper_7d: Optional[float]) -> str:
    if stage in ("filled_win",):
        return "trade_win"
    if stage in ("filled_loss",):
        return "trade_loss"
    if stage == "filled_open":
        return "trade_open"
    if stage == "blocked_no_fill":
        return "blocked"
    if stage == "signaled":
        if paper_7d is not None and paper_7d > 0:
            return "paper_green_unfilled"
        if paper_7d is not None and paper_7d < 0:
            return "paper_red_unfilled"
        return "signaled_idle"
    if stage == "seated":
        return "seated_no_signal"
    if stage == "stale_no_signal":
        return "stale"
    return "other"


def build_episodes(
    ledger: Sequence[Mapping[str, Any]],
    grad_picks: Optional[Sequence[Mapping[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """One episode per promote pick, joined with graduation fields."""
    by_id: Dict[str, Dict[str, Any]] = {}
    for gp in grad_picks or []:
        pid = str(gp.get("pick_id") or "")
        if pid:
            by_id[pid] = dict(gp)

    episodes: List[Dict[str, Any]] = []
    for row in ledger:
        pid = str(row.get("pick_id") or "")
        g = dict(row.get("graduation") or {})
        if pid and pid in by_id:
            # graduation latest pick board wins for stage/fills when present
            for k, v in by_id[pid].items():
                if v is not None and k not in ("pick_id",):
                    g.setdefault(k, v)
                    if k in (
                        "stage",
                        "filled",
                        "signaled",
                        "realized_pnl_sum",
                        "hours_to_first_signal",
                        "hours_to_first_fill",
                        "paper_ret_7d_pct",
                        "paper_excess_7d_pct",
                        "n_run_phase_blocks",
                    ):
                        g[k] = v

        stage = _stage_of(g)
        paper_7d = _f(g.get("paper_ret_7d_pct"))
        if paper_7d is None:
            marks = row.get("marks") or {}
            m7 = marks.get("7d") or {}
            paper_7d = _f(m7.get("ret_pct"))
        paper_ex7 = _f(g.get("paper_excess_7d_pct"))
        if paper_ex7 is None:
            marks = row.get("marks") or {}
            m7 = marks.get("7d") or {}
            paper_ex7 = _f(m7.get("excess_vs_remove_pct"))

        episodes.append(
            {
                "pick_id": pid or None,
                "add_pair": row.get("add_pair") or g.get("add_pair"),
                "remove_pair": row.get("remove_pair") or g.get("remove_pair"),
                "promoted_at": row.get("promoted_at") or g.get("promoted_at"),
                "source": row.get("source") or g.get("source"),
                "status": row.get("status") or "open",
                "stage": stage,
                "signaled": bool(g.get("signaled")),
                "filled": bool(g.get("filled")),
                "hours_to_first_signal": _f(g.get("hours_to_first_signal")),
                "hours_to_first_fill": _f(g.get("hours_to_first_fill")),
                "realized_pnl_sum": _f(g.get("realized_pnl_sum")),
                "paper_ret_7d_pct": paper_7d,
                "paper_excess_7d_pct": paper_ex7,
                "age_days": _f(g.get("age_days")),
                "n_run_phase_blocks": _i(g.get("n_run_phase_blocks")),
                "outcome_class": _outcome_class(stage, paper_7d),
            }
        )

    # stable: oldest promote first
    def _key(e: Dict[str, Any]) -> str:
        return str(e.get("promoted_at") or "")

    episodes.sort(key=_key)
    return episodes


def funnel_from_episodes(episodes: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    n_seated = len(episodes)
    n_signaled = sum(1 for e in episodes if e.get("signaled") or e.get("stage") not in ("seated", "stale_no_signal", "unknown", ""))
    # stricter: stage not seated/stale
    n_signaled = sum(
        1
        for e in episodes
        if e.get("signaled")
        or str(e.get("stage") or "")
        in (
            "signaled",
            "blocked_no_fill",
            "filled_open",
            "filled_win",
            "filled_loss",
        )
    )
    n_filled = sum(1 for e in episodes if e.get("filled") or str(e.get("stage") or "").startswith("filled"))
    n_win = sum(1 for e in episodes if e.get("stage") == "filled_win")
    n_loss = sum(1 for e in episodes if e.get("stage") == "filled_loss")
    n_open = sum(1 for e in episodes if e.get("stage") == "filled_open")
    n_blocked = sum(1 for e in episodes if e.get("stage") == "blocked_no_fill")
    n_stale = sum(1 for e in episodes if e.get("stage") in ("stale_no_signal", "seated"))

    closed = n_win + n_loss
    return {
        "n_seated": n_seated,
        "n_signaled": n_signaled,
        "n_filled": n_filled,
        "n_filled_win": n_win,
        "n_filled_loss": n_loss,
        "n_filled_open": n_open,
        "n_blocked_no_fill": n_blocked,
        "n_stale_no_signal": n_stale,
        "rate_signal_given_seat": round(n_signaled / n_seated, 4) if n_seated else None,
        "rate_fill_given_signal": round(n_filled / n_signaled, 4) if n_signaled else None,
        "rate_win_given_fill_closed": round(n_win / closed, 4) if closed else None,
        "rate_win_given_seat": round(n_win / n_seated, 4) if n_seated else None,
        "stages": {
            "seated": sum(1 for e in episodes if e.get("stage") == "seated"),
            "signaled": sum(1 for e in episodes if e.get("stage") == "signaled"),
            "blocked_no_fill": n_blocked,
            "filled_open": n_open,
            "filled_win": n_win,
            "filled_loss": n_loss,
            "stale_no_signal": sum(1 for e in episodes if e.get("stage") == "stale_no_signal"),
        },
    }


def paper_scoreboard(summary: Mapping[str, Any], episodes: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    avg = summary.get("avg_ret_pct_by_horizon") or {}
    ex = summary.get("avg_excess_vs_remove_pct") or {}
    n = _i(summary.get("n_picks"), len(episodes))
    hit7 = _f(summary.get("hit_rate_positive_7d"))
    # recompute hit from episodes if missing
    if hit7 is None:
        vals = [e.get("paper_ret_7d_pct") for e in episodes if e.get("paper_ret_7d_pct") is not None]
        hit7 = (sum(1 for v in vals if float(v) > 0) / len(vals)) if vals else None

    claim = bool(
        n >= CLAIM_MIN_N
        and hit7 is not None
        and hit7 >= CLAIM_MIN_HIT7
        and sum(1 for e in episodes if e.get("filled")) >= CLAIM_MIN_FILLS
    )
    return {
        "n_picks": n,
        "open_picks": _i(summary.get("open_picks")),
        "adds": list(summary.get("adds") or [e.get("add_pair") for e in episodes]),
        "avg_ret_1d_pct": _f(avg.get("1d")),
        "avg_ret_3d_pct": _f(avg.get("3d")),
        "avg_ret_7d_pct": _f(avg.get("7d")),
        "avg_ret_14d_pct": _f(avg.get("14d")),
        "avg_excess_7d_pct": _f(ex.get("7d")),
        "hit_rate_positive_7d": hit7,
        "claim_allowed": claim,
        "claim_bar": {
            "min_n_picks": CLAIM_MIN_N,
            "min_hit_rate_7d": CLAIM_MIN_HIT7,
            "min_filled": CLAIM_MIN_FILLS,
        },
        "note": (
            "Paper MTM vs promote baseline; excess = add − remove. "
            "Not live PnL. claim_allowed requires N≥20, hit7≥40%, filled≥10."
        ),
    }


def timing_stats(episodes: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    hs = [e.get("hours_to_first_signal") for e in episodes if e.get("hours_to_first_signal") is not None]
    hf = [e.get("hours_to_first_fill") for e in episodes if e.get("hours_to_first_fill") is not None]

    def _med(xs: List[Any]) -> Optional[float]:
        vals = sorted(float(x) for x in xs)
        if not vals:
            return None
        mid = len(vals) // 2
        if len(vals) % 2:
            return round(vals[mid], 2)
        return round((vals[mid - 1] + vals[mid]) / 2.0, 2)

    return {
        "n_with_signal_latency": len(hs),
        "median_hours_to_signal": _med(hs),
        "mean_hours_to_signal": round(sum(float(x) for x in hs) / len(hs), 2) if hs else None,
        "n_with_fill_latency": len(hf),
        "median_hours_to_fill": _med(hf),
        "mean_hours_to_fill": round(sum(float(x) for x in hf) / len(hf), 2) if hf else None,
    }


def choke_point(funnel: Mapping[str, Any]) -> Dict[str, Any]:
    n_seat = _i(funnel.get("n_seated"))
    n_sig = _i(funnel.get("n_signaled"))
    n_fill = _i(funnel.get("n_filled"))
    n_win = _i(funnel.get("n_filled_win"))
    n_loss = _i(funnel.get("n_filled_loss"))
    if n_seat == 0:
        return {"id": "no_promotes", "why": "No seated promote episodes yet."}
    if n_sig == 0:
        return {"id": "signal", "why": f"seated={n_seat} but none signaled — entry/gate drought"}
    fill_rate = (n_fill / n_sig) if n_sig else 0.0
    if fill_rate < 0.35 and n_sig >= 3:
        return {
            "id": "fill",
            "why": f"sig={n_sig} fill={n_fill} (fill|sig={fill_rate:.0%}) — size/armor/limit path",
        }
    if n_fill >= 1 and n_win == 0 and n_loss >= 1:
        return {
            "id": "trade_success",
            "why": f"filled={n_fill} wins=0 losses={n_loss} — exit/entry quality, not more scouts",
        }
    if n_fill == 0:
        return {"id": "fill", "why": f"signaled={n_sig} but zero fills"}
    return {"id": "ok_thin", "why": "No dominant choke; N still thin for claims."}


# ---------------------------------------------------------------------------
# SVG charts (no matplotlib)
# ---------------------------------------------------------------------------

_COLORS = {
    "bg": "#0f1419",
    "panel": "#1a2332",
    "grid": "#2a3544",
    "text": "#e7ecf3",
    "muted": "#8b9bb4",
    "seat": "#5b8def",
    "signal": "#3dbb9a",
    "fill": "#f0b429",
    "win": "#3dd68c",
    "loss": "#f07178",
    "blocked": "#c792ea",
    "paper_pos": "#7fd962",
    "paper_neg": "#ff8b6a",
    "axis": "#6b7c93",
}


def _esc(s: Any) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_funnel_svg(funnel: Mapping[str, Any], *, title: str = "Promote graduation funnel") -> str:
    stages = [
        ("Seat", _i(funnel.get("n_seated")), _COLORS["seat"]),
        ("Signal", _i(funnel.get("n_signaled")), _COLORS["signal"]),
        ("Fill", _i(funnel.get("n_filled")), _COLORS["fill"]),
        ("Win", _i(funnel.get("n_filled_win")), _COLORS["win"]),
        ("Loss", _i(funnel.get("n_filled_loss")), _COLORS["loss"]),
    ]
    w, h = 720, 280
    left, right, top, bot = 90, 40, 48, 36
    plot_w = w - left - right
    plot_h = h - top - bot
    mx = max((v for _, v, _ in stages), default=1) or 1
    n = len(stages)
    gap = 14
    bar_h = (plot_h - gap * (n - 1)) / n

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        f'<rect width="100%" height="100%" fill="{_COLORS["bg"]}"/>',
        f'<text x="24" y="28" fill="{_COLORS["text"]}" font-family="ui-sans-serif,system-ui,sans-serif" '
        f'font-size="16" font-weight="600">{_esc(title)}</text>',
        f'<text x="{w - 24}" y="28" text-anchor="end" fill="{_COLORS["muted"]}" '
        f'font-family="ui-sans-serif,system-ui,sans-serif" font-size="11">measure-only · thin N honest</text>',
    ]
    for i, (label, val, color) in enumerate(stages):
        y = top + i * (bar_h + gap)
        bw = max(2.0, (val / mx) * plot_w) if mx else 2.0
        parts.append(
            f'<text x="{left - 12}" y="{y + bar_h / 2 + 4}" text-anchor="end" fill="{_COLORS["muted"]}" '
            f'font-family="ui-sans-serif,system-ui,sans-serif" font-size="13">{_esc(label)}</text>'
        )
        parts.append(
            f'<rect x="{left}" y="{y}" width="{bw:.1f}" height="{bar_h:.1f}" rx="4" fill="{color}" opacity="0.92"/>'
        )
        parts.append(
            f'<text x="{left + bw + 8}" y="{y + bar_h / 2 + 4}" fill="{_COLORS["text"]}" '
            f'font-family="ui-sans-serif,system-ui,sans-serif" font-size="13" font-weight="600">{val}</text>'
        )
    # rate captions
    rates = [
        f"sig|seat={funnel.get('rate_signal_given_seat')}",
        f"fill|sig={funnel.get('rate_fill_given_signal')}",
        f"win|fill={funnel.get('rate_win_given_fill_closed')}",
        f"win|seat={funnel.get('rate_win_given_seat')}",
    ]
    parts.append(
        f'<text x="24" y="{h - 12}" fill="{_COLORS["muted"]}" font-family="ui-sans-serif,system-ui,sans-serif" '
        f'font-size="11">{" · ".join(rates)}</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


def render_outcomes_svg(episodes: Sequence[Mapping[str, Any]], *, title: str = "Promote episodes by outcome") -> str:
    order = [
        ("trade_win", "Trade win", _COLORS["win"]),
        ("trade_loss", "Trade loss", _COLORS["loss"]),
        ("trade_open", "Trade open", _COLORS["fill"]),
        ("blocked", "Blocked", _COLORS["blocked"]),
        ("paper_green_unfilled", "Paper+ unfilled", _COLORS["paper_pos"]),
        ("paper_red_unfilled", "Paper− unfilled", _COLORS["paper_neg"]),
        ("signaled_idle", "Signaled idle", _COLORS["signal"]),
        ("seated_no_signal", "Seated no sig", _COLORS["seat"]),
        ("stale", "Stale", _COLORS["axis"]),
        ("other", "Other", _COLORS["muted"]),
    ]
    counts = {k: 0 for k, _, _ in order}
    for e in episodes:
        oc = str(e.get("outcome_class") or "other")
        if oc not in counts:
            oc = "other"
        counts[oc] += 1
    rows = [(lab, counts[k], col) for k, lab, col in order if counts[k] > 0]
    if not rows:
        rows = [("None", 0, _COLORS["muted"])]

    w, h = 720, max(220, 40 + 28 * len(rows) + 36)
    left, right, top, bot = 150, 40, 48, 28
    plot_w = w - left - right
    mx = max((v for _, v, _ in rows), default=1) or 1
    bar_h = 18
    gap = 10

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        f'<rect width="100%" height="100%" fill="{_COLORS["bg"]}"/>',
        f'<text x="24" y="28" fill="{_COLORS["text"]}" font-family="ui-sans-serif,system-ui,sans-serif" '
        f'font-size="16" font-weight="600">{_esc(title)}</text>',
        f'<text x="{w - 24}" y="28" text-anchor="end" fill="{_COLORS["muted"]}" '
        f'font-family="ui-sans-serif,system-ui,sans-serif" font-size="11">n={len(episodes)}</text>',
    ]
    for i, (lab, val, col) in enumerate(rows):
        y = top + i * (bar_h + gap)
        bw = max(2.0, (val / mx) * plot_w) if mx else 2.0
        parts.append(
            f'<text x="{left - 10}" y="{y + bar_h - 4}" text-anchor="end" fill="{_COLORS["muted"]}" '
            f'font-family="ui-sans-serif,system-ui,sans-serif" font-size="12">{_esc(lab)}</text>'
        )
        parts.append(
            f'<rect x="{left}" y="{y}" width="{bw:.1f}" height="{bar_h}" rx="3" fill="{col}" opacity="0.9"/>'
        )
        parts.append(
            f'<text x="{left + bw + 8}" y="{y + bar_h - 4}" fill="{_COLORS["text"]}" '
            f'font-family="ui-sans-serif,system-ui,sans-serif" font-size="12">{val}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def render_paper_bars_svg(episodes: Sequence[Mapping[str, Any]], *, title: str = "Paper 7d return by promote") -> str:
    rows = [
        e
        for e in episodes
        if e.get("paper_ret_7d_pct") is not None and e.get("add_pair")
    ]
    # newest last for reading left→right chronological
    rows = sorted(rows, key=lambda e: str(e.get("promoted_at") or ""))
    w, h = 720, 300
    left, right, top, bot = 48, 24, 48, 70
    plot_w = w - left - right
    plot_h = h - top - bot

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        f'<rect width="100%" height="100%" fill="{_COLORS["bg"]}"/>',
        f'<text x="24" y="28" fill="{_COLORS["text"]}" font-family="ui-sans-serif,system-ui,sans-serif" '
        f'font-size="16" font-weight="600">{_esc(title)}</text>',
        f'<text x="{w - 24}" y="28" text-anchor="end" fill="{_COLORS["muted"]}" '
        f'font-family="ui-sans-serif,system-ui,sans-serif" font-size="11">'
        f'paper MTM ≠ fill PnL</text>',
    ]
    if not rows:
        parts.append(
            f'<text x="{w/2}" y="{h/2}" text-anchor="middle" fill="{_COLORS["muted"]}" '
            f'font-family="ui-sans-serif,system-ui,sans-serif" font-size="14">No 7d paper marks yet</text>'
        )
        parts.append("</svg>")
        return "\n".join(parts)

    vals = [float(e["paper_ret_7d_pct"]) for e in rows]
    mx = max(abs(v) for v in vals) or 1.0
    mx = max(mx, 5.0)
    zero_y = top + plot_h * (mx / (2 * mx))  # center zero
    # actually symmetric scale
    y_for = lambda v: top + plot_h * (1.0 - (v + mx) / (2 * mx))

    # zero line
    zy = y_for(0.0)
    parts.append(
        f'<line x1="{left}" y1="{zy:.1f}" x2="{left + plot_w}" y2="{zy:.1f}" '
        f'stroke="{_COLORS["grid"]}" stroke-width="1"/>'
    )
    n = len(rows)
    gap = 6
    bw = max(8.0, (plot_w - gap * (n + 1)) / n)

    for i, e in enumerate(rows):
        v = float(e["paper_ret_7d_pct"])
        x = left + gap + i * (bw + gap)
        y0 = zy
        y1 = y_for(v)
        y = min(y0, y1)
        bh = max(2.0, abs(y1 - y0))
        col = _COLORS["paper_pos"] if v >= 0 else _COLORS["paper_neg"]
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="2" fill="{col}" opacity="0.9"/>'
        )
        pair = str(e.get("add_pair") or "").replace("-USD", "")
        parts.append(
            f'<text x="{x + bw/2:.1f}" y="{h - 36}" text-anchor="middle" fill="{_COLORS["muted"]}" '
            f'font-family="ui-sans-serif,system-ui,sans-serif" font-size="10" '
            f'transform="rotate(-35 {x + bw/2:.1f} {h - 36})">{_esc(pair)}</text>'
        )
        label_y = (y - 4) if v >= 0 else (y + bh + 12)
        parts.append(
            f'<text x="{x + bw/2:.1f}" y="{label_y:.1f}" text-anchor="middle" '
            f'fill="{_COLORS["text"]}" font-family="ui-sans-serif,system-ui,sans-serif" font-size="10">'
            f"{v:+.1f}</text>"
        )
    parts.append(
        f'<text x="24" y="{h - 10}" fill="{_COLORS["muted"]}" font-family="ui-sans-serif,system-ui,sans-serif" '
        f'font-size="11">7d paper return % from promote baseline (chronological)</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Series / crumbs
# ---------------------------------------------------------------------------


def _crumb_from_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    funnel = payload.get("funnel") or {}
    paper = payload.get("paper") or {}
    as_of = str(payload.get("as_of") or _utc_now().isoformat())
    day = as_of[:10]
    return {
        "date": day,
        "as_of": as_of,
        "n_seated": funnel.get("n_seated"),
        "n_signaled": funnel.get("n_signaled"),
        "n_filled": funnel.get("n_filled"),
        "n_filled_win": funnel.get("n_filled_win"),
        "n_filled_loss": funnel.get("n_filled_loss"),
        "rate_fill_given_signal": funnel.get("rate_fill_given_signal"),
        "rate_win_given_seat": funnel.get("rate_win_given_seat"),
        "hit_rate_positive_7d": paper.get("hit_rate_positive_7d"),
        "avg_ret_7d_pct": paper.get("avg_ret_7d_pct"),
        "avg_excess_7d_pct": paper.get("avg_excess_7d_pct"),
        "choke": (payload.get("choke_point") or {}).get("id"),
        "claim_allowed": paper.get("claim_allowed"),
    }


def append_crumb(payload: Mapping[str, Any], path: Path = CRUMBS) -> Dict[str, Any]:
    """One crumb per UTC date (overwrite same-day)."""
    crumb = _crumb_from_payload(payload)
    existing = _load_jsonl(path)
    day = crumb["date"]
    kept = [r for r in existing if str(r.get("date")) != day]
    kept.append(crumb)
    kept.sort(key=lambda r: str(r.get("date") or ""))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in kept:
            f.write(json.dumps(r, default=str) + "\n")
    return {"wrote": True, "n": len(kept), "date": day}


def series_from_crumbs(path: Path = CRUMBS) -> Dict[str, Any]:
    rows = _load_jsonl(path)
    return {
        "n_points": len(rows),
        "points": rows,
        "note": "Daily snapshots of promote graduation funnel + paper scoreboard. Grows with cron.",
    }


# ---------------------------------------------------------------------------
# Board build
# ---------------------------------------------------------------------------


def build_chart(
    *,
    ledger: Optional[Sequence[Mapping[str, Any]]] = None,
    summary: Optional[Mapping[str, Any]] = None,
    grad: Optional[Mapping[str, Any]] = None,
    idle: Optional[Mapping[str, Any]] = None,
    now: Optional[datetime] = None,
    write: bool = True,
    append_history: bool = True,
    root: Optional[Path] = None,
) -> Dict[str, Any]:
    now = now or _utc_now()
    root = root or ROOT
    state = root / "data" / "state"
    reports = root / "reports"
    charts = reports / "charts"

    if ledger is None:
        ledger = _load_jsonl(state / "basket_pick_metrics.jsonl" if root != ROOT else PICK_LEDGER)
    if summary is None:
        summary = _load_json(state / "basket_pick_metrics_summary.json" if root != ROOT else PICK_SUMMARY)
    if grad is None:
        grad = _load_json(state / "basket_seat_graduation_latest.json" if root != ROOT else GRAD_LATEST)
    if idle is None:
        idle = _load_json(state / "basket_seat_idle_latest.json" if root != ROOT else IDLE_LATEST)

    grad_picks = list(grad.get("picks") or [])
    episodes = build_episodes(ledger, grad_picks)
    # Prefer live graduation funnel when present & consistent; else from episodes
    funnel_src = grad.get("funnel") if isinstance(grad.get("funnel"), dict) else None
    funnel_ep = funnel_from_episodes(episodes)
    if funnel_src and _i(funnel_src.get("n_seated")) == len(episodes):
        funnel = dict(funnel_src)
        # keep rates
    else:
        funnel = funnel_ep
        if funnel_src and _i(funnel_src.get("n_seated")) > 0:
            funnel["source_note"] = "episodes_recomputed; grad.funnel n mismatch"
        else:
            funnel["source_note"] = "episodes"

    paper = paper_scoreboard(summary or {}, episodes)
    timing = timing_stats(episodes)
    choke = choke_point(funnel)

    promote_talk_ok = bool(paper.get("claim_allowed") and _i(funnel.get("n_filled_win")) >= 3)
    go = {
        "promote_talk_ok": promote_talk_ok,
        "claim_allowed": bool(paper.get("claim_allowed")),
        "choke_point": choke.get("id"),
        "choke_why": choke.get("why"),
        "money_path_hint": (
            "NO_GO_SCALE"
            if _i(funnel.get("n_filled_win")) == 0 and _i(funnel.get("n_seated")) >= 3
            else ("ATTENTION" if not promote_talk_ok else "REVIEW")
        ),
        "plain_english": (
            f"promotes={funnel.get('n_seated')} sig={funnel.get('n_signaled')} "
            f"fill={funnel.get('n_filled')} win={funnel.get('n_filled_win')} "
            f"choke={choke.get('id')} paper_hit7={paper.get('hit_rate_positive_7d')} "
            f"claim={paper.get('claim_allowed')}."
        ),
    }

    # idle DQ candidates (observe only)
    idle_flagged = list(idle.get("idle_flagged_pairs") or []) if idle else []

    payload: Dict[str, Any] = {
        "schema": SCHEMA,
        "as_of": now.isoformat(),
        "measure_only": True,
        "no_live_writes": True,
        "funnel": funnel,
        "paper": paper,
        "timing": timing,
        "choke_point": choke,
        "go_nogo": go,
        "episodes": episodes,
        "n_episodes": len(episodes),
        "dq_observe": {
            "mode": idle.get("mode") if idle else "observe_only",
            "hard_eject": bool(idle.get("hard_eject")) if idle else False,
            "n_idle_flagged": _i(idle.get("n_idle_flagged")) if idle else len(idle_flagged),
            "idle_flagged_pairs": idle_flagged,
            "note": "DQ candidates only — hard eject stays OFF until Brad GO.",
        },
        "dashboard": {
            "ready_for_pane": True,
            "title": "Promote graduation",
            "subtitle": go["plain_english"],
            "tiles": [
                {"id": "seated", "label": "Seated", "value": funnel.get("n_seated"), "tone": "info"},
                {
                    "id": "fill_rate",
                    "label": "Fill|sig",
                    "value": funnel.get("rate_fill_given_signal"),
                    "tone": "warn" if (funnel.get("rate_fill_given_signal") or 1) < 0.35 else "ok",
                },
                {
                    "id": "win_seat",
                    "label": "Win|seat",
                    "value": funnel.get("rate_win_given_seat"),
                    "tone": "bad" if (funnel.get("rate_win_given_seat") or 0) == 0 else "ok",
                },
                {
                    "id": "hit7",
                    "label": "Paper hit7",
                    "value": paper.get("hit_rate_positive_7d"),
                    "tone": "bad" if (paper.get("hit_rate_positive_7d") or 0) < 0.4 else "ok",
                },
                {
                    "id": "claim",
                    "label": "Claim OK",
                    "value": paper.get("claim_allowed"),
                    "tone": "ok" if paper.get("claim_allowed") else "muted",
                },
                {
                    "id": "choke",
                    "label": "Choke",
                    "value": choke.get("id"),
                    "tone": "warn",
                },
            ],
            "chart_urls": {
                "funnel": "reports/charts/promote_graduation_funnel_latest.svg",
                "outcomes": "reports/charts/promote_graduation_outcomes_latest.svg",
                "paper": "reports/charts/promote_graduation_paper_latest.svg",
            },
            "api_path_suggestion": "/api/promote-graduation",
        },
        "links": {
            "pick_ledger": str(PICK_LEDGER.relative_to(ROOT)),
            "graduation": str(GRAD_LATEST.relative_to(ROOT)),
            "summary": str(PICK_SUMMARY.relative_to(ROOT)),
            "spine": "data/state/platform_metrics_spine_latest.json",
        },
        "actions_taken": [],
    }

    # series (include current as pending crumb view)
    if write:
        charts.mkdir(parents=True, exist_ok=True)
        state.mkdir(parents=True, exist_ok=True)
        reports.mkdir(parents=True, exist_ok=True)

        funnel_svg = render_funnel_svg(funnel)
        outcomes_svg = render_outcomes_svg(episodes)
        paper_svg = render_paper_bars_svg(episodes)

        f_funnel = charts / "promote_graduation_funnel_latest.svg"
        f_out = charts / "promote_graduation_outcomes_latest.svg"
        f_paper = charts / "promote_graduation_paper_latest.svg"
        f_funnel.write_text(funnel_svg)
        f_out.write_text(outcomes_svg)
        f_paper.write_text(paper_svg)

        payload["charts"] = {
            "funnel_svg": str(f_funnel.relative_to(root)),
            "outcomes_svg": str(f_out.relative_to(root)),
            "paper_svg": str(f_paper.relative_to(root)),
        }

        if append_history:
            crumb_path = state / "promote_graduation_crumbs.jsonl"
            cr = append_crumb(payload, path=crumb_path)
            payload["crumb"] = cr
            payload["actions_taken"] = list(payload.get("actions_taken") or []) + [
                f"crumb_append:{cr.get('date')}"
            ]

        payload["series"] = series_from_crumbs(state / "promote_graduation_crumbs.jsonl")

        latest = state / "promote_graduation_chart_latest.json"
        latest.write_text(json.dumps(payload, indent=2, default=str) + "\n")
        md_path = reports / "PROMOTE_GRADUATION_CHART_LATEST.md"
        md_path.write_text(render_markdown(payload))
        payload["wrote"] = {
            "json": str(latest.relative_to(root)),
            "md": str(md_path.relative_to(root)),
            "charts": payload.get("charts"),
        }
    else:
        payload["charts"] = {
            "funnel_svg_inline_ok": True,
            "outcomes_svg_inline_ok": True,
            "paper_svg_inline_ok": True,
        }
        payload["series"] = {"n_points": 0, "points": [], "note": "write=False — no crumb"}

    return payload


def render_markdown(payload: Mapping[str, Any]) -> str:
    funnel = payload.get("funnel") or {}
    paper = payload.get("paper") or {}
    go = payload.get("go_nogo") or {}
    choke = payload.get("choke_point") or {}
    timing = payload.get("timing") or {}
    episodes = payload.get("episodes") or []
    dq = payload.get("dq_observe") or {}
    charts = payload.get("charts") or {}
    series = payload.get("series") or {}

    lines = [
        "# Promote graduation chart",
        "",
        f"**as_of:** `{payload.get('as_of')}`  ",
        f"**measure_only:** `{payload.get('measure_only')}` · **no_live_writes:** `{payload.get('no_live_writes')}`",
        "",
        "## Go / no-go",
        "",
        f"| Gate | Value |",
        f"|------|-------|",
        f"| Promote talk OK | `{go.get('promote_talk_ok')}` |",
        f"| Claim allowed | `{go.get('claim_allowed')}` |",
        f"| Money path hint | **{go.get('money_path_hint')}** |",
        f"| Choke | `{choke.get('id')}` — {choke.get('why')} |",
        "",
        f"_{go.get('plain_english')}_",
        "",
        "## Funnel",
        "",
        f"seat **{funnel.get('n_seated')}** → signal **{funnel.get('n_signaled')}** "
        f"({funnel.get('rate_signal_given_seat')}) → fill **{funnel.get('n_filled')}** "
        f"({funnel.get('rate_fill_given_signal')}|sig) → win **{funnel.get('n_filled_win')}** / "
        f"loss **{funnel.get('n_filled_loss')}** (win|seat={funnel.get('rate_win_given_seat')})",
        "",
        f"Stages: `{json.dumps(funnel.get('stages') or {})}`",
        "",
        "## Paper scoreboard (≠ fill PnL)",
        "",
        f"- n_picks=`{paper.get('n_picks')}` open=`{paper.get('open_picks')}`",
        f"- avg 7d ret=`{paper.get('avg_ret_7d_pct')}`% · excess7=`{paper.get('avg_excess_7d_pct')}`%",
        f"- hit_rate_7d=`{paper.get('hit_rate_positive_7d')}`",
        f"- claim_allowed=`{paper.get('claim_allowed')}` bar=`{paper.get('claim_bar')}`",
        "",
        "## Timing",
        "",
        f"- median h→signal=`{timing.get('median_hours_to_signal')}` (n={timing.get('n_with_signal_latency')})",
        f"- median h→fill=`{timing.get('median_hours_to_fill')}` (n={timing.get('n_with_fill_latency')})",
        "",
        "## Charts",
        "",
        f"- funnel: `{charts.get('funnel_svg')}`",
        f"- outcomes: `{charts.get('outcomes_svg')}`",
        f"- paper 7d: `{charts.get('paper_svg')}`",
        "",
        f"Series points: **{series.get('n_points')}** (daily crumbs)",
        "",
        "## Episodes",
        "",
        "| promoted | add | rm | stage | h→sig | h→fill | pnl | paper7d | class |",
        "|----------|-----|----|-------|-------|--------|-----|---------|-------|",
    ]
    for e in episodes:
        lines.append(
            "| {p} | {a} | {r} | `{s}` | {hs} | {hf} | {pnl} | {p7} | `{oc}` |".format(
                p=str(e.get("promoted_at") or "")[:10],
                a=e.get("add_pair") or "—",
                r=e.get("remove_pair") or "—",
                s=e.get("stage"),
                hs=e.get("hours_to_first_signal") if e.get("hours_to_first_signal") is not None else "—",
                hf=e.get("hours_to_first_fill") if e.get("hours_to_first_fill") is not None else "—",
                pnl=e.get("realized_pnl_sum") if e.get("realized_pnl_sum") is not None else "—",
                p7=e.get("paper_ret_7d_pct") if e.get("paper_ret_7d_pct") is not None else "—",
                oc=e.get("outcome_class"),
            )
        )
    lines += [
        "",
        "## DQ observe (not auto-eject)",
        "",
        f"- mode=`{dq.get('mode')}` hard_eject=`{dq.get('hard_eject')}`",
        f"- idle_flagged ({dq.get('n_idle_flagged')}): {', '.join(dq.get('idle_flagged_pairs') or []) or '—'}",
        "",
        "## Dashboard readiness",
        "",
        f"- ready_for_pane=`{(payload.get('dashboard') or {}).get('ready_for_pane')}`",
        f"- suggested API: `{(payload.get('dashboard') or {}).get('api_path_suggestion')}`",
        "",
        "_Spine never auto-promotes or hard-ejects. P2 is justify/optimize only._",
        "",
    ]
    return "\n".join(lines)


def short_board(payload: Mapping[str, Any]) -> str:
    go = payload.get("go_nogo") or {}
    funnel = payload.get("funnel") or {}
    paper = payload.get("paper") or {}
    choke = payload.get("choke_point") or {}
    return "\n".join(
        [
            "promote-graduation-chart",
            f"talk={go.get('promote_talk_ok')} claim={go.get('claim_allowed')} path={go.get('money_path_hint')}",
            f"seat={funnel.get('n_seated')}→sig={funnel.get('n_signaled')}→fill={funnel.get('n_filled')}→win={funnel.get('n_filled_win')} choke={choke.get('id')}",
            f"paper_hit7={paper.get('hit_rate_positive_7d')} avg7={paper.get('avg_ret_7d_pct')}",
            go.get("plain_english") or "",
        ]
    )
