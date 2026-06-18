#!/usr/bin/env python3
"""
Phase 5 OrderExecutor Wrapper - Sandbox Integration Module

Provides clean integration between Phase 5 trading logic and direct Coinbase API.
Handles trade logging, error recovery, and audit trail management.

WORKAROUND: Bypass OrderExecutor class (which expects CoinbaseWrapper) and call
Coinbase Advanced Trade API directly for sandbox execution.

Usage:
    from phase5_order_executor_wrapper import OrderExecutorWrapper
    
    wrapper = OrderExecutorWrapper(
        cb_client=coinbase_client,
        sandbox_mode=True,
        order_size_usd=25.0,
        logger=logger
    )
    
    results = wrapper.execute_signal(pair, signal, price, rsi, sentiment, cycle)
"""

import os
import csv
import logging
from datetime import datetime
from pathlib import Path


class OrderExecutorWrapper:
    """Direct Coinbase trade execution for Phase 5"""
    
    def __init__(self, cb_client, sandbox_mode=True, order_size_usd=25.0, logger=None):
        """
        Initialize wrapper.
        
        Args:
            cb_client: Coinbase Advanced Trade client (RESTClient)
            sandbox_mode: Whether to use sandbox/paper trading
            order_size_usd: Order size in USD per trade
            logger: Logger instance
        """
        self.cb_client = cb_client
        self.sandbox_mode = sandbox_mode
        self.order_size_usd = order_size_usd
        self.logger = logger or logging.getLogger(__name__)
        
        # Trade audit log
        self.trades_csv = Path(os.path.dirname(__file__)) / 'trades_sandbox.csv'
        self.trades_executed = []
        
        self.logger.info(
            f"OrderExecutorWrapper initialized: sandbox={sandbox_mode}, "
            f"order_size=${order_size_usd:.2f}"
        )
    
    def execute_signal(self, pair, signal, price, rsi, sentiment, cycle):
        """
        Execute trading signal directly via Coinbase Advanced Trade API.
        
        Args:
            pair: Trading pair (e.g., "BTC-USD")
            signal: Trade signal ("BUY", "SELL", or "HOLD")
            price: Current price
            rsi: RSI value for logging
            sentiment: Sentiment score for logging
            cycle: Trading cycle number
        
        Returns:
            List of trade result dicts
        """
        if signal == "HOLD":
            self.logger.debug(f"{pair}: Signal={signal}, skipping execution")
            return []
        
        try:
            self.logger.info(
                f"Executing {signal} for {pair} @ ${price:.2f} "
                f"(RSI={rsi:.0f}, Sentiment={sentiment:.2f}, Cycle={cycle})"
            )
            
            if not self.cb_client:
                raise ValueError("Coinbase client not available")
            
            # Calculate order size
            quantity = self.order_size_usd / price if price > 0 else 0
            if quantity <= 0:
                raise ValueError(f"Invalid quantity: {quantity}")
            
            # Execute trade
            order_id = None
            status = "PENDING"
            price_executed = price
            transaction_cost = quantity * price
            error = None
            
            try:
                if self.sandbox_mode:
                    # Sandbox: just log the intent
                    self.logger.info(
                        f"📝 [SANDBOX] Would place {signal} order: {quantity:.8f} {pair} @ ${price:.2f}"
                    )
                    order_id = f"sandbox-{cycle}-{pair}"
                    status = "SIMULATED"
                    transaction_cost = self.order_size_usd
                else:
                    # Live: actually execute
                    self.logger.warning(
                        f"🔥 LIVE TRADE: {signal} {quantity:.8f} {pair} @ ${price:.2f}"
                    )
                    order = self.cb_client.create_market_order(
                        client_order_id=f"phase5-{cycle}-{pair}",
                        product_id=pair,
                        side="BUY" if signal == "BUY" else "SELL",
                        quote_size=self.order_size_usd  # Use quote_size for USD amount
                    )
                    order_id = order.order_id if hasattr(order, 'order_id') else str(order)
                    status = "SUBMITTED"
                    transaction_cost = self.order_size_usd
                
                result = {
                    'timestamp': datetime.now().isoformat(),
                    'cycle': cycle,
                    'pair': pair,
                    'signal': signal,
                    'order_id': order_id,
                    'status': status,
                    'quantity': quantity,
                    'price_executed': price_executed,
                    'transaction_cost': transaction_cost,
                    'error': None
                }
                
                self.logger.info(
                    f"✅ {pair} {signal}: Order={order_id}, Status={status}, "
                    f"Qty={quantity:.8f}, Cost=${transaction_cost:.2f}"
                )
                
                results = [result]
                
            except Exception as order_error:
                self.logger.error(f"Order execution error: {order_error}", exc_info=True)
                result = {
                    'timestamp': datetime.now().isoformat(),
                    'cycle': cycle,
                    'pair': pair,
                    'signal': signal,
                    'order_id': None,
                    'status': 'FAILED',
                    'quantity': quantity,
                    'price_executed': None,
                    'transaction_cost': 0.0,
                    'error': str(order_error)
                }
                results = [result]
            
            # Log to CSV
            self._log_trades_to_csv(results)
            
            return results
            
        except Exception as e:
            self.logger.error(f"Wrapper error for {pair} {signal}: {e}", exc_info=True)
            result = {
                'timestamp': datetime.now().isoformat(),
                'cycle': cycle,
                'pair': pair,
                'signal': signal,
                'order_id': None,
                'status': 'FAILED',
                'quantity': 0.0,
                'price_executed': None,
                'transaction_cost': 0.0,
                'error': str(e)
            }
            self._log_trades_to_csv([result])
            return [result]
    
    def _log_trades_to_csv(self, results):
        """Log trade results to CSV audit trail"""
        try:
            file_exists = self.trades_csv.exists()
            
            with open(self.trades_csv, 'a', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'timestamp', 'cycle', 'pair', 'signal', 'order_id', 'status',
                    'quantity', 'price_executed', 'transaction_cost', 'error'
                ])
                
                if not file_exists:
                    writer.writeheader()
                
                for result in results:
                    writer.writerow({
                        'timestamp': result.get('timestamp', ''),
                        'cycle': result.get('cycle', ''),
                        'pair': result.get('pair', ''),
                        'signal': result.get('signal', ''),
                        'order_id': result.get('order_id', 'N/A'),
                        'status': result.get('status', ''),
                        'quantity': result.get('quantity', 0.0),
                        'price_executed': result.get('price_executed', 'N/A'),
                        'transaction_cost': result.get('transaction_cost', 0.0),
                        'error': result.get('error', '')
                    })
                    
                    self.trades_executed.append({
                        'order_id': result.get('order_id'),
                        'status': result.get('status'),
                        'cost': result.get('transaction_cost', 0.0)
                    })
            
            self.logger.debug(f"Logged {len(results)} trades to {self.trades_csv}")
        
        except Exception as e:
            self.logger.error(f"CSV logging error: {e}")
    
    def get_trade_summary(self):
        """Get summary of trades executed in this session"""
        total_trades = len(self.trades_executed)
        successful = sum(
            1 for t in self.trades_executed 
            if t['status'] in ['SIMULATED', 'SUBMITTED', 'FILLED']
        )
        total_cost = sum(t['cost'] for t in self.trades_executed)
        
        return {
            'total_trades': total_trades,
            'successful': successful,
            'failed': total_trades - successful,
            'total_cost': total_cost,
            'avg_cost': total_cost / total_trades if total_trades > 0 else 0
        }


if __name__ == '__main__':
    # Test wrapper initialization
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    print("✅ OrderExecutorWrapper module loaded successfully")
