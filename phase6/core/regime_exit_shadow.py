#!/usr/bin/env python3
"""Regime-aware exit policy map — SHADOW only (profit optimization layer).

Reads config/regime_exit_policy_map.json, resolves active BTC regime, evaluates
open book with that regime's TP / trail / RSI knobs.

- mode=shadow (default): log would-fire, optional Telegram, never places orders
- live_apply is always forced off while mode != live or map.live_apply false
- Does not flip hard_exit.operator_approve or take_profit.mode in exit_automation

State:
  data/state/regime_exit_shadow_status.json
  data/state/regime_exit_shadow_events.jsonl
  data/state/regime_exit_shadow_notify_dedupe.json
  data/state/regime_exit_shadow_collection.json  — multi-week gates by regime
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from phase6.core.paths import PROJECT_ROOT

logger = logging.getLogger("phase6.regime_exit_shadow")

MAP_PATH = PROJECT_ROOT / "config" / "regime_exit_policy_map.json"
REGIME_STATUS = PROJECT_ROOT / "data" / "state" / "regime_cash_status.json"
STATE_PATH = PROJECT_ROOT / "data" / "state" / "regime_exit_shadow_status.json"
EVENTS_PATH = PROJECT_ROOT / "data" / "state" / "regime_exit_shadow_events.jsonl"
DEDUPE_PATH = PROJECT_ROOT / "data" / "state" / "regime_exit_shadow_notify_dedupe.json"
COLLECTION_PATH = PROJECT_ROOT / "data" / "state" / "regime_exit_shadow_collection.json"

EPISODE_GAP_SEC = 30 * 60  # unique would-fire episodes


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _now()).isoformat()


def load_map(path: Optional[Path] = None) -> Dict[str, Any]:
    p = path or MAP_PATH
    if not p.exists():
        return {"enabled": False, "mode": "off", "regimes": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("regime_exit_policy_map load failed: %s", e)
        return {"enabled": False, "mode": "off", "regimes": {}}


def resolve_active_regime(status: Optional[Dict[str, Any]] = None) -> Tuple[str, Dict[str, Any]]:
    """Return (regime, meta). Prefer live regime_cash_status; fallback detector."""
    meta: Dict[str, Any] = {"source": "unknown"}
    st = status
    if st is None and REGIME_STATUS.exists():
        try:
            st = json.loads(REGIME_STATUS.read_text(encoding="utf-8"))
        except Exception:
            st = {}
    st = st or {}
    reg = str(st.get("regime") or "").lower().strip()
    if reg:
        meta = {
            "source": "regime_cash_status",
            "btc_return_pct": st.get("btc_return_pct"),
            "confidence": st.get("confidence"),
            "label": st.get("label"),
            "strategy_mode": st.get("strategy_mode"),
        }
        return reg, meta
    try:
        from phase6.research.regime_detector import detect_regime

        det = detect_regime()
        reg = str(det.get("regime") or "unknown").lower()
        meta = {"source": "detect_regime", **{k: det.get(k) for k in ("btc_return_pct", "confidence", "as_of")}}
        return reg or "unknown", meta
    except Exception as e:
        meta["error"] = str(e)
        return "unknown", meta


def policy_for_regime(mmap: Dict[str, Any], regime: str) -> Dict[str, Any]:
    regimes = mmap.get("regimes") or {}
    pol = dict(regimes.get(regime) or regimes.get("unknown") or mmap.get("defaults") or {})
    # fill defaults for missing knobs
    defaults = mmap.get("defaults") or {}
    for k in ("fixed_tp", "trail", "rsi_hard_exit"):
        if k not in pol:
            pol[k] = dict(defaults.get(k) or {})
        else:
            pol[k] = dict(pol[k] or {})
    pol["regime"] = regime
    return pol


@dataclass
class MapSignal:
    pair: str
    kind: str  # fixed_tp | trail | rsi_hard_exit
    regime: str
    r: float
    entry_px: float
    mark_px: float
    usd: float
    detail: str
    would_exit_usd: float
    knobs: Dict[str, Any]


def _load_collection() -> Dict[str, Any]:
    if COLLECTION_PATH.exists():
        try:
            return json.loads(COLLECTION_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "schema": "regime_exit_shadow_collection_v1",
        "started_at": None,
        "by_regime": {},
        "days_regime_seen": {},
        "last_episode_ts": {},  # key regime|pair|kind -> iso
    }


def _save_collection(c: Dict[str, Any]) -> None:
    try:
        COLLECTION_PATH.parent.mkdir(parents=True, exist_ok=True)
        COLLECTION_PATH.write_text(json.dumps(c, indent=2, default=str), encoding="utf-8")
    except Exception as e:
        logger.warning("collection write failed: %s", e)


def _bump_episode(coll: Dict[str, Any], regime: str, pair: str, kind: str, ts: datetime) -> bool:
    """Return True if this counts as a new episode (gap > 30m)."""
    key = f"{regime}|{pair}|{kind}"
    last_map = coll.setdefault("last_episode_ts", {})
    prev = last_map.get(key)
    is_new = True
    if prev:
        try:
            t0 = datetime.fromisoformat(str(prev).replace("Z", "+00:00"))
            if t0.tzinfo is None:
                t0 = t0.replace(tzinfo=timezone.utc)
            if (ts - t0).total_seconds() < EPISODE_GAP_SEC:
                is_new = False
        except Exception:
            pass
    last_map[key] = ts.isoformat()
    if is_new:
        br = coll.setdefault("by_regime", {}).setdefault(
            regime,
            {
                "would_fire_episodes": 0,
                "would_fire_ticks": 0,
                "by_kind": {},
                "pairs": {},
            },
        )
        br["would_fire_episodes"] = int(br.get("would_fire_episodes") or 0) + 1
        br["would_fire_ticks"] = int(br.get("would_fire_ticks") or 0) + 1
        bk = br.setdefault("by_kind", {})
        bk[kind] = int(bk.get(kind) or 0) + 1
        bp = br.setdefault("pairs", {})
        bp[pair] = int(bp.get(pair) or 0) + 1
    else:
        br = coll.setdefault("by_regime", {}).setdefault(regime, {"would_fire_ticks": 0})
        br["would_fire_ticks"] = int(br.get("would_fire_ticks") or 0) + 1
    return is_new


def _mark_regime_day(coll: Dict[str, Any], regime: str, day: str) -> None:
    dr = coll.setdefault("days_regime_seen", {})
    s = set(dr.get(regime) or [])
    s.add(day)
    # keep last 120 day stamps
    dr[regime] = sorted(s)[-120:]


def evaluate_map_signals(
    marks: List[Any],
    policy: Dict[str, Any],
    *,
    regime: str,
    rsi_by_pair: Optional[Dict[str, float]] = None,
    peak_r: Optional[Dict[str, float]] = None,
    min_usd: float = 25.0,
) -> Tuple[List[MapSignal], Dict[str, float]]:
    """marks: objects with pair, usd, r, entry_px, mark_px (shadow_tp.PositionMark ok)."""
    peak_r = dict(peak_r or {})
    rsi_by_pair = rsi_by_pair or {}
    signals: List[MapSignal] = []

    ftp = dict(policy.get("fixed_tp") or {})
    trail = dict(policy.get("trail") or {})
    rsi_he = dict(policy.get("rsi_hard_exit") or {})

    tp_on = bool(ftp.get("enabled")) and ftp.get("pct") is not None
    fixed = float(ftp["pct"]) if tp_on else None
    trail_on = bool(trail.get("enabled"))
    arm = float(trail.get("arm_pct") or 0.04)
    trail_pct = float(trail.get("trail_pct") or 0.02)
    be = float(trail.get("breakeven_lock_pct") or 0.005)
    rsi_on = bool(rsi_he.get("enabled")) and rsi_he.get("overbought") is not None
    rsi_th = float(rsi_he["overbought"]) if rsi_on else None

    knobs_pub = {
        "fixed_tp": ftp,
        "trail": trail,
        "rsi_hard_exit": rsi_he,
    }

    for m in marks:
        pair = getattr(m, "pair", None) or (m.get("pair") if isinstance(m, dict) else None)
        if not pair:
            continue
        try:
            if isinstance(m, dict):
                usd = float(m.get("usd") or 0)
                r = m.get("r")
                entry_px = m.get("entry_px")
                mark_px = float(m.get("mark_px") or 0)
            else:
                usd = float(getattr(m, "usd", 0) or 0)
                r = getattr(m, "r", None)
                entry_px = getattr(m, "entry_px", None)
                mark_px = float(getattr(m, "mark_px", 0) or 0)
        except (TypeError, ValueError):
            continue
        if usd < min_usd or r is None or entry_px is None or mark_px <= 0:
            continue
        try:
            r = float(r)
            entry_px = float(entry_px)
        except (TypeError, ValueError):
            continue
        prev_peak = peak_r.get(pair)
        peak = max(prev_peak, r) if prev_peak is not None else r
        peak_r[pair] = peak

        if fixed is not None and r >= fixed - 1e-12:
            signals.append(
                MapSignal(
                    pair=pair,
                    kind="fixed_tp",
                    regime=regime,
                    r=r,
                    entry_px=entry_px,
                    mark_px=mark_px,
                    usd=usd,
                    detail=f"regime={regime} r={r:.4f} >= tp {fixed}",
                    would_exit_usd=round(usd, 2),
                    knobs=knobs_pub,
                )
            )

        if trail_on and peak >= arm:
            stop_r = max(peak - trail_pct, be)
            if r <= stop_r + 1e-12:
                signals.append(
                    MapSignal(
                        pair=pair,
                        kind="trail",
                        regime=regime,
                        r=r,
                        entry_px=entry_px,
                        mark_px=mark_px,
                        usd=usd,
                        detail=f"regime={regime} armed peak_r={peak:.4f} stop_r={stop_r:.4f} mark_r={r:.4f}",
                        would_exit_usd=round(usd, 2),
                        knobs=knobs_pub,
                    )
                )

        if rsi_th is not None:
            rv = rsi_by_pair.get(pair)
            if rv is None:
                # try uppercase / bare
                rv = rsi_by_pair.get(pair.upper()) or rsi_by_pair.get(pair.split("-")[0])
            try:
                rv_f = float(rv) if rv is not None else None
            except (TypeError, ValueError):
                rv_f = None
            if rv_f is not None and rv_f >= rsi_th:
                signals.append(
                    MapSignal(
                        pair=pair,
                        kind="rsi_hard_exit",
                        regime=regime,
                        r=r,
                        entry_px=entry_px,
                        mark_px=mark_px,
                        usd=usd,
                        detail=f"regime={regime} rsi={rv_f:.1f} >= {rsi_th} (shadow hard-exit; no order)",
                        would_exit_usd=round(usd, 2),
                        knobs=knobs_pub,
                    )
                )

    return signals, peak_r


def _promotion_progress(mmap: Dict[str, Any], coll: Dict[str, Any]) -> Dict[str, Any]:
    prom = dict(mmap.get("promotion") or {})
    days_needed = int(prom.get("shadow_min_calendar_days") or 60)
    early = int(prom.get("early_review_calendar_days") or 45)
    min_ep = int(prom.get("min_would_fire_episodes_per_regime") or 5)
    min_legs = int(prom.get("min_closed_legs_per_regime") or 15)
    required = list(prom.get("regimes_required_for_global_flip") or ["bull", "bear", "flat"])
    min_ready = int(prom.get("min_regimes_ready") or len(required))

    started = coll.get("started_at")
    shadow_days = 0.0
    if started:
        try:
            t0 = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
            if t0.tzinfo is None:
                t0 = t0.replace(tzinfo=timezone.utc)
            shadow_days = (_now() - t0).total_seconds() / 86400.0
        except Exception:
            pass

    by = coll.get("by_regime") or {}
    days_seen = coll.get("days_regime_seen") or {}
    per: Dict[str, Any] = {}
    ready_list = []
    for reg in required:
        ep = int((by.get(reg) or {}).get("would_fire_episodes") or 0)
        dcount = len(days_seen.get(reg) or [])
        # closed legs filled by offline re-runs (optional field)
        closed = int((by.get(reg) or {}).get("closed_legs_observed") or 0)
        reg_ready = ep >= min_ep and (closed >= min_legs or ep >= min_ep * 2)
        # calendar per-regime soft: at least 7 distinct days seen in that regime OR global days gate later
        per[reg] = {
            "would_fire_episodes": ep,
            "episodes_needed": min_ep,
            "closed_legs_observed": closed,
            "closed_legs_needed": min_legs,
            "distinct_days_seen": dcount,
            "episode_gate_met": ep >= min_ep,
            "ready_hint": reg_ready and ep >= min_ep,
        }
        if per[reg]["ready_hint"]:
            ready_list.append(reg)

    calendar_ok = shadow_days >= days_needed
    early_ok = shadow_days >= early
    n_ready = len(ready_list)
    review_ready = (
        calendar_ok
        and n_ready >= min_ready
        and not bool(prom.get("auto_promote"))
    )
    early_review = early_ok and n_ready >= 1 and not review_ready

    return {
        "shadow_days": round(shadow_days, 2),
        "days_needed": days_needed,
        "early_review_days": early,
        "regimes_required": required,
        "regimes_ready_hint": ready_list,
        "n_regimes_ready_hint": n_ready,
        "min_regimes_ready": min_ready,
        "per_regime": per,
        "ready_for_settings_flip_review": review_ready,
        "early_review_ok": early_review,
        "auto_promote": False,
        "action_if_ready": prom.get("action_if_ready"),
        "note": "ready_hint uses shadow episodes; still re-run offline study + Brad OK before any live map.",
    }


def _fingerprint(signals: List[MapSignal], regime: str) -> str:
    """Stable identity for an ongoing would-fire condition.

    Do NOT include mark r / RSI — those jitter every cycle and re-spam Telegram.
    Identity = regime + pair + kind only.
    """
    parts = sorted(f"{s.pair}:{s.kind}" for s in signals)
    raw = f"{regime}|" + "|".join(parts)
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _should_notify(fp: str, hours: float) -> bool:
    try:
        d = json.loads(DEDUPE_PATH.read_text(encoding="utf-8")) if DEDUPE_PATH.exists() else {}
    except Exception:
        d = {}
    fps = d.get("fingerprints") or {}
    prev = fps.get(fp)
    if prev:
        try:
            t = datetime.fromisoformat(str(prev).replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            if _now() - t < timedelta(hours=hours):
                return False
        except Exception:
            pass
    fps[fp] = _iso()
    cut = _now() - timedelta(days=7)
    kept = {}
    for k, v in fps.items():
        try:
            t = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            if t >= cut:
                kept[k] = v
        except Exception:
            kept[k] = v
    DEDUPE_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEDUPE_PATH.write_text(json.dumps({"fingerprints": kept}, indent=2), encoding="utf-8")
    return True


def _telegram(html: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    try:
        import requests

        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": html,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        return r.status_code == 200
    except Exception as e:
        logger.warning("regime_exit_shadow telegram failed: %s", e)
        return False


def append_events(signals: List[MapSignal], mode: str) -> None:
    if not signals:
        return
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with EVENTS_PATH.open("a", encoding="utf-8") as f:
        for s in signals:
            row = {"ts": _iso(), "mode": mode, **asdict(s)}
            f.write(json.dumps(row, default=str) + "\n")


def run_regime_exit_shadow_cycle(
    held_usd: Dict[str, float],
    prices: Dict[str, float],
    *,
    positions: Optional[Dict[str, Any]] = None,
    rsi_by_pair: Optional[Dict[str, float]] = None,
    mmap: Optional[Dict[str, Any]] = None,
    notify: Optional[bool] = None,
    prior_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    mmap = mmap or load_map()
    mode = str(mmap.get("mode") or "off").lower().strip()
    enabled = bool(mmap.get("enabled", True))
    # Force no live
    live_apply = bool(mmap.get("live_apply")) and mode == "live"
    if live_apply:
        # Safety: never live until explicitly redesigned — force shadow
        logger.warning("[REGIME-EXIT-MAP] live_apply requested but hard-blocked; forcing shadow")
        live_apply = False
        mode = "shadow"

    prior = prior_state
    if prior is None and STATE_PATH.exists():
        try:
            prior = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            prior = {}
    prior = prior or {}

    regime, reg_meta = resolve_active_regime()
    policy = policy_for_regime(mmap, regime)
    coll = _load_collection()
    if coll.get("started_at") is None and enabled and mode == "shadow":
        coll["started_at"] = _iso()
    today = _now().strftime("%Y-%m-%d")
    if enabled and mode == "shadow":
        _mark_regime_day(coll, regime, today)

    result: Dict[str, Any] = {
        "schema": "regime_exit_shadow_status_v1",
        "as_of": _iso(),
        "enabled": enabled,
        "mode": mode,
        "live_apply": False,
        "orders_placed": False,
        "regime": regime,
        "regime_meta": reg_meta,
        "active_policy": {
            "label": policy.get("label"),
            "source_study_call": policy.get("source_study_call"),
            "confidence": policy.get("confidence"),
            "fixed_tp": policy.get("fixed_tp"),
            "trail": policy.get("trail"),
            "rsi_hard_exit": policy.get("rsi_hard_exit"),
        },
        "marks": [],
        "signals": [],
        "n_signals": 0,
        "n_new_episodes": 0,
        "notified": False,
        "peak_r": dict(prior.get("peak_r") or {}),
        "promotion": None,
        "plain_english": "",
    }

    if not enabled or mode == "off":
        result["plain_english"] = "Regime exit map off."
        result["promotion"] = _promotion_progress(mmap, coll)
        _save_collection(coll)
        _write_state(result)
        return result

    # Reuse shadow_tp marks (lot basis)
    from phase6.core.shadow_tp import marks_from_holdings

    marks = marks_from_holdings(held_usd, prices, positions=positions)
    min_usd = float(mmap.get("min_position_usd") or 25.0)
    signals, peak_r = evaluate_map_signals(
        marks,
        policy,
        regime=regime,
        rsi_by_pair=rsi_by_pair,
        peak_r=result["peak_r"],
        min_usd=min_usd,
    )
    result["peak_r"] = peak_r
    result["marks"] = [asdict(m) if hasattr(m, "__dataclass_fields__") else m for m in marks]
    # PositionMark is dataclass
    try:
        from dataclasses import is_dataclass

        result["marks"] = [asdict(m) if is_dataclass(m) else m for m in marks]
    except Exception:
        pass

    result["signals"] = [asdict(s) for s in signals]
    result["n_signals"] = len(signals)

    n_new = 0
    ts = _now()
    for s in signals:
        if _bump_episode(coll, regime, s.pair, s.kind, ts):
            n_new += 1
    result["n_new_episodes"] = n_new
    # Log ticks only for new episodes (status still shows live would-fire each cycle)
    if signals and n_new > 0:
        append_events(signals, mode=mode)

    result["promotion"] = _promotion_progress(mmap, coll)
    _save_collection(coll)

    # Plain English summary
    ftp = policy.get("fixed_tp") or {}
    rsi_he = policy.get("rsi_hard_exit") or {}
    tp_s = f"TP {float(ftp['pct'])*100:.0f}%" if ftp.get("enabled") and ftp.get("pct") is not None else "TP off"
    rsi_s = (
        f"RSI≥{float(rsi_he['overbought']):.0f} watch"
        if rsi_he.get("enabled") and rsi_he.get("overbought") is not None
        else "RSI exit off"
    )
    trail_s = "trail on" if (policy.get("trail") or {}).get("enabled") else "trail off"
    result["plain_english"] = (
        f"Regime **{regime}** → shadow knobs: {tp_s}, {trail_s}, {rsi_s}. "
        f"Would-fire now: {len(signals)} (new episodes this cycle: {n_new}). "
        f"No orders. Collection day {result['promotion'].get('shadow_days')}/"
        f"{result['promotion'].get('days_needed')}."
    )

    do_notify = bool(mmap.get("notify_on_would_fire", True)) if notify is None else notify
    # Notify only on NEW episodes + stable fingerprint (pair/kind, not jittering r)
    if signals and n_new > 0 and do_notify and mode == "shadow":
        fp = _fingerprint(signals, regime)
        if _should_notify(fp, float(mmap.get("notify_dedupe_hours") or 12)):
            lines = [
                "<b>SHADOW regime-exit map</b> (no order)",
                f"regime=<code>{regime}</code> · {tp_s} · {trail_s} · {rsi_s}",
                "",
            ]
            for s in signals[:8]:
                lines.append(f"• <b>{s.pair}</b> {s.kind} r={s.r:.2%} ${s.would_exit_usd:.0f}")
                lines.append(f"  {s.detail}")
            prom = result["promotion"] or {}
            lines += [
                "",
                f"Collection: {prom.get('shadow_days')}d / {prom.get('days_needed')}d · "
                f"regimes ready hint: {prom.get('regimes_ready_hint')}",
                "Evidence only — live flip needs full gates + Brad OK.",
                "You get this once per new episode (not every price tick).",
            ]
            result["notified"] = _telegram("\n".join(lines))
            result["notify_fingerprint"] = fp
    elif signals and n_new == 0:
        result["notify_suppressed"] = "ongoing_episode_no_reping"

    _write_state(result)
    if signals:
        logger.info(
            "[REGIME-EXIT-MAP] regime=%s n=%s new_ep=%s pairs=%s",
            regime,
            len(signals),
            n_new,
            [s.pair for s in signals],
        )
    return result


def _write_state(result: Dict[str, Any]) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    except Exception as e:
        logger.warning("regime_exit_shadow state write failed: %s", e)


def apply_regime_exit_shadow_from_runner(runner: Any) -> Dict[str, Any]:
    """Hook for phase6 runner cycle — shadow only, no orders."""
    held: Dict[str, float] = {}
    prices: Dict[str, float] = {}
    positions: Dict[str, Any] = {}

    try:
        from phase6.core.shadow_tp import (
            _filter_junk_held,
            _held_from_live_state_file,
            _ingest_position_row,
        )

        held, prices, positions = _held_from_live_state_file()
        if not held:
            try:
                port = getattr(runner, "portfolio", None) or getattr(runner, "live_portfolio", None)
                if port and hasattr(port, "get_positions"):
                    pos = port.get_positions() or []
                    for p in pos:
                        if not isinstance(p, dict):
                            continue
                        pair = p.get("pair") or p.get("product_id")
                        if pair:
                            _ingest_position_row(str(pair), p, held, prices, positions)
            except Exception:
                pass
        held = _filter_junk_held(held)
    except Exception as e:
        logger.debug("regime_exit holdings: %s", e)

    rsi_by_pair: Dict[str, float] = {}
    try:
        rv = getattr(runner, "rsi_values", None) or {}
        if isinstance(rv, dict):
            for k, v in rv.items():
                try:
                    if isinstance(v, dict):
                        if v.get("rsi") is not None:
                            rsi_by_pair[str(k)] = float(v["rsi"])
                    else:
                        rsi_by_pair[str(k)] = float(v)  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    pass
    except Exception:
        pass
    if not rsi_by_pair:
        for name in ("rsi_cache.json", "rsi_values.json"):
            p = PROJECT_ROOT / "data" / "state" / name
            if not p.exists():
                continue
            try:
                blob = json.loads(p.read_text(encoding="utf-8"))
                if not isinstance(blob, dict):
                    continue
                src = blob.get("values") if isinstance(blob.get("values"), dict) else blob
                if not isinstance(src, dict):
                    continue
                for k, v in src.items():
                    if k in ("as_of", "updated_at", "schema"):
                        continue
                    try:
                        if isinstance(v, dict) and v.get("rsi") is not None:
                            rsi_by_pair[str(k)] = float(v["rsi"])
                        elif not isinstance(v, dict):
                            rsi_by_pair[str(k)] = float(v)  # type: ignore[arg-type]
                    except (TypeError, ValueError):
                        pass
            except Exception:
                pass

    return run_regime_exit_shadow_cycle(
        held, prices, positions=positions, rsi_by_pair=rsi_by_pair
    )
