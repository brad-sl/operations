#!/usr/bin/env python3
"""
Diagnostic: What is get_enriched_positions() actually returning right now?
"""

from dotenv import load_dotenv
load_dotenv()

from phase6.core.exchange_client import CoinbaseExchangeClient
from phase6.core.live_portfolio_manager import LivePortfolioManager

def main():
    print("=== Holdings Diagnostic ===\n")

    exchange = CoinbaseExchangeClient(mode="live")
    portfolio = LivePortfolioManager(exchange)

    print("1. get_holdings():")
    holdings = portfolio.get_positions(force_refresh=True)
    print(holdings)
    print()

    print("2. get_enriched_positions():")
    enriched = portfolio.get_enriched_positions(force_refresh=True)
    print(enriched)
    print()

    print("3. Raw get_holdings() from exchange:")
    raw = exchange.get_holdings()
    print(raw)

if __name__ == "__main__":
    main()
