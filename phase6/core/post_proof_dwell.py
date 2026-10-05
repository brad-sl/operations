"""Post-proof dwell — graduate proven names out of tryout reincarnation.

Measure + shadow by default. live_apply=false → log would_* only; no orders.
Policy SSOT: docs/features/POST_PROOF_DWELL_POLICY.md
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

SCHEMA = "post_proof_dwell_v1"
ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "post_proof_dwell.json"
STATE_DIR = ROOT / "data" / "state"
STATE_PATH = STATE_DIR / "post_proof_dwell.json"
SHADOW_CRUMBS = STATE_DIR / "post_proof_dwell_shadow_crumbs.jsonl"
KILL_PATH = STATE_DIR / "post_proof_dwell_KILL"

DEFAULTS: Dict[str, Any] = {
    "schema": SCHEMA,
    "enabled": True,
    "live_apply": False,
    "shadow_log": True,
    "proof": {
        "min_tp_net_usd": 0.50,
        "min_tp_net_pct": 0.015,
        "min_clean_green_rts": 2,
        "clean_rt_lookback_days": 14,
        "accept_live_kindling_fill": True,
    },
    "dwell": {
        "default_hours": 168.0,
        "extend_hours_on_reproof": 168.0,
        "max_hours": 504.0,
        "sleeve_cap_usd": 150.0,
        "sleeve_cap_nav_frac": 0.08,
    },
    "tryout_block": {
        "block_new_shell_while_graduated": True,
        "post_tp_tryout_ban_hours": 48.0,
        "post_tp_tryout_ban_if_not_graduated": True,
    },
    "scale_window": {"skip_eject_while_graduated": True},
    "demote": {
        "on_sl": True,
        "on_hard_dump": True,
        "post_sl_cooloff_hours": 72.0,
    },
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso(dt: Optional[datetime] = None) -> str:
    d = dt or _utc_now()
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_ts(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    s = str(raw).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return float(default)
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def _norm_pair(pair: str) -> str:
    p = str(pair or "").strip().upper().replace("_", "-")
    if p and not p.endswith("-USD") and "-" not in p:
        p = f"{p}-USD"
    return p


def kill_switch_on() -> bool:
    return KILL_PATH.exists()


def load_config(path: Optional[Path] = None) -> Dict[str, Any]:
    p = path or CONFIG_PATH
    cfg = json.loads(json.dumps(DEFAULTS))
    if p.exists():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for k, v in raw.items():
                    if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                        merged = dict(cfg[k])
                        merged.update(v)
                        cfg[k] = merged
                    else:
                        cfg[k] = v
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("post_proof_dwell load_config failed: %s", e)
    # Force-safe until GO: env can still force off
    if os.environ.get("POST_PROOF_DWELL_FORCE_OFF", "").strip() in ("1", "true", "yes"):
        cfg["enabled"] = False
    if kill_switch_on():
        cfg["live_apply"] = False
        cfg["kill"] = True
    else:
        cfg["kill"] = False
    return cfg


def _empty_state() -> Dict[str, Any]:
    return {
        "schema": SCHEMA,
        "updated_at": _utc_iso(),
        "pairs": {},
        "events": [],
    }


def load_state(path: Optional[Path] = None) -> Dict[str, Any]:
    p = path or STATE_PATH
    if not p.exists():
        return _empty_state()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return _empty_state()
        raw.setdefault("pairs", {})
        raw.setdefault("events", [])
        raw.setdefault("schema", SCHEMA)
        return raw
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("post_proof_dwell load_state failed: %s", e)
        return _empty_state()


def write_state(state: Dict[str, Any], path: Optional[Path] = None) -> None:
    p = path or STATE_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    state = dict(state)
    state["updated_at"] = _utc_iso()
    state["schema"] = SCHEMA
    # Keep event tail bounded
    ev = state.get("events")
    if isinstance(ev, list) and len(ev) > 200:
        state["events"] = ev[-200:]
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(p)


def append_shadow_crumb(event: Dict[str, Any], path: Optional[Path] = None) -> None:
    p = path or SHADOW_CRUMBS
    p.parent.mkdir(parents=True, exist_ok=True)
    row = dict(event)
    row.setdefault("ts", _utc_iso())
    row.setdefault("schema", "post_proof_dwell_shadow_v1")
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def _is_tp_reason(reason: str) -> bool:
    r = (reason or "").lower()
    if not r:
        return False
    if "scale_window" in r or "eject" in r and "tp" not in r:
        # eject is not TP proof
        if "take_profit" not in r and "trail" not in r and "fixed_tp" not in r:
            return False
    return any(
        k in r
        for k in (
            "take_profit",
            "fixed_tp",
            "trail",
            "tp_",
            "lifecycle_extension",
            "extension_partial",
        )
    )


def _is_sl_reason(reason: str) -> bool:
    r = (reason or "").lower()
    return any(
        k in r
        for k in (
            "stop_loss",
            "stop-loss",
            "exchange_stop",
            "sl_hit",
            "hard_exit",
            "missfire",
            "liquidation",
        )
    )


def _is_eject_reason(reason: str) -> bool:
    r = (reason or "").lower()
    return "scale_window" in r or "tryout_scale_window" in r or "eject" in r


def fee_aware_net_pnl(trade: Dict[str, Any]) -> Optional[float]:
    """Prefer stamped fee-aware net; fall back to pnl - fees."""
    for k in ("pnl_net", "net_pnl", "fee_aware_pnl"):
        if trade.get(k) is not None:
            return _f(trade.get(k))
    pnl = trade.get("pnl")
    if pnl is None:
        return None
    fees = trade.get("total_fees")
    if fees is None:
        fees = _f(trade.get("fees")) + _f(trade.get("fee"))
    # If fees already netted into pnl, total_fees may still be set — prefer explicit net flags
    if trade.get("pnl_is_net") or trade.get("pnl_fee_aware"):
        return _f(pnl)
    if fees:
        return _f(pnl) - abs(_f(fees))
    return _f(pnl)


def proof_from_sell(
    trade: Dict[str, Any],
    *,
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Does this SELL count as proof for graduation?"""
    c = cfg or load_config()
    proof = c.get("proof") if isinstance(c.get("proof"), dict) else DEFAULTS["proof"]
    side = str(trade.get("side") or trade.get("action") or "").upper()
    if side not in ("SELL", "SELL_SHORT", "EXIT"):
        return {"is_proof": False, "reason": "not_sell"}
    reason = str(
        trade.get("reason")
        or trade.get("exit_reason")
        or trade.get("signal_source")
        or ""
    )
    if _is_eject_reason(reason) and not _is_tp_reason(reason):
        return {"is_proof": False, "reason": "eject_not_proof"}
    if _is_sl_reason(reason):
        return {"is_proof": False, "reason": "sl_not_proof"}
    if not _is_tp_reason(reason):
        # live kindling fill is a separate stamp path
        return {"is_proof": False, "reason": "not_tp_class"}

    net = fee_aware_net_pnl(trade)
    min_usd = _f(proof.get("min_tp_net_usd"), 0.50)
    min_pct = _f(proof.get("min_tp_net_pct"), 0.015)
    pnl_pct = trade.get("pnl_pct")
    try:
        pct = float(pnl_pct) if pnl_pct is not None else None
    except (TypeError, ValueError):
        pct = None
    # if pct looks like percent points (e.g. 3.2) vs fraction
    if pct is not None and abs(pct) > 1.0:
        pct = pct / 100.0

    ok_usd = net is not None and net >= min_usd
    ok_pct = pct is not None and pct >= min_pct
    # dust/green-after-fee thin: require at least one bar
    if net is not None and net < 0:
        return {"is_proof": False, "reason": "net_red", "net": net}
    if not (ok_usd or ok_pct):
        # still allow clearly positive tiny TP if net > 0 and reason is trail/fixed
        if net is not None and net > 0 and min_usd <= 0.50 and net >= 0.25:
            ok_usd = True
        else:
            return {
                "is_proof": False,
                "reason": "below_min_meat",
                "net": net,
                "pct": pct,
                "min_usd": min_usd,
                "min_pct": min_pct,
            }
    return {
        "is_proof": True,
        "reason": "tp_bank",
        "net": net,
        "pct": pct,
        "exit_reason": reason,
    }


def stamp_proof_from_sell(
    trade: Dict[str, Any],
    *,
    cfg: Optional[Dict[str, Any]] = None,
    state: Optional[Dict[str, Any]] = None,
    state_path: Optional[Path] = None,
    now: Optional[datetime] = None,
    persist: bool = True,
) -> Dict[str, Any]:
    """On TP/trail SELL: mark pair graduated_tryout. Never on eject/SL."""
    c = cfg or load_config()
    if not c.get("enabled", True):
        return {"ok": False, "skipped": "disabled"}
    pair = _norm_pair(str(trade.get("pair") or ""))
    if not pair:
        return {"ok": False, "error": "no_pair"}

    reason = str(
        trade.get("reason")
        or trade.get("exit_reason")
        or trade.get("signal_source")
        or ""
    )
    # demote path
    demote_cfg = c.get("demote") if isinstance(c.get("demote"), dict) else {}
    if demote_cfg.get("on_sl", True) and _is_sl_reason(reason):
        return demote_pair(
            pair,
            reason="sl_exit",
            cfg=c,
            state=state,
            state_path=state_path,
            now=now,
            persist=persist,
            meta={"trade_pnl": trade.get("pnl")},
        )

    pr = proof_from_sell(trade, cfg=c)
    if not pr.get("is_proof"):
        return {"ok": True, "stamped": False, "proof": pr, "pair": pair}

    n = now or _utc_now()
    st = state if isinstance(state, dict) else load_state(state_path)
    pairs = st.setdefault("pairs", {})
    dwell = c.get("dwell") if isinstance(c.get("dwell"), dict) else DEFAULTS["dwell"]
    default_h = _f(dwell.get("default_hours"), 168.0)
    extend_h = _f(dwell.get("extend_hours_on_reproof"), 168.0)
    max_h = _f(dwell.get("max_hours"), 504.0)

    prev = pairs.get(pair) if isinstance(pairs.get(pair), dict) else {}
    already = str(prev.get("status") or "") == "graduated_hold"
    graduated_at = _parse_ts(prev.get("graduated_at")) or n
    if already:
        # extend, capped
        base_exp = _parse_ts(prev.get("expires_at")) or (n + timedelta(hours=default_h))
        new_exp = max(base_exp, n) + timedelta(hours=extend_h)
        max_exp = graduated_at + timedelta(hours=max_h)
        if new_exp > max_exp:
            new_exp = max_exp
        proof_count = int(prev.get("proof_count") or 1) + 1
    else:
        new_exp = n + timedelta(hours=default_h)
        proof_count = 1
        graduated_at = n

    entry = {
        "pair": pair,
        "status": "graduated_hold",
        "role": "graduated_hold",
        "graduated_at": _utc_iso(graduated_at),
        "expires_at": _utc_iso(new_exp),
        "proof_count": proof_count,
        "last_proof_at": _utc_iso(n),
        "last_proof": {
            "net": pr.get("net"),
            "pct": pr.get("pct"),
            "exit_reason": pr.get("exit_reason"),
            "order_id": trade.get("order_id"),
            "pnl": trade.get("pnl"),
        },
        "demoted_at": None,
        "demote_reason": None,
    }
    pairs[pair] = entry
    ev = {
        "ts": _utc_iso(n),
        "type": "graduate" if not already else "reproof_extend",
        "pair": pair,
        "entry": entry,
    }
    st.setdefault("events", []).append(ev)
    if persist:
        write_state(st, state_path)
        if c.get("shadow_log", True):
            append_shadow_crumb(
                {
                    "kind": "stamp_proof",
                    "pair": pair,
                    "already": already,
                    "entry": entry,
                    "live_apply": bool(c.get("live_apply")),
                }
            )
    return {
        "ok": True,
        "stamped": True,
        "pair": pair,
        "extended": already,
        "entry": entry,
        "proof": pr,
        "live_apply": bool(c.get("live_apply")),
    }


def stamp_live_kindling_proof(
    pair: str,
    *,
    meta: Optional[Dict[str, Any]] = None,
    cfg: Optional[Dict[str, Any]] = None,
    state_path: Optional[Path] = None,
    now: Optional[datetime] = None,
    persist: bool = True,
) -> Dict[str, Any]:
    """Live kindling add fill counts as proof (config accept_live_kindling_fill)."""
    c = cfg or load_config()
    proof = c.get("proof") if isinstance(c.get("proof"), dict) else {}
    if not proof.get("accept_live_kindling_fill", True):
        return {"ok": False, "skipped": "kindling_proof_off"}
    fake = {
        "pair": pair,
        "side": "SELL",  # reuse path shape via direct graduate
        "reason": "take_profit_kindling_proxy",
        "pnl": _f((meta or {}).get("pnl"), 1.0),
        "pnl_pct": 0.02,
        "pnl_is_net": True,
        "order_id": (meta or {}).get("order_id"),
    }
    # Direct graduate without requiring sell classification
    n = now or _utc_now()
    st = load_state(state_path)
    pn = _norm_pair(pair)
    dwell = c.get("dwell") if isinstance(c.get("dwell"), dict) else DEFAULTS["dwell"]
    default_h = _f(dwell.get("default_hours"), 168.0)
    pairs = st.setdefault("pairs", {})
    prev = pairs.get(pn) if isinstance(pairs.get(pn), dict) else {}
    entry = {
        "pair": pn,
        "status": "graduated_hold",
        "role": "graduated_hold",
        "graduated_at": prev.get("graduated_at") or _utc_iso(n),
        "expires_at": _utc_iso(n + timedelta(hours=default_h)),
        "proof_count": int(prev.get("proof_count") or 0) + 1,
        "last_proof_at": _utc_iso(n),
        "last_proof": {"source": "live_kindling_fill", "meta": meta or {}},
        "demoted_at": None,
        "demote_reason": None,
    }
    pairs[pn] = entry
    st.setdefault("events", []).append(
        {"ts": _utc_iso(n), "type": "graduate_kindling", "pair": pn, "entry": entry}
    )
    if persist:
        write_state(st, state_path)
        append_shadow_crumb({"kind": "kindling_proof", "pair": pn, "entry": entry})
    return {"ok": True, "stamped": True, "pair": pn, "entry": entry}


def demote_pair(
    pair: str,
    *,
    reason: str,
    cfg: Optional[Dict[str, Any]] = None,
    state: Optional[Dict[str, Any]] = None,
    state_path: Optional[Path] = None,
    now: Optional[datetime] = None,
    persist: bool = True,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    c = cfg or load_config()
    n = now or _utc_now()
    st = state if isinstance(state, dict) else load_state(state_path)
    pn = _norm_pair(pair)
    pairs = st.setdefault("pairs", {})
    prev = pairs.get(pn) if isinstance(pairs.get(pn), dict) else {}
    if not prev:
        return {"ok": True, "demoted": False, "reason": "not_tracked", "pair": pn}
    demote_cfg = c.get("demote") if isinstance(c.get("demote"), dict) else {}
    cool_h = _f(demote_cfg.get("post_sl_cooloff_hours"), 72.0)
    entry = dict(prev)
    entry["status"] = "demoted"
    entry["role"] = "tryout_shell"
    entry["demoted_at"] = _utc_iso(n)
    entry["demote_reason"] = reason
    entry["expires_at"] = _utc_iso(n)  # graduated window closed
    entry["tryout_ban_until"] = _utc_iso(n + timedelta(hours=cool_h))
    entry["meta"] = meta or {}
    pairs[pn] = entry
    st.setdefault("events", []).append(
        {"ts": _utc_iso(n), "type": "demote", "pair": pn, "reason": reason, "entry": entry}
    )
    if persist:
        write_state(st, state_path)
        if c.get("shadow_log", True):
            append_shadow_crumb(
                {"kind": "demote", "pair": pn, "reason": reason, "entry": entry}
            )
    return {"ok": True, "demoted": True, "pair": pn, "entry": entry}


def _entry_active(
    entry: Dict[str, Any],
    *,
    now: Optional[datetime] = None,
) -> bool:
    if not isinstance(entry, dict):
        return False
    if str(entry.get("status") or "") != "graduated_hold":
        return False
    n = now or _utc_now()
    exp = _parse_ts(entry.get("expires_at"))
    if exp is None:
        return True
    return exp > n


def is_graduated(
    pair: str,
    *,
    state: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
    state_path: Optional[Path] = None,
) -> bool:
    st = state if isinstance(state, dict) else load_state(state_path)
    pn = _norm_pair(pair)
    entry = (st.get("pairs") or {}).get(pn)
    return _entry_active(entry or {}, now=now)


def get_pair_entry(
    pair: str,
    *,
    state: Optional[Dict[str, Any]] = None,
    state_path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    st = state if isinstance(state, dict) else load_state(state_path)
    return (st.get("pairs") or {}).get(_norm_pair(pair))


def would_block_tryout(
    pair: str,
    *,
    cfg: Optional[Dict[str, Any]] = None,
    state: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
    state_path: Optional[Path] = None,
    last_tp_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Shadow/live gate: block new $25 tryout shell reincarnation."""
    c = cfg or load_config()
    n = now or _utc_now()
    pn = _norm_pair(pair)
    out: Dict[str, Any] = {
        "pair": pn,
        "block": False,
        "reasons": [],
        "live_apply": bool(c.get("live_apply")) and not kill_switch_on(),
        "enabled": bool(c.get("enabled", True)),
        "apply_block": False,
    }
    if not c.get("enabled", True) or kill_switch_on():
        out["reasons"].append("disabled_or_kill")
        return out

    tb = c.get("tryout_block") if isinstance(c.get("tryout_block"), dict) else {}
    st = state if isinstance(state, dict) else load_state(state_path)
    entry = (st.get("pairs") or {}).get(pn) or {}

    if tb.get("block_new_shell_while_graduated", True) and _entry_active(entry, now=n):
        out["block"] = True
        out["reasons"].append("graduated_hold")
        out["entry"] = entry

    # demoted post-SL ban
    ban_until = _parse_ts(entry.get("tryout_ban_until"))
    if ban_until and ban_until > n:
        out["block"] = True
        out["reasons"].append(f"tryout_ban_until:{_utc_iso(ban_until)}")

    # post-TP ban even if not graduated (shadow hygiene)
    ban_h = _f(tb.get("post_tp_tryout_ban_hours"), 48.0)
    if tb.get("post_tp_tryout_ban_if_not_graduated", True) and ban_h > 0:
        tp_at = last_tp_at or _parse_ts(entry.get("last_proof_at"))
        if tp_at is None and entry.get("last_proof"):
            tp_at = _parse_ts((entry.get("last_proof") or {}).get("at"))
        if tp_at is not None:
            hrs = (n - tp_at).total_seconds() / 3600.0
            if 0 <= hrs <= ban_h:
                out["block"] = True
                out["reasons"].append(f"post_tp_tryout_ban_{hrs:.1f}h<={ban_h:g}")

    out["apply_block"] = bool(out["block"] and out["live_apply"])
    out["would_block_if_live"] = bool(out["block"])
    return out


def should_skip_scale_window_eject(
    pair: str,
    *,
    cfg: Optional[Dict[str, Any]] = None,
    state: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
    state_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """If graduated, scale-window should not auto-eject (shadow records would_skip)."""
    c = cfg or load_config()
    pn = _norm_pair(pair)
    sw = c.get("scale_window") if isinstance(c.get("scale_window"), dict) else {}
    out = {
        "pair": pn,
        "skip": False,
        "reasons": [],
        "live_apply": bool(c.get("live_apply")) and not kill_switch_on(),
        "apply_skip": False,
    }
    if not c.get("enabled", True):
        out["reasons"].append("disabled")
        return out
    if not sw.get("skip_eject_while_graduated", True):
        out["reasons"].append("skip_eject_off")
        return out
    if is_graduated(pn, state=state, now=now, state_path=state_path):
        out["skip"] = True
        out["reasons"].append("graduated_hold")
    out["apply_skip"] = bool(out["skip"] and out["live_apply"])
    out["would_skip_if_live"] = bool(out["skip"])
    return out


def apply_to_composer_candidate(
    cand: Optional[Dict[str, Any]],
    *,
    cfg: Optional[Dict[str, Any]] = None,
    persist: bool = True,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Composer hook after discipline/knife. Shadow: never skip unless live_apply."""
    c = cfg or load_config()
    if cand is None:
        return {
            "ran": False,
            "skip_seat": False,
            "reason": "no_candidate",
            "live_apply": bool(c.get("live_apply")),
        }
    pair = str(cand.get("pair") or "")
    wb = would_block_tryout(pair, cfg=c, now=now)
    skip = bool(wb.get("apply_block"))  # only when live_apply
    if persist and c.get("shadow_log", True) and wb.get("block"):
        append_shadow_crumb(
            {
                "kind": "would_block_tryout",
                "pair": wb.get("pair"),
                "block": wb.get("block"),
                "apply_block": skip,
                "reasons": wb.get("reasons"),
                "live_apply": wb.get("live_apply"),
                "eng": cand.get("eng"),
                "rsi": cand.get("rsi"),
            }
        )
    return {
        "ran": True,
        "skip_seat": skip,
        "would_block_if_live": bool(wb.get("block")),
        "live_apply": bool(wb.get("live_apply")),
        "reasons": wb.get("reasons"),
        "pair": wb.get("pair"),
        "result": wb,
        "plain_english": (
            f"post_proof_dwell {wb.get('pair')} "
            f"block={wb.get('block')} apply={skip} "
            f"reasons={wb.get('reasons')}"
        ),
    }


def snapshot(
    *,
    cfg: Optional[Dict[str, Any]] = None,
    state: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Board snapshot for analyst / weekly fact pack."""
    c = cfg or load_config()
    n = now or _utc_now()
    st = state if isinstance(state, dict) else load_state()
    pairs = st.get("pairs") or {}
    active = []
    demoted = []
    expired = []
    for pn, ent in pairs.items():
        if not isinstance(ent, dict):
            continue
        if _entry_active(ent, now=n):
            active.append(ent)
        elif str(ent.get("status")) == "demoted":
            demoted.append(ent)
        else:
            expired.append(ent)
    return {
        "schema": SCHEMA,
        "as_of": _utc_iso(n),
        "enabled": bool(c.get("enabled")),
        "live_apply": bool(c.get("live_apply")) and not kill_switch_on(),
        "kill": kill_switch_on(),
        "n_graduated_active": len(active),
        "n_demoted": len(demoted),
        "n_expired_or_other": len(expired),
        "active_pairs": [e.get("pair") for e in active],
        "active": active,
        "plain": (
            f"post_proof_dwell live_apply={bool(c.get('live_apply'))} "
            f"active={len(active)} demoted={len(demoted)} "
            f"pairs={','.join(e.get('pair') or '' for e in active) or '—'}"
        ),
        "edge_class": "ATTENTION_ONLY_less_loss_path",
    }


def rebuild_state_from_ledger(
    rows: Sequence[Dict[str, Any]],
    *,
    cfg: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Offline: walk sells in time order and stamp proofs (no disk write)."""
    c = cfg or load_config()
    st = _empty_state()
    sells = []
    for r in rows:
        if str(r.get("side") or "").upper() not in ("SELL", "EXIT", "SELL_SHORT"):
            continue
        ts = _parse_ts(r.get("timestamp") or r.get("ts") or r.get("time"))
        if ts is None:
            continue
        sells.append((ts, r))
    sells.sort(key=lambda x: x[0])
    for ts, r in sells:
        stamp_proof_from_sell(
            r, cfg=c, state=st, now=ts, persist=False
        )
    # refresh expiry relative to now
    n = now or _utc_now()
    st["rebuilt_at"] = _utc_iso(n)
    st["n_sells_scanned"] = len(sells)
    return st


__all__ = [
    "SCHEMA",
    "load_config",
    "load_state",
    "write_state",
    "stamp_proof_from_sell",
    "stamp_live_kindling_proof",
    "demote_pair",
    "is_graduated",
    "would_block_tryout",
    "should_skip_scale_window_eject",
    "apply_to_composer_candidate",
    "snapshot",
    "proof_from_sell",
    "rebuild_state_from_ledger",
    "kill_switch_on",
    "append_shadow_crumb",
]
