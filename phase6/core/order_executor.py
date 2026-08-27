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
        trade_ledger: Any = None,
    ):
        self.exchange = exchange
        self.stop_loss_manager = stop_loss_manager
        self.mode = mode.lower().strip()
        self.shadow_mode = self.mode == "shadow"
        self.logger = logger or logging.getLogger("phase6.executor")
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.trade_ledger = trade_ledger

    def _record_to_ledger(self, result: Dict[str, Any], signal_source: str = "order_executor") -> None:
        if not self.trade_ledger or not result.get("success"):
            return
        try:
            self.trade_ledger.log_execution_result(
                result,
                mode=self.mode,
                exchange=self.exchange,
                signal_source=signal_source,
                stop_loss_manager=self.stop_loss_manager,
            )
        except Exception as e:
            self.logger.warning(f"Ledger record failed: {e}")

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


    def execute_buy(self, pair: str, usd_amount: float, tp_pct: float = None, *, record_ledger: bool = True) -> Dict[str, Any]:
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
            # ENG-S3-01: shadow must not invoke live stop_loss_manager (no exchange/SL API).
            if self.stop_loss_manager:
                self.logger.debug(
                    "[SHADOW BUY] Skipping SL/TP attach (ENG-S3-01); simulated entry only"
                )
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
            # ENG-S3-02: no settlement/fill polling here — stop_loss_manager owns poll_for_settlement.
            from phase6.core.sl_preflight import fetch_verified_order_fill

            hint = (
                fetch_verified_order_fill(self.exchange, order_id)
                if order_id
                else {"average_filled_price": 0.0, "filled_size": 0.0, "fill_verified": False}
            )
            entry_price = float(hint.get("average_filled_price") or 0.0)
            size = float(hint.get("filled_size") or 0.0)
            if size > 0 and entry_price <= 0:
                entry_price = usd_amount / size
            elif size <= 0 and entry_price > 0:
                size = usd_amount / entry_price
            if entry_price <= 0 and size <= 0:
                self.logger.info(
                    f"[EXEC BUY] Fill not yet visible for {pair} (order_id={order_id}); "
                    f"delegating settlement wait to stop_loss_manager"
                )

            # P0-02.5: ensure quantization via exchange metadata for the resulting base size
            if size > 0 and hasattr(self.exchange, "quantize_size"):
                try:
                    size = float(self.exchange.quantize_size(pair, size))
                except Exception:
                    size = round(size, 8)

            sl_result = False
            tp_result = False
            if self.stop_loss_manager:
                sl_result = self.stop_loss_manager.attach_stop_loss(
                    pair,
                    entry_price,
                    size,
                    anchor_entry=entry_price if entry_price > 0 else None,
                    order_id=order_id if order_id else None,
                    fresh_buy=True,
                )
                # EXIT-H2: exchange fixed TP only when exit_automation says
                # mode=live AND live_attach_on_buy (effective_tp_pct_for_buy).
                effective_tp = tp_pct
                if effective_tp is None:
                    try:
                        from phase6.core.shadow_tp import effective_tp_pct_for_buy

                        cfg = getattr(self.stop_loss_manager, "config", None) or {}
                        # Prefer exit_automation when trading_config has no take_profit block
                        if not isinstance(cfg, dict) or "take_profit" not in cfg:
                            cfg = None
                        effective_tp = effective_tp_pct_for_buy(cfg)
                    except Exception:
                        effective_tp = None
                if effective_tp is None:
                    # Do NOT fall back to default_tp_pct — that would attach
                    # exchange TP while software trail is the primary path.
                    effective_tp = None
                if effective_tp and effective_tp > 0:
                    tp_result = self.stop_loss_manager.attach_take_profit(
                        pair, entry_price, size, effective_tp
                    )
                self.logger.info(
                    f"[SL/TP] Post-buy for {pair}: entry=${entry_price:.4f} size={size:.8f} "
                    f"SL={sl_result} TP={tp_result} tp_pct={effective_tp}"
                )

            # ENG-S3-03: re-query fill after SL attach (settlement poll completed inside attach)
            verified = fetch_verified_order_fill(self.exchange, order_id) if order_id else hint
            if verified.get("fill_verified"):
                entry_price = float(verified["average_filled_price"])
                size = float(verified["filled_size"])
                if size > 0 and hasattr(self.exchange, "quantize_size"):
                    try:
                        size = float(self.exchange.quantize_size(pair, size))
                    except Exception:
                        size = round(size, 8)
            elif sl_result and order_id:
                self.logger.warning(
                    f"[EXEC BUY] SL attached for {pair} but fill still unverified (order_id={order_id})"
                )

            result["entry_price"] = round(entry_price, 4) if entry_price > 0 else 0.0
            result["size"] = size
            result["qty"] = size
            result["sl_attached"] = sl_result
            result["tp_attached"] = tp_result
            result["actual_fill_used"] = bool(verified.get("fill_verified"))
            result["fill_verified"] = bool(verified.get("fill_verified"))
        else:
            result["sl_attached"] = False
            result["tp_attached"] = False

        result["pair"] = pair
        result["action"] = "BUY"
        result["side"] = "BUY"
        if record_ledger:
            from phase6.core.ledger_sl_truth import enrich_buy_sl_truth

            enrich_buy_sl_truth(result, self.stop_loss_manager)
            self._record_to_ledger(result, signal_source="order_executor_buy")
        return result

    def execute_sell(self, pair: str, usd_amount: float) -> Dict[str, Any]:
        """Execute a market sell. Accepts usd_amount (like execute_buy) and computes crypto size internally.
        P0-02.6: Critical sell path audit/fix.
        - size = usd_amount / price (full get_price prec)
        - ALWAYS quantize with base_increment (via exchange.quantize_size)
        - For LIVE (P6-PE-CALLER-OE-SELL): delegates to protected_market_exit which unlocks
          any stop-held base before rebalance sells (cancel+resolve+reattach). Quantize+return shape preserved.
        - Shadow unchanged.
        - No more direct place_market_sell in this path.
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
            # P6-PE-CALLER-OE-SELL-20260826 + P0-02.6: route live sells (rebalance etc) via protected to unlock
            # stop-held base. Compute/quantize logic above is preserved exactly.
            try:
                from phase6.core.protected_market_exit import protected_market_exit
                pe = protected_market_exit(
                    self.exchange,
                    pair,
                    qty=size,
                    qty_full_hint=size,
                    mark_price=price,
                    reason="order_executor_sell",
                    signal_source="order_executor_sell",
                    ledger=True,
                    reattach_sl=True,
                )
                if not pe.get("success", False):
                    err = pe.get("error") or pe.get("cancel_error") or "protected_market_exit failed"
                    return {"success": False, "error": str(err)[:200]}
                filled = float(pe.get("filled_qty") or pe.get("qty") or size or 0)
                exit_px = float(pe.get("exit_price") or 0.0)
                out = {
                    "success": True,
                    "order_id": pe.get("order_id"),
                    "size": round(filled, 8),
                    "qty": round(filled, 8),
                    "exit_price": round(exit_px, 4) if exit_px > 0 else None,
                    "actual_fill_used": bool(exit_px > 0),
                    "pair": pair,
                    "action": "SELL",
                    "side": "SELL",
                }
                # protected did the ledger + unlock + reattach; skip _record to avoid dup
                return out
            except Exception as pe_exc:
                self.logger.error(f"[OE-SELL] protected exit exception for {pair}: {pe_exc}")
                return {"success": False, "error": f"protected: {str(pe_exc)[:120]}"}
        
        # Shadow mode
        out = {
            "success": True,
            "order_id": f"shadow_sell-{__import__('secrets').token_hex(4)}",
            "size": round(size, 8),
            "qty": round(size, 8),
            "exit_price": price,
            "pair": pair,
            "action": "SELL",
            "side": "SELL",
        }
        self._record_to_ledger(out, signal_source="order_executor_sell")
        return out

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
                # Defer ledger until after attach_stop_loss inside execute_buy, then
                # finalize with exchange protective-order truth (P6-OPS #14).
                result = self.execute_buy(pair, usd_amount, record_ledger=False)
                if result.get("success"):
                    from phase6.core.ledger_sl_truth import enrich_buy_sl_truth

                    enrich_buy_sl_truth(result, self.stop_loss_manager)
                    self._record_to_ledger(result, signal_source="order_executor_rebalance")
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
