#!/usr/bin/env python3
"""
Test Phase 6 persistent trading loop
- Validates config loading
- Tests sentiment integration
- Verifies 30-min cycle runs
- Checks trade CSV logging
"""

import os
import json
import time
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Import phase6
import sys
sys.path.insert(0, '/home/brad/.openclaw/workspace/coding-products/crypto-bot')

from phase6 import (
    ConfigLoader, TradingConfig, SentimentManager, Phase6TradingBot,
    GlobalSettings, RiskManagement, ExpansionRules, Phase6Specific
)


def test_config_loading():
    """Test config loading from trading_config_phase6.json"""
    config_path = 'config/trading_config_phase6.json'
    print(f"Testing config loading from {config_path}...")
    
    if not os.path.exists(config_path):
        print(f"  ⚠️  Config file not found at {config_path}")
        return False
    
    try:
        config = ConfigLoader.load(config_path)
        assert config.global_settings.total_capital == 1000
        assert len(config.global_settings.pairs) == 6
        assert config.global_settings.cycle_interval_seconds == 1800
        assert config.risk_management.stop_loss_pct == 2.0
        print(f"  ✅ Config loaded: {config.global_settings.total_capital} capital, "
              f"{len(config.global_settings.pairs)} pairs, "
              f"{config.global_settings.cycle_interval_seconds}s cycles")
        return True
    except Exception as e:
        print(f"  ❌ Config load failed: {e}")
        return False


def test_sentiment_integration():
    """Test sentiment manager integration"""
    print("\nTesting sentiment integration...")
    
    sentiment_file = '/home/brad/.openclaw/workspace/agents/memory/trading-monitor-status.json'
    if not os.path.exists(sentiment_file):
        print(f"  ⚠️  Sentiment file not found at {sentiment_file}")
        return False
    
    try:
        sentiment = SentimentManager.get_sentiment()
        assert 'overall' in sentiment
        assert 'state' in sentiment
        assert 0 <= sentiment['overall'] <= 1
        print(f"  ✅ Sentiment fetched: {sentiment['overall']:.2f} ({sentiment['state']})")
        return True
    except Exception as e:
        print(f"  ❌ Sentiment fetch failed: {e}")
        return False


def test_rsi_calculation():
    """Test RSI calculation with mock data"""
    print("\nTesting RSI calculation...")
    
    try:
        # Mock a bot with price history
        config_path = 'config/trading_config_phase6.json'
        config = ConfigLoader.load(config_path)
        
        # Create bot (will fail on Coinbase init, but we can test RSI)
        # We'll mock the Coinbase client
        with patch('phase6.CoinbaseAdvancedClient'):
            bot = Phase6TradingBot.__new__(Phase6TradingBot)
            bot.config = config
            bot.pairs = config.global_settings.pairs
            bot.logger = Mock()
            
            # Test with synthetic RSI data
            pair = 'BTC-USD'
            bot.price_history = {p: [] for p in bot.pairs}
            
            # Generate rising prices (should give high RSI)
            for i in range(20):
                bot.price_history[pair].append(50000 + i * 100)
            
            rsi = bot._calculate_rsi(pair)
            assert 0 <= rsi <= 100
            print(f"  ✅ RSI calculated: {rsi:.1f} (for rising prices)")
            
            # Generate falling prices (should give low RSI)
            bot.price_history[pair] = []
            for i in range(20):
                bot.price_history[pair].append(50000 - i * 100)
            
            rsi = bot._calculate_rsi(pair)
            assert 0 <= rsi <= 100
            print(f"  ✅ RSI calculated: {rsi:.1f} (for falling prices)")
            
            return True
    except Exception as e:
        print(f"  ❌ RSI test failed: {e}")
        return False


def test_csv_logging():
    """Test CSV trade logging"""
    print("\nTesting CSV trade logging...")
    
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, 'test_trades.csv')
            
            # Mock a bot
            config_path = 'config/trading_config_phase6.json'
            config = ConfigLoader.load(config_path)
            
            with patch('phase6.CoinbaseAdvancedClient'):
                bot = Phase6TradingBot.__new__(Phase6TradingBot)
                bot.config = config
                bot.pairs = config.global_settings.pairs
                bot.logger = Mock()
                bot.trades_csv_path = csv_path
                
                # Init CSV
                bot._init_trades_csv()
                assert os.path.exists(csv_path)
                
                # Log a trade
                bot._log_trade('BTC-USD', 'BUY', 50000.0, 0.01, 'BUY')
                
                # Check CSV
                with open(csv_path) as f:
                    lines = f.readlines()
                    assert len(lines) >= 2  # Header + 1 trade
                    assert 'BTC-USD' in lines[1]
                    assert 'BUY' in lines[1]
                
                print(f"  ✅ CSV logging works: {len(lines)-1} trades recorded")
                return True
    except Exception as e:
        print(f"  ❌ CSV logging test failed: {e}")
        return False


def test_exit_logic():
    """Test position exit logic (SL/TP)"""
    print("\nTesting exit logic...")
    
    try:
        from phase6 import Position
        
        config_path = 'config/trading_config_phase6.json'
        config = ConfigLoader.load(config_path)
        
        with patch('phase6.CoinbaseAdvancedClient'):
            bot = Phase6TradingBot.__new__(Phase6TradingBot)
            bot.config = config
            bot.pairs = config.global_settings.pairs
            bot.logger = Mock()
            bot.trades_csv_path = '/tmp/test_trades.csv'
            bot.sl_pct = 0.02  # 2%
            bot.tp_pct = 0.05  # 5%
            bot.positions = {}
            
            # Create mock position
            pair = 'BTC-USD'
            entry_price = 50000.0
            pos = Position(
                pair=pair,
                entry_price=entry_price,
                entry_qty=0.01,
                entry_timestamp='2026-04-29T00:00:00Z',
                sl_price=entry_price * 0.98,
                tp_price=entry_price * 1.05
            )
            bot.positions[pair] = pos
            
            # Test SL trigger
            sl_price = entry_price * 0.97  # Below SL
            exited = bot._check_exit(pair, sl_price, 50)  # RSI=50 (neutral)
            assert exited, "Should exit on stop loss"
            assert pair not in bot.positions
            print(f"  ✅ Stop loss triggered at {sl_price:.2f}")
            
            # Test TP trigger
            pos = Position(
                pair=pair,
                entry_price=entry_price,
                entry_qty=0.01,
                entry_timestamp='2026-04-29T00:00:00Z',
                sl_price=entry_price * 0.98,
                tp_price=entry_price * 1.05
            )
            bot.positions[pair] = pos
            
            tp_price = entry_price * 1.06  # Above TP
            exited = bot._check_exit(pair, tp_price, 50)
            assert exited, "Should exit on take profit"
            assert pair not in bot.positions
            print(f"  ✅ Take profit triggered at {tp_price:.2f}")
            
            # Test RSI sell trigger
            pos = Position(
                pair=pair,
                entry_price=entry_price,
                entry_qty=0.01,
                entry_timestamp='2026-04-29T00:00:00Z',
                sl_price=entry_price * 0.98,
                tp_price=entry_price * 1.05
            )
            bot.positions[pair] = pos
            bot.rsi_sell_thresh = 70
            
            exited = bot._check_exit(pair, entry_price * 1.02, 75)  # RSI > 70
            assert exited, "Should exit on RSI>70"
            assert pair not in bot.positions
            print(f"  ✅ RSI sell triggered at RSI=75")
            
            return True
    except Exception as e:
        print(f"  ❌ Exit logic test failed: {e}")
        return False


def main():
    """Run all tests"""
    print("="*80)
    print("PHASE 6 PERSISTENT TRADING LOOP - TEST SUITE")
    print("="*80)
    
    tests = [
        ("Config Loading", test_config_loading),
        ("Sentiment Integration", test_sentiment_integration),
        ("RSI Calculation", test_rsi_calculation),
        ("CSV Logging", test_csv_logging),
        ("Exit Logic", test_exit_logic),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"  ❌ Test error: {e}")
            results.append((name, False))
    
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == '__main__':
    os.chdir('/home/brad/.openclaw/workspace/coding-products/crypto-bot')
    exit(main())
