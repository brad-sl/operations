#!/usr/bin/env python3
"""Bear profit-take shadow — laddered scale-out into strength (NO shorts, NO orders in Phase 1).

See docs/features/BEAR_PROFIT_TAKE_NO_SHORT_SPEC.md
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from phase6.core.paths import PROJECT_ROOT, STATE_DIR

logger = logging.getLogger("phase6.bear_profit_take")

CFG_PATH = PROJECT_ROOT / "config" / "bear_profit_take.json"
REGIME_STATUS = STATE_DIR / "regime_cash_status.json"
STATE_PATH = STATE_DIR / "bear_profit_take_shadow_status.json"
EVENTS_PATH = STATE_DIR / "bear_profit_take_shadow_events.jsonl"
FILLED_PATH = STATE_DIR / "bear_profit_take_shadow_filled.json"  # pair -> levels filled


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _now()).isoformat()


def load_cfg(path: Optional[Path] = None) -> Dict[str, Any]:
    p = path or CFG_PATH
    if not p.exists():
        return {"enabled": False, "mode": "off", "live_apply": False}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("bear_profit_take cfg: %s", e)
        return {"enabled": False, "mode": "off", "live_apply": False}


def resolve_regime(status: Optional[Dict[str, Any]] = None) -> Tuple[str, Dict[str, Any]]:
    st = status
    if st is None and REGIME_STATUS.exists():
        try:
            st = json.loads(REGIME_STATUS.read_text(encoding="utf-8"))
        except Exception:
            st = {}
    st = st or {}
    reg = str(st.get("regime") or "unknown").lower().strip() or "unknown"
    meta = {
        "btc_return_pct": st.get("btc_return_pct"),
        "label": st.get("label"),
        "strategy_mode": st.get("strategy_mode"),
        "source": "regime_cash_status" if st else "default",
    }
    return reg, meta


@dataclass
class LadderSignal:
    pair: str
    level: int
    label: str
    r: float
    r_threshold: float
    sell_frac: float
    would_exit_usd: float
    entry_px: float
    mark_px: float
    usd: float
    kind: str  # ladder_scale_out | limit_tp_mark
    detail: str


def _load_filled() -> Dict[str, List[int]]:
    if not FILLED_PATH.exists():
        return {}
    try:
        d = json.loads(FILLED_PATH.read_text(encoding="utf-8"))
        out: Dict[str, List[int]] = {}
        for k, v in (d.get("filled") or {}).items():
            out[str(k)] = [int(x) for x in v]
        return out
    except Exception:
        return {}


def _save_filled(filled: Dict[str, List[int]]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    FILLED_PATH.write_text(
        json.dumps({"as_of": _iso(), "filled": filled}, indent=2) + "\n",
        encoding="utf-8",
    )


def evaluate_ladder(
    *,
    held_usd: Dict[str, float],
    prices: Dict[str, float],
    positions: Dict[str, Dict[str, Any]],
    cfg: Dict[str, Any],
    filled: Optional[Dict[str, List[int]]] = None,
) -> List[LadderSignal]:
    """Pure ladder eval — no I/O."""
    ladder = cfg.get("ladder") or {}
    if not ladder.get("enabled", True):
        return []
    min_usd = float(cfg.get("min_position_usd") or 25.0)
    tranches = list(ladder.get("tranches") or [])
    filled = filled if filled is not None else {}
    signals: List[LadderSignal] = []

    for pair, usd in held_usd.items():
        try:
            u = float(usd)
        except (TypeError, ValueError):
            continue
        if u < min_usd:
            continue
        if pair in ("USD", "USDC", "USDT", "USDC-USD", "USDT-USD"):
            continue
        # PAXG can still ladder if green
        pos = positions.get(pair) or {}
        try:
            entry = float(pos.get("entry_price") or pos.get("entry_px") or 0)
            mark = float(prices.get(pair) or pos.get("mark_px") or pos.get("price") or 0)
        except (TypeError, ValueError):
            continue
        if entry <= 0 or mark <= 0:
            continue
        r = (mark / entry) - 1.0
        done = set(filled.get(pair) or [])
        for tr in tranches:
            try:
                level = int(tr.get("level") or 0)
                thr = float(tr.get("r_pct") or 0)
                frac = float(tr.get("sell_frac") or 0)
            except (TypeError, ValueError):
                continue
            if level in done:
                continue
            if r + 1e-12 < thr:
                continue
            if frac <= 0:
                continue
            would = u * frac
            label = str(tr.get("label") or f"L{level}")
            signals.append(
                LadderSignal(
                    pair=pair,
                    level=level,
                    label=label,
                    r=round(r, 6),
                    r_threshold=thr,
                    sell_frac=frac,
                    would_exit_usd=round(would, 2),
                    entry_px=entry,
                    mark_px=mark,
                    usd=round(u, 2),
                    kind="ladder_scale_out",
                    detail=(
                        f"r={r:.2%} ≥ {thr:.0%} ladder → would sell {frac:.0%} "
                        f"(~${would:.0f}); leave moon bag per config"
                    ),
                )
            )
            if cfg.get("limit_tp_levels", {}).get("enabled", True):
                signals.append(
                    LadderSignal(
                        pair=pair,
                        level=level,
                        label=label,
                        r=round(r, 6),
                        r_threshold=thr,
                        sell_frac=frac,
                        would_exit_usd=round(would, 2),
                        entry_px=entry,
                        mark_px=mark,
                        usd=round(u, 2),
                        kind="limit_tp_mark",
                        detail=f"shadow limit level at +{thr:.0%} from entry (not placed on exchange)",
                    )
                )
    return signals


def _episode_key(sig: LadderSignal) -> str:
    return f"{sig.pair}|{sig.kind}|L{sig.level}"


def _append_events(rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with EVENTS_PATH.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")


def _recent_episode_keys(gap_min: int) -> set:
    if not EVENTS_PATH.exists():
        return set()
    cutoff = _now() - timedelta(minutes=gap_min)
    keys = set()
    try:
        lines = EVENTS_PATH.read_text(encoding="utf-8").splitlines()[-500:]
        for line in lines:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = d.get("ts") or d.get("as_of")
            try:
                t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if t >= cutoff and d.get("episode_key"):
                keys.add(d["episode_key"])
    except OSError:
        pass
    return keys


def plain_english_status(result: Dict[str, Any]) -> str:
    reg = result.get("regime") or "unknown"
    if not result.get("enabled"):
        return "Bear profit-take is off."
    if result.get("status") == "idle_wrong_regime":
        return (
            f"Market regime is {reg}, not bear — profit ladder is on standby "
            "(only arms in a down-market regime)."
        )
    n = int(result.get("n_new_episodes") or 0)
    if n <= 0:
        return (
            f"Bear mode watch is on. No new partial take-profit levels hit this cycle "
            f"({int(result.get('n_signals') or 0)} open signals, 0 new)."
        )
    parts = []
    for s in result.get("new_episodes") or []:
        if s.get("kind") != "ladder_scale_out":
            continue
        pair = str(s.get("pair") or "").replace("-USD", "")
        parts.append(
            f"{pair} +{float(s.get('r') or 0)*100:.1f}% → would sell "
            f"{float(s.get('sell_frac') or 0)*100:.0f}% (~${float(s.get('would_exit_usd') or 0):.0f})"
        )
    body = "; ".join(parts[:5]) if parts else f"{n} level(s)"
    dest = result.get("proceeds_destination") or "stables"
    return (
        f"Down-market playbook (shadow only — no real sell): {body}. "
        f"Proceeds would go to {dest}; no quick rebuy for "
        f"{int(result.get('rebuy_block_hours') or 72)}h. Not a short."
    )


def run_bear_profit_take_cycle(
    held_usd: Dict[str, float],
    prices: Dict[str, float],
    *,
    positions: Optional[Dict[str, Dict[str, Any]]] = None,
    cfg: Optional[Dict[str, Any]] = None,
    regime: Optional[str] = None,
    regime_meta: Optional[Dict[str, Any]] = None,
    force_regime: Optional[str] = None,
    persist_fills: bool = True,
) -> Dict[str, Any]:
    """One evaluation cycle. Never places orders."""
    cfg = cfg if cfg is not None else load_cfg()
    enabled = bool(cfg.get("enabled"))
    mode = str(cfg.get("mode") or "shadow").lower()
    # Force shadow safety
    if mode == "live" and not cfg.get("live_apply"):
        mode = "shadow"
    live_apply = bool(cfg.get("live_apply")) and mode == "live"
    # Phase 1 hard clamp
    live_apply = False
    if mode == "live":
        mode = "shadow"

    if force_regime:
        reg = force_regime.lower()
        rmeta = regime_meta or {"source": "force"}
    elif regime:
        reg = regime.lower()
        rmeta = regime_meta or {}
    else:
        reg, rmeta = resolve_regime()

    active = [str(x).lower() for x in (cfg.get("active_regimes") or ["bear"])]
    positions = positions or {}

    base = {
        "as_of": _iso(),
        "schema": "bear_profit_take_shadow_v1",
        "enabled": enabled,
        "mode": mode,
        "live_apply": live_apply,
        "orders_placed": False,
        "regime": reg,
        "regime_meta": rmeta,
        "active_regimes": active,
        "proceeds_destination": cfg.get("proceeds_destination") or "stables",
        "rebuy_block_hours": int(cfg.get("rebuy_block_hours_after_tp") or 72),
        "exclude": list(cfg.get("exclude") or []),
        "promotion": {
            "auto_promote": bool((cfg.get("promotion") or {}).get("auto_promote")),
            "require_brad_ok": True,
        },
    }

    if not enabled or mode == "off":
        base.update({"status": "off", "n_signals": 0, "n_new_episodes": 0, "signals": []})
        base["plain_english"] = plain_english_status(base)
        _write_status(base)
        return base

    if reg not in active:
        base.update(
            {
                "status": "idle_wrong_regime",
                "n_signals": 0,
                "n_new_episodes": 0,
                "signals": [],
                "new_episodes": [],
            }
        )
        base["plain_english"] = plain_english_status(base)
        _write_status(base)
        return base

    filled = _load_filled()
    sigs = evaluate_ladder(
        held_usd=held_usd,
        prices=prices,
        positions=positions,
        cfg=cfg,
        filled=filled,
    )
    gap = int(cfg.get("episode_gap_minutes") or 30)
    recent = _recent_episode_keys(gap)
    new_eps: List[Dict[str, Any]] = []
    event_rows = []
    for s in sigs:
        if s.kind != "ladder_scale_out":
            continue  # limit marks don't open episodes / fills
        ek = _episode_key(s)
        if ek in recent:
            continue
        row = {
            "ts": _iso(),
            "episode_key": ek,
            "pair": s.pair,
            "kind": s.kind,
            "level": s.level,
            "label": s.label,
            "r": s.r,
            "r_threshold": s.r_threshold,
            "sell_frac": s.sell_frac,
            "would_exit_usd": s.would_exit_usd,
            "regime": reg,
            "orders_placed": False,
        }
        new_eps.append(row)
        event_rows.append(row)
        # Mark level filled in shadow ledger so we don't re-fire forever
        fl = list(filled.get(s.pair) or [])
        if s.level not in fl:
            fl.append(s.level)
            filled[s.pair] = sorted(fl)

    if persist_fills and new_eps:
        _save_filled(filled)
    _append_events(event_rows)

    sig_dicts = [asdict(s) for s in sigs]
    base.update(
        {
            "status": "active_bear",
            "n_signals": len(sig_dicts),
            "n_new_episodes": len(new_eps),
            "signals": sig_dicts,
            "new_episodes": new_eps,
            "filled_ledger": filled,
        }
    )
    base["plain_english"] = plain_english_status(base)
    try:
        from phase6.core.trader_message_compose import compose_bear_tp_channels

        base["messages"] = compose_bear_tp_channels(base)
    except Exception as e:
        base["messages"] = {"error": str(e), "no_ai": True}
    _write_status(base)
    return base


def _write_status(payload: Dict[str, Any]) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        # Collection rollup for scoreboard / promotion gates
        coll_path = STATE_DIR / "bear_profit_take_collection.json"
        coll: Dict[str, Any] = {}
        if coll_path.exists():
            try:
                coll = json.loads(coll_path.read_text(encoding="utf-8"))
            except Exception:
                coll = {}
        if not coll.get("started_at"):
            coll["started_at"] = payload.get("as_of") or _iso()
        days = set(coll.get("bear_days_seen") or [])
        if str(payload.get("regime") or "").lower() == "bear":
            day = str(payload.get("as_of") or "")[:10]
            if len(day) >= 10:
                days.add(day)
        coll["bear_days_seen"] = sorted(days)
        coll["bear_calendar_days"] = len(days)
        n_ep = 0
        pairs_lvls: Dict[str, set] = {}
        if EVENTS_PATH.exists():
            for line in EVENTS_PATH.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                n_ep += 1
                pair = str(row.get("pair") or "")
                try:
                    lvl = int(row.get("level") or 0)
                except (TypeError, ValueError):
                    lvl = 0
                if pair:
                    pairs_lvls.setdefault(pair, set()).add(lvl)
        multi = sum(1 for lvls in pairs_lvls.values() if len([x for x in lvls if x > 0]) >= 2)
        coll["n_episodes_total"] = n_ep
        coll["n_pairs_multi_slice"] = multi
        coll["updated_at"] = payload.get("as_of") or _iso()
        coll_path.write_text(json.dumps(coll, indent=2) + "\n", encoding="utf-8")
        payload["bear_calendar_days"] = coll["bear_calendar_days"]
        payload["n_episodes_total"] = n_ep
        payload["n_pairs_multi_slice"] = multi
        payload["collection"] = {
            "started_at": coll.get("started_at"),
            "bear_calendar_days": coll["bear_calendar_days"],
            "n_episodes_total": n_ep,
        }

        STATE_PATH.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
        report = PROJECT_ROOT / "reports" / "BEAR_PROFIT_TAKE_SHADOW_LATEST.md"
        lines = [
            "# Bear profit-take shadow",
            "",
            f"**As of:** {payload.get('as_of')}",
            f"**Regime:** {payload.get('regime')} · status `{payload.get('status')}`",
            f"**Mode:** {payload.get('mode')} · orders_placed={payload.get('orders_placed')}",
            f"**Collection:** bear_days={payload.get('bear_calendar_days')} · episodes={payload.get('n_episodes_total')}",
            "",
            payload.get("plain_english") or "",
            "",
            f"New episodes: {payload.get('n_new_episodes')} · signals: {payload.get('n_signals')}",
            "",
            "_No live sells. Spec: docs/features/BEAR_PROFIT_TAKE_NO_SHORT_SPEC.md_",
            "",
        ]
        report.write_text("\n".join(lines), encoding="utf-8")
    except OSError as e:
        logger.debug("status write: %s", e)


def apply_bear_profit_take_from_runner(runner: Any = None) -> Dict[str, Any]:
    """Best-effort cycle from runner or live_state file."""
    held: Dict[str, float] = {}
    prices: Dict[str, float] = {}
    positions: Dict[str, Dict[str, Any]] = {}
    try:
        from phase6.core.shadow_tp import (
            _filter_junk_held,
            _held_from_live_state_file,
            _ingest_position_row,
        )

        held, prices, positions = _held_from_live_state_file()
        if not held and runner is not None:
            try:
                port = getattr(runner, "portfolio", None) or getattr(runner, "live_portfolio", None)
                if port and hasattr(port, "get_positions"):
                    for p in port.get_positions() or []:
                        if not isinstance(p, dict):
                            continue
                        pair = p.get("pair") or p.get("product_id")
                        if pair:
                            _ingest_position_row(str(pair), p, held, prices, positions)
            except Exception:
                pass
        held = _filter_junk_held(held)
    except Exception as e:
        logger.debug("bear_tp holdings: %s", e)

    return run_bear_profit_take_cycle(held, prices, positions=positions)
