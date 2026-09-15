#!/usr/bin/env python3
"""Isolation tests — knife_filter_shadow R1."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core import knife_filter_shadow as kfs  # noqa: E402
from phase6.core.knife_filter_shadow import (  # noqa: E402
    KnifeConfig,
    arm_rsi_delay,
    arm_rsi_only,
    arm_rsi_reclaim,
    arm_standdown_c,
    evaluate_arms_on_closes,
    run_knife_filter_shadow,
    simulate_path,
    summarize_arm_table,
    synthetic_wash_closes,
    PairKnifeRow,
)


class KnifeFilterTests(unittest.TestCase):
    def test_reclaim_allows_bounce(self):
        closes = synthetic_wash_closes(reclaim=True, continue_down=False, wash_at=80)
        wash = 80
        v = arm_rsi_reclaim(closes, wash, lookback=6)
        self.assertTrue(v.allow, v.reason)

    def test_reclaim_denies_continue_down(self):
        closes = synthetic_wash_closes(reclaim=False, continue_down=True, wash_at=80)
        wash = 80
        v = arm_rsi_reclaim(closes, wash, lookback=6)
        self.assertFalse(v.allow)

    def test_delay_denies_new_low(self):
        closes = synthetic_wash_closes(reclaim=False, continue_down=True, wash_at=80)
        v = arm_rsi_delay(closes, 80, delay_min=1, delay_max=3)
        self.assertFalse(v.allow)

    def test_delay_allows_hold(self):
        closes = synthetic_wash_closes(reclaim=True, continue_down=False, wash_at=80)
        v = arm_rsi_delay(closes, 80, delay_min=1, delay_max=3)
        self.assertTrue(v.allow, v.reason)

    def test_standdown_blocks_elev(self):
        v = arm_standdown_c(elev_primary=True, wash_idx=10)
        self.assertFalse(v.allow)
        v2 = arm_standdown_c(elev_primary=False, wash_idx=10)
        self.assertTrue(v2.allow)

    def test_rsi_only_always_on_wash(self):
        v = arm_rsi_only(50)
        self.assertTrue(v.allow)

    def test_simulate_sl_on_continue_down(self):
        closes = synthetic_wash_closes(continue_down=True, reclaim=False, wash_at=50, n=100)
        cfg = KnifeConfig(sl_pct=0.04, horizon_bars=40)
        oc = simulate_path(closes, 50, 0, cfg=cfg)
        self.assertEqual(oc.exit_kind, "sl")
        self.assertTrue(oc.hit_sl_72h)

    def test_evaluate_arms_bundle(self):
        closes = synthetic_wash_closes(reclaim=True, wash_at=80)
        arms = evaluate_arms_on_closes(closes, wash_idx=80, elev_primary=False)
        self.assertIn("rsi_only", arms)
        self.assertTrue(arms["rsi_only"]["allow"])
        self.assertTrue(arms["rsi_reclaim"]["allow"])

    def test_summarize_table_n_tags(self):
        closes = synthetic_wash_closes(reclaim=True, wash_at=80)
        arms = evaluate_arms_on_closes(closes, wash_idx=80)
        row = PairKnifeRow(pair="TEST-USD", arms=arms)
        table = summarize_arm_table([row])
        self.assertEqual(table["rsi_only"]["claim"], "ATTENTION_ONLY")

    def test_run_shadow_with_injected_closes(self):
        closes = {
            "AAA-USD": synthetic_wash_closes(reclaim=True, wash_at=80),
            "BBB-USD": synthetic_wash_closes(continue_down=True, reclaim=False, wash_at=80),
        }
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            old_latest, old_crumbs, old_md = kfs.LATEST, kfs.CRUMBS, kfs.MD_PATH
            kfs.LATEST = td_path / "latest.json"
            kfs.CRUMBS = td_path / "crumbs.jsonl"
            kfs.MD_PATH = td_path / "out.md"
            try:
                summary = run_knife_filter_shadow(
                    closes_by_pair=closes,
                    pairs=list(closes.keys()),
                    write=True,
                )
                self.assertEqual(summary["n_pairs"], 2)
                self.assertFalse(summary["live_gate"])
                self.assertTrue(kfs.LATEST.exists())
                self.assertIn("rsi_reclaim", summary["arm_table"])
            finally:
                kfs.LATEST, kfs.CRUMBS, kfs.MD_PATH = old_latest, old_crumbs, old_md


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(KnifeFilterTests)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    n = result.testsRun
    print(f"Tests passed: {n}" if result.wasSuccessful() else f"FAIL {result}")
    raise SystemExit(0 if result.wasSuccessful() else 1)
