"""Tryout scale-window kill — shell is an option on kindling, not a mini-bag.

Product bar (Brad 2026-10-01):
  A tryout bag without a clear scale-up path is inventory tax.
  When the opportunity window closes (late phase, structure break, dead/neg sent,
  hold past deadline with no live scale) → full shell exit, free powder.

Standing rules
--------------
• Decision = this module. Money mechanics = protected_market_exit.
• DEFAULTS.live_apply is false (safe code default). Live money = config SSOT:
  Brad GO 2026-10-01 set config live_apply true (board cron auto-ejects).
  Kill file freezes. Operator CLI --go still works.
• Cooloff SSOT: config post_eject_pair_cooloff_hours (DEFAULTS 24h as of 2026-10-02).
• Tryout-shell / open-lot registry only — never BTC/ETH/PAXG ballast.
• One full flat per pair; no half-trim here (that is dual-peak's job).
• No cash-hold on eject reason (strategy/process exit, not discretionary park).
• Board always records would_eject; auto money needs config live_apply + no kill.

Does NOT replace SL / trail TP / dual-peak. Orthogonal: those need meat or -3%;
this frees shells that will never kindle.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

from phase6.core.paths import PROJECT_ROOT

logger = logging.getLogger(__name__)

SCHEMA = "tryout_scale_window_v1"
STATE_DIR = PROJECT_ROOT / "data" / "state"
CONFIG_PATH = PROJECT_ROOT / "config" / "tryout_scale_window.json"
LATEST_PATH = STATE_DIR / "tryout_scale_window_latest.json"
CRUMBS_PATH = STATE_DIR / "tryout_scale_window_crumbs.jsonl"
KILL_PATH = STATE_DIR / "tryout_scale_window_KILL"
EJECT_RESULT_PATH = STATE_DIR / "tryout_scale_window_eject_latest.json"
BOARD_SEEN_PATH = STATE_DIR / "tryout_scale_window_board_seen.json"
COOLOFF_PATH = STATE_DIR / "tryout_scale_window_cooloff.json"
BOARD_DEDUPE_HOURS = 12.0

# Ledger / capital reason — must match runner_capital_events strategy-exit allowlist
EJECT_REASON = "tryout_scale_window_eject"
EJECT_SIGNAL = "tryout_scale_window"

STICKY_NEVER_EJECT: Set[str] = {
    "BTC-USD",
    "BTC-USDC",
    "ETH-USD",
    "ETH-USDC",
    "PAXG-USD",
    "PAXG-USDC",
    "USDC-USD",
    "USD-USD",
}

DEFAULTS: Dict[str, Any] = {
    "enabled": True,
    "live_apply": False,  # auto eject OFF until Brad GO
    "min_hold_hours": 2.0,  # never eject brand-new shells
    "max_hold_hours_no_scale": 36.0,  # deadline if never live_scaled
    "eject_phase_ge": 3,  # extension+ with no live scale = window closed
    "require_not_live_scaled": True,
    "eject_on_structure_break": True,  # structure_ok is False
    "eject_on_structure_unknown_after_h": 12.0,  # null structure too long in late phase
    "eject_on_dead_sent": True,
    "dead_sent_max": 0.05,  # show/eng below this = dead
    "neg_sent_max": 0.0,  # strictly negative
    "min_shell_usd": 15.0,
    "max_shell_usd": 100.0,  # still tryout-sized
    "post_eject_pair_cooloff_hours": 24.0,  # same-pair re-seat block after eject (config SSOT)
    # Process-tax hygiene (not edge claim): 2nd+ dead eject in lookback → longer cooloff
    "repeat_eject_lookback_days": 7.0,
    "repeat_eject_min_count": 2,  # this eject inclusive
    "repeat_eject_cooloff_hours": 72.0,  # escalated block after repeat dead shells
    "rt_fee_rate_per_side": 0.006,  # measure-only Coinbase-ish taker estimate when fees missing
    "ballast_pairs": list(STICKY_NEVER_EJECT),
    "note": (
        "Shell = option on kindling. Dead scale path → full exit. "
        "DEFAULTS.live_apply false; live config may be true after Brad GO. "
        "post_eject_pair_cooloff_hours default 24h (config SSOT). "
        "repeat_eject → 72h cooloff = less churn tax, not alpha."
    ),
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
    p = str(pair or "").strip().upper()
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


def _append_crumb(row: Dict[str, Any]) -> None:
    CRUMBS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CRUMBS_PATH.open("a") as f:
        f.write(json.dumps(row, default=str) + "\n")


def kill_switch_on() -> bool:
    return KILL_PATH.exists()


def load_cfg(overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = dict(DEFAULTS)
    raw = _load_json(CONFIG_PATH, {})
    if isinstance(raw, dict):
        cfg.update({k: v for k, v in raw.items() if v is not None})
    if overrides:
        cfg.update({k: v for k, v in overrides.items() if v is not None})
    # hard pin: kill file freezes auto
    if kill_switch_on():
        cfg["live_apply"] = False
    return cfg


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
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _hold_hours(entry_ts: Any, now: Optional[datetime] = None) -> float:
    ts = _parse_ts(entry_ts)
    if not ts:
        return 0.0
    n = now or _utc_now()
    return max(0.0, (n - ts).total_seconds() / 3600.0)


def _open_lots() -> Dict[str, Dict[str, Any]]:
    from phase6.core import tryout_scale_up_shadow as shadow

    reg = _load_json(shadow.OPEN_LOTS_PATH, {"lots": {}})
    lots = (reg.get("lots") if isinstance(reg, dict) else {}) or {}
    out: Dict[str, Dict[str, Any]] = {}
    if isinstance(lots, dict):
        for k, v in lots.items():
            if isinstance(v, dict):
                out[_norm_pair(k)] = v
    return out


def _held_usd_map() -> Dict[str, float]:
    """Best-effort live held notional by pair."""
    out: Dict[str, float] = {}
    try:
        from phase6.core.exchange_client import CoinbaseExchangeClient
        from phase6.core.live_portfolio_manager import LivePortfolioManager

        ex = CoinbaseExchangeClient(mode="live")
        ex._ensure_live_client()
        pm = LivePortfolioManager(exchange=ex)
        enr = pm.get_enriched_positions() or {}
        pos = enr.get("positions") or {}
        if isinstance(pos, dict):
            for k, v in pos.items():
                pn = _norm_pair(k)
                if isinstance(v, dict):
                    out[pn] = _f(v.get("value_usd") or v.get("usd_value"))
        elif isinstance(pos, list):
            for row in pos:
                if not isinstance(row, dict):
                    continue
                pn = _norm_pair(row.get("pair") or "")
                if pn:
                    out[pn] = _f(row.get("value_usd") or row.get("usd_value"))
    except Exception as e:
        logger.debug("held_usd_map: %s", e)
    return out


def _sentiment_for(pair: str) -> Optional[float]:
    """Gate-grade show sentiment if present."""
    pn = _norm_pair(pair)
    paths = [
        STATE_DIR / "sentiment_cache.json",
        STATE_DIR / "pair_sentiment_latest.json",
        STATE_DIR / "x_reddit_bridge_latest.json",
    ]
    for path in paths:
        raw = _load_json(path, None)
        if not isinstance(raw, dict):
            continue
        # nested by pair
        for key in (pn, pn.replace("-USD", ""), pn.split("-")[0]):
            row = raw.get(key)
            if isinstance(row, dict):
                for sk in ("sentiment", "eng", "score", "show", "value"):
                    if row.get(sk) is not None:
                        return _f(row.get(sk))
            elif row is not None and not isinstance(row, (dict, list)):
                try:
                    return float(row)
                except (TypeError, ValueError):
                    pass
        # pairs list
        for row in raw.get("pairs") or raw.get("rows") or []:
            if isinstance(row, dict) and _norm_pair(row.get("pair") or "") == pn:
                for sk in ("sentiment", "eng", "score", "sentiment_show"):
                    if row.get(sk) is not None:
                        return _f(row.get(sk))
    # pair-signals board
    try:
        import urllib.request

        sig = json.loads(
            urllib.request.urlopen("http://127.0.0.1:8502/api/pair-signals", timeout=8).read()
        )
        for row in sig.get("rows") or []:
            if _norm_pair(row.get("pair") or "") == pn:
                if row.get("sentiment_show") is not None:
                    return _f(row.get("sentiment_show"))
                if row.get("sentiment") is not None:
                    return _f(row.get("sentiment"))
    except Exception:
        pass
    return None


def _phase_structure(pair: str) -> Dict[str, Any]:
    """Reuse scale-up phase/structure helper when available."""
    try:
        from phase6.core import tryout_scale_up_shadow as shadow

        ps = shadow._phase_and_structure(pair)  # returns dict
        if isinstance(ps, dict):
            return {
                "phase": ps.get("phase"),
                "structure_ok": ps.get("structure_ok"),
                "detail": ps,
            }
    except Exception as e:
        logger.debug("phase_structure shadow %s: %s", pair, e)
    try:
        from phase6.core import tryout_scale_up_live as live

        plan = live.plan_live_steps()
        for row in plan.get("plans") or []:
            if _norm_pair(row.get("pair") or "") == _norm_pair(pair):
                return {
                    "phase": row.get("phase"),
                    "structure_ok": row.get("structure_ok"),
                    "unrealized_r": row.get("unrealized_r"),
                    "detail": row.get("detail") or {},
                }
    except Exception as e:
        logger.debug("phase_structure live %s: %s", pair, e)
    return {"phase": None, "structure_ok": None, "detail": {}}


def evaluate_pair(
    pair: str,
    *,
    lot: Optional[Dict[str, Any]] = None,
    held_usd: Optional[float] = None,
    cfg: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Return scale-window judgment for one pair."""
    c = cfg or load_cfg()
    n = now or _utc_now()
    pn = _norm_pair(pair)
    reasons: List[str] = []
    out: Dict[str, Any] = {
        "pair": pn,
        "would_eject": False,
        "status": "skip",
        "reasons": reasons,
        "scale_path": "unknown",
    }
    if not pn or pn in set(c.get("ballast_pairs") or STICKY_NEVER_EJECT) or pn in STICKY_NEVER_EJECT:
        reasons.append("ballast_or_sticky")
        out["status"] = "never"
        out["scale_path"] = "n/a"
        return out

    lots = _open_lots() if lot is None else {_norm_pair(pair): lot}
    meta = lot if isinstance(lot, dict) else lots.get(pn)
    if not isinstance(meta, dict):
        reasons.append("no_open_lot")
        out["status"] = "no_lot"
        return out

    # must look like tryout shell / paper tryout lot
    live_scaled = bool(meta.get("live_scaled"))
    shellish = bool(
        meta.get("tryout_shell")
        or meta.get("tryout_tagged_buy")
        or meta.get("status") in ("tryout_open", "paper_open")
        or meta.get("source") == "tryout_seat_buy"
        or (meta.get("paper_scaled") and not live_scaled)
    )
    if not shellish and not meta.get("scaled"):
        # scaled paper without shell flag still counts if held small
        shellish = True
    if not shellish:
        reasons.append("not_tryout_shell")
        out["status"] = "skip"
        return out

    if live_scaled and c.get("require_not_live_scaled", True):
        reasons.append("already_live_scaled")
        out["status"] = "scaled"
        out["scale_path"] = "used"
        return out

    husd_arg = held_usd
    if husd_arg is None:
        live_held = _held_usd_map().get(pn)
        live_usd = _f(live_held, 0.0)
    else:
        live_usd = _f(husd_arg, 0.0)
    meta_shell = _f(meta.get("shell_usd") or meta.get("held_usd_at_scale"), 25.0)
    # Prefer live book; meta is only a size hint when still held.
    husd = live_usd if live_usd > 0 else meta_shell
    out["held_usd"] = husd
    out["live_held_usd"] = live_usd
    out["on_book"] = live_usd >= _f(c.get("min_shell_usd"), 15.0) * 0.5
    if live_usd <= 0.0:
        # Registry ghost / already flat — never money-page as would_eject.
        reasons.append("not_on_book")
        out["status"] = "registry_ghost"
        out["scale_path"] = "n/a_flat"
        out["would_eject"] = False
        out["reasons"] = reasons
        return out
    if husd < _f(c.get("min_shell_usd"), 15.0):
        reasons.append("below_min_shell")
        out["status"] = "dust"
        return out
    if husd > _f(c.get("max_shell_usd"), 100.0):
        reasons.append("above_tryout_band")
        out["status"] = "full_stack"
        out["scale_path"] = "n/a_full"
        return out

    hold_h = _hold_hours(meta.get("entry_ts"), n)
    out["hold_hours"] = round(hold_h, 3)
    out["entry_ts"] = meta.get("entry_ts")
    out["live_scaled"] = live_scaled
    out["paper_scaled"] = bool(meta.get("paper_scaled"))
    min_h = _f(c.get("min_hold_hours"), 2.0)
    if hold_h < min_h:
        reasons.append(f"min_hold {hold_h:.2f}h < {min_h}")
        out["status"] = "too_fresh"
        out["scale_path"] = "pending"
        return out

    ps = _phase_structure(pn)
    phase = ps.get("phase")
    if phase is None:
        phase = meta.get("phase")
    structure_ok = ps.get("structure_ok")
    out["phase"] = phase
    out["structure_ok"] = structure_ok
    out["unrealized_r"] = ps.get("unrealized_r")

    sent = _sentiment_for(pn)
    out["sentiment"] = sent

    eject_phase_ge = int(c.get("eject_phase_ge") or 3)
    window_closed = False

    # Primary: late phase, never live-scaled
    try:
        phase_i = int(phase) if phase is not None else None
    except (TypeError, ValueError):
        phase_i = None
    if phase_i is not None and phase_i >= eject_phase_ge and not live_scaled:
        window_closed = True
        reasons.append(f"phase={phase_i}>=eject_ge {eject_phase_ge} no_live_scale")

    # Structure break
    if c.get("eject_on_structure_break", True) and structure_ok is False and not live_scaled:
        window_closed = True
        reasons.append("structure_break")

    # Structure unknown too long while late/aged
    unk_h = _f(c.get("eject_on_structure_unknown_after_h"), 12.0)
    if (
        structure_ok is None
        and hold_h >= unk_h
        and not live_scaled
        and phase_i is not None
        and phase_i >= eject_phase_ge
    ):
        window_closed = True
        reasons.append(f"structure_unknown hold>={unk_h}h late_phase")

    # Dead / negative sentiment after min hold
    if c.get("eject_on_dead_sent", True) and sent is not None and not live_scaled:
        if sent < _f(c.get("neg_sent_max"), 0.0):
            window_closed = True
            reasons.append(f"neg_sent={sent}")
        elif sent <= _f(c.get("dead_sent_max"), 0.05) and (
            phase_i is not None and phase_i >= eject_phase_ge or hold_h >= unk_h
        ):
            window_closed = True
            reasons.append(f"dead_sent={sent}")

    # Max hold with no scale
    max_h = _f(c.get("max_hold_hours_no_scale"), 36.0)
    if hold_h >= max_h and not live_scaled:
        window_closed = True
        reasons.append(f"max_hold {hold_h:.1f}h>={max_h} no_live_scale")

    if window_closed:
        out["would_eject"] = True
        out["status"] = "window_closed"
        out["scale_path"] = "dead"
        out["reasons"] = reasons
        return out

    # Still open path
    if phase_i is not None and phase_i in (1, 2) and not live_scaled:
        out["scale_path"] = "live_kindling_possible"
        out["status"] = "open"
        reasons.append("early_phase_window_open")
    elif not live_scaled:
        out["scale_path"] = "pending"
        out["status"] = "watch"
        reasons.append("no_close_trigger_yet")
    else:
        out["scale_path"] = "used"
        out["status"] = "scaled"
    out["reasons"] = reasons
    return out


def evaluate_open_tryouts(
    *,
    cfg: Optional[Dict[str, Any]] = None,
    pairs: Optional[Sequence[str]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Board: all open tryout lots → would_eject list."""
    c = cfg or load_cfg()
    n = now or _utc_now()
    lots = _open_lots()
    held = _held_usd_map()
    rows: List[Dict[str, Any]] = []
    allow = {_norm_pair(p) for p in (pairs or []) if p} or None
    for pn, meta in lots.items():
        if allow is not None and pn not in allow:
            continue
        row = evaluate_pair(pn, lot=meta, held_usd=held.get(pn), cfg=c, now=n)
        rows.append(row)
    would = [r for r in rows if r.get("would_eject")]
    payload = {
        "schema": SCHEMA,
        "as_of": _utc_iso(n),
        "enabled": bool(c.get("enabled")),
        "live_apply": bool(c.get("live_apply")) and not kill_switch_on(),
        "kill": kill_switch_on(),
        "n_scanned": len(rows),
        "n_would_eject": len(would),
        "would_eject_pairs": [r["pair"] for r in would],
        "rows": rows,
        "cfg_note": c.get("note"),
        "plain": (
            f"scale-window scanned={len(rows)} would_eject={len(would)} "
            f"live_apply={bool(c.get('live_apply'))} kill={kill_switch_on()}"
        ),
    }
    # Ghost registry hygiene (never trades) — keep open_lots honest for board
    ghost_purge: Dict[str, Any] = {}
    try:
        from phase6.core.tryout_seat_ledger import purge_ghost_lots

        # Auto-apply purge of unheld registry rows (ZEC-class scored ghosts).
        # Money-safe: only deletes JSON keys; archives to jsonl.
        ghost_purge = purge_ghost_lots(dry_run=False, held_map=held, archive=True) or {}
        payload["ghost_purge"] = {
            "n_removed": ghost_purge.get("n_removed"),
            "removed_pairs": ghost_purge.get("removed_pairs") or [],
        }
    except Exception as e:
        payload["ghost_purge_error"] = str(e)

    _write_json(LATEST_PATH, payload)
    _append_crumb(
        {
            "kind": "evaluate",
            "ts": _utc_iso(n),
            "n_would_eject": len(would),
            "pairs": payload["would_eject_pairs"],
            "n_ghosts_purged": (ghost_purge or {}).get("n_removed") or 0,
        }
    )
    return payload


def mark_lot_ejected(
    pair: str,
    *,
    reason: str = EJECT_REASON,
    order_id: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
    skip_dwell: bool = False,
) -> None:
    """Clear open-lot registry after successful flat.

    Dwell/on_tryout_exit: only when skip_dwell=False. Live eject goes through
    protected_market_exit → TradeLedger SELL which already runs close_tryout_lot
    + on_tryout_exit — set skip_dwell=True there to avoid double dwell (P2).
    """
    pn = _norm_pair(pair)
    try:
        from phase6.core.tryout_seat_ledger import close_tryout_lot

        close_tryout_lot(pn, exit_class=None, reason=reason, keep_scored_meta=False)
    except Exception:
        try:
            from phase6.core import tryout_scale_up_shadow as shadow

            shadow._clear_open_lot(pn)  # type: ignore[attr-defined]
        except Exception as e:
            logger.warning("clear open lot %s: %s", pn, e)
    if skip_dwell:
        return
    try:
        from phase6.core.pair_funnel_dwell import on_tryout_exit

        on_tryout_exit(
            pn,
            exit_reason=reason,
            exit_ts=_utc_iso(),
            meta={"order_id": order_id, "hook_source": "scale_window_mark", **(meta or {})},
        )
    except Exception as e:
        logger.warning("dwell on_tryout_exit %s: %s", pn, e)


def _load_cooloff_file() -> Dict[str, Any]:
    try:
        if COOLOFF_PATH.exists():
            raw = json.loads(COOLOFF_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return raw
    except Exception as e:
        logger.warning("cooloff file read: %s", e)
    return {"schema": "tryout_scale_window_cooloff_v1", "pairs": {}}


def _save_cooloff_file(blob: Dict[str, Any]) -> None:
    COOLOFF_PATH.parent.mkdir(parents=True, exist_ok=True)
    blob = dict(blob)
    blob["schema"] = "tryout_scale_window_cooloff_v1"
    blob["updated_at"] = _utc_iso()
    COOLOFF_PATH.write_text(json.dumps(blob, indent=2, default=str) + "\n", encoding="utf-8")


def estimate_rt_fees_usd(
    notional_usd: float,
    *,
    rate_per_side: float = 0.006,
) -> float:
    """Measure-only round-trip fee estimate when exchange fees missing on row."""
    n = max(0.0, float(notional_usd or 0.0))
    r = max(0.0, float(rate_per_side or 0.0))
    return round(n * r * 2.0, 6)


def count_recent_scale_window_ejects(
    pair: str,
    *,
    lookback_days: float = 7.0,
    now: Optional[datetime] = None,
    ledger_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Count tryout_scale_window_eject SELLs for pair in lookback (process-tax)."""
    pn = _norm_pair(pair)
    now = now or _utc_now()
    cut = now.timestamp() - float(lookback_days) * 86400.0
    path = ledger_path or (PROJECT_ROOT / "trades" / "phase6_trades.jsonl")
    n = 0
    times: List[str] = []
    if path.is_file():
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue
                if str(row.get("side") or "").upper() != "SELL":
                    continue
                rsn = str(row.get("reason") or row.get("exit_reason") or "").lower()
                if "tryout_scale_window_eject" not in rsn and "scale_window_eject" not in rsn:
                    continue
                rp = _norm_pair(str(row.get("pair") or row.get("product_id") or ""))
                if rp != pn:
                    continue
                ts = row.get("timestamp") or row.get("ts") or row.get("time") or ""
                try:
                    from dateutil import parser as _dp  # type: ignore

                    t = _dp.isoparse(str(ts))
                    if t.tzinfo is None:
                        t = t.replace(tzinfo=timezone.utc)
                    if t.timestamp() >= cut:
                        n += 1
                        times.append(str(ts))
                except Exception:
                    # count undated recent-looking rows conservatively as in-window
                    n += 1
                    times.append(str(ts))
        except Exception as e:
            logger.warning("count_recent_ejects %s: %s", pn, e)
    return {
        "pair": pn,
        "n": n,
        "lookback_days": float(lookback_days),
        "times": times[-8:],
    }


def effective_post_eject_cooloff_hours(
    pair: str,
    cfg: Optional[Dict[str, Any]] = None,
    *,
    now: Optional[datetime] = None,
    include_this_eject: bool = True,
) -> Dict[str, Any]:
    """Base cooloff, or escalated after repeat dead ejects in lookback.

    Hygiene only — not an edge claim. 2nd eject in 7d → longer same-pair block.
    """
    c = cfg or load_cfg()
    base = _f(
        c.get("post_eject_pair_cooloff_hours"),
        float(DEFAULTS.get("post_eject_pair_cooloff_hours") or 24.0),
    )
    lookback = _f(c.get("repeat_eject_lookback_days"), 7.0)
    min_n = int(c.get("repeat_eject_min_count") or DEFAULTS.get("repeat_eject_min_count") or 2)
    escalated = _f(
        c.get("repeat_eject_cooloff_hours"),
        float(DEFAULTS.get("repeat_eject_cooloff_hours") or 72.0),
    )
    hist = count_recent_scale_window_ejects(pair, lookback_days=lookback, now=now)
    # include_this_eject: ledger may not yet have this fill when called post-success
    n = int(hist.get("n") or 0) + (1 if include_this_eject else 0)
    # if ledger already has this eject, don't double-count
    if include_this_eject and int(hist.get("n") or 0) >= min_n:
        n = int(hist.get("n") or 0)
    hours = base
    reason = "base"
    if n >= min_n:
        hours = max(base, escalated)
        reason = f"repeat_eject_n={n}_ge_{min_n}"
    return {
        "pair": _norm_pair(pair),
        "hours": float(hours),
        "base_hours": float(base),
        "escalated_hours": float(escalated),
        "n_recent_ejects": int(hist.get("n") or 0),
        "n_for_gate": n,
        "min_count": min_n,
        "lookback_days": float(lookback),
        "reason": reason,
        "hist_times": hist.get("times") or [],
    }


def set_post_eject_cooloff(pair: str, hours: float) -> Dict[str, Any]:
    """Same-pair rebuy cooloff so dead shells are not instantly re-seated.

    Writes two durable surfaces (both read by load_buy_block_status / process-tax):
      1) capital_controls store ``manual_sell_cooldown``
      2) data/state/tryout_scale_window_cooloff.json (audit + recovery if store races)

    Hours SSOT: config ``post_eject_pair_cooloff_hours`` (default 24).
    Returns receipt; raises only on total write failure after retries logged.
    """
    import time

    out: Dict[str, Any] = {
        "pair": "",
        "hours": float(hours or 0.0),
        "ok": False,
        "expires_ts": None,
        "capital_ok": False,
        "file_ok": False,
    }
    if hours <= 0:
        out["ok"] = True
        out["skipped"] = "hours_le_0"
        return out
    pn = _norm_pair(pair)
    out["pair"] = pn
    exp_ts = time.time() + float(hours) * 3600.0
    out["expires_ts"] = exp_ts
    out["expires_at"] = datetime.fromtimestamp(exp_ts, tz=timezone.utc).isoformat()

    # 1) Dedicated cooloff file (always attempt first — simple durable audit)
    try:
        blob = _load_cooloff_file()
        pairs = blob.get("pairs")
        if not isinstance(pairs, dict):
            pairs = {}
        pairs[pn] = {
            "expires_ts": exp_ts,
            "expires_at": out["expires_at"],
            "hours": float(hours),
            "reason": "tryout_scale_window_eject",
            "set_at": _utc_iso(),
        }
        # prune expired
        now = time.time()
        pairs = {
            k: v
            for k, v in pairs.items()
            if isinstance(v, dict) and float(v.get("expires_ts") or 0) > now
        }
        blob["pairs"] = pairs
        _save_cooloff_file(blob)
        out["file_ok"] = True
    except Exception as e:
        logger.warning("post_eject cooloff file %s: %s", pn, e)
        out["file_err"] = str(e)[:160]

    # 2) capital_controls store — process-tax / seat buy SSOT path
    try:
        from phase6.core.capital_controls_store import (
            load_account_capital_state,
            primary_account_id,
            save_account_capital_state,
        )

        aid = primary_account_id()
        st = load_account_capital_state(aid)
        cd = st.get("manual_sell_cooldown")
        if not isinstance(cd, dict):
            cd = {}
        # keep longer of existing vs new (don't shorten a longer block)
        prev = float(cd.get(pn) or 0.0)
        cd[pn] = max(prev, exp_ts)
        st["manual_sell_cooldown"] = cd
        # ensure we do NOT park cash — eject is process exit, powder stays deployable
        st["manual_liquidation_cash_hold_usd"] = 0.0
        save_account_capital_state(aid, st)
        # verify read-back
        st2 = load_account_capital_state(aid)
        got = float((st2.get("manual_sell_cooldown") or {}).get(pn) or 0.0)
        if got >= exp_ts - 1.0:
            out["capital_ok"] = True
        else:
            out["capital_err"] = f"readback_miss got={got} want>={exp_ts}"
            logger.error("post_eject cooloff capital readback fail %s: %s", pn, out["capital_err"])
    except Exception as e:
        logger.error("post_eject cooloff capital %s: %s", pn, e)
        out["capital_err"] = str(e)[:160]

    out["ok"] = bool(out["capital_ok"] or out["file_ok"])
    if not out["ok"]:
        logger.error("post_eject cooloff TOTAL FAIL %s hours=%s", pn, hours)
    return out


def eject_pair(
    exchange: Any,
    pair: str,
    *,
    dry_run: bool = True,
    go: bool = False,
    reason: str = EJECT_REASON,
    entry_price: float = 0.0,
    qty_hint: float = 0.0,
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Full protected flat of one tryout shell."""
    from phase6.core.protected_market_exit import protected_market_exit

    c = cfg or load_cfg()
    pn = _norm_pair(pair)
    result: Dict[str, Any] = {
        "pair": pn,
        "success": False,
        "dry_run": bool(dry_run),
        "go": bool(go),
        "reason": reason,
    }
    if pn in STICKY_NEVER_EJECT:
        result["error"] = "ballast_refused"
        return result
    if not dry_run and not go:
        result["error"] = "need_go"
        return result

    # resolve qty hint from portfolio if needed
    hint = float(qty_hint or 0.0)
    mark = 0.0
    entry = float(entry_price or 0.0)
    try:
        from phase6.core.live_portfolio_manager import LivePortfolioManager

        pm = LivePortfolioManager(exchange=exchange)
        enr = pm.get_enriched_positions() or {}
        pos = enr.get("positions") or {}
        row = pos.get(pn) if isinstance(pos, dict) else None
        if isinstance(row, dict):
            hint = max(hint, _f(row.get("amount") or row.get("qty") or row.get("quantity")))
            mark = _f(row.get("current_price"))
            if entry <= 0:
                entry = _f(row.get("entry_price"))
    except Exception as e:
        result["portfolio_err"] = str(e)[:120]

    if entry <= 0:
        try:
            from phase6.core import tryout_scale_up_shadow as shadow

            lots = _open_lots()
            entry = _f((lots.get(pn) or {}).get("entry_price"))
        except Exception:
            pass
    if mark <= 0 and hasattr(exchange, "get_price"):
        try:
            mark = _f(exchange.get_price(pn))
        except Exception:
            pass

    pe = protected_market_exit(
        exchange,
        pn,
        frac=1.0,
        qty_full_hint=hint,
        entry_price=entry,
        mark_price=mark,
        reason=reason,
        signal_source=EJECT_SIGNAL,
        dry_run=bool(dry_run),
        ledger=not dry_run,
        reattach_sl=True,  # no-op if flat; reattach if partial fail
        cancel_stops=True,
    )
    result["protected_exit"] = pe
    result["success"] = bool(pe.get("success")) or (
        dry_run and not pe.get("error") and not pe.get("naked_risk")
    )
    if dry_run:
        # SW-03: never claim dry success if cancel left bag naked
        if pe.get("naked_risk") or (
            pe.get("error") and str(pe.get("error")).startswith("dry_run_sl_reattach")
        ):
            result["success"] = False
            result["error"] = pe.get("error") or "dry_run_naked_risk"
            result["naked_risk"] = True
        else:
            result["success"] = True
        result["would_sell_qty_hint"] = hint
        result["mark"] = mark
        return result

    if pe.get("success"):
        # Ledger already ran close_tryout_lot + on_tryout_exit — skip dwell here
        mark_lot_ejected(
            pn,
            reason=reason,
            order_id=pe.get("order_id"),
            meta={"filled_qty": pe.get("filled_qty"), "exit_price": pe.get("exit_price")},
            skip_dwell=True,
        )
        cool_meta = effective_post_eject_cooloff_hours(pn, c, include_this_eject=False)
        cool_h = float(cool_meta.get("hours") or 24.0)
        cool = set_post_eject_cooloff(pn, cool_h)
        cool["repeat_policy"] = cool_meta
        result["cooloff"] = cool
        # Measure-only fee estimate for honesty when fill fees missing
        try:
            notional = abs(_f(pe.get("filled_qty")) * _f(pe.get("exit_price") or mark))
            if notional <= 0 and hint > 0 and mark > 0:
                notional = float(hint) * float(mark)
            fee_est = estimate_rt_fees_usd(
                notional,
                rate_per_side=_f(c.get("rt_fee_rate_per_side"), 0.006),
            )
            result["fee_measure"] = {
                "notional_usd": round(notional, 4),
                "rt_fee_est_usd": fee_est,
                "rate_per_side": _f(c.get("rt_fee_rate_per_side"), 0.006),
                "note": "estimate only when exchange fees absent — not P&L truth",
            }
        except Exception as e:
            result["fee_measure_err"] = str(e)[:120]
        if not cool.get("ok"):
            result["cooloff_failed"] = True
            logger.error(
                "eject %s succeeded but cooloff failed — pair may re-seat: %s",
                pn,
                cool,
            )
        # force zero cash hold if disposition raced
        try:
            from phase6.core.capital_controls_store import (
                load_account_capital_state,
                primary_account_id,
                save_account_capital_state,
            )

            aid = primary_account_id()
            st = load_account_capital_state(aid)
            if _f(st.get("manual_liquidation_cash_hold_usd")) > 0:
                st["manual_liquidation_cash_hold_usd"] = 0.0
                save_account_capital_state(aid, st)
        except Exception:
            pass
    return result


def eject_pairs(
    pairs: Sequence[str],
    *,
    dry_run: bool = True,
    go: bool = False,
    exchange: Any = None,
    cfg: Optional[Dict[str, Any]] = None,
    require_would_eject: bool = False,
) -> Dict[str, Any]:
    """Eject one or more shells. Operator path ignores live_apply."""
    c = cfg or load_cfg()
    ex = exchange
    if ex is None:
        from phase6.core.exchange_client import CoinbaseExchangeClient

        ex = CoinbaseExchangeClient(mode="live")
        ex._ensure_live_client()

    board = evaluate_open_tryouts(cfg=c, pairs=list(pairs))
    by_pair = {r["pair"]: r for r in board.get("rows") or []}
    results: List[Dict[str, Any]] = []
    for raw in pairs:
        pn = _norm_pair(raw)
        judgment = by_pair.get(pn) or evaluate_pair(pn, cfg=c)
        if require_would_eject and not judgment.get("would_eject"):
            results.append(
                {
                    "pair": pn,
                    "success": False,
                    "skipped": True,
                    "error": "not_would_eject",
                    "judgment": judgment,
                }
            )
            continue
        # Operator GO can force eject even if board lagging (explicit pairs list)
        er = eject_pair(ex, pn, dry_run=dry_run, go=go, cfg=c)
        er["judgment"] = judgment
        results.append(er)

    summary = {
        "schema": SCHEMA,
        "as_of": _utc_iso(),
        "dry_run": bool(dry_run),
        "go": bool(go),
        "n": len(results),
        "n_ok": sum(1 for r in results if r.get("success")),
        "results": results,
        "board": {"n_would_eject": board.get("n_would_eject"), "pairs": board.get("would_eject_pairs")},
        "brad": "GO C 2026-10-01 tryout scale-window eject",
    }
    _write_json(EJECT_RESULT_PATH, summary)
    _append_crumb({"kind": "eject", "ts": _utc_iso(), **{k: summary[k] for k in ("dry_run", "go", "n", "n_ok")}})
    return summary


def auto_eject_if_armed(
    *,
    dry_run: bool = False,
    exchange: Any = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """When config live_apply ON and no kill: eject current would_eject shells.

    Safety belt: require_would_eject=True always. Returns skipped payload when
    not armed. Cron should call this after board refresh.
    """
    c = cfg or load_cfg()
    if kill_switch_on():
        out = {
            "schema": SCHEMA,
            "as_of": _utc_iso(),
            "ran": False,
            "skipped": "kill_switch",
            "n_ok": 0,
            "n": 0,
        }
        _append_crumb({"kind": "auto_eject_skip", "ts": _utc_iso(), "reason": "kill"})
        return out
    if not bool(c.get("live_apply")):
        out = {
            "schema": SCHEMA,
            "as_of": _utc_iso(),
            "ran": False,
            "skipped": "live_apply_off",
            "n_ok": 0,
            "n": 0,
        }
        return out
    board = evaluate_open_tryouts(cfg=c)
    pairs = list(board.get("would_eject_pairs") or [])
    if not pairs:
        out = {
            "schema": SCHEMA,
            "as_of": _utc_iso(),
            "ran": False,
            "skipped": "no_would_eject",
            "n_ok": 0,
            "n": 0,
            "board": {"n_would_eject": 0, "pairs": []},
        }
        _write_json(EJECT_RESULT_PATH, {**out, "kind": "auto_eject_idle"})
        return out
    summary = eject_pairs(
        pairs,
        dry_run=bool(dry_run),
        go=True,
        exchange=exchange,
        cfg=c,
        require_would_eject=True,
    )
    summary["ran"] = True
    summary["kind"] = "auto_eject"
    summary["source"] = "live_apply_cron"
    _append_crumb(
        {
            "kind": "auto_eject",
            "ts": _utc_iso(),
            "pairs": pairs,
            "n_ok": summary.get("n_ok"),
            "dry_run": bool(dry_run),
        }
    )
    return summary


def board_fingerprint(board: Dict[str, Any]) -> str:
    """Stable key for would_eject set + top reason tags so same board doesn't re-page."""
    parts: List[str] = []
    for row in board.get("rows") or []:
        if not isinstance(row, dict) or not row.get("would_eject"):
            continue
        pair = _norm_pair(row.get("pair") or "")
        if not pair:
            continue
        reasons = row.get("reasons") or []
        tag = ",".join(str(r) for r in reasons[:3]) if isinstance(reasons, list) else str(reasons)
        parts.append(f"{pair}:{tag}")
    return "|".join(sorted(parts))


def _load_board_seen() -> Dict[str, Any]:
    raw = _load_json(BOARD_SEEN_PATH, {"fingerprints": {}})
    if not isinstance(raw, dict):
        return {"fingerprints": {}}
    if not isinstance(raw.get("fingerprints"), dict):
        raw["fingerprints"] = {}
    return raw


def _should_send_board(
    fingerprint: str,
    *,
    now: Optional[datetime] = None,
    dedupe_hours: float = BOARD_DEDUPE_HOURS,
    mark: bool = True,
) -> bool:
    """True once per fingerprint within dedupe window."""
    fp = str(fingerprint or "").strip()
    if not fp:
        return False
    now_dt = now or _utc_now()
    seen = _load_board_seen()
    fps_raw = seen.get("fingerprints")
    fps: Dict[str, Any] = fps_raw if isinstance(fps_raw, dict) else {}
    last_raw = str(fps.get(fp) or "")
    last = None
    if last_raw:
        try:
            last = datetime.fromisoformat(last_raw.replace("Z", "+00:00"))
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
        except Exception:
            last = None
    if last is not None and (now_dt - last).total_seconds() < float(dedupe_hours) * 3600.0:
        return False
    if mark:
        fps[fp] = _utc_iso(now_dt)
        horizon = max(float(dedupe_hours), 24.0) * 3600.0 * 7.0
        keep: Dict[str, str] = {}
        for k, v in list(fps.items()):
            try:
                t = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
                if (now_dt - t).total_seconds() <= horizon:
                    keep[str(k)] = str(v)
            except Exception:
                continue
        seen["fingerprints"] = keep
        seen["updated_at"] = _utc_iso(now_dt)
        _write_json(BOARD_SEEN_PATH, seen)
    return True


def board_telegram_summary(
    board: Optional[Dict[str, Any]] = None,
    *,
    force: bool = False,
    mark_sent: bool = True,
    dedupe_hours: float = BOARD_DEDUPE_HOURS,
) -> str:
    """Operator TG body only when n_would_eject > 0.

    Empty when: kill on, disabled, no would_eject, or same fingerprint within
    dedupe window. Never places orders. Cron must only call evaluate path.
    """
    if kill_switch_on():
        return ""
    b = board if isinstance(board, dict) else evaluate_open_tryouts()
    if not b.get("enabled", True):
        return ""
    n = int(b.get("n_would_eject") or 0)
    if n <= 0:
        return ""
    rows = [r for r in (b.get("rows") or []) if isinstance(r, dict) and r.get("would_eject")]
    if not rows:
        return ""
    fp = board_fingerprint(b)
    if not force and not _should_send_board(fp, dedupe_hours=dedupe_hours, mark=mark_sent):
        return ""

    live_apply = bool(b.get("live_apply"))
    lines = [
        "SCALE-WINDOW BOARD (measure — money OFF until you GO)",
        f"would_eject {n} · live_apply={'ON' if live_apply else 'OFF'} · fp={fp}",
        "Shells with dead kindling path — recycle powder, don't babysit.",
        "Eject CLI:",
        "  PYTHONPATH=. .venv/bin/python3 scripts/phase6/run_tryout_scale_window.py \\",
        "    --eject " + " ".join(_norm_pair(r.get("pair") or "") for r in rows) + " --go --no-dry-run",
        "Pairs:",
    ]
    for r in rows[:12]:
        pair = _norm_pair(r.get("pair") or "")
        reasons = r.get("reasons") or []
        rsn = ", ".join(str(x) for x in reasons[:4]) if isinstance(reasons, list) else str(reasons)
        hold = r.get("hold_hours")
        hold_s = f"{float(hold):.1f}h" if hold is not None else "?"
        phase = r.get("phase")
        path = r.get("scale_path") or "?"
        lines.append(
            f"  · {pair} path={path} phase={phase} hold={hold_s} · {rsn}"
        )
    if live_apply:
        lines.append("NOTE: live_apply ON — auto eject path may fire if armed cron exists.")
    else:
        lines.append("NOTE: auto live_apply OFF — this card is attention only.")
    lines.append(f"board: {LATEST_PATH}")
    body = "\n".join(lines)
    _append_crumb(
        {
            "kind": "board_tg",
            "ts": _utc_iso(),
            "n_would_eject": n,
            "fingerprint": fp,
            "force": bool(force),
        }
    )
    return body
