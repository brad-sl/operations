#!/usr/bin/env python3
"""Isolation: bull_reentry_layered pure policy (no I/O)."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.bull_reentry_layered import (  # noqa: E402
    CAP_BULL,
    CAP_PARK,
    CAP_REENTRY,
    build_signal_series,
    resolve_layered_cap,
    regime_label_from_ret30,
)


def main() -> int:
    assert regime_label_from_ret30(16) == "bull"
    assert regime_label_from_ret30(-12) == "bear"
    assert regime_label_from_ret30(3) == "flat"
    assert regime_label_from_ret30(12) == "transition"

    layer, cap, buys, alloc, _ = resolve_layered_cap(
        regime_label="bear", btc_ret_30=-11, breakout_on=True, rsi=60
    )
    assert layer == "bear_park" and cap == CAP_PARK and buys is False

    layer, cap, buys, alloc, _ = resolve_layered_cap(
        regime_label="transition", btc_ret_30=12, breakout_on=True, rsi=60
    )
    assert layer == "reentry_flat_b" and cap == CAP_REENTRY and alloc == "rebalance"

    layer, cap, buys, alloc, _ = resolve_layered_cap(
        regime_label="transition", btc_ret_30=12, breakout_on=True, rsi=80
    )
    assert cap == CAP_PARK  # RSI chase guard

    layer, cap, buys, alloc, _ = resolve_layered_cap(
        regime_label="bull", btc_ret_30=16, breakout_on=False, rsi=40
    )
    assert cap == CAP_BULL and buys is True

    # synthetic uptrend series
    d0 = date(2026, 1, 1)
    days = [d0 + timedelta(days=i) for i in range(80)]
    px = {d: 100.0 + i * 0.8 for i, d in enumerate(days)}  # steady grind up
    sigs = build_signal_series(days, px, flat_deploy_without_breakout=True)
    assert len(sigs) == 80
    assert any(s.breakout_on for s in sigs[40:]), "expected some breakout_on in grind"
    print("bull_reentry_layered isolation PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
