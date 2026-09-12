#!/usr/bin/env python3
"""Isolation: PC-03 tryout readiness board (floors, sensor, can_buy)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core.tryout_readiness import (
    PairDoor,
    build_readiness_payload,
    classify_sensor,
    live_entry_floor,
    next_slot_pt,
    render_markdown,
    write_artifacts,
)

PT = ZoneInfo("America/Los_Angeles")


class TestTryoutReadinessPC03(unittest.TestCase):
    def test_live_floor_ssot_max(self):
        # recovery new-pair 0.35 beats tryout 0.30
        self.assertEqual(
            live_entry_floor(
                min_sentiment=0.25,
                min_sentiment_new_pair=0.35,
                quality_tryout_min_sentiment=0.30,
                is_new_pair=True,
            ),
            0.35,
        )
        # tryout can win if higher
        self.assertEqual(
            live_entry_floor(
                min_sentiment_new_pair=0.25,
                quality_tryout_min_sentiment=0.40,
                is_new_pair=True,
            ),
            0.40,
        )

    def test_sensor_aged_out_not_broken(self):
        s = classify_sensor(
            mode="x_reddit_bridge",
            eng_scores={"ETH-USD": 0.0, "AVAX-USD": 0.0},
            x_posts_total=10,
            x_age_hours=9.0,
            reddit_nz=0,
            free_nz=1,
            floor=0.35,
        )
        self.assertFalse(s["broken"])
        self.assertIn("aged_out", s["class"])

    def test_sensor_stuck_zero_flag(self):
        s = classify_sensor(
            mode="x",
            eng_scores={"ETH-USD": 0.0},
            x_posts_total=0,
            x_age_hours=0.2,
            reddit_nz=0,
            free_nz=0,
            floor=0.35,
        )
        self.assertTrue(s["broken"])

    def test_can_buy_requires_allowed_door(self):
        floors = {
            "min_sentiment": 0.25,
            "min_sentiment_new_pair": 0.35,
            "quality_tryout_min_sentiment": 0.30,
            "live_floor_used": 0.35,
            "max_rsi": 55.0,
        }
        sensor = {"broken": False, "class": "ok", "detail": "ok"}
        blocked = [
            PairDoor(pair="ETH-USD", eligible=True, allowed=False, reasons=["sentiment 0.01 < min 0.35"], eng_sent=0.01)
        ]
        p = build_readiness_payload(
            doors=blocked,
            floors=floors,
            sensor=sensor,
            cash_usd=200.0,
            seats_used_today=0,
            max_new_seats_per_day=2,
            tryout_cap_usd=75.0,
            eligible_tryout_pairs=["ETH-USD"],
            regime="flat",
            equity_health="soft_down",
            sent_mode="x",
            next_x_refresh_pt="20:50",
            next_rebalance_pt="~21:00",
        )
        self.assertFalse(p["can_buy_before_next_rebalance"])

        open_door = [
            PairDoor(pair="ETH-USD", eligible=True, allowed=True, reasons=["entry_ok"], eng_sent=0.42, rsi=40.0)
        ]
        p2 = build_readiness_payload(
            doors=open_door,
            floors=floors,
            sensor=sensor,
            cash_usd=200.0,
            seats_used_today=0,
            max_new_seats_per_day=2,
            tryout_cap_usd=75.0,
            eligible_tryout_pairs=["ETH-USD"],
            regime="flat",
            equity_health="soft_down",
            sent_mode="x",
            next_x_refresh_pt="20:50",
            next_rebalance_pt="~21:00",
        )
        self.assertTrue(p2["can_buy_before_next_rebalance"])

    def test_free_tee_does_not_imply_can_buy(self):
        """Warm free tee on door with eng 0 → still cannot buy."""
        floors = {"live_floor_used": 0.35, "min_sentiment_new_pair": 0.35, "quality_tryout_min_sentiment": 0.3}
        door = PairDoor(
            pair="AVAX-USD",
            eligible=True,
            force_eligible=True,
            allowed=False,
            eng_sent=0.0,
            free_tee=0.16,
            reasons=["sentiment 0.000 < min 0.35"],
            note="Free/tee warm but does NOT clear REGIME-CASH.",
        )
        p = build_readiness_payload(
            doors=[door],
            floors=floors,
            sensor={"broken": False, "class": "aged_out", "detail": "x"},
            cash_usd=200.0,
            seats_used_today=0,
            max_new_seats_per_day=2,
            tryout_cap_usd=75.0,
            eligible_tryout_pairs=["AVAX-USD"],
            regime="flat",
            equity_health="declining",
            sent_mode="x_reddit_bridge",
            next_x_refresh_pt="20:50",
            next_rebalance_pt="~21:00",
        )
        self.assertFalse(p["can_buy_before_next_rebalance"])
        self.assertIn("Free/tee", p["plain_english"] + door.note)

    def test_write_artifacts(self):
        floors = {"live_floor_used": 0.35}
        p = build_readiness_payload(
            doors=[PairDoor(pair="ETH-USD", eligible=True, allowed=False)],
            floors=floors,
            sensor={"broken": False, "class": "x", "detail": "d"},
            cash_usd=100.0,
            seats_used_today=0,
            max_new_seats_per_day=1,
            tryout_cap_usd=75.0,
            eligible_tryout_pairs=["ETH-USD"],
            regime="flat",
            equity_health="ok",
            sent_mode="x",
            next_x_refresh_pt="08:50",
            next_rebalance_pt="~09:00",
        )
        with tempfile.TemporaryDirectory() as td:
            jp = Path(td) / "r.json"
            mp = Path(td) / "r.md"
            write_artifacts(p, state_path=jp, report_path=mp)
            data = json.loads(jp.read_text())
            self.assertEqual(data["schema"], "tryout_readiness_v1")
            md = mp.read_text()
            self.assertIn("can_buy_before_next_rebalance", md)
            self.assertIn(render_markdown(p).split("\n")[0], md.split("\n")[0])

    def test_next_slot(self):
        now = datetime(2026, 9, 11, 17, 0, tzinfo=PT)
        lbl, dt = next_slot_pt(now, ((8, 50), (20, 50)))
        self.assertEqual(lbl, "20:50")
        self.assertEqual(dt.hour, 20)


if __name__ == "__main__":
    unittest.main()
