#!/usr/bin/env python3
"""Isolation tests for POOL-CYCLING-001 (no live config mutation)."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.pool_cycling import (  # noqa: E402
    PairScore,
    PoolCyclingConfig,
    SwapProposal,
    apply_swaps_to_active,
    propose_swaps,
    run_pool_cycling,
)


def test_propose_swaps_basic():
    active = ["BTC-USD", "ETH-USD", "WEAK-USD", "OK-USD"]
    scores = [
        PairScore("BTC-USD", 0.50, "h", 50, 0.1, 0, 0.01, True, 100, True, "c", True),
        PairScore("ETH-USD", 0.48, "h", 50, 0.1, 0, 0.01, True, 100, True, "c", True),
        PairScore("WEAK-USD", 0.20, "h", 50, 0.0, 0, 0.01, True, 0.0, False, "weak", True),
        PairScore("OK-USD", 0.42, "h", 50, 0.1, 0, 0.01, True, 50, False, "ok", True),
        PairScore("STRONG-USD", 0.55, "h", 50, 0.2, 1, 0.01, False, 0.0, False, "in", True),
    ]
    cfg = PoolCyclingConfig(
        min_score_delta=0.08,
        weak_max_score=0.35,
        strong_min_score=0.40,
        max_swaps=1,
        sticky_pairs=("BTC-USD", "ETH-USD"),
    )
    swaps = propose_swaps(scores, active, cfg)
    assert len(swaps) == 1, swaps
    assert swaps[0].remove == "WEAK-USD"
    assert swaps[0].add == "STRONG-USD"
    assert swaps[0].delta >= 0.08
    new = apply_swaps_to_active(active, swaps)
    assert "STRONG-USD" in new and "WEAK-USD" not in new
    assert "BTC-USD" in new and "ETH-USD" in new
    print("PASS test_propose_swaps_basic")


def test_sticky_never_ejected():
    active = ["BTC-USD", "ALT-USD"]
    scores = [
        PairScore("BTC-USD", 0.10, "h", 50, 0, 0, 0.01, True, 0, True, "sticky weak", True),
        PairScore("ALT-USD", 0.45, "h", 50, 0, 0, 0.01, True, 0, False, "ok", True),
        PairScore("NEW-USD", 0.90, "h", 50, 0, 0, 0.01, False, 0, False, "hot", True),
    ]
    cfg = PoolCyclingConfig(weak_max_score=0.35, strong_min_score=0.40, min_score_delta=0.05)
    swaps = propose_swaps(scores, active, cfg)
    assert all(s.remove != "BTC-USD" for s in swaps)
    print("PASS test_sticky_never_ejected")


def test_no_swap_when_delta_small():
    active = ["A-USD"]
    scores = [
        PairScore("A-USD", 0.30, "h", 50, 0, 0, 0.01, True, 0, False, "a", True),
        PairScore("B-USD", 0.34, "h", 50, 0, 0, 0.01, False, 0, False, "b", True),
    ]
    cfg = PoolCyclingConfig(min_score_delta=0.08, weak_max_score=0.35, strong_min_score=0.30)
    swaps = propose_swaps(scores, active, cfg)
    assert swaps == []
    print("PASS test_no_swap_when_delta_small")


def test_run_shadow_does_not_touch_config():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        cfg_path = td_path / "trading_config_phase6.json"
        cfg = {
            "global_settings": {
                "pairs": ["BTC-USD", "ETH-USD", "WEAK-USD"],
            },
            "phase_6_specific": {
                "opportunity_pool": ["BTC-USD", "ETH-USD", "WEAK-USD", "STRONG-USD"],
                "expansion_rules": {"max_pairs": 12},
            },
        }
        cfg_path.write_text(json.dumps(cfg))
        before = cfg_path.read_text()

        fake_scores = [
            PairScore("BTC-USD", 0.5, "h", 50, 0.1, 0, 0.01, True, 0, True, "c", True),
            PairScore("ETH-USD", 0.5, "h", 50, 0.1, 0, 0.01, True, 0, True, "c", True),
            PairScore("WEAK-USD", 0.15, "h", 40, 0.0, -1, 0.02, True, 0, False, "w", True),
            PairScore("STRONG-USD", 0.6, "h", 55, 0.2, 2, 0.01, False, 0, False, "s", True),
        ]

        with patch("phase6.core.pool_cycling.TRADING_CONFIG_PHASE6", cfg_path), patch(
            "phase6.core.pool_cycling.score_universe", return_value=fake_scores
        ), patch("phase6.core.pool_cycling.load_holdings_usd", return_value={}), patch(
            "phase6.core.pool_cycling.load_real_data",
            return_value={"data_sources": ["test"], "rsi": {}, "sentiment": {}, "price_history": {}},
        ), patch(
            "phase6.core.pool_cycling.DEFAULT_STATE_DIR", td_path
        ), patch(
            "phase6.core.pool_cycling.PROPOSALS_JSONL", td_path / "pool_cycling_proposals.jsonl"
        ), patch(
            "phase6.core.pool_cycling.LATEST_JSON", td_path / "pool_cycling_latest.json"
        ), patch(
            "phase6.core.pool_cycling.PROPOSED_PAIRS_JSON", td_path / "proposed.json"
        ):
            report = run_pool_cycling(
                cfg=PoolCyclingConfig(max_swaps=1),
                trading_config_path=cfg_path,
                write_log=True,
                write_proposed=False,
                apply_config=False,
            )
        assert cfg_path.read_text() == before
        assert report.mode == "shadow"
        assert len(report.swaps) == 1
        assert report.swaps[0]["add"] == "STRONG-USD"
        print("PASS test_run_shadow_does_not_touch_config")


def test_apply_swaps_helper():
    active = ["A", "B", "C"]
    swaps = [SwapProposal("B", "D", 0.1, 0.5, 0.4, "x", 0.0)]
    assert apply_swaps_to_active(active, swaps) == ["A", "D", "C"]
    print("PASS test_apply_swaps_helper")


if __name__ == "__main__":
    test_propose_swaps_basic()
    test_sticky_never_ejected()
    test_no_swap_when_delta_small()
    test_apply_swaps_helper()
    test_run_shadow_does_not_touch_config()
    print("ALL isolation pool cycling tests PASS")
