"""P3 — Regime arm switch success metrics (measure-only).

Joins switch crumbs with:
  - forward BTC tape alignment (did preferred arm stay regime-correct?)
  - arm CF/HC board preferred vs alternative (paper L1 — not live PnL)
  - flip episode ledger

Honesty
-------
- No live book PnL claims.
- L1 CF excess = ADD vs REMOVE paper, not wallet.
- claim_allowed only when N complete flips meet bar.
- live_membership_swaps never touched.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from phase6.core.paths import PROJECT_ROOT

SCHEMA = "regime_arm_switch_metrics_v1"
CLAIM_MIN_FLIPS = 5
CLAIM_MIN_COMPLETE_FWD = 3  # flips with ≥3d forward tape scored

ARM_UP_CHOP = "rel_btc_stable"
ARM_DOWN = "risk_adj_mom"
ALT = {ARM_UP_CHOP: ARM_DOWN, ARM_DOWN: ARM_UP_CHOP}

ENTER_UP_PCT = 2.0
ENTER_DOWN_PCT = -2.0

CRUMBS = PROJECT_ROOT / "data" / "state" / "regime_arm_switch_crumbs.jsonl"
LATEST_SWITCH = PROJECT_ROOT / "data" / "state" / "regime_arm_switch_latest.json"
HC_BOARD = PROJECT_ROOT / "data" / "state" / "basket_swap_confidence_board_latest.json"
BTC_CACHE = PROJECT_ROOT / "data" / "ohlcv" / "BTC-USD_1d_coinbase.json"
OUT_JSON = PROJECT_ROOT / "data" / "state" / "regime_arm_switch_metrics_latest.json"
OUT_MD = PROJECT_ROOT / "reports" / "REGIME_ARM_SWITCH_METRICS_LATEST.md"
OUT_CRUMBS = PROJECT_ROOT / "data" / "state" / "regime_arm_switch_metrics_crumbs.jsonl"
CHART_DIR = PROJECT_ROOT / "reports" / "charts"
FUNNEL_SVG = CHART_DIR / "regime_arm_switch_timeline_latest.svg"
COMPARE_SVG = CHART_DIR / "regime_arm_switch_compare_latest.svg"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse_ts(v: Any) -> Optional[datetime]:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _f(v: Any) -> Optional[float]:
    try:
        if v is None or isinstance(v, bool):
            return None
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    except Exception:
        return None


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_jsonl(path: Path) -> List[dict]:
    if not path.exists():
        return []
    out: List[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if isinstance(row, dict):
                out.append(row)
    except Exception:
        return []
    return out


def load_switch_crumbs(path: Path = CRUMBS) -> List[dict]:
    return _read_jsonl(path)


def extract_flip_events(crumbs: Sequence[Mapping[str, Any]]) -> List[dict]:
    """Deduped real flips: preferred arm changes (decision_written preferred)."""
    flips: List[dict] = []
    last_arm: Optional[str] = None
    for c in crumbs:
        arm = str(c.get("preferred_arm") or "").strip() or None
        ts = _parse_ts(c.get("ts") or c.get("as_of"))
        if not arm or ts is None:
            continue
        changed = bool(c.get("changed") or c.get("flipped"))
        written = bool(c.get("decision_written"))
        prev_field = c.get("previous_preferred_arm")
        if last_arm is None:
            # Genesis: first written/changed adopt counts as a flip episode
            # (even if an earlier non-written crumb already showed the arm).
            if written and changed:
                flips.append(_flip_row(c, ts, prev=str(prev_field) if prev_field else None))
                last_arm = arm
            elif written or changed:
                # observe arm without counting until a real write/change boundary
                last_arm = arm
            else:
                last_arm = arm
            continue
        if arm != last_arm:
            # any arm transition is a flip; prefer written rows
            flips.append(_flip_row(c, ts, prev=last_arm))
            last_arm = arm
        elif written and changed and not flips:
            # same arm but first explicit apply after observe-only crumbs
            flips.append(_flip_row(c, ts, prev=str(prev_field) if prev_field else None))
    # de-dupe same day+arm+prev
    seen = set()
    out: List[dict] = []
    for f in flips:
        key = (f["day"], f["preferred_arm"], f.get("previous_arm"))
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def _flip_row(c: Mapping[str, Any], ts: datetime, *, prev: Optional[str]) -> dict:
    arm = str(c.get("preferred_arm") or "")
    return {
        "ts": _iso(ts),
        "day": ts.date().isoformat(),
        "preferred_arm": arm,
        "previous_arm": prev or c.get("previous_preferred_arm"),
        "alt_arm": ALT.get(arm),
        "sticky_tape": c.get("sticky_tape") or c.get("raw_tape"),
        "raw_tape": c.get("raw_tape"),
        "btc_ret_7d_pct": _f(c.get("btc_ret_7d_pct")),
        "decision_written": bool(c.get("decision_written")),
        "dwell_blocked": bool(c.get("dwell_blocked")),
        "mode": c.get("mode"),
    }


def load_btc_daily(path: Path = BTC_CACHE) -> List[dict]:
    raw = _read_json(path)
    rows: List[dict] = []
    if isinstance(raw, list):
        src = raw
    elif isinstance(raw, dict) and isinstance(raw.get("candles"), list):
        src = raw["candles"]
    else:
        src = []
    for r in src:
        if not isinstance(r, (list, dict)):
            continue
        if isinstance(r, list) and len(r) >= 5:
            # coinbase REST array: [time, low, high, open, close, volume]
            try:
                t = int(r[0])
                close = float(r[4])
            except Exception:
                continue
            day = datetime.fromtimestamp(t, tz=timezone.utc).date().isoformat()
            rows.append({"day": day, "close": close, "t": t})
        elif isinstance(r, dict):
            close = _f(r.get("close") or r.get("c"))
            day = ""
            if r.get("day") or r.get("date"):
                day = str(r.get("day") or r.get("date") or "")[:10]
            elif r.get("time") is not None:
                tv = r.get("time")
                if isinstance(tv, (int, float)):
                    day = datetime.fromtimestamp(int(tv), tz=timezone.utc).date().isoformat()
                else:
                    dt = _parse_ts(tv)
                    if dt is not None:
                        day = dt.date().isoformat()
            if day and close is not None:
                rows.append({"day": day, "close": close})
    rows.sort(key=lambda x: x["day"])
    by: Dict[str, dict] = {}
    for r in rows:
        by[r["day"]] = r
    return [by[k] for k in sorted(by)]


def btc_fwd_return(daily: Sequence[Mapping[str, Any]], day: str, horizon_d: int) -> Optional[float]:
    idx = {str(r["day"]): i for i, r in enumerate(daily)}
    i = idx.get(day)
    if i is None:
        return None
    j = i + horizon_d
    if j >= len(daily):
        return None
    c0 = _f(daily[i].get("close"))
    c1 = _f(daily[j].get("close"))
    if c0 is None or c1 is None or c0 == 0:
        return None
    return (c1 / c0 - 1.0) * 100.0


def arm_for_ret(ret7: Optional[float]) -> Optional[str]:
    if ret7 is None:
        return None
    if ret7 >= ENTER_UP_PCT:
        return ARM_UP_CHOP
    if ret7 <= ENTER_DOWN_PCT:
        return ARM_DOWN
    return ARM_UP_CHOP  # chop → stable


def tape_from_ret(ret7: Optional[float]) -> str:
    if ret7 is None:
        return "unknown"
    if ret7 >= ENTER_UP_PCT:
        return "btc_up"
    if ret7 <= ENTER_DOWN_PCT:
        return "btc_down"
    return "btc_chop"


def score_flip_forward(
    flip: Mapping[str, Any],
    daily: Sequence[Mapping[str, Any]],
) -> dict:
    """Did the chosen arm match the *realized* forward BTC regime?"""
    day = str(flip.get("day") or "")
    arm = str(flip.get("preferred_arm") or "")
    alt = ALT.get(arm)
    out: Dict[str, Any] = {
        **dict(flip),
        "fwd": {},
        "alignment": {},
        "winner_vs_alt": None,
        "complete_3d": False,
        "complete_7d": False,
    }
    for h in (1, 3, 7):
        ret = btc_fwd_return(daily, day, h)
        out["fwd"][f"{h}d"] = ret
        # realized tape from forward return (same thresholds on horizon return)
        realized_arm = None
        if ret is not None:
            if ret >= ENTER_UP_PCT * (h / 7.0) if h != 7 else ret >= ENTER_UP_PCT:
                # scale thresholds roughly for shorter horizons
                thr_up = ENTER_UP_PCT * (h / 7.0)
                thr_dn = ENTER_DOWN_PCT * (h / 7.0)
            else:
                thr_up = ENTER_UP_PCT * (h / 7.0)
                thr_dn = ENTER_DOWN_PCT * (h / 7.0)
            if ret >= thr_up:
                realized_arm = ARM_UP_CHOP
            elif ret <= thr_dn:
                realized_arm = ARM_DOWN
            else:
                realized_arm = ARM_UP_CHOP  # chop → stable
        match = (realized_arm == arm) if realized_arm else None
        alt_match = (realized_arm == alt) if realized_arm and alt else None
        out["alignment"][f"{h}d"] = {
            "fwd_btc_ret_pct": ret,
            "realized_preferred_by_tape": realized_arm,
            "chosen_match": match,
            "alt_would_match": alt_match,
            "chosen_beats_alt": (match is True and alt_match is False)
            if match is not None
            else None,
        }
        if h == 3 and ret is not None:
            out["complete_3d"] = True
        if h == 7 and ret is not None:
            out["complete_7d"] = True
    # primary success: 3d chosen_beats_alt or match
    a3 = out["alignment"].get("3d") or {}
    if a3.get("chosen_beats_alt") is True:
        out["winner_vs_alt"] = "chosen"
    elif a3.get("chosen_match") is True:
        out["winner_vs_alt"] = "chosen_tie_chop"
    elif a3.get("alt_would_match") is True:
        out["winner_vs_alt"] = "alt"
    elif a3.get("chosen_match") is False:
        out["winner_vs_alt"] = "miss"
    return out


def hc_arm_map(board: Any) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    if not isinstance(board, dict):
        return out
    arms = board.get("arms")
    if isinstance(arms, list):
        for a in arms:
            if isinstance(a, dict) and a.get("arm"):
                out[str(a["arm"])] = a
    elif isinstance(arms, dict):
        for k, v in arms.items():
            if isinstance(v, dict):
                out[str(k)] = {**v, "arm": k}
    return out


def compare_arms_hc(board: Any, preferred: str, alt: Optional[str] = None) -> dict:
    m = hc_arm_map(board)
    alt = alt or ALT.get(preferred)
    pref = m.get(preferred) or {}
    alt_row = m.get(alt or "") or {}

    def pack(row: Mapping[str, Any]) -> dict:
        return {
            "arm": row.get("arm"),
            "ex7": _f(row.get("ex7")),
            "hit7": _f(row.get("hit7")),
            "n7": row.get("n7"),
            "sleeve_delta": _f(row.get("sleeve_delta")),
            "high_confidence": bool(row.get("high_confidence")),
            "missing": row.get("missing"),
        }

    p = pack(pref)
    a = pack(alt_row)
    ex_p, ex_a = p.get("ex7"), a.get("ex7")
    leader = None
    if ex_p is not None and ex_a is not None:
        if ex_p > ex_a + 0.05:
            leader = preferred
        elif ex_a > ex_p + 0.05:
            leader = alt
        else:
            leader = "tie"
    return {
        "preferred": p,
        "alt": a,
        "ex7_leader": leader,
        "preferred_is_hc": p.get("high_confidence"),
        "alt_is_hc": a.get("high_confidence"),
        "note": "HC board is rolling L1 CF — not causal proof the flip helped.",
    }


def summarize_episodes(episodes: Sequence[Mapping[str, Any]]) -> dict:
    n = len(episodes)
    n3 = sum(1 for e in episodes if e.get("complete_3d"))
    n7 = sum(1 for e in episodes if e.get("complete_7d"))
    wins = sum(1 for e in episodes if e.get("winner_vs_alt") in ("chosen", "chosen_tie_chop"))
    alt_wins = sum(1 for e in episodes if e.get("winner_vs_alt") == "alt")
    miss = sum(1 for e in episodes if e.get("winner_vs_alt") == "miss")
    # 3d match rate among complete
    match3 = []
    beat3 = []
    for e in episodes:
        a = (e.get("alignment") or {}).get("3d") or {}
        if a.get("chosen_match") is not None:
            match3.append(1.0 if a["chosen_match"] else 0.0)
        if a.get("chosen_beats_alt") is not None:
            beat3.append(1.0 if a["chosen_beats_alt"] else 0.0)
    return {
        "n_flips": n,
        "n_complete_3d": n3,
        "n_complete_7d": n7,
        "n_chosen_ok_3d": wins,
        "n_alt_better_3d": alt_wins,
        "n_miss_3d": miss,
        "match_rate_3d": (sum(match3) / len(match3)) if match3 else None,
        "beat_alt_rate_3d": (sum(beat3) / len(beat3)) if beat3 else None,
        "claim_bar": {
            "min_flips": CLAIM_MIN_FLIPS,
            "min_complete_3d": CLAIM_MIN_COMPLETE_FWD,
        },
        "claim_allowed": bool(
            n >= CLAIM_MIN_FLIPS and n3 >= CLAIM_MIN_COMPLETE_FWD and len(match3) >= CLAIM_MIN_COMPLETE_FWD
        ),
        "N_tag": f"flips={n} complete3d={n3}",
    }


def render_timeline_svg(episodes: Sequence[Mapping[str, Any]], *, w: int = 720, h: int = 160) -> str:
    if not episodes:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">'
            f'<rect width="100%" height="100%" fill="#0f172a"/>'
            f'<text x="24" y="80" fill="#94a3b8" font-family="system-ui" font-size="13">No flip episodes yet</text></svg>'
        )
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        '<rect width="100%" height="100%" rx="12" fill="#0f172a"/>',
        '<text x="20" y="28" fill="#e2e8f0" font-family="system-ui,sans-serif" font-size="14" font-weight="600">Regime arm flips (paper-primary only)</text>',
        f'<text x="20" y="48" fill="#64748b" font-family="system-ui" font-size="11">N={len(episodes)} · green=chosen matched forward tape · rose=alt better · amber=incomplete</text>',
    ]
    y = 95
    x0, x1 = 40, w - 40
    parts.append(f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" stroke="#334155" stroke-width="2"/>')
    n = len(episodes)
    for i, e in enumerate(episodes):
        x = x0 if n == 1 else x0 + (x1 - x0) * (i / (n - 1))
        wres = e.get("winner_vs_alt")
        if wres in ("chosen", "chosen_tie_chop"):
            color = "#34d399"
        elif wres == "alt":
            color = "#fb7185"
        elif wres == "miss":
            color = "#f87171"
        else:
            color = "#fbbf24"
        arm = str(e.get("preferred_arm") or "").replace("_", " ")
        day = str(e.get("day") or "")[5:]
        parts.append(f'<circle cx="{x:.1f}" cy="{y}" r="8" fill="{color}" stroke="#0f172a" stroke-width="2"/>')
        parts.append(
            f'<text x="{x:.1f}" y="{y - 16}" text-anchor="middle" fill="#cbd5e1" font-family="system-ui" font-size="10">{day}</text>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{y + 28}" text-anchor="middle" fill="#94a3b8" font-family="system-ui" font-size="9">{arm[:14]}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def render_compare_svg(cmp: Mapping[str, Any], *, w: int = 720, h: int = 200) -> str:
    return _render_compare_svg_safe(cmp, w=w, h=h)


def build_metrics(
    *,
    crumbs: Optional[Sequence[Mapping[str, Any]]] = None,
    board: Any = None,
    daily: Optional[Sequence[Mapping[str, Any]]] = None,
    switch_latest: Any = None,
    now: Optional[datetime] = None,
    write: bool = True,
    append_history: bool = True,
    root: Path = PROJECT_ROOT,
) -> dict:
    now = now or _now()
    crumbs = list(crumbs if crumbs is not None else load_switch_crumbs(root / "data/state/regime_arm_switch_crumbs.jsonl"))
    board = board if board is not None else _read_json(root / "data/state/basket_swap_confidence_board_latest.json")
    daily = list(daily if daily is not None else load_btc_daily(root / "data/ohlcv/BTC-USD_1d_coinbase.json"))
    switch_latest = switch_latest if switch_latest is not None else _read_json(root / "data/state/regime_arm_switch_latest.json")

    flips = extract_flip_events(crumbs)
    episodes = [score_flip_forward(f, daily) for f in flips]
    summary = summarize_episodes(episodes)

    preferred = None
    if isinstance(switch_latest, dict):
        preferred = switch_latest.get("preferred_arm")
    if not preferred and crumbs:
        preferred = crumbs[-1].get("preferred_arm")
    preferred = str(preferred or ARM_UP_CHOP)
    cmp = compare_arms_hc(board, preferred)

    # activity stats
    n_crumbs = len(crumbs)
    n_changed = sum(1 for c in crumbs if c.get("changed") or c.get("flipped"))
    n_dwell = sum(1 for c in crumbs if c.get("dwell_blocked"))

    go = {
        "claim_allowed": summary["claim_allowed"],
        "success_hint": (
            "ATTENTION_ONLY"
            if not summary["claim_allowed"]
            else (
                "FLIP_OK"
                if (summary.get("match_rate_3d") or 0) >= 0.55
                else "FLIP_WEAK"
            )
        ),
        "live_swaps": False,
        "plain_english": _plain(summary, preferred, cmp, switch_latest),
    }

    charts = {}
    timeline = render_timeline_svg(episodes)
    # fix compare svg label y
    compare = _render_compare_svg_safe(cmp)

    payload = {
        "schema": SCHEMA,
        "as_of": _iso(now),
        "measure_only": True,
        "no_live_writes": True,
        "live_membership_swaps": False,
        "current": {
            "preferred_arm": preferred,
            "sticky_tape": (switch_latest or {}).get("sticky_tape") if isinstance(switch_latest, dict) else None,
            "btc_ret_7d_pct": (switch_latest or {}).get("btc_ret_7d_pct") if isinstance(switch_latest, dict) else None,
            "last_flip_at": (switch_latest or {}).get("last_flip_at") if isinstance(switch_latest, dict) else None,
            "flipped_latest": (switch_latest or {}).get("flipped") if isinstance(switch_latest, dict) else None,
        },
        "activity": {
            "n_crumbs": n_crumbs,
            "n_changed_flags": n_changed,
            "n_dwell_blocked": n_dwell,
            "n_flip_episodes": summary["n_flips"],
        },
        "summary": summary,
        "episodes": episodes,
        "hc_compare": cmp,
        "go_nogo": go,
        "charts": {},
        "dashboard": {
            "title": "Regime arm switch",
            "ready_for_pane": True,
            "tiles": [
                {"id": "preferred", "label": "Paper arm", "value": preferred},
                {"id": "flips", "label": "Flips", "value": summary["n_flips"], "n_tag": summary["N_tag"]},
                {
                    "id": "match3",
                    "label": "3d match",
                    "value": summary.get("match_rate_3d"),
                    "format": "pct",
                },
                {
                    "id": "claim",
                    "label": "Claim",
                    "value": "ON" if summary["claim_allowed"] else "OFF",
                },
                {
                    "id": "ex7_leader",
                    "label": "ex7 leader",
                    "value": cmp.get("ex7_leader"),
                },
            ],
            "honesty": [
                "Paper-primary only — live swaps stay OFF",
                "Forward tape match ≠ live book PnL",
                "Thin N → claim OFF",
            ],
        },
        "actions_taken": [],
    }

    if write:
        charts_dir = root / "reports" / "charts"
        charts_dir.mkdir(parents=True, exist_ok=True)
        t_path = charts_dir / "regime_arm_switch_timeline_latest.svg"
        c_path = charts_dir / "regime_arm_switch_compare_latest.svg"
        t_path.write_text(timeline, encoding="utf-8")
        c_path.write_text(compare, encoding="utf-8")
        payload["charts"] = {
            "timeline_svg": str(t_path.relative_to(root)),
            "compare_svg": str(c_path.relative_to(root)),
        }
        jpath = root / "data" / "state" / "regime_arm_switch_metrics_latest.json"
        mpath = root / "reports" / "REGIME_ARM_SWITCH_METRICS_LATEST.md"
        jpath.parent.mkdir(parents=True, exist_ok=True)
        mpath.parent.mkdir(parents=True, exist_ok=True)
        jpath.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
        mpath.write_text(render_markdown(payload), encoding="utf-8")
        payload["wrote"] = {"json": str(jpath.relative_to(root)), "md": str(mpath.relative_to(root)), **payload["charts"]}
        payload["actions_taken"] = [f"wrote {k}" for k in payload["wrote"]]
        if append_history:
            _append_crumb(root / "data/state/regime_arm_switch_metrics_crumbs.jsonl", payload, now)
    return payload


def _render_compare_svg_safe(cmp: Mapping[str, Any], *, w: int = 720, h: int = 200) -> str:
    p = cmp.get("preferred") or {}
    a = cmp.get("alt") or {}
    bars = [
        ("pref ex7", _f(p.get("ex7")) or 0.0, "#38bdf8"),
        ("alt ex7", _f(a.get("ex7")) or 0.0, "#a78bfa"),
        ("pref hit7%", (_f(p.get("hit7")) or 0.0) * 100.0, "#34d399"),
        ("alt hit7%", (_f(a.get("hit7")) or 0.0) * 100.0, "#f472b6"),
    ]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        '<rect width="100%" height="100%" rx="12" fill="#0f172a"/>',
        '<text x="20" y="28" fill="#e2e8f0" font-family="system-ui" font-size="14" font-weight="600">Preferred vs alt (rolling HC board)</text>',
        f'<text x="20" y="48" fill="#64748b" font-family="system-ui" font-size="11">leader={cmp.get("ex7_leader")} · pref_HC={cmp.get("preferred_is_hc")} · alt_HC={cmp.get("alt_is_hc")} · not live PnL</text>',
    ]
    vals = [b[1] for b in bars]
    mx = max(abs(v) for v in vals) or 1.0
    base_y = 130
    bw = 90
    gap = 40
    x = 60.0
    for label, v, color in bars:
        bh = abs(v) / mx * 60
        y = base_y - bh if v >= 0 else base_y
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw}" height="{max(bh, 1):.1f}" rx="6" fill="{color}" opacity="0.85"/>'
        )
        parts.append(
            f'<text x="{x + bw/2:.1f}" y="{base_y + 24}" text-anchor="middle" fill="#94a3b8" font-family="system-ui" font-size="11">{label}</text>'
        )
        ly = (y - 6) if v >= 0 else (y + bh + 14)
        parts.append(
            f'<text x="{x + bw/2:.1f}" y="{ly:.1f}" text-anchor="middle" fill="#e2e8f0" font-family="system-ui" font-size="11">{v:+.2f}</text>'
        )
        x += bw + gap
    parts.append(f'<line x1="40" y1="{base_y}" x2="{w-40}" y2="{base_y}" stroke="#334155"/>')
    parts.append("</svg>")
    return "\n".join(parts)


def _plain(summary: Mapping[str, Any], preferred: str, cmp: Mapping[str, Any], switch_latest: Any) -> str:
    n = summary.get("n_flips") or 0
    m = summary.get("match_rate_3d")
    m_s = f"{m:.0%}" if isinstance(m, float) else "n/a"
    claim = "claim ON" if summary.get("claim_allowed") else "claim OFF (thin N)"
    leader = cmp.get("ex7_leader")
    tape = ""
    if isinstance(switch_latest, dict):
        tape = f" tape={switch_latest.get('sticky_tape')} ret7={switch_latest.get('btc_ret_7d_pct')}"
    return (
        f"paper arm={preferred}{tape} · flips={n} · 3d-match={m_s} · "
        f"ex7_leader={leader} · {claim}. Not live PnL; swaps stay OFF."
    )


def _append_crumb(path: Path, payload: Mapping[str, Any], now: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    day = now.date().isoformat()
    existing = _read_jsonl(path)
    if any(str(r.get("day")) == day for r in existing):
        # replace same-day
        existing = [r for r in existing if str(r.get("day")) != day]
    row = {
        "day": day,
        "ts": _iso(now),
        "preferred_arm": (payload.get("current") or {}).get("preferred_arm"),
        "n_flips": (payload.get("summary") or {}).get("n_flips"),
        "match_rate_3d": (payload.get("summary") or {}).get("match_rate_3d"),
        "claim_allowed": (payload.get("summary") or {}).get("claim_allowed"),
        "ex7_leader": (payload.get("hc_compare") or {}).get("ex7_leader"),
        "success_hint": (payload.get("go_nogo") or {}).get("success_hint"),
    }
    existing.append(row)
    with path.open("w", encoding="utf-8") as f:
        for r in existing:
            f.write(json.dumps(r, default=str) + "\n")


def render_markdown(payload: Mapping[str, Any]) -> str:
    s = payload.get("summary") or {}
    go = payload.get("go_nogo") or {}
    cur = payload.get("current") or {}
    lines = [
        "# Regime arm switch metrics (P3)",
        "",
        f"_as_of {payload.get('as_of')} · measure-only · live swaps OFF_",
        "",
        "## Go / no-go",
        f"- claim_allowed: **{go.get('claim_allowed')}**",
        f"- success_hint: **{go.get('success_hint')}**",
        f"- {go.get('plain_english')}",
        "",
        "## Current",
        f"- preferred_arm: `{cur.get('preferred_arm')}`",
        f"- sticky_tape: {cur.get('sticky_tape')} · btc_ret_7d={cur.get('btc_ret_7d_pct')}",
        "",
        "## Flip success",
        f"- flips: {s.get('n_flips')} · complete_3d: {s.get('n_complete_3d')} · complete_7d: {s.get('n_complete_7d')}",
        f"- match_rate_3d: {s.get('match_rate_3d')} · beat_alt_rate_3d: {s.get('beat_alt_rate_3d')}",
        f"- N_tag: {s.get('N_tag')}",
        "",
        "## Episodes",
        "| day | arm | tape | ret7 | 3d btc | winner |",
        "|-----|-----|------|------|--------|--------|",
    ]
    for e in payload.get("episodes") or []:
        a3 = (e.get("alignment") or {}).get("3d") or {}
        lines.append(
            f"| {e.get('day')} | `{e.get('preferred_arm')}` | {e.get('sticky_tape')} | "
            f"{e.get('btc_ret_7d_pct')} | {a3.get('fwd_btc_ret_pct')} | {e.get('winner_vs_alt')} |"
        )
    cmp = payload.get("hc_compare") or {}
    lines += [
        "",
        "## HC compare (rolling)",
        f"- ex7_leader: {cmp.get('ex7_leader')}",
        f"- preferred: {cmp.get('preferred')}",
        f"- alt: {cmp.get('alt')}",
        "",
        "## Charts",
    ]
    for k, v in (payload.get("charts") or {}).items():
        lines.append(f"- {k}: `{v}`")
    lines += ["", "---", "_Not live PnL. Not an auto-promote signal._", ""]
    return "\n".join(lines)


def short_board(payload: Mapping[str, Any]) -> str:
    go = payload.get("go_nogo") or {}
    s = payload.get("summary") or {}
    cur = payload.get("current") or {}
    return (
        "regime-arm-switch-metrics\n"
        f"arm={cur.get('preferred_arm')} claim={go.get('claim_allowed')} hint={go.get('success_hint')}\n"
        f"flips={s.get('n_flips')} match3={s.get('match_rate_3d')} beat3={s.get('beat_alt_rate_3d')}\n"
        f"{go.get('plain_english')}"
    )
