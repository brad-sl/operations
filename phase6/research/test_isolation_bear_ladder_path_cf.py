#!/usr/bin/env python3
"""Isolation: bear ladder path CF simulators (no network)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from phase6.research import run_bear_ladder_path_cf as m

    # synthetic bars: drift up then dump
    entry = 100.0
    bars = []
    # day1 high +4% (tags L1 +3%), day2 high +6% (L2), day3 high +9% (L3), day4 crash SL
    bars.append({"high": 104.0, "low": 99.0, "close": 103.0})
    bars.append({"high": 106.0, "low": 102.0, "close": 105.0})
    bars.append({"high": 109.0, "low": 104.0, "close": 108.0})
    bars.append({"high": 100.0, "low": 90.0, "close": 92.0})  # SL 97

    sl = m.simulate_sl_ride(entry, bars, 0.03)
    assert sl["exit_reason"] == "sl"
    assert abs(sl["r"] - (-0.03 - m.FEE_RT)) < 1e-6

    ftp = m.simulate_full_tp(entry, bars, sl_pct=0.03, tp=0.06)
    # day2 high 106 tags +6% before day4 SL
    assert ftp["exit_reason"] == "full_tp"
    assert abs(ftp["r"] - (0.06 - m.FEE_RT)) < 1e-6

    lad = m.simulate_ladder(entry, bars, sl_pct=0.03, moon_bag_frac=0.25)
    assert lad["slices"] == 3, lad
    # 0.25*0.03 + 0.25*0.05 + 0.25*0.08 + 0.25*(-0.03) - fees
    # = 0.0075 + 0.0125 + 0.02 - 0.0075 = 0.0325 - fees
    assert lad["r"] is not None and lad["r"] > 0.02, lad
    assert lad["r"] > sl["r"], (lad, sl)

    # no path
    assert m.simulate_ladder(0, [])["r"] is None

    print("bear_ladder_path_cf isolation PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
