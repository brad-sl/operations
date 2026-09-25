"""Isolation: shell slot scorecard. No live files."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.shell_slot_score import (  # noqa: E402
    classify_doors,
    is_bug_exit,
    is_risk_buy,
    score_slot,
    telegram_body,
    wave2_hint,
)

PT = ZoneInfo("America/Los_Angeles")


def test_quiet_sensor_silent_until_final():
    readiness = {
        "can_buy_before_next_rebalance": False,
        "seats_used_today": 0,
        "max_new_seats_per_day": 4,
        "plain_english": "no door",
        "pairs": [
            {"pair": "ETH-USD", "eligible": True, "allowed": False, "eng_sent": 0.04, "rsi": 53, "reasons": ["sentiment 0.04 < min 0.3"]},
            {"pair": "LINK-USD", "eligible": True, "allowed": False, "eng_sent": 0.03, "rsi": 57.7, "reasons": ["sentiment 0.03 < min 0.3", "rsi 57.7 > max_buy 55.0"]},
        ],
    }
    now = datetime(2026, 9, 24, 21, 20, tzinfo=PT)
    card = score_slot(readiness=readiness, ledger_rows=[], now=now, prior_slot_ids=[])
    assert card["slot_id"] == "2026-09-24|21:00"
    assert card["slot_index"] == 1
    assert card["n_risk_fills"] == 0
    assert "W2-D" in card["wave2_hint"]
    assert telegram_body(card) == ""
    assert card["knobs_touched"] is False


def test_rsi_only_pages():
    readiness = {
        "pairs": [
            {"pair": "LINK-USD", "eligible": True, "allowed": False, "eng_sent": 0.41, "rsi": 57.7, "reasons": ["rsi 57.7 > max_buy 55.0"]},
        ]
    }
    now = datetime(2026, 9, 25, 21, 20, tzinfo=PT)
    card = score_slot(readiness=readiness, ledger_rows=[], now=now, prior_slot_ids=["2026-09-24|21:00"])
    assert card["classify"]["rsi_only_block"] == ["LINK-USD"]
    assert "W2-C" in card["wave2_hint"]
    assert "RSI-only block" in card["telegram"]
    assert card["slot_index"] == 2


def test_bug_and_stable_ignored():
    assert is_risk_buy({"side": "BUY", "pair": "USDT-USD"}) is False
    assert is_risk_buy({"side": "BUY", "pair": "ETH-USD"}) is True
    assert is_bug_exit({"side": "SELL", "pair": "LINK-USD", "exit_reason": "dust_sweep_orphan", "price": 12.3, "size": 2.04}) is True
    assert is_bug_exit({"side": "SELL", "pair": "LINK-USD", "exit_reason": "dust_sweep_orphan", "price": 12.0, "size": 0.05}) is False
    assert is_bug_exit({"side": "SELL", "exit_reason": "process_bug_orphan_dust_full_bag", "pnl": 0.1}) is True


def test_final_slot_pages_even_if_idle():
    readiness = {"pairs": [{"pair": "ETH-USD", "eligible": True, "eng_sent": 0.02, "reasons": ["sentiment 0.02 < min 0.3"]}]}
    now = datetime(2026, 9, 26, 21, 20, tzinfo=PT)
    card = score_slot(
        readiness=readiness,
        ledger_rows=[],
        now=now,
        prior_slot_ids=["2026-09-24|21:00", "2026-09-25|21:00"],
    )
    assert card["final_slot"] is True
    assert card["slot_index"] == 3
    assert "W2-D" in card["telegram"]
    assert "No knobs" in card["telegram"]


def test_hint_fill_stops_loosen():
    assert "No scale" in wave2_hint({"quiet_sensor": ["ETH-USD"]}, 1, 0)
    assert "STOP" in wave2_hint({}, 0, 1)
    assert classify_doors([])["sent_clear"] == []


if __name__ == "__main__":
    test_quiet_sensor_silent_until_final()
    test_rsi_only_pages()
    test_bug_and_stable_ignored()
    test_final_slot_pages_even_if_idle()
    test_hint_fill_stops_loosen()
    print("OK shell_slot_score 5/5")
