#!/usr/bin/env python3
"""
Basket pick metrics — track promoted membership changes and later outcomes.

Ledger: data/state/basket_pick_metrics.jsonl  (one JSON object per line)
Summary: data/state/basket_pick_metrics_latest.json

A "pick" is a promoted add (and optional remove). We snapshot baseline market
stats at promote time, then refresh marks at 1d/3d/7d/14d/30d for methodology
validation — not for auto-trading.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = PROJECT_ROOT / "data" / "state"
LEDGER_PATH = STATE_DIR / "basket_pick_metrics.jsonl"
LATEST_PATH = STATE_DIR / "basket_pick_metrics_latest.json"
SUMMARY_PATH = STATE_DIR / "basket_pick_metrics_summary.json"

UA = {"User-Agent": "phase6-basket-metrics/1.0"}
HORIZONS_HOURS = (24, 72, 168, 336, 720)  # 1d 3d 7d 14d 30d


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(UA)
    return s


def fetch_spot_and_stats(product_id: str, session: Optional[requests.Session] = None) -> Dict[str, Any]:
    sess = session or _session()
    out: Dict[str, Any] = {"product_id": product_id, "ok": False}
    try:
        t = sess.get(f"https://api.exchange.coinbase.com/products/{product_id}/ticker", timeout=20)
        st = sess.get(f"https://api.exchange.coinbase.com/products/{product_id}/stats", timeout=20)
        if t.status_code == 200:
            td = t.json()
            out["price"] = float(td.get("price") or 0.0)
            out["bid"] = float(td.get("bid") or 0.0) if td.get("bid") else None
            out["ask"] = float(td.get("ask") or 0.0) if td.get("ask") else None
        if st.status_code == 200:
            sd = st.json()
            last = float(sd.get("last") or out.get("price") or 0.0)
            open_ = float(sd.get("open") or 0.0)
            high = float(sd.get("high") or 0.0)
            low = float(sd.get("low") or 0.0)
            vol = float(sd.get("volume") or 0.0)
            out["last"] = last
            out["open_24h"] = open_
            out["high_24h"] = high
            out["low_24h"] = low
            out["volume_base_24h"] = vol
            mid = (high + low) / 2.0 if high and low else last
            out["volume_quote_24h_est"] = vol * mid if mid else None
            out["ret_24h"] = ((last - open_) / open_) if open_ else None
        out["ok"] = bool(out.get("price") or out.get("last"))
        if out.get("price") is None and out.get("last") is not None:
            out["price"] = out["last"]
    except Exception as e:
        out["error"] = str(e)[:200]
    out["ts"] = _utc_now()
    return out


@dataclass
class BasketPickRecord:
    pick_id: str
    promoted_at: str
    source: str  # discovery_pipeline | pool_cycling | manual
    add_pair: str
    remove_pair: Optional[str]
    add_score: Optional[float] = None
    remove_score: Optional[float] = None
    delta: Optional[float] = None
    reason: str = ""
    remove_held_usd_at_promote: float = 0.0
    residual_hold_allowed: bool = False
    methodology: Dict[str, Any] = field(default_factory=dict)
    baseline_add: Dict[str, Any] = field(default_factory=dict)
    baseline_remove: Dict[str, Any] = field(default_factory=dict)
    basket_before: List[str] = field(default_factory=list)
    basket_after: List[str] = field(default_factory=list)
    marks: Dict[str, Any] = field(default_factory=dict)  # horizon_key -> mark
    status: str = "open"  # open | closed | superseded
    notes: List[str] = field(default_factory=list)


def append_pick(record: BasketPickRecord, path: Path = LEDGER_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(asdict(record), default=str) + "\n")
    LATEST_PATH.write_text(json.dumps(asdict(record), indent=2, default=str) + "\n")
    return path


def load_ledger(path: Path = LEDGER_PATH) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def rewrite_ledger(rows: Sequence[Dict[str, Any]], path: Path = LEDGER_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")


def _horizon_key(hours: int) -> str:
    if hours % 24 == 0:
        d = hours // 24
        return f"{d}d"
    return f"{hours}h"


def refresh_open_picks(path: Path = LEDGER_PATH) -> Dict[str, Any]:
    """Update mark-to-market for open picks at due horizons."""
    rows = load_ledger(path)
    sess = _session()
    now = datetime.now(timezone.utc)
    updated = 0
    for row in rows:
        if row.get("status") != "open":
            continue
        try:
            t0 = datetime.fromisoformat(str(row["promoted_at"]).replace("Z", "+00:00"))
        except Exception:
            continue
        age_h = (now - t0).total_seconds() / 3600.0
        marks = dict(row.get("marks") or {})
        add = row.get("add_pair")
        base_px = float((row.get("baseline_add") or {}).get("price") or 0.0)
        if not add or base_px <= 0:
            continue
        changed = False
        for h in HORIZONS_HOURS:
            key = _horizon_key(h)
            if key in marks:
                continue
            if age_h + 0.5 < h:  # not yet due (30m slack)
                continue
            spot = fetch_spot_and_stats(add, sess)
            px = float(spot.get("price") or 0.0)
            if px <= 0:
                continue
            ret = (px / base_px) - 1.0
            marks[key] = {
                "ts": spot.get("ts"),
                "price": px,
                "ret_vs_promote": round(ret, 6),
                "ret_pct": round(ret * 100.0, 3),
                "age_hours": round(age_h, 2),
            }
            # Optional: remove-pair counterfactual if we have baseline
            rem = row.get("remove_pair")
            br = row.get("baseline_remove") or {}
            br_px = float(br.get("price") or 0.0)
            if rem and br_px > 0:
                rspot = fetch_spot_and_stats(rem, sess)
                rpx = float(rspot.get("price") or 0.0)
                if rpx > 0:
                    rret = (rpx / br_px) - 1.0
                    marks[key]["remove_ret_pct"] = round(rret * 100.0, 3)
                    marks[key]["excess_vs_remove_pct"] = round((ret - rret) * 100.0, 3)
            changed = True
        if changed:
            row["marks"] = marks
            row["last_refresh"] = _utc_now()
            updated += 1
    if updated:
        rewrite_ledger(rows, path)
    summary = summarize(rows)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2) + "\n")
    return {"updated": updated, "open": summary.get("open_picks"), "summary": summary}


def summarize(rows: Optional[Sequence[Dict[str, Any]]] = None) -> Dict[str, Any]:
    rows = list(rows if rows is not None else load_ledger())
    open_rows = [r for r in rows if r.get("status") == "open"]
    by_h: Dict[str, List[float]] = {}
    excess: Dict[str, List[float]] = {}
    for r in rows:
        for k, m in (r.get("marks") or {}).items():
            if isinstance(m, dict) and m.get("ret_pct") is not None:
                by_h.setdefault(k, []).append(float(m["ret_pct"]))
            if isinstance(m, dict) and m.get("excess_vs_remove_pct") is not None:
                excess.setdefault(k, []).append(float(m["excess_vs_remove_pct"]))

    def _avg(xs: List[float]) -> Optional[float]:
        return round(sum(xs) / len(xs), 3) if xs else None

    return {
        "ts": _utc_now(),
        "n_picks": len(rows),
        "open_picks": len(open_rows),
        "adds": [r.get("add_pair") for r in rows],
        "avg_ret_pct_by_horizon": {k: _avg(v) for k, v in sorted(by_h.items())},
        "avg_excess_vs_remove_pct": {k: _avg(v) for k, v in sorted(excess.items())},
        "hit_rate_positive_7d": (
            round(
                sum(1 for x in by_h.get("7d", []) if x > 0) / len(by_h["7d"]),
                3,
            )
            if by_h.get("7d")
            else None
        ),
        "methodology_note": (
            "Success = add_pair mark-to-market vs promote baseline; "
            "excess_vs_remove = add return minus removed pair return (counterfactual stay)."
        ),
    }


def record_promotion(
    *,
    add_pair: str,
    remove_pair: Optional[str],
    basket_before: Sequence[str],
    basket_after: Sequence[str],
    source: str = "pool_cycling",
    add_score: Optional[float] = None,
    remove_score: Optional[float] = None,
    delta: Optional[float] = None,
    reason: str = "",
    remove_held_usd: float = 0.0,
    residual_hold_allowed: bool = False,
    methodology: Optional[Dict[str, Any]] = None,
    notes: Optional[List[str]] = None,
) -> BasketPickRecord:
    sess = _session()
    base_add = fetch_spot_and_stats(add_pair, sess)
    base_rem = fetch_spot_and_stats(remove_pair, sess) if remove_pair else {}
    rec = BasketPickRecord(
        pick_id=str(uuid.uuid4())[:12],
        promoted_at=_utc_now(),
        source=source,
        add_pair=add_pair,
        remove_pair=remove_pair,
        add_score=add_score,
        remove_score=remove_score,
        delta=delta,
        reason=reason,
        remove_held_usd_at_promote=float(remove_held_usd or 0.0),
        residual_hold_allowed=residual_hold_allowed,
        methodology=methodology or {},
        baseline_add=base_add,
        baseline_remove=base_rem,
        basket_before=list(basket_before),
        basket_after=list(basket_after),
        notes=list(notes or []),
    )
    append_pick(rec)
    summarize()  # refresh summary file
    SUMMARY_PATH.write_text(json.dumps(summarize(), indent=2) + "\n")
    return rec
