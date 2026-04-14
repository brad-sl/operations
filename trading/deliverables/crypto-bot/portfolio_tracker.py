"""
Portfolio Tracker — Module 7 of Crypto Bot Phase 2

Tracks portfolio state and calculates P&L based on executed orders from Module 6.

Features:
  - Receives order execution data from Module 6
  - Tracks portfolio holdings (BTC amount, USD cash balance)
  - Calculates P&L based on entry vs exit prices
  - Tracks order history + execution metadata
  - Writes checkpoints every N operations
  - At end: Sends readiness signal to Module 8 via context

Checkpointing:
  - Writes STATE.json + MANIFEST.json every N orders
  - Enables resumable execution after interruption
  - Full audit trail of all portfolio updates
"""

import sys
import os
import json
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

sys.path.insert(0, '/home/brad/.openclaw/workspace/operations/crypto-bot')

try:
    from checkpoint_manager import CheckpointManager
except ImportError:
    CheckpointManager = None


@dataclass
class PortfolioState:
    """Snapshot of portfolio state at a point in time."""
    timestamp: str
    btc_holdings: float
    cash_balance: float
    total_value_usd: float
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    num_orders_processed: int
    current_price_btc: float = 0.0


@dataclass
class Order:
    """Represents an executed order."""
    order_id: str
    timestamp: str
    side: str  # "BUY" or "SELL"
    product_id: str
    price: float
    size: float
    fee: float = 0.0
    status: str = "SUCCESS"


@dataclass
class Position:
    """Track an open position."""
    entry_price: float
    entry_quantity: float
    entry_time: str
    avg_cost: float = 0.0
    realized_pnl: float = 0.0
    partially_closed: float = 0.0


class PortfolioTracker:
    """Tracks portfolio state and calculates P&L based on executed orders."""

    def __init__(
        self,
        orders: List[Dict[str, Any]],
        initial_cash: float = 10000.0,
        initial_btc: float = 0.0,
    ):
        """Initialize portfolio tracker."""
        self.orders = orders
        self.cash_balance = initial_cash
        self.btc_holdings = initial_btc
        self.realized_pnl = 0.0
        self.unrealized_pnl = 0.0
        
        self.positions: List[Position] = []
        self.order_history: List[Order] = []
        self.current_price_btc = 0.0
        
        # Initialize checkpointer if available
        if CheckpointManager:
            session_id = os.getenv(
                "SESSION_ID",
                f"portfolio-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
            )
            
            output_dir = os.getenv(
                "CHECKPOINT_OUTPUT_DIR",
                f"/home/brad/.openclaw/workspace/projects/orchestrator/agents/{session_id}"
            )

            self.checkpointer = CheckpointManager(
                session_id=session_id,
                agent_name="portfolio_tracker",
                output_dir=output_dir,
                total_tasks=len(orders),
                checkpoint_interval=20
            )
        else:
            self.checkpointer = None

    def process_order(self, order: Dict[str, Any]) -> PortfolioState:
        """Process a single order and update portfolio state."""
        order_id = order.get("order_id", "unknown")
        side = order.get("side", "").upper()
        product_id = order.get("product_id", "BTC-USD")
        price = float(order.get("price", 0.0))
        size = float(order.get("size", 0.0))
        fee = float(order.get("fee", 0.0))
        status = order.get("status", "SUCCESS")
        timestamp = order.get("timestamp", datetime.utcnow().isoformat() + "Z")
        
        # Skip failed orders
        if status != "SUCCESS":
            return self._get_state()
        
        # Update current price
        self.current_price_btc = price
        
        # Process BUY orders
        if side == "BUY":
            self.cash_balance -= (price * size) + fee
            self.btc_holdings += size
            
            position = Position(
                entry_price=price,
                entry_quantity=size,
                entry_time=timestamp,
                avg_cost=price
            )
            self.positions.append(position)
        
        # Process SELL orders
        elif side == "SELL":
            self.cash_balance += (price * size) - fee
            self.btc_holdings -= size
            
            # FIFO position closing
            remaining_to_close = size
            while remaining_to_close > 0 and self.positions:
                position = self.positions[0]
                close_amount = min(remaining_to_close, 
                                  position.entry_quantity - position.partially_closed)
                
                close_cost = position.entry_price * close_amount
                close_proceeds = price * close_amount
                position_pnl = close_proceeds - close_cost - (fee * close_amount / size)
                
                self.realized_pnl += position_pnl
                position.partially_closed += close_amount
                remaining_to_close -= close_amount
                
                if position.partially_closed >= position.entry_quantity:
                    self.positions.pop(0)
        
        order_obj = Order(
            order_id=order_id,
            timestamp=timestamp,
            side=side,
            product_id=product_id,
            price=price,
            size=size,
            fee=fee,
            status=status
        )
        self.order_history.append(order_obj)
        
        # Calculate unrealized P&L
        self.unrealized_pnl = 0.0
        for position in self.positions:
            open_quantity = position.entry_quantity - position.partially_closed
            if open_quantity > 0:
                current_value = open_quantity * self.current_price_btc
                cost_basis = open_quantity * position.entry_price
                self.unrealized_pnl += current_value - cost_basis
        
        return self._get_state()

    def process_all_orders(self) -> List[PortfolioState]:
        """Process all orders with checkpointing support."""
        states: List[PortfolioState] = []

        try:
            for i, order in enumerate(self.orders):
                state = self.process_order(order)
                states.append(state)
                
                if self.checkpointer:
                    self.checkpointer.mark_complete(
                        task_index=i,
                        output=asdict(state),
                        cost=0.0,
                        metadata={
                            "btc_holdings": state.btc_holdings,
                            "cash_balance": state.cash_balance,
                            "total_pnl": state.total_pnl
                        }
                    )

            if self.checkpointer:
                self.checkpointer.finalize()
            
            return states

        except Exception as e:
            if self.checkpointer:
                recovery = self.checkpointer.get_recovery_point()
                print(f"Recovery point: {json.dumps(recovery, indent=2)}")
            raise

    def _get_state(self) -> PortfolioState:
        """Build current portfolio state snapshot."""
        total_value = self.cash_balance + (self.btc_holdings * self.current_price_btc)
        total_pnl = self.realized_pnl + self.unrealized_pnl
        
        return PortfolioState(
            timestamp=datetime.utcnow().isoformat() + "Z",
            btc_holdings=self.btc_holdings,
            cash_balance=self.cash_balance,
            total_value_usd=total_value,
            realized_pnl=self.realized_pnl,
            unrealized_pnl=self.unrealized_pnl,
            total_pnl=total_pnl,
            num_orders_processed=len(self.order_history),
            current_price_btc=self.current_price_btc
        )

    def get_portfolio_summary(self) -> Dict[str, Any]:
        """Get summary statistics of portfolio."""
        if not self.order_history:
            return {"total_orders": 0, "current_state": asdict(self._get_state())}
        
        buy_orders = [o for o in self.order_history if o.side == "BUY"]
        sell_orders = [o for o in self.order_history if o.side == "SELL"]
        
        avg_buy = sum(o.price for o in buy_orders) / len(buy_orders) if buy_orders else 0.0
        avg_sell = sum(o.price for o in sell_orders) / len(sell_orders) if sell_orders else 0.0
        total_fees = sum(o.fee for o in self.order_history)
        
        return {
            "total_orders": len(self.order_history),
            "buy_orders": len(buy_orders),
            "sell_orders": len(sell_orders),
            "avg_buy_price": avg_buy,
            "avg_sell_price": avg_sell,
            "total_fees": total_fees,
            "current_state": asdict(self._get_state())
        }


if __name__ == "__main__":
    # Example usage
    test_orders = [
        {"order_id": "1", "side": "BUY", "product_id": "BTC-USD", "price": 40000, "size": 0.1, "fee": 10},
        {"order_id": "2", "side": "BUY", "product_id": "BTC-USD", "price": 39500, "size": 0.1, "fee": 10},
        {"order_id": "3", "side": "SELL", "product_id": "BTC-USD", "price": 42000, "size": 0.05, "fee": 10},
    ]
    
    tracker = PortfolioTracker(test_orders, initial_cash=10000.0)
    states = tracker.process_all_orders()
    summary = tracker.get_portfolio_summary()
    
    print("Portfolio Summary:")
    print(json.dumps(summary, indent=2, default=str))
