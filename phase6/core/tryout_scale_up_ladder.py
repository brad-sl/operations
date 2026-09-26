#!/usr/bin/env python3
"""Tryout scale-up (R5) — approval → autonomous ladder (Brad 2026-09-25).

Mirrors the tryout-seat ladder:
  1. approval (default): TG card when n_planned>0; money only via CLI GO
  2. After required_manual_gos (default 2) live scale steps, Brad --arm-auto
  3. autonomous: approval cron may apply one planned step (still kill/caps)

Artifacts
---------
  data/state/tryout_scale_up_brad_ladder.json
  (decision file still owns live_apply arming for the path itself)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from phase6.core.paths import STATE_DIR

SCHEMA = "tryout_scale_up_ladder_v1"
LADDER_PATH = STATE_DIR / "tryout_scale_up_brad_ladder.json"
DEFAULT_REQUIRED = 2


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")


def default_ladder() -> Dict[str, Any]:
    return {
        "schema": SCHEMA,
        "mode": "approval",  # approval | autonomous
        "required_manual_gos": DEFAULT_REQUIRED,
        "manual_gos": [],
        "auto_armed": False,
        "kill": False,
        "note": (
            "First N live scale-up steps need Brad CLI GO. "
            "Then --arm-auto for unattended kindling (still live_signal + caps)."
        ),
        "updated_at": _utc_iso(),
    }


def load_ladder() -> Dict[str, Any]:
    raw = _load(LADDER_PATH, None)
    if not isinstance(raw, dict):
        out = default_ladder()
        _write(LADDER_PATH, out)
        return out
    out = default_ladder()
    out.update({k: v for k, v in raw.items() if v is not None})
    if not isinstance(out.get("manual_gos"), list):
        out["manual_gos"] = []
    try:
        out["required_manual_gos"] = int(out.get("required_manual_gos") or DEFAULT_REQUIRED)
    except (TypeError, ValueError):
        out["required_manual_gos"] = DEFAULT_REQUIRED
    mode = str(out.get("mode") or "approval").strip().lower()
    out["mode"] = mode if mode in ("approval", "autonomous") else "approval"
    out["auto_armed"] = bool(out.get("auto_armed"))
    out["kill"] = bool(out.get("kill"))
    return out


def save_ladder(pol: Dict[str, Any]) -> Dict[str, Any]:
    out = load_ladder()
    out.update(pol)
    out["schema"] = SCHEMA
    out["updated_at"] = _utc_iso()
    _write(LADDER_PATH, out)
    return out


def manual_go_count(pol: Optional[Dict[str, Any]] = None) -> int:
    p = pol or load_ladder()
    return len(p.get("manual_gos") or [])


def ready_to_arm(pol: Optional[Dict[str, Any]] = None) -> bool:
    p = pol or load_ladder()
    return manual_go_count(p) >= int(p.get("required_manual_gos") or DEFAULT_REQUIRED) and not bool(
        p.get("auto_armed")
    )


def autonomous_apply_allowed(pol: Optional[Dict[str, Any]] = None) -> bool:
    """True when approval cron may place one planned kindling step unattended."""
    p = pol or load_ladder()
    if bool(p.get("kill")):
        return False
    if str(p.get("mode") or "") != "autonomous":
        return False
    if not bool(p.get("auto_armed")):
        return False
    if manual_go_count(p) < int(p.get("required_manual_gos") or DEFAULT_REQUIRED):
        return False
    # Path still needs decision.live_apply + no KILL file
    try:
        from phase6.core.tryout_scale_up_live import is_live_armed, kill_switch_on, load_decision

        if kill_switch_on():
            return False
        if not is_live_armed(load_decision()):
            return False
    except Exception:
        return False
    return True


def record_manual_go(
    *,
    pair: str,
    step_usd: float,
    order_id: str = "",
    note: str = "",
    source: str = "cli_go",
) -> Dict[str, Any]:
    p = load_ladder()
    gos: List[Dict[str, Any]] = list(p.get("manual_gos") or [])
    oid = str(order_id or "").strip()
    if oid and any(str(g.get("order_id") or "") == oid for g in gos if isinstance(g, dict)):
        return p
    gos.append(
        {
            "ts": _utc_iso(),
            "pair": str(pair or "").strip().upper().replace("_", "-"),
            "step_usd": float(step_usd or 0),
            "order_id": oid,
            "note": note or "",
            "source": source,
        }
    )
    p["manual_gos"] = gos
    need = int(p.get("required_manual_gos") or DEFAULT_REQUIRED)
    if len(gos) >= need and not p.get("auto_armed"):
        p["note"] = (
            f"{len(gos)}/{need} scale GOs done — arm autonomous: "
            "python3 scripts/phase6/run_tryout_scale_up_ladder.py --arm-auto"
        )
    p["updated_at"] = _utc_iso()
    _write(LADDER_PATH, p)
    return p


def arm_autonomous(*, force: bool = False) -> Dict[str, Any]:
    p = load_ladder()
    need = int(p.get("required_manual_gos") or DEFAULT_REQUIRED)
    n = manual_go_count(p)
    if n < need and not force:
        p["arm_refused"] = f"need {need} scale GOs, have {n}"
        return p
    p["mode"] = "autonomous"
    p["auto_armed"] = True
    p["kill"] = False
    p["arm_refused"] = None
    p["note"] = f"Scale-up autonomous armed at {_utc_iso()} after {n} GOs"
    p["updated_at"] = _utc_iso()
    _write(LADDER_PATH, p)
    return p


def disarm(*, kill: bool = False) -> Dict[str, Any]:
    p = load_ladder()
    p["mode"] = "approval"
    p["auto_armed"] = False
    if kill:
        p["kill"] = True
    p["note"] = f"Scale-up disarmed to approval at {_utc_iso()}"
    p["updated_at"] = _utc_iso()
    _write(LADDER_PATH, p)
    return p


def status_plain() -> str:
    p = load_ladder()
    n = manual_go_count(p)
    need = int(p.get("required_manual_gos") or DEFAULT_REQUIRED)
    return (
        f"scale_up_ladder mode={p.get('mode')} auto_armed={p.get('auto_armed')} "
        f"kill={p.get('kill')} gos={n}/{need} "
        f"autonomous_apply={autonomous_apply_allowed(p)} ready_to_arm={ready_to_arm(p)}"
    )
