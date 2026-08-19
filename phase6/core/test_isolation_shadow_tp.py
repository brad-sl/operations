#!/usr/bin/env python3
"""Isolation: shadow TP evaluator — no live orders."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def test_fixed_tp_and_trail():
    from phase6.core import shadow_tp as st

    marks = st.marks_from_holdings(
        {"LINK-USD": 1000.0},
        {"LINK-USD": 11.0},
        positions={"LINK-USD": {"entry_price": 10.0, "entry_basis": "test_fixture"}},
    )
    assert len(marks) == 1
    assert abs(marks[0].r - 0.10) < 1e-9

    cfg = {
        "take_profit": {
            "mode": "shadow",
            "fixed_tp_pct": 0.06,
            "trail": {"enabled": True, "arm_pct": 0.04, "trail_pct": 0.02, "breakeven_lock_pct": 0.005},
            "min_position_usd": 25,
            "notify_on_would_fire": False,
        }
    }
    # peak high then pull back → trail fire
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        # redirect state paths
        st.STATE_PATH = td / "status.json"
        st.EVENTS_PATH = td / "events.jsonl"
        st.DEDUPE_PATH = td / "dedupe.json"

        # first mark high
        r1 = st.run_shadow_tp_cycle(
            {"SOL-USD": 500.0},
            {"SOL-USD": 108.0},
            positions={"SOL-USD": {"entry_price": 100.0, "entry_basis": "test_fixture"}},
            cfg=cfg,
            notify=False,
        )
        assert r1["mode"] == "shadow"
        # r=8% → fixed_tp fires
        kinds = {s["kind"] for s in r1["signals"]}
        assert "fixed_tp" in kinds

        # peak then drop below trail stop
        r2 = st.run_shadow_tp_cycle(
            {"SOL-USD": 500.0},
            {"SOL-USD": 105.0},  # r=5%, peak was 8%, stop = max(0.08-0.02, 0.005)=0.06 → 5%<6% trail
            positions={"SOL-USD": {"entry_price": 100.0, "entry_basis": "test_fixture"}},
            cfg=cfg,
            notify=False,
            prior_state=r1,
        )
        kinds2 = {s["kind"] for s in r2["signals"]}
        assert "trail" in kinds2, kinds2
        assert r2["peak_r"].get("SOL-USD", 0) >= 0.08 - 1e-9


def test_live_buy_tp_only_when_mode_live():
    from phase6.core.shadow_tp import effective_tp_pct_for_buy

    assert effective_tp_pct_for_buy({"take_profit": {"mode": "shadow", "fixed_tp_pct": 0.06, "live_attach_on_buy": True}}) is None
    assert effective_tp_pct_for_buy({"take_profit": {"mode": "live", "fixed_tp_pct": 0.06, "live_attach_on_buy": False}}) is None
    assert effective_tp_pct_for_buy({"take_profit": {"mode": "live", "fixed_tp_pct": 0.06, "live_attach_on_buy": True}}) == 0.06


def test_off_mode():
    from phase6.core import shadow_tp as st

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        st.STATE_PATH = td / "s.json"
        st.EVENTS_PATH = td / "e.jsonl"
        r = st.run_shadow_tp_cycle(
            {"LINK-USD": 1000},
            {"LINK-USD": 20},
            positions={"LINK-USD": {"entry_price": 10, "entry_basis": "test_fixture"}},
            cfg={"take_profit": {"mode": "off"}},
            notify=False,
        )
        assert r["mode"] == "off"
        assert r["n_signals"] == 0


def test_filter_junk_and_live_state_fallback(tmp_path=None):
    """Runner holdings that only contain 'verified' must fall back to live_state pairs."""
    from phase6.core import shadow_tp as st

    # unit: junk filter
    cleaned = st._filter_junk_held({"verified": 1.0, "USD": 100.0, "BTC-USD": 500.0})
    assert cleaned == {"BTC-USD": 500.0}, cleaned

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        held: dict = {}
        prices: dict = {}
        positions: dict = {}
        st._ingest_position_row(
            "BTC-USD",
            {
                "value_usd": 1000.0,
                "entry_price": 100.0,
                "unrealized_pnl_pct": 0.10,
                "entry_basis": "test_fixture",
            },
            held,
            prices,
            positions,
        )
        assert held["BTC-USD"] == 1000.0
        assert abs(prices["BTC-USD"] - 110.0) < 1e-9
        st.STATE_PATH = td / "status.json"
        st.EVENTS_PATH = td / "events.jsonl"
        st.DEDUPE_PATH = td / "dedupe.json"
        r = st.run_shadow_tp_cycle(
            held,
            prices,
            positions=positions,
            cfg={
                "take_profit": {
                    "mode": "shadow",
                    "fixed_tp_pct": 0.06,
                    "trail": {"enabled": False},
                    "min_position_usd": 25,
                    "notify_on_would_fire": False,
                }
            },
            notify=False,
        )
        assert any(m["pair"] == "BTC-USD" for m in r["marks"]), r["marks"]
        assert any(s["kind"] == "fixed_tp" for s in r["signals"]), r["signals"]


def test_btc_shadow_r_uses_lot_not_lifetime():
    """If live BTC still has lying ~43k entry without basis tag, shadow uses ledger lot."""
    from phase6.core import shadow_tp as st

    live_path = Path("data/state/phase6_live_state.json")
    if not live_path.exists():
        print("SKIP no live_state")
        return
    live = json.loads(live_path.read_text())
    btc = next((p for p in (live.get("positions") or []) if p.get("pair") == "BTC-USD"), None)
    if not btc:
        print("SKIP no BTC")
        return
    pos = {
        "pair": "BTC-USD",
        "amount": float(btc.get("amount") or 0),
        "entry_price": 43264.0,  # lying lifetime avg
        "value_usd": float(btc.get("value_usd") or 1000),
        "current_price": float(btc.get("current_price") or 65000),
    }
    entry, src = st.resolve_entry("BTC-USD", pos, qty=pos["amount"])
    assert entry is not None
    assert entry > 55000, (entry, src)
    assert ("ledger" in src) or ("lifo" in src) or ("last_buy" in src), src
    r = (pos["current_price"] - entry) / entry
    assert r < 0.15, (r, entry, src)
    print(f"shadow BTC resolve OK entry={entry} r={r:.4f} src={src}")


if __name__ == "__main__":
    test_fixed_tp_and_trail()
    test_live_buy_tp_only_when_mode_live()
    test_off_mode()
    test_filter_junk_and_live_state_fallback()
    test_btc_shadow_r_uses_lot_not_lifetime()
    print("shadow_tp isolation PASS")
