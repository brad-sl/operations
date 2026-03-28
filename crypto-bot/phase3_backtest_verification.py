#!/usr/bin/env python3
"""
Phase 3 Crypto Trading Backtest Verification
Tests signal generation, order execution, and P&L calculation
"""

import json
import math
import sys
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Any
from dataclasses import dataclass, asdict

# Add paths for imports
sys.path.insert(0, '/home/brad/.openclaw/workspace/operations/crypto-bot')
sys.path.insert(0, '/home/brad/.openclaw/workspace/operations/crypto-bot/src')

from indicators.rsi import calculate_rsi, calculate_stochastic_rsi

# Configuration from trading_config.json
CONFIG = {
    "xrp": {
        "stochastic_threshold_oversold": 35,
        "stochastic_threshold_overbought": 65,
        "rsi_threshold_oversold": 35,
        "rsi_threshold_overbought": 65,
    },
    "btc": {
        "rsi_threshold_oversold": 30,
        "rsi_threshold_overbought": 70,
    }
}

# Current market conditions (as of task creation)
MARKET_DATA = {
    "BTC-USD": {"current_price": 67500, "change_24h": -0.05},  # Down ~5%
    "XRP-USD": {"current_price": 0.58, "change_24h": -0.024}   # Down ~2.4%
}

# Backtest parameters
INITIAL_CAPITAL = 10000
FEE_PER_TRADE = 0.001  # 0.1% per trade
BACKTEST_CYCLES = 100

@dataclass
class Trade:
    cycle: int
    timestamp: str
    pair: str
    side: str  # buy or sell
    price: float
    size: float
    fee: float
    pnl: float  # realized P&L after trade
    signal: str  # BUY/SELL/HOLD
    rsi: float
    stoch_k: float
    stoch_d: float

class Phase3Backtest:
    def __init__(self, pair: str, config: Dict[str, Any]):
        self.pair = pair
        self.config = config
        self.capital = INITIAL_CAPITAL
        self.position = 0.0  # Position in base currency
        self.position_value = 0.0
        self.trades: List[Trade] = []
        self.equity_curve = [INITIAL_CAPITAL]
        
    def generate_synthetic_data(self, days: int = 60) -> List[Dict]:
        """Generate synthetic OHLCV data based on current market conditions"""
        data = []
        
        # Get current price and recent trend
        current_price = MARKET_DATA[self.pair]["current_price"]
        
        # Adjust starting price to create realistic price history
        # Simulate a downtrend (current market)
        if self.pair == "BTC-USD":
            start_price = current_price * 1.08  # Started ~8% higher
            volatility = 0.025
        else:  # XRP
            start_price = current_price * 1.05  # Started ~5% higher
            volatility = 0.035
        
        price = start_price
        start_date = datetime(2026, 1, 27)  # 60 days ago
        
        for day in range(days):
            for hour in range(24):
                # Hourly candles
                timestamp = start_date + timedelta(days=day, hours=hour)
                
                # Random walk with slight mean reversion
                hourly_return = (0.0001 + 
                                volatility * (2 * (hash((day, hour)) % 100) / 100 - 1) +
                                0.001 * math.sin(hour / 24 * 2 * math.pi))
                
                open_p = price
                change = open_p * hourly_return
                close_p = open_p + change
                high_p = max(open_p, close_p) * (1 + abs(hourly_return))
                low_p = min(open_p, close_p) * (1 - abs(hourly_return))
                
                data.append({
                    'timestamp': timestamp.isoformat(),
                    'open': open_p,
                    'high': high_p,
                    'low': low_p,
                    'close': close_p,
                    'volume': 1000000 + (hour * 50000)
                })
                
                price = close_p
        
        return data
    
    def calculate_indicators(self, closes: List[float]) -> Tuple[List[float], List[float], List[float]]:
        """Calculate RSI and Stochastic RSI"""
        rsi = calculate_rsi(closes, period=14)
        k, d = calculate_stochastic_rsi(closes, rsi_period=14, k_period=14, d_period=3)
        return rsi, k, d
    
    def generate_signal(self, rsi: float, k: float, d: float) -> str:
        """Generate trading signal based on thresholds"""
        
        if self.pair == "BTC-USD":
            # Standard RSI thresholds: 30/70
            oversold = self.config["rsi_threshold_oversold"]
            overbought = self.config["rsi_threshold_overbought"]
            
            if rsi < oversold:
                return "BUY"
            elif rsi > overbought:
                return "SELL"
            return "HOLD"
        
        else:  # XRP - uses Stochastic RSI
            # Stochastic RSI thresholds: 35/65
            oversold = self.config["stochastic_threshold_oversold"]
            overbought = self.config["stochastic_threshold_overbought"]
            
            if k < oversold and rsi < 40:
                return "BUY"
            elif k > overbought and rsi > 60:
                return "SELL"
            return "HOLD"
    
    def run_backtest(self) -> Dict[str, Any]:
        """Run the 100-cycle backtest"""
        print(f"\n{'='*60}")
        print(f"Phase 3 Backtest: {self.pair}")
        print(f"{'='*60}")
        
        # Generate data (last 60 days of hourly = ~1440 candles)
        data = self.generate_synthetic_data(days=60)
        closes = [d['close'] for d in data]
        
        print(f"Generated {len(closes)} hourly candles")
        print(f"Price range: ${min(closes):.2f} - ${max(closes):.2f}")
        
        # Calculate indicators
        rsi, k, d = self.calculate_indicators(closes)
        
        # Find valid start index (when indicators are ready)
        start_idx = max(14 + 14 + 3, 30)  # Need at least 30 candles for stable indicators
        
        # Track signals
        signals_generated = {"BUY": 0, "SELL": 0, "HOLD": 0}
        expected_pnl = 0.0
        actual_pnl = 0.0
        
        print(f"\nRunning {BACKTEST_CYCLES} cycles...")
        
        for cycle in range(BACKTEST_CYCLES):
            # Sample a candle every ~14 hours (to simulate different market conditions)
            idx = start_idx + (cycle * 14)
            if idx >= len(closes):
                idx = len(closes) - 1
            
            current_rsi = rsi[idx] if not math.isnan(rsi[idx]) else 50
            current_k = k[idx] if not math.isnan(k[idx]) else 50
            current_d = d[idx] if not math.isnan(d[idx]) else 50
            current_price = closes[idx]
            
            # Generate signal
            signal = self.generate_signal(current_rsi, current_k, current_d)
            signals_generated[signal] += 1
            
            # Simulate trade execution
            trade_pnl = 0.0
            
            if signal == "BUY" and self.position == 0:
                # Open long position
                position_size = (self.capital * 0.1) / current_price  # 10% of capital
                fee = position_size * current_price * FEE_PER_TRADE
                
                self.position = position_size
                self.position_value = position_size * current_price
                self.capital -= fee
                
                trade = Trade(
                    cycle=cycle,
                    timestamp=data[idx]['timestamp'],
                    pair=self.pair,
                    side="buy",
                    price=current_price,
                    size=position_size,
                    fee=fee,
                    pnl=0,  # No P&L yet
                    signal=signal,
                    rsi=current_rsi,
                    stoch_k=current_k,
                    stoch_d=current_d
                )
                self.trades.append(trade)
                
            elif signal == "SELL" and self.position > 0:
                # Close position
                proceeds = self.position * current_price
                fee = proceeds * FEE_PER_TRADE
                net_proceeds = proceeds - fee
                
                # Calculate P&L
                entry_cost = self.position_value
                trade_pnl = net_proceeds - entry_cost
                
                self.capital += net_proceeds
                actual_pnl += trade_pnl
                
                trade = Trade(
                    cycle=cycle,
                    timestamp=data[idx]['timestamp'],
                    pair=self.pair,
                    side="sell",
                    price=current_price,
                    size=self.position,
                    fee=fee,
                    pnl=trade_pnl,
                    signal=signal,
                    rsi=current_rsi,
                    stoch_k=current_k,
                    stoch_d=current_d
                )
                self.trades.append(trade)
                
                self.position = 0
                self.position_value = 0
            
            # Calculate expected P&L for this cycle
            if self.position > 0:
                unrealized_pnl = (current_price * self.position) - self.position_value
                expected_pnl = actual_pnl + unrealized_pnl
            else:
                expected_pnl = actual_pnl
            
            # Record equity
            current_equity = self.capital + (self.position * current_price)
            self.equity_curve.append(current_equity)
        
        # Close any remaining position at end
        if self.position > 0:
            final_price = closes[-1]
            proceeds = self.position * final_price
            fee = proceeds * FEE_PER_TRADE
            trade_pnl = proceeds - fee - self.position_value
            actual_pnl += trade_pnl
            self.capital += proceeds - fee
            self.position = 0
        
        # Summary
        total_fees = sum(t.fee for t in self.trades)
        
        return {
            "pair": self.pair,
            "config": self.config,
            "initial_capital": INITIAL_CAPITAL,
            "final_capital": self.capital,
            "total_return_pct": ((self.capital - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100,
            "total_trades": len(self.trades),
            "signals_generated": signals_generated,
            "total_fees": total_fees,
            "expected_pnl": expected_pnl,
            "actual_pnl": actual_pnl,
            "equity_curve": self.equity_curve[-20:],  # Last 20 values
            "trades": [asdict(t) for t in self.trades[-10:]]  # Last 10 trades
        }

def main():
    print("="*60)
    print("Phase 3 Crypto Trading Backtest Verification")
    print("="*60)
    
    results = {}
    
    # Test BTC-USD
    btc_result = Phase3Backtest("BTC-USD", CONFIG["btc"]).run_backtest()
    results["BTC-USD"] = btc_result
    
    # Test XRP-USD
    xrp_result = Phase3Backtest("XRP-USD", CONFIG["xrp"]).run_backtest()
    results["XRP-USD"] = xrp_result
    
    # Summary comparison
    print("\n" + "="*60)
    print("BACKTEST SUMMARY")
    print("="*60)
    
    for pair, result in results.items():
        print(f"\n{pair}:")
        print(f"  Initial Capital: ${result['initial_capital']:.2f}")
        print(f"  Final Capital:   ${result['final_capital']:.2f}")
        print(f"  Total Return:    {result['total_return_pct']:.2f}%")
        print(f"  Total Trades:    {result['total_trades']}")
        print(f"  Total Fees:      ${result['total_fees']:.2f}")
        print(f"  Signals:         BUY={result['signals_generated']['BUY']}, "
              f"SELL={result['signals_generated']['SELL']}, "
              f"HOLD={result['signals_generated']['HOLD']}")
        print(f"  Expected P&L:    ${result['expected_pnl']:.2f}")
        print(f"  Actual P&L:      ${result['actual_pnl']:.2f}")
        print(f"  P&L Variance:    ${abs(result['expected_pnl'] - result['actual_pnl']):.2f}")
    
    # Save results
    output_file = "/home/brad/.openclaw/workspace/BACKTEST_VERIFICATION_RESULTS.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✓ Results saved to {output_file}")
    
    return results

if __name__ == "__main__":
    main()