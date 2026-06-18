#!/usr/bin/env python3
"""
Phase 6 Error Notification & Alerting System
Structured logging with Telegram integration.
"""

import json
import logging
import os
import requests
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger("phase6.notifier")

class Phase6Notifier:
    """Handle structured error logging and critical Telegram alerts."""
    
    def __init__(self, log_dir: str = 'logs/phase6'):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.error_log = self.log_dir / 'errors.jsonl'
        self.critical_log = self.log_dir / 'critical_events.log'
        
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        logger.info(f"Phase6Notifier initialized. Logs: {self.log_dir}")
    
    def _send_telegram(self, message: str):
        if not self.token or not self.chat_id:
            logger.warning("Telegram credentials missing - alert not sent")
            return
            
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            requests.post(
                url,
                json={
                    "chat_id": self.chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=10,
            )
        except Exception as e:
            logger.error(f"Telegram alert failed: {e}")

    def log_error(self, error_type: str, message: str, context: Optional[Dict[str, Any]] = None) -> str:
        event_id = f"p6err-{int(datetime.utcnow().timestamp() * 1000)}"
        
        event = {
            'event_id': event_id,
            'timestamp': datetime.utcnow().isoformat(),
            'error_type': error_type,
            'message': message,
            'context': context or {}
        }
        
        with open(self.error_log, 'a') as f:
            f.write(json.dumps(event) + '\n')
            
        logger.error(f"[{error_type}] {message} (ID: {event_id})")
        return event_id
    
    def notify_critical(self, error_type: str, message: str, context: Optional[Dict[str, Any]] = None):
        event_id = self.log_error(error_type, message, context)
        
        alert_msg = f"<b>🚨 PHASE 6 CRITICAL</b>\nID: <code>{event_id}</code>\nType: {error_type}\nMessage: {message}"
        if context:
            alert_msg += f"\nContext: {json.dumps(context, indent=2)}"
            
        with open(self.critical_log, 'a') as f:
            f.write(f"{datetime.utcnow().isoformat()} | {alert_msg}\n")
            
        self._send_telegram(alert_msg)
        return event_id
