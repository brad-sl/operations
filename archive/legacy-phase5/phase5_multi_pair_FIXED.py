#!/usr/bin/env python3
"""
REPLACEMENT _process_pair() METHOD

Replace lines 156-205 in phase5_multi_pair.py with this version.
This uses BATCH-FETCHED prices instead of re-fetching individually.
"""

def _process_pair(self, pair, cycle):
    """Process individual trading pair (uses batch-fetched price)"""
    try:
        # Use batch-fetched price (already cached on self by run())
        price = getattr(self, f'{pair}_price', None)
        
        # Fallback only if batch fetch failed completely
        if price is None or price <= 0:
            price = self.price_wrapper.get_price(pair)
        
        # Update Prometheus metrics (safe if metrics disabled)
        if self.pair_price_gauge:
            try:
                self.pair_price_gauge.labels(pair=pair).set(price)
            except Exception:
                pass
        if self.trading_capital_gauge:
            try:
                self.trading_capital_gauge.set(self.total_capital)
            except Exception:
                pass
        
        # Log price (from batch fetch)
        self.logger.info(f"CYCLE {cycle}: {pair} Price=${price:.4f}")
        
        # Real trading logic (NO mocks in live mode)
        rsi = self._calculate_rsi(pair)
        sentiment = self._get_sentiment(pair)
        
        # Trading decision logic
        signal = self._determine_trade_signal(pair, price, rsi, sentiment)
        
        return signal
    except Exception as e:
        self.logger.error(f"Error processing {pair}: {e}")
        return "HOLD"
