"""ATR coil + buy-stop breakout — LAB ONLY seed (parked 2026-09-17).

Recipe (crypto 24/7; no futures Friday exit):
  - Coil gate: ATR(20) < ATR(30)
  - Buy-stop level: open + 2.5 * ATR(20)
  - Stop: entry - 0.5 * ATR(20)

NOT wired to live runner, evaluate_buy_entry, basket, or auto-promote.
Plan: docs/plans/2026-09-17-atr-coil-buystop-breakout-lab.md
Cousin (different coil def): phase6/research/squeeze_regime_breakout.py
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

# ---------- CONFIG (frozen v0; grid only via explicit overrides) ----------
ATR_FAST = 20
ATR_SLOW = 30
ENTRY_MULT = 2.5  # open + ENTRY_MULT * ATR(20)
STOP_MULT = 0.5  # stop distance = STOP_MULT * ATR(20)
# -------------------------------------------------------------------------

SCHEMA = "atr_coil_buystop_breakout_v0"
LAB_ONLY = True


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def atr_sma(tr: pd.Series, period: int) -> pd.Series:
    """Simple moving average of true range (v0). Wilder = future grid arm only."""
    return tr.rolling(int(period)).mean()


def generate_signals(
    df: pd.DataFrame,
    *,
    atr_fast: int = ATR_FAST,
    atr_slow: int = ATR_SLOW,
    entry_mult: float = ENTRY_MULT,
    stop_mult: float = STOP_MULT,
) -> pd.DataFrame:
    """
    Expects columns: open, high, low, close (case-insensitive ok after normalize).
    Adds: tr, atr20, atr30, coiling, entry_level, stop_level, signal
    signal: 1 = arm buy-stop setup this bar, 0 = flat / no setup
    """
    if df is None or df.empty:
        out = pd.DataFrame()
        out.attrs["schema"] = SCHEMA
        out.attrs["lab_only"] = LAB_ONLY
        return out

    work = df.copy()
    cols = {c.lower(): c for c in work.columns}
    for need in ("open", "high", "low", "close"):
        if need not in cols:
            raise ValueError(f"generate_signals requires column '{need}' (got {list(work.columns)})")
    o = work[cols["open"]].astype(float)
    h = work[cols["high"]].astype(float)
    low = work[cols["low"]].astype(float)
    c = work[cols["close"]].astype(float)

    tr = true_range(h, low, c)
    atr20 = atr_sma(tr, atr_fast)
    atr30 = atr_sma(tr, atr_slow)
    coiling = atr20 < atr30

    entry_level = o + float(entry_mult) * atr20
    stop_level = entry_level - float(stop_mult) * atr20
    signal = np.where(coiling & atr20.notna() & atr30.notna(), 1, 0).astype(int)

    out = work.copy()
    out["tr"] = tr
    out["atr20"] = atr20
    out["atr30"] = atr30
    out["coiling"] = coiling.fillna(False).astype(bool)
    out["entry_level"] = entry_level
    out["stop_level"] = stop_level
    out["signal"] = signal
    out.attrs["schema"] = SCHEMA
    out.attrs["lab_only"] = LAB_ONLY
    out.attrs["knobs"] = {
        "atr_fast": atr_fast,
        "atr_slow": atr_slow,
        "entry_mult": entry_mult,
        "stop_mult": stop_mult,
        "atr_mode": "sma_tr",
    }
    return out


def latest_setup(df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """Last-bar setup dict for shadow logs; None if no rows or invalid."""
    if df is None or len(df) == 0:
        return None
    sig = generate_signals(df)
    row = sig.iloc[-1]
    return {
        "schema": SCHEMA,
        "lab_only": LAB_ONLY,
        "signal": int(row["signal"]),
        "coiling": bool(row["coiling"]),
        "atr20": float(row["atr20"]) if pd.notna(row["atr20"]) else None,
        "atr30": float(row["atr30"]) if pd.notna(row["atr30"]) else None,
        "entry_level": float(row["entry_level"]) if pd.notna(row["entry_level"]) else None,
        "stop_level": float(row["stop_level"]) if pd.notna(row["stop_level"]) else None,
        "knobs": dict(sig.attrs.get("knobs") or {}),
        "note": "LAB ONLY — place_buy_stop not called from this module",
    }


def plain_english_parked() -> str:
    return (
        "ATR coil buy-stop breakout is PARKED (lab seed). "
        "Coil=ATR20<ATR30; entry=open+2.5*ATR20 stop-entry; stop=0.5*ATR20. "
        "Not live. See docs/plans/2026-09-17-atr-coil-buystop-breakout-lab.md"
    )
