#!/usr/bin/env python3
"""Isolation tests for basket seat idle tracker (no live IO required for core math)."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.basket_seat_idle import (  # noqa: E402
    SeatIdleConfig,
    annotate_scores_with_idle,
    build_seat_idle_snapshot,
    compute_idle_flag,
    resolve_active_since,
)


def test_compute_idle_flag_basic():
    cfg = SeatIdleConfig(min_seat_days=7, min_idle_days=7, require_flat_for_flag=True)
    flag, reasons, cap = compute_idle_flag(
        sticky=False,
        seat_days=10,
        buys_while_seated=0,
        days_since_buy=None,
        flat=True,
        cfg=cfg,
    )
    assert flag is True, (flag, reasons, cap)
    assert cap == 10
    assert "idle_cycle_candidate" in reasons

    flag2, _, _ = compute_idle_flag(
        sticky=True,
        seat_days=99,
        buys_while_seated=0,
        days_since_buy=None,
        flat=True,
        cfg=cfg,
    )
    assert flag2 is False

    flag3, reasons3, _ = compute_idle_flag(
        sticky=False,
        seat_days=10,
        buys_while_seated=0,
        days_since_buy=None,
        flat=False,
        cfg=cfg,
    )
    assert flag3 is False
    assert "not_flat" in reasons3
    print("PASS test_compute_idle_flag_basic")


def test_resolve_active_since_after_remove():
    t0 = datetime(2026, 8, 1, tzinfo=timezone.utc)
    t1 = datetime(2026, 8, 9, tzinfo=timezone.utc)
    t2 = datetime(2026, 8, 11, tzinfo=timezone.utc)
    events = [
        {"ts": t0, "kind": "add", "pair": "FOO-USD", "source": "a"},
        {"ts": t1, "kind": "remove", "pair": "FOO-USD", "source": "b"},
        {"ts": t2, "kind": "add", "pair": "FOO-USD", "source": "c"},
    ]
    since, src = resolve_active_since("FOO-USD", events=events, prior_row=None)
    assert since == t2
    assert src == "c"
    print("PASS test_resolve_active_since_after_remove")


def test_snapshot_idle_and_annotate():
    now = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)
    active = ["BTC-USD", "WEAK-USD", "HELD-USD"]
    holdings = {"BTC-USD": 1000.0, "WEAK-USD": 0.0, "HELD-USD": 200.0}
    since_weak = now - timedelta(days=14)
    since_held = now - timedelta(days=14)
    events = [
        {"ts": since_weak, "kind": "add", "pair": "WEAK-USD", "source": "test"},
        {"ts": since_held, "kind": "add", "pair": "HELD-USD", "source": "test"},
        {"ts": now - timedelta(days=30), "kind": "add", "pair": "BTC-USD", "source": "test"},
    ]
    buys = [
        ("BTC-USD", now - timedelta(days=2)),
        # WEAK never bought; HELD bought long ago before seat
        ("HELD-USD", now - timedelta(days=40)),
    ]
    prior = {
        "as_of_date": (now.date() - timedelta(days=1)).isoformat(),
        "pairs": {
            "WEAK-USD": {
                "as_of_date": (now.date() - timedelta(days=1)).isoformat(),
                "flat": True,
                "flat_day_streak": 3,
                "active_since": since_weak.isoformat(),
                "active_since_source": "prior",
            }
        },
    }
    snap = build_seat_idle_snapshot(
        active=active,
        holdings=holdings,
        prior_latest=prior,
        buys=buys,
        events=events,
        cfg=SeatIdleConfig(min_seat_days=7, min_idle_days=7, require_flat_for_flag=True),
        now=now,
        write=False,
    )
    pairs = snap["pairs"]
    assert pairs["WEAK-USD"]["idle_cycle_flag"] is True
    assert pairs["WEAK-USD"]["flat_day_streak"] == 4  # 3 + 1 consecutive day
    assert pairs["BTC-USD"]["idle_cycle_flag"] is False  # sticky
    assert pairs["HELD-USD"]["idle_cycle_flag"] is False  # not flat
    assert pairs["HELD-USD"]["buys_while_seated"] == 0
    assert "WEAK-USD" in snap["idle_flagged_pairs"]

    class S:
        def __init__(self, pair, reason="ok"):
            self.pair = pair
            self.reason = reason

    scores = [S("WEAK-USD"), S("BTC-USD")]
    n = annotate_scores_with_idle(scores, idle_flag_map_from_snap(snap))
    assert n == 1
    assert "IDLE_SEAT_FLAG" in scores[0].reason
    assert "IDLE_SEAT_FLAG" not in scores[1].reason
    print("PASS test_snapshot_idle_and_annotate")


def idle_flag_map_from_snap(snap):
    return {
        p: {
            "idle_cycle_flag": d.get("idle_cycle_flag"),
            "seat_days": d.get("seat_days"),
            "capital_idle_days": d.get("capital_idle_days"),
            "flat_day_streak": d.get("flat_day_streak"),
            "held_usd": d.get("held_usd"),
            "idle_reasons": d.get("idle_reasons") or [],
        }
        for p, d in (snap.get("pairs") or {}).items()
    }


def main() -> int:
    test_compute_idle_flag_basic()
    test_resolve_active_since_after_remove()
    test_snapshot_idle_and_annotate()
    print("ALL PASS test_isolation_basket_seat_idle")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
