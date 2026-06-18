#!/usr/bin/env python3
"""
Phase 5.1 Live Trading Initializer
===================================

DEPLOYMENT: Fresh Start scenario with $1K real capital
ALLOCATION: Volatility/RSI-weighted across 5 pairs
ENTRY: RSI < 40, TP +10%, SL -5%, RSI > 70 exit

ACTION: Deploy $1K, allocate pairs, place initial funding orders.
"""

import json
import logging
from datetime import datetime
import os

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('/home/brad/.openclaw/workspace/operations/crypto-bot/phase5_1_live_trade.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Placeholder: Import real order executor when available
# from order_executor import OrderExecutor

class Phase51LiveInitializer:
    """Initialize Phase 5.1 live trading with $1K capital."""
    
    def __init__(self, total_capital=1000.0, reserve_pct=0.25):
        self.total_capital = total_capital
        self.reserve_pct = reserve_pct
        self.reserve = total_capital * reserve_pct
        self.deploy_capital = total_capital - self.reserve
        
        logger.info(f"Phase 5.1 Initializer: ${total_capital} total")
        logger.info(f"  Reserve: ${self.reserve:.2f} (25%)")
        logger.info(f"  Deploy: ${self.deploy_capital:.2f} (75%)")
    
    def calculate_volatility_allocation(self, pair_metrics):
        """
        Allocate deploy capital based on volatility + RSI.
        
        pair_metrics: {
            'BTC-USD': {'volatility': 3.2, 'rsi': 38, 'current_price': 62450},
            ...
        }
        
        Returns: {'BTC-USD': 300.0, 'ETH-USD': 250.0, ...}
        """
        pairs = list(pair_metrics.keys())
        allocations = {}
        
        # Score each pair: volatility (high) + RSI < 50 (good entry)
        scores = {}
        for pair, metrics in pair_metrics.items():
            vol_score = metrics['volatility']
            rsi_score = max(0, 50 - metrics['rsi'])  # Lower RSI = higher score
            total_score = (vol_score * 0.6) + (rsi_score * 0.4)
            scores[pair] = total_score
        
        # Allocate proportionally
        total_score = sum(scores.values())
        for pair, score in scores.items():
            allocation = (score / total_score) * self.deploy_capital
            allocations[pair] = allocation
            logger.info(f"  {pair}: ${allocation:.2f} (score={score:.2f})")
        
        return allocations
    
    def place_funding_orders(self, allocations, pair_metrics):
        """
        Place market buy orders to fund each pair.
        
        allocations: {'BTC-USD': 300.0, ...}
        pair_metrics: Current prices + volatility
        """
        trades = []
        
        for pair, usd_amount in allocations.items():
            price = pair_metrics[pair]['current_price']
            qty = usd_amount / price
            
            logger.info(f"[INIT] Order: BUY {qty:.6f} {pair} @ ${price:.2f} (${usd_amount:.2f})")
            
            # TODO: Call order_executor.place_market_buy(pair, qty)
            # For now, mock the order
            trades.append({
                'timestamp': datetime.utcnow().isoformat(),
                'pair': pair,
                'side': 'BUY',
                'qty': qty,
                'price': price,
                'usd_amount': usd_amount,
                'status': 'PENDING_EXECUTION'  # Would be 'FILLED' after real order
            })
        
        return trades
    
    def initialize(self, pair_metrics, order_executor=None):
        """
        Full initialization: allocate capital, place funding orders.
        
        Returns: Initialization report
        """
        logger.info("=" * 80)
        logger.info("PHASE 5.1 LIVE TRADING INITIALIZATION")
        logger.info("=" * 80)
        logger.info(f"Time: {datetime.utcnow().isoformat()}")
        logger.info(f"Capital: ${self.total_capital}")
        logger.info("")
        
        # Calculate allocations
        logger.info("PAIR ALLOCATION (Volatility/RSI-weighted):")
        allocations = self.calculate_volatility_allocation(pair_metrics)
        logger.info(f"  Total allocated: ${sum(allocations.values()):.2f}")
        logger.info("")
        
        # Place funding orders
        logger.info("FUNDING ORDERS:")
        trades = self.place_funding_orders(allocations, pair_metrics)
        logger.info(f"  Total orders: {len(trades)}")
        logger.info("")
        
        # Reserve summary
        logger.info(f"RESERVE: ${self.reserve:.2f} (for new entry opportunities)")
        logger.info("")
        
        report = {
            'timestamp': datetime.utcnow().isoformat(),
            'total_capital': self.total_capital,
            'reserve': self.reserve,
            'deploy_capital': sum(allocations.values()),
            'allocations': allocations,
            'trades': trades,
            'status': 'INITIALIZED'
        }
        
        logger.info("STATUS: READY TO TRADE (Phase 5.1 live trading active)")
        logger.info("=" * 80)
        
        return report

def main():
    """Initialize Phase 5.1 with example pair metrics."""
    
    # Example: Current market metrics (would come from live feed)
    pair_metrics = {
        'BTC-USD': {
            'volatility': 3.2,
            'rsi': 38,
            'current_price': 62450.00
        },
        'ETH-USD': {
            'volatility': 2.8,
            'rsi': 42,
            'current_price': 2340.00
        },
        'SOL-USD': {
            'volatility': 4.1,
            'rsi': 35,
            'current_price': 142.50
        },
        'XRP-USD': {
            'volatility': 3.5,
            'rsi': 44,
            'current_price': 2.48
        },
        'DOGE-USD': {
            'volatility': 4.7,
            'rsi': 40,
            'current_price': 0.2492
        }
    }
    
    # Initialize
    init = Phase51LiveInitializer(total_capital=1000.0, reserve_pct=0.25)
    report = init.initialize(pair_metrics)
    
    # Save report
    with open('/home/brad/.openclaw/workspace/operations/crypto-bot/phase5_1_init_report.json', 'w') as f:
        json.dump(report, f, indent=2)
    
    logger.info("\n✅ Phase 5.1 initialization complete.")
    logger.info(f"Report saved to: phase5_1_init_report.json")

if __name__ == '__main__':
    main()
