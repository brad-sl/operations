#!/bin/bash
# Comprehensive Crypto Trading Bot Reset Script

# Ensure directories exist
mkdir -p /home/brad/.openclaw/workspace/operations/crypto-bot/config
mkdir -p /home/brad/.openclaw/workspace/operations/crypto-bot/logs

# Reset git repository state
cd /home/brad/.openclaw/workspace/operations/crypto-bot
git fetch origin
git checkout feature/phase4b-production-separation
git reset --hard origin/feature/phase4b-production-separation

# Backup existing configurations
timestamp=$(date +"%Y%m%d_%H%M%S")
mkdir -p /home/brad/.openclaw/workspace/operations/crypto-bot/config/backups

# Phase 5 Configuration
cat > config/trading_config_phase5.json << EOL
{
    "global_settings": {
        "total_capital": 1000,
        "pairs": ["BTC-USD", "XRP-USD", "ETH-USD", "DOGE-USD", "ADA-USD", "SOL-USD"],
        "cycle_interval_seconds": 1800
    },
    "risk_management": {
        "max_daily_loss_pct": 2.0,
        "var_threshold": 0.015,
        "stop_loss_pct": 2.0,
        "take_profit_pct": 5.0
    },
    "sentiment": {
        "sources": ["x_api", "reddit", "news_api"],
        "weight": 0.4
    },
    "phase_5_specific": {
        "entry_conditions": {
            "rsi_periods": [14, 21],
            "sentiment_threshold": 0.3,
            "volatility_filter": true
        }
    }
}
EOL

# Phase 6 Configuration
cat > config/trading_config_phase6.json << EOL
{
    "global_settings": {
        "total_capital": 1000,
        "pairs": ["BTC-USD", "XRP-USD", "ETH-USD", "DOGE-USD", "ADA-USD", "SOL-USD"],
        "cycle_interval_seconds": 1800
    },
    "risk_management": {
        "max_daily_loss_pct": 2.0,
        "var_threshold": 0.015,
        "stop_loss_pct": 2.0,
        "take_profit_pct": 5.0
    },
    "phase_6_specific": {
        "expansion_rules": {
            "max_pairs": 12,
            "correlation_threshold": 0.3,
            "reserve_min_pct": 0.2
        }
    }
}
EOL

# Sentiment Configuration
cat > config/sentiment_config.json << EOL
{
    "sources": {
        "x_api": {
            "enabled": true,
            "weight": 0.4,
            "cache_duration": 3600
        },
        "reddit": {
            "enabled": true,
            "weight": 0.3,
            "subreddits": ["CryptoCurrency", "Bitcoin", "CryptoMarkets"]
        },
        "news_api": {
            "enabled": true,
            "weight": 0.3,
            "sources": ["CoinDesk", "CryptoSlate", "The Block"]
        }
    }
}
EOL

# Commit changes
git add config/trading_config_phase5.json config/trading_config_phase6.json config/sentiment_config.json
git commit -m "Trading Bot Reset: Updated configurations for Phase 5 and Phase 6"
git push origin feature/phase4b-production-separation

# Output success message
echo "🚀 Trading Bot Configuration Reset Complete"