"""
Average-cost basis for open positions from TradeLedger (buy adds, sell reduces).

Coinbase portfolio PnL uses cost basis for *current* holdings; the old runner helper
summed every BUY in the window and ignored SELLs, which inflated entry (e.g. ETH -24% vs ~flat).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from phase6.core.paths import PROJECT_ROOT
from phase6.core.trade_ledger import TradeLedger

_PLACEHOLDER_ENTRY = 100.0
_QTY_MISMATCH_RATIO = 0.12
_DEFAULT_SL_PCT = 0.03
_EXCHANGE_FILLS_PATH = PROJECT_ROOT / "trades/phase6_exchange_fills.jsonl"
_VERIFIED_FILLS_GLOB = "data/state/trading_log/**/verified_fills_*.jsonl"


def _trade_qty(trade: Dict[str, Any]) -> float:
    for key in ("qty", "amount", "size", "base_size"):
        raw = trade.get(key)
        if raw is None:
            continue
        try:
            q = float(raw)
        except (TypeError, ValueError):
            continue
        if q > 0:
            return q
    return 0.0


def _trade_fill_price(trade: Dict[str, Any]) -> Optional[float]:
    side = str(trade.get("side") or "").upper()
    if side == "SELL":
        keys = ("exit_price", "average_filled_price", "fill_price", "price")
    else:
        keys = ("average_filled_price", "fill_price", "price", "entry_price")
    for key in keys:
        raw = trade.get(key)
        if raw is None:
            continue
        try:
            px = float(raw)
        except (TypeError, ValueError):
            continue
        if px <= 0:
            continue
        if key == "entry_price" and abs(px - _PLACEHOLDER_ENTRY) < 0.01:
            continue
        return px
    return None


def _fifo_layers_from_trades(
    ordered: List[Dict[str, Any]],
) -> Tuple[List[List[float]], Optional[float]]:
    """FIFO inventory layers [qty, unit_cost] after processing sells."""
    layers: List[List[float]] = []
    last_buy_price: Optional[float] = None
    for t in ordered:
        side = str(t.get("side") or "").upper()
        n = _trade_qty(t)
        if n <= 0:
            continue
        if side == "BUY":
            px = _trade_fill_price(t)
            if not px:
                continue
            last_buy_price = px
            layers.append([n, px])
        elif side == "SELL":
            px = _trade_fill_price(t)
            if not px:
                continue
            rem = n
            while rem > 1e-12 and layers:
                take = min(rem, layers[0][0])
                layers[0][0] -= take
                rem -= take
                if layers[0][0] < 1e-12:
                    layers.pop(0)
    return layers, last_buy_price


def average_cost_from_trades(
    trades: List[Dict[str, Any]],
    *,
    expected_qty: Optional[float] = None,
) -> Tuple[Optional[float], str]:
    """
    Average cost for open inventory: FIFO walk, then LIFO slice to exchange qty when ledger drifts.
    """
    ordered = sorted(trades, key=lambda t: str(t.get("timestamp") or ""))
    layers, last_buy_price = _fifo_layers_from_trades(ordered)
    ledger_qty = sum(q for q, _ in layers)

    if ledger_qty > 1e-12:
        if expected_qty and expected_qty > 0:
            drift = abs(ledger_qty - expected_qty) / expected_qty
            if drift > _QTY_MISMATCH_RATIO:
                cost = 0.0
                need = expected_qty
                for q, px in reversed(layers):
                    if need <= 1e-12:
                        break
                    take = min(need, q)
                    cost += take * px
                    need -= take
                if need / expected_qty < 0.02:
                    return cost / expected_qty, "ledger_lifo_exchange_qty"
                if last_buy_price:
                    return last_buy_price, "last_buy_ledger_drift"
        cost_total = sum(q * px for q, px in layers)
        return cost_total / ledger_qty, "ledger_avg_cost"

    if last_buy_price:
        return last_buy_price, "last_buy_flat"
    return None, "unknown"


def _dedupe_trades_by_order_id(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: Set[str] = set()
    out: List[Dict[str, Any]] = []
    for t in sorted(trades, key=lambda x: str(x.get("timestamp") or "")):
        oid = str(t.get("order_id") or "")
        key = oid if oid else f"{t.get('timestamp')}|{t.get('side')}|{t.get('qty')}"
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def _load_verified_fill_trades(pair: str) -> List[Dict[str, Any]]:
    trades: List[Dict[str, Any]] = []
    root = PROJECT_ROOT / "data/state/trading_log"
    if not root.exists():
        return trades
    for path in sorted(root.glob("**/verified_fills_*.jsonl")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(row.get("pair") or "") != pair:
                continue
            if not row.get("fill_verified") and not _trade_fill_price(row):
                continue
            trades.append(row)
    return trades


def _trade_from_exchange_fill_order(order: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    pair = order.get("product_id") or order.get("pair")
    side = str(order.get("side") or "").upper()
    if not pair or side not in ("BUY", "SELL"):
        return None
    status = str(order.get("status") or "").upper()
    if status and status not in ("FILLED", "FILLED_SETTLED", "DONE", "COMPLETED"):
        return None
    fill_px = float(order.get("average_filled_price") or 0)
    fill_sz = float(order.get("filled_size") or 0)
    if fill_px <= 0 or fill_sz <= 0:
        return None
    ts = order.get("completion_time") or order.get("created_time") or order.get("last_fill_time")
    return {
        "timestamp": str(ts or ""),
        "pair": pair,
        "side": side,
        "qty": fill_sz,
        "average_filled_price": fill_px,
        "order_id": order.get("order_id") or order.get("id"),
        "signal_source": "exchange_fills_jsonl",
        "fill_verified": True,
    }


def _load_exchange_jsonl_trades(pair: str) -> List[Dict[str, Any]]:
    if not _EXCHANGE_FILLS_PATH.exists():
        return []
    trades: List[Dict[str, Any]] = []
    try:
        lines = _EXCHANGE_FILLS_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return trades
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        order = row.get("order") if isinstance(row.get("order"), dict) else row
        if not isinstance(order, dict):
            continue
        if str(order.get("product_id") or order.get("pair") or "") != pair:
            continue
        t = _trade_from_exchange_fill_order(order)
        if t:
            trades.append(t)
    return trades


def gather_cost_basis_trades(
    ledger: TradeLedger,
    pair: str,
    *,
    limit: int = 5000,
) -> List[Dict[str, Any]]:
    """Merge ledger + verified fills + raw exchange fills for refresh-accurate avg cost."""
    merged: List[Dict[str, Any]] = []
    merged.extend(
        t for t in ledger.get_recent_trades(limit=limit) if str(t.get("pair") or "") == pair
    )
    merged.extend(_load_verified_fill_trades(pair))
    merged.extend(_load_exchange_jsonl_trades(pair))
    return _dedupe_trades_by_order_id(merged)


def average_cost_for_pair(
    ledger: TradeLedger,
    pair: str,
    *,
    expected_qty: Optional[float] = None,
    limit: int = 5000,
) -> Tuple[Optional[float], str]:
    trades = gather_cost_basis_trades(ledger, pair, limit=limit)
    return average_cost_from_trades(trades, expected_qty=expected_qty)


def enrich_position_unrealized(
    position: Dict[str, Any],
    ledger: TradeLedger,
) -> Dict[str, Any]:
    """Recompute entry_price, unrealized_pnl_pct, unrealized_pnl_usd on a position dict."""
    out = dict(position)
    pair = str(out.get("pair") or "")
    amount = float(out.get("amount") or 0)
    price = float(out.get("current_price") or 0)
    if not pair or amount <= 0 or price <= 0:
        return out

    entry, basis = average_cost_for_pair(ledger, pair, expected_qty=amount)
    if not entry or entry <= 0:
        entry = float(out.get("entry_price") or 0) or price
        basis = "state_fallback"

    pnl_usd = (price - entry) * amount
    pnl_pct = (price - entry) / entry if entry > 0 else 0.0
    sl_stop = entry * (1.0 - _DEFAULT_SL_PCT) if entry > 0 else None
    out["entry_price"] = round(entry, 6)
    out["entry_basis"] = basis
    out["unrealized_pnl_usd"] = round(pnl_usd, 4)
    out["unrealized_pnl_pct"] = round(pnl_pct, 4)
    out["sl_stop_price_est"] = round(sl_stop, 4) if sl_stop else None
    out["sl_pct_nominal"] = _DEFAULT_SL_PCT
    from phase6.core.price_freshness import apply_stale_price_pnl_guard

    return apply_stale_price_pnl_guard(out)


def recompute_trading_positions_pnl(
    positions: List[Dict[str, Any]],
    ledger: Optional[TradeLedger] = None,
) -> List[Dict[str, Any]]:
    lg = ledger or TradeLedger()
    return [enrich_position_unrealized(p, lg) for p in positions]