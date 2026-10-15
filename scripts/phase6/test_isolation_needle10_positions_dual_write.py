#!/usr/bin/env python3
"""NEEDLE-10: current_positions dual-write from live_state (no live orders)."""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path("/home/brad/projects/crypto-trading-bot")
sys.path.insert(0, str(ROOT))


def test_dual_write_replaces_demo_rows(tmp_path: Path):
    db = tmp_path / "phase6.db"
    live = tmp_path / "phase6_live_state.json"
    live.write_text(
        json.dumps(
            {
                "positions": [
                    {
                        "pair": "BTC-USD",
                        "amount": 0.001,
                        "entry_price": 100000.0,
                        "current_price": 110000.0,
                        "value_usd": 110.0,
                        "unrealized_pnl_pct": 0.1,
                        "side": "long",
                    },
                    {
                        "pair": "ADA-USD",
                        "amount": 100.0,
                        "entry_price": 0.5,
                        "current_price": 0.55,
                        "value_usd": 55.0,
                    },
                ]
            }
        )
    )
    con = sqlite3.connect(str(db))
    con.execute(
        """CREATE TABLE current_positions (
            ts TEXT, pair TEXT, amount REAL, entry_price REAL,
            current_price REAL, value_usd REAL, unrealized_pnl_pct REAL,
            side TEXT, source TEXT
        )"""
    )
    con.execute(
        "INSERT INTO current_positions VALUES (?,?,?,?,?,?,?,?,?)",
        ("2026-06-29", "UNI-USD", 1.0, 1.0, 1.0, 1.0, 0.0, "long", "demo"),
    )
    con.commit()

    # Minimal runner stub
    from phase6.core.phase6_runner import Phase6Runner

    runner = MagicMock(spec=Phase6Runner)
    runner.logger = MagicMock()
    # bind real method
    runner._dual_write_current_positions = Phase6Runner._dual_write_current_positions.__get__(
        runner, Phase6Runner
    )

    # Patch Path read inside method by chdir
    import os

    cwd = os.getcwd()
    try:
        # write live under data/state relative
        (tmp_path / "data" / "state").mkdir(parents=True)
        (tmp_path / "data" / "state" / "phase6_live_state.json").write_text(live.read_text())
        os.chdir(tmp_path)
        runner._dual_write_current_positions(
            con, ts="2026-10-14T00:00:00Z", holdings={}, price_snapshot={}
        )
        con.commit()
        rows = con.execute(
            "SELECT pair, source, amount FROM current_positions ORDER BY pair"
        ).fetchall()
    finally:
        os.chdir(cwd)
        con.close()

    pairs = [r[0] for r in rows]
    assert "UNI-USD" not in pairs, rows
    assert "BTC-USD" in pairs and "ADA-USD" in pairs, rows
    assert all(r[1] == "live_state" for r in rows), rows
    print("OK needle10 positions dual-write isolation")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as d:
        test_dual_write_replaces_demo_rows(Path(d))
