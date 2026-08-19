#!/usr/bin/env python3
"""Isolation: runtime knobs — config wins; no silent 12%/24h/$200 defeats."""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core import runtime_knobs as rk  # noqa: E402
from phase6.core.runtime_knobs import (  # noqa: E402
    allocator_kwargs,
    create_allocator_from_config,
    min_reserve_usd,
    rebalance_cap_usd,
    stop_loss_block_rebuy_hours,
    stop_loss_pct,
)


def _live_cfg() -> dict:
    p = ROOT / "config" / "trading_config_phase6.json"
    return json.loads(p.read_text())


def test_live_config_stop_is_3pct_not_12() -> None:
    cfg = _live_cfg()
    sl = stop_loss_pct(cfg)
    assert abs(sl - 0.03) < 1e-9, sl
    kw = allocator_kwargs(cfg)
    assert abs(kw["stop_loss_pct"] - 0.03) < 1e-9
    assert kw["min_move_usd"] == 50.0
    assert abs(kw["min_score_delta"] - 0.05) < 1e-9
    print("PASS live config → allocator stop 3%, min_move 50, score_delta 0.05")


def test_create_allocator_from_config_honors_override() -> None:
    cfg = _live_cfg()
    a = create_allocator_from_config("rotation", cfg)
    assert abs(a.config.stop_loss_pct - 0.03) < 1e-9
    a2 = create_allocator_from_config("rotation", cfg, stop_loss_pct=0.02)
    assert abs(a2.config.stop_loss_pct - 0.02) < 1e-9
    print("PASS create_allocator_from_config + override")


def test_cap_and_reserve_match_config() -> None:
    cfg = _live_cfg()
    assert rebalance_cap_usd(cfg) == 150.0
    assert min_reserve_usd(cfg) == 50.0
    assert stop_loss_block_rebuy_hours(cfg) == 72.0
    # empty → intended defaults (not 200 / 24 / 12%)
    assert rebalance_cap_usd({}) == 150.0
    assert min_reserve_usd({}) == 50.0
    assert stop_loss_block_rebuy_hours({}) == 72.0
    assert abs(stop_loss_pct({}) - 0.03) < 1e-9
    print("PASS cap/reserve/block defaults = product policy")


def test_coordinators_do_not_hardcode_sl12_or_cap200() -> None:
    from phase6.core import rebalance_coordinator as rc
    from phase6.core import cycle_coordinator as cc
    from phase6.core import runner_capital_events as rce

    rc_src = inspect.getsource(rc)
    cc_src = inspect.getsource(cc)
    rce_src = inspect.getsource(rce)

    assert "stop_loss_pct=0.12" not in rc_src
    assert "stop_loss_pct=0.12" not in cc_src
    assert "min_move_usd=50.0, min_score_delta=0.05, stop_loss_pct=0.12" not in rc_src
    assert 'rebalance_cap_usd", 200.0)' not in rc_src
    assert "min_reserve_usd\", 200.0)" not in rc_src
    assert "min_reserve_usd\": 250.0" not in rc_src
    assert "min_rsi=30.0" not in rc_src
    # capital settings fallbacks
    assert (
        'capital_event_stop_loss_exchange_block_rebuy_hours", 24.0)' not in rce_src
    )
    assert 'stop_loss_exchange_block_rebuy_hours", 24.0)' not in rce_src
    assert "create_allocator_from_config" in rc_src
    assert "create_allocator_from_config" in cc_src
    print("PASS no SL12 / $200 / $250 / 24h fallback hardcodes in live paths")


def test_empty_config_allocator_not_legacy_12pct() -> None:
    kw = allocator_kwargs({})
    assert abs(kw["stop_loss_pct"] - 0.03) < 1e-9
    assert kw["stop_loss_pct"] != 0.12
    print("PASS empty config allocator default is 3% not 12%")


if __name__ == "__main__":
    test_live_config_stop_is_3pct_not_12()
    test_create_allocator_from_config_honors_override()
    test_cap_and_reserve_match_config()
    test_coordinators_do_not_hardcode_sl12_or_cap200()
    test_empty_config_allocator_not_legacy_12pct()
    print("ALL RUNTIME KNOBS ISOLATION CHECKS PASSED")
