#!/usr/bin/env python3
"""Refresh scenario pack date_range.end from OHLCV manifest / BTC file."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data/state/ohlcv_extension_manifest.json"
PACKS = [
    ROOT / "phase6/research/scenarios/r1_arch4_smoke_three.json",
    ROOT / "phase6/research/scenarios/regime_quad_template.json",
]


def resolve_data_end() -> str | None:
    if MANIFEST.exists():
        m = json.loads(MANIFEST.read_text())
        if m.get("data_end"):
            return m["data_end"]
    btc = ROOT / "backtests/data/backtest_historical_ohlcv_btc_2025-04-20_to_2026-04-20.json"
    if btc.exists():
        data = json.loads(btc.read_text())
        if data:
            return data[-1]["timestamp"][:10]
    return None


def main() -> int:
    end = resolve_data_end()
    if not end:
        print("no data_end")
        return 1

    for path in PACKS:
        pack = json.loads(path.read_text())
        pack.setdefault("date_range", {})["end"] = end
        for rw in pack.get("regime_windows") or []:
            if rw.get("regime") == "recent":
                rw.setdefault("date_range", {})["end"] = end
        path.write_text(json.dumps(pack, indent=2))
        print(f"updated {path.name} date end -> {end}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())