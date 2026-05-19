"""
Paper P&L helpers - add to Phase6TradingBot

Functions to:
- calculate_paper_portfolio_value
- persist_paper_portfolio_state
"""

from datetime import datetime
from pathlib import Path
from typing import Dict
import json

def calculate_paper_portfolio_value(self, current_prices: Dict[str, float]) -> Dict:
    """Calculate total portfolio value from cash + open positions (paper mode)"""
    cash = self.total_capital  # start with full capital
    positions_value = 0.0
    position_details = {}
    
    for pair, pos in self.position_manager.positions.items():
        price = current_prices.get(pair, pos['entry_price'])
        position_market_value = pos['qty'] * price
        positions_value += position_market_value
        pnl = (price - pos['entry_price']) * pos['qty'] if pos['signal'] == 'BUY' else (pos['entry_price'] - price) * pos['qty']
        position_details[pair] = {
            'qty': pos['qty'],
            'entry_price': pos['entry_price'],
            'current_price': price,
            'market_value': round(position_market_value, 2),
            'unrealized_pnl': round(pnl, 2)
        }
        # Subtract allocated capital (already 'spent' on positions)
        cash -= (pos['qty'] * pos['entry_price'])
    
    total_value = cash + positions_value
    
    return {
        'timestamp': datetime.utcnow().isoformat(),
        'total_value': round(total_value, 2),
        'cash': round(cash, 2),
        'positions_value': round(positions_value, 2),
        'positions': position_details,
        'cycle': self.cycle_count
    }

def persist_paper_portfolio_state(self, portfolio_value: Dict, prices: Dict[str, float]):
    """Write latest paper portfolio state to JSON"""
    try:
        state = {
            'last_updated': datetime.utcnow().isoformat(),
            'portfolio': portfolio_value,
            'current_prices': {k: round(v, 4) for k, v in prices.items()}
        }
        self.portfolio_state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.portfolio_state_path, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        self.logger.error(f"Failed to persist paper portfolio state: {e}")