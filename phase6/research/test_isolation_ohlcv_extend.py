"""Verify OHLCV extension manifest and pack end dates."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data/state/ohlcv_extension_manifest.json"
PACK = ROOT / "phase6/research/scenarios/r1_arch4_smoke_three.json"


def main() -> int:
    assert MANIFEST.exists(), "run extend_backtest_ohlcv.py first"
    m = json.loads(MANIFEST.read_text())
    assert m.get("data_end"), m
    pack = json.loads(PACK.read_text())
    assert pack["date_range"]["end"] == m["data_end"]
    assert (ROOT / "data/state/analyst_regime_scorecard_latest.json").exists()
    print("OHLCV extend + scorecard artifacts OK data_end=", m["data_end"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())