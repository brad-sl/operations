#!/usr/bin/env python3
"""Isolation: manual liquidation registers cooldown even when external flow would classify deposit."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from phase6.core import runner_capital_events as rce
    from phase6.core.portfolio_disposition import detect_manual_disposition

    with tempfile.TemporaryDirectory() as td:
        state = Path(td) / "phase6_runner_state.json"
        state.write_text(json.dumps({"capital_nav_snapshot": 1000.0}))
        runner = type("R", (), {"state_file": str(state), "_manual_liquidation_cash_hold_usd": 0.0})()

        prev_pos = {"OP-USD": 380.0, "USD": 620.0}
        cur_pos = {"OP-USD": 0.0, "USD": 1380.0}
        deltas = {"delta_cash": 760.0, "delta_holdings": -380.0, "delta_total": 5.0}
        disp = detect_manual_disposition(prev_pos, cur_pos, **deltas, min_usd=25.0)
        assert disp and disp["event_type"] == "manual_liquidation_to_cash", disp

        settings = rce._runner_capital_settings(runner)
        rce.apply_manual_disposition(runner, {**disp, "pairs_sold": disp["pairs_sold"]}, settings)

        data = json.loads(state.read_text())
        cd = data.get("manual_sell_cooldown") or {}
        assert "OP-USD" in cd, data
        class _Plan:
            actions = [{"pair": "OP-USD", "action": "BUY", "usd": 100.0}]

        out = rce.filter_trade_plan_manual_cooldown(runner, _Plan())
        assert out.actions == [], f"expected OP blocked, got {out.actions}"
    print("OK test_isolation_capital_disposition_cooldown")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())