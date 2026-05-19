import logging
from typing import Optional

logger = logging.getLogger(__name__)

def get_user_currency_preference() -> str:
    """Prompt user for USD or USDC preference."""
    while True:
        choice = input("Choose trading fiat (USD/USDC): ").strip().upper()
        if choice in ['USD', 'USDC']:
            logger.info(f"User selected trading fiat: {choice}")
            return choice
        print("Invalid choice. Enter USD or USDC.")

def confirm_entry_price(pair: str, suggested_price: float) -> Optional[float]:
    """Prompt for entry price confirmation."""
    print(f"Entry price for {pair}? (Enter for current ${suggested_price:.2f}): ")
    user_input = input().strip()
    if not user_input:
        logger.info(f"Using suggested entry price for {pair}: ${suggested_price:.2f}")
        return suggested_price
    try:
        price = float(user_input)
        logger.info(f"User confirmed entry price for {pair}: ${price:.2f}")
        return price
    except ValueError:
        print("Invalid price. Using suggested.")
        return suggested_price

def approve_liquidation(pair: str, qty: float, usd_to_raise: float, reason: str) -> bool:
    """Prompt for liquidation approval."""
    print(f"Approve selling {qty:.4f} {pair} to raise ~${usd_to_raise:.2f} USD? Reason: {reason} (y/n): ")
    choice = input().strip().lower()
    approved = choice in ['y', 'yes']
    logger.info(f"Liquidation {'approved' if approved else 'rejected'} for {pair}: {qty}")
    return approved

def confirm_sl_tp(pair: str, sl_price: float, tp_price: float) -> bool:
    """Confirm SL/TP settings."""
    print(f"Set SL/TP for {pair}: SL=${sl_price:.2f}, TP=${tp_price:.2f} (y/n): ")
    choice = input().strip().lower()
    confirmed = choice in ['y', 'yes']
    logger.info(f"SL/TP {'confirmed' if confirmed else 'rejected'} for {pair}")
    return confirmed
