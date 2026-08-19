#!/usr/bin/env python3
"""Isolation: signal DQ monitor defer-streak + cooldown."""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.signal_dq_monitor import (  # noqa: E402
    detect_defer_streak,
    evaluate_signal_dq,
)


def test_detect_streak_requires_min():
    lines = [
        "2026-07-22 10:00:00 [PRE-REBAL REFRESH] starting parallel missing_rsi=['OP-USD'] missing_sent=[]",
        "2026-07-22 10:00:01 [REBALANCE DEFER] slot=2026-07-22|09:00 reasons=['incomplete_coverage']",
        "2026-07-22 10:01:00 [PRE-REBAL REFRESH] starting parallel missing_rsi=['OP-USD'] missing_sent=[]",
        "2026-07-22 10:01:01 [REBALANCE DEFER] slot=2026-07-22|09:00 reasons=['incomplete_coverage']",
    ]
    assert detect_defer_streak(lines, min_streak=3) is None
    lines.append(
        "2026-07-22 10:02:01 [REBALANCE DEFER] slot=2026-07-22|09:00 reasons=['incomplete_coverage']"
    )
    st = detect_defer_streak(lines, min_streak=3)
    assert st is not None
    assert st.count == 3
    assert "incomplete_coverage" in st.reasons
    assert st.sample_missing_rsi == ["OP-USD"]
    print("detect_streak_requires_min OK", st)


def test_clear_resets_streak():
    lines = [
        "[REBALANCE DEFER] slot=2026-07-22|09:00 reasons=['incomplete_coverage']",
        "[REBALANCE DEFER] slot=2026-07-22|09:00 reasons=['incomplete_coverage']",
        "[REBALANCE DEFER] slot=2026-07-22|09:00 reasons=['incomplete_coverage']",
        "[REBALANCE GATE] allowed slot=2026-07-22|09:00 (connectivity + basket signals ready)",
        "[REBALANCE DEFER] slot=2026-07-22|09:00 reasons=['incomplete_coverage']",
    ]
    assert detect_defer_streak(lines, min_streak=3) is None
    print("clear_resets_streak OK")


def test_evaluate_cooldown(tmp_path: Path | None = None):
    td = Path(tempfile.mkdtemp()) if tmp_path is None else tmp_path
    log = td / "runner.log"
    state = td / "dq.json"
    body = "\n".join(
        [
            "missing_rsi=['OP-USD']",
            "[REBALANCE DEFER] slot=2026-07-22|09:00 reasons=['incomplete_coverage']",
            "missing_rsi=['OP-USD']",
            "[REBALANCE DEFER] slot=2026-07-22|09:00 reasons=['incomplete_coverage']",
            "missing_rsi=['OP-USD']",
            "[REBALANCE DEFER] slot=2026-07-22|09:00 reasons=['incomplete_coverage']",
            "missing_rsi=['OP-USD']",
            "[REBALANCE DEFER] slot=2026-07-22|09:00 reasons=['incomplete_coverage']",
        ]
    )
    log.write_text(body + "\n")

    t0 = datetime(2026, 7, 22, 17, 0, tzinfo=timezone.utc)
    d1 = evaluate_signal_dq(
        log_path=log,
        state_path=state,
        min_streak=3,
        cooldown_minutes=60,
        now=t0,
    )
    assert d1.should_alert is True, d1.message
    assert d1.streak and d1.streak.count >= 3

    d2 = evaluate_signal_dq(
        log_path=log,
        state_path=state,
        min_streak=3,
        cooldown_minutes=60,
        now=t0 + timedelta(minutes=10),
    )
    assert d2.should_alert is False, "cooldown should suppress re-alert"
    assert "cooldown" in d2.message.lower() or d2.level == "warning"

    d3 = evaluate_signal_dq(
        log_path=log,
        state_path=state,
        min_streak=3,
        cooldown_minutes=60,
        now=t0 + timedelta(minutes=61),
    )
    assert d3.should_alert is True, "after cooldown should alert again"

    # clear path
    log.write_text(body + "\n[REBALANCE GATE] allowed slot=x\nDaily rebalance completed. Executed=0\n")
    d4 = evaluate_signal_dq(
        log_path=log,
        state_path=state,
        min_streak=3,
        cooldown_minutes=60,
        now=t0 + timedelta(minutes=62),
    )
    assert d4.should_alert is False
    assert d4.level == "ok"
    print("evaluate_cooldown OK")


if __name__ == "__main__":
    test_detect_streak_requires_min()
    test_clear_resets_streak()
    test_evaluate_cooldown()
    print("[SIGNAL-DQ-MONITOR] PASSED")
