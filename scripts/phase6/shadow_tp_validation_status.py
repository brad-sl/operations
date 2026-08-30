#!/usr/bin/env python3
"""Shadow TP validation reporter — HISTORICAL / READ-ONLY.

SSOT rules (Brad 2026-08-29):
  Policy mode  → config/exit_automation.json only
  Runtime book → data/state/shadow_tp_status.json  (writer: phase6/core/shadow_tp.py runner only)
  This script  → reports/* + shadow_tp_validation_*.json ONLY

NEVER writes:
  - config/*
  - data/state/shadow_tp_status.json
  - any production trading settings

Window completed 2026-08-28. Daily cron is paused/archived. Manual runs OK for forensics.
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
STATUS_PATH = ROOT / "data" / "state" / "shadow_tp_status.json"  # READ ONLY
REPORT_PATH = ROOT / "reports" / "SHADOW_TP_VALIDATION_LATEST.md"
CFG_PATH = ROOT / "config" / "exit_automation.json"  # READ ONLY

EPISODE_GAP = timedelta(minutes=30)

# Paths this reporter is allowed to write (report surfaces only).
_ALLOWED_WRITE_ROOTS = (
    LATEST_PATH,
    REPORT_PATH,
    WINDOW_PATH,  # archive metadata only; never production knobs
)


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


def _assert_report_only_write(path: Path) -> None:
    """Hard guard: refuse any write outside report/validation artifact paths."""
    resolved = path.resolve()
    allowed = {p.resolve() for p in _ALLOWED_WRITE_ROOTS}
    if resolved not in allowed:
        raise RuntimeError(
            f"REFUSED write to {resolved} — validation reporter is report-only "
            f"(allowed: {[str(p) for p in _ALLOWED_WRITE_ROOTS]})"
        )
    # Never under config/
    if "config" in resolved.parts and resolved.parts[resolved.parts.index("config")] == "config":
        # path contains a config segment as a directory component under project
        try:
            cfg_root = (ROOT / "config").resolve()
            if str(resolved).startswith(str(cfg_root)):
                raise RuntimeError(f"REFUSED config write: {resolved}")
        except ValueError:
            pass
    if resolved.name == "shadow_tp_status.json":
        raise RuntimeError("REFUSED runtime SSOT write: shadow_tp_status.json")


def _write_report_json(path: Path, payload: Dict[str, Any]) -> None:
    _assert_report_only_write(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")


def _write_report_text(path: Path, text: str) -> None:
    _assert_report_only_write(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_window() -> Dict[str, Any]:
    if WINDOW_PATH.exists():
        try:
            return json.loads(WINDOW_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def load_policy_tp() -> Dict[str, Any]:
    """Read-only policy SSOT."""
    if not CFG_PATH.exists():
        return {}
    try:
        cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
        return cfg.get("take_profit") or {}
    except Exception:
        return {}


def live_tp_active(tp: Dict[str, Any]) -> bool:
    mode = str(tp.get("mode") or "off").lower().strip()
    if mode != "live":
        return False
    return bool(tp.get("live_market_exit")) or bool(tp.get("live_attach_on_buy"))


def archive_window_if_needed(window: Dict[str, Any]) -> Dict[str, Any]:
    """Mark completed validation window as archived. Does not touch runtime SSOT."""
    if not window:
        return window
    if window.get("archived"):
        return window
    end = _parse_ts(window.get("target_end_at"))
    if end and _now() >= end:
        window = dict(window)
        window["archived"] = True
        window["archived_at"] = _now().isoformat()
        window["archive_note"] = (
            "Trial window ended. Live TP policy is config/exit_automation.json — "
            "not this file. Reporter must not write shadow_tp_status or config."
        )
        # Preserve historical intent; do not rewrite live_orders from frozen trial
        # into a claim about current product state.
        window["historical_trial_live_orders"] = window.get("live_orders", False)
        window["note_current"] = (
            "ARCHIVED. Do not treat live_orders here as product mode. "
            "Read exit_automation.json take_profit.mode + live_market_exit."
        )
        _write_report_json(WINDOW_PATH, window)
    return window


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
    """READ-ONLY runtime snapshot from shadow_tp_status.json. Never runs TP cycle."""
    if not STATUS_PATH.exists():
        return {"error": "shadow_tp_status.json missing", "n_signals": 0, "signals": [], "marks": []}
    try:
        st = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        return {"error": str(e), "n_signals": 0, "signals": [], "marks": []}
    return {
        "mode": st.get("mode"),
        "live_market_exit": st.get("live_market_exit"),
        "live_attach_on_buy": st.get("live_attach_on_buy"),
        "n_signals": st.get("n_signals") or 0,
        "signals": st.get("signals") or [],
        "marks": st.get("marks") or [],
        "promotion_hint": st.get("promotion_hint"),
        "as_of": st.get("as_of"),
        "source": "shadow_tp_status.json (read-only)",
    }


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

    tp = load_policy_tp()
    open_book = open_book_snapshot()
    live_on = live_tp_active(tp)
    window_done = elapsed_days >= target_days and len(episodes) >= 5

    return {
        "schema": "shadow_tp_validation_latest_v1",
        "as_of": now.isoformat(),
        "authority": {
            "policy_ssot": "config/exit_automation.json",
            "runtime_ssot": "data/state/shadow_tp_status.json",
            "this_file": "report only — not product mode",
            "writes_runtime": False,
            "writes_config": False,
        },
        "window": window,
        "window_archived": bool(window.get("archived")),
        "elapsed_days": round(elapsed_days, 2),
        "remaining_days": round(remaining, 2),
        "target_days": target_days,
        # Policy truth (never hardcode OFF)
        "mode": tp.get("mode"),
        "fixed_tp_pct": tp.get("fixed_tp_pct"),
        "trail": tp.get("trail"),
        "live_market_exit": bool(tp.get("live_market_exit")),
        "live_attach_on_buy": bool(tp.get("live_attach_on_buy")),
        "live_tp_active": live_on,
        "brad_promoted_at": tp.get("brad_promoted_at"),
        "events_raw_in_window": len(events),
        "episodes_unique": len(episodes),
        "episodes_by_pair": dict(by_pair),
        "episodes_by_kind": dict(by_kind),
        "episodes_tail": episodes[-12:],
        "open_book": open_book,
        "gates": {
            "days_met": elapsed_days >= target_days,
            "episodes_met": len(episodes) >= 5,
            "window_complete": window_done,
            "auto_promote": False,
            # Historical trial gate only — NOT a live flip request when already live
            "ready_for_brad_review": False if live_on else window_done,
            "review_note": (
                "Live TP already ON (policy SSOT). Historical window is closed — no review needed."
                if live_on
                else "Trial window metrics only; flip requires Brad OK + config write by operator."
            ),
        },
        "fingerprint": f"{len(episodes)}|{round(elapsed_days,1)}|{open_book.get('n_signals')}|live={int(live_on)}",
    }


def to_md(st: Dict[str, Any]) -> str:
    g = st.get("gates") or {}
    ob = st.get("open_book") or {}
    live = st.get("live_tp_active")
    lines = [
        f"# Shadow TP validation — {str(st.get('as_of'))[:10]} (ARCHIVED reporter)",
        "",
        "**Authority:** policy = `config/exit_automation.json` · runtime = `shadow_tp_status.json` · this file = metrics only.",
        "",
        f"**Day {st.get('elapsed_days')} / {st.get('target_days')}** · remaining ~{st.get('remaining_days')}d · window_archived={st.get('window_archived')}",
        f"- policy mode=`{st.get('mode')}` · live_market_exit={st.get('live_market_exit')} · **live_tp_active={live}**",
        f"- Unique episodes (≥30m): **{st.get('episodes_unique')}** (raw ticks {st.get('events_raw_in_window')})",
        f"- By pair: {st.get('episodes_by_pair')}",
        f"- By kind: {st.get('episodes_by_kind')}",
        f"- Open would-fire now: **{ob.get('n_signals')}** · source={ob.get('source')}",
        f"- Review gate: **{g.get('ready_for_brad_review')}** — {g.get('review_note')}",
        "",
        "## Rule",
        "Reporter never writes config or runtime SSOT. Daily cron paused post-promote.",
        "",
    ]
    return "\n".join(lines)


def telegram_body(st: Dict[str, Any]) -> str:
    """Forensic body only — does not claim authority on live mode incorrectly."""
    g = st.get("gates") or {}
    ob = st.get("open_book") or {}
    live = st.get("live_tp_active")
    live_s = "ON" if live else "OFF"
    if st.get("window_archived") or live:
        status = f"Live TP: {live_s} (policy SSOT) · trial window ARCHIVED — no action"
    else:
        ready = "YES — review" if g.get("ready_for_brad_review") else "collecting"
        status = f"Live TP: {live_s} · trial: {ready}"
    return (
        f"SHADOW TP metrics (report-only) day {st.get('elapsed_days')}/{st.get('target_days')}\n"
        f"Episodes (unique): {st.get('episodes_unique')} · open would-fire: {ob.get('n_signals')}\n"
        f"Pairs: {st.get('episodes_by_pair') or '—'}\n"
        f"{status}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Historical Shadow TP trial metrics. Report-only; never writes runtime/config."
    )
    ap.add_argument(
        "--start-window",
        action="store_true",
        help="DISABLED post-promote. Refuses to reset or write runtime.",
    )
    ap.add_argument("--notify", action="store_true", help="Print Telegram body to stdout")
    ap.add_argument(
        "--quiet-if-same",
        action="store_true",
        help="Print nothing if fingerprint unchanged",
    )
    ap.add_argument(
        "--write-reports",
        action="store_true",
        default=True,
        help="Write validation_latest.json + MD (default on)",
    )
    ap.add_argument("--no-write-reports", action="store_true", help="Stdout only")
    args = ap.parse_args()

    if args.start_window:
        print(
            "REFUSED: --start-window disabled. Validation window is historical. "
            "Do not reset first_shadow_at / shadow_tp_status from this reporter.",
            file=sys.stderr,
        )
        return 2

    window = load_window()
    if not window.get("started_at"):
        print("No validation window on disk — nothing to report (trial never started).", file=sys.stderr)
        return 0

    window = archive_window_if_needed(window)
    st = build_status(window)

    if not args.no_write_reports:
        prev_fp = None
        if LATEST_PATH.exists():
            try:
                prev_fp = json.loads(LATEST_PATH.read_text(encoding="utf-8")).get("fingerprint")
            except Exception:
                pass
        _write_report_json(LATEST_PATH, st)
        _write_report_text(REPORT_PATH, to_md(st))
        changed = prev_fp != st.get("fingerprint")
    else:
        changed = True

    if args.quiet_if_same and not changed:
        return 0
    if args.notify or changed or not args.quiet_if_same:
        print(telegram_body(st))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
