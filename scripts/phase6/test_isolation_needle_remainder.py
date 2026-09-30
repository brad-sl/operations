#!/usr/bin/env python3
"""Isolation: NEEDLE-01/02/05/07/08 contracts. No live orders."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path("/home/brad/projects/crypto-trading-bot")
sys.path.insert(0, str(ROOT))


def test_01_never_dumps_usdc():
    from phase6.core.deploy_clip_unwind import plan_clip_unwind

    p = plan_clip_unwind(usd=50, usdc=1432, target_usd_reserve=150)
    assert p.action == "unwind"
    assert p.unwind_usd <= 150
    assert p.unwind_usd == 100  # shortfall only
    p2 = plan_clip_unwind(usd=148, usdc=1432, target_usd_reserve=150)
    assert p2.action == "hold"
    p3 = plan_clip_unwind(usd=50, usdc=1432, target_usd_reserve=150, park_signal=True)
    assert p3.action == "hold"
    p4 = plan_clip_unwind(usd=10, usdc=2000, target_usd_reserve=2000)
    assert p4.unwind_usd <= 150
    print("[01] clip unwind cap OK")


def test_02_overlay_prefers_latch(tmp_path: Path):
    from phase6.core.tryout_sent_latch import write_latches_from_scores, active_latch_for_pair

    p = tmp_path / "latch.json"
    write_latches_from_scores(
        {"LINK-USD": 0.31},
        tryout_pairs=["LINK-USD"],
        floor=0.30,
        source="test",
        path=p,
    )
    row = active_latch_for_pair("LINK-USD", floor=0.30, path=p)
    assert row is not None
    assert float(row["cleared_sent"]) >= 0.30
    print("[02] latch overlay OK")


def test_05_tryout_clears_min_move_flag_off():
    from phase6.core.needle05_size_split import plan_size_split, from_config

    p = plan_size_split(equity_usd=2282, min_move_usd=25, tryout_usd=25, enabled=False)
    assert p.tryout_passes_min_move is True
    assert p.enabled is False
    assert p.core_plan_usd >= 400
    cfg = json.loads((ROOT / "config/trading_config_phase6.json").read_text())
    live = from_config(cfg, 2282)
    assert live.min_move_usd <= 25.0 + 1e-9
    assert live.tryout_passes_min_move
    assert live.enabled is False
    print("[05] size split flag-off OK")


def test_07_refuses_full_bag_even_if_cap_loose():
    from unittest.mock import patch
    from phase6.core.sl_dust_sweep import sweep_orphan_dust

    class _BagEx:
        def get_crypto_available(self, asset):
            return 1.73

        def get_holdings_verified(self):
            return {
                "positions": {"LINK": {"available": 0.04, "hold": 1.69, "amount": 1.73}},
                "verified": True,
            }

        def get_price(self, pair):
            return 14.4

        def get_open_stop_orders(self, pair):
            return []

        def get_open_orders(self, pair):
            return []

        def place_market_sell(self, *a, **k):
            raise AssertionError("NEEDLE-07 must not sell full bag")

    with patch(
        "phase6.core.sl_dust_sweep.list_orphan_dust_from_live_state",
        return_value=[{"pair": "LINK-USD", "amount": 1.73, "value_usd": 24.9}],
    ):
        out = sweep_orphan_dust(_BagEx(), dry_run=False, max_usd=50.0, skip_if_open_stop=False)
    r = (out.get("results") or [None])[0]
    assert r and r.get("skipped") is True
    assert r.get("skip_reason") in {
        "needle07_full_bag",
        "above_max_usd_full_bag",
        "held_under_stop_not_dust",
    }
    print("[07] full bag refuse OK")


def test_08_rank_does_not_mutate_membership(tmp_path: Path):
    from phase6.core.needle08_ignition_rank import rank_from_scout_board

    board = {
        "top": [{"pair": "ETH-USD", "score": 0.709}],
        "all_scored": [
            {"pair": "ETH-USD", "score": 0.709, "phase": "ignition"},
            {"pair": "SOL-USD", "score": 0.40, "phase": "base"},
        ],
    }
    out = rank_from_scout_board(board, universe=["ETH-USD", "SOL-USD"], write=False)
    assert out["mutates_membership"] is False
    assert out["ranked"][0]["pair"] == "ETH-USD"
    print("[08] ranking-only OK")


def main():
    test_01_never_dumps_usdc()
    with tempfile.TemporaryDirectory() as d:
        test_02_overlay_prefers_latch(Path(d))
        test_08_rank_does_not_mutate_membership(Path(d))
    test_05_tryout_clears_min_move_flag_off()
    test_07_refuses_full_bag_even_if_cap_loose()
    print("OK needle remainder isolation")


if __name__ == "__main__":
    main()
