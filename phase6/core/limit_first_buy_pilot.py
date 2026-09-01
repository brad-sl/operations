#!/usr/bin/env python3
"""
Limit-first buy Phase D pilot controls.

- Day counters (attempts / filled / usd)
- Hard kill switch file
- Live config hot-reload of entry_execution (so OFF works without restart)
- Never places orders itself

Doctrine: cost-cut pilot, not alpha. Caps limit exposure of the NEW path;
over-cap falls back to market IOC (legacy).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from phase6.core.paths import PROJECT_ROOT, STATE_DIR, TRADING_CONFIG_PHASE6

PILOT_STATE = STATE_DIR / "limit_first_buy_pilot_state.json"
PILOT_EVENTS = STATE_DIR / "limit_first_buy_pilot_events.jsonl"
PILOT_REPORT = PROJECT_ROOT / "reports" / "LIMIT_FIRST_BUY_PILOT_LATEST.md"
KILL_SWITCH = STATE_DIR / "limit_first_buy_KILL"  # presence → force market
# Also honor env LIMIT_FIRST_BUY_KILL=1


def _utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def kill_switch_active() -> bool:
    if os.environ.get("LIMIT_FIRST_BUY_KILL", "").strip() in ("1", "true", "TRUE", "yes"):
        return True
    return KILL_SWITCH.exists()


def load_entry_execution_from_disk() -> Dict[str, Any]:
    """Hot-read entry_execution from trading_config_phase6.json."""
    try:
        path = TRADING_CONFIG_PHASE6
        if not path.exists():
            path = PROJECT_ROOT / "config" / "trading_config_phase6.json"
        raw = json.loads(path.read_text())
        ee = raw.get("entry_execution")
        return ee if isinstance(ee, dict) else {}
    except Exception:
        return {}


def merge_live_config(config_dict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Overlay disk entry_execution onto in-memory config (pilot kill/enable without restart)."""
    base: Dict[str, Any] = dict(config_dict) if isinstance(config_dict, dict) else {}
    ee_disk = load_entry_execution_from_disk()
    if ee_disk:
        base["entry_execution"] = ee_disk
    return base


def load_pilot_state() -> Dict[str, Any]:
    day = _utc_day()
    if PILOT_STATE.exists():
        try:
            st = json.loads(PILOT_STATE.read_text())
            if st.get("utc_day") == day:
                return st
        except Exception:
            pass
    return {
        "utc_day": day,
        "limit_attempts": 0,
        "limit_filled": 0,
        "limit_unfilled": 0,
        "limit_errors": 0,
        "usd_attempted": 0.0,
        "usd_filled": 0.0,
        "market_fallback_over_cap": 0,
        "kill_hits": 0,
        "elevated_aborts": 0,
        "events_sample": [],
    }


def save_pilot_state(st: Dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    st["updated_at"] = _iso()
    PILOT_STATE.write_text(json.dumps(st, indent=2, default=str) + "\n")


def append_pilot_event(ev: Dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    ev = dict(ev)
    ev.setdefault("ts", _iso())
    with PILOT_EVENTS.open("a") as f:
        f.write(json.dumps(ev, default=str) + "\n")


def pilot_allows_limit(
    usd_amount: float,
    policy: Any,
) -> Tuple[bool, str]:
    """
    Whether this buy may attempt limit-first.
    Returns (ok, reason). reason in:
      ok | kill_switch | pilot_max_buys | pilot_max_usd | disabled
    """
    if kill_switch_active():
        return False, "kill_switch"
    if not getattr(policy, "enabled", False):
        return False, "disabled"
    max_buys = int(getattr(policy, "pilot_max_buys_per_day", 0) or 0)
    max_usd = float(getattr(policy, "pilot_max_usd_per_day", 0) or 0)
    st = load_pilot_state()
    if max_buys > 0 and int(st.get("limit_attempts") or 0) >= max_buys:
        return False, "pilot_max_buys"
    if max_usd > 0 and float(st.get("usd_attempted") or 0) + float(usd_amount or 0) > max_usd + 1e-9:
        return False, "pilot_max_usd"
    return True, "ok"


def record_limit_attempt(
    *,
    pair: str,
    usd_amount: float,
    outcome: str,
    order_id: Optional[str] = None,
    filled_usd: float = 0.0,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """outcome: attempted | filled | unfilled | error | elevated_abort | over_cap_market | kill_market"""
    st = load_pilot_state()
    if outcome == "attempted":
        st["limit_attempts"] = int(st.get("limit_attempts") or 0) + 1
        st["usd_attempted"] = float(st.get("usd_attempted") or 0) + float(usd_amount or 0)
    elif outcome == "filled":
        st["limit_filled"] = int(st.get("limit_filled") or 0) + 1
        st["usd_filled"] = float(st.get("usd_filled") or 0) + float(filled_usd or 0)
    elif outcome == "unfilled":
        st["limit_unfilled"] = int(st.get("limit_unfilled") or 0) + 1
    elif outcome == "error":
        st["limit_errors"] = int(st.get("limit_errors") or 0) + 1
    elif outcome == "elevated_abort":
        st["elevated_aborts"] = int(st.get("elevated_aborts") or 0) + 1
    elif outcome == "over_cap_market":
        st["market_fallback_over_cap"] = int(st.get("market_fallback_over_cap") or 0) + 1
    elif outcome == "kill_market":
        st["kill_hits"] = int(st.get("kill_hits") or 0) + 1

    sample = list(st.get("events_sample") or [])
    row = {
        "ts": _iso(),
        "pair": pair,
        "usd": usd_amount,
        "outcome": outcome,
        "order_id": order_id,
        "filled_usd": filled_usd,
    }
    if extra:
        row.update(extra)
    sample.append(row)
    st["events_sample"] = sample[-40:]
    save_pilot_state(st)
    append_pilot_event(row)
    return st


def pair_elevated_from_c_shadow(pair: str) -> bool:
    """Best-effort: C stand-down shadow latest says would_block for pair."""
    path = STATE_DIR / "standdown_filter_c_shadow_latest.json"
    if not path.exists():
        return False
    try:
        d = json.loads(path.read_text())
        rows = d.get("pairs") or d.get("rows") or d.get("results") or []
        if isinstance(rows, dict):
            row = rows.get(pair) or rows.get(pair.upper())
            if isinstance(row, dict):
                return bool(row.get("would_block") or row.get("elevated"))
            return False
        for r in rows:
            if not isinstance(r, dict):
                continue
            if str(r.get("pair") or r.get("product_id") or "") == pair:
                return bool(r.get("would_block") or r.get("elevated") or r.get("block"))
        # aggregate flag
        blocked = d.get("would_block_pairs") or d.get("blocked_pairs") or []
        if pair in blocked:
            return True
    except Exception:
        return False
    return False


def write_pilot_report(extra: Optional[Dict[str, Any]] = None) -> Path:
    st = load_pilot_state()
    ee = load_entry_execution_from_disk()
    lf = ee.get("limit_first") if isinstance(ee.get("limit_first"), dict) else {}
    attempts = int(st.get("limit_attempts") or 0)
    filled = int(st.get("limit_filled") or 0)
    unfilled = int(st.get("limit_unfilled") or 0)
    fill_rate = (filled / attempts) if attempts else None
    lines = [
        "# Limit-first buy pilot (Phase D)",
        "",
        f"**As of:** {_iso()}",
        f"**UTC day:** {st.get('utc_day')}",
        f"**Kill switch:** {'ON ⛔' if kill_switch_active() else 'off'}",
        f"**Config mode:** `{ee.get('mode')}` · enabled=`{lf.get('enabled')}`",
        f"**Caps:** buys/day={lf.get('pilot_max_buys_per_day')} · usd/day={lf.get('pilot_max_usd_per_day')}",
        f"**Policy:** post_only={lf.get('post_only')} · wait={lf.get('fill_wait_s')}s · "
        f"fallback={lf.get('market_fallback')} · elevated={lf.get('elevated_tape')}",
        "",
        "## Honesty",
        "",
        "- Cost-cut pilot only — **not alpha**, not a printer.",
        "- Fill rate at post_only bid is the metric that matters.",
        "- Over-cap / kill → **market IOC** (legacy), not forced skip of all buys.",
        "- Review bar (design): ≥30 limit attempts or 14d before promote talk.",
        "",
        "## Today",
        "",
        f"- Limit attempts: **{attempts}**",
        f"- Filled: **{filled}** · Unfilled: **{unfilled}** · Errors: **{st.get('limit_errors')}**",
        f"- Fill rate: **{f'{100*fill_rate:.0f}%' if fill_rate is not None else 'n/a'}**",
        f"- USD attempted (limit): **${float(st.get('usd_attempted') or 0):.2f}**",
        f"- USD filled (limit): **${float(st.get('usd_filled') or 0):.2f}**",
        f"- Over-cap → market: **{st.get('market_fallback_over_cap')}**",
        f"- Kill → market: **{st.get('kill_hits')}**",
        f"- Elevated aborts: **{st.get('elevated_aborts')}**",
        "",
        f"State: `{PILOT_STATE.relative_to(PROJECT_ROOT)}`",
        f"Events: `{PILOT_EVENTS.relative_to(PROJECT_ROOT)}`",
        f"Kill file: `{KILL_SWITCH.relative_to(PROJECT_ROOT)}` (touch to force market)",
        "",
    ]
    if extra:
        lines.append("## Extra")
        lines.append("```json")
        lines.append(json.dumps(extra, indent=2, default=str)[:2000])
        lines.append("```")
        lines.append("")
    PILOT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    PILOT_REPORT.write_text("\n".join(lines))
    return PILOT_REPORT


def telegram_pilot_summary() -> str:
    st = load_pilot_state()
    n = int(st.get("limit_attempts") or 0)
    if n <= 0 and not kill_switch_active():
        return ""
    filled = int(st.get("limit_filled") or 0)
    return (
        f"Limit-first D pilot day={st.get('utc_day')}\n"
        f"attempts={n} filled={filled} unfilled={st.get('limit_unfilled')} "
        f"err={st.get('limit_errors')}\n"
        f"usd_att=${float(st.get('usd_attempted') or 0):.0f} "
        f"usd_fill=${float(st.get('usd_filled') or 0):.0f}\n"
        f"kill={'ON' if kill_switch_active() else 'off'} · cost-cut only"
    )
