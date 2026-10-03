"""Unified tryout seat ledger — one read API for open shells + day burn + ghosts.

SSOT for operator/Signals/ops triage. Does **not** place orders.
Combines:
  • open lots registry (tryout_scale_up_open_lots.json)
  • live held notional
  • quality_tryout day seat burn (regime_cash_policy.count_new_seat_buys_today)
  • first_fill open concurrent count
  • scale-window board (would_eject)
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

from phase6.core.paths import PROJECT_ROOT

logger = logging.getLogger(__name__)

SCHEMA = "tryout_seat_ledger_v1"
STATE_DIR = PROJECT_ROOT / "data" / "state"
OPEN_LOTS_PATH = STATE_DIR / "tryout_scale_up_open_lots.json"
OPEN_LOTS_LOCK_PATH = STATE_DIR / "tryout_scale_up_open_lots.lock"
LATEST_PATH = STATE_DIR / "tryout_seat_ledger_latest.json"
SCALE_WINDOW_LATEST = STATE_DIR / "tryout_scale_window_latest.json"
GHOST_ARCHIVE_PATH = STATE_DIR / "tryout_open_lot_ghosts.jsonl"

# Held below this is dust / not a shell seat for inventory
MIN_HELD_USD = 15.0
# Registry row with held under this + not live = ghost candidate
GHOST_HELD_MAX_USD = 12.0

BALLAST: Set[str] = {
    "BTC-USD",
    "BTC-USDC",
    "ETH-USD",
    "ETH-USDC",
    "PAXG-USD",
    "PAXG-USDC",
    "USDC-USD",
    "USD-USD",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso(dt: Optional[datetime] = None) -> str:
    d = dt or _utc_now()
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.isoformat()


def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _norm_pair(pair: str) -> str:
    p = str(pair or "").strip().upper().replace("_", "-")
    if not p:
        return ""
    if "-" not in p:
        p = f"{p}-USD"
    return p


def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception as e:
        logger.debug("load %s: %s", path, e)
    return default


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n")


class _OpenLotsFileLock:
    """Best-effort exclusive lock for open_lots.json (POSIX flock; no-op fallback)."""

    def __init__(self, lock_path: Path = OPEN_LOTS_LOCK_PATH, timeout_s: float = 5.0):
        self.lock_path = lock_path
        self.timeout_s = timeout_s
        self._fd: Optional[int] = None

    def __enter__(self) -> "_OpenLotsFileLock":
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = os.open(str(self.lock_path), os.O_CREAT | os.O_RDWR, 0o644)
        deadline = time.time() + self.timeout_s
        while True:
            try:
                import fcntl

                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except ImportError:
                # Non-POSIX: skip lock rather than block money path
                return self
            except (BlockingIOError, OSError):
                if time.time() >= deadline:
                    logger.warning("open_lots lock timeout after %.1fs — proceeding unlocked", self.timeout_s)
                    return self
                time.sleep(0.05)

    def __exit__(self, *args: Any) -> None:
        if self._fd is not None:
            try:
                import fcntl

                fcntl.flock(self._fd, fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                os.close(self._fd)
            except Exception:
                pass
            self._fd = None


def load_open_lots_raw() -> Dict[str, Any]:
    reg = _load_json(OPEN_LOTS_PATH, {"schema": "tryout_scale_up_v1", "lots": {}})
    if not isinstance(reg, dict):
        return {"schema": "tryout_scale_up_v1", "lots": {}}
    lots = reg.get("lots")
    if not isinstance(lots, dict):
        reg["lots"] = {}
    return reg


def write_open_lots_raw(reg: Dict[str, Any]) -> None:
    """Atomic-ish write under flock so purge/close/register don't clobber each other."""
    with _OpenLotsFileLock():
        _write_json(OPEN_LOTS_PATH, reg)


def load_held_usd_map() -> Dict[str, float]:
    """Live held USD by pair (best-effort)."""
    out: Dict[str, float] = {}
    # Prefer scale-up shadow loader (already hardened for dashboard live_state shapes)
    try:
        from phase6.core.tryout_scale_up_shadow import load_live_positions

        for p in load_live_positions() or []:
            if not isinstance(p, dict):
                continue
            pair = _norm_pair(str(p.get("pair") or p.get("product_id") or ""))
            if not pair:
                continue
            out[pair] = _f(p.get("value_usd") or p.get("usd_value") or p.get("market_value"))
    except Exception as e:
        logger.debug("held map via load_live_positions: %s", e)
    if out:
        return out
    # Fallback: phase6_live_state.json direct
    try:
        path = PROJECT_ROOT / "data" / "state" / "phase6_live_state.json"
        raw = _load_json(path, {})
        if isinstance(raw, dict):
            rows = raw.get("trading_positions") or raw.get("positions") or []
            for p in rows if isinstance(rows, list) else []:
                if not isinstance(p, dict):
                    continue
                pair = _norm_pair(str(p.get("pair") or p.get("product_id") or ""))
                if not pair:
                    continue
                usd = p.get("value_usd")
                if usd is None:
                    usd = p.get("usd_value")
                if usd is None:
                    usd = p.get("market_value")
                out[pair] = _f(usd)
    except Exception as e:
        logger.debug("held map fallback: %s", e)
    return out


def _scale_window_by_pair() -> Dict[str, Dict[str, Any]]:
    board = _load_json(SCALE_WINDOW_LATEST, {})
    by: Dict[str, Dict[str, Any]] = {}
    if not isinstance(board, dict):
        return by
    for row in board.get("decisions") or board.get("rows") or []:
        if not isinstance(row, dict):
            continue
        pn = _norm_pair(str(row.get("pair") or ""))
        if pn:
            by[pn] = row
    return by


def classify_scale_path(
    *,
    pair: str,
    lot: Optional[Dict[str, Any]],
    held_usd: float,
    window_row: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return scale_path chip fields for one pair.

    Labels: none | open | pending | live | dead | ghost
    """
    pn = _norm_pair(pair)
    lot = lot if isinstance(lot, dict) else None
    wr = window_row if isinstance(window_row, dict) else {}

    if lot and held_usd < GHOST_HELD_MAX_USD and str(lot.get("status") or "") in (
        "scored",
        "flat_no_sell_row",
        "ghost",
        "closed",
    ):
        return {
            "scale_path": "ghost",
            "scale_path_label": "ghost",
            "live_scaled": bool(lot.get("live_scaled")),
            "paper_scaled": bool(lot.get("paper_scaled") or lot.get("scaled")),
            "would_eject": False,
            "lot_status": lot.get("status"),
            "held_usd": held_usd,
        }

    if lot and held_usd < GHOST_HELD_MAX_USD and not bool(lot.get("live_scaled")):
        # registry without bag
        st = str(lot.get("status") or "")
        if st in ("tryout_open", "paper_open", "") or lot.get("tryout_shell"):
            return {
                "scale_path": "ghost",
                "scale_path_label": "ghost",
                "live_scaled": False,
                "paper_scaled": bool(lot.get("paper_scaled") or lot.get("scaled")),
                "would_eject": False,
                "lot_status": st or "ghost_unheld",
                "held_usd": held_usd,
            }

    would_eject = bool(wr.get("would_eject") or wr.get("status") == "would_eject")
    if would_eject and held_usd >= MIN_HELD_USD:
        return {
            "scale_path": "dead",
            "scale_path_label": "dead",
            "live_scaled": bool((lot or {}).get("live_scaled")),
            "paper_scaled": bool((lot or {}).get("paper_scaled") or (lot or {}).get("scaled")),
            "would_eject": True,
            "eject_reasons": list(wr.get("reasons") or wr.get("eject_reasons") or []),
            "lot_status": (lot or {}).get("status"),
            "held_usd": held_usd,
        }

    if lot and bool(lot.get("live_scaled")) and held_usd >= MIN_HELD_USD:
        return {
            "scale_path": "live",
            "scale_path_label": "live",
            "live_scaled": True,
            "paper_scaled": bool(lot.get("paper_scaled") or lot.get("scaled")),
            "would_eject": False,
            "lot_status": lot.get("status"),
            "held_usd": held_usd,
        }

    if lot and held_usd >= MIN_HELD_USD:
        # open shell — kindling may be pending (Signals doesn't force plan read here)
        paper = bool(lot.get("paper_scaled") or lot.get("scaled"))
        label = "pending" if paper and not lot.get("live_scaled") else "open"
        return {
            "scale_path": label,
            "scale_path_label": label,
            "live_scaled": False,
            "paper_scaled": paper,
            "would_eject": False,
            "lot_status": lot.get("status"),
            "held_usd": held_usd,
            "tryout_shell": bool(lot.get("tryout_shell") or lot.get("tryout_tagged_buy")),
        }

    if held_usd >= MIN_HELD_USD and pn not in BALLAST:
        # held but not in tryout registry (ballast-size alt or untagged)
        return {
            "scale_path": "none",
            "scale_path_label": "none",
            "live_scaled": False,
            "paper_scaled": False,
            "would_eject": False,
            "lot_status": None,
            "held_usd": held_usd,
            "untagged_held": True,
        }

    return {
        "scale_path": "none",
        "scale_path_label": "none",
        "live_scaled": False,
        "paper_scaled": False,
        "would_eject": False,
        "lot_status": (lot or {}).get("status") if lot else None,
        "held_usd": held_usd,
    }


def build_seat_ledger(
    *,
    pairs: Optional[Sequence[str]] = None,
    persist: bool = True,
    held_map: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """One snapshot: open shells, ghosts, day seats, scale_path by pair."""
    now = _utc_now()
    reg = load_open_lots_raw()
    lots = reg.get("lots") if isinstance(reg.get("lots"), dict) else {}
    held = held_map if held_map is not None else load_held_usd_map()
    window_by = _scale_window_by_pair()

    # quality tryout day burn + caps
    seats_today = 0
    max_new = 6
    max_open = 6
    try:
        from phase6.core.regime_cash_policy import count_new_seat_buys_today

        seats_today = int(count_new_seat_buys_today() or 0)
    except Exception as e:
        logger.debug("seat day count: %s", e)
        seats_today = 0
    try:
        # Nested under recovery_soft_down / quality_tryout in regime_cash_policy.json
        pol = _load_json(PROJECT_ROOT / "config" / "regime_cash_policy.json", {})
        qt: Dict[str, Any] = {}
        if isinstance(pol, dict):
            # common nests
            for path_keys in (
                ("quality_tryout",),
                ("recovery_soft_down", "quality_tryout"),
                ("operator_override", "recovery_soft_down_quality_tryout"),
            ):
                cur: Any = pol
                ok = True
                for k in path_keys:
                    if not isinstance(cur, dict) or k not in cur:
                        ok = False
                        break
                    cur = cur[k]
                if ok and isinstance(cur, dict) and (
                    cur.get("max_new_seats_per_day") is not None
                    or cur.get("abs_cap_usd") is not None
                ):
                    qt = cur
                    break
            if not qt:
                # deep search once
                def _find_qt(node: Any) -> Optional[Dict[str, Any]]:
                    if isinstance(node, dict):
                        if "max_new_seats_per_day" in node and (
                            "abs_cap_usd" in node or "max_open_tryout_seats" in node
                        ):
                            return node
                        for v in node.values():
                            found = _find_qt(v)
                            if found:
                                return found
                    return None

                found = _find_qt(pol)
                if found:
                    qt = found
        max_new = int(qt.get("max_new_seats_per_day") or qt.get("max_seats_per_day") or 6)
        max_open = int(qt.get("max_open_tryout_seats") or max_new)
    except Exception as e:
        logger.debug("seat caps: %s", e)

    # first-fill concurrent
    first_fill_open: List[str] = []
    try:
        from phase6.core.first_fill_probation import count_open_first_fill_seats

        pos = {k: v for k, v in held.items() if _f(v) >= MIN_HELD_USD}
        first_fill_open = list(count_open_first_fill_seats(pos) or [])
    except Exception as e:
        logger.debug("first_fill open: %s", e)

    by_pair: Dict[str, Any] = {}
    open_shells: List[str] = []
    ghosts: List[str] = []
    dead: List[str] = []
    live_kindled: List[str] = []

    universe: Set[str] = set()
    if pairs:
        universe |= {_norm_pair(p) for p in pairs if p}
    if isinstance(lots, dict):
        universe |= {_norm_pair(p) for p in lots.keys()}
    universe |= {
        _norm_pair(p)
        for p, u in held.items()
        if _f(u) >= MIN_HELD_USD and _norm_pair(p) not in BALLAST
    }
    universe.discard("")

    for pn in sorted(universe):
        raw_lot = lots.get(pn) if isinstance(lots, dict) else None
        lot = raw_lot if isinstance(raw_lot, dict) else None
        hu = _f(held.get(pn))
        sp = classify_scale_path(
            pair=pn, lot=lot, held_usd=hu, window_row=window_by.get(pn)
        )
        row = {
            "pair": pn,
            "held_usd": round(hu, 2),
            "lot": {
                k: lot.get(k)
                for k in (
                    "status",
                    "shell_usd",
                    "entry_ts",
                    "entry_price",
                    "live_scaled",
                    "paper_scaled",
                    "scaled",
                    "source",
                    "tryout_shell",
                )
                if lot and k in lot
            }
            if lot
            else None,
            **sp,
        }
        by_pair[pn] = row
        path = sp.get("scale_path")
        if path == "ghost":
            ghosts.append(pn)
        elif path == "dead":
            dead.append(pn)
            open_shells.append(pn)
        elif path == "live":
            live_kindled.append(pn)
            open_shells.append(pn)
        elif path in ("open", "pending"):
            open_shells.append(pn)

    out: Dict[str, Any] = {
        "schema": SCHEMA,
        "as_of": _utc_iso(now),
        "seats_today": seats_today,
        "max_new_seats_per_day": max_new,
        "max_open_tryout_seats": max_open,
        "n_open_shells": len(open_shells),
        "open_shells": open_shells,
        "n_ghosts": len(ghosts),
        "ghosts": ghosts,
        "n_dead_kindling": len(dead),
        "dead_kindling": dead,
        "n_live_kindled": len(live_kindled),
        "live_kindled": live_kindled,
        "first_fill_open": first_fill_open,
        "n_first_fill_open": len(first_fill_open),
        "by_pair": by_pair,
        "open_lots_path": str(OPEN_LOTS_PATH),
        "note": (
            "Inventory open_shells ≠ seats_today day burn. "
            "Ghosts are registry tax — purge does not trade."
        ),
    }
    if persist:
        try:
            _write_json(LATEST_PATH, out)
        except Exception as e:
            logger.debug("persist ledger: %s", e)
    return out


def scale_path_for_pairs(
    pairs: Sequence[str],
    *,
    ledger: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Thin map pair → scale_path fields for Signals rows."""
    led = ledger or build_seat_ledger(pairs=pairs, persist=False)
    by = led.get("by_pair") or {}
    out: Dict[str, Dict[str, Any]] = {}
    for p in pairs:
        pn = _norm_pair(p)
        row = by.get(pn) or {}
        out[pn] = {
            "scale_path": row.get("scale_path") or "none",
            "scale_path_label": row.get("scale_path_label") or "none",
            "live_scaled": bool(row.get("live_scaled")),
            "paper_scaled": bool(row.get("paper_scaled")),
            "would_eject": bool(row.get("would_eject")),
            "lot_status": row.get("lot_status"),
            "held_usd": row.get("held_usd"),
        }
    return out


def purge_ghost_lots(
    *,
    dry_run: bool = True,
    held_map: Optional[Dict[str, float]] = None,
    archive: bool = True,
) -> Dict[str, Any]:
    """Remove registry rows with no live bag (ghosts). Never places orders.

    Keeps scored history crumbs via archive jsonl; drops active lots keys.

    Safety (TL-P1-HELD):
      • Never delete a lot while held_usd ≥ MIN_HELD_USD (15).
      • Open-looking rows (tryout_open / shell) only purge when held_map is
        trustworthy (caller-provided non-None, or loaded map non-empty).
        Empty/failed held load refuses open-row purge so stale portfolio lag
        cannot wipe an active shell registry key.
      • Already-terminal status (scored/closed/ghost) may still purge on low held.
    """
    now = _utc_now()
    reg = load_open_lots_raw()
    lots = reg.get("lots") if isinstance(reg.get("lots"), dict) else {}
    held_caller = held_map is not None
    held = dict(held_map) if held_caller else load_held_usd_map()
    # Trust: explicit caller map (even empty — operator means empty book) OR
    # non-empty loaded map. Empty auto-load = unreliable → refuse open-row purge.
    held_trustworthy = held_caller or bool(held)
    removed: List[Dict[str, Any]] = []
    kept: Dict[str, Any] = {}
    refused: List[Dict[str, Any]] = []

    terminal_status = ("scored", "flat_no_sell_row", "ghost", "closed", "flat_pending_score")
    open_looking_status = ("tryout_open", "paper_open", "")

    lot_items = list(lots.items()) if isinstance(lots, dict) else []
    for pn, meta in lot_items:
        if not isinstance(meta, dict):
            continue
        p = _norm_pair(pn)
        hu = _f(held.get(p))
        status = str(meta.get("status") or "")
        is_ghost = False
        why = ""

        # Belt: never purge while inventory says real bag
        if hu >= MIN_HELD_USD:
            kept[p] = meta
            continue

        if hu < GHOST_HELD_MAX_USD:
            if status in terminal_status:
                is_ghost = True
                why = f"status={status}|held={hu:.2f}"
            elif meta.get("tryout_shell") or meta.get("tryout_tagged_buy") or status in open_looking_status:
                if not held_trustworthy:
                    refused.append(
                        {
                            "pair": p,
                            "why": "held_map_unreliable|open_row_refuse_purge",
                            "status": status or "open",
                            "held": hu,
                        }
                    )
                    kept[p] = meta
                    continue
                # open-looking row but no bag on a trusted held map
                is_ghost = True
                why = f"unheld_registry|status={status or 'open'}|held={hu:.2f}"
        if is_ghost:
            removed.append(
                {
                    "pair": p,
                    "why": why,
                    "lot": meta,
                    "purged_at": _utc_iso(now),
                    "dry_run": dry_run,
                }
            )
        else:
            kept[p] = meta

    result = {
        "ok": True,
        "dry_run": dry_run,
        "n_removed": len(removed),
        "removed_pairs": [r["pair"] for r in removed],
        "n_kept": len(kept),
        "n_refused": len(refused),
        "refused": refused,
        "held_trustworthy": held_trustworthy,
        "held_caller": held_caller,
        "as_of": _utc_iso(now),
    }

    if archive and removed:
        try:
            GHOST_ARCHIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with GHOST_ARCHIVE_PATH.open("a") as f:
                for r in removed:
                    f.write(json.dumps(r, default=str) + "\n")
            result["archive"] = str(GHOST_ARCHIVE_PATH)
        except Exception as e:
            result["archive_error"] = str(e)

    if not dry_run and removed:
        reg["lots"] = kept
        reg["updated_at"] = _utc_iso(now)
        reg["last_ghost_purge"] = {
            "at": _utc_iso(now),
            "n_removed": len(removed),
            "pairs": result["removed_pairs"],
        }
        write_open_lots_raw(reg)
        result["wrote"] = str(OPEN_LOTS_PATH)
        # refresh ledger snapshot
        try:
            build_seat_ledger(persist=True, held_map=held)
        except Exception as e:
            logger.warning("post-purge seat ledger refresh failed: %s", e)
            result["ledger_refresh_error"] = str(e)
    return result


def close_tryout_lot(
    pair: str,
    *,
    exit_class: Optional[str] = None,
    reason: Optional[str] = None,
    keep_scored_meta: bool = True,
) -> Dict[str, Any]:
    """Mark/remove open lot on flat. Prefer taxonomy exit_class when known."""
    pn = _norm_pair(pair)
    if not pn:
        return {"ok": False, "error": "bad_pair"}
    reg = load_open_lots_raw()
    lots = reg.setdefault("lots", {})
    prev = lots.get(pn) if isinstance(lots.get(pn), dict) else None
    if not prev:
        return {"ok": True, "pair": pn, "action": "noop_absent"}

    # If paper/live scaled and not yet scored, leave for CF scorer — mark flat intent
    if keep_scored_meta and (prev.get("scaled") or prev.get("live_scaled") or prev.get("paper_scaled")):
        if str(prev.get("status") or "") != "scored":
            prev = dict(prev)
            prev["status"] = "flat_pending_score"
            prev["closed_at"] = _utc_iso()
            if exit_class:
                prev["exit_class"] = exit_class
            if reason:
                prev["exit_reason"] = reason
            lots[pn] = prev
            reg["lots"] = lots
            reg["updated_at"] = _utc_iso()
            write_open_lots_raw(reg)
            return {"ok": True, "pair": pn, "action": "marked_flat_pending_score", "lot": prev}

    lots.pop(pn, None)
    reg["lots"] = lots
    reg["updated_at"] = _utc_iso()
    write_open_lots_raw(reg)
    try:
        GHOST_ARCHIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with GHOST_ARCHIVE_PATH.open("a") as f:
            f.write(
                json.dumps(
                    {
                        "pair": pn,
                        "why": "close_tryout_lot",
                        "exit_class": exit_class,
                        "reason": reason,
                        "lot": prev,
                        "purged_at": _utc_iso(),
                    },
                    default=str,
                )
                + "\n"
            )
    except Exception:
        pass
    return {"ok": True, "pair": pn, "action": "removed", "exit_class": exit_class}
