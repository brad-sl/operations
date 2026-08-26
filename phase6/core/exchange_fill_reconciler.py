"""
P6-FILL-RECON: Ingest Coinbase FILLED orders (especially stop-limit SELLs) into TradeLedger.

Exchange-triggered stops never pass through OrderExecutor; this closes the audit gap.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from phase6.core.paths import PROJECT_ROOT
from phase6.core.sl_preflight import order_configuration_is_stop, extract_stop_price_from_order
from phase6.core.protective_orders_registry import (
    lookup_entry_for_pair,
    mark_sl_filled,
)
from phase6.core.trade_ledger import TradeLedger

logger = logging.getLogger(__name__)

CURSOR_PATH = PROJECT_ROOT / "data/state/fill_reconcile_cursor.json"
RAW_FILLS_PATH = PROJECT_ROOT / "trades/phase6_exchange_fills.jsonl"
DEFAULT_SL_PCT = 0.03

# Coinbase UI "Trading Bot" / API-key orders (Advanced Trade proxy).
TRADING_BOT_DATA_SOURCE = "ORDER_DATA_SOURCE_TRADING_PROXY"


def is_coinbase_trading_bot_order(order: Dict[str, Any]) -> bool:
    """True when order matches Coinbase ledger filter 'Trading Bot transactions only'."""
    src = str(order.get("order_data_source") or "")
    if src == TRADING_BOT_DATA_SOURCE:
        return True
    # Future: dedicated placement source values from CDP.
    return str(order.get("order_placement_source") or "").upper() in (
        "RETAIL_ADVANCED",
    ) and src in ("", "ORDER_DATA_SOURCE_TRADING_PROXY")


def _parse_ts(order: Dict[str, Any]) -> str:
    for key in ("completion_time", "created_time", "last_fill_time", "timestamp"):
        v = order.get(key)
        if v:
            return str(v)
    return datetime.now(timezone.utc).isoformat()


def _order_id(order: Dict[str, Any]) -> Optional[str]:
    return order.get("order_id") or order.get("id")


def _is_filled_stop_sell(order: Dict[str, Any]) -> bool:
    side = str(order.get("side", "")).upper()
    if side != "SELL":
        return False
    status = str(order.get("status", "")).upper()
    if status and status not in ("FILLED", "FILLED_SETTLED", "DONE", "COMPLETED"):
        return False
    oc = order.get("order_configuration") or {}
    if order_configuration_is_stop(oc):
        return True
    ot = str(order.get("order_type", "")).lower()
    if "stop" in ot:
        return True
    return False


def _load_ledger_order_ids(ledger: TradeLedger) -> Set[str]:
    ids: Set[str] = set()
    path = ledger.jsonl_path
    if not path.exists():
        return ids
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            oid = row.get("order_id") or row.get("sl_order_id")
            if oid:
                ids.add(str(oid))
    return ids


def _load_cursor() -> Dict[str, Any]:
    if not CURSOR_PATH.exists():
        return {}
    try:
        return json.loads(CURSOR_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cursor(data: Dict[str, Any]) -> None:
    CURSOR_PATH.parent.mkdir(parents=True, exist_ok=True)
    CURSOR_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _append_raw_fill(row: Dict[str, Any]) -> None:
    RAW_FILLS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RAW_FILLS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def _entry_from_ledger_buys(ledger: TradeLedger, pair: str, before_ts: str) -> Tuple[Optional[float], str]:
    """Last BUY for pair in JSONL before fill time (best-effort)."""
    path = ledger.jsonl_path
    if not path.exists():
        return None, "none"
    try:
        fill_dt = datetime.fromisoformat(before_ts.replace("Z", "+00:00"))
    except Exception:
        fill_dt = None
    best: Optional[Dict[str, Any]] = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("pair") != pair or str(row.get("side", "")).upper() != "BUY":
                continue
            ts = row.get("timestamp")
            if fill_dt and ts:
                try:
                    tdt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                    if tdt > fill_dt:
                        continue
                except Exception:
                    pass
            ep = float(row.get("entry_price") or row.get("price") or 0)
            if ep > 0:
                best = row
    if best:
        return float(best.get("entry_price") or best.get("price")), "ledger_last_buy"
    return None, "none"


def _infer_entry_from_stop(stop_price: float, sl_pct: float = DEFAULT_SL_PCT) -> Tuple[Optional[float], str]:
    if stop_price <= 0 or sl_pct <= 0:
        return None, "none"
    # stop ≈ entry * (1 - sl_pct)
    entry = stop_price / (1.0 - sl_pct)
    return entry, "inferred_from_stop"


def _registry_entry_consistent_with_stop(
    entry_px: float, stop_px: Optional[float], *, sl_pct: float = DEFAULT_SL_PCT
) -> bool:
    """Reject registry rows where stop sits well *above* entry (stale-low basis).

    Normal crypto SL: stop ≈ entry*(1-sl) (below entry). Mild BE ratchet may put
    stop slightly above entry. A stop >> entry with a much lower entry is the
    LINK 2026-08-25 failure mode (entry $10, stop $11.28 → fake +12% PnL).
    """
    if entry_px <= 0:
        return False
    if stop_px is None or stop_px <= 0:
        return True
    # Allow stop down to deep adaptive SL and up to small BE lock above entry
    lo = entry_px * (1.0 - max(sl_pct * 2.5, 0.08))
    hi = entry_px * 1.015
    return lo <= float(stop_px) <= hi


def resolve_sl_fill_entry(
    *,
    pair: str,
    fill_ts: str,
    fill_px: float,
    ledger: TradeLedger,
    sl_order_id: Optional[str] = None,
    stop_px: Optional[float] = None,
    sl_pct: float = DEFAULT_SL_PCT,
) -> Tuple[Optional[float], str]:
    """Pick economic entry for SL fill diagnostics (prefer open-lot buy over stale registry)."""
    ledger_px, ledger_src = _entry_from_ledger_buys(ledger, pair, fill_ts)
    reg = lookup_entry_for_pair(sl_order_id, pair)
    reg_px: Optional[float] = None
    if reg and reg.get("entry_price"):
        try:
            reg_px = float(reg["entry_price"])
        except (TypeError, ValueError):
            reg_px = None
    if stop_px is None and reg and reg.get("stop_price"):
        try:
            stop_px = float(reg["stop_price"])
        except (TypeError, ValueError):
            stop_px = None

    reg_ok = bool(
        reg_px
        and reg_px > 0
        and _registry_entry_consistent_with_stop(reg_px, stop_px, sl_pct=sl_pct)
    )

    # Prefer last open-lot BUY when present and not absurd vs fill
    if ledger_px and ledger_px > 0:
        if fill_px <= 0 or abs(ledger_px - fill_px) / max(fill_px, 1e-12) <= 0.35:
            if reg_ok and reg_px is not None and abs(reg_px - ledger_px) / ledger_px <= 0.02:
                return reg_px, "protective_registry"
            if reg_px and reg_px > 0 and not reg_ok:
                return ledger_px, "ledger_last_buy_over_stale_registry"
            return ledger_px, ledger_src

    if reg_ok and reg_px is not None:
        return reg_px, "protective_registry"

    if reg_px and reg_px > 0 and not reg_ok:
        # Stale registry: try imply from stop, else keep ledger if any
        if stop_px and stop_px > 0:
            implied, src = _infer_entry_from_stop(float(stop_px), sl_pct=sl_pct)
            if implied and implied > 0:
                return implied, f"{src}_registry_inconsistent"
        if ledger_px and ledger_px > 0:
            return ledger_px, "ledger_last_buy_registry_inconsistent"

    if stop_px and stop_px > 0:
        return _infer_entry_from_stop(float(stop_px), sl_pct=sl_pct)

    if ledger_px and ledger_px > 0:
        return ledger_px, ledger_src
    if reg_px and reg_px > 0:
        return reg_px, "protective_registry_unchecked"
    return None, "none"


def build_ledger_row_from_fill(
    order: Dict[str, Any],
    exchange: Any,
    ledger: TradeLedger,
    *,
    backfill: bool = False,
) -> Optional[Dict[str, Any]]:
    if not _is_filled_stop_sell(order):
        return None
    oid = _order_id(order)
    if not oid:
        return None
    pair = order.get("product_id") or order.get("pair")
    if not pair:
        return None

    fill_px = float(order.get("average_filled_price") or 0)
    fill_sz = float(order.get("filled_size") or order.get("filled_value") or 0)
    if (fill_px <= 0 or fill_sz <= 0) and exchange and hasattr(exchange, "get_order_fill_details"):
        try:
            fd = exchange.get_order_fill_details(oid) or {}
            fill_px = float(fd.get("average_filled_price") or fill_px or 0)
            fill_sz = float(fd.get("filled_size") or fill_sz or 0)
        except Exception as exc:
            logger.debug("fill details failed %s: %s", oid, exc)

    if fill_px <= 0 or fill_sz <= 0:
        logger.warning("[FILL-RECON] skip %s %s: missing fill px/sz", pair, oid)
        return None

    ts = _parse_ts(order)
    stop_px = extract_stop_price_from_order(order)
    entry_px, entry_source = resolve_sl_fill_entry(
        pair=str(pair),
        fill_ts=ts,
        fill_px=fill_px,
        ledger=ledger,
        sl_order_id=str(oid),
        stop_px=float(stop_px) if stop_px else None,
    )

    pnl = 0.0
    pnl_pct = 0.0
    if entry_px and entry_px > 0:
        pnl = (fill_px - entry_px) * fill_sz
        pnl_pct = (fill_px - entry_px) / entry_px

    row = {
        "timestamp": ts,
        "pair": pair,
        "side": "SELL",
        "qty": fill_sz,
        "entry_price": entry_px,
        "exit_price": fill_px,
        "pnl": round(pnl, 6),
        "pnl_pct": round(pnl_pct, 6),
        "order_id": oid,
        "reason": "stop_loss_exchange",
        "exit_reason": "stop_loss_exchange",
        "signal_source": "coinbase_fill_reconcile",
        "mode": "live",
        "fill_verified": True,
        "entry_source": entry_source,
        "backfilled": backfill,
        "exchange_status": order.get("status"),
        "order_type": order.get("order_type"),
        "order_data_source": order.get("order_data_source"),
        "coinbase_trading_bot": is_coinbase_trading_bot_order(order),
    }
    fees = order.get("total_fees")
    if fees is not None:
        try:
            row["fees"] = float(fees)
        except (TypeError, ValueError):
            pass
    return row


def build_ledger_row_from_market_sell(
    order: Dict[str, Any],
    exchange: Any,
    ledger: TradeLedger,
    *,
    backfill: bool = False,
) -> Optional[Dict[str, Any]]:
    """FILLED MARKET (or non-stop) SELL from Trading Bot proxy."""
    if not is_coinbase_trading_bot_order(order):
        return None
    if _is_filled_stop_sell(order):
        return None
    side = str(order.get("side", "")).upper()
    if side != "SELL":
        return None
    oid = _order_id(order)
    pair = order.get("product_id") or order.get("pair")
    if not oid or not pair:
        return None

    fill_px = float(order.get("average_filled_price") or 0)
    fill_sz = float(order.get("filled_size") or 0)
    if (fill_px <= 0 or fill_sz <= 0) and exchange and hasattr(exchange, "get_order_fill_details"):
        try:
            fd = exchange.get_order_fill_details(oid) or {}
            fill_px = float(fd.get("average_filled_price") or fill_px or 0)
            fill_sz = float(fd.get("filled_size") or fill_sz or 0)
        except Exception as exc:
            logger.debug("market sell fill details failed %s: %s", oid, exc)
    if fill_px <= 0 or fill_sz <= 0:
        return None

    ts = _parse_ts(order)
    entry_px, entry_source = _entry_from_ledger_buys(ledger, pair, ts)
    pnl = 0.0
    pnl_pct = 0.0
    if entry_px and entry_px > 0:
        pnl = (fill_px - entry_px) * fill_sz
        pnl_pct = (fill_px - entry_px) / entry_px

    row = {
        "timestamp": ts,
        "pair": pair,
        "side": "SELL",
        "qty": fill_sz,
        "entry_price": entry_px,
        "exit_price": fill_px,
        "pnl": round(pnl, 6),
        "pnl_pct": round(pnl_pct, 6),
        "order_id": oid,
        "reason": (
            "preserve_disarm"
            if str(pair).upper().startswith("PAXG")
            else "rotation_exchange"
        ),
        "exit_reason": (
            "preserve_disarm"
            if str(pair).upper().startswith("PAXG")
            else "rotation_exchange"
        ),
        "signal_source": "coinbase_fill_reconcile",
        "mode": "live",
        "fill_verified": True,
        "entry_source": entry_source,
        "backfilled": backfill,
        "exchange_status": order.get("status"),
        "order_type": order.get("order_type"),
        "order_data_source": order.get("order_data_source"),
        "coinbase_trading_bot": True,
        "sleeve": "preserve" if str(pair).upper().startswith("PAXG") else "trade",
    }
    fees = order.get("total_fees")
    if fees is not None:
        try:
            row["fees"] = float(fees)
        except (TypeError, ValueError):
            pass
    return row


def build_ledger_row_from_market_buy(
    order: Dict[str, Any],
    exchange: Any,
    *,
    backfill: bool = False,
) -> Optional[Dict[str, Any]]:
    if not is_coinbase_trading_bot_order(order):
        return None
    if str(order.get("side", "")).upper() != "BUY":
        return None
    ot = str(order.get("order_type") or "").upper()
    if ot and ot != "MARKET":
        return None
    oid = _order_id(order)
    pair = order.get("product_id") or order.get("pair")
    if not oid or not pair:
        return None
    fill_px = float(order.get("average_filled_price") or 0)
    fill_sz = float(order.get("filled_size") or 0)
    if (fill_px <= 0 or fill_sz <= 0) and exchange and hasattr(exchange, "get_order_fill_details"):
        try:
            fd = exchange.get_order_fill_details(oid) or {}
            fill_px = float(fd.get("average_filled_price") or fill_px or 0)
            fill_sz = float(fd.get("filled_size") or fill_sz or 0)
        except Exception:
            pass
    if fill_px <= 0 or fill_sz <= 0:
        return None
    return {
        "timestamp": _parse_ts(order),
        "pair": pair,
        "side": "BUY",
        "qty": fill_sz,
        "entry_price": fill_px,
        "exit_price": None,
        "pnl": 0.0,
        "pnl_pct": 0.0,
        "order_id": oid,
        # PAXG is the Preserve ballast asset — never a basket rebalance buy
        "reason": (
            "preserve_arm" if str(pair).upper().startswith("PAXG") else "rebalance_buy"
        ),
        "signal_source": "coinbase_fill_reconcile",
        "mode": "live",
        "fill_verified": True,
        "backfilled": backfill,
        "exchange_status": order.get("status"),
        "order_type": order.get("order_type"),
        "order_data_source": order.get("order_data_source"),
        "coinbase_trading_bot": True,
        "sleeve": "preserve" if str(pair).upper().startswith("PAXG") else "trade",
    }


def _ingest_row(
    ledger: TradeLedger,
    exchange: Any,
    order: Dict[str, Any],
    row: Dict[str, Any],
    known: Set[str],
    added: List[str],
    *,
    dry_run: bool,
) -> None:
    oid = str(row.get("order_id") or "")
    if not oid or oid in known:
        return
    _append_raw_fill(
        {
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "order": order,
            "ledger_row": row,
        }
    )
    if not dry_run:
        ledger.log_trade(row, exchange=exchange)
        if row.get("reason") == "stop_loss_exchange":
            mark_sl_filled(oid)
            try:
                from phase6.core.sl_dust_sweep import sweep_residual_after_stop

                sweep_residual_after_stop(
                    exchange,
                    str(row.get("pair") or ""),
                    filled_qty=float(row.get("qty") or 0.0),
                    parent_sl_order_id=str(oid),
                    dry_run=False,
                )
            except Exception as dust_exc:
                logger.warning(
                    "[FILL-RECON] dust sweep after SL failed %s: %s",
                    row.get("pair"),
                    dust_exc,
                )
        # Shadow partial-redeploy would-fire (rotation + stop reasons); never orders
        if str(row.get("side") or "").upper() == "SELL":
            try:
                from phase6.core.liquidation_redeploy_shadow import (
                    record_from_ledger_sell_row,
                )

                record_from_ledger_sell_row(row, source="fill_recon")
            except Exception as shadow_exc:
                logger.debug("[LIQ-REDEPLOY-SHADOW] fill hook skipped: %s", shadow_exc)
        try:
            from phase6.core.trading_log_store import append_verified_fill
            from phase6.core.param_audit import resolve_account_id_from_exchange

            acct = resolve_account_id_from_exchange(exchange)
            append_verified_fill(row, account_id=acct)
        except Exception as exc:
            logger.debug("verified fill store append skipped: %s", exc)
    known.add(oid)
    added.append(oid)
    logger.info(
        "[FILL-RECON] %s %s %s qty=%s px=%s reason=%s",
        row.get("pair"),
        row.get("side"),
        oid[:8],
        row.get("qty"),
        row.get("exit_price") or row.get("entry_price"),
        row.get("reason"),
    )


def reconcile_all_filled_sells(
    exchange: Any,
    *,
    backfill_days: Optional[int] = None,
    dry_run: bool = False,
    include_non_stop: bool = False,
) -> Dict[str, Any]:
    """Ingest Trading Bot FILLED SELLs (stops + optional market rotations)."""
    if not include_non_stop:
        return reconcile_filled_stops(exchange, backfill_days=backfill_days, dry_run=dry_run)

    ledger = TradeLedger()
    known = _load_ledger_order_ids(ledger)
    start_date: Optional[str] = None
    if backfill_days:
        start = datetime.now(timezone.utc) - timedelta(days=backfill_days)
        start_date = start.strftime("%Y-%m-%dT%H:%M:%SZ")

    if not hasattr(exchange, "list_filled_orders"):
        return {"ok": False, "error": "exchange missing list_filled_orders"}

    orders = exchange.list_filled_orders(side="SELL", start_date=start_date)
    orders = [o for o in orders if is_coinbase_trading_bot_order(o)]

    added: List[str] = []
    skipped = 0
    stop_n = 0
    market_n = 0
    for order in orders:
        oid = _order_id(order)
        if not oid or str(oid) in known:
            skipped += 1
            continue
        if _is_filled_stop_sell(order):
            row = build_ledger_row_from_fill(
                order, exchange, ledger, backfill=bool(backfill_days)
            )
            stop_n += 1
        else:
            row = build_ledger_row_from_market_sell(
                order, exchange, ledger, backfill=bool(backfill_days)
            )
            if row:
                market_n += 1
        if not row:
            skipped += 1
            continue
        _ingest_row(ledger, exchange, order, row, known, added, dry_run=dry_run)

    cursor = {
        "last_run": datetime.now(timezone.utc).isoformat(),
        "mode": "all_sells",
        "filled_sell_scanned": len(orders),
        "added_order_ids": added,
        "start_date": start_date,
    }
    if not dry_run:
        _save_cursor(cursor)

    return {
        "ok": True,
        "scanned_filled_sells": len(orders),
        "stop_candidates": stop_n,
        "market_candidates": market_n,
        "added": len(added),
        "skipped": skipped,
        "order_ids": added,
        "dry_run": dry_run,
    }


def reconcile_missing_filled_buys(
    exchange: Any,
    *,
    backfill_days: Optional[int] = 120,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Append exchange-verified FILLED BUYs whose order_id is not yet in JSONL."""
    ledger = TradeLedger()
    known = _load_ledger_order_ids(ledger)
    start_date: Optional[str] = None
    if backfill_days:
        start = datetime.now(timezone.utc) - timedelta(days=backfill_days)
        start_date = start.strftime("%Y-%m-%dT%H:%M:%SZ")

    orders = exchange.list_filled_orders(side="BUY", start_date=start_date)
    orders = [o for o in orders if is_coinbase_trading_bot_order(o)]
    added: List[str] = []
    skipped = 0
    for order in orders:
        oid = _order_id(order)
        if not oid or str(oid) in known:
            skipped += 1
            continue
        row = build_ledger_row_from_market_buy(order, exchange, backfill=bool(backfill_days))
        if not row:
            skipped += 1
            continue
        _ingest_row(ledger, exchange, order, row, known, added, dry_run=dry_run)

    return {
        "ok": True,
        "scanned_filled_buys": len(orders),
        "added": len(added),
        "skipped": skipped,
        "order_ids": added,
        "dry_run": dry_run,
    }


def reconcile_trading_bot_ledger(
    exchange: Any,
    *,
    backfill_days: Optional[int] = 120,
    dry_run: bool = False,
    include_buys: bool = True,
    include_all_sells: bool = True,
) -> Dict[str, Any]:
    """Full Coinbase Trading Bot parity: verified buys + stop/market sells."""
    out: Dict[str, Any] = {"ok": True, "dry_run": dry_run}
    if include_all_sells:
        out["sells"] = reconcile_all_filled_sells(
            exchange,
            backfill_days=backfill_days,
            dry_run=dry_run,
            include_non_stop=True,
        )
    else:
        out["sells"] = reconcile_filled_stops(
            exchange, backfill_days=backfill_days, dry_run=dry_run
        )
    if include_buys:
        out["buys"] = reconcile_missing_filled_buys(
            exchange, backfill_days=backfill_days, dry_run=dry_run
        )
    return out


def reconcile_filled_stops(
    exchange: Any,
    *,
    backfill_days: Optional[int] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Pull FILLED SELL orders from Coinbase, append stop exits to phase6_trades.jsonl.
    """
    ledger = TradeLedger()
    known = _load_ledger_order_ids(ledger)
    start_date: Optional[str] = None
    if backfill_days is not None and backfill_days > 0:
        start = datetime.now(timezone.utc) - timedelta(days=backfill_days)
        start_date = start.strftime("%Y-%m-%dT%H:%M:%SZ")

    if not hasattr(exchange, "list_filled_orders"):
        return {"ok": False, "error": "exchange missing list_filled_orders"}

    orders = exchange.list_filled_orders(side="SELL", start_date=start_date)
    orders = [o for o in orders if is_coinbase_trading_bot_order(o)]
    stop_orders = [o for o in orders if _is_filled_stop_sell(o)]

    added: List[str] = []
    skipped = 0
    dust_sweeps: List[Dict[str, Any]] = []
    for order in stop_orders:
        oid = _order_id(order)
        if not oid or str(oid) in known:
            skipped += 1
            continue
        row = build_ledger_row_from_fill(
            order, exchange, ledger, backfill=bool(backfill_days)
        )
        if not row:
            skipped += 1
            continue
        _append_raw_fill({"ingested_at": datetime.now(timezone.utc).isoformat(), "order": order, "ledger_row": row})
        if not dry_run:
            ledger.log_trade(row, exchange=exchange)
            mark_sl_filled(oid)
            # 0.98 attach buffer leaves ~2% residual — sweep so SL exits clean the book
            try:
                from phase6.core.sl_dust_sweep import sweep_residual_after_stop

                sweep = sweep_residual_after_stop(
                    exchange,
                    str(row.get("pair") or ""),
                    filled_qty=float(row.get("qty") or 0.0),
                    parent_sl_order_id=str(oid),
                    dry_run=False,
                )
                dust_sweeps.append(sweep)
                if sweep.get("success") and not sweep.get("skipped"):
                    logger.info(
                        "[FILL-RECON] dust sweep after SL %s: qty=%s",
                        row.get("pair"),
                        sweep.get("filled_qty") or sweep.get("size"),
                    )
            except Exception as dust_exc:
                logger.warning(
                    "[FILL-RECON] dust sweep after SL failed %s: %s",
                    row.get("pair"),
                    dust_exc,
                )
            try:
                from phase6.core.liquidation_redeploy_shadow import (
                    record_from_ledger_sell_row,
                )

                record_from_ledger_sell_row(row, source="fill_recon_sl")
            except Exception as shadow_exc:
                logger.debug("[LIQ-REDEPLOY-SHADOW] sl fill hook skipped: %s", shadow_exc)
        known.add(str(oid))
        added.append(str(oid))
        logger.info(
            "[FILL-RECON] %s SELL %s qty=%s exit=%s pnl=%s entry_src=%s",
            row["pair"],
            oid,
            row["qty"],
            row["exit_price"],
            row["pnl"],
            row.get("entry_source"),
        )

    cursor = {
        "last_run": datetime.now(timezone.utc).isoformat(),
        "filled_sell_scanned": len(orders),
        "stop_filled_seen": len(stop_orders),
        "added_order_ids": added,
        "start_date": start_date,
    }
    if not dry_run:
        _save_cursor(cursor)

    return {
        "ok": True,
        "scanned_filled_sells": len(orders),
        "stop_filled": len(stop_orders),
        "added": len(added),
        "skipped": skipped,
        "order_ids": added,
        "dust_sweeps": dust_sweeps if not dry_run else [],
        "dry_run": dry_run,
    }


def reconcile_stored_exchange_fills_into_ledger(
    *,
    dry_run: bool = False,
    ledger: Optional[TradeLedger] = None,
) -> Dict[str, Any]:
    """
    No Coinbase API: append ledger rows for orders already captured in
    trades/phase6_exchange_fills.jsonl (keeps JSONL aligned with stored fills).
    """
    ledger = ledger or TradeLedger()
    known = _load_ledger_order_ids(ledger)
    if not RAW_FILLS_PATH.exists():
        return {"ok": True, "added": 0, "skipped": 0, "scanned": 0, "dry_run": dry_run}

    added: List[str] = []
    skipped = 0
    scanned = 0
    seen_orders: Set[str] = set()

    for line in RAW_FILLS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            blob = json.loads(line)
        except json.JSONDecodeError:
            continue
        scanned += 1
        prebuilt = blob.get("ledger_row") if isinstance(blob.get("ledger_row"), dict) else None
        order = blob.get("order") if isinstance(blob.get("order"), dict) else blob
        if not isinstance(order, dict):
            skipped += 1
            continue
        oid = str(_order_id(order) or (prebuilt or {}).get("order_id") or "")
        if not oid or oid in known or oid in seen_orders:
            skipped += 1
            continue
        seen_orders.add(oid)

        row = prebuilt
        if not row:
            if _is_filled_stop_sell(order):
                row = build_ledger_row_from_fill(order, None, ledger, backfill=True)
            elif str(order.get("side", "")).upper() == "SELL":
                row = build_ledger_row_from_market_sell(order, None, ledger, backfill=True)
            elif str(order.get("side", "")).upper() == "BUY":
                row = build_ledger_row_from_market_buy(order, None, backfill=True)
        if not row:
            skipped += 1
            continue
        if not dry_run:
            ledger.log_trade(row, exchange=None)
            try:
                from phase6.core.trading_log_store import append_verified_fill
                append_verified_fill(row, account_id=row.get("account_id"))
            except Exception:
                pass
        known.add(oid)
        added.append(oid)

    return {
        "ok": True,
        "scanned": scanned,
        "added": len(added),
        "skipped": skipped,
        "order_ids": added,
        "dry_run": dry_run,
    }