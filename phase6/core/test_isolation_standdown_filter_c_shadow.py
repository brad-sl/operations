#!/usr/bin/env python3
"""Isolation: stand-down C pure rules + no-order fence (no network)."""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.standdown_filter_c_shadow import (  # noqa: E402
    StanddownConfig,
    pct_return,
    process_hint,
    tape_from_closes,
    would_block_process,
)


def _closes_with_r24(r24_pct: float, n: int = 30) -> list:
    """Synthetic hourly closes ending with exact r24 move over last 24 steps."""
    # closes[0]..closes[-25] span 24 intervals if len>=25
    base = 100.0
    closes = [base] * (n - 1)
    end = base * (1.0 + r24_pct / 100.0)
    closes.append(end)
    # reshape so index -25 is base and -1 is end
    out = [base] * 25
    # linear path optional; only endpoints matter for pct_return(closes[-25], last)
    out[-1] = end
    # pad front
    while len(out) < n:
        out.insert(0, base)
    return out


def test_pct_and_primary_block() -> None:
    pr = pct_return(100, 105)
    assert pr is not None and abs(pr - 5.0) < 1e-9
    assert pct_return(0, 100) is None

    cfg = StanddownConfig()
    hot = tape_from_closes(_closes_with_r24(7.0), rsi=50.0, cfg=cfg)
    assert hot["elev_primary"] is True
    assert would_block_process(hot["elev_primary"]) is True
    assert hot["r24_pct"] is not None and hot["r24_pct"] >= 5.0

    calm = tape_from_closes(_closes_with_r24(2.0), rsi=50.0, cfg=cfg)
    assert calm["elev_primary"] is False
    assert would_block_process(calm["elev_primary"]) is False


def test_sanity_spike_dropped() -> None:
    cfg = StanddownConfig()
    # absurd jump
    closes = [1.0] * 25 + [1.0 * 50]  # +4900%
    feat = tape_from_closes(closes, cfg=cfg)
    assert feat["r24_pct"] is None or abs(feat["r24_pct"]) <= cfg.max_abs_ret_sanity_pct


def test_soft_and_strict() -> None:
    cfg = StanddownConfig()
    # soft via RSI only
    closes = [100.0] * 30  # flat
    soft = tape_from_closes(closes, rsi=70.0, cfg=cfg)
    assert soft["elev_soft"] is True
    assert soft["elev_primary"] is False  # r24 flat
    assert would_block_process(soft["elev_primary"]) is False

    strict = tape_from_closes(_closes_with_r24(13.0), rsi=40.0, cfg=cfg)
    assert strict["elev_strict"] is True
    assert strict["elev_primary"] is True


def test_process_hint() -> None:
    assert process_hint("coinbase_fill_reconcile", "rebalance_buy") is True
    assert process_hint("arch4_rebalance", "") is True
    assert process_hint("coinbase_fill_reconcile", "") is False
    assert process_hint("manual", "dust_cleanup") is False


def test_config_fence() -> None:
    cfg = StanddownConfig()
    assert cfg.place_orders is False
    assert cfg.mutate_config is False


def test_module_has_no_order_strings_in_run() -> None:
    """Sanity: run function source must not call order APIs."""
    import phase6.core.standdown_filter_c_shadow as m
    import inspect
    import re

    src = inspect.getsource(m.run_standdown_filter_c_shadow)
    # Match call-like forms, not the fence flags place_orders / mutate_config
    banned = (
        r"create_order\s*\(",
        r"place_order\s*\(",
        r"submit_order\s*\(",
        r"execute_trade\s*\(",
        r"live_buy\s*\(",
    )
    for pat in banned:
        assert re.search(pat, src) is None, pat


if __name__ == "__main__":
    test_pct_and_primary_block()
    test_sanity_spike_dropped()
    test_soft_and_strict()
    test_process_hint()
    test_config_fence()
    test_module_has_no_order_strings_in_run()
    print("test_isolation_standdown_filter_c_shadow PASS")
