#!/usr/bin/env python3
"""Isolation tests for regime_arm_switch — synthetic BTC closes, no network."""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import phase6.core.regime_arm_switch as m  # noqa: E402


def _setup_tmp(tmp: Path) -> None:
    m.STATE_DIR = tmp / "state"
    m.OHLCV_DIR = tmp / "ohlcv"
    m.STATE_DIR.mkdir(parents=True, exist_ok=True)
    m.OHLCV_DIR.mkdir(parents=True, exist_ok=True)
    m.BRAD_DECISION_JSON = m.STATE_DIR / "basket_swap_brad_decision.json"
    m.SWITCH_LATEST = m.STATE_DIR / "regime_arm_switch_latest.json"
    m.SWITCH_JSONL = m.STATE_DIR / "regime_arm_switch_crumbs.jsonl"
    m.BTC_CACHE = m.OHLCV_DIR / "BTC-USD_1d_coinbase.json"
    m.REPORT_MD = tmp / "reports" / "REGIME_ARM_SWITCH_LATEST.md"
    m.REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    # seed decision
    m.BRAD_DECISION_JSON.write_text(
        json.dumps(
            {
                "schema": "basket_swap_brad_decision_v1",
                "preferred_arm": "rel_btc_stable",
                "previous_preferred_arm": "risk_adj_mom",
                "live_membership_swaps": False,
                "live_apply": False,
            },
            indent=2,
        )
    )


def test_classify_raw():
    assert m.classify_raw_tape(3.0) == "btc_up"
    assert m.classify_raw_tape(-3.0) == "btc_down"
    assert m.classify_raw_tape(0.5) == "btc_chop"
    assert m.classify_raw_tape(None) == "unknown"
    print("PASS classify_raw")


def test_hysteresis_hold_up():
    # was up; ret now 1.0 (below enter_up 2 but above exit_up 0.5) → stay up
    sticky = m.apply_hysteresis("btc_chop", "btc_up", 1.0)
    assert sticky == "btc_up", sticky
    # drop below exit → reclassify chop
    sticky2 = m.apply_hysteresis("btc_chop", "btc_up", 0.0)
    assert sticky2 == "btc_chop", sticky2
    print("PASS hysteresis_hold_up")


def test_hysteresis_hold_down():
    sticky = m.apply_hysteresis("btc_chop", "btc_down", -1.0)
    assert sticky == "btc_down", sticky
    sticky2 = m.apply_hysteresis("btc_chop", "btc_down", 0.0)
    assert sticky2 == "btc_chop", sticky2
    print("PASS hysteresis_hold_down")


def test_arm_map():
    assert m.arm_for_tape("btc_up") == "rel_btc_stable"
    assert m.arm_for_tape("btc_chop") == "rel_btc_stable"
    assert m.arm_for_tape("btc_down") == "risk_adj_mom"
    print("PASS arm_map")


def test_down_tape_flips_to_ram():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _setup_tmp(tmp)
        # 8 days: flat then crash ~5% over last 7d
        closes = [100.0] * 8
        # day0=100 ... day7: walk down so 7d ret from day0 to day7 = -5%
        closes = [100.0, 100.0, 99.0, 98.0, 97.0, 96.0, 95.5, 95.0]
        candles = m.synthetic_candles_from_closes(closes, start_day="2026-08-01")
        snap = m.compute_snapshot(
            candles=candles,
            prev_state={},
            min_dwell_hours=0.0,
            use_network=False,
        )
        assert snap.btc_ret_7d_pct is not None
        assert snap.btc_ret_7d_pct < -2.0, snap
        assert snap.sticky_tape == "btc_down", snap
        assert snap.preferred_arm == "risk_adj_mom", snap
        res = m.apply_to_decision(snap, mode="shadow", apply=True)
        assert res["decision_written"] is True
        brad = json.loads(m.BRAD_DECISION_JSON.read_text())
        assert brad["preferred_arm"] == "risk_adj_mom"
        assert brad["live_membership_swaps"] is False
        assert brad["live_apply"] is False
        assert brad["previous_preferred_arm"] == "rel_btc_stable"
        print("PASS down_tape_flips_to_ram", snap.btc_ret_7d_pct)


def test_up_tape_stays_rel():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _setup_tmp(tmp)
        # strong up 7d
        closes = [100.0 + i * 1.0 for i in range(10)]  # +9% over 9 days
        candles = m.synthetic_candles_from_closes(closes)
        snap = m.compute_snapshot(
            candles=candles, prev_state={}, min_dwell_hours=0.0, use_network=False
        )
        assert snap.sticky_tape == "btc_up", snap
        assert snap.preferred_arm == "rel_btc_stable"
        res = m.apply_to_decision(snap, mode="production", apply=True)
        brad = json.loads(m.BRAD_DECISION_JSON.read_text())
        assert brad["preferred_arm"] == "rel_btc_stable"
        assert brad["live_membership_swaps"] is False
        assert res["mode"] == "production"
        print("PASS up_tape_stays_rel", snap.btc_ret_7d_pct)


def test_dwell_blocks_flip():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _setup_tmp(tmp)
        # state says we just flipped
        m.SWITCH_LATEST.write_text(
            json.dumps(
                {
                    "sticky_tape": "btc_up",
                    "preferred_arm": "rel_btc_stable",
                    "last_flip_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        )
        # crash series → would want ram
        closes = [100.0, 99, 98, 97, 96, 95, 94, 93]
        candles = m.synthetic_candles_from_closes(closes)
        snap = m.compute_snapshot(
            candles=candles,
            prev_state=json.loads(m.SWITCH_LATEST.read_text()),
            min_dwell_hours=24.0,
            use_network=False,
        )
        assert snap.dwell_blocked is True, snap
        assert snap.preferred_arm == "rel_btc_stable", snap
        print("PASS dwell_blocks_flip")


def test_force_live_refused():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _setup_tmp(tmp)
        closes = [100.0] * 10
        candles = m.synthetic_candles_from_closes(closes)
        snap = m.compute_snapshot(
            candles=candles, prev_state={}, min_dwell_hours=0.0, use_network=False
        )
        res = m.apply_to_decision(
            snap, mode="production", apply=True, force_live_swaps=True
        )
        brad = json.loads(m.BRAD_DECISION_JSON.read_text())
        assert brad["live_membership_swaps"] is False
        assert "refused" in (res.get("note") or "").lower()
        print("PASS force_live_refused")


def test_dry_run_no_write():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _setup_tmp(tmp)
        before = m.BRAD_DECISION_JSON.read_text()
        closes = [100.0, 99, 98, 97, 96, 95, 94, 90]
        candles = m.synthetic_candles_from_closes(closes)
        snap = m.compute_snapshot(
            candles=candles, prev_state={}, min_dwell_hours=0.0, use_network=False
        )
        res = m.apply_to_decision(snap, mode="shadow", apply=False)
        assert res["decision_written"] is False
        assert m.BRAD_DECISION_JSON.read_text() == before
        assert m.SWITCH_LATEST.exists()
        print("PASS dry_run_no_write")


def main() -> int:
    test_classify_raw()
    test_hysteresis_hold_up()
    test_hysteresis_hold_down()
    test_arm_map()
    test_down_tape_flips_to_ram()
    test_up_tape_stays_rel()
    test_dwell_blocks_flip()
    test_force_live_refused()
    test_dry_run_no_write()
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
