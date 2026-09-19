#!/usr/bin/env python3
"""Isolation for trial closeout watchdog."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def test_past_final_emits_action_and_packet():
    import phase6.research.trial_closeout_watch as w

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        trials = td_path / "trials"
        inbox = td_path / "inbox"
        state = td_path / "state"
        trials.mkdir()
        inbox.mkdir()
        state.mkdir()
        tid = "TEST-CLOSEOUT-OVERDUE-001"
        trial = {
            "trial_id": tid,
            "status": "RUNNING",
            "final_at": "2020-01-01T00:00:00+00:00",
            "family": "unit",
            "master_id": "MASTER-X",
            "reports": [],
            "success_criteria": {},
        }
        (trials / f"{tid}.json").write_text(json.dumps(trial))

        def fake_scan(grace_hours=48.0):
            return [
                {
                    "trial_id": tid,
                    "reason": "past_final_still_open",
                    "status": "RUNNING",
                    "final_at": trial["final_at"],
                }
            ]

        with mock.patch.object(w, "TRIALS_DIR", trials), mock.patch.object(
            w, "INBOX_DIR", inbox
        ), mock.patch.object(w, "STATE", state), mock.patch.object(
            w, "OUT_JSON", state / "latest.json"
        ), mock.patch.object(w, "OUT_MD", state / "latest.md"), mock.patch.object(
            w, "OUT_TXT", state / "latest.txt"
        ), mock.patch.object(w, "PREV_FP", state / "fp.txt"), mock.patch.object(
            w, "HISTORY", state / "hist.jsonl"
        ), mock.patch.object(w, "reindex", lambda: {"ok": True}), mock.patch.object(
            w, "scan_stale", fake_scan
        ), mock.patch.object(
            w, "check_report_completeness", lambda t: ["final_report path missing on disk"]
        ), mock.patch(
            "phase6.research.trial_cycle.INBOX_DIR", inbox
        ):
            board = w.build_watch(grace_hours=1.0, write_packets=True)
            assert board["n_actions"] >= 1, board
            act = next(a for a in board["actions"] if a["trial_id"] == tid)
            assert act["reason"] == "past_final_still_open"
            assert board["tg_deliver"] is True
            overdue = list(inbox.glob(f"OVERDUE_{tid}.md"))
            assert overdue, f"expected OVERDUE packet, got {list(inbox.iterdir())}"
            card = w.format_tg(board)
            assert tid in card
            assert "No auto-decide" in card
            board2 = w.build_watch(grace_hours=1.0, write_packets=False)
            assert board2["fingerprint"] == board["fingerprint"]


def test_quiet_when_all_closed():
    import phase6.research.trial_closeout_watch as w

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        trials = td_path / "trials"
        inbox = td_path / "inbox"
        state = td_path / "state"
        trials.mkdir()
        inbox.mkdir()
        state.mkdir()
        tid = "TEST-CLOSED-001"
        (trials / f"{tid}.json").write_text(
            json.dumps(
                {
                    "trial_id": tid,
                    "status": "CLOSED",
                    "final_at": "2020-01-01T00:00:00+00:00",
                }
            )
        )
        with mock.patch.object(w, "TRIALS_DIR", trials), mock.patch.object(
            w, "INBOX_DIR", inbox
        ), mock.patch.object(w, "STATE", state), mock.patch.object(
            w, "OUT_JSON", state / "latest.json"
        ), mock.patch.object(w, "OUT_MD", state / "latest.md"), mock.patch.object(
            w, "OUT_TXT", state / "latest.txt"
        ), mock.patch.object(w, "PREV_FP", state / "fp.txt"), mock.patch.object(
            w, "HISTORY", state / "hist.jsonl"
        ), mock.patch.object(w, "reindex", lambda: {"ok": True}), mock.patch.object(
            w, "scan_stale", lambda grace_hours=48.0: []
        ):
            board = w.build_watch(grace_hours=1.0, write_packets=True)
            assert board["n_actions"] == 0
            assert board["tg_deliver"] is False


if __name__ == "__main__":
    test_past_final_emits_action_and_packet()
    test_quiet_when_all_closed()
    print("OK trial_closeout_watch isolation")
