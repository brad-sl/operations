#!/usr/bin/env python3
"""NEEDLE-04 apply isolation: live knobs 8% floor; core blocks 3% allows 8%."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def test_live_knobs():
    cfg = json.loads((ROOT / "config/trading_config_phase6.json").read_text())
    rm = cfg["risk_management"]
    assert float(rm["stop_loss_pct"]) == 0.08
    assert float(rm["sl_base_pct"]) == 0.08
    assert float(rm["sl_min_pct"]) >= 0.06
    assert float(rm["sl_max_pct"]) >= 0.08
    assert float(cfg["global_settings"]["allocator"]["min_move_usd"]) == 25.0
    pol = json.loads((ROOT / "config/regime_cash_policy.json").read_text())
    assert pol.get("enforce") is True
    assert float(pol["add_risk"]["min_move_usd"]) == 25.0


def test_core_blocks_tight_allows_structure():
    from unittest.mock import MagicMock
    from phase6.core.stop_loss_manager import StopLossManager

    ex = MagicMock()
    cfg = json.loads((ROOT / "config/trading_config_phase6.json").read_text())
    slm = StopLossManager(ex, cfg, mode="shadow")
    assert slm.attach_stop_loss("BTC-USD", 80000.0, 0.002, sl_pct=0.03) is False
    assert slm.attach_stop_loss("LINK-USD", 14.4, 1.73, sl_pct=0.03) is False


if __name__ == "__main__":
    test_live_knobs()
    test_core_blocks_tight_allows_structure()
    print("test_isolation_needle_04_apply: OK")
