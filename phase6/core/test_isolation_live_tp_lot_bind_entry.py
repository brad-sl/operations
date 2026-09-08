#!/usr/bin/env python3
"""Isolation: live TP fail-closed unless entry is lot-bound (C). LINK 2026-09-07 class."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _live_cfg():
    return {
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
            "brad_promoted_at": "2026-09-07T00:00:00Z",
        }
    }


def test_entry_source_trusted_helper() -> None:
    from phase6.core.shadow_tp import entry_source_trusted_for_live

    assert entry_source_trusted_for_live("ledger_avg_cost") is True
    assert entry_source_trusted_for_live("position.entry_price+test_fixture") is True
    assert entry_source_trusted_for_live("position.entry_price+ledger_avg_cost") is True
    assert entry_source_trusted_for_live("last_buy_flat") is False
    assert entry_source_trusted_for_live("ledger_flat_exchange_open") is False
    assert entry_source_trusted_for_live("ledger_lifo_exchange_qty") is False
    assert entry_source_trusted_for_live("ledger_last_buy") is False
    assert entry_source_trusted_for_live("unknown") is False
    assert entry_source_trusted_for_live("position.entry_price") is False


def test_untrusted_entry_no_live_exit() -> None:
    """Phantom last_buy / lifo basis must not live-execute even if mark looks +8%."""
    from phase6.core import shadow_tp as st

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        st.STATE_PATH = td / "status.json"
        st.EVENTS_PATH = td / "events.jsonl"
        st.DEDUPE_PATH = td / "dedupe.json"
        st.LIVE_EXITS_PATH = td / "live.jsonl"
        st.TRADES_PATH = td / "no_trades.jsonl"
        st.REGISTRY_PATH = td / "no_reg.jsonl"

        # Force untrusted basis via position stamp (simulates bad enrich)
        r = st.run_shadow_tp_cycle(
            {"LINK-USD": 75.0},
            {"LINK-USD": 12.65},  # mark
            positions={
                "LINK-USD": {
                    "entry_price": 11.641,  # ghost lot → fake +8.7%
                    "entry_basis": "last_buy_flat",
                    "amount": 5.92,
                }
            },
            cfg=_live_cfg(),
            notify=False,
            exchange=MagicMock(),
            dry_run_live=True,
            prior_state={"live_peak_seeded_for": "2026-09-07T00:00:00Z"},
        )
        live_ex = r.get("live_exits") or []
        # dry_run still "executes" candidates — gate must remove candidates first
        cands = r.get("live_exit_candidates") or []
        assert not cands, f"untrusted entry must block live candidates: {cands}"
        assert not any(x.get("success") for x in live_ex if not x.get("blocked")), live_ex
        # May still surface shadow signals for observability, but tagged/blocked
        blocked = r.get("live_exit_blocked") or []
        assert blocked or not cands


def test_trusted_fill_lot_may_fire_fixed_tp() -> None:
    from phase6.core import shadow_tp as st

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        st.STATE_PATH = td / "status.json"
        st.EVENTS_PATH = td / "events.jsonl"
        st.DEDUPE_PATH = td / "dedupe.json"
        st.LIVE_EXITS_PATH = td / "live.jsonl"
        st.TRADES_PATH = td / "no_trades.jsonl"
        st.REGISTRY_PATH = td / "no_reg.jsonl"

        entry = 12.658
        mark = entry * 1.061  # +6.1% → fixed_tp
        r = st.run_shadow_tp_cycle(
            {"LINK-USD": 75.0},
            {"LINK-USD": mark},
            positions={
                "LINK-USD": {
                    "entry_price": entry,
                    "entry_basis": "test_fixture",
                    "amount": 5.92,
                }
            },
            cfg=_live_cfg(),
            notify=False,
            exchange=MagicMock(),
            dry_run_live=True,
            prior_state={"live_peak_seeded_for": "2026-09-07T00:00:00Z"},
        )
        kinds = {s.get("kind") for s in (r.get("live_exit_candidates") or [])}
        assert "fixed_tp" in kinds, r.get("live_exit_candidates")


def test_lifo_mismatch_source_blocked() -> None:
    from phase6.core import shadow_tp as st

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        st.STATE_PATH = td / "status.json"
        st.EVENTS_PATH = td / "events.jsonl"
        st.DEDUPE_PATH = td / "dedupe.json"
        st.LIVE_EXITS_PATH = td / "live.jsonl"

        r = st.run_shadow_tp_cycle(
            {"LINK-USD": 75.0},
            {"LINK-USD": 12.65},
            positions={
                "LINK-USD": {
                    "entry_price": 11.641,
                    "entry_basis": "ledger_lifo_exchange_qty",
                    "amount": 5.92,
                }
            },
            cfg=_live_cfg(),
            notify=False,
            exchange=MagicMock(),
            dry_run_live=True,
            prior_state={"live_peak_seeded_for": "2026-09-07T00:00:00Z"},
        )
        assert not (r.get("live_exit_candidates") or []), r.get("live_exit_candidates")


def test_uni_peak_lot_regression_still_holds() -> None:
    """Peak-lot bind still resets on new entry (UNI 2026-08-23 class)."""
    from phase6.core import shadow_tp as st

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        st.STATE_PATH = td / "status.json"
        st.EVENTS_PATH = td / "events.jsonl"
        st.DEDUPE_PATH = td / "dedupe.json"
        st.LIVE_EXITS_PATH = td / "live.jsonl"

        prior = {
            "peak_r": {"UNI-USD": 0.1123},
            "live_peak_seeded_for": "2026-09-07T00:00:00Z",
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


if __name__ == "__main__":
    test_entry_source_trusted_helper()
    test_untrusted_entry_no_live_exit()
    test_trusted_fill_lot_may_fire_fixed_tp()
    test_lifo_mismatch_source_blocked()
    test_uni_peak_lot_regression_still_holds()
    print("live tp lot bind entry isolation PASS")
