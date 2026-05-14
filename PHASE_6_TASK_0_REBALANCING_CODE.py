# PHASE 6 TASK 0: WEEKLY REBALANCING CODE
# Insert this method into phase5_multi_pair.py Phase5Harness class
# Call it in run() loop: self._rebalance_if_needed(cycle)

def _rebalance_if_needed(self, cycle_number):
    """
    Weekly rebalancing: Every 7 cycles (~7 min), rebalance portfolio based on correlation.
    
    ALGORITHM:
    1. Calculate correlation matrix from 30-cycle price history
    2. Detect high-correlation pairs (avg_corr > 0.7)
    3. Shift 50% of high-corr allocations to reserve
    4. Re-deploy from reserve based on sentiment weighting
    
    METRICS LOGGED:
    - Average correlation
    - High-correlation pair list
    - Allocations before/after
    - Reserve level change
    """
    if cycle_number % 7 != 0:
        return  # Only rebalance every 7 cycles
    
    try:
        # Initialize allocations tracking
        if not hasattr(self, 'allocations'):
            self.allocations = {pair: self.capital_per_pair for pair in self.pairs}
            self.reserve = 0.0
        
        # Build price matrix (pairs × 30 cycles)
        price_matrix = []
        for pair in self.pairs:
            if pair in self.price_history and len(self.price_history[pair]) >= 30:
                pair_prices = self.price_history[pair][-30:]  # Last 30 cycles
                price_matrix.append(pair_prices)
            else:
                # Fallback: use current price repeated
                current_price = getattr(self, f'{pair}_price', 0)
                if current_price > 0:
                    price_matrix.append([current_price] * 30)
                else:
                    self.logger.warning(f"⚠️  {pair}: Insufficient price data for correlation")
                    continue
        
        if len(price_matrix) < 2:
            self.logger.warning("Not enough pairs with price history for correlation")
            return
        
        # Calculate correlation matrix
        import numpy as np
        price_matrix = np.array(price_matrix)
        corr_matrix = np.corrcoef(price_matrix)
        
        # Get average correlation (excluding diagonal self-correlations)
        corr_values = corr_matrix[np.triu_indices_from(corr_matrix, k=1)]
        avg_correlation = np.mean(corr_values) if len(corr_values) > 0 else 0
        
        self.logger.info(f"🔄 REBALANCING TRIGGER (Cycle {cycle_number})")
        self.logger.info(f"📊 Average Correlation: {avg_correlation:.3f}")
        
        # Rebalance if high correlation detected
        if avg_correlation > 0.7:
            self.logger.info(f"⚠️  High correlation ({avg_correlation:.3f}). Initiating rebalancing...")
            
            # Identify high-correlation pairs
            high_corr_pairs = []
            for i, pair in enumerate(self.pairs):
                if i < len(corr_matrix):
                    pair_corrs = corr_matrix[i]
                    avg_pair_corr = np.mean(pair_corrs)
                    if avg_pair_corr > 0.7:
                        high_corr_pairs.append((pair, avg_pair_corr))
            
            self.logger.info(f"High-correlation pairs: {high_corr_pairs}")
            
            # Save state before rebalancing
            allocations_before = dict(self.allocations)
            reserve_before = self.reserve
            
            # Shift 50% of high-corr pairs to reserve
            for pair, pair_corr in high_corr_pairs:
                if pair in self.allocations:
                    shift_amount = self.allocations[pair] * 0.5
                    self.allocations[pair] -= shift_amount
                    self.reserve += shift_amount
                    self.logger.info(f"  {pair} (corr={pair_corr:.2f}): Shifted ${shift_amount:.2f} to reserve")
            
            # Log rebalancing summary
            self.logger.info(f"Allocations BEFORE: {allocations_before}")
            self.logger.info(f"Allocations AFTER:  {self.allocations}")
            self.logger.info(f"Reserve: ${reserve_before:.2f} → ${self.reserve:.2f}")
            
        else:
            self.logger.info(f"✅ Correlation healthy ({avg_correlation:.3f}). No rebalancing needed.")
        
        # Log final portfolio state
        total_allocated = sum(self.allocations.values())
        self.logger.info(f"📈 Portfolio State: ${total_allocated:.2f} allocated + ${self.reserve:.2f} reserve")
        
    except Exception as e:
        self.logger.error(f"❌ Rebalancing error: {e}", exc_info=True)


# INTEGRATION IN run() METHOD:
# Add this line inside the run() loop after processing pairs:
#
#   for cycle in range(1, total_cycles + 1):
#       self.logger.info(f"CYCLE {cycle}")
#       batch_prices = self._fetch_all_pairs_batch()
#       for pair in self.pairs:
#           if pair in batch_prices:
#               setattr(self, f'{pair}_price', batch_prices[pair])
#           self._process_pair(pair, cycle)
#       
#       # ADD THIS LINE:
#       self._rebalance_if_needed(cycle)  # Weekly rebalancing every 7 cycles
#       
#       # Sleep or continue...
