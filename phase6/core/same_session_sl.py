"""
Same-session BUY → stop_loss_exchange metric (P6-SAME-SESSION-SL-METRIC-20260813).

Ledger-only. Counts pairs where a BUY is followed by stop_loss_exchange
within a short window (default 2h; also report <5m). Not a trade signal.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEDGER = ROOT / "trades" / "phase6_trades.jsonl"
DEFAULT_STATE = ROOT / "data" / "state" / "same_session_sl_latest.json"

BUY_REASONS = frozenset(
    {
        "buy",
        "rebalance_buy",
        "rotation_buy",
        "manual_buy",
        "",  # some historical BUY rows omit reason
    }
)
SL_REASONS = frozenset(
    {
        "stop_loss_exchange",
        "stop_loss",
        "stop_loss_fill",
        "protective_stop",
    }
)


def _parse_ts(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    s = str(raw).strip()
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


def _is_buy(row: Dict[str, Any]) -> bool:
    if str(row.get("side") or "").upper() != "BUY":
        return False
    reason = str(row.get("reason") or "").strip().lower()
    # Explicit non-buy reasons on BUY side are rare; keep open
    if reason in ("ops_correction",):
        return False
    return True


def _is_sl_sell(row: Dict[str, Any]) -> bool:
    if str(row.get("side") or "").upper() != "SELL":
        return False
    reason = str(row.get("reason") or row.get("exit_reason") or "").strip().lower()
    if reason in SL_REASONS:
        return True
    # Loose match for historical variants
    return "stop_loss" in reason and "exchange" in reason


def load_ledger_rows(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def find_same_session_events(
    rows: Sequence[Dict[str, Any]],
    *,
    window: timedelta = timedelta(hours=2),
    lookback: Optional[timedelta] = timedelta(days=30),
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """
    For each SL sell, find the most recent prior BUY on the same pair within `window`.
    One event per SL fill (not per BUY).
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - lookback if lookback is not None else None

    parsed: List[Tuple[datetime, Dict[str, Any]]] = []
    for row in rows:
        dt = _parse_ts(row.get("timestamp"))
        if dt is None:
            continue
        if cutoff is not None and dt < cutoff:
            continue
        parsed.append((dt, row))
    parsed.sort(key=lambda x: x[0])

    events: List[Dict[str, Any]] = []
    # last buy time per pair
    last_buy: Dict[str, Tuple[datetime, Dict[str, Any]]] = {}

    for dt, row in parsed:
        pair = str(row.get("pair") or "").strip().upper()
        if not pair:
            continue
        if _is_buy(row):
            last_buy[pair] = (dt, row)
            continue
        if not _is_sl_sell(row):
            continue
        buy = last_buy.get(pair)
        if not buy:
            continue
        buy_dt, buy_row = buy
        delta = dt - buy_dt
        if delta < timedelta(0) or delta > window:
            continue
        seconds = delta.total_seconds()
        events.append(
            {
                "pair": pair,
                "buy_ts": buy_dt.isoformat().replace("+00:00", "Z"),
                "sl_ts": dt.isoformat().replace("+00:00", "Z"),
                "delta_seconds": int(seconds),
                "delta_minutes": round(seconds / 60.0, 2),
                "under_5m": seconds < 300,
                "buy_reason": str(buy_row.get("reason") or ""),
                "sl_reason": str(row.get("reason") or row.get("exit_reason") or ""),
                "buy_order_id": str(buy_row.get("order_id") or "")[:36],
                "sl_order_id": str(row.get("order_id") or "")[:36],
            }
        )
    return events


def summarize(
    *,
    ledger_path: Optional[Path] = None,
    window_hours: float = 2.0,
    lookback_days: float = 30.0,
    now: Optional[datetime] = None,
    persist: bool = False,
    state_path: Optional[Path] = None,
) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    ledger = Path(ledger_path) if ledger_path else DEFAULT_LEDGER
    rows = load_ledger_rows(ledger)
    window = timedelta(hours=float(window_hours))
    lookback = timedelta(days=float(lookback_days))
    events = find_same_session_events(
        rows, window=window, lookback=lookback, now=now
    )
    under_5m = [e for e in events if e.get("under_5m")]
    pairs = sorted({e["pair"] for e in events})
    pairs_5m = sorted({e["pair"] for e in under_5m})
    # newest-first examples
    examples = sorted(events, key=lambda e: e.get("sl_ts") or "", reverse=True)[:8]

    payload: Dict[str, Any] = {
        "as_of": now.isoformat().replace("+00:00", "Z"),
        "window_hours": float(window_hours),
        "lookback_days": float(lookback_days),
        "ledger": str(ledger),
        "count_2h": len(events),
        "count_5m": len(under_5m),
        "pairs_2h": pairs,
        "pairs_5m": pairs_5m,
        "examples": examples,
        "sl_reasons_included": sorted(SL_REASONS),
        "note": "BUY then stop_loss_exchange (or stop_loss*) same pair within window — ledger only",
    }
    if persist:
        path = Path(state_path) if state_path else DEFAULT_STATE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        payload["state_path"] = str(path)
    return payload


def format_brief_line(summary: Optional[Dict[str, Any]] = None, **kwargs: Any) -> str:
    """One Health line. Always prints a count (including 0)."""
    s = summary if summary is not None else summarize(**kwargs)
    n = int(s.get("count_2h") or 0)
    n5 = int(s.get("count_5m") or 0)
    pairs = s.get("pairs_2h") or []
    if n == 0:
        return "Same-session SL (<2h): 0"
    pair_s = ", ".join(pairs[:6])
    if len(pairs) > 6:
        pair_s += f" +{len(pairs) - 6}"
    extra = f" | <5m: {n5}" if n5 else ""
    return f"Same-session SL (<2h): {n} ({pair_s}){extra}"


def ops_finding_if_any(
    summary: Optional[Dict[str, Any]] = None,
    *,
    lookback_days: float = 3.0,
) -> Optional[Dict[str, str]]:
    """Optional medium finding for ops triage when recent count > 0 (default 3d)."""
    if summary is not None:
        s = summary
        lb = float(summary.get("lookback_days") or lookback_days)
    else:
        s = summarize(persist=False, lookback_days=lookback_days)
        lb = float(lookback_days)
    n = int(s.get("count_2h") or 0)
    if n <= 0:
        return None
    pairs = ", ".join((s.get("pairs_2h") or [])[:8]) or "?"
    return {
        "finding": f"Same-session BUY→SL (<2h, {lb:g}d): {n} event(s) — {pairs}",
        "priority": "medium",
        "evidence": str(DEFAULT_STATE),
    }


if __name__ == "__main__":
    s = summarize(persist=True)
    print(format_brief_line(s))
    print(json.dumps({k: s[k] for k in ("count_2h", "count_5m", "pairs_2h", "as_of")}, indent=2))
