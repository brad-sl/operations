#!/usr/bin/env python3
"""
Phase 6 Structured Logging Configuration
- Console + file logging
- Separate error log
- JSON structured option
"""

import logging
import json
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime


def setup_phase6_logging(
    log_dir: Path = None,
    level: int = logging.INFO,
    max_bytes: int = 5_000_000,
    backup_count: int = 3
) -> logging.Logger:
    """
    Set up structured logging for Phase 6.

    Returns a configured logger named 'phase6'.
    """
    if log_dir is None:
        log_dir = Path(__file__).parent.parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("phase6")
    logger.setLevel(level)
    logger.handlers.clear()  # Avoid duplicate handlers

    # Formatter
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )

    # Main log file (rotating)
    main_handler = RotatingFileHandler(
        log_dir / "phase6_trading.log",
        maxBytes=max_bytes,
        backupCount=backup_count
    )
    main_handler.setFormatter(formatter)
    logger.addHandler(main_handler)

    # Error-only log
    error_handler = RotatingFileHandler(
        log_dir / "phase6_errors.log",
        maxBytes=max_bytes,
        backupCount=backup_count
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    logger.addHandler(error_handler)

    # Console output
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    logger.info("Phase 6 logging initialized")
    return logger


if __name__ == "__main__":
    logger = setup_phase6_logging()
    logger.info("This is a normal message")
    logger.error("This is an error message")
    print("Logging test complete. Check logs/ directory.")