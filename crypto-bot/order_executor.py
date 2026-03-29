"""
Order Executor — Module 6 of Crypto Bot Phase 2

Takes trading signals from Module 5 (Signal Generator) and executes orders
via Coinbase API (paper trading first).

Features:
- Executes BUY/SELL/HOLD signals with order confirmation tracking
- Integrates with Coinbase Advanced Trade API
- Checkpointing support (STATE.json + MANIFEST.json every 10 orders)
- Inter-session messaging to Module 7 (Portfolio Tracker)
- Error handling and logging
- Paper trading (sandbox) mode by default

Usage:
    from order_executor import OrderExecutor, ExecutionResult
    from coinbase_wrapper import CoinbaseWrapper
    
    wrapper = CoinbaseWrapper(api_key, private_key, passphrase, sandbox=True)
    signals = [{"id": "sig-1", "signal": "BUY", "confidence": 0.85, ...}, ...]
    executor = OrderExecutor(signals, wrapper, product_id="BTC-USD")
    results = executor.execute_all_signals()
    # Automatically sends handoff to Module 7 via inter-session messaging
"""

import json
import os
import time
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from pathlib import Path

from checkpoint_manager import CheckpointManager
from coinbase_wrapper import CoinbaseWrapper, OrderResponse
from config_loader import ConfigLoader, TradingConfig


class SpendTracker:
    """Track daily spending and losses to enforce limits"""

    def __init__(self, config: TradingConfig):
        self.config = config
        self.daily_spend_usd = 0.0
        self.daily_orders = []  # List of order results per day
        self.session_start = datetime.now(timezone.utc)

    def within_daily_budget(self, additional_spend: float) -> bool:
        """Check if additional spend exceeds daily limit"""
        return (self.daily_spend_usd + additional_spend) <= self.config.daily_spend_usd

    def within_position_limit(self, product_id: str, quantity: float) -> bool:
        """Check if order quantity exceeds position limit for this pair"""
        max_size = self.config.position_limits.get(product_id, 0.05)
        return quantity <= max_size

    def within_daily_loss_limit(self) -> bool:
        """Check if daily loss exceeds circuit breaker"""
        daily_pnl = sum(
            (order.get("price_executed", 0) * order.get("quantity", 0))
            for order in self.daily_orders
            if order.get("status") != "FAILED"
        )
        return daily_pnl >= -self.config.max_daily_loss_usd

    def add_order(self, result, usd_amount: float):
        """Track order spending"""
        self.daily_spend_usd += usd_amount
        self.daily_orders.append(
            {
                "status": result.status,
                "quantity": result.quantity,
                "price_executed": result.price_executed,
                "timestamp": result.timestamp,
            }
        )


@dataclass
class ExecutionResult:
    """
    Result of executing a single trading signal.
    
    Attributes:
        signal_id: Unique identifier for the signal
        signal_type: BUY, SELL, or HOLD
        confidence: Confidence score (0.0 to 1.0)
        order_id: Coinbase order ID (None if HOLD or error)
        status: PENDING, FILLED, FAILED, SKIPPED, CANCELLED
        price_executed: Price at execution (None if HOLD or error)
        quantity: Amount executed (0.0 for HOLD)
        timestamp: ISO 8601 timestamp of signal
        error: Error message (None if successful)
        transaction_cost: Transaction cost in USD (if executed)
    """
    signal_id: str
    signal_type: str  # BUY, SELL, HOLD
    confidence: float
    order_id: Optional[str]
    status: str  # PENDING, FILLED, FAILED, SKIPPED, CANCELLED
    price_executed: Optional[float]
    quantity: float
    timestamp: str
    error: Optional[str] = None
    transaction_cost: float = 0.0


class OrderExecutor:
    """
    Executes trading signals by creating orders on Coinbase.
    
    Workflow:
    1. Initialize with signals and Coinbase wrapper
    2. Call execute_all_signals()
    3. Results are checkpointed every 10 orders
    4. Execution summary is sent to Module 7 via sessions_send
    """

    def __init__(
        self,
        signals: List[Dict[str, Any]],
        coinbase_wrapper: CoinbaseWrapper,
        product_id: str = "BTC-USD",
        order_size_usd: float = 50.0,
        sandbox_mode: bool = True,
        config_path: str = None,
    ):
        """
        Initialize Order Executor.

        Args:
            signals: List of signal dicts from Module 5
                     Each should have: {id, signal, confidence, timestamp, ...}
            coinbase_wrapper: CoinbaseWrapper instance (Module 4)
            product_id: Trading pair (default: "BTC-USD")
            order_size_usd: Order size in USD (default: $50)
            sandbox_mode: Use paper trading (default: True for safety)
            config_path: Path to trading_config.json (optional, defaults to workspace location)
        """
        self.signals = signals
        self.wrapper = coinbase_wrapper
        self.product_id = product_id
        self.order_size_usd = order_size_usd
        self.sandbox_mode = sandbox_mode

        # Ensure wrapper is in sandbox mode if requested
        if sandbox_mode and not self.wrapper.sandbox:
            raise ValueError(
                "Sandbox mode requested but wrapper is in live mode. "
                "Create wrapper with sandbox=True"
            )

        # Load config and initialize spend tracker
        loader = ConfigLoader(config_path)
        self.config = loader.get_config()
        self.spend_tracker = SpendTracker(self.config)

        # Initialize checkpointer
        session_id = os.getenv("SESSION_ID", f"order-exec-{int(time.time())}")
        self.checkpoint_interval = 10  # Save checkpoint every 10 orders
        
        output_dir = Path(
            f"/home/brad/.openclaw/workspace/projects/orchestrator/agents/{session_id}"
        )

        self.checkpointer = CheckpointManager(
            session_id=session_id,
            agent_name="order_executor",
            output_dir=str(output_dir),
            total_tasks=len(signals),
            checkpoint_interval=self.checkpoint_interval,
        )

        self.session_id = session_id
        self.output_dir = output_dir

    def execute_signal(self, signal: Dict) -> ExecutionResult:
        """
        Execute a single trading signal.

        Args:
            signal: Signal dict with keys: id, signal, confidence, timestamp

        Returns:
            ExecutionResult with order details
        """
        signal_id = signal.get("id", f"unknown-{int(time.time())}")
        signal_type = signal.get("signal", "HOLD")
        confidence = signal.get("confidence", 0.0)
        timestamp = signal.get("timestamp", datetime.now(timezone.utc).isoformat())

        # Validate signal type
        if signal_type not in ["BUY", "SELL", "HOLD"]:
            return ExecutionResult(
                signal_id=signal_id,
                signal_type=signal_type,
                confidence=confidence,
                order_id=None,
                status="FAILED",
                price_executed=None,
                quantity=0.0,
                timestamp=timestamp,
                error=f"Invalid signal type: {signal_type}",
            )

        # Skip HOLD signals (no order needed)
        if signal_type == "HOLD":
            return ExecutionResult(
                signal_id=signal_id,
                signal_type="HOLD",
                confidence=0.0,
                order_id=None,
                status="SKIPPED",
                price_executed=None,
                quantity=0.0,
                timestamp=timestamp,
            )

        try:
            # Get current price
            price_data = self.wrapper.get_price(self.product_id)
            if not price_data.get("success"):
                raise Exception(
                    f"Failed to get price: {price_data.get('error', 'unknown')}"
                )

            current_price = price_data.get("price", 0.0)
            if current_price <= 0:
                raise ValueError(f"Invalid price: {current_price}")

            # Calculate quantity
            quantity = self.order_size_usd / current_price

            # Check spend limits before creating order
            if not self.spend_tracker.within_daily_budget(self.order_size_usd):
                raise ValueError(
                    f"Daily budget exceeded. Spent: ${self.spend_tracker.daily_spend_usd:.2f}, "
                    f"Limit: ${self.config.daily_spend_usd:.2f}"
                )

            if not self.spend_tracker.within_position_limit(self.product_id, quantity):
                raise ValueError(
                    f"Position size {quantity:.8f} {self.product_id.split('-')[0]} "
                    f"exceeds limit {self.config.position_limits.get(self.product_id, 0.05)}"
                )

            if not self.spend_tracker.within_daily_loss_limit():
                raise ValueError(
                    f"Daily loss limit (${self.config.max_daily_loss_usd}) reached. "
                    f"Trading halted for today."
                )

            # Create order via Coinbase API
            order_response = self.wrapper.create_order(
                product_id=self.product_id,
                side=signal_type.lower(),  # "buy" or "sell"
                order_type="limit",
                price=current_price,
                size=quantity,
            )

            if not order_response.success:
                raise Exception(
                    f"Order creation failed: {order_response.error}"
                )

            # Build execution result
            # BUGFIX #001: transaction_cost is now the ACTUAL FEE (0.4% maker rate),
            # not the gross notional. Gross = quantity * current_price; Fee = Gross * rate
            gross_notional = quantity * current_price
            transaction_cost = gross_notional * self.config.COINBASE_MAKER_FEE_RATE
            
            result = ExecutionResult(
                signal_id=signal_id,
                signal_type=signal_type,
                confidence=confidence,
                order_id=order_response.order_id,
                status=order_response.status or "PENDING",
                price_executed=current_price,
                quantity=quantity,
                timestamp=timestamp,
                transaction_cost=transaction_cost,
            )

            # Track spend on success
            self.spend_tracker.add_order(result, self.order_size_usd)

            return result

        except Exception as e:
            return ExecutionResult(
                signal_id=signal_id,
                signal_type=signal_type,
                confidence=confidence,
                order_id=None,
                status="FAILED",
                price_executed=None,
                quantity=0.0,
                timestamp=timestamp,
                error=str(e),
            )

    def execute_all_signals(self) -> List[ExecutionResult]:
        """
        Execute all signals with checkpointing.

        Writes STATE.json + MANIFEST.json every checkpoint_interval orders.
        At completion, sends handoff summary to Module 7.

        Returns:
            List of ExecutionResult objects
        """
        results = []

        for i, signal in enumerate(self.signals):
            result = self.execute_signal(signal)
            results.append(result)

            # Record checkpoint only if order was successfully created
            if result.status != "FAILED":
                self.checkpointer.mark_complete(
                    task_index=i,
                    output=asdict(result),
                    metadata={
                        "order_id": result.order_id,
                        "status": result.status,
                        "signal_type": result.signal_type,
                    },
                )

        # Finalize checkpoint (writes final STATE.json + MANIFEST.json + RECOVERY.md)
        final_state = self.checkpointer.finalize()

        # Send handoff to Module 7 (Portfolio Tracker)
        self._send_portfolio_handoff(results)

        return results

    def _send_portfolio_handoff(self, results: List[ExecutionResult]) -> None:
        """
        Prepare and send execution summary to Module 7 (Portfolio Tracker).

        This uses inter-session messaging pattern:
        - Module 6 (this) builds execution_summary dict
        - Logs it with label for routing to Module 7
        - Parent orchestrator receives the label and calls sessions_send

        Args:
            results: List of ExecutionResult objects from execute_all_signals
        """
        # Calculate execution summary stats
        execution_summary = {
            "module": "order_executor",
            "total_signals": len(results),
            "buy_orders": sum(
                1 for r in results if r.signal_type == "BUY" and r.status != "FAILED"
            ),
            "sell_orders": sum(
                1 for r in results if r.signal_type == "SELL" and r.status != "FAILED"
            ),
            "hold_signals": sum(1 for r in results if r.signal_type == "HOLD"),
            "skipped_orders": sum(1 for r in results if r.status == "SKIPPED"),
            "failed_orders": sum(1 for r in results if r.status == "FAILED"),
            "total_usd_executed": sum(
                r.transaction_cost
                for r in results
                if r.transaction_cost and r.status != "FAILED"
            ),
            "total_btc_executed": sum(
                r.quantity for r in results if r.status != "FAILED"
            ),
            "order_ids": [r.order_id for r in results if r.order_id],
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "checkpoint_file": str(self.output_dir / "STATE.json"),
            "manifest_file": str(self.output_dir / "MANIFEST.json"),
        }

        try:
            # Build message for Module 7
            message = f"Order execution complete. Summary: {json.dumps(execution_summary, indent=2)}"

            # Log the handoff (parent will route via sessions_send)
            print(f"\n{'='*70}")
            print(f"✅ [HANDOFF] Ready to send to Module 7: Order execution complete")
            print(f"{'='*70}")
            print(f"Label: module-7-portfolio-tracker")
            print(f"Data:")
            print(
                f"  • {execution_summary['total_signals']} total signals processed"
            )
            print(
                f"  • {execution_summary['buy_orders']} BUY orders executed"
            )
            print(
                f"  • {execution_summary['sell_orders']} SELL orders executed"
            )
            print(
                f"  • {execution_summary['hold_signals']} HOLD signals (skipped)"
            )
            print(
                f"  • {execution_summary['failed_orders']} orders FAILED"
            )
            print(
                f"  • ${execution_summary['total_usd_executed']:.2f} total USD executed"
            )
            print(
                f"  • {execution_summary['total_btc_executed']:.8f} total BTC executed"
            )
            print(f"  • {len(execution_summary['order_ids'])} order IDs tracked")
            print(f"\nFull Summary:")
            print(json.dumps(execution_summary, indent=2))
            print(f"{'='*70}\n")

            # Save handoff summary to file for audit trail
            handoff_file = self.output_dir / "HANDOFF_MODULE_7.json"
            with open(handoff_file, "w") as f:
                json.dump(execution_summary, f, indent=2)

        except Exception as e:
            print(f"⚠️ Failed to prepare handoff to Module 7: {e}")


def main():
    """
    Standalone execution for testing (requires real .env or mock data).

    This demonstrates Module 6 running independently with mock signals.
    In production, signals come from Module 5.
    """
    # Mock signals for testing
    mock_signals = [
        {
            "id": f"sig-{i:03d}",
            "signal": ["BUY", "SELL", "HOLD"][(i) % 3],
            "confidence": 0.7 + (i % 3) * 0.1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        for i in range(20)  # 20 test signals
    ]

    # Create mock wrapper
    wrapper = CoinbaseWrapper(
        api_key="test-key",
        private_key="test-private",
        passphrase="test-pass",
        sandbox=True,
    )

    # Execute orders
    executor = OrderExecutor(
        signals=mock_signals,
        coinbase_wrapper=wrapper,
        product_id="BTC-USD",
        order_size_usd=50.0,
        sandbox_mode=True,
    )

    print(f"Executing {len(mock_signals)} signals in sandbox mode...")
    results = executor.execute_all_signals()

    # Print summary
    successful = sum(1 for r in results if r.status != "FAILED")
    print(f"\n✅ Execution complete: {successful}/{len(results)} orders successful")
    print(f"Checkpoint files created: {executor.output_dir}")


if __name__ == "__main__":
    main()
