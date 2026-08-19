#!/usr/bin/env python3
"""Shadow / automated take-profit + trail evaluator (TG-04 design).

Philosophy: few end-user knobs in config/exit_automation.json.
  mode=off     — disabled
  mode=shadow  — evaluate open book, write state, optional Telegram would-fire
  mode=live    — reserved: attach fixed TP on buys when live_attach_on_buy;
                 market trail exits only if live_market_exit (default false)

Does NOT place orders in shadow. Does NOT mutate take_profit_pct in trading_config.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from phase6.core.paths import PROJECT_ROOT

logger = logging.getLogger("phase6.shadow_tp")

CFG_PATH = PROJECT_ROOT / "config" / "exit_automation.json"
STATE_PATH = PROJECT_ROOT / "data" / "state" / "shadow_tp_status.json"
EVENTS_PATH = PROJECT_ROOT / "data" / "state" / "shadow_tp_events.jsonl"
DEDUPE_PATH = PROJECT_ROOT / "data" / "state" / "shadow_tp_notify_dedupe.json"
REGISTRY_PATH = PROJECT_ROOT / "data" / "state" / "protective_orders_registry.jsonl"
TRADES_PATH = PROJECT_ROOT / "trades" / "phase6_trades.jsonl"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _now()).isoformat()


def load_exit_automation(path: Optional[Path] = None) -> Dict[str, Any]:
    p = path or CFG_PATH
    if not p.exists():
        return {
            "take_profit": {"mode": "off", "fixed_tp_pct": 0.06, "trail": {"enabled": False}},
        }
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("exit_automation load failed: %s", e)
        return {"take_profit": {"mode": "off"}}


def _tp_cfg(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return dict(cfg.get("take_profit") or {})


@dataclass
class PositionMark:
    pair: str
    usd: float
    qty: float
    mark_px: float
    entry_px: Optional[float]
    entry_source: str
    r: Optional[float]  # (mark-entry)/entry


@dataclass
class ShadowSignal:
    pair: str
    kind: str  # fixed_tp | trail | breakeven_lock
    r: float
    entry_px: float
    mark_px: float
    usd: float
    detail: str
    would_exit_usd: float


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


def entry_from_protective_registry(pair: str) -> Optional[Tuple[float, str]]:
    if not REGISTRY_PATH.exists():
        return None
    last = None
    try:
        for line in REGISTRY_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("pair") != pair:
                continue
            ep = r.get("entry_price") or r.get("anchor_entry") or r.get("entry")
            if ep is None:
                continue
            try:
                last = (float(ep), "protective_registry")
            except (TypeError, ValueError):
                continue
    except Exception:
        return None
    return last


def entry_from_ledger_last_buy(pair: str) -> Optional[Tuple[float, str]]:
    if not TRADES_PATH.exists():
        return None
    last = None
    try:
        for line in TRADES_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("pair") != pair:
                continue
            if str(r.get("side") or "").upper() != "BUY":
                continue
            px = r.get("entry_price") or r.get("price") or r.get("avg_price") or r.get("fill_price")
            if px is None:
                continue
            try:
                last = (float(px), "ledger_last_buy")
            except (TypeError, ValueError):
                continue
    except Exception:
        return None
    return last


def resolve_entry(
    pair: str,
    position: Optional[Dict[str, Any]] = None,
    *,
    qty: Optional[float] = None,
) -> Tuple[Optional[float], str]:
    """Resolve open-lot entry for shadow r.

    Order:
      1. position.entry_price when entry_basis is set (lot recompute already ran)
      2. FIFO/LIFO ledger lot basis (same as dashboard) — beats bare lying entry
      3. bare position.entry_price fallback
      4. protective registry / last buy
    """
    # qty from arg or position
    q = qty
    if q is None and position:
        for k in ("amount", "qty", "quantity", "size", "base_size"):
            if position.get(k) is not None:
                try:
                    qf = float(position.get(k))
                    if qf > 0:
                        q = qf
                        break
                except (TypeError, ValueError):
                    pass
        if (q is None or q <= 0) and position.get("value_usd") and (
            position.get("current_price") or position.get("price")
        ):
            try:
                px = float(position.get("current_price") or position.get("price") or 0)
                usd = float(position.get("value_usd") or position.get("usd") or 0)
                if px > 0 and usd > 0:
                    q = usd / px
            except (TypeError, ValueError):
                pass

    # Trusted state: enrich / recompute already stamped basis
    if position and position.get("entry_basis"):
        for k in ("entry_price", "avg_entry", "cost_basis"):
            v = position.get(k)
            if v is None:
                continue
            try:
                f = float(v)
            except (TypeError, ValueError):
                continue
            if f > 0:
                return f, f"position.{k}+{position.get('entry_basis')}"

    try:
        from phase6.core.position_cost_basis import average_cost_for_pair
        from phase6.core.trade_ledger import TradeLedger

        entry, basis = average_cost_for_pair(TradeLedger(), pair, expected_qty=q)
        if entry and float(entry) > 0:
            return float(entry), str(basis or "ledger_lot")
    except Exception as e:
        logger.debug("shadow_tp lot basis %s: %s", pair, e)

    if position:
        for k in ("entry_price", "avg_entry", "cost_basis", "basis"):
            v = position.get(k)
            if v is not None:
                try:
                    f = float(v)
                    if f > 0:
                        return f, f"position.{k}"
                except (TypeError, ValueError):
                    pass
    reg = entry_from_protective_registry(pair)
    if reg:
        return reg
    led = entry_from_ledger_last_buy(pair)
    if led:
        return led
    return None, "unknown"


def marks_from_holdings(
    held_usd: Dict[str, float],
    prices: Dict[str, float],
    positions: Optional[Dict[str, Any]] = None,
) -> List[PositionMark]:
    positions = positions or {}
    out: List[PositionMark] = []
    for pair, usd in (held_usd or {}).items():
        try:
            u = float(usd or 0)
        except (TypeError, ValueError):
            continue
        if u <= 0:
            continue
        px = prices.get(pair)
        try:
            px_f = float(px) if px is not None else 0.0
        except (TypeError, ValueError):
            px_f = 0.0
        pos = positions.get(pair) if isinstance(positions.get(pair), dict) else {}
        qty_hint = None
        if px_f > 0 and u > 0:
            qty_hint = u / px_f
        if isinstance(pos, dict):
            for k in ("amount", "qty", "quantity", "size"):
                if pos.get(k) is not None:
                    try:
                        qty_hint = float(pos.get(k)) or qty_hint
                    except (TypeError, ValueError):
                        pass
        entry, src = resolve_entry(pair, pos, qty=qty_hint)
        qty = 0.0
        if px_f > 0:
            qty = u / px_f
        if qty_hint and qty_hint > 0:
            qty = qty_hint
        r = None
        if entry and entry > 0 and px_f > 0:
            r = (px_f - entry) / entry
        out.append(
            PositionMark(
                pair=pair,
                usd=u,
                qty=qty,
                mark_px=px_f,
                entry_px=entry,
                entry_source=src,
                r=r,
            )
        )
    return out


def evaluate_signals(
    marks: List[PositionMark],
    tp_cfg: Dict[str, Any],
    *,
    peak_r: Optional[Dict[str, float]] = None,
) -> Tuple[List[ShadowSignal], Dict[str, float]]:
    """Return signals + updated peak_r by pair (max favorable r seen)."""
    peak_r = dict(peak_r or {})
    fixed = float(tp_cfg.get("fixed_tp_pct") or 0.06)
    trail = dict(tp_cfg.get("trail") or {})
    trail_on = bool(trail.get("enabled", True))
    arm = float(trail.get("arm_pct") or 0.04)
    trail_pct = float(trail.get("trail_pct") or 0.02)
    be = float(trail.get("breakeven_lock_pct") or 0.005)
    min_usd = float(tp_cfg.get("min_position_usd") or 25.0)

    signals: List[ShadowSignal] = []
    for m in marks:
        if m.usd < min_usd or m.r is None or m.entry_px is None or m.mark_px <= 0:
            continue
        r = float(m.r)
        prev_peak = peak_r.get(m.pair)
        peak = max(prev_peak, r) if prev_peak is not None else r
        peak_r[m.pair] = peak

        # Fixed TP: mark at or above target
        if r >= fixed - 1e-12:
            signals.append(
                ShadowSignal(
                    pair=m.pair,
                    kind="fixed_tp",
                    r=r,
                    entry_px=m.entry_px,
                    mark_px=m.mark_px,
                    usd=m.usd,
                    detail=f"r={r:.4f} >= fixed_tp {fixed}",
                    would_exit_usd=round(m.usd, 2),
                )
            )

        if trail_on and peak >= arm:
            # Stop level in r-space: max(peak - trail, be)
            stop_r = max(peak - trail_pct, be)
            if r <= stop_r + 1e-12:
                signals.append(
                    ShadowSignal(
                        pair=m.pair,
                        kind="trail",
                        r=r,
                        entry_px=m.entry_px,
                        mark_px=m.mark_px,
                        usd=m.usd,
                        detail=f"armed peak_r={peak:.4f} stop_r={stop_r:.4f} mark_r={r:.4f}",
                        would_exit_usd=round(m.usd, 2),
                    )
                )
            elif r >= be and peak >= arm and r < fixed:
                # informational: armed, trail active, not firing
                pass

    return signals, peak_r


def _fingerprint(signals: List[ShadowSignal]) -> str:
    parts = sorted(f"{s.pair}:{s.kind}:{round(s.r, 3)}" for s in signals)
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


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
        logger.warning("shadow_tp telegram failed: %s", e)
        return False


def append_events(signals: List[ShadowSignal], mode: str) -> None:
    if not signals:
        return
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with EVENTS_PATH.open("a", encoding="utf-8") as f:
        for s in signals:
            f.write(
                json.dumps(
                    {
                        "ts": _iso(),
                        "mode": mode,
                        **asdict(s),
                    },
                    default=str,
                )
                + "\n"
            )


def run_shadow_tp_cycle(
    held_usd: Dict[str, float],
    prices: Dict[str, float],
    *,
    positions: Optional[Dict[str, Any]] = None,
    cfg: Optional[Dict[str, Any]] = None,
    notify: Optional[bool] = None,
    prior_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    cfg = cfg or load_exit_automation()
    tp = _tp_cfg(cfg)
    mode = str(tp.get("mode") or "off").lower().strip()
    prior = prior_state
    if prior is None and STATE_PATH.exists():
        try:
            prior = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            prior = {}
    prior = prior or {}

    result: Dict[str, Any] = {
        "schema": "shadow_tp_status_v1",
        "as_of": _iso(),
        "mode": mode,
        "live_config_take_profit_pct": None,  # never auto-write trading_config
        "marks": [],
        "signals": [],
        "n_signals": 0,
        "notified": False,
        "peak_r": dict(prior.get("peak_r") or {}),
        "would_fire_count_total": int(prior.get("would_fire_count_total") or 0),
        "first_shadow_at": prior.get("first_shadow_at"),
        "promotion_hint": None,
    }

    if mode == "off":
        _write_state(result)
        return result

    if mode == "live" and not bool(tp.get("live_attach_on_buy")) and not bool(tp.get("live_market_exit")):
        result["note"] = "mode=live but both live_attach_on_buy and live_market_exit false — acting as shadow"
        mode = "shadow"
        result["mode"] = "shadow"

    marks = marks_from_holdings(held_usd, prices, positions=positions)
    # Drop peaks from lying lifetime cost basis (e.g. BTC peak_r~0.50 while true r~0.03)
    peak_in = dict(result["peak_r"] or {})
    peak_sanitized = False
    mark_by = {m.pair: m for m in marks}
    for pair, pk in list(peak_in.items()):
        m = mark_by.get(pair)
        if not m or m.r is None:
            continue
        try:
            pk_f = float(pk)
            r_f = float(m.r)
        except (TypeError, ValueError):
            continue
        if pk_f - r_f > 0.15 and r_f < 0.08:
            logger.info(
                "[SHADOW-TP] reset peak_r %s %.4f -> %.4f (stale peak vs lot basis)",
                pair,
                pk_f,
                r_f,
            )
            peak_in[pair] = r_f
            peak_sanitized = True
    if peak_sanitized:
        # Prior would-fire totals / calendar are not trustworthy after basis repair
        result["would_fire_count_total"] = 0
        result["first_shadow_at"] = _iso()
        result["peak_r_reset_reason"] = "entry_basis_repair"
        result["would_fire_reset_at"] = _iso()

    signals, peak_r = evaluate_signals(marks, tp, peak_r=peak_in)
    result["peak_r"] = peak_r
    result["marks"] = [asdict(m) for m in marks]
    result["signals"] = [asdict(s) for s in signals]
    result["n_signals"] = len(signals)
    if result.get("first_shadow_at") is None and mode == "shadow":
        result["first_shadow_at"] = _iso()
    if signals:
        result["would_fire_count_total"] = int(result["would_fire_count_total"]) + len(signals)
        append_events(signals, mode=mode)

    # Promotion hint (settings flip — not per-trade)
    prom = dict(cfg.get("promotion") or {})
    days_needed = int(prom.get("shadow_min_calendar_days") or 7)
    events_needed = int(prom.get("shadow_min_would_fire_events") or 5)
    shadow_days = 0.0
    if result.get("first_shadow_at"):
        try:
            t0 = datetime.fromisoformat(str(result["first_shadow_at"]).replace("Z", "+00:00"))
            if t0.tzinfo is None:
                t0 = t0.replace(tzinfo=timezone.utc)
            shadow_days = (_now() - t0).total_seconds() / 86400.0
        except Exception:
            pass
    ready = (
        shadow_days >= days_needed
        and int(result["would_fire_count_total"]) >= events_needed
        and not bool(prom.get("auto_promote"))
    )
    result["promotion_hint"] = {
        "shadow_days": round(shadow_days, 2),
        "days_needed": days_needed,
        "would_fire_count_total": result["would_fire_count_total"],
        "events_needed": events_needed,
        "ready_for_settings_flip_review": ready,
        "action_if_ready": "Set take_profit.mode=live and live_attach_on_buy=true (one-time knob). Not per-trade approve.",
    }

    do_notify = bool(tp.get("notify_on_would_fire", True)) if notify is None else notify
    if signals and do_notify and mode == "shadow":
        fp = _fingerprint(signals)
        if _should_notify(fp, float(tp.get("notify_dedupe_hours") or 12)):
            lines = [
                "<b>SHADOW TP would-fire</b> (no order)",
                f"mode=<code>{mode}</code> · knobs in exit_automation.json",
                "",
            ]
            for s in signals[:8]:
                lines.append(
                    f"• <b>{s.pair}</b> {s.kind} r={s.r:.2%} ${s.would_exit_usd:.0f}"
                )
                lines.append(f"  {s.detail}")
            lines += [
                "",
                "Not a decision request — evidence for eventual one-time mode flip.",
                "Hard exits stay on operator loop until you turn operator_approve off.",
            ]
            result["notified"] = _telegram("\n".join(lines))
            result["notify_fingerprint"] = fp

    _write_state(result)
    if signals:
        logger.info(
            "[SHADOW-TP] mode=%s n=%s pairs=%s",
            mode,
            len(signals),
            [s.pair for s in signals],
        )
    return result


def _write_state(result: Dict[str, Any]) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    except Exception as e:
        logger.warning("shadow_tp state write failed: %s", e)


_CASH_PAIRS = frozenset({"USD", "USDC", "USDT", "EUR", "GBP"})
_FAKE_HOLDING_KEYS = frozenset({"VERIFIED", "TOTAL", "CASH", "ALL"})


def _is_tradable_pair(pair: str) -> bool:
    p = (pair or "").strip().upper()
    if not p or p in _CASH_PAIRS or p in _FAKE_HOLDING_KEYS:
        return False
    # Prefer product ids like BTC-USD; allow bare BTC if ever passed
    if p in _FAKE_HOLDING_KEYS:
        return False
    return True


def _ingest_position_row(
    pair: str,
    row: Dict[str, Any],
    held: Dict[str, float],
    prices: Dict[str, float],
    positions: Dict[str, Any],
) -> None:
    if not _is_tradable_pair(pair):
        return
    try:
        usd = float(row.get("usd") or row.get("value_usd") or 0)
    except (TypeError, ValueError):
        usd = 0.0
    if usd <= 0:
        return
    held[pair] = usd
    positions[pair] = row
    px = row.get("price") or row.get("mark_px") or row.get("last_price")
    if px is None:
        # Derive mark from entry + unrealized fraction when price missing
        try:
            entry = float(row.get("entry_price") or 0)
            up = row.get("unrealized_pnl_pct")
            if entry > 0 and up is not None:
                u = float(up)
                # live_state stores fraction (0.01 = 1%), not 1.0 = 1%
                px = entry * (1.0 + u)
        except (TypeError, ValueError):
            px = None
    if px is not None:
        try:
            pf = float(px)
            if pf > 0:
                prices[pair] = pf
        except (TypeError, ValueError):
            pass


def _held_from_live_state_file() -> tuple[Dict[str, float], Dict[str, float], Dict[str, Any]]:
    """Fallback when runner portfolio API returns empty/junk (e.g. only 'verified')."""
    held: Dict[str, float] = {}
    prices: Dict[str, float] = {}
    positions: Dict[str, Any] = {}
    path = PROJECT_ROOT / "data" / "state" / "phase6_live_state.json"
    if not path.exists():
        return held, prices, positions
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return held, prices, positions
    rows = d.get("trading_positions") or d.get("positions") or []
    if isinstance(rows, dict):
        for pair, v in rows.items():
            if isinstance(v, dict):
                _ingest_position_row(str(pair), v, held, prices, positions)
            else:
                try:
                    u = float(v or 0)
                except (TypeError, ValueError):
                    continue
                if u > 0 and _is_tradable_pair(str(pair)):
                    held[str(pair)] = u
    else:
        for p in rows or []:
            if not isinstance(p, dict):
                continue
            pair = p.get("pair") or p.get("product_id")
            if pair:
                _ingest_position_row(str(pair), p, held, prices, positions)
    return held, prices, positions


def _filter_junk_held(held: Dict[str, float]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for k, v in (held or {}).items():
        if not _is_tradable_pair(str(k)):
            continue
        try:
            u = float(v or 0)
        except (TypeError, ValueError):
            continue
        if u > 0:
            out[str(k)] = u
    return out


def apply_shadow_tp_from_runner(runner: Any) -> Dict[str, Any]:
    """Hook for phase6 runner / rebalance path."""
    cfg = load_exit_automation()
    tp = _tp_cfg(cfg)
    if str(tp.get("mode") or "off").lower() == "off":
        return {"mode": "off", "n_signals": 0}

    held: Dict[str, float] = {}
    prices: Dict[str, float] = {}
    positions: Dict[str, Any] = {}

    # Prefer portfolio helpers
    try:
        pf = getattr(runner, "portfolio", None)
        if pf and hasattr(pf, "get_holdings_usd"):
            held = dict(pf.get_holdings_usd() or {})
        elif pf and hasattr(pf, "get_positions"):
            raw = pf.get_positions() or {}
            for k, v in raw.items():
                if isinstance(v, dict):
                    _ingest_position_row(str(k), v, held, prices, positions)
                else:
                    try:
                        u = float(v or 0)
                    except (TypeError, ValueError):
                        continue
                    if u > 0 and _is_tradable_pair(str(k)):
                        held[str(k)] = u
    except Exception as e:
        logger.debug("shadow_tp holdings: %s", e)

    held = _filter_junk_held(held)

    if not held:
        # dashboard cache fallback
        try:
            dash = PROJECT_ROOT / "data/state/dashboard_cache.json"
            if dash.exists():
                d = json.loads(dash.read_text(encoding="utf-8"))
                for p in d.get("positions") or []:
                    pair = p.get("pair") or p.get("product_id")
                    if not pair:
                        continue
                    _ingest_position_row(str(pair), p, held, prices, positions)
        except Exception:
            pass
        held = _filter_junk_held(held)

    if not held:
        # live_state fallback — real open book when portfolio API is empty/junk
        h2, p2, pos2 = _held_from_live_state_file()
        held, prices, positions = h2, p2, pos2
        held = _filter_junk_held(held)

    # prices from runner
    try:
        snap = getattr(runner, "price_snapshot", None) or getattr(runner, "prices", None) or {}
        if isinstance(snap, dict):
            for k, v in snap.items():
                try:
                    prices[k] = float(v)
                except (TypeError, ValueError):
                    pass
    except Exception:
        pass

    # fill missing prices via exchange
    ex = getattr(runner, "exchange", None)
    if ex and hasattr(ex, "get_price"):
        for pair in list(held.keys()):
            if pair not in prices or not prices[pair]:
                try:
                    prices[pair] = float(ex.get_price(pair) or 0)
                except Exception:
                    pass

    return run_shadow_tp_cycle(held, prices, positions=positions, cfg=cfg)


def effective_tp_pct_for_buy(cfg: Optional[Dict[str, Any]] = None) -> Optional[float]:
    """What OrderExecutor should pass as tp_pct on new buys.

    Only non-None when mode=live AND live_attach_on_buy.
    Shadow never attaches exchange TP.
    """
    cfg = cfg or load_exit_automation()
    tp = _tp_cfg(cfg)
    if str(tp.get("mode") or "").lower() != "live":
        return None
    if not bool(tp.get("live_attach_on_buy")):
        return None
    v = tp.get("fixed_tp_pct")
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None
