#!/usr/bin/env python3
"""Isolation: bear profit-take ladder shadow — no orders."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from phase6.core import bear_profit_take_shadow as bpt

    td = Path(tempfile.mkdtemp(prefix="bpt_iso_"))
    bpt.STATE_PATH = td / "status.json"
    bpt.EVENTS_PATH = td / "events.jsonl"
    bpt.FILLED_PATH = td / "filled.json"
    bpt.REGIME_STATUS = td / "regime.json"
    bpt.CFG_PATH = td / "cfg.json"
    # reports path still under project — OK for latest md

    cfg = {
        "schema": "bear_profit_take_v1",
        "mode": "shadow",
        "live_apply": False,
        "enabled": True,
        "active_regimes": ["bear"],
        "min_position_usd": 25.0,
        "ladder": {
            "enabled": True,
            "tranches": [
                {"level": 1, "r_pct": 0.03, "sell_frac": 0.25, "label": "first_slice"},
                {"level": 2, "r_pct": 0.05, "sell_frac": 0.25, "label": "second_slice"},
                {"level": 3, "r_pct": 0.08, "sell_frac": 0.25, "label": "third_slice"},
            ],
            "leave_moon_bag_frac": 0.25,
        },
        "limit_tp_levels": {"enabled": True},
        "proceeds_destination": "stables",
        "rebuy_block_hours_after_tp": 72,
        "episode_gap_minutes": 30,
        "promotion": {"auto_promote": False},
        "exclude": ["loans", "shorting"],
    }
    bpt.CFG_PATH.write_text(json.dumps(cfg), encoding="utf-8")

    held = {"LINK-USD": 100.0, "BTC-USD": 200.0}
    # LINK +6% from entry → levels 1 and 2; BTC flat
    prices = {"LINK-USD": 10.6, "BTC-USD": 100.0}
    positions = {
        "LINK-USD": {"entry_price": 10.0},
        "BTC-USD": {"entry_price": 100.0},
    }

    # non-bear → idle
    r0 = bpt.run_bear_profit_take_cycle(
        held,
        prices,
        positions=positions,
        cfg=cfg,
        force_regime="transition",
        persist_fills=True,
    )
    assert r0["status"] == "idle_wrong_regime", r0
    assert r0["orders_placed"] is False
    assert r0["n_new_episodes"] == 0
    assert "standby" in (r0.get("plain_english") or "").lower() or "not bear" in (
        r0.get("plain_english") or ""
    ).lower()

    # bear + green LINK → ladder episodes
    r1 = bpt.run_bear_profit_take_cycle(
        held,
        prices,
        positions=positions,
        cfg=cfg,
        force_regime="bear",
        persist_fills=True,
    )
    assert r1["regime"] == "bear"
    assert r1["live_apply"] is False
    assert r1["orders_placed"] is False
    assert r1["mode"] == "shadow"
    assert r1["n_new_episodes"] >= 1, r1
    ladder = [e for e in r1["new_episodes"] if e.get("kind") == "ladder_scale_out"]
    assert ladder, r1
    levels = {int(e["level"]) for e in ladder}
    assert 1 in levels and 2 in levels, levels  # +6% clears 3% and 5%
    assert 3 not in levels  # 8% not hit
    assert r1.get("messages", {}).get("no_ai") is True
    assert "short" not in (r1.get("plain_english") or "").lower() or "not a short" in (
        r1.get("plain_english") or ""
    ).lower()

    # second cycle same book → no re-fire (filled ledger + episode gap)
    r2 = bpt.run_bear_profit_take_cycle(
        held,
        prices,
        positions=positions,
        cfg=cfg,
        force_regime="bear",
        persist_fills=True,
    )
    assert r2["n_new_episodes"] == 0, r2

    # live_apply forced off even if cfg lies
    cfg_live = dict(cfg)
    cfg_live["mode"] = "live"
    cfg_live["live_apply"] = True
    # reset filled so we can see signals still shadow
    bpt.FILLED_PATH.write_text(json.dumps({"filled": {}}), encoding="utf-8")
    if bpt.EVENTS_PATH.exists():
        bpt.EVENTS_PATH.write_text("", encoding="utf-8")
    r3 = bpt.run_bear_profit_take_cycle(
        held,
        prices,
        positions=positions,
        cfg=cfg_live,
        force_regime="bear",
        persist_fills=False,
    )
    assert r3["live_apply"] is False
    assert r3["mode"] == "shadow"
    assert r3["orders_placed"] is False

    # pure evaluate_ladder unit
    sigs = bpt.evaluate_ladder(
        held_usd=held,
        prices=prices,
        positions=positions,
        cfg=cfg,
        filled={},
    )
    assert any(s.kind == "ladder_scale_out" and s.pair == "LINK-USD" for s in sigs)

    print("bear_profit_take_shadow isolation PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
