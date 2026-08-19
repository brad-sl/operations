#!/usr/bin/env python3
"""GAP-02: Fleet manufactured-loss KPI — BUY→SL same-session + post-fix audit.

Ledger-only. Multi-window (7d / 30d) + since armed-stop ship (2026-08-13).
Writes:
  data/state/fleet_wound_kpi_latest.json
  data/state/fleet_wound_kpi_alert.json  (only on breach, else cleared/absent flag)
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from phase6.core.same_session_sl import (
    DEFAULT_LEDGER,
    find_same_session_events,
    load_ledger_rows,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATE = ROOT / "data/state/fleet_wound_kpi_latest.json"
DEFAULT_ALERT = ROOT / "data/state/fleet_wound_kpi_alert.json"

# Hard [ARMED-STOP] race fix shipped
ARMED_STOP_FIX_TS = datetime(2026, 8, 13, 0, 0, tzinfo=timezone.utc)

# Product thresholds (fleet): 0 new same-session wounds expected post-fix
THRESHOLD_7D = 0
THRESHOLD_30D = 0
THRESHOLD_POST_FIX = 0


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def window_events(
    rows: Sequence[Dict[str, Any]],
    *,
    lookback: timedelta,
    window: timedelta = timedelta(hours=2),
    now: Optional[datetime] = None,
    since: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    events = find_same_session_events(
        rows, window=window, lookback=lookback, now=now
    )
    if since is None:
        return list(events)
    out = []
    for e in events:
        sl_ts = e.get("sl_ts")
        if not sl_ts:
            continue
        s = str(sl_ts).replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if dt >= since:
            out.append(e)
    return out


def classify(
    *,
    count_7d: int,
    count_30d: int,
    count_post_fix: int,
    count_5m_7d: int,
    count_5m_post_fix: int = 0,
    threshold_7d: int = THRESHOLD_7D,
    threshold_30d: int = THRESHOLD_30D,
    threshold_post_fix: int = THRESHOLD_POST_FIX,
) -> Dict[str, Any]:
    breaches: List[str] = []
    if count_post_fix > threshold_post_fix:
        breaches.append(
            f"post_fix_same_session_sl={count_post_fix}>{threshold_post_fix}"
        )
    if count_5m_post_fix > 0:
        breaches.append(f"post_fix_under_5m_sl={count_5m_post_fix}>0")
    if count_7d > threshold_7d:
        breaches.append(f"7d_same_session_sl={count_7d}>{threshold_7d}")
    if count_30d > threshold_30d:
        breaches.append(f"30d_same_session_sl={count_30d}>{threshold_30d}")
    if count_5m_7d > 0 and count_5m_post_fix == 0:
        breaches.append(f"7d_under_5m_pre_fix_residual={count_5m_7d}")

    # True regression = wounds at/after armed-stop fix (incl. <5m post-fix)
    if count_post_fix > threshold_post_fix or count_5m_post_fix > 0:
        decision = "breach"
        go = (
            "ALERT — same-session BUY→SL after armed-stop fix; "
            "investigate rebalance gate miss"
        )
        flag = "NEEDS_VALIDATE"
        severity = (
            "high" if (count_5m_post_fix > 0 or count_post_fix >= 2) else "medium"
        )
    elif count_7d > threshold_7d and count_post_fix == 0:
        decision = "watch_pre_fix_residual"
        go = (
            "WATCH — 7d still shows pre-fix BUY→SL residual; "
            "post-fix window clean. Re-check as calendar rolls."
        )
        flag = "OK"
        severity = "low"
    elif count_30d > threshold_30d:
        decision = "watch_historical"
        go = (
            "WATCH — 30d has wounds but 7d/post-fix clean "
            "(pre-fix history; keep monitoring)"
        )
        flag = "OK"
        severity = "low"
    else:
        decision = "pass"
        go = "OK — 0 manufactured BUY→SL wounds in 7d / post-fix windows (ledger)"
        flag = "OK"
        severity = "none"

    return {
        "decision": decision,
        "go_no_go": go,
        "flag": flag,
        "severity": severity,
        "breaches": breaches,
        "pass": decision == "pass",
    }


def compute(
    *,
    ledger_path: Optional[Path] = None,
    now: Optional[datetime] = None,
    window_hours: float = 2.0,
    fix_ts: Optional[datetime] = None,
    persist: bool = False,
    state_path: Optional[Path] = None,
    alert_path: Optional[Path] = None,
    account_id: str = "primary",
) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    fix_ts = fix_ts or ARMED_STOP_FIX_TS
    ledger = Path(ledger_path) if ledger_path else DEFAULT_LEDGER
    rows = load_ledger_rows(ledger)
    window = timedelta(hours=float(window_hours))

    e7 = window_events(
        rows, lookback=timedelta(days=7), window=window, now=now
    )
    e30 = window_events(
        rows, lookback=timedelta(days=30), window=window, now=now
    )
    # Post-fix: look back enough to cover fix→now, filter since fix
    since_fix = fix_ts
    lookback_post = max(timedelta(days=7), now - fix_ts + timedelta(days=1))
    e_post = window_events(
        rows,
        lookback=lookback_post,
        window=window,
        now=now,
        since=since_fix,
    )

    def _pack(ev: List[Dict[str, Any]]) -> Dict[str, Any]:
        u5 = [x for x in ev if x.get("under_5m")]
        pairs = sorted({x["pair"] for x in ev})
        return {
            "count": len(ev),
            "count_under_5m": len(u5),
            "pairs": pairs,
            "examples": sorted(ev, key=lambda x: x.get("sl_ts") or "", reverse=True)[
                :8
            ],
        }

    w7 = _pack(e7)
    w30 = _pack(e30)
    wfix = _pack(e_post)
    cls = classify(
        count_7d=w7["count"],
        count_30d=w30["count"],
        count_post_fix=wfix["count"],
        count_5m_7d=w7["count_under_5m"],
        count_5m_post_fix=wfix["count_under_5m"],
    )

    payload: Dict[str, Any] = {
        "schema": "fleet_wound_kpi_v1",
        "gap_id": "P6-SCALE-GAP-02-FLEET-WOUND-KPI-20260816",
        "as_of": _iso(now),
        "account_id": account_id,
        "ledger": str(ledger),
        "window_hours": float(window_hours),
        "armed_stop_fix_ts": _iso(fix_ts),
        "thresholds": {
            "7d": THRESHOLD_7D,
            "30d": THRESHOLD_30D,
            "post_fix": THRESHOLD_POST_FIX,
            "under_5m_7d": 0,
        },
        "windows": {
            "d7": w7,
            "d30": w30,
            "post_armed_stop_fix": wfix,
        },
        "classification": cls,
        "decision": cls["decision"],
        "go_no_go": cls["go_no_go"],
        "flag": cls["flag"],
        "note": (
            "Manufactured wound = BUY then stop_loss* same pair within window. "
            "Single-ledger today; account_id reserved for multi-tenant rollup."
        ),
        "fleet_accounts": [
            {
                "account_id": account_id,
                "count_7d": w7["count"],
                "count_30d": w30["count"],
                "count_post_fix": wfix["count"],
                "decision": cls["decision"],
            }
        ],
    }

    if persist:
        sp = Path(state_path) if state_path else DEFAULT_STATE
        ap = Path(alert_path) if alert_path else DEFAULT_ALERT
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        payload["state_path"] = str(sp)
        if cls["decision"] == "breach":
            alert = {
                "schema": "fleet_wound_kpi_alert_v1",
                "as_of": payload["as_of"],
                "severity": cls["severity"],
                "decision": cls["decision"],
                "go_no_go": cls["go_no_go"],
                "breaches": cls["breaches"],
                "windows": {
                    "d7_count": w7["count"],
                    "d30_count": w30["count"],
                    "post_fix_count": wfix["count"],
                    "d7_under_5m": w7["count_under_5m"],
                },
                "pairs_7d": w7["pairs"],
                "state_path": str(sp),
            }
            ap.write_text(json.dumps(alert, indent=2) + "\n", encoding="utf-8")
            payload["alert_path"] = str(ap)
            payload["alert_active"] = True
        else:
            payload["alert_active"] = False
            if ap.exists():
                # Clear stale alert so ops doesn't chase ghosts
                try:
                    ap.unlink()
                except Exception:
                    pass
    return payload


def format_brief_line(summary: Optional[Dict[str, Any]] = None, **kwargs: Any) -> str:
    s = summary if summary is not None else compute(persist=False, **kwargs)
    w = s.get("windows") or {}
    d7 = (w.get("d7") or {}).get("count", 0)
    d30 = (w.get("d30") or {}).get("count", 0)
    pf = (w.get("post_armed_stop_fix") or {}).get("count", 0)
    dec = s.get("decision") or "?"
    return f"Fleet wounds 7d={d7} 30d={d30} post_fix={pf} · {dec}"


def render_md(s: Dict[str, Any]) -> str:
    w = s.get("windows") or {}
    lines = [
        "# Fleet wound KPI (GAP-02)",
        "",
        f"**As of:** {s.get('as_of')}  ",
        f"**Decision:** `{s.get('decision')}` · **Flag:** `{s.get('flag')}`  ",
        f"**Go/no-go:** {s.get('go_no_go')}  ",
        "",
        "| Window | Count | Under 5m | Pairs |",
        "|--------|-------|----------|-------|",
    ]
    for key, label in (
        ("d7", "7d"),
        ("d30", "30d"),
        ("post_armed_stop_fix", "post armed-stop fix"),
    ):
        b = w.get(key) or {}
        pairs = ", ".join((b.get("pairs") or [])[:8]) or "—"
        lines.append(
            f"| {label} | {b.get('count')} | {b.get('count_under_5m')} | {pairs} |"
        )
    lines.extend(
        [
            "",
            f"Armed-stop fix clock: `{s.get('armed_stop_fix_ts')}`  ",
            f"Alert active: **{s.get('alert_active')}**  ",
            "",
            str(s.get("note") or ""),
            "",
        ]
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--persist", action="store_true", default=True)
    ap.add_argument("--no-persist", action="store_true")
    args = ap.parse_args()
    persist = not args.no_persist
    s = compute(persist=persist)
    print(format_brief_line(s))
    print(json.dumps({k: s[k] for k in ("decision", "flag", "go_no_go", "alert_active")}, indent=2))
    md_path = ROOT / "reports/FLEET_WOUND_KPI_LATEST.md"
    md_path.write_text(render_md(s), encoding="utf-8")
    print(f"wrote {md_path}")
    if s.get("state_path"):
        print(f"wrote {s['state_path']}")
    if s.get("alert_path"):
        print(f"ALERT {s['alert_path']}")
