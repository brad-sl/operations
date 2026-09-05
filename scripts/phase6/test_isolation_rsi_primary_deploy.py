#!/usr/bin/env python3
"""
Isolation tests: RSI-primary deploy gates + sentiment-fade shadow.

Run:
  cd /home/brad/projects/crypto-trading-bot && PYTHONPATH=. python3 scripts/phase6/test_isolation_rsi_primary_deploy.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.rsi_primary_deploy import (
    apply_buy_size_gates,
    apply_gates_to_actions,
    classify_entry_drivers,
    evaluate_sentiment_fade,
    filter_trade_plan_rsi_primary_deploy,
    load_rsi_primary_config,
    record_entry_lot,
)


class _Plan:
    def __init__(self, actions):
        self.actions = actions
        self.notes = ""


class _Runner:
    def __init__(self, cfg, rsi, positions=None, equity=2372.0, cash=1975.0):
        self.config_dict = cfg
        self.rsi_values = rsi
        self.FIXED_UNIVERSE = list(rsi.keys())
        self._positions = positions or {}
        self._equity = equity
        self._cash = cash
        self.exchange = None


def main() -> int:
    fails = []
    cfg = load_rsi_primary_config(
        json.loads((ROOT / "config/trading_config_phase6.json").read_text())
    )
    assert cfg.get("enabled") is True, "config enabled"
    # Pure gate math must not depend on live operator pair caps (LINK tryout etc.)
    cfg_pure = json.loads(json.dumps(cfg))
    cfg_pure["pair_ticket_caps"] = {}

    # --- classify ---
    ed = classify_entry_drivers("LINK-USD", 46.6, 0.89, cfg=cfg_pure)
    if not ed.sentiment_only:
        fails.append(f"expected sentiment_only LINK, got {ed}")
    ed2 = classify_entry_drivers("BTC-USD", 28.0, 0.1, cfg=cfg_pure)
    if ed2.sentiment_only or "rsi_oversold" not in ed2.drivers:
        fails.append(f"expected rsi_oversold BTC, got {ed2}")
    ed3 = classify_entry_drivers("ETH-USD", 32.0, 0.5, cfg=cfg_pure)
    if ed3.sentiment_only or not ed3.full_size_ok:
        fails.append(f"expected full_size RSI+sent ETH, got {ed3}")

    # --- LINK poster child: $1925 recovery, cap $100 ---
    g = apply_buy_size_gates(
        "LINK-USD",
        1925.0,
        rsi=46.6,
        sentiment=0.89,
        equity_usd=2372.0,
        current_pair_usd=0.0,
        rebalance_cap_usd=100.0,
        free_cash_usd=1975.0,
        emergency_recovery=True,
        cfg=cfg_pure,
    )
    print("LINK case:", json.dumps(g.as_dict(), indent=2))
    if not g.haircut_applied:
        fails.append("LINK haircut not applied")
    if not g.ticket_cap_applied:
        fails.append("LINK ticket cap not applied")
    # haircut 1925*0.35=673.75 then cap 100
    if abs(g.final_usd - 100.0) > 1e-6:
        fails.append(f"LINK final expected 100 got {g.final_usd}")

    # --- without cap, haircut + pair weight + free cash share ---
    g2 = apply_buy_size_gates(
        "LINK-USD",
        1925.0,
        rsi=46.6,
        sentiment=0.89,
        equity_usd=2372.0,
        current_pair_usd=0.0,
        rebalance_cap_usd=None,
        free_cash_usd=1975.0,
        emergency_recovery=True,
        cfg=cfg_pure,
    )
    # 1925*0.35=673.75; pair w=0.35*2372=830.2; free share 0.5*1975=987.5 → 673.75
    print("LINK no-cap:", g2.final_usd, g2.notes)
    if g2.final_usd > 700:
        fails.append(f"no-cap should be haircut-bound ~674 got {g2.final_usd}")
    if g2.final_usd < 600:
        fails.append(f"no-cap unexpectedly small {g2.final_usd}")

    # --- live operator pair_ticket_caps (LINK $150) binds when regime cap higher ---
    g_pair = apply_buy_size_gates(
        "LINK-USD",
        500.0,
        rsi=44.0,
        sentiment=0.4,
        equity_usd=2300.0,
        current_pair_usd=0.0,
        rebalance_cap_usd=200.0,
        free_cash_usd=800.0,
        emergency_recovery=False,
        cfg=cfg,  # live config with pair_ticket_caps
    )
    print("LINK pair_ticket_cap live cfg:", g_pair.final_usd, g_pair.notes)
    live_cap = float((cfg.get("pair_ticket_caps") or {}).get("LINK-USD") or 0)
    if live_cap > 0 and g_pair.final_usd > live_cap + 1e-6:
        fails.append(f"pair_ticket_cap not bound: {g_pair.final_usd} > {live_cap}")
    if live_cap > 0 and not any("pair_ticket_cap" in n for n in g_pair.notes):
        # may already be under via haircut; force high proposed after haircut
        g_pair2 = apply_buy_size_gates(
            "LINK-USD",
            2000.0,
            rsi=28.0,
            sentiment=0.5,
            equity_usd=5000.0,
            current_pair_usd=0.0,
            rebalance_cap_usd=500.0,
            free_cash_usd=3000.0,
            cfg=cfg,
        )
        if g_pair2.final_usd > live_cap + 1e-6:
            fails.append(f"pair_ticket_cap miss on large: {g_pair2.final_usd}")
        elif not any("pair_ticket_cap" in n for n in g_pair2.notes):
            fails.append(f"pair_ticket_cap note missing: {g_pair2.notes}")

    # --- RSI oversold full size subject to cap only ---
    g3 = apply_buy_size_gates(
        "SOL-USD",
        500.0,
        rsi=28.0,
        sentiment=0.5,
        equity_usd=2500.0,
        current_pair_usd=0.0,
        rebalance_cap_usd=150.0,
        free_cash_usd=800.0,
        emergency_recovery=False,
        cfg=cfg_pure,
    )
    print("SOL oversold+sent:", g3.as_dict())
    if g3.haircut_applied:
        fails.append("SOL should not haircut (has RSI driver)")
    if abs(g3.final_usd - 150.0) > 1e-6:
        fails.append(f"SOL should hit ticket 150 got {g3.final_usd}")

    # --- pair weight room ---
    g4 = apply_buy_size_gates(
        "ETH-USD",
        400.0,
        rsi=25.0,
        sentiment=0.0,
        equity_usd=1000.0,
        current_pair_usd=250.0,  # already 25%; max 30% → room 50
        rebalance_cap_usd=500.0,
        free_cash_usd=500.0,
        emergency_recovery=False,
        cfg=cfg_pure,
    )
    print("ETH room:", g4.final_usd, g4.notes)
    if abs(g4.final_usd - 50.0) > 1e-6:
        fails.append(f"ETH room expected 50 got {g4.final_usd}")

    # --- multi-action free cash sequential ---
    acts, res = apply_gates_to_actions(
        [
            {"pair": "A-USD", "action": "BUY", "usd": 1000, "reason": "t"},
            {"pair": "B-USD", "action": "BUY", "usd": 1000, "reason": "t"},
        ],
        rsi_by_pair={"A-USD": 45.0, "B-USD": 45.0},
        sent_by_pair={"A-USD": 0.8, "B-USD": 0.8},
        equity_usd=3000.0,
        positions_usd={},
        rebalance_cap_usd=2000.0,
        free_cash_usd=1000.0,
        emergency_recovery=True,
        cfg=cfg_pure,
    )
    print("multi BUY finals:", [(a["pair"], a["usd"]) for a in acts])
    total = sum(a["usd"] for a in acts)
    if total > 1000.0 + 1e-6:
        fails.append(f"multi BUY total {total} > free cash 1000")
    # each sentiment-only haircut 0.35*1000=350 then share 0.5*remaining
    if len(acts) < 1:
        fails.append("expected at least one multi BUY survive")

    # --- fade: cool sent, no TP arm → would_trim ---
    lots = [
        {
            "pair": "LINK-USD",
            "open": True,
            "sentiment_led": True,
            "sentiment_only": True,
            "entry_sentiment": 0.89,
            "entry_price": 11.60,
            "usd": 1895.0,
        }
    ]
    ev = evaluate_sentiment_fade(
        lots=lots,
        current_sentiment={"LINK-USD": 0.40},
        current_prices={"LINK-USD": 11.48},  # -1% peak
        positions_usd={"LINK-USD": 1895.0},
        cfg=cfg,
    )
    print("fade events:", [e.as_dict() for e in ev])
    if len(ev) != 1:
        fails.append(f"expected 1 fade event got {len(ev)}")
    else:
        if abs(ev[0].would_trim_usd - 947.5) > 1.0:
            fails.append(f"trim usd unexpected {ev[0].would_trim_usd}")

    # --- fade suppressed when TP arm zone ---
    ev2 = evaluate_sentiment_fade(
        lots=lots,
        current_sentiment={"LINK-USD": 0.10},
        current_prices={"LINK-USD": 12.20},  # +5.17%
        positions_usd={"LINK-USD": 1895.0},
        cfg=cfg,
    )
    if ev2:
        fails.append(f"fade should skip when peak>=arm, got {ev2}")

    # --- filter_trade_plan integration ---
    plan = _Plan(
        [{"pair": "LINK-USD", "action": "BUY", "usd": 1925.0, "reason": "opportunistic_rotation_from_weak"}]
    )
    runner = _Runner(
        json.loads((ROOT / "config/trading_config_phase6.json").read_text()),
        {"LINK-USD": 46.6},
        positions={},
        equity=2372.0,
        cash=1975.0,
    )

    # stub live state for filter
    with tempfile.TemporaryDirectory() as td:
        # filter uses cwd live state; monkey via positions kwargs path — call apply path directly
        from phase6.core import rsi_primary_deploy as m

        # Directly use apply via filter with explicit kwargs
        class R2:
            config_dict = runner.config_dict
            rsi_values = {"LINK-USD": 46.6}
            FIXED_UNIVERSE = ["LINK-USD"]
            exchange = type("E", (), {"get_account_balance": staticmethod(lambda c: 1975.0)})()

        plan2 = filter_trade_plan_rsi_primary_deploy(
            R2(),
            plan,
            sentiment_scores={"LINK-USD": 0.89},
            rsi_values={"LINK-USD": 46.6},
            equity_usd=2372.0,
            positions_usd={},
            rebalance_cap_usd=100.0,
            free_cash_usd=1975.0,
            emergency_recovery=True,
        )
        print("filtered plan:", plan2.actions)
        if not plan2.actions:
            fails.append("filtered plan empty (cap 100 should keep $100)")
        else:
            if abs(float(plan2.actions[0]["usd"]) - 100.0) > 1e-6:
                fails.append(f"filtered usd {plan2.actions[0]['usd']}")
            if not plan2.actions[0].get("sentiment_only"):
                fails.append("missing sentiment_only tag on action")

    # --- entry lot write ---
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "lots.json"
        ed = classify_entry_drivers("LINK-USD", 46.6, 0.89, cfg=cfg)
        record_entry_lot(
            pair="LINK-USD",
            entry_price=11.60,
            usd=100.0,
            drivers=ed,
            path=p,
        )
        data = json.loads(p.read_text())
        if not data.get("lots") or not data["lots"][0].get("sentiment_only"):
            fails.append(f"lot write bad: {data}")

    print("\n==== RESULTS ====")
    if fails:
        for f in fails:
            print("FAIL:", f)
        print(f"{len(fails)} failure(s)")
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
