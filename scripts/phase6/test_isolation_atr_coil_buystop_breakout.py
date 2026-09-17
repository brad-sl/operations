#!/usr/bin/env python3
"""Isolation: ATR coil buy-stop lab seed (no network, no live)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.atr_coil_buystop_breakout import (  # noqa: E402
    ATR_FAST,
    ENTRY_MULT,
    LAB_ONLY,
    STOP_MULT,
    generate_signals,
    latest_setup,
    plain_english_parked,
    true_range,
)


def _fixture(n: int = 80) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    close = 100 + np.cumsum(rng.normal(0, 0.3, size=n))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + 0.2
    low = np.minimum(open_, close) - 0.2
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close})


def test_lab_flag():
    assert LAB_ONLY is True
    assert "PARKED" in plain_english_parked() or "parked" in plain_english_parked().lower() or "LAB" in plain_english_parked()


def test_true_range_nonneg():
    df = _fixture(30)
    tr = true_range(df["high"], df["low"], df["close"])
    assert (tr.dropna() >= 0).all()


def test_generate_signals_columns():
    df = _fixture(80)
    sig = generate_signals(df)
    for col in ("atr20", "atr30", "coiling", "entry_level", "stop_level", "signal"):
        assert col in sig.columns
    # ATR warm-up: first bar has no full window
    assert pd.isna(sig["atr20"].iloc[0])
    assert sig["atr20"].iloc[ATR_FAST:].notna().all()
    assert sig["signal"].isin([0, 1]).all()


def test_entry_stop_geometry_when_valid():
    df = _fixture(80)
    sig = generate_signals(df, entry_mult=ENTRY_MULT, stop_mult=STOP_MULT)
    valid = sig["atr20"].notna() & (sig["signal"] == 1)
    if valid.any():
        i = valid.idxmax()
        row = sig.loc[i]
        expected_entry = float(row["open"]) + ENTRY_MULT * float(row["atr20"])
        expected_stop = expected_entry - STOP_MULT * float(row["atr20"])
        assert abs(float(row["entry_level"]) - expected_entry) < 1e-9
        assert abs(float(row["stop_level"]) - expected_stop) < 1e-9
        assert float(row["stop_level"]) < float(row["entry_level"])


def test_coil_requires_atr20_lt_atr30():
    df = _fixture(80)
    sig = generate_signals(df)
    armed = sig["signal"] == 1
    if armed.any():
        assert (sig.loc[armed, "atr20"] < sig.loc[armed, "atr30"]).all()


def test_latest_setup_shape():
    df = _fixture(80)
    setup = latest_setup(df)
    assert setup is not None
    assert setup["lab_only"] is True
    assert "entry_level" in setup


def main() -> int:
    import pandas as pd  # noqa: F401 — used in test_generate via isna path

    test_lab_flag()
    test_true_range_nonneg()
    test_generate_signals_columns()
    test_entry_stop_geometry_when_valid()
    test_coil_requires_atr20_lt_atr30()
    test_latest_setup_shape()
    print("PASS isolation atr_coil_buystop_breakout")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
