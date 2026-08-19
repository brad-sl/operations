#!/usr/bin/env python3
"""ENG-S4-01: coordinator context calls verify_reconciliation after reattach."""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from phase6.core.stop_loss_coordinator import StopLossCoordinator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_suspend_reattach_context_verifies():
    verify_calls = []

    class SLMgr:
        def attach_stop_loss(self, **kwargs):
            return True

        def verify_protective_stop(self, pair, entry):
            return {"verified": True, "status": "ok"}

        def verify_reconciliation(self, basket=None, suspended=None):
            verify_calls.append({"basket": basket, "suspended": suspended})
            return {"success": True, "details": "ok"}

    client = MagicMock()
    client.get_open_stop_orders = MagicMock(return_value=[])
    client.quantize_size = MagicMock(side_effect=lambda p, s: s)

    coord = StopLossCoordinator(SLMgr(), exchange_client=client, config={"mode": "shadow"})
    positions = {"BTC-USD": {"amount": 0.01, "entry_price": 100.0, "current_price": 101.0}}

    with coord.suspend_reattach_context(["BTC-USD"], positions):
        pass

    assert len(verify_calls) == 1, "verify_reconciliation must run on success path"
    logger.info("[ENG-S4-01] coordinator verify_reconciliation — OK")
    print("[ENG-S4-P0] PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(test_suspend_reattach_context_verifies())