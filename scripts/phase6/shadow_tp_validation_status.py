#!/usr/bin/env python3
"""Shadow TP 7d validation status — episode-aware, no live orders.

Writes:
  data/state/shadow_tp_validation_window.json
  data/state/shadow_tp_validation_latest.json
  reports/SHADOW_TP_VALIDATION_LATEST.md

Stdout: short Telegram body when --notify (always) or when --quiet-if-same and changed.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

WINDOW_PATH = ROOT / "data" / "state" / "shadow_tp_validation_window.json"
LATEST_PATH = ROOT / "data" / "state" / "shadow_tp_validation_latest.json"
EVENTS_PATH = ROOT / "data" / "state" / "shadow_tp_events.jsonl"
STATUS_PATH = ROOT / "data" / "state" / "shadow_tp_status.json"
REPORT_PATH = ROOT / "reports" / "SHADOW_TP_VALIDATION_LATEST.md"
CFG_PATH = ROOT / "config" / "exit_automation.json"

EPISODE_GAP = timedelta(minutes=30)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(raw: Any) -> Optional[datetime]:
    if not raw:
        return None
    try:
        t = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t
    except Exception:
        return None


def load_window() -> Dict[str, Any]:
    if WINDOW_PATH.exists():
        try:
            return json.loads(WINDOW_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def ensure_window(start_fresh: bool = False) -> Dict[str, Any]:
    w = load_window()
    if start_fresh or not w.get("started_at"):
        now = _now()
        w = {
            "schema": "shadow_tp_validation_window_v1",
            "started_at": now.isoformat(),
            "target_days": 7,
            "target_end_at": (now + timedelta(days=7)).isoformat(),
            "fixed_tp_pct": 0.06,
            "live_orders": False,
            "note": "Brad 2026-08-21: run shadow 1 week to validate +6% bank opportunity. No auto promote.",
            "brad_intent": "shadow_week_then_review",
        }
        WINDOW_PATH.parent.mkdir(parents=True, exist_ok=True)
        WINDOW_PATH.write_text(json.dumps(w, indent=2) + "\n", encoding="utf-8")
        # Align promo clock to this window (honest days)
        st: Dict[str, Any] = {}
        if STATUS_PATH.exists():
            try:
                st = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
            except Exception:
                st = {}
        st["first_shadow_at"] = w["started_at"]
        st["would_fire_count_total"] = 0
        st["validation_window_reset_at"] = w["started_at"]
        st["validation_window_note"] = "Reset for 7d Brad validation; raw pre-window totals void"
        STATUS_PATH.write_text(json.dumps(st, indent=2) + "\n", encoding="utf-8")
    return w


def load_events_since(start: datetime) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not EVENTS_PATH.exists():
        return rows
    for line in EVENTS_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        ts = _parse_ts(o.get("ts") or o.get("as_of") or o.get("timestamp"))
        if ts is None or ts < start:
            continue
        rows.append(o)
    return rows


def episodes_from_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Collapse spam ticks into pair+kind episodes with ≥30m gap."""
    by_key: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for e in events:
        pair = str(e.get("pair") or e.get("product_id") or "?")
        kind = str(e.get("kind") or e.get("signal_kind") or e.get("type") or "would_fire")
        # nested signal
        if "signal" in e and isinstance(e["signal"], dict):
            pair = str(e["signal"].get("pair") or pair)
            kind = str(e["signal"].get("kind") or kind)
        ts = _parse_ts(e.get("ts") or e.get("as_of") or e.get("timestamp"))
        if not ts:
            continue
        by_key[(pair, kind)].append({**e, "_ts": ts, "_pair": pair, "_kind": kind})

    episodes: List[Dict[str, Any]] = []
    for (pair, kind), items in by_key.items():
        items.sort(key=lambda x: x["_ts"])
        last: Optional[datetime] = None
        for it in items:
            ts = it["_ts"]
            if last is None or (ts - last) >= EPISODE_GAP:
                episodes.append(
                    {
                        "pair": pair,
                        "kind": kind,
                        "ts": ts.isoformat(),
                        "r": it.get("r") or (it.get("signal") or {}).get("r"),
                        "mark_px": it.get("mark_px") or (it.get("signal") or {}).get("mark_px"),
                        "usd": it.get("usd") or (it.get("signal") or {}).get("usd"),
                    }
                )
                last = ts
    episodes.sort(key=lambda x: x["ts"])
    return episodes


def open_book_snapshot() -> Dict[str, Any]:
    try:
        from phase6.core.shadow_tp import run_shadow_tp_cycle

        live = json.loads((ROOT / "data/state/phase6_live_state.json").read_text(encoding="utf-8"))
        held_usd: Dict[str, float] = {}
        prices: Dict[str, float] = {}
        positions: Dict[str, Any] = {}
        for p in live.get("trading_positions") or live.get("positions") or []:
            if not isinstance(p, dict):
                continue
            pair = p.get("pair") or p.get("product_id")
            usd = float(p.get("value_usd") or p.get("usd_value") or p.get("usd") or 0)
            px = float(p.get("current_price") or p.get("price") or 0)
            entry = float(p.get("entry_price") or p.get("avg_entry") or p.get("cost_basis") or 0)
            qty = float(p.get("quantity") or p.get("size") or p.get("qty") or 0)
            if pair and usd >= 25 and px > 0:
                held_usd[pair] = usd
                prices[pair] = px
                positions[pair] = {"entry_price": entry, "quantity": qty, "usd": usd}
        res = run_shadow_tp_cycle(held_usd, prices, positions=positions)
        sigs = []
        for s in res.get("signals") or []:
            if hasattr(s, "__dict__"):
                s = dict(s.__dict__)
            sigs.append(s)
        marks = []
        for m in res.get("marks") or []:
            if hasattr(m, "__dict__"):
                m = dict(m.__dict__)
            marks.append(m)
        return {
            "mode": res.get("mode"),
            "n_signals": res.get("n_signals"),
            "signals": sigs,
            "marks": marks,
            "promotion_hint": res.get("promotion_hint"),
        }
    except Exception as e:
        return {"error": str(e)}


def build_status(window: Dict[str, Any]) -> Dict[str, Any]:
    start = _parse_ts(window.get("started_at")) or _now()
    target_days = int(window.get("target_days") or 7)
    end = _parse_ts(window.get("target_end_at")) or (start + timedelta(days=target_days))
    now = _now()
    elapsed_days = max(0.0, (now - start).total_seconds() / 86400.0)
    remaining = max(0.0, (end - now).total_seconds() / 86400.0)

    events = load_events_since(start)
    episodes = episodes_from_events(events)
    by_pair: Dict[str, int] = defaultdict(int)
    by_kind: Dict[str, int] = defaultdict(int)
    for ep in episodes:
        by_pair[ep["pair"]] += 1
        by_kind[ep["kind"]] += 1

    cfg = {}
    if CFG_PATH.exists():
        try:
            cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    tp = cfg.get("take_profit") or {}
    open_book = open_book_snapshot()

    ready = elapsed_days >= target_days and len(episodes) >= 5
    return {
        "schema": "shadow_tp_validation_latest_v1",
        "as_of": now.isoformat(),
        "window": window,
        "elapsed_days": round(elapsed_days, 2),
        "remaining_days": round(remaining, 2),
        "target_days": target_days,
        "mode": tp.get("mode"),
        "fixed_tp_pct": tp.get("fixed_tp_pct"),
        "trail": tp.get("trail"),
        "live_orders": False,
        "events_raw_in_window": len(events),
        "episodes_unique": len(episodes),
        "episodes_by_pair": dict(by_pair),
        "episodes_by_kind": dict(by_kind),
        "episodes_tail": episodes[-12:],
        "open_book": open_book,
        "gates": {
            "days_met": elapsed_days >= target_days,
            "episodes_met": len(episodes) >= 5,
            "path_study_design_shadow": True,
            "auto_promote": False,
            "ready_for_brad_review": ready,
        },
        "fingerprint": f"{len(episodes)}|{round(elapsed_days,1)}|{open_book.get('n_signals')}",
    }


def to_md(st: Dict[str, Any]) -> str:
    g = st.get("gates") or {}
    ob = st.get("open_book") or {}
    lines = [
        f"# Shadow TP validation — {str(st.get('as_of'))[:10]}",
        "",
        f"**Day {st.get('elapsed_days')} / {st.get('target_days')}** · remaining ~{st.get('remaining_days')}d",
        f"- mode=`{st.get('mode')}` · fixed_tp={st.get('fixed_tp_pct')} · live orders: **false**",
        f"- Unique episodes (≥30m): **{st.get('episodes_unique')}** (raw ticks {st.get('events_raw_in_window')})",
        f"- By pair: {st.get('episodes_by_pair')}",
        f"- By kind: {st.get('episodes_by_kind')}",
        f"- Open would-fire now: **{ob.get('n_signals')}** · { [ (s.get('pair'), s.get('kind'), round(float(s.get('r') or 0)*100,1)) for s in (ob.get('signals') or []) ] }",
        f"- Ready for Brad review: **{g.get('ready_for_brad_review')}** (days={g.get('days_met')}, episodes≥5={g.get('episodes_met')})",
        "",
        "## Rule",
        "No live TP. Review only after 7d + human OK.",
        "",
    ]
    return "\n".join(lines)


def telegram_body(st: Dict[str, Any]) -> str:
    g = st.get("gates") or {}
    ob = st.get("open_book") or {}
    sigs = ob.get("signals") or []
    sig_bits = []
    for s in sigs[:6]:
        try:
            r = float(s.get("r") or 0) * 100
        except Exception:
            r = 0
        sig_bits.append(f"{s.get('pair')} {s.get('kind')} +{r:.1f}%")
    ready = "YES — review now" if g.get("ready_for_brad_review") else "no (still collecting)"
    return (
        f"SHADOW TP validation day {st.get('elapsed_days')}/{st.get('target_days')}\n"
        f"Episodes (unique): {st.get('episodes_unique')} · open would-fire: {ob.get('n_signals')}\n"
        f"Pairs: {st.get('episodes_by_pair') or '—'}\n"
        f"Now: {', '.join(sig_bits) if sig_bits else 'none'}\n"
        f"Live TP: OFF · Ready for review: {ready}"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-window", action="store_true", help="Reset/start 7d validation window")
    ap.add_argument("--notify", action="store_true", help="Always print Telegram body to stdout")
    ap.add_argument(
        "--quiet-if-same",
        action="store_true",
        help="Print nothing if fingerprint unchanged (for silent cron)",
    )
    args = ap.parse_args()

    window = ensure_window(start_fresh=args.start_window)
    st = build_status(window)
    LATEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    prev_fp = None
    if LATEST_PATH.exists():
        try:
            prev_fp = json.loads(LATEST_PATH.read_text(encoding="utf-8")).get("fingerprint")
        except Exception:
            pass
    LATEST_PATH.write_text(json.dumps(st, indent=2, default=str) + "\n", encoding="utf-8")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(to_md(st), encoding="utf-8")

    changed = prev_fp != st.get("fingerprint")
    if args.quiet_if_same and not changed and not st.get("gates", {}).get("ready_for_brad_review"):
        return 0
    if args.notify or changed or st.get("gates", {}).get("ready_for_brad_review"):
        print(telegram_body(st))
    elif not args.quiet_if_same:
        print(telegram_body(st))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
