#!/usr/bin/env python3
"""Isolation: tryout scale-window kill — dead kindling → would_eject; ballast safe."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


class TestTryoutScaleWindow(unittest.TestCase):
    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.state = self.root / "state"
        self.state.mkdir()
        self.cfg_path = self.root / "tryout_scale_window.json"

        import phase6.core.tryout_scale_window as tw

        self.tw = tw
        self._orig = {
            "STATE_DIR": tw.STATE_DIR,
            "CONFIG_PATH": tw.CONFIG_PATH,
            "LATEST_PATH": tw.LATEST_PATH,
            "CRUMBS_PATH": tw.CRUMBS_PATH,
            "KILL_PATH": tw.KILL_PATH,
            "EJECT_RESULT_PATH": tw.EJECT_RESULT_PATH,
            "BOARD_SEEN_PATH": tw.BOARD_SEEN_PATH,
            "COOLOFF_PATH": tw.COOLOFF_PATH,
        }
        tw.STATE_DIR = self.state
        tw.CONFIG_PATH = self.cfg_path
        tw.LATEST_PATH = self.state / "latest.json"
        tw.CRUMBS_PATH = self.state / "crumbs.jsonl"
        tw.KILL_PATH = self.state / "KILL"
        tw.EJECT_RESULT_PATH = self.state / "eject_latest.json"
        tw.BOARD_SEEN_PATH = self.state / "board_seen.json"
        tw.COOLOFF_PATH = self.state / "cooloff.json"
        # Isolate from live post_proof_dwell state (TIA/SOL may be graduated after GO).
        self._ppd_patch = mock.patch(
            "phase6.core.post_proof_dwell.should_skip_scale_window_eject",
            return_value={
                "pair": "",
                "skip": False,
                "reasons": ["iso_no_dwell"],
                "live_apply": False,
                "apply_skip": False,
                "would_skip_if_live": False,
            },
        )
        self._ppd_patch.start()

    def tearDown(self) -> None:
        tw = self.tw
        for k, v in self._orig.items():
            setattr(tw, k, v)
        try:
            self._ppd_patch.stop()
        except Exception:
            pass
        self.td.cleanup()

    def test_phase3_no_scale_would_eject(self) -> None:
        tw = self.tw
        entry = (datetime.now(timezone.utc) - timedelta(hours=18)).isoformat()
        lot = {
            "tryout_shell": True,
            "live_scaled": False,
            "paper_scaled": True,
            "status": "paper_open",
            "entry_ts": entry,
            "shell_usd": 25.0,
            "phase": 3,
        }
        with mock.patch.object(tw, "_phase_structure", return_value={"phase": 3, "structure_ok": None, "detail": {}}):
            with mock.patch.object(tw, "_sentiment_for", return_value=0.02):
                with mock.patch.object(tw, "_held_usd_map", return_value={"HYPE-USD": 25.0}):
                    row = tw.evaluate_pair("HYPE-USD", lot=lot, held_usd=25.0, cfg=tw.DEFAULTS)
        self.assertTrue(row["would_eject"], row)
        self.assertEqual(row["scale_path"], "dead")

    def test_graduated_live_apply_clears_would_eject(self) -> None:
        """When dwell live_apply + graduated, would_eject clears (money path hold)."""
        tw = self.tw
        self._ppd_patch.stop()
        entry = (datetime.now(timezone.utc) - timedelta(hours=18)).isoformat()
        lot = {
            "tryout_shell": True,
            "live_scaled": False,
            "paper_scaled": True,
            "status": "paper_open",
            "entry_ts": entry,
            "shell_usd": 25.0,
            "phase": 3,
        }
        live_skip = {
            "pair": "SOL-USD",
            "skip": True,
            "reasons": ["graduated_hold"],
            "live_apply": True,
            "apply_skip": True,
            "would_skip_if_live": True,
        }
        with mock.patch(
            "phase6.core.post_proof_dwell.should_skip_scale_window_eject",
            return_value=live_skip,
        ):
            with mock.patch.object(
                tw, "_phase_structure", return_value={"phase": 3, "structure_ok": True, "detail": {}}
            ):
                with mock.patch.object(tw, "_sentiment_for", return_value=0.02):
                    with mock.patch.object(tw, "_held_usd_map", return_value={"SOL-USD": 25.0}):
                        row = tw.evaluate_pair("SOL-USD", lot=lot, held_usd=25.0, cfg=tw.DEFAULTS)
        self.assertFalse(row["would_eject"], row)
        self.assertEqual(row["status"], "dwell_hold")
        self.assertEqual(row["scale_path"], "graduated_hold")
        # restore default iso mock for any later tests in same instance
        self._ppd_patch = mock.patch(
            "phase6.core.post_proof_dwell.should_skip_scale_window_eject",
            return_value={
                "pair": "",
                "skip": False,
                "reasons": ["iso_no_dwell"],
                "live_apply": False,
                "apply_skip": False,
                "would_skip_if_live": False,
            },
        )
        self._ppd_patch.start()

    def test_fresh_shell_not_ejected(self) -> None:
        tw = self.tw
        entry = (datetime.now(timezone.utc) - timedelta(hours=0.5)).isoformat()
        lot = {
            "tryout_shell": True,
            "live_scaled": False,
            "status": "tryout_open",
            "entry_ts": entry,
            "shell_usd": 25.0,
        }
        row = tw.evaluate_pair("HYPE-USD", lot=lot, held_usd=25.0, cfg=tw.DEFAULTS)
        self.assertFalse(row["would_eject"], row)
        self.assertEqual(row["status"], "too_fresh")

    def test_ballast_never(self) -> None:
        tw = self.tw
        row = tw.evaluate_pair("BTC-USD", lot={"tryout_shell": True, "entry_ts": "2020-01-01T00:00:00+00:00"}, held_usd=25.0)
        self.assertFalse(row["would_eject"])
        self.assertEqual(row["status"], "never")

    def test_live_scaled_skips(self) -> None:
        tw = self.tw
        entry = (datetime.now(timezone.utc) - timedelta(hours=20)).isoformat()
        lot = {
            "tryout_shell": True,
            "live_scaled": True,
            "entry_ts": entry,
            "shell_usd": 50.0,
            "phase": 3,
        }
        row = tw.evaluate_pair("LINK-USD", lot=lot, held_usd=50.0, cfg=tw.DEFAULTS)
        self.assertFalse(row["would_eject"])
        self.assertEqual(row["status"], "scaled")

    def test_early_phase_open_path(self) -> None:
        tw = self.tw
        entry = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        lot = {
            "tryout_shell": True,
            "live_scaled": False,
            "entry_ts": entry,
            "shell_usd": 25.0,
        }
        with mock.patch.object(
            tw, "_phase_structure", return_value={"phase": 1, "structure_ok": True, "detail": {}}
        ):
            with mock.patch.object(tw, "_sentiment_for", return_value=0.4):
                row = tw.evaluate_pair("HYPE-USD", lot=lot, held_usd=25.0, cfg=tw.DEFAULTS)
        self.assertFalse(row["would_eject"], row)
        self.assertEqual(row["scale_path"], "live_kindling_possible")

    def test_eject_needs_go(self) -> None:
        tw = self.tw
        r = tw.eject_pair(object(), "TIA-USD", dry_run=False, go=False)
        self.assertEqual(r.get("error"), "need_go")
        r2 = tw.eject_pair(object(), "BTC-USD", dry_run=True, go=True)
        self.assertEqual(r2.get("error"), "ballast_refused")

    def test_capital_reason_is_strategy(self) -> None:
        from phase6.core.runner_capital_events import (
            _reason_is_scale_window_eject,
            _reason_is_strategy_profit_exit,
            load_buy_block_status,
        )
        import tempfile
        from pathlib import Path
        from datetime import datetime, timezone

        # Disposition: eject is strategy (not manual cash-park)
        self.assertTrue(_reason_is_strategy_profit_exit("tryout_scale_window_eject"))
        self.assertTrue(_reason_is_strategy_profit_exit("TRYOUT_SCALE_WINDOW_EJECT"))
        self.assertTrue(_reason_is_scale_window_eject("tryout_scale_window_eject"))

        # Buy-block: eject must NOT mint post_tp on top of cooloff SSOT
        with tempfile.TemporaryDirectory() as td:
            trades = Path(td) / "trades.jsonl"
            ts = datetime.now(timezone.utc).isoformat()
            trades.write_text(
                json.dumps(
                    {
                        "pair": "HYPE-USD",
                        "side": "SELL",
                        "reason": "tryout_scale_window_eject",
                        "timestamp": ts,
                    }
                )
                + "\n"
            )
            blocks = load_buy_block_status(
                jsonl_path=trades,
                include_runtime_controls=False,
            )
            self.assertNotIn("HYPE-USD", blocks, blocks)

    def test_board_tg_dedupe_and_empty(self) -> None:
        tw = self.tw
        board = {
            "enabled": True,
            "live_apply": False,
            "n_would_eject": 1,
            "rows": [
                {
                    "pair": "TIA-USD",
                    "would_eject": True,
                    "scale_path": "dead",
                    "phase": 3,
                    "hold_hours": 20.0,
                    "reasons": ["phase=3>=eject_ge 3 no_live_scale"],
                    "live_held_usd": 25.0,
                    "on_book": True,
                }
            ],
        }
        fp = tw.board_fingerprint(board)
        self.assertIn("TIA-USD", fp)
        body = tw.board_telegram_summary(board, force=True, mark_sent=False)
        self.assertIn("SCALE-WINDOW BOARD", body)
        self.assertIn("TIA-USD", body)
        self.assertIn("money off", body.lower())
        b1 = tw.board_telegram_summary(board, force=False, mark_sent=True)
        self.assertTrue(b1)
        b2 = tw.board_telegram_summary(board, force=False, mark_sent=True)
        self.assertEqual(b2, "")
        empty = tw.board_telegram_summary(
            {"enabled": True, "n_would_eject": 0, "rows": []}, force=True
        )
        self.assertEqual(empty, "")

    def test_registry_ghost_not_would_eject(self) -> None:
        tw = self.tw
        entry = (datetime.now(timezone.utc) - timedelta(hours=200)).isoformat()
        lot = {
            "tryout_shell": True,
            "live_scaled": False,
            "entry_ts": entry,
            "shell_usd": 25.0,
            "phase": 3,
        }
        with mock.patch.object(tw, "_held_usd_map", return_value={}):
            row = tw.evaluate_pair("ZEC-USD", lot=lot, held_usd=0.0, cfg=tw.DEFAULTS)
        self.assertFalse(row["would_eject"])
        self.assertEqual(row["status"], "registry_ghost")

    def test_post_eject_cooloff_file_and_config_default(self) -> None:
        """Cooloff hours are config SSOT; file write is durable even if capital store mocked."""
        tw = self.tw
        self.assertGreaterEqual(float(tw.DEFAULTS["post_eject_pair_cooloff_hours"]), 24.0)
        with mock.patch.object(
            tw,
            "set_post_eject_cooloff",
            wraps=None,
        ):
            pass
        # Direct file path: capital store may fail in isolation; file must still land
        with mock.patch.dict("sys.modules", {}):
            # Force capital path failure by patching import target
            import phase6.core.capital_controls_store as ccs

            with mock.patch.object(ccs, "primary_account_id", side_effect=RuntimeError("iso")):
                out = tw.set_post_eject_cooloff("LINK-USD", 48.0)
        self.assertTrue(out.get("file_ok"), out)
        self.assertTrue(out.get("ok"), out)
        self.assertFalse(out.get("capital_ok"), out)
        blob = json.loads(tw.COOLOFF_PATH.read_text(encoding="utf-8"))
        self.assertIn("LINK-USD", blob.get("pairs") or {})
        exp = float((blob["pairs"]["LINK-USD"]).get("expires_ts") or 0)
        self.assertGreater(exp, 0)

    def test_repeat_eject_escalates_cooloff(self) -> None:
        """2nd dead eject in lookback → 72h hygiene cooloff (not edge claim)."""
        tw = self.tw
        now = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)
        times = [
            (now - timedelta(days=2)).isoformat().replace("+00:00", "Z"),
            (now - timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        ]
        with mock.patch.object(
            tw,
            "count_recent_scale_window_ejects",
            return_value={"n": 2, "times": times, "pair": "LINK-USD"},
        ):
            meta = tw.effective_post_eject_cooloff_hours(
                "LINK-USD",
                {
                    **tw.DEFAULTS,
                    "post_eject_pair_cooloff_hours": 24.0,
                    "repeat_eject_min_count": 2,
                    "repeat_eject_cooloff_hours": 72.0,
                },
                now=now,
                include_this_eject=False,
            )
        self.assertEqual(meta["hours"], 72.0)
        self.assertIn("repeat_eject", meta["reason"])

        with mock.patch.object(
            tw,
            "count_recent_scale_window_ejects",
            return_value={"n": 0, "times": [], "pair": "SOL-USD"},
        ):
            base = tw.effective_post_eject_cooloff_hours(
                "SOL-USD",
                tw.DEFAULTS,
                now=now,
                include_this_eject=False,
            )
        self.assertEqual(base["hours"], float(tw.DEFAULTS["post_eject_pair_cooloff_hours"]))
        self.assertEqual(base["reason"], "base")

    def test_estimate_rt_fees_measure(self) -> None:
        tw = self.tw
        est = tw.estimate_rt_fees_usd(25.0, rate_per_side=0.006)
        self.assertAlmostEqual(est, 25.0 * 0.006 * 2, places=4)


if __name__ == "__main__":
    unittest.main()
