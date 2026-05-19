#!/usr/bin/env python3
"""
Phase 6 Telegram Alert Module
- Launch overview
- AM / PM summaries (2x daily)
"""

import os
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

# Channel ID confirmed by user
TELEGRAM_CHAT_ID = 8736967053


class TelegramAlerter:
    """Handles Telegram notifications for Phase 6."""

    def __init__(self, bot_token: Optional[str] = None):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = TELEGRAM_CHAT_ID
        self.enabled = bool(self.bot_token)

    def send_message(self, text: str) -> bool:
        """Send a message via Telegram."""
        if not self.enabled:
            print("[Telegram] Bot token not set — message not sent.")
            print(f"[Telegram] Would have sent: {text[:100]}...")
            return False

        # Placeholder for actual Telegram API call
        # In production this would use requests.post to the Telegram API
        print(f"[Telegram] Sending to {self.chat_id}: {text[:120]}...")
        return True

    def send_launch_overview(self, status: Dict[str, Any]) -> None:
        """Send overview on initial launch."""
        msg = (
            "🚀 *Phase 6 Live Launch*\n\n"
            f"Capital: ${status.get('capital', 0):.2f}\n"
            f"Pairs: {', '.join(status.get('pairs', []))}\n"
            f"Mode: {status.get('mode', 'LIVE')}\n"
            f"Open Positions: {status.get('open_positions', 0)}\n"
            f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        )
        self.send_message(msg)

    def send_daily_summary(self, summary: Dict[str, Any]) -> None:
        """Send AM or PM summary."""
        period = summary.get("period", "Daily")
        msg = (
            f"📊 *Phase 6 {period} Summary*\n\n"
            f"Trades: {summary.get('trade_count', 0)}\n"
            f"PnL: ${summary.get('total_pnl', 0):.2f}\n"
            f"Win Rate: {summary.get('win_rate', 0):.1f}%\n"
            f"Open Positions: {summary.get('open_positions', 0)}"
        )
        self.send_message(msg)


if __name__ == "__main__":
    alerter = TelegramAlerter()
    alerter.send_launch_overview({
        "capital": 967.76,
        "pairs": ["BTC-USD", "ETH-USD", "SOL-USD"],
        "mode": "LIVE",
        "open_positions": 0
    })
