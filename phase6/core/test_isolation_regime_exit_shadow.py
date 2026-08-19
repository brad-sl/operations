#!/usr/bin/env python3
"""Isolation: regime exit policy map shadow — no orders, regime knobs apply."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from phase6.core import regime_exit_shadow as rex
    from phase6.core.shadow_tp import PositionMark

    # temp paths
    td = Path(tempfile.mkdtemp(prefix="rex_iso_"))
    rex.STATE_PATH = td / "status.json"
    rex.EVENTS_PATH = td / "events.jsonl"
    rex.DEDUPE_PATH = td / "dedupe.json"
    rex.COLLECTION_PATH = td / "collection.json"
    rex.MAP_PATH = td / "map.json"
    rex.REGIME_STATUS = td / "regime.json"

    mmap = {
        "schema": "regime_exit_policy_map_v1",
        "mode": "shadow",
        "live_apply": False,
        "enabled": True,
        "min_position_usd": 25.0,
        "notify_on_would_fire": False,
        "regimes": {
            "flat": {
                "label": "flat test",
                "fixed_tp": {"enabled": True, "pct": 0.05},
                "trail": {"enabled": True, "arm_pct": 0.04, "trail_pct": 0.02, "breakeven_lock_pct": 0.005},
                "rsi_hard_exit": {"enabled": True, "overbought": 65.0},
            },
            "bear": {
                "label": "bear test",
                "fixed_tp": {"enabled": False, "pct": None},
                "trail": {"enabled": False},
                "rsi_hard_exit": {"enabled": False, "overbought": None},
            },
        },
        "promotion": {
            "auto_promote": False,
            "shadow_min_calendar_days": 60,
            "min_would_fire_episodes_per_regime": 5,
            "min_closed_legs_per_regime": 15,
            "regimes_required_for_global_flip": ["bull", "bear", "flat"],
            "min_regimes_ready": 3,
        },
    }
    rex.MAP_PATH.write_text(json.dumps(mmap), encoding="utf-8")
    rex.REGIME_STATUS.write_text(json.dumps({"regime": "flat", "btc_return_pct": 2.0}), encoding="utf-8")

    held = {"LINK-USD": 100.0, "BTC-USD": 200.0}
    prices = {"LINK-USD": 10.0, "BTC-USD": 100.0}
    # LINK up 6% -> TP 5% fires; BTC flat
    positions = {
        "LINK-USD": {"entry_price": 10.0 / 1.06, "qty": 10.0},
        "BTC-USD": {"entry_price": 100.0, "qty": 2.0},
    }
    rsi = {"LINK-USD": 70.0, "BTC-USD": 50.0}

    r1 = rex.run_regime_exit_shadow_cycle(
        held, prices, positions=positions, rsi_by_pair=rsi, mmap=mmap, notify=False
    )
    assert r1["regime"] == "flat", r1
    assert r1["live_apply"] is False
    assert r1["orders_placed"] is False
    kinds = {s["kind"] for s in r1["signals"]}
    assert "fixed_tp" in kinds, r1["signals"]
    assert "rsi_hard_exit" in kinds, r1["signals"]
    assert r1["n_new_episodes"] >= 1
    assert r1["promotion"]["ready_for_settings_flip_review"] is False
    assert r1["promotion"]["auto_promote"] is False

    # bear: no TP/RSI fires even if green + high RSI
    rex.REGIME_STATUS.write_text(json.dumps({"regime": "bear", "btc_return_pct": -12.0}), encoding="utf-8")
    r2 = rex.run_regime_exit_shadow_cycle(
        held, prices, positions=positions, rsi_by_pair=rsi, mmap=mmap, notify=False
    )
    assert r2["regime"] == "bear"
    assert r2["n_signals"] == 0, r2["signals"]

    # live_apply forced off
    mmap2 = dict(mmap)
    mmap2["mode"] = "live"
    mmap2["live_apply"] = True
    r3 = rex.run_regime_exit_shadow_cycle(
        held, prices, positions=positions, rsi_by_pair=rsi, mmap=mmap2, notify=False
    )
    assert r3["live_apply"] is False
    assert r3["mode"] == "shadow"

    # episode dedupe: second cycle same signals <30m → 0 new episodes, no re-notify
    rex.REGIME_STATUS.write_text(json.dumps({"regime": "flat", "btc_return_pct": 2.0}), encoding="utf-8")
    r4 = rex.run_regime_exit_shadow_cycle(
        held, prices, positions=positions, rsi_by_pair=rsi, mmap=mmap, notify=True
    )
    assert r4["n_new_episodes"] == 0, r4
    assert r4.get("notified") in (False, None)
    assert r4.get("notify_suppressed") == "ongoing_episode_no_reping"

    # stable fingerprint ignores r jitter
    fp_a = rex._fingerprint(
        [
            rex.MapSignal(
                pair="LINK-USD",
                kind="rsi_hard_exit",
                regime="flat",
                r=0.008,
                entry_px=1.0,
                mark_px=1.0,
                usd=50,
                detail="x",
                would_exit_usd=50,
                knobs={},
            )
        ],
        "flat",
    )
    fp_b = rex._fingerprint(
        [
            rex.MapSignal(
                pair="LINK-USD",
                kind="rsi_hard_exit",
                regime="flat",
                r=0.012,
                entry_px=1.0,
                mark_px=1.0,
                usd=50,
                detail="x",
                would_exit_usd=50,
                knobs={},
            )
        ],
        "flat",
    )
    assert fp_a == fp_b, (fp_a, fp_b)

    print("regime_exit_shadow isolation PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
