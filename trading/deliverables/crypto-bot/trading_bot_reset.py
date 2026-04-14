#!/usr/bin/env python3
"""
Comprehensive Trading Bot Reset and Relaunch Script
Handles Phase 5 and Phase 6 Trading Bot Reconfiguration
"""

import os
import sys
import logging
import json
from datetime import datetime
from pathlib import Path

# Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format='🔧 [TRADING_BOT_RESET] %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/home/brad/.openclaw/workspace/logs/trading_bot_reset.log')
    ]
)
logger = logging.getLogger(__name__)

# Paths
BOT_DIR = Path('/home/brad/.openclaw/workspace/operations/crypto-bot')
CONFIG_DIR = BOT_DIR / 'config'
LOGS_DIR = BOT_DIR / 'logs'

def create_base_configuration():
    """Create unified base configuration for trading bots"""
    base_config = {
        'global_settings': {
            'total_capital': 1000,
            'pairs': ['BTC-USD', 'XRP-USD', 'ETH-USD', 'DOGE-USD', 'ADA-USD', 'SOL-USD'],
            'cycle_interval_seconds': 1800  # 30-minute cycles
        },
        'risk_management': {
            'max_daily_loss_pct': 2.0,
            'var_threshold': 0.015,
            'stop_loss_pct': 2.0,
            'take_profit_pct': 5.0
        },
        'sentiment': {
            'sources': ['x_api', 'reddit', 'news_api'],
            'weight': 0.4
        },
        'phase_5_specific': {
            'entry_conditions': {
                'rsi_periods': [14, 21],
                'sentiment_threshold': 0.3,
                'volatility_filter': True
            }
        },
        'phase_6_specific': {
            'expansion_rules': {
                'max_pairs': 12,
                'correlation_threshold': 0.3,
                'reserve_min_pct': 0.2
            }
        }
    }
    
    # Write Phase 5 Config
    with open(CONFIG_DIR / 'trading_config_phase5.json', 'w') as f:
        json.dump(base_config, f, indent=2)
    
    # Write Phase 6 Config
    with open(CONFIG_DIR / 'trading_config_phase6.json', 'w') as f:
        json.dump(base_config, f, indent=2)
    
    logger.info("✅ Base configurations created successfully")

def reset_trading_state():
    """Reset trading state files and logs"""
    state_files = [
        'phase4_trades.db',
        'takeover_account.json',
        'x_sentiment_cache.json'
    ]
    
    for file in state_files:
        file_path = BOT_DIR / file
        if file_path.exists():
            # Create backup
            backup_path = file_path.with_name(f"{file}.bak.{datetime.now().isoformat()}")
            file_path.rename(backup_path)
            logger.info(f"Backed up {file} to {backup_path}")
    
    # Clear and recreate log directories
    for log_dir in [LOGS_DIR, BOT_DIR / 'logs']:
        log_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info("✅ Trading state reset complete")

def update_sentiment_fetcher():
    """Update sentiment fetching mechanisms"""
    # Placeholder for advanced sentiment fetching configuration
    sentiment_config = {
        'sources': {
            'x_api': {
                'enabled': True,
                'weight': 0.4,
                'cache_duration': 3600  # 1-hour cache
            },
            'reddit': {
                'enabled': True,
                'weight': 0.3,
                'subreddits': ['CryptoCurrency', 'Bitcoin', 'CryptoMarkets']
            },
            'news_api': {
                'enabled': True,
                'weight': 0.3,
                'sources': ['CoinDesk', 'CryptoSlate', 'The Block']
            }
        }
    }
    
    with open(CONFIG_DIR / 'sentiment_config.json', 'w') as f:
        json.dump(sentiment_config, f, indent=2)
    
    logger.info("✅ Sentiment configuration updated")

def main():
    """Execute comprehensive trading bot reset"""
    logger.info("🚀 Starting Comprehensive Trading Bot Reset")
    
    try:
        create_base_configuration()
        reset_trading_state()
        update_sentiment_fetcher()
        
        logger.info("🏁 Trading Bot Reset Completed Successfully")
    except Exception as e:
        logger.error(f"❌ Reset Failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()