#!/usr/bin/env python3
"""Isolation: discovery retro board lead classes + why-not + no production path writes."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core import discovery_retro_board as drb


def test_lead_class_boundaries():
    assert drb.lead_class(None) == drb.CLASS_NEVER
    assert drb.lead_class(0.5) == drb.CLASS_COINCIDENT
    assert drb.lead_class(30) == drb.CLASS_SHORT
    assert drb.lead_class(100) == drb.CLASS_MEDIUM
    assert drb.lead_class(200) == drb.CLASS_EARLY


def test_classify_without_network(tmp_path: Path, monkeypatch=None):
    now = datetime(2026, 8, 29, 17, 0, tzinfo=timezone.utc)
    runs = [
        {
            "ts": now - timedelta(days=8),
            "contenders": ["AAA-USD", "BBB-USD"],
            "universe_n": 10,
            "prequal_n": 5,
            "quality_n": 3,
        },
        {
            "ts": now - timedelta(days=1),
            "contenders": ["SKR-USD"],
            "universe_n": 10,
            "prequal_n": 5,
            "quality_n": 3,
        },
        {
            "ts": now,
            "contenders": ["HNT-USD"],
            "universe_n": 10,
            "prequal_n": 5,
            "quality_n": 3,
            "schema": "pair_discovery_run_v2",
            "prequal_top": [
                {
                    "product_id": "HNT-USD",
                    "energy": 0.9,
                    "rank_energy": 1,
                    "ret_24h": 0.7,
                    "volume_quote_usd": 5e6,
                }
            ],
            "quality_fail": [],
            "quality_pass": [
                {
                    "product_id": "HNT-USD",
                    "quality_score": 0.97,
                    "reason": "ok",
                    "mom_3d": 0.5,
                }
            ],
            "contenders_detail": [
                {
                    "product_id": "HNT-USD",
                    "quality_score": 0.97,
                    "promote_eligible": False,
                    "reasons": ["pump_brake_ret_24h"],
                    "ret_24h": 0.7,
                }
            ],
        },
    ]
    pipe = [
        {
            "ts": now - timedelta(days=1),
            "eligible": ["SKR-USD"],
            "swaps": ["SOL-USD→SKR-USD"],
        }
    ]
    cfg = drb.RetroConfig(
        fetch_prices=False, write=False, run_quiet_features=False
    )

    early = drb.classify_gainer(
        "AAA-USD",
        {"ret_24h_pct": 20.0, "volume_quote_usd": 1e6},
        runs,
        pipe,
        {},
        now,
        cfg,
        sess=None,
    )
    assert early["lead_class"] == drb.CLASS_EARLY
    assert early["anchors"]["T-7d"]["present"] is True
    assert early["why_not_primary"] in ("picked", "coincident_late")

    coin = drb.classify_gainer(
        "HNT-USD",
        {"ret_24h_pct": 70.0, "volume_quote_usd": 5e6},
        runs,
        pipe,
        {},
        now,
        cfg,
        sess=None,
        discovery_idx={
            "prequal": {
                "HNT-USD": {
                    "product_id": "HNT-USD",
                    "energy": 0.9,
                    "rank_energy": 1,
                }
            },
            "quality": {},
            "contenders": {
                "HNT-USD": {
                    "product_id": "HNT-USD",
                    "promote_eligible": False,
                    "reasons": ["pump_brake_ret_24h"],
                    "ret_24h": 0.7,
                }
            },
            "active": set(),
            "cfg": {"min_quote_volume_24h_usd": 2_000_000.0},
            "ts": now.isoformat(),
        },
    )
    assert coin["lead_class"] == drb.CLASS_COINCIDENT
    assert coin["anchors"]["T0"]["present"] is True
    assert coin["anchors"]["T-7d"]["present"] is False
    assert coin["why_not_primary"] == "pump_brake"

    never = drb.classify_gainer(
        "ZKP-USD",
        {"ret_24h_pct": 30.0, "volume_quote_usd": 5e5},
        runs,
        pipe,
        {},
        now,
        cfg,
        sess=None,
        discovery_idx={
            "prequal": {},
            "quality": {},
            "contenders": {},
            "active": set(),
            "cfg": {"min_quote_volume_24h_usd": 2_000_000.0},
            "prequal_n_listed": 0,
        },
    )
    assert never["lead_class"] == drb.CLASS_NEVER
    assert never["methods"] == []
    assert never["why_not_primary"] == "thin_liquidity"

    # vol ok, not in prequal → below_prequal_cutoff
    loud_miss = drb.classify_gainer(
        "ELA-USD",
        {"ret_24h_pct": 25.0, "volume_quote_usd": 5_000_000.0},
        runs,
        pipe,
        {},
        now,
        cfg,
        sess=None,
        discovery_idx={
            "prequal": {},
            "quality": {},
            "contenders": {},
            "active": set(),
            "cfg": {"min_quote_volume_24h_usd": 2_000_000.0},
            "prequal_n_listed": 15,
        },
    )
    assert loud_miss["why_not_primary"] == "below_prequal_cutoff"

    # quality fail path
    qfail = drb.classify_gainer(
        "QFAIL-USD",
        {"ret_24h_pct": 12.0, "volume_quote_usd": 3e6},
        runs,
        pipe,
        {},
        now,
        cfg,
        sess=None,
        discovery_idx={
            "prequal": {
                "QFAIL-USD": {
                    "product_id": "QFAIL-USD",
                    "energy": 0.5,
                    "rank_energy": 4,
                }
            },
            "quality": {
                "QFAIL-USD": {
                    "product_id": "QFAIL-USD",
                    "quality_score": 0.2,
                    "pass_gate": False,
                    "reason": "quality 0.200 < 0.350",
                }
            },
            "contenders": {},
            "active": set(),
            "cfg": {
                "min_quote_volume_24h_usd": 2_000_000.0,
                "min_quality_score": 0.35,
            },
        },
    )
    assert qfail["why_not_primary"] == "quality_fail"

    short = drb.classify_gainer(
        "SKR-USD",
        {"ret_24h_pct": 15.0, "volume_quote_usd": 2e6},
        runs,
        pipe,
        {"SKR-USD": {"arms": ["baseline_hybrid"], "n": 2}},
        now,
        cfg,
        sess=None,
    )
    assert short["lead_class"] == drb.CLASS_SHORT
    assert "basket_swap_cf:baseline_hybrid" in short["methods"]
    assert short["pipeline_swaps"]
    assert short["why_not_primary"] in ("picked", "coincident_late")

    # O-USD must not match inside AERO-USD swap labels
    o_pipe = [{"ts": now, "eligible": [], "swaps": ["ARB-USD→AERO-USD", "DOGE-USD→BICO-USD"]}]
    o = drb.classify_gainer(
        "O-USD",
        {"ret_24h_pct": 10.0, "volume_quote_usd": 1e5},
        runs,
        o_pipe,
        {},
        now,
        cfg,
        sess=None,
        discovery_idx={
            "prequal": {},
            "quality": {},
            "contenders": {},
            "active": set(),
            "cfg": {"min_quote_volume_24h_usd": 2_000_000.0},
        },
    )
    assert o["pipeline_swaps"] == []
    assert "discovery_pipeline_swap_proposal" not in o["methods"]
    assert o["why_not_primary"] == "thin_liquidity"


def test_quiet_features_offline():
    # Synthetic candles: quiet mid, then volume jump + modest expand
    candles = []
    t0 = 1_700_000_000
    price = 1.0
    for i in range(200):
        vol = 10.0 if i < 170 else (80.0 if i >= 176 else 12.0)
        hi = price * 1.01
        lo = price * 0.99
        if i >= 176:
            price *= 1.005
            hi = price * 1.02
            lo = price * 0.99
        candles.append([t0 + i * 3600, lo, hi, price, price, vol])
    btc = []
    bp = 100.0
    for i in range(200):
        btc.append([t0 + i * 3600, bp * 0.999, bp * 1.001, bp, bp, 1000.0])
    q = drb.compute_quiet_features(candles, btc_candles=btc)
    assert q["ok"] is True
    assert "quiet_early_score" in q
    assert q["liq_jump_24_vs_3d"] is not None
    assert q["btc_rel_3d"] is not None


def test_pair_in_swap_label():
    assert drb._pair_in_swap_label("SKR-USD", "SOL-USD→SKR-USD")
    assert not drb._pair_in_swap_label("O-USD", "ARB-USD→AERO-USD")
    assert drb._pair_in_swap_label("AERO-USD", "ARB-USD→AERO-USD")


def test_persist_does_not_touch_config(tmp_path: Path):
    # Redirect outputs into tmp
    drb.OUT_JSON = tmp_path / "discovery_retro_board_latest.json"
    drb.OUT_JSONL = tmp_path / "discovery_retro_board_runs.jsonl"
    drb.OUT_MD = tmp_path / "DISCOVERY_RETRO_BOARD_LATEST.md"
    board = {
        "schema": "discovery_retro_board_v2",
        "as_of": "2026-08-29T00:00:00+00:00",
        "config": {},
        "discovery_runs_n": 0,
        "discovery_runs_from": None,
        "discovery_runs_to": None,
        "gainer_retro": [
            {
                "product_id": "AAA-USD",
                "ret_24h_pct": 10.0,
                "volume_quote_usd": 1e6,
                "lead_class": "NEVER",
                "watch_style": "absent",
                "why_not_primary": "thin_liquidity",
                "why_not": "thin_liquidity: vol under floor",
                "quiet_early_score": 0.4,
                "methods": [],
                "anchors": {},
            }
        ],
        "forward_book": {"summary": {}, "rows": [], "contenders_union": []},
        "lead_class_counts": {"NEVER": 1},
        "why_not_counts": {"thin_liquidity": 1},
        "method_hypotheses": ["test"],
        "plain_english": "test board",
    }
    paths = drb.persist_board(board)
    assert Path(paths["json"]).exists()
    assert Path(paths["md"]).exists()
    md = Path(paths["md"]).read_text(encoding="utf-8")
    assert "Discovery retro board" in md
    assert "shadow" in md.lower()
    assert "Why not" in md
    assert "thin_liquidity" in md
    assert Path(paths["jsonl"]).exists()


def main() -> int:
    test_lead_class_boundaries()
    test_classify_without_network(Path("/tmp"))
    test_quiet_features_offline()
    test_pair_in_swap_label()
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        test_persist_does_not_touch_config(Path(td))
    print("PASS isolation discovery_retro_board")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
