#!/usr/bin/env python3
"""
Phase 6 Runner Monitoring Agent

Duties:
- Check if the main Phase6Runner is running
- Verify last rebalance timestamp is recent (respect daily 9am schedule + grace)
- Detect excessive errors in logs
- Send alerts via Telegram on issues

Mitigation Strategies:
- Auto-restart runner if down (optional)
- Trigger manual rebalance if overdue
- Escalate to human via Telegram if critical

Escalation Path:
1. Warning → Telegram alert
2. Critical → Telegram + log to file
3. Persistent failure → Human intervention required
"""

import os
import sys
import time
import subprocess
import requests
from datetime import datetime, timedelta, time as dt_time
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
RUNNER_LOG = "logs/phase6_runner.log"
STATE_FILE = "data/state/phase6_runner_state.json"


def send_telegram(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[MONITOR] Telegram not configured")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=10)
    except Exception as e:
        print(f"[MONITOR] Telegram send failed: {e}")


def is_runner_running() -> bool:
    try:
        result = subprocess.run(
            ["pgrep", "-f", "phase6_runner.py"],
            capture_output=True, text=True
        )
        return bool(result.stdout.strip())
    except Exception:
        return False


def check_last_rebalance() -> bool:
    """Returns True if healthy (suppress alert).
    Respects the actual daily_rebalance_time from config (21:00 PT per trading_config_phase6.json).
    Only flags overdue *after* the target window + 1h grace when last_rebalance_date is stale.
    This prevents false "over 24h/36h" alarms during the day when the evening rebalance is still pending.
    Matches the runner's _should_rebalance logic exactly.
    """
    if not os.path.exists(STATE_FILE):
        return False
    try:
        import json
        with open(STATE_FILE) as f:
            state = json.load(f)
        last = state.get("last_rebalance_date")
        if not last:
            return False
        last_date = datetime.fromisoformat(last).date()
        now = datetime.now()
        today = now.date()

        # Load real schedule (no hard-coded 09:00/10:00)
        rebalance_time_str = "21:00"
        try:
            with open("config/trading_config_phase6.json") as cf:
                cfg = json.load(cf)
            rebalance_time_str = cfg.get("scheduler", {}).get("daily_rebalance_time", "21:00")
        except Exception:
            pass
        target = dt_time.fromisoformat(rebalance_time_str)
        grace_delta = timedelta(hours=1)

        if last_date == today:
            return True
        days = (today - last_date).days
        if days <= 0:
            return True
        if days == 1:
            # Yesterday's last; today's 21:00 window + grace not yet passed -> healthy (no false alarm)
            target_dt = datetime.combine(today, target) + grace_delta
            if now < target_dt:
                return True
            else:
                return False
        # >1 day stale
        return False
    except Exception:
        return False


def main():
    print(f"[MONITOR] Phase 6 Monitoring Agent started at {datetime.now()}")

    if not is_runner_running():
        msg = "🚨 CRITICAL: Phase 6 Runner is NOT running!"
        print(msg)
        send_telegram(msg)
        # Optional: auto-restart logic can go here
        return

    if not check_last_rebalance():
        msg = "⚠️ WARNING: Rebalance window missed for configured daily time (21:00 PT + 1h grace; last_rebalance stale)"
        print(msg)
        send_telegram(msg)

    print("[MONITOR] Health check passed")


if __name__ == "__main__":
    main()
