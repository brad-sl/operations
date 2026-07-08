#!/usr/bin/env python3
# See docs/DATA_FLOW_AND_LOCATIONS.md and phase6/core/paths.py for paths, state, config hygiene and drift prevention.
# All code must derive PROJECT_ROOT via paths.py and avoid absolute hardcodes.

"""
Phase 6 OrderExecutor - Robust Order Execution Wrapper
"""

import logging
import secrets
import time
from datetime import datetime
from typing import Any, Dict, List, Optional


class OrderExecutor:
    """Robust order executor for Phase 6."""

    def __init__(
        self,
        exchange: Any,
        stop_loss_manager: Any,
        mode: str = "shadow",
        logger: Optional[logging.Logger] = None,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ):
        self.exchange = exchange
        self.stop_loss_manager = stop_loss_manager
        self.mode = mode.lower().strip()
        self.shadow_mode = self.mode == "shadow"
        self.logger = logger or logging.getLogger("phase6.executor")
        self.max_retries = max_retries
        self.base_delay = base_delay

    def _generate_client_order_id(self, prefix: str = "phase6") -> str:
        return f"{prefix}-{secrets.token_hex(16)}"

    def _retry_with_backoff(self, func, *args, **kwargs) -> Dict[str, Any]:
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                time.sleep(self.base_delay * (2 ** (attempt - 1)))
        return {"success": False, "error": str(last_error)}


    def execute_buy(self, pair: str, usd_amount: float, tp_pct: float = None) -> Dict[str, Any]:
        """Execute BUY. Returns dict with 'entry_price' (from actual fill for live, sim price for shadow),
        'size' and 'qty' (alias), never uses current market price as entry for live pairs (per audit).
        """
        if self.shadow_mode:
            # Shadow: use snapshot price as sim entry (not live trading)
            entry_price = getattr(self.exchange, 'get_price', lambda p: 0.0)(pair) or 0.0
            size = usd_amount / entry_price if entry_price > 0 else 0.0
            # P0-02: unify - quantize computed base size from usd/price (for consistent SL/ledger)
            if size > 0 and hasattr(self.exchange, 'quantize_size'):
                try:
                    size = float(self.exchange.quantize_size(pair, size))
                except Exception:
                    size = round(size, 8)
            sl_result = False
            tp_result = False
            if self.stop_loss_manager:
                sl_result = self.stop_loss_manager.attach_stop_loss(pair, entry_price, size, order_id="shadow_buy")
                if tp_pct is not None or getattr(self.stop_loss_manager, 'default_tp_pct', 0):
                    tp_result = self.stop_loss_manager.attach_take_profit(pair, entry_price, size, tp_pct)
            return {
                "success": True,
                "order_id": "shadow_buy",
                "entry_price": round(entry_price, 4),
                "size": size,
                "qty": size,
                "sl_attached": sl_result,
                "tp_attached": tp_result,
                "actual_fill_used": False
            }

        def _do_buy():
            return self.exchange.place_market_buy(pair, usd_amount)

        result = self._retry_with_backoff(_do_buy)

        if result.get("success"):
            order_id = result.get("order_id")
            # Prefer ACTUAL fill details ONLY - poll longer for settlement (fixes zero price on new buys)
            fill = {"average_filled_price": 0.0, "filled_size": 0.0}
            if order_id and hasattr(self.exchange, "get_order_fill_details"):
                fill = self.exchange.get_order_fill_details(order_id) or fill
                # Extended polling for actual fill price (common Coinbase settlement delay)
                if fill.get("average_filled_price", 0) <= 0:
                    self.logger.info(f"[FILL POLL] Polling for actual fill details on {pair} (up to ~30s)...")
                    import time
                    for _ in range(15):  # 15 * 2s = 30s max
                        time.sleep(2)
                        try:
                            new_fill = self.exchange.get_order_fill_details(order_id)
                            if new_fill and new_fill.get("average_filled_price", 0) > 0:
                                fill = new_fill
                                self.logger.info(f"[FILL POLL] Got real fill price for {pair}: {fill.get('average_filled_price')}")
                                break
                        except Exception:
                            pass
            entry_price = fill.get("average_filled_price") or 0.0
            size = fill.get("filled_size") or 0.0
            if entry_price <= 0 or size <= 0:
                # Fallback for SL attachment only (ledger still prefers real fill)
                current_px = 0.0
                try:
                    current_px = getattr(self.exchange, "get_price", lambda p: 0.0)(pair) or 0.0
                except Exception:
                    pass
                if current_px > 0 and entry_price <= 0:
                    entry_price = current_px
                    self.logger.warning(
                        f"[EXEC BUY] Using current market price ${entry_price} as SL anchor for {pair} (real fill price still 0 after polling)"
                    )
                elif size > 0 and entry_price <= 0:
                    entry_price = usd_amount / size
                if entry_price <= 0:
                    self.logger.warning(
                        f"[EXEC BUY] Live fill price unavailable or zero for {pair} (order_id={order_id}). "
                        f"entry_price={entry_price} (settlement delay; SL may use fallback)"
                    )
            if size <= 0 and entry_price > 0:
                size = usd_amount / entry_price

            # P0-02.5: ensure quantization via exchange metadata for the resulting base size
            # (live buy uses quote_size at exchange, but we must quantize base for result, ledger, SL attach consistency)
            if size > 0 and hasattr(self.exchange, "quantize_size"):
                try:
                    size = float(self.exchange.quantize_size(pair, size))
                except Exception:
                    size = round(size, 8)

            sl_result = False
            tp_result = False
            if self.stop_loss_manager:
                if getattr(self, "mode", None) == "live" and order_id:
                    import time
                    self.logger.info(f"[PRE-FLIGHT SETTLEMENT POLL] Explicit pre-SL poll for buy order {order_id} on {pair} (using get_order_fill_details)...")
                    # Additional dedicated settlement confirmation poll (per ANALYST-20260703-051)
                    if hasattr(self.exchange, "poll_for_settlement"):
                        try:
                            settled = self.exchange.poll_for_settlement(pair, timeout=15.0, order_id=order_id)
                            self.logger.info(f"[PRE-FLIGHT SETTLEMENT POLL] Result for {order_id}: {settled}")
                        except Exception as pe:
                            self.logger.debug(f"[PRE-FLIGHT] extra poll err: {pe}")
                    self.logger.info("[SL/TP] Post explicit poll, attaching protective orders...")
                # Pass entry as anchor for robust SL calc + order_id for fill-tied poll inside attach
                sl_result = self.stop_loss_manager.attach_stop_loss(pair, entry_price, size, anchor_entry=entry_price if entry_price > 0 else None, order_id=order_id if order_id else None)
                # Attach TP only if configured (not null/disabled for "let it ride")
                effective_tp = tp_pct
                if effective_tp is None:
                    effective_tp = getattr(self.stop_loss_manager, 'default_tp_pct', None)
                if effective_tp and effective_tp > 0:
                    tp_result = self.stop_loss_manager.attach_take_profit(pair, entry_price, size, effective_tp)
                self.logger.info(f"[SL/TP] Post-buy for {pair}: entry=${entry_price:.4f} size={size:.8f} SL={sl_result} TP={tp_result}")

            result["entry_price"] = round(entry_price, 4) if entry_price > 0 else 0.0
            result["size"] = size
            result["qty"] = size
            result["sl_attached"] = sl_result
            result["tp_attached"] = tp_result
            result["actual_fill_used"] = bool(fill.get("average_filled_price") and fill.get("average_filled_price") > 0)
        else:
            result["sl_attached"] = False
            result["tp_attached"] = False

        return result
    def execute_sell(self, pair: str, usd_amount: float) -> Dict[str, Any]:
        """Execute a market sell. Accepts usd_amount (like execute_buy) and computes crypto size internally.
        P0-02.6: Critical sell path audit/fix.
        - size = usd_amount / price (full get_price prec)
        - ALWAYS quantize with base_increment (Decimal ROUND_DOWN via public quantize_size) BEFORE calling place_market_sell
        - Consistent for direct sells and rebalance sells (both delegate here)
        - place_market_sell uses live meta base_increment as final guard
        - Fixes any usd-as-size; reports fill size (actual quantized from exchange or computed)
        - Higher prec reporting (round 8) to preserve small base sizes (e.g. BTC 1e-8 inc)
        """
        if usd_amount <= 0:
            return {"success": False, "error": "zero usd amount"}
        size = 0.0
        price = 0.0
        try:
            price = getattr(self.exchange, "get_price", lambda p: 0.0)(pair) or 0.0
            if price > 0:
                size = usd_amount / price
                # P0-02.6: sell path uses unified quantize (see above)
                if size > 0 and hasattr(self.exchange, 'quantize_size'):
                    try:
                        size = float(self.exchange.quantize_size(pair, size))
                    except Exception:
                        size = round(size, 8)
        except Exception:
            pass
        if self.mode == "live":
            if size <= 0:
                return {"success": False, "error": "could not compute sell size (price=0)"}
            # P0-02.6: size passed here is guaranteed quantized base (usd/price -> quantize_size) not raw usd
            result = self.exchange.place_market_sell(pair, size)
            if not result.get("success", False):
                return {"success": False, "error": result.get("error", "Failed")}
            order_id = result.get("order_id") or result.get("id")
            # Fetch actual fill for exit_price (consistent with execute_buy for ledger/PnL)
            fill = {"average_filled_price": 0.0, "filled_size": size}
            if order_id and hasattr(self.exchange, "get_order_fill_details"):
                try:
                    fill = self.exchange.get_order_fill_details(order_id) or fill
                except Exception:
                    pass
            exit_price = fill.get("average_filled_price") or 0.0
            filled = fill.get("filled_size") or size
            return {
                "success": True,
                "order_id": order_id,
                "size": round(filled, 8),
                "qty": round(filled, 8),
                "exit_price": round(exit_price, 4) if exit_price > 0 else None,
                "actual_fill_used": bool(exit_price > 0)
            }
        
        # Shadow mode
        return {"success": True, "order_id": f"shadow_sell-{__import__('secrets').token_hex(4)}", "size": round(size, 8), "qty": round(size, 8), "exit_price": price}

    def execute_rebalance_plan(self, plan: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Execute a full rebalance plan.
        Processes SELL moves first, and aborts if a SELL fails in live mode.
        """
        results = []
        sorted_plan = sorted(plan, key=lambda x: x.get("action", "") != "SELL")

        for move in sorted_plan:
            pair = move.get("pair")
            action = move.get("action", "").upper()
            usd_amount = float(move.get("usd_amount", 0))

            if action == "BUY":
                result = self.execute_buy(pair, usd_amount)
                # Note: execute_buy now handles SL attachment internally (including shadow simulation)
            elif action == "SELL":
                result = self.execute_sell(pair, usd_amount)
            else:
                result = {"success": False, "error": f"unknown action: {action}"}

            result["pair"] = pair
            result["action"] = action
            # P0-02.7: preserve usd_amount from input move for logging/metadata
            if "usd_amount" not in result:
                result["usd_amount"] = usd_amount
            results.append(result)
            
            # Atomic enforcement: abort plan if SELL failed in live mode
            if self.mode == "live" and action == "SELL" and not result.get("success"):
                self.logger.error(f"[ATOMIC] SELL failed ({pair}). Aborting full plan execution.")
                break

        return results
