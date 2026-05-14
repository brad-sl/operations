# Bootstrap loader method - Add to Phase5Harness class
# Call from __init__ after: self.sentiment_weight = ...

def _load_bootstrap_rsi_history(self):
    """Load pre-seeded RSI history from bootstrap file (warm-start)."""
    bootstrap_file = os.path.join(os.path.dirname(__file__), 'price_history_bootstrap.json')
    
    if not os.path.exists(bootstrap_file):
        self.logger.info("ℹ️  No bootstrap file found. RSI will warm up over 15 cycles.")
        return
    
    try:
        with open(bootstrap_file, 'r') as f:
            bootstrap_data = json.load(f)
        
        loaded_count = 0
        for pair in self.pairs:
            if pair in bootstrap_data:
                prices = bootstrap_data[pair].get('prices', [])
                if prices and len(prices) >= 14:
                    self.price_history[pair] = prices
                    loaded_count += 1
                    self.logger.info(f"✅ Loaded bootstrap RSI history for {pair} ({len(prices)} prices)")
        
        if loaded_count > 0:
            self.logger.info(f"🚀 Warm-started {loaded_count}/{len(self.pairs)} pairs. RSI signals ready on cycle 1.")
        else:
            self.logger.warning("Bootstrap file found but no data for configured pairs.")
    
    except Exception as e:
        self.logger.warning(f"Failed to load bootstrap: {e}. Proceeding with cold start.")


# In __init__, after line "self.sentiment_weight = self.config.get(...)", add:
# self.price_history = {}
# self._load_bootstrap_rsi_history()
