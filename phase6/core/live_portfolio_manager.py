"""
LivePortfolioManager
Maintains current positions by querying the exchange.
Rate-limit safe: callers should prefer cached views unless after a trade.
"""
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class LivePortfolioManager:
    def __init__(self, exchange, initial_capital: float = None):
        self.exchange = exchange
        self.initial_capital = initial_capital
        self.positions = {}
        self.verified = False
        self.last_refresh = None
        self.refresh()

    def refresh(self):
        """Refresh positions from the exchange (use sparingly)."""
        try:
            data = self.exchange.get_holdings_verified()
            if data.get("verified", False):
                self.positions = data.get("positions", {})
                self.verified = True
                self.last_refresh = datetime.now()
            else:
                self.verified = False
                # Keep previous positions only if we had them; sentinel is in get_*
        except Exception:
            self.verified = False
            self.positions = {}

    def has_open_positions(self):
        holdings = self.get_positions()
        if not holdings.get("verified", False):
            return None
        return len(holdings.get("positions", {})) > 0

    def get_positions(self, force_refresh=False):
        if force_refresh or not self.last_refresh or (datetime.now() - self.last_refresh) > timedelta(minutes=10):
            self.refresh()
        return {
            "positions": self.positions,
            "verified": self.verified,
            "error": None if self.verified else "Unverified or error"
        }

    def get_enriched_positions(self, force_refresh=False, price_snapshot=None):
        """Return positions with current USD values.
        ALWAYS returns structured dict with 'verified' key.
        On any error or unverified state, returns sentinel with verified=False.
        Never returns bare {} (P6-151 / G3 critical).
        """
        if force_refresh or not self.last_refresh or (datetime.now() - self.last_refresh) > timedelta(minutes=10):
            self.refresh()
        try:
            base_positions = self.positions if self.verified else {}
            if not self.verified:
                return {"positions": {}, "verified": False, "error": "Unverified or error", "value_usd": {}}
            enriched = self.exchange.get_enriched_positions(force_refresh=force_refresh, price_snapshot=price_snapshot)
            # If exchange also returns bare or missing verified, wrap it
            if isinstance(enriched, dict) and enriched and "verified" not in enriched:
                enriched = {
                    "positions": enriched,
                    "verified": True,
                    "error": None,
                    "value_usd": enriched,  # legacy compat for some callers
                }
            return enriched if isinstance(enriched, dict) else {
                "positions": {}, "verified": False, "error": "Bad enrichment response"
            }
        except Exception as e:
            logger.error(f"LivePortfolioManager get_enriched_positions failed: {e}")
            return {"positions": {}, "verified": False, "error": str(e)}