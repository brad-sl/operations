"""
Phase 6 Liquidation Manager: Poor Performer Optimization
========================================================

STRATEGY & REASONING:
- Identifies underperforming positions automatically
- Liquidates based on PAIN_SCORE (composite metric)
- Frees capital for reinvestment in Fresh Start trading loop
- Continuously rebalances portfolio toward best performers

PAIN_SCORE FORMULA:
    PAIN_SCORE = (Negative_PnL_%) + (100 - RSI) + (Correlation_Redundancy)

Components:
1. Negative P&L: How underwater is the position?
   - 0 if profitable
   - Scaled to 0-100 if negative
   
2. RSI Momentum: Is the trend weak?
   - RSI < 40 = high pain (weak momentum)
   - RSI > 70 = low pain (strong momentum)
   - Scale: 100 - RSI
   
3. Correlation Redundancy: Does this overlap with other holdings?
   - High correlation to other assets = redundant exposure
   - Low correlation = unique diversification benefit
   - Scale: 0-50 based on average correlation

LIQUIDATION TRIGGERS:
- Automatic: PAIN_SCORE > 25 (daily check)
- Manual override: User can force liquidation anytime
- Protection: Never liquidate entire account (min holdings required)

CAPITAL FLOW:
1. Liquidate poor performer → USD reserve
2. Wait for Fresh Start signals (RSI < 40)
3. Deploy from USD to new trades
4. Profitable exits → back to USD
5. Repeat daily for continuous rebalancing

USE CASES:
- Takeover 1: Reduce underwater positions early
- Takeover 2: Self-fund by liquidating worst performers
- Fresh Start: Not needed (fresh capital only)
- Bank Your Wins: Continuously trim losers, bank profits
"""

import logging
from typing import Dict, List, Tuple, Optional
import numpy as np

logger = logging.getLogger(__name__)

class LiquidationManager:
    """Manage automated liquidation of poor-performing positions."""
    
    def __init__(self, cb_client, order_executor, min_position_usd: float = 50.0):
        """
        Args:
            cb_client: Coinbase API client
            order_executor: Order execution interface
            min_position_usd: Minimum position size to keep (prevent micro positions)
        """
        self.cb_client = cb_client
        self.order_exec = order_executor
        self.min_position_usd = min_position_usd
        self.entry_prices = {}  # Track entry price per pair
        self.historical_prices = {}  # Store price history for correlation
    
    def update_entry_price(self, pair: str, price: float):
        """Track entry price when position is opened."""
        self.entry_prices[pair] = price
        logger.info(f"Entry price tracked: {pair} @ ${price}")
    
    def add_price_history(self, pair: str, price: float):
        """Add price to rolling history for correlation calculation."""
        if pair not in self.historical_prices:
            self.historical_prices[pair] = []
        self.historical_prices[pair].append(price)
        # Keep only 30 days
        if len(self.historical_prices[pair]) > 30:
            self.historical_prices[pair].pop(0)
    
    def calculate_rsi(self, pair: str, period: int = 14) -> float:
        """Calculate RSI for a pair from price history."""
        if pair not in self.historical_prices or len(self.historical_prices[pair]) < period:
            return 50.0  # Neutral RSI if insufficient data
        
        prices = self.historical_prices[pair][-period:]
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        
        gains = [d for d in deltas if d > 0]
        losses = [abs(d) for d in deltas if d < 0]
        
        avg_gain = sum(gains) / period if gains else 0
        avg_loss = sum(losses) / period if losses else 0
        
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def calculate_correlation(self, pair1: str, pair2: str, window: int = 30) -> float:
        """Calculate Pearson correlation between two price series."""
        if pair1 not in self.historical_prices or pair2 not in self.historical_prices:
            return 0.0
        
        h1 = self.historical_prices[pair1]
        h2 = self.historical_prices[pair2]
        
        # Use common window
        min_len = min(len(h1), len(h2), window)
        if min_len < 2:
            return 0.0
        
        p1 = np.array(h1[-min_len:])
        p2 = np.array(h2[-min_len:])
        
        if np.std(p1) == 0 or np.std(p2) == 0:
            return 0.0
        
        corr = np.corrcoef(p1, p2)[0, 1]
        return float(corr) if not np.isnan(corr) else 0.0
    
    def calculate_pain_score(self, 
                            pair: str,
                            current_price: float,
                            holdings: Dict[str, float]) -> float:
        """
        Calculate PAIN_SCORE for a position.
        
        Higher score = worse performer = liquidate first
        
        Formula:
            PAIN_SCORE = pnl_pain + rsi_pain + correlation_pain
        """
        # Component 1: P&L Pain
        if pair not in self.entry_prices:
            pnl_pain = 0
        else:
            entry_price = self.entry_prices[pair]
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
            # Only count negative P&L as pain
            pnl_pain = max(0, -pnl_pct)  # 0 if profitable, -pnl_pct if negative
        
        # Component 2: RSI Momentum Pain
        rsi = self.calculate_rsi(pair)
        rsi_pain = 100 - rsi  # RSI 30 = pain 70, RSI 70 = pain 30
        
        # Component 3: Correlation Redundancy Pain
        held_pairs = [p for p in holdings if holdings[p] > 0 and p != pair]
        if held_pairs:
            correlations = [self.calculate_correlation(pair, p) for p in held_pairs]
            avg_correlation = np.mean(correlations) if correlations else 0.0
            correlation_pain = avg_correlation * 50  # Scale to 0-50
        else:
            correlation_pain = 0.0
        
        total_pain = pnl_pain + rsi_pain + correlation_pain
        
        return total_pain
    
    def identify_poor_performers(self,
                                 holdings: Dict[str, float],
                                 current_prices: Dict[str, float],
                                 pain_threshold: float = 25.0) -> List[Tuple[str, float]]:
        """
        Identify positions to liquidate.
        
        Returns:
            List of (pair, pain_score) tuples, sorted by pain (highest first)
        """
        pain_scores = {}
        
        for pair, qty in holdings.items():
            if qty <= 0 or pair not in current_prices:
                continue
            
            pain = self.calculate_pain_score(pair, current_prices[pair], holdings)
            pain_scores[pair] = pain
        
        # Filter by threshold and sort
        poor = [(p, s) for p, s in pain_scores.items() if s > pain_threshold]
        poor.sort(key=lambda x: x[1], reverse=True)
        
        logger.info(f"Pain scores: {pain_scores}")
        logger.info(f"Poor performers (>={pain_threshold}): {poor}")
        
        return poor
    
    def can_liquidate_safely(self, pair: str, qty: float, price: float) -> bool:
        """Check if liquidation is safe (min position, circuit breaker, etc)."""
        position_value = qty * price
        
        if position_value < self.min_position_usd:
            logger.warning(f"Position too small: {pair} ${position_value:.2f} < ${self.min_position_usd}")
            return False
        
        return True
    
    def liquidate_position(self, pair: str, qty: float, price: float) -> bool:
        """
        Execute liquidation of a position.
        
        Returns:
            True if successful, False otherwise
        """
        if not self.can_liquidate_safely(pair, qty, price):
            return False
        
        try:
            # Place market sell order
            order = self.order_exec.place_market_sell(pair, qty)
            usd_raised = qty * price
            
            logger.info(f"Liquidated {pair}: {qty} @ ${price} = ${usd_raised:.2f}")
            
            # Clean up tracking
            if pair in self.entry_prices:
                del self.entry_prices[pair]
            
            return True
        
        except Exception as e:
            logger.error(f"Liquidation failed for {pair}: {e}")
            return False
    
    def weekly_rebalance(self, holdings: Dict[str, float], 
                       current_prices: Dict[str, float]) -> Dict[str, float]:
        """
        Perform daily rebalancing by liquidating poor performers.
        
        Returns:
            Updated holdings dict after liquidations
        """
        updated_holdings = holdings.copy()
        
        # Identify and liquidate poor performers
        poor = self.identify_poor_performers(holdings, current_prices, pain_threshold=30.0)
        
        for pair, pain_score in poor:
            qty = holdings[pair]
            price = current_prices[pair]
            
            if self.liquidate_position(pair, qty, price):
                updated_holdings[pair] = 0.0
            else:
                logger.warning(f"Could not liquidate {pair}, keeping position")
        
        return updated_holdings
    
    def get_liquidation_report(self, holdings: Dict[str, float],
                              current_prices: Dict[str, float]) -> Dict:
        """Generate detailed report of liquidation analysis."""
        report = {
            'timestamp': str(np.datetime64('now')),
            'total_pain_scores': {},
            'poor_performers': [],
            'recommendation': 'HOLD'
        }
        
        pain_scores = {}
        for pair, qty in holdings.items():
            if qty > 0 and pair in current_prices:
                pain = self.calculate_pain_score(pair, current_prices[pair], holdings)
                pain_scores[pair] = pain
        
        report['total_pain_scores'] = pain_scores
        
        poor = [(p, pain_scores[p]) for p in pain_scores if pain_scores[p] > 25]
        poor.sort(key=lambda x: x[1], reverse=True)
        
        for pair, pain in poor:
            report['poor_performers'].append({
                'pair': pair,
                'pain_score': pain,
                'qty': holdings[pair],
                'current_price': current_prices[pair],
                'position_value': holdings[pair] * current_prices[pair]
            })
        
        if poor:
            report['recommendation'] = f"LIQUIDATE {poor[0][0]} (pain={poor[0][1]:.1f})"
        
        return report
