"""NEEDLE-04 same-session SL guard (attach deferral).

Sep 9 LINK class: limit_first BUY 16:01 → 3% native SL void 16:07.
`same_session_sl.py` is a ledger metric only — this module is the live guard.

Contract
--------
After a limit_first fill, do **not** attach a stop for MIN_HOLD_MINUTES (60).
A synthetic −3% print at +6 minutes therefore cannot void the bag.
After the window, deferred attaches may proceed (tryout 3% still live policy;
geometry 6–8% is a separate Brad-GO apply — do not write live knobs here).

Core BTC/ETH remain on NEEDLE-03 skip_sl; this guard does not attach 3% to core.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from phase6.core.paths import PROJECT_ROOT, STATE_DIR

SCHEMA = "same_session_sl_guard_v1"
STATE_PATH = STATE_DIR / "same_session_sl_guard.json"
MIN_HOLD_MINUTES = 60.0  # in Brad 30–120m band
TAKER_FEE = 0.009
MAKER_FEE = 0.005
TRYOUT_SL_PCT_LIVE = 0.03
RECOMMENDED_TRYOUT_SL_FLOOR = 0.06
RECOMMENDED_CORE_SL_FLOOR = 0.08

LIMIT_STYLES = frozenset(
    {
        "limit_post_only",
        "limit_gtc",
        "limit_first",
        "limit_first_v1",
    }
)


def _utc(now: Optional[datetime] = None) -> datetime:
    d = now or datetime.now(timezone.utc)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def _parse_ts(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return _utc(raw)
    s = str(raw).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return _utc(datetime.fromisoformat(s))
    except Exception:
        return None


def is_limit_first_style(execution_style: Any) -> bool:
    st = str(execution_style or "").strip().lower()
    if not st:
        return False
    if st in LIMIT_STYLES:
        return True
    return st.startswith("limit") and "market" not in st


def sl_pct_too_tight_vs_fees(
    sl_pct: float,
    *,
    taker_fee: float = TAKER_FEE,
    floor: float = RECOMMENDED_TRYOUT_SL_FLOOR,
) -> bool:
    """True when a hard stop cannot survive Intro taker + the stop itself."""
    try:
        pct = float(sl_pct)
    except (TypeError, ValueError):
        return True
    # Round-trip taker on stop-out ≈ 2 * taker; stop must clear that with room.
    return pct < float(floor) or pct <= (2.0 * float(taker_fee) + 0.02)


def would_same_session_void(
    buy_ts: Any,
    sl_ts: Any,
    *,
    min_hold_minutes: float = MIN_HOLD_MINUTES,
) -> bool:
    """Sep 9 shape: SL fill inside the hold window after the BUY."""
    b = _parse_ts(buy_ts)
    s = _parse_ts(sl_ts)
    if b is None or s is None:
        return False
    delta = s - b
    if delta < timedelta(0):
        return False
    return delta < timedelta(minutes=float(min_hold_minutes))


def _load_state(path: Optional[Path] = None) -> Dict[str, Any]:
    path = path or STATE_PATH
    try:
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return raw
    except Exception:
        pass
    return {"schema": SCHEMA, "pending": {}}


def _save_state(state: Dict[str, Any], path: Optional[Path] = None) -> None:
    path = path or STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    state = dict(state)
    state["schema"] = SCHEMA
    path.write_text(json.dumps(state, indent=2, default=str) + "\n", encoding="utf-8")


def record_limit_first_fill(
    pair: str,
    *,
    fill_ts: Optional[datetime] = None,
    entry_price: float = 0.0,
    size: float = 0.0,
    order_id: Optional[str] = None,
    execution_style: str = "limit_post_only",
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    path = path or STATE_PATH
    p = str(pair or "").strip().upper()
    st = _load_state(path)
    pending = dict(st.get("pending") or {})
    rec = {
        "pair": p,
        "fill_ts": _utc(fill_ts).isoformat().replace("+00:00", "Z"),
        "entry_price": float(entry_price or 0),
        "size": float(size or 0),
        "order_id": str(order_id or "")[:48],
        "execution_style": str(execution_style or ""),
        "min_hold_minutes": MIN_HOLD_MINUTES,
        "status": "deferred",
    }
    pending[p] = rec
    st["pending"] = pending
    _save_state(st, path)
    return rec


def should_defer_sl_attach(
    pair: str,
    *,
    now: Optional[datetime] = None,
    execution_style: Any = None,
    path: Optional[Path] = None,
    min_hold_minutes: float = MIN_HOLD_MINUTES,
) -> Tuple[bool, str, float]:
    """Return (defer, reason, remaining_minutes).

    Defer when this is a limit_first fill still inside the hold window.
    Market IOC is not deferred (Sep 9 class is limit_first).
    """
    path = path or STATE_PATH
    p = str(pair or "").strip().upper()
    if execution_style is not None and not is_limit_first_style(execution_style):
        # Explicit market path — do not apply this guard
        if str(execution_style or "").lower().startswith("market"):
            return False, "market_style", 0.0
    st = _load_state(path)
    rec = (st.get("pending") or {}).get(p)
    if not rec:
        return False, "no_pending_limit_fill", 0.0
    fill = _parse_ts(rec.get("fill_ts"))
    if fill is None:
        return False, "bad_fill_ts", 0.0
    hold = float(rec.get("min_hold_minutes") or min_hold_minutes)
    elapsed_m = (_utc(now) - fill).total_seconds() / 60.0
    remaining = hold - elapsed_m
    if remaining > 1e-9:
        return True, f"limit_first_hold_{hold:g}m", round(remaining, 2)
    return False, "hold_elapsed", 0.0


def mark_attached(pair: str, path: Path = STATE_PATH) -> None:
    p = str(pair or "").strip().upper()
    st = _load_state(path)
    pending = dict(st.get("pending") or {})
    rec = pending.get(p)
    if rec:
        rec["status"] = "attached"
        rec["attached_ts"] = _utc().isoformat().replace("+00:00", "Z")
        pending[p] = rec
        st["pending"] = pending
        _save_state(st, path)


def due_deferred_attaches(
    *,
    now: Optional[datetime] = None,
    path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Pending limit_first fills whose hold window has elapsed."""
    path = path or STATE_PATH
    st = _load_state(path)
    due: List[Dict[str, Any]] = []
    for pair, rec in (st.get("pending") or {}).items():
        if not isinstance(rec, dict):
            continue
        if str(rec.get("status") or "") != "deferred":
            continue
        defer, reason, rem = should_defer_sl_attach(pair, now=now, path=path)
        if not defer:
            due.append(dict(rec))
    return due


def process_deferred_sl_attaches(
    sl_manager: Any,
    *,
    now: Optional[datetime] = None,
    path: Path = STATE_PATH,
) -> List[Dict[str, Any]]:
    """Runner tick: attach due tryout stops. Never touches core skip pairs."""
    out: List[Dict[str, Any]] = []
    if sl_manager is None:
        return out
    core = set()
    try:
        skip_path = PROJECT_ROOT / "data" / "state" / "core_skip_sl_pairs.json"
        if skip_path.exists():
            raw = json.loads(skip_path.read_text())
            core = {str(x).upper() for x in (raw.get("pairs") or [])}
    except Exception:
        core = set()
    for rec in due_deferred_attaches(now=now, path=path):
        pair = str(rec.get("pair") or "").upper()
        row = {"pair": pair, "ok": False, "reason": ""}
        if pair in core:
            row["reason"] = "core_skip"
            out.append(row)
            continue
        entry = float(rec.get("entry_price") or 0)
        size = float(rec.get("size") or 0)
        oid = rec.get("order_id") or None
        if entry <= 0 or size <= 0:
            row["reason"] = "missing_fill"
            out.append(row)
            continue
        try:
            ok = bool(
                sl_manager.attach_stop_loss(
                    pair,
                    entry,
                    size,
                    anchor_entry=entry,
                    order_id=oid,
                    fresh_buy=False,
                )
            )
            row["ok"] = ok
            row["reason"] = "attached" if ok else "attach_false"
            if ok:
                mark_attached(pair, path=path)
        except Exception as e:
            row["reason"] = f"error:{e}"
        out.append(row)
    return out
