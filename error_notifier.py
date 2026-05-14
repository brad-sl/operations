#!/usr/bin/env python3
"""
Error Notification System for Phase 5.1
========================================

Logs critical errors (INSUFFICIENT_FUND, API failures, etc.) and notifies user.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ErrorNotifier:
    """Handle error logging and notifications."""
    
    def __init__(self, log_dir: str = '/home/brad/.openclaw/workspace/operations/crypto-bot'):
        self.log_dir = Path(log_dir)
        self.error_log = self.log_dir / 'phase5_1_errors.jsonl'
        self.critical_log = self.log_dir / 'phase5_1_critical_events.log'
        
        # Ensure files exist
        self.error_log.touch(exist_ok=True)
        self.critical_log.touch(exist_ok=True)
        
        logger.info(f"ErrorNotifier initialized")
        logger.info(f"  Error log: {self.error_log}")
        logger.info(f"  Critical log: {self.critical_log}")
    
    def log_error(self, error_type: str, message: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Log an error event.
        
        Args:
            error_type: Type of error (e.g., 'INSUFFICIENT_FUND', 'API_ERROR', 'ORDER_FAILED')
            message: Human-readable message
            context: Additional context dict (pair, amount, response, etc.)
        
        Returns:
            Event ID for tracking
        """
        event_id = f"err-{int(datetime.utcnow().timestamp() * 1000)}"
        
        event = {
            'event_id': event_id,
            'timestamp': datetime.utcnow().isoformat(),
            'error_type': error_type,
            'message': message,
            'context': context or {}
        }
        
        # Append to JSONL (one JSON per line)
        with open(self.error_log, 'a') as f:
            f.write(json.dumps(event) + '\n')
        
        logger.error(f"[{error_type}] {message} (ID: {event_id})")
        
        return event_id
    
    def notify_critical(self, error_type: str, message: str, context: Optional[Dict[str, Any]] = None):
        """
        Log CRITICAL error and prepare notification.
        
        Args:
            error_type: Type of error
            message: Message for user
            context: Error context
        
        Returns:
            Notification message ready to send
        """
        event_id = self.log_error(error_type, message, context)
        
        # Format notification
        notification = f"""
🚨 PHASE 5.1 CRITICAL ERROR
Error ID: {event_id}
Type: {error_type}
Message: {message}
Time: {datetime.utcnow().isoformat()}
"""
        
        if context:
            notification += f"\nContext:\n"
            for key, val in context.items():
                notification += f"  {key}: {val}\n"
        
        # Log to critical events
        with open(self.critical_log, 'a') as f:
            f.write(notification + '\n')
        
        logger.critical(f"CRITICAL: {error_type} - {message}")
        
        return notification, event_id
    
    def get_recent_errors(self, error_type: Optional[str] = None, limit: int = 10) -> list:
        """Get recent errors from log."""
        errors = []
        
        if not self.error_log.exists():
            return []
        
        with open(self.error_log, 'r') as f:
            for line in f:
                try:
                    event = json.loads(line.strip())
                    if error_type and event['error_type'] != error_type:
                        continue
                    errors.append(event)
                except json.JSONDecodeError:
                    continue
        
        return errors[-limit:]  # Last N errors


# Singleton instance
_notifier = None

def get_notifier() -> ErrorNotifier:
    """Get or create singleton notifier."""
    global _notifier
    if _notifier is None:
        _notifier = ErrorNotifier()
    return _notifier


def log_insufficient_fund(pair: str, required: float, available: float, order_id: str = ""):
    """Log INSUFFICIENT_FUND error."""
    notifier = get_notifier()
    context = {
        'pair': pair,
        'required_usd': required,
        'available_usd': available,
        'shortfall': required - available,
        'order_id': order_id
    }
    return notifier.notify_critical(
        'INSUFFICIENT_FUND',
        f"Failed to place order for {pair}: required ${required:.2f} but only ${available:.2f} available",
        context
    )


def log_api_error(endpoint: str, status_code: int, error_msg: str):
    """Log API error."""
    notifier = get_notifier()
    context = {
        'endpoint': endpoint,
        'status_code': status_code,
        'error_message': error_msg
    }
    return notifier.notify_critical(
        'API_ERROR',
        f"API request failed: {endpoint} ({status_code})",
        context
    )


if __name__ == '__main__':
    # Test
    notifier = get_notifier()
    
    # Simulate an error
    notification, event_id = notifier.notify_critical(
        'TEST_ERROR',
        'This is a test notification',
        {'test': True, 'timestamp': datetime.utcnow().isoformat()}
    )
    
    print(notification)
    print(f"\nEvent logged with ID: {event_id}")
