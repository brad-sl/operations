#!/usr/bin/env python3
"""Isolation: tryout lifecycle B–G modules (taxonomy, seat ledger, grow guards).

No live orders. Temp dirs only for registry writes.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestExitTaxonomy(unittest.TestCase):
    def test_closed_classes(self):
        from phase6.core.tryout_exit_taxonomy import (
            CLOSED_DUAL_PEAK,
            CLOSED_SCALE_WINDOW,
            CLOSED_SL,
            CLOSED_TP_TRAIL,
            classify_closed_class,
            closed_class_to_dwell_stage,
            stamp_exit_taxonomy,
        )

        self.assertEqual(classify_closed_class("stop_loss_exchange"), CLOSED_SL)
        self.assertEqual(classify_closed_class("tryout_scale_window_eject"), CLOSED_SCALE_WINDOW)
        self.assertEqual(classify_closed_class("lifecycle_dual_peak:peak"), CLOSED_DUAL_PEAK)
        self.assertEqual(classify_closed_class("trail_tp_hit"), CLOSED_TP_TRAIL)
        self.assertEqual(closed_class_to_dwell_stage(CLOSED_SCALE_WINDOW), "exit_scale_window")
        stamped = stamp_exit_taxonomy(
            {"side": "SELL", "reason": "tryout_scale_window_eject", "pair": "HYPE-USD"}
        )
        self.assertEqual(stamped["exit_class"], CLOSED_SCALE_WINDOW)
        self.assertTrue(stamped.get("exit_taxonomy_schema"))

    def test_attr_and_dwell_delegate(self):
        from phase6.core.attribution_rt_weekly import classify_exit_reason
        from phase6.core.pair_funnel_dwell import classify_exit_stage

        self.assertEqual(
            classify_exit_reason({"reason": "tryout_scale_window_eject"}),
            "scale_window_eject",
        )
        self.assertEqual(classify_exit_stage("tryout_scale_window_eject"), "exit_scale_window")
        self.assertEqual(classify_exit_stage("stop_loss"), "exit_sl")


class TestSeatLedger(unittest.TestCase):
    def test_scale_path_and_ghost_purge(self):
        from phase6.core import tryout_seat_ledger as L

        held = {"HYPE-USD": 25.0, "ZEC-USD": 0.0, "BTC-USD": 300.0}
        lots = {
            "HYPE-USD": {
                "status": "tryout_open",
                "tryout_shell": True,
                "live_scaled": False,
                "shell_usd": 25,
            },
            "ZEC-USD": {
                "status": "scored",
                "tryout_shell": True,
                "live_scaled": False,
                "score": {"excess_r": 0.01},
            },
        }
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            open_path = tdp / "open_lots.json"
            open_path.write_text(json.dumps({"lots": lots}))
            archive = tdp / "ghosts.jsonl"
            with mock.patch.object(L, "OPEN_LOTS_PATH", open_path), mock.patch.object(
                L, "GHOST_ARCHIVE_PATH", archive
            ), mock.patch.object(L, "LATEST_PATH", tdp / "ledger.json"), mock.patch.object(
                L, "SCALE_WINDOW_LATEST", tdp / "sw.json"
            ):
                (tdp / "sw.json").write_text(
                    json.dumps(
                        {
                            "rows": [
                                {
                                    "pair": "HYPE-USD",
                                    "would_eject": False,
                                    "status": "open",
                                }
                            ]
                        }
                    )
                )
                led = L.build_seat_ledger(
                    pairs=["HYPE-USD", "ZEC-USD", "BTC-USD"],
                    persist=True,
                    held_map=held,
                )
                self.assertIn("HYPE-USD", led["open_shells"])
                self.assertIn("ZEC-USD", led["ghosts"])
                sp = L.scale_path_for_pairs(["HYPE-USD", "ZEC-USD"], ledger=led)
                self.assertEqual(sp["HYPE-USD"]["scale_path"], "open")
                self.assertEqual(sp["ZEC-USD"]["scale_path"], "ghost")

                dry = L.purge_ghost_lots(dry_run=True, held_map=held)
                self.assertGreaterEqual(dry["n_removed"], 1)
                self.assertIn("ZEC-USD", dry["removed_pairs"])
                # dry run leaves file intact
                still = json.loads(open_path.read_text())
                self.assertIn("ZEC-USD", still["lots"])

                live = L.purge_ghost_lots(dry_run=False, held_map=held)
                self.assertGreaterEqual(live["n_removed"], 1)
                after = json.loads(open_path.read_text())
                self.assertNotIn("ZEC-USD", after.get("lots") or {})
                self.assertIn("HYPE-USD", after.get("lots") or {})
                self.assertTrue(archive.exists())

    def test_purge_never_drops_held_shell(self):
        """TL-P1-HELD: held ≥ MIN never purged even if status looks terminal-ish."""
        from phase6.core import tryout_seat_ledger as L

        held = {"HYPE-USD": 25.0}
        lots = {
            "HYPE-USD": {
                "status": "tryout_open",
                "tryout_shell": True,
                "live_scaled": False,
            }
        }
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            open_path = tdp / "open_lots.json"
            open_path.write_text(json.dumps({"lots": lots}))
            with mock.patch.object(L, "OPEN_LOTS_PATH", open_path), mock.patch.object(
                L, "GHOST_ARCHIVE_PATH", tdp / "g.jsonl"
            ), mock.patch.object(L, "LATEST_PATH", tdp / "ledger.json"), mock.patch.object(
                L, "SCALE_WINDOW_LATEST", tdp / "sw.json"
            ):
                (tdp / "sw.json").write_text("{}")
                out = L.purge_ghost_lots(dry_run=False, held_map=held)
                self.assertEqual(out["n_removed"], 0)
                after = json.loads(open_path.read_text())
                self.assertIn("HYPE-USD", after["lots"])

    def test_purge_refuses_open_row_when_held_unreliable(self):
        """Empty auto-loaded held map must not wipe tryout_open rows."""
        from phase6.core import tryout_seat_ledger as L

        lots = {
            "HYPE-USD": {
                "status": "tryout_open",
                "tryout_shell": True,
            },
            "ZEC-USD": {
                "status": "scored",
                "tryout_shell": True,
            },
        }
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            open_path = tdp / "open_lots.json"
            open_path.write_text(json.dumps({"lots": lots}))
            with mock.patch.object(L, "OPEN_LOTS_PATH", open_path), mock.patch.object(
                L, "GHOST_ARCHIVE_PATH", tdp / "g.jsonl"
            ), mock.patch.object(L, "LATEST_PATH", tdp / "ledger.json"), mock.patch.object(
                L, "SCALE_WINDOW_LATEST", tdp / "sw.json"
            ), mock.patch.object(L, "load_held_usd_map", return_value={}):
                (tdp / "sw.json").write_text("{}")
                # held_map=None → empty load → refuse open HYPE, still purge terminal ZEC
                out = L.purge_ghost_lots(dry_run=False, held_map=None)
                self.assertFalse(out["held_trustworthy"])
                self.assertIn("HYPE-USD", [r["pair"] for r in out.get("refused") or []])
                after = json.loads(open_path.read_text())
                self.assertIn("HYPE-USD", after["lots"])
                self.assertNotIn("ZEC-USD", after.get("lots") or {})
                self.assertIn("ZEC-USD", out["removed_pairs"])


class TestGrowHonesty(unittest.TestCase):
    def test_one_step_safety_defaults(self):
        from phase6.core.tryout_scale_up_live import LIVE_SAFETY

        self.assertTrue(LIVE_SAFETY.get("one_step_per_lot"))
        self.assertLessEqual(float(LIVE_SAFETY.get("max_total_after_step_usd_hard") or 0), 100.0)


class TestDisciplineAndScaleWindowArmed(unittest.TestCase):
    def test_live_apply_true_after_brad_go(self):
        """Brad GO 2026-10-01 armed both; isolation asserts ON not OFF."""
        cfg = json.loads(
            (ROOT / "config" / "tryout_decision_discipline.json").read_text()
        )
        self.assertTrue(bool(cfg.get("live_apply")))
        sw = json.loads((ROOT / "config" / "tryout_scale_window.json").read_text())
        self.assertTrue(bool(sw.get("live_apply")))
        knife = json.loads((ROOT / "config" / "knife_filter.json").read_text())
        self.assertTrue(bool(knife.get("live_gate")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
