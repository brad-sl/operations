#!/usr/bin/env python3
"""Isolation tests for platform_metrics_spine — fixtures only, no network, no live writes."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core import platform_metrics_spine as m  # noqa: E402


NOW = datetime(2026, 9, 14, 20, 0, 0, tzinfo=timezone.utc)


def _base_feeds(**over) -> dict:
    feeds = {
        "runner_state": {
            "last_rebalance_date": "2026-09-14",
            "rebalance_slots_completed": ["2026-09-14|09:00"],
            "last_updated": "2026-09-14T19:50:00+00:00",
            "manual_liquidation_cash_hold_usd": 0.0,
            "capital_nav_snapshot": {
                "cash_usd": 2000.0,
                "holdings_usd": 80.0,
                "total_usd": 2080.0,
                "ts": "2026-09-14T19:50:00+00:00",
            },
            "_exists": True,
        },
        "live_state": {
            "last_updated": "2026-09-14T19:50:00+00:00",
            "trading_positions": [
                {
                    "pair": "PAXG-USD",
                    "qty": 0.02,
                    "value_usd": 80.0,
                    "sleeve": "preserve",
                }
            ],
            "_exists": True,
        },
        "runner_pid": {"pid": 1, "alive": True, "_exists": True},
        "regime_cash": {
            "regime": "flat",
            "strategy_mode": "deploy",
            "allow_new_buys": True,
            "as_of": "2026-09-14T16:00:00+00:00",
            "_exists": True,
        },
        "tryout_readiness": {
            "can_buy_before_next_rebalance": False,
            "eligible_tryout_pairs": ["ETH-USD", "LINK-USD"],
            "pairs": [
                {"pair": "ETH-USD", "eligible": True, "allowed": False},
                {"pair": "LINK-USD", "eligible": True, "allowed": False},
            ],
            "as_of": "2026-09-14T19:00:00+00:00",
            "_exists": True,
        },
        "brad_decision": {
            "preferred_arm": "rel_btc_stable",
            "live_membership_swaps": False,
            "_exists": True,
        },
        "confidence_board": {
            "status": "preferred_arm_shadow_collecting",
            "arms": [
                {
                    "arm": "rel_btc_stable",
                    "ex7": 5.0,
                    "hit7": 0.52,
                    "n7": 40,
                    "high_confidence": True,
                },
                {
                    "arm": "risk_adj_mom",
                    "ex7": -1.0,
                    "hit7": 0.45,
                    "n7": 40,
                    "high_confidence": False,
                },
            ],
            "as_of": "2026-09-14T18:00:00+00:00",
            "_exists": True,
        },
        "l2": {
            "summary": {"n_pass": 0, "n_rows": 12},
            "rows": [],
            "as_of": "2026-09-12T04:00:00+00:00",
            "_exists": True,
        },
        "pick_summary": {
            "n_picks": 8,
            "open_picks": 5,
            "adds": ["ADA-USD", "WLD-USD"],
            "hit_rate_positive_7d": 0.25,
            "avg_ret_pct_by_horizon": {"7d": -9.0},
            "avg_excess_vs_remove_pct": {"7d": 0.5},
            "ts": "2026-09-14T19:00:00+00:00",
            "_exists": True,
        },
        "graduation": {
            "funnel": {
                "n_seated": 8,
                "n_signaled": 8,
                "n_filled": 2,
                "n_filled_win": 0,
                "n_filled_loss": 2,
                "n_blocked_no_fill": 1,
                "rate_signal_given_seat": 1.0,
                "rate_fill_given_signal": 0.25,
                "rate_win_given_fill_closed": 0.0,
                "rate_win_given_seat": 0.0,
            },
            "ts": "2026-09-14T19:00:00+00:00",
            "_exists": True,
        },
        "seat_idle": {
            "mode": "observe_only",
            "hard_eject": False,
            "n_idle_flagged": 2,
            "idle_flagged_pairs": ["DOGE-USD", "NEAR-USD"],
            "ts": "2026-09-14T19:00:00+00:00",
            "_exists": True,
        },
        "attribution": {
            "summary": {
                "n_rt_primary": 7,
                "edge_claim_allowed": False,
                "process_tax_bank": {"n": 5, "pnl_sum": -4.0},
                "non_tax_bank": {"n": 2, "pnl_sum": 8.0},
            },
            "as_of": "2026-09-12T04:00:00+00:00",
            "_exists": True,
        },
        "exit_stack": {"go_nogo": {"overall": "ATTENTION"}, "as_of_utc": "2026-09-12T01:00:00+00:00", "_exists": True},
        "limit_first": {
            "aggregate": {"attempts": 7, "filled": 5, "promote_talk_ok": False},
            "as_of": "2026-09-12T04:00:00+00:00",
            "_exists": True,
        },
        "regime_arm": {
            "preferred_arm": "rel_btc_stable",
            "sticky_tape": "btc_chop",
            "as_of": "2026-09-14T18:41:00+00:00",
            "_exists": True,
        },
        "missfire": {
            "blocked_pairs": ["RAVE-USD"],
            "as_of": "2026-09-14T12:00:00+00:00",
            "_exists": True,
        },
        "novelty": {
            "counts": {"CORE": 10, "NOVELTY_RESTRICTED": 5},
            "asof": "2026-09-14T12:00:00+00:00",
            "_exists": True,
        },
        "protective_registry": {
            "_lines": [
                {"pair": "PAXG-USD", "status": "open", "sl_order_id": "x"},
            ]
        },
    }
    feeds.update(over)
    return feeds


def test_lifecycle_stages_ordered_and_choke_trade_success():
    payload = m.build_spine(feeds=_base_feeds(), now=NOW, write=False)
    assert payload["schema"] == m.SCHEMA
    assert payload["measure_only"] is True
    assert payload["no_live_writes"] is True
    stages = payload["lifecycle"]["stages"]
    ids = [s["id"] for s in stages]
    assert ids == list(m.LIFECYCLE_ORDER)
    # 2 fills, 0 wins → trade_success choke
    assert payload["lifecycle"]["choke_point"]["id"] == "trade_success"
    assert payload["go_nogo"]["money_path"] == "NO_GO_SCALE"
    assert payload["go_nogo"]["auto_membership"] in ("NO_GO", "STILL_NO_AUTO")
    assert payload["lifecycle"]["live_membership_swaps"] is False
    assert payload["lifecycle"]["automation_readiness"]["auto_promote_live"] is False


def test_runner_ops_ok_with_preserve_only_and_dead_pid_fails():
    ok = m.build_spine(feeds=_base_feeds(), now=NOW, write=False)
    assert ok["runner_ops"]["ops_ok"] is True
    assert ok["runner_ops"]["sl_coverage"] == 1.0  # vacuous — no trade bags
    assert ok["go_nogo"]["ops"] == "GO"

    dead = m.build_spine(
        feeds=_base_feeds(**{"runner_pid": {"pid": 999999, "alive": False}}),
        now=NOW,
        write=False,
    )
    assert dead["runner_ops"]["ops_ok"] is False
    assert dead["go_nogo"]["ops"] == "NO_GO"


def test_naked_trade_bag_flags_ops():
    feeds = _base_feeds(
        live_state={
            "last_updated": "2026-09-14T19:50:00+00:00",
            "trading_positions": [
                {"pair": "ETH-USD", "qty": 1.0, "value_usd": 100.0, "sleeve": "tryout"},
            ],
            "_exists": True,
        },
        protective_registry={"_lines": []},
    )
    payload = m.build_spine(feeds=feeds, now=NOW, write=False)
    assert payload["runner_ops"]["ops_ok"] is False
    assert payload["runner_ops"]["naked_bags"]
    assert payload["runner_ops"]["naked_bags"][0]["pair"] == "ETH-USD"


def test_active_positions_count_int_safe():
    """live_state.active_positions is often a COUNT int — never iterate it."""
    feeds = _base_feeds(
        live_state={
            "last_updated": "2026-09-14T19:50:00+00:00",
            "active_positions": 1,
            "positions": [
                {"pair": "ETH-USD", "qty": 1.0, "value_usd": 100.0, "sleeve": "tryout"},
            ],
            "_exists": True,
        },
        protective_registry={
            "_lines": [{"pair": "ETH-USD", "status": "open", "order_type": "stop"}],
        },
    )
    payload = m.build_spine(feeds=feeds, now=NOW, write=False)
    assert payload["runner_ops"]["n_open_trade_bags"] == 1
    assert payload["runner_ops"]["sl_coverage"] == 1.0
    assert payload["runner_ops"]["ops_ok"] is True


def test_fill_choke_when_seats_no_fills():
    feeds = _base_feeds(
        graduation={
            "funnel": {
                "n_seated": 8,
                "n_signaled": 8,
                "n_filled": 0,
                "n_filled_win": 0,
                "n_filled_loss": 0,
                "n_blocked_no_fill": 2,
                "rate_signal_given_seat": 1.0,
                "rate_fill_given_signal": 0.0,
                "rate_win_given_fill_closed": None,
                "rate_win_given_seat": 0.0,
            },
            "ts": "2026-09-14T19:00:00+00:00",
            "_exists": True,
        }
    )
    payload = m.build_spine(feeds=feeds, now=NOW, write=False)
    assert payload["lifecycle"]["choke_point"]["id"] == "fill"


def test_markdown_and_no_write_side_effects(tmp_path: Path | None = None):
    payload = m.build_spine(feeds=_base_feeds(), now=NOW, write=False)
    md = m.render_markdown(payload)
    assert "Platform metrics spine" in md
    assert "Pair lifecycle funnel" in md
    assert "Automation readiness" in md
    assert payload.get("actions_taken") == []


def test_write_artifacts_to_tmp(tmp_path: Path):
    # redirect write paths via monkeypatch root
    root = tmp_path
    (root / "data" / "state").mkdir(parents=True)
    (root / "reports").mkdir(parents=True)
    payload = m.build_spine(feeds=_base_feeds(), now=NOW, write=False)
    # manual write using helper with root
    m._write_artifacts(payload, root=root)
    state = root / "data" / "state" / "platform_metrics_spine_latest.json"
    report = root / "reports" / "PLATFORM_METRICS_SPINE_LATEST.md"
    assert state.exists()
    assert report.exists()
    loaded = json.loads(state.read_text())
    assert loaded["schema"] == m.SCHEMA
    assert "Go / no-go" in report.read_text()


if __name__ == "__main__":
    test_lifecycle_stages_ordered_and_choke_trade_success()
    test_runner_ops_ok_with_preserve_only_and_dead_pid_fails()
    test_naked_trade_bag_flags_ops()
    test_active_positions_count_int_safe()
    test_fill_choke_when_seats_no_fills()
    test_markdown_and_no_write_side_effects()
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        test_write_artifacts_to_tmp(Path(d))
    print("PASS: platform_metrics_spine isolation")
