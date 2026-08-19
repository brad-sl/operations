#!/usr/bin/env python3
"""Isolation: StopLossCoordinator.attach_stop_loss delegates to sl_manager with order_id."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from phase6.core.stop_loss_coordinator import StopLossCoordinator

    slm = MagicMock()
    slm.attach_stop_loss.return_value = True
    coord = StopLossCoordinator(slm)
    coord.set_buy_order_ids({"ARB-USD": "ord-123"})
    ok = coord.attach_stop_loss("ARB-USD", 0.35, 100.0, order_id="ord-123", fresh_buy=True)
    assert ok is True
    slm.attach_stop_loss.assert_called_once()
    kwargs = slm.attach_stop_loss.call_args.kwargs
    assert kwargs.get("order_id") == "ord-123"
    assert kwargs.get("fresh_buy") is True
    print("OK test_isolation_sl_coordinator_attach")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())