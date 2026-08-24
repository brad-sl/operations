#!/usr/bin/env python3
"""Isolation: live TP trail-primary + fixed fallback + PAXG exclude + post-TP block."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def test_select_trail_primary_over_fixed():
    from phase6.core.shadow_tp import ShadowSignal, select_live_exit_signals, is_tp_excluded_pair

    assert is_tp_excluded_pair("PAXG-USD") is True
    assert is_tp_excluded_pair("LINK-USD") is False

    sigs = [
        ShadowSignal("LINK-USD", "fixed_tp", 0.07, 10.0, 10.7, 1000, "fixed", 1000),
        ShadowSignal("LINK-USD", "trail", 0.05, 10.0, 10.5, 1000, "trail", 1000),
        ShadowSignal("PAXG-USD", "fixed_tp", 0.10, 3000, 3300, 80, "gold", 80),
        ShadowSignal("SOL-USD", "fixed_tp", 0.08, 100, 108, 500, "fixed only", 500),
    ]
    chosen = select_live_exit_signals(sigs)
    by = {s.pair: s.kind for s in chosen}
    assert by["LINK-USD"] == "trail", by
    assert by["SOL-USD"] == "fixed_tp", by
    assert "PAXG-USD" not in by


def test_dry_run_live_exit_no_order():
    from phase6.core import shadow_tp as st

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        st.STATE_PATH = td / "status.json"
        st.EVENTS_PATH = td / "events.jsonl"
        st.DEDUPE_PATH = td / "dedupe.json"
        st.LIVE_EXITS_PATH = td / "live.jsonl"

        # Peak then pullback → trail
        r1 = st.run_shadow_tp_cycle(
            {"SOL-USD": 500.0},
            {"SOL-USD": 108.0},
            positions={"SOL-USD": {"entry_price": 100.0, "entry_basis": "test_fixture"}},
            cfg={
                "take_profit": {
                    "mode": "live",
                    "fixed_tp_pct": 0.06,
                    "trail": {
                        "enabled": True,
                        "arm_pct": 0.04,
                        "trail_pct": 0.02,
                        "breakeven_lock_pct": 0.005,
                    },
                    "min_position_usd": 25,
                    "live_market_exit": True,
                    "live_attach_on_buy": False,
                    "notify_on_would_fire": False,
                }
            },
            notify=False,
            exchange=MagicMock(),
            dry_run_live=True,
        )
        assert r1["mode"] == "live"
        # r=8% → fixed fires; dry run may exit on fixed
        r2 = st.run_shadow_tp_cycle(
            {"SOL-USD": 500.0},
            {"SOL-USD": 105.0},
            positions={"SOL-USD": {"entry_price": 100.0, "entry_basis": "test_fixture"}},
            cfg={
                "take_profit": {
                    "mode": "live",
                    "fixed_tp_pct": 0.06,
                    "trail": {
                        "enabled": True,
                        "arm_pct": 0.04,
                        "trail_pct": 0.02,
                        "breakeven_lock_pct": 0.005,
                    },
                    "min_position_usd": 25,
                    "live_market_exit": True,
                    "live_attach_on_buy": False,
                    "notify_on_would_fire": False,
                }
            },
            notify=False,
            prior_state=r1,
            exchange=MagicMock(),
            dry_run_live=True,
        )
        kinds = {s["kind"] for s in r2.get("live_exit_candidates") or []}
        assert "trail" in kinds or any(
            x.get("kind") == "trail" for x in (r2.get("live_exits") or [])
        ), r2
        for x in r2.get("live_exits") or []:
            assert x.get("dry_run") is True
            assert x.get("order_id") is None


def test_post_tp_block_from_ledger():
    from phase6.core import runner_capital_events as rce
    from datetime import datetime, timezone, timedelta
    from unittest.mock import patch

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        ledger = td / "trades.jsonl"
        state = td / "runner_state.json"
        state.write_text("{}")
        ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        row = {
            "timestamp": ts,
            "pair": "LINK-USD",
            "side": "SELL",
            "reason": "take_profit_trail",
            "qty": 10,
            "exit_price": 12.0,
        }
        ledger.write_text(json.dumps(row) + "\n")
        # Isolate from live capital_user_controls / multi-account store
        with patch.object(rce, "DEFAULT_STATE_FILE", state), patch.object(
            rce, "STATE_DIR", td
        ), patch(
            "phase6.core.capital_controls_store.load_for_runner",
            return_value={},
        ), patch(
            "phase6.core.capital_controls_store.load_account_capital_state",
            return_value={},
        ):
            blocks = rce.load_buy_block_status(
                hours=72, jsonl_path=ledger, state_file=state
            )
        assert "LINK-USD" in blocks, blocks
        assert blocks["LINK-USD"]["reason"] == "post_tp_rebuy_block"
        assert blocks["LINK-USD"]["block_hours"] == 24.0


def _live_cfg(**extra):
    cfg = {
        "take_profit": {
            "mode": "live",
            "fixed_tp_pct": 0.06,
            "trail": {
                "enabled": True,
                "arm_pct": 0.04,
                "trail_pct": 0.02,
                "breakeven_lock_pct": 0.005,
            },
            "min_position_usd": 25,
            "live_market_exit": True,
            "live_attach_on_buy": False,
            "notify_on_would_fire": False,
            "brad_promoted_at": "2026-08-23T05:30:00Z",
        }
    }
    cfg["take_profit"].update(extra)
    return cfg


def test_uni_stale_peak_does_not_fire_trail_on_fresh_lot():
    """Regression: 2026-08-23 UNI rebal buy then phantom trail sell ~90s later."""
    from phase6.core import shadow_tp as st

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        st.STATE_PATH = td / "status.json"
        st.EVENTS_PATH = td / "events.jsonl"
        st.DEDUPE_PATH = td / "dedupe.json"
        st.LIVE_EXITS_PATH = td / "live.jsonl"

        # Prior bag/promote left peak_r=+11.23% with no lot bind (or old lot).
        prior = {
            "peak_r": {"UNI-USD": 0.1123, "BTC-USD": 0.2092},
            "live_peak_seeded_for": "2026-08-23T05:30:00Z",
            "would_fire_count_total": 2,
        }
        r = st.run_shadow_tp_cycle(
            {"UNI-USD": 335.0},
            {"UNI-USD": 4.556},
            positions={
                "UNI-USD": {
                    "entry_price": 4.570063,
                    "entry_basis": "test_fixture",
                    "amount": 73.56,
                }
            },
            cfg=_live_cfg(),
            notify=False,
            prior_state=prior,
            exchange=None,
            dry_run_live=True,
        )
        kinds = {s["kind"] for s in (r.get("signals") or [])}
        assert "trail" not in kinds, r.get("signals")
        # Peak must collapse to current mark r (~-0.3%), not stay at 0.1123
        assert r["peak_r"]["UNI-USD"] < 0.01, r["peak_r"]
        assert "UNI-USD" in (r.get("peak_lot") or {}), r.get("peak_lot")
        assert any(
            e.get("action") == "reset_peak" for e in (r.get("peak_sanitize_events") or [])
        ), r.get("peak_sanitize_events")
        # Orphan BTC peak dropped (not held)
        assert "BTC-USD" not in r["peak_r"], r["peak_r"]


def test_same_lot_trail_still_fires_after_real_pullback():
    """Lot-bound peaks must still allow genuine trail exits."""
    from phase6.core import shadow_tp as st

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        st.STATE_PATH = td / "status.json"
        st.EVENTS_PATH = td / "events.jsonl"
        st.DEDUPE_PATH = td / "dedupe.json"
        st.LIVE_EXITS_PATH = td / "live.jsonl"

        r1 = st.run_shadow_tp_cycle(
            {"SOL-USD": 500.0},
            {"SOL-USD": 108.0},  # r=+8%
            positions={"SOL-USD": {"entry_price": 100.0, "entry_basis": "test_fixture"}},
            cfg=_live_cfg(),
            notify=False,
            prior_state={"live_peak_seeded_for": "2026-08-23T05:30:00Z"},
            exchange=None,
            dry_run_live=True,
        )
        assert r1["peak_r"].get("SOL-USD", 0) >= 0.08 - 1e-9
        lot = r1.get("peak_lot") or {}
        assert "SOL-USD" in lot

        r2 = st.run_shadow_tp_cycle(
            {"SOL-USD": 500.0},
            {"SOL-USD": 105.0},  # r=+5%; stop=max(0.08-0.02,0.005)=0.06 → trail
            positions={"SOL-USD": {"entry_price": 100.0, "entry_basis": "test_fixture"}},
            cfg=_live_cfg(),
            notify=False,
            prior_state=r1,
            exchange=None,
            dry_run_live=True,
        )
        kinds = {s["kind"] for s in (r2.get("signals") or [])}
        assert "trail" in kinds, r2.get("signals")
        assert r2["peak_r"]["SOL-USD"] >= 0.08 - 1e-9


def test_entry_change_resets_peak_even_with_lot_meta():
    from phase6.core import shadow_tp as st

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        st.STATE_PATH = td / "status.json"
        st.EVENTS_PATH = td / "events.jsonl"
        st.DEDUPE_PATH = td / "dedupe.json"
        st.LIVE_EXITS_PATH = td / "live.jsonl"

        prior = {
            "peak_r": {"UNI-USD": 0.12},
            "peak_lot": {
                "UNI-USD": {
                    "entry_px": 3.5954,  # old SL lot anchor
                    "qty": 21.0,
                    "entry_source": "old",
                }
            },
            "live_peak_seeded_for": "2026-08-23T05:30:00Z",
        }
        r = st.run_shadow_tp_cycle(
            {"UNI-USD": 335.0},
            {"UNI-USD": 4.556},
            positions={
                "UNI-USD": {
                    "entry_price": 4.570063,
                    "entry_basis": "test_fixture",
                    "amount": 73.56,
                }
            },
            cfg=_live_cfg(),
            notify=False,
            prior_state=prior,
            exchange=None,
            dry_run_live=True,
        )
        kinds = {s["kind"] for s in (r.get("signals") or [])}
        assert "trail" not in kinds, r.get("signals")
        assert r["peak_r"]["UNI-USD"] < 0.01
        assert abs(float(r["peak_lot"]["UNI-USD"]["entry_px"]) - 4.570063) < 1e-6


def main():
    test_select_trail_primary_over_fixed()
    test_dry_run_live_exit_no_order()
    test_post_tp_block_from_ledger()
    test_uni_stale_peak_does_not_fire_trail_on_fresh_lot()
    test_same_lot_trail_still_fires_after_real_pullback()
    test_entry_change_resets_peak_even_with_lot_meta()
    # existing shadow tests still pass
    from phase6.core.test_isolation_shadow_tp import (
        test_fixed_tp_and_trail,
        test_live_buy_tp_only_when_mode_live,
        test_off_mode,
    )

    test_fixed_tp_and_trail()
    test_live_buy_tp_only_when_mode_live()
    test_off_mode()
    print("live TP trail/fixed + post-TP block + lot-bound peaks OK")
    print("PASS")


if __name__ == "__main__":
    main()
