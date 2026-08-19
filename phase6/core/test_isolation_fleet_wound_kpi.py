#!/usr/bin/env python3
"""Isolation: fleet wound KPI (GAP-02)."""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.fleet_wound_kpi import (  # noqa: E402
    ARMED_STOP_FIX_TS,
    classify,
    compute,
    format_brief_line,
    render_md,
)


def _row(ts: datetime, pair: str, side: str, reason: str) -> dict:
    return {
        "timestamp": ts.isoformat().replace("+00:00", "Z"),
        "pair": pair,
        "side": side,
        "reason": reason,
        "qty": 1.0,
        "order_id": f"{pair}-{side}-{int(ts.timestamp())}",
    }


def main() -> int:
    # classify pure
    assert classify(
        count_7d=0, count_30d=0, count_post_fix=0, count_5m_7d=0
    )["decision"] == "pass"
    assert (
        classify(count_7d=1, count_30d=2, count_post_fix=1, count_5m_7d=0)["decision"]
        == "breach"
    )
    assert (
        classify(
            count_7d=1,
            count_30d=2,
            count_post_fix=0,
            count_5m_7d=1,
            count_5m_post_fix=0,
        )["decision"]
        == "watch_pre_fix_residual"
    )
    assert (
        classify(count_7d=0, count_30d=3, count_post_fix=0, count_5m_7d=0)["decision"]
        == "watch_historical"
    )
    assert (
        classify(count_7d=1, count_30d=2, count_post_fix=0, count_5m_7d=0)["decision"]
        == "watch_pre_fix_residual"
    )
    assert (
        classify(
            count_7d=1,
            count_30d=1,
            count_post_fix=1,
            count_5m_7d=1,
            count_5m_post_fix=1,
        )["decision"]
        == "breach"
    )

    now = datetime(2026, 8, 16, 18, 0, tzinfo=timezone.utc)
    fix = ARMED_STOP_FIX_TS
    # Pre-fix wound (should land in 30d if within 30d, not post_fix if before fix)
    pre_buy = fix - timedelta(days=2)
    pre_sl = pre_buy + timedelta(minutes=30)
    # Post-fix clean path — no wound
    # Post-fix wound for breach fixture
    post_buy = fix + timedelta(days=1, hours=2)
    post_sl = post_buy + timedelta(minutes=4)  # under 5m

    rows_hist = [
        _row(pre_buy, "BTC-USD", "BUY", "rebalance_buy"),
        _row(pre_sl, "BTC-USD", "SELL", "stop_loss_exchange"),
    ]
    rows_breach = rows_hist + [
        _row(post_buy, "RAVE-USD", "BUY", "rebalance_buy"),
        _row(post_sl, "RAVE-USD", "SELL", "stop_loss_exchange"),
    ]

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        led_h = td_path / "hist.jsonl"
        led_b = td_path / "breach.jsonl"
        st = td_path / "state.json"
        al = td_path / "alert.json"
        with led_h.open("w") as f:
            for r in rows_hist:
                f.write(json.dumps(r) + "\n")
        with led_b.open("w") as f:
            for r in rows_breach:
                f.write(json.dumps(r) + "\n")

        h = compute(
            ledger_path=led_h,
            now=now,
            fix_ts=fix,
            persist=True,
            state_path=st,
            alert_path=al,
        )
        # Pre-fix only: post_fix=0, may be in 7d or 30d depending on dates
        # fix=Aug13, pre=Aug11, now=Aug16 → within 7d
        # Actually pre is 2d before fix = Aug 11, now Aug 16 → 5 days ago → in 7d
        # So historical pre-fix within 7d still counts as 7d wound → breach
        # Adjust: put pre-fix further back (>7d from now) but within 30d
        assert h["schema"] == "fleet_wound_kpi_v1"

        # Better fixture: only old 30d wound
        old_buy = now - timedelta(days=20)
        old_sl = old_buy + timedelta(hours=1)
        led_old = td_path / "old.jsonl"
        with led_old.open("w") as f:
            f.write(json.dumps(_row(old_buy, "ETH-USD", "BUY", "rebalance_buy")) + "\n")
            f.write(
                json.dumps(_row(old_sl, "ETH-USD", "SELL", "stop_loss_exchange")) + "\n"
            )
        # old is before fix (Aug 16-20 = Jul 27) — well before fix
        o = compute(
            ledger_path=led_old,
            now=now,
            fix_ts=fix,
            persist=True,
            state_path=td_path / "st_old.json",
            alert_path=td_path / "al_old.json",
        )
        assert o["windows"]["d7"]["count"] == 0, o
        assert o["windows"]["d30"]["count"] == 1, o
        assert o["windows"]["post_armed_stop_fix"]["count"] == 0, o
        assert o["decision"] == "watch_historical", o
        assert o.get("alert_active") is False

        b = compute(
            ledger_path=led_b,
            now=now,
            fix_ts=fix,
            persist=True,
            state_path=td_path / "st_b.json",
            alert_path=td_path / "al_b.json",
        )
        assert b["windows"]["post_armed_stop_fix"]["count"] >= 1, b
        assert b["decision"] == "breach", b
        assert b.get("alert_active") is True
        assert (td_path / "al_b.json").is_file()
        assert "Fleet wounds" in format_brief_line(b)
        assert "Fleet wound KPI" in render_md(b)

        # Clean ledger
        led_c = td_path / "clean.jsonl"
        led_c.write_text("")
        c = compute(
            ledger_path=led_c,
            now=now,
            fix_ts=fix,
            persist=True,
            state_path=td_path / "st_c.json",
            alert_path=td_path / "al_c.json",
        )
        assert c["decision"] == "pass", c
        assert c["windows"]["d7"]["count"] == 0

    live = compute(persist=True)
    assert "decision" in live
    print("PASS test_isolation_fleet_wound_kpi")
    print("  fixture_old:", o["decision"], format_brief_line(o))
    print("  fixture_breach:", b["decision"], format_brief_line(b))
    print("  fixture_clean:", c["decision"])
    print("  live:", format_brief_line(live), live.get("go_no_go", "")[:100])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
