"""Isolation tests for first-fill tryout sizing (no live orders)."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

from phase6.core.first_fill_probation import (
    DEFAULTS,
    FirstFillDecision,
    count_open_first_fill_seats,
    filter_trade_plan_first_fill,
    is_first_fill_candidate,
    size_first_fill,
    tag_promote_add,
)
from phase6.core.missfire_probation import PairMissfireStats


def _st(**kw: Any) -> PairMissfireStats:
    pair = str(kw.pop("pair", "X-USD"))
    base = dict(
        n_rt=0,
        n_sl=0,
        n_tp_or_rot=0,
        n_fast_hole=0,
        n_slow_hole=0,
        net_pnl=0.0,
        sl_rate=0.0,
        tp_rate=0.0,
        med_hold_h=None,
    )
    base.update(kw)
    return PairMissfireStats(pair=pair, **base)


def test_size_haircut_and_caps() -> None:
    dec = size_first_fill(pair="SKR-USD", proposed_usd=400.0, equity_usd=2300.0, cfg=DEFAULTS)
    assert dec.status == "haircut"
    # 400*0.4=160, abs_cap 150 → 150
    assert abs(dec.final_usd - 150.0) < 1e-6


def test_drop_below_min_move() -> None:
    cfg = dict(DEFAULTS)
    cfg["abs_cap_usd"] = 30.0
    cfg["min_move_usd"] = 40.0
    dec = size_first_fill(pair="SKR-USD", proposed_usd=50.0, equity_usd=2300.0, cfg=cfg)
    assert dec.status == "drop"
    assert dec.final_usd == 0.0


def test_sticky_not_first_fill() -> None:
    is_ff, why, _ = is_first_fill_candidate("BTC-USD", position_usd=0.0, stats_map={})
    assert is_ff is False
    assert "sticky_exempt" in why[0] or why == ["sticky_exempt"]


def test_no_history_is_first_fill() -> None:
    is_ff, why, _ = is_first_fill_candidate(
        "SKR-USD", position_usd=0.0, stats_map={}, cfg=DEFAULTS
    )
    assert is_ff is True
    assert "no_ledger_history" in why


def test_graduated_tp_clears() -> None:
    smap = {
        "LINK-USD": _st(pair="LINK-USD", n_rt=3, n_tp_or_rot=1, n_sl=2, net_pnl=10.0),
    }
    is_ff, why, _ = is_first_fill_candidate(
        "LINK-USD", position_usd=0.0, stats_map=smap, cfg=DEFAULTS
    )
    assert is_ff is False
    assert any("graduated" in w for w in why)


def test_filter_plan_haircuts_new_and_spares_sticky() -> None:
    class Plan:
        def __init__(self, actions: List[Dict[str, Any]]):
            self.actions = actions

    runner = SimpleNamespace(
        config_dict={"risk_management": {"first_fill_probation": dict(DEFAULTS)}},
        positions={"BTC-USD": {"value": 50.0}},
        equity_usd=2300.0,
    )
    plan = Plan(
        [
            {"action": "BUY", "pair": "SKR-USD", "usd": 400.0, "reason": "rot"},
            {"action": "BUY", "pair": "BTC-USD", "usd": 200.0, "reason": "core"},
            {"action": "SELL", "pair": "SOL-USD", "usd": 80.0},
        ]
    )
    # empty stats → SKR first fill; BTC sticky/seated path
    out = filter_trade_plan_first_fill(runner, plan)
    by = {a.get("pair"): a for a in out.actions if a.get("action") == "BUY"}
    assert "SKR-USD" in by
    assert by["SKR-USD"].get("first_fill_probation") is True
    assert float(by["SKR-USD"]["usd"]) <= 150.0 + 1e-6
    assert float(by["SKR-USD"]["usd"]) < 400.0
    # BTC should pass without first_fill tag (sticky or seated)
    assert by["BTC-USD"].get("first_fill_probation") is not True
    assert float(by["BTC-USD"]["usd"]) == 200.0


def test_seat_cap_blocks_third_new() -> None:
    class Plan:
        def __init__(self, actions: List[Dict[str, Any]]):
            self.actions = actions

    cfg = dict(DEFAULTS)
    cfg["max_open_first_fill_seats"] = 2
    runner = SimpleNamespace(
        config_dict={"risk_management": {"first_fill_probation": cfg}},
        # two open no-history seats already
        positions={
            "AAA-USD": {"value": 80.0},
            "BBB-USD": {"value": 90.0},
        },
        equity_usd=2300.0,
    )
    plan = Plan([{"action": "BUY", "pair": "CCC-USD", "usd": 200.0}])
    out = filter_trade_plan_first_fill(runner, plan)
    buys = [a for a in out.actions if str(a.get("action")).upper() == "BUY"]
    assert buys == [], f"expected seat_cap drop, got {buys}"
    decs = getattr(out, "first_fill_decisions", [])
    assert any(d.get("status") == "seat_cap" for d in decs)


def test_tag_promote_add_no_hist() -> None:
    t = tag_promote_add("SKR-USD")
    assert t["first_fill_probation"] is True


def main() -> None:
    test_size_haircut_and_caps()
    test_drop_below_min_move()
    test_sticky_not_first_fill()
    test_no_history_is_first_fill()
    test_graduated_tp_clears()
    test_filter_plan_haircuts_new_and_spares_sticky()
    test_seat_cap_blocks_third_new()
    test_tag_promote_add_no_hist()
    print("first_fill_probation isolation PASS")


if __name__ == "__main__":
    main()
