"""
Post-SL residual dust sweep.

Why this exists
---------------
SL attach uses safety_ratio (default 0.98) on *available* balance so Coinbase
does not reject stops with PREVIEW_INSUFFICIENT_FUND. That intentionally leaves
~2% uncovered. When the stop fills, that residual stays as wallet dust and
clutters Positions / NAV. There is no portfolio reason to keep it.

This module market-sells residual after a stop fill (and can sweep orphan dust
under a USD cap) so exits leave a clean book.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from phase6.core.paths import PROJECT_ROOT
from phase6.core.shadow_tp import is_tp_excluded_pair

# protected_market_exit SSOT import at top so tests can patch("...sl_dust_sweep.protected_market_exit")
from phase6.core.protected_market_exit import protected_market_exit

logger = logging.getLogger(__name__)

STATE_PATH = PROJECT_ROOT / "data/state/sl_dust_sweep_latest.json"
DEFAULT_MAX_USD = 50.0
DEFAULT_MIN_USD = 0.50
DEFAULT_MAX_FRAC_OF_FILL = 0.06  # 2% buffer + slack
STABLE = frozenset({"USD", "USDC", "USDT", "DAI", "EUR", "GBP"})


def load_dust_sweep_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    rm = (config or {}).get("risk_management") or {}
    gs = (config or {}).get("global_settings") or {}
    enabled = rm.get("dust_sweep_after_sl", gs.get("dust_sweep_after_sl", True))
    return {
        "enabled": bool(enabled),
        "max_usd": float(rm.get("dust_sweep_max_usd", DEFAULT_MAX_USD)),
        "min_usd": float(rm.get("dust_sweep_min_usd", DEFAULT_MIN_USD)),
        "max_frac_of_fill": float(
            rm.get("dust_sweep_max_frac_of_fill", DEFAULT_MAX_FRAC_OF_FILL)
        ),
        "cycle_orphan_sweep": bool(rm.get("dust_sweep_orphan_each_cycle", True)),
    }


def asset_from_pair(pair: str) -> str:
    return pair.split("-")[0] if "-" in pair else pair


def residual_is_sweepable(
    *,
    residual_qty: float,
    residual_usd: float,
    filled_qty: float = 0.0,
    max_usd: float = DEFAULT_MAX_USD,
    min_usd: float = DEFAULT_MIN_USD,
    max_frac_of_fill: float = DEFAULT_MAX_FRAC_OF_FILL,
) -> tuple[bool, str]:
    """
    Gate: residual must be real dust, not a large leftover from a failed partial stop.
    """
    if residual_qty <= 0 or residual_usd <= 0:
        return False, "zero_residual"
    if residual_usd < min_usd:
        return False, "below_min_usd"
    if residual_usd > max_usd:
        return False, "above_max_usd"
    if filled_qty and filled_qty > 0:
        frac = residual_qty / filled_qty
        if frac > max_frac_of_fill:
            return False, f"frac_of_fill={frac:.4f}>{max_frac_of_fill}"
    return True, "ok"


def read_residual_balance(exchange: Any, pair: str) -> Dict[str, float]:
    """Return {qty_avail, qty_total, price, usd_avail, usd_total}."""
    asset = asset_from_pair(pair)
    avail = 0.0
    total = 0.0
    price = 0.0
    try:
        if hasattr(exchange, "get_crypto_available"):
            avail = float(exchange.get_crypto_available(asset) or 0.0)
    except Exception as exc:
        logger.debug("get_crypto_available %s: %s", asset, exc)
    try:
        if hasattr(exchange, "get_holdings_verified"):
            hv = exchange.get_holdings_verified() or {}
            pos = hv.get("positions") or {}
            total = float(pos.get(asset, 0.0) or 0.0)
        elif hasattr(exchange, "get_holdings"):
            h = exchange.get_holdings() or {}
            total = float(h.get(asset, 0.0) or 0.0)
    except Exception as exc:
        logger.debug("holdings %s: %s", asset, exc)
    try:
        if hasattr(exchange, "get_price"):
            price = float(exchange.get_price(pair) or 0.0)
    except Exception:
        price = 0.0
    qty = max(avail, 0.0)
    if qty <= 0 and total > 0:
        qty = total
    return {
        "qty_avail": avail,
        "qty_total": total,
        "qty": qty,
        "price": price,
        "usd_avail": avail * price if price > 0 else 0.0,
        "usd_total": total * price if price > 0 else 0.0,
        "usd": qty * price if price > 0 else 0.0,
    }


def _quantize_size(exchange: Any, pair: str, size: float) -> float:
    if size <= 0:
        return 0.0
    if hasattr(exchange, "quantize_size"):
        try:
            return float(exchange.quantize_size(pair, size))
        except Exception:
            return float(size)
    return float(size)


def _ledger_dust_sell(
    exchange: Any,
    *,
    pair: str,
    qty: float,
    exit_price: float,
    order_id: Optional[str],
    reason: str,
    parent_sl_order_id: Optional[str],
    entry_price: Optional[float] = None,
) -> None:
    try:
        from phase6.core.trade_ledger import TradeLedger

        entry = float(entry_price or 0.0)
        if entry <= 0:
            try:
                from phase6.core.protective_orders_registry import lookup_entry_for_pair

                looked = lookup_entry_for_pair(parent_sl_order_id, pair) or {}
                entry = float(looked.get("entry_price") or 0.0)
            except Exception:
                entry = 0.0
        pnl = None
        pnl_pct = None
        if entry > 0 and exit_price > 0 and qty > 0:
            pnl = (exit_price - entry) * qty
            pnl_pct = (exit_price - entry) / entry
        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pair": pair,
            "side": "SELL",
            "qty": qty,
            "entry_price": entry if entry > 0 else None,
            "exit_price": exit_price if exit_price > 0 else None,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "order_id": order_id,
            "reason": reason,
            "exit_reason": reason,
            "signal_source": "sl_dust_sweep",
            "mode": "live",
            "parent_sl_order_id": parent_sl_order_id,
            "fill_verified": bool(order_id),
        }
        TradeLedger().log_trade(row, exchange=exchange)
    except Exception as exc:
        logger.warning("[DUST-SWEEP] ledger failed %s: %s", pair, exc)


def market_sell_full_available(
    exchange: Any,
    pair: str,
    *,
    dry_run: bool = False,
    reason: str = "dust_sweep_after_sl",
    parent_sl_order_id: Optional[str] = None,
    settle_wait_s: float = 2.0,
    cancel_stops: bool = True,
) -> Dict[str, Any]:
    """Market-sell all tradable base for pair through protected_market_exit SSOT.

    cancel_stops=True when hold may linger (e.g. post-SL residual).
    Protected handles: cancel stops → poll free → quantize sell → market sell → reattach or full cancel.
    """
    out: Dict[str, Any] = {
        "pair": pair,
        "reason": reason,
        "requested_qty": 0.0,
        "size": 0.0,
        "usd_est": 0.0,
        "price": 0.0,
        "dry_run": dry_run,
        "parent_sl_order_id": parent_sl_order_id,
    }

    # Wire through protected SSOT (the point of this task)
    try:
        pe = protected_market_exit(
            exchange,
            pair,
            qty=None,  # full residual free after unlock
            frac=None,
            qty_full_hint=0.0,
            entry_price=0.0,
            mark_price=0.0,
            reason=reason,
            signal_source="sl_dust_sweep",
            dry_run=dry_run,
            ledger=False,  # we call _ledger_dust_sell below to carry parent_sl + custom fields
            reattach_sl=True,
            cancel_stops=bool(cancel_stops),
        )
    except Exception as pe_exc:
        out["success"] = False
        out["error"] = f"protected_market_exit error: {pe_exc}"
        return out

    # map protected result to legacy keys expected by callers + tests
    out["success"] = bool(pe.get("success"))
    out["skipped"] = bool(pe.get("skipped", False))
    if pe.get("skip_reason"):
        out["skip_reason"] = pe.get("skip_reason")
    out["order_id"] = pe.get("order_id")
    out["exit_price"] = pe.get("exit_price")
    filled = float(pe.get("filled_qty") or pe.get("qty") or 0.0)
    out["filled_qty"] = filled
    out["size"] = pe.get("qty") or filled
    out["cancelled_stops"] = pe.get("cancelled_stops")
    out["protected_exit"] = True
    px = float(pe.get("exit_price") or 0.0)
    out["usd_est"] = filled * px if px > 0 else 0.0
    out["exchange_result"] = {
        k: pe.get(k)
        for k in ("success", "order_id", "size", "qty", "error")
        if k in pe or k in ("size",)
    }
    if pe.get("error"):
        out["error"] = pe.get("error")
    if pe.get("used_hint_fallback"):
        out["used_hint_fallback"] = True

    if out.get("success") and not dry_run:
        oid = pe.get("order_id")
        exit_px = float(pe.get("exit_price") or 0.0)
        _ledger_dust_sell(
            exchange,
            pair=pair,
            qty=filled,
            exit_price=exit_px,
            order_id=str(oid) if oid else None,
            reason=reason,
            parent_sl_order_id=parent_sl_order_id,
        )
        logger.info(
            "[DUST-SWEEP] %s sold qty=%s usd~%.2f reason=%s oid=%s (via protected)",
            pair,
            filled,
            (filled * exit_px) if exit_px else 0.0,
            reason,
            (str(oid)[:8] if oid else None),
        )
    return out


def sweep_residual_after_stop(
    exchange: Any,
    pair: str,
    *,
    filled_qty: float = 0.0,
    parent_sl_order_id: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    After a stop-loss fill is reconciled: if residual is small dust, market-sell it.
    Wired through protected_market_exit; cancel_stops=True when hold may linger.
    Honors preserve/excluded.
    """
    cfg = load_dust_sweep_config(config)
    base = {
        "pair": pair,
        "action": "sweep_residual_after_stop",
        "enabled": cfg["enabled"],
        "parent_sl_order_id": parent_sl_order_id,
        "filled_qty": filled_qty,
    }
    if is_tp_excluded_pair(pair):
        base["success"] = False
        base["skipped"] = True
        base["skip_reason"] = "preserve_or_excluded"
        logger.info("[DUST-SWEEP] skip residual %s: preserve_or_excluded", pair)
        return base
    if not cfg["enabled"]:
        base["success"] = False
        base["skipped"] = True
        base["skip_reason"] = "disabled"
        return base

    # Brief wait: stop fill releases holds; residual becomes available.
    time.sleep(0.8)
    bal = read_residual_balance(exchange, pair)
    ok, reason = residual_is_sweepable(
        residual_qty=bal["qty"],
        residual_usd=bal["usd"],
        filled_qty=float(filled_qty or 0.0),
        max_usd=cfg["max_usd"],
        min_usd=cfg["min_usd"],
        max_frac_of_fill=cfg["max_frac_of_fill"],
    )
    base["balance"] = bal
    base["gate"] = reason
    if not ok:
        base["success"] = False
        base["skipped"] = True
        base["skip_reason"] = reason
        logger.info(
            "[DUST-SWEEP] skip %s after SL: %s (qty=%s usd=%.4f)",
            pair,
            reason,
            bal["qty"],
            bal["usd"],
        )
        return base

    sell = market_sell_full_available(
        exchange,
        pair,
        dry_run=dry_run,
        reason="dust_sweep_after_sl",
        parent_sl_order_id=parent_sl_order_id,
        settle_wait_s=1.5,
        cancel_stops=True,  # hold may linger from parent SL
    )
    base.update(sell)
    base["skipped"] = False
    return base


def list_orphan_dust_from_live_state(
    *,
    max_usd: float = DEFAULT_MAX_USD,
    min_usd: float = 0.0,
    live_state_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Positions in phase6_live_state under max_usd (excluding stables)."""
    path = live_state_path or (PROJECT_ROOT / "data/state/phase6_live_state.json")
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    positions = data.get("positions") or []
    if isinstance(positions, dict):
        iter_pos = [
            {"pair": k, **(v if isinstance(v, dict) else {})}
            for k, v in positions.items()
        ]
    else:
        iter_pos = list(positions)

    dust: List[Dict[str, Any]] = []
    for pos in iter_pos:
        if not isinstance(pos, dict):
            continue
        pair = pos.get("pair") or pos.get("product_id")
        if not pair:
            continue
        asset = asset_from_pair(str(pair))
        if asset.upper() in STABLE:
            continue
        val = float(pos.get("value_usd") or 0.0)
        amt = float(pos.get("amount") or pos.get("qty") or 0.0)
        if amt <= 0 or val <= 0:
            continue
        if val < min_usd:
            continue
        if val > max_usd:
            continue
        dust.append(
            {
                "pair": str(pair),
                "value_usd": val,
                "amount": amt,
                "entry_price": pos.get("entry_price"),
            }
        )
    by_pair: Dict[str, Dict[str, Any]] = {}
    for d in dust:
        p = d["pair"]
        if p not in by_pair or d["value_usd"] > by_pair[p]["value_usd"]:
            by_pair[p] = d
    return list(by_pair.values())


def pair_has_open_stop(exchange: Any, pair: str) -> bool:
    try:
        if hasattr(exchange, "get_open_stop_orders"):
            stops = exchange.get_open_stop_orders(pair) or []
            return len(stops) > 0
        if hasattr(exchange, "get_open_orders"):
            orders = exchange.get_open_orders(pair) or []
            from phase6.core.sl_preflight import order_configuration_is_stop

            for o in orders:
                oc = o.get("order_configuration") or {}
                if order_configuration_is_stop(oc) or "stop" in str(
                    o.get("order_type", "")
                ).lower():
                    return True
    except Exception as exc:
        logger.debug("open stop check %s: %s", pair, exc)
    return False


def sweep_orphan_dust(
    exchange: Any,
    *,
    config: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
    max_usd: Optional[float] = None,
    min_usd: Optional[float] = None,
    skip_if_open_stop: bool = True,
) -> Dict[str, Any]:
    """
    Sweep all live-state dust lines under max_usd (default config).
    Skips pairs that still have an open protective stop (unless disabled).
    """
    cfg = load_dust_sweep_config(config)
    cap = float(max_usd if max_usd is not None else cfg["max_usd"])
    floor = float(min_usd if min_usd is not None else 0.0)
    candidates = list_orphan_dust_from_live_state(max_usd=cap, min_usd=floor)
    results: List[Dict[str, Any]] = []
    for c in candidates:
        pair = c["pair"]
        if is_tp_excluded_pair(pair):
            results.append(
                {
                    "pair": pair,
                    "success": False,
                    "skipped": True,
                    "skip_reason": "preserve_or_excluded",
                    "value_usd": c["value_usd"],
                }
            )
            continue
        if skip_if_open_stop and pair_has_open_stop(exchange, pair):
            results.append(
                {
                    "pair": pair,
                    "success": False,
                    "skipped": True,
                    "skip_reason": "open_stop_present",
                    "value_usd": c["value_usd"],
                }
            )
            continue
        # Prefer live balance over stale snapshot amount
        bal = read_residual_balance(exchange, pair)
        usd = bal["usd"] if bal["usd"] > 0 else float(c["value_usd"])
        qty = bal["qty"] if bal["qty"] > 0 else float(c["amount"])
        ok, gate = residual_is_sweepable(
            residual_qty=qty,
            residual_usd=usd,
            filled_qty=0.0,
            max_usd=cap,
            min_usd=max(floor, 0.0),
            max_frac_of_fill=1.0,  # orphan path: USD cap only
        )
        # Allow sub-min_usd micro dust attempts only when max_usd small path? Keep min for orphan at 0
        # so we try pennies; exchange may reject — that's fine.
        if usd > cap:
            results.append(
                {
                    "pair": pair,
                    "success": False,
                    "skipped": True,
                    "skip_reason": "above_max_usd",
                    "value_usd": usd,
                }
            )
            continue
        if qty <= 0:
            results.append(
                {
                    "pair": pair,
                    "success": False,
                    "skipped": True,
                    "skip_reason": "zero_live_qty",
                    "value_usd": usd,
                }
            )
            continue
        # For sub-min notional, still try — Coinbase may reject; capture error.
        if not ok and gate == "below_min_usd":
            # try anyway for cleanup of cents-level dust
            pass
        elif not ok:
            results.append(
                {
                    "pair": pair,
                    "success": False,
                    "skipped": True,
                    "skip_reason": gate,
                    "value_usd": usd,
                }
            )
            continue

        sell = market_sell_full_available(
            exchange,
            pair,
            dry_run=dry_run,
            reason="dust_sweep_orphan",
            parent_sl_order_id=None,
            settle_wait_s=0.5,
            cancel_stops=True,  # defensive even for orphan (no open stop per gate)
        )
        sell["value_usd_snapshot"] = c["value_usd"]
        results.append(sell)

    summary = {
        "ok": all(r.get("success") or r.get("skipped") for r in results) if results else True,
        "dry_run": dry_run,
        "max_usd": cap,
        "candidates": len(candidates),
        "results": results,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    except Exception:
        pass
    return summary
