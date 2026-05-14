#!/usr/bin/env python3
"""
RSI Warm-Start Bootstrap System

Fetches 60 days of historical price data and pre-calculates RSI(14)
so Phase 5 bot can fire signals immediately on startup (cycle 1).

Usage:
  python3 bootstrap_rsi_history.py                    # generates bootstrap file
  docker compose run --rm bot python3 bootstrap_rsi_history.py
"""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import requests
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment
load_dotenv()

# Constants
DAYS_HISTORY = 60
RSI_PERIOD = 14
BOOTSTRAP_FILE = Path(__file__).parent / "price_history_bootstrap.json"

# Trading pairs
PAIRS = ["BTC-USD", "XRP-USD", "ETH-USD", "DOGE-USD", "ADA-USD", "SOL-USD"]

# CoinGecko API (free, no auth required)
COINGECKO_API = "https://api.coingecko.com/api/v3"
COINGECKO_MAPPING = {
    "BTC-USD": "bitcoin",
    "XRP-USD": "ripple",
    "ETH-USD": "ethereum",
    "DOGE-USD": "dogecoin",
    "ADA-USD": "cardano",
    "SOL-USD": "solana"
}


def fetch_coingecko_historical(pair: str, days: int = 60) -> Optional[List[Tuple[int, float]]]:
    """
    Fetch historical daily close prices from CoinGecko.
    
    Args:
        pair: Trading pair (e.g., "BTC-USD")
        days: Number of days of history
    
    Returns:
        List of [timestamp_ms, close_price] or None on error
    """
    coin_id = COINGECKO_MAPPING.get(pair)
    if not coin_id:
        logger.warning(f"Pair {pair} not in CoinGecko mapping")
        return None
    
    try:
        url = f"{COINGECKO_API}/coins/{coin_id}/market_chart"
        params = {
            "vs_currency": "usd",
            "days": days,
            "interval": "daily"
        }
        
        logger.info(f"Fetching {days}d history for {pair} from CoinGecko...")
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        prices = data.get("prices", [])  # [[timestamp_ms, price], ...]
        
        if not prices:
            logger.warning(f"No price data returned for {pair}")
            return None
        
        logger.info(f"✅ Fetched {len(prices)} price points for {pair}")
        return prices
    
    except requests.exceptions.RequestException as e:
        logger.error(f"CoinGecko API error for {pair}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching {pair}: {e}")
        return None


def calculate_rsi(prices: List[float], period: int = 14) -> Optional[float]:
    """
    Calculate RSI(14) from price list.
    
    Args:
        prices: List of prices (oldest first)
        period: RSI period (default 14)
    
    Returns:
        RSI value (0-100) or None if insufficient data
    """
    if len(prices) < period + 1:
        return None
    
    # Use last (period + 1) prices for calculation
    prices_subset = prices[-(period + 1):]
    
    # Calculate price changes
    changes = [prices_subset[i] - prices_subset[i - 1] for i in range(1, len(prices_subset))]
    
    # Separate gains and losses
    gains = [c if c > 0 else 0 for c in changes]
    losses = [-c if c < 0 else 0 for c in changes]
    
    # Average gain and loss (first period uses simple average)
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    
    # Calculate RS and RSI
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return round(rsi, 2)


def bootstrap_pair(pair: str) -> Optional[Dict]:
    """
    Bootstrap RSI history for a single pair.
    
    Returns:
        Dict with prices (last 14), rsi value, or None on error
    """
    # Fetch historical data
    price_data = fetch_coingecko_historical(pair, DAYS_HISTORY)
    if not price_data:
        return None
    
    # Extract close prices (price_data is [[timestamp_ms, close], ...])
    prices = [p[1] for p in price_data]
    
    if len(prices) < RSI_PERIOD + 1:
        logger.warning(f"Insufficient data for {pair}: {len(prices)} prices (need {RSI_PERIOD + 1})")
        return None
    
    # Calculate RSI
    rsi = calculate_rsi(prices, RSI_PERIOD)
    if rsi is None:
        return None
    
    # Extract last 14 prices for live updates
    price_buffer = prices[-RSI_PERIOD:]
    
    return {
        "prices": price_buffer,
        "rsi": rsi,
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "data_points": len(prices),
        "pair": pair
    }


def main():
    """Generate bootstrap file for all pairs."""
    logger.info(f"🚀 Starting RSI warm-start bootstrap ({DAYS_HISTORY}d history)...")
    
    bootstrap_data = {}
    success_count = 0
    
    for pair in PAIRS:
        result = bootstrap_pair(pair)
        if result:
            bootstrap_data[pair] = result
            success_count += 1
            logger.info(f"✅ {pair}: RSI={result['rsi']}, prices={len(result['prices'])}")
        else:
            logger.warning(f"❌ {pair}: Bootstrap failed")
    
    if success_count == 0:
        logger.error("❌ No pairs bootstrapped. Check network/CoinGecko API.")
        return False
    
    # Write bootstrap file
    try:
        with open(BOOTSTRAP_FILE, 'w') as f:
            json.dump(bootstrap_data, f, indent=2)
        logger.info(f"✅ Bootstrap file written: {BOOTSTRAP_FILE}")
        logger.info(f"✅ {success_count}/{len(PAIRS)} pairs ready (RSI pre-seeded)")
        return True
    except Exception as e:
        logger.error(f"Failed to write bootstrap file: {e}")
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
