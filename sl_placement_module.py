#!/usr/bin/env python3
"""
Stop-Loss (SL) Placement Module for Coinbase Advanced Orders
Reusable for both automatic (during trades) and manual (utility script) SL management
"""

import logging
import secrets
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

class SLPlacement:
    """Handle stop-loss order placement via Coinbase Advanced Orders API"""
    
    def __init__(self, cb_client):
        """
        Args:
            cb_client: CoinbaseAdvancedClient or similar with _request method
        """
        self.cb_client = cb_client
    
    def place_stop_limit_sell(
        self,
        product_id: str,
        qty: float,
        stop_price: float,
        limit_price: Optional[float] = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Place a stop-limit SELL order (for stop-loss protection)
        
        Args:
            product_id: e.g., 'BTC-USD'
            qty: Quantity to sell (in base asset)
            stop_price: Trigger price (when market hits this, order activates)
            limit_price: Execution price (default: stop_price * 0.995 for safety margin)
        
        Returns:
            (success: bool, order_id: str or None, error: str or None)
        """
        if limit_price is None:
            limit_price = stop_price * 0.995  # Slightly below stop for buffer
        
        try:
            body = {
                'client_order_id': secrets.token_hex(16),
                'product_id': product_id,
                'side': 'SELL',
                'order_configuration': {
                    'stop_limit_stop_limit_gtc': {
                        'base_size': f"{qty:.8f}",
                        'stop_price': f"{stop_price:.2f}",
                        'limit_price': f"{limit_price:.2f}"
                    }
                }
            }
            
            logger.info(f"Placing SL order: {product_id} {qty:.8f}@ ${stop_price:.2f} (limit ${limit_price:.2f})")
            
            response = self.cb_client._request('POST', '/api/v3/brokerage/orders', body)
            
            if response.get('success'):
                success_response = response.get('success_response', {})
                order_id = success_response.get('order_id')
                logger.info(f"✅ SL order placed: {order_id}")
                return (True, order_id, None)
            else:
                error = response.get('error_response', {}).get('error', 'Unknown error')
                logger.error(f"❌ SL placement failed: {error}")
                return (False, None, error)
        
        except Exception as e:
            logger.error(f"❌ SL placement exception: {e}")
            return (False, None, str(e))
    
    def get_sl_price(self, entry_price: float, sl_pct: float) -> float:
        """Calculate SL price from entry price and percentage"""
        return entry_price * (1 - sl_pct)
    
    def check_sl_order_status(self, order_id: str) -> Dict[str, Any]:
        """
        Check if SL order has filled or been triggered
        
        Args:
            order_id: Coinbase order ID
        
        Returns:
            {'status': 'OPEN|FILLED|PENDING_TRIGGER|etc', 'filled_qty': float, ...}
        """
        try:
            response = self.cb_client._request('GET', f'/api/v3/brokerage/orders/{order_id}')
            if response.get('success'):
                order_data = response.get('order', {})
                return {
                    'status': order_data.get('status', 'UNKNOWN'),
                    'filled_qty': float(order_data.get('filled_size', 0)),
                    'order_id': order_id,
                    'raw': order_data
                }
            else:
                return {'status': 'ERROR', 'error': response.get('error_response')}
        except Exception as e:
            logger.error(f"Failed to check SL status: {e}")
            return {'status': 'ERROR', 'error': str(e)}
