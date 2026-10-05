#!/usr/bin/env python3
"""Isolation tests: post_proof_dwell (no live I/O money path)."""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core import post_proof_dwell as ppd  # noqa: E402


def _ts(h_ago: float = 0.0) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=h_ago)


def _cfg(tmp: Path, live: bool = False) -> Dict[str, Any]:
    return {
        "schema": ppd.SCHEMA,
        "enabled": True,
        "live_apply": live,
        "shadow_log": True,
        "proof": {
            "min_tp_net_usd": 0.50,
            "min_tp_net_pct": 0.015,
            "min_clean_green_rts": 2,
            "clean_rt_lookback_days": 14,
            "accept_live_kindling_fill": True,
        },
        "dwell": {
            "default_hours": 168.0,
            "extend_hours_on_reproof": 168.0,
            "max_hours": 504.0,
            "sleeve_cap_usd": 150.0,
            "sleeve_cap_nav_frac": 0.08,
        },
        "tryout_block": {
            "block_new_shell_while_graduated": True,
            "post_tp_tryout_ban_hours": 48.0,
            "post_tp_tryout_ban_if_not_graduated": True,
        },
        "scale_window": {"skip_eject_while_graduated": True},
        "demote": {"on_sl": True, "on_hard_dump": True, "post_sl_cooloff_hours": 72.0},
    }


def _bind_tmp(tmp: Path) -> None:
    ppd.STATE_DIR = tmp  # type: ignore[attr-defined]
    ppd.STATE_PATH = tmp / "post_proof_dwell.json"  # type: ignore[attr-defined]
    ppd.SHADOW_CRUMBS = tmp / "crumbs.jsonl"  # type: ignore[attr-defined]
    ppd.KILL_PATH = tmp / "post_proof_dwell_KILL"  # type: ignore[attr-defined]


def test_tp_stamps_graduate() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _bind_tmp(tmp)
        cfg = _cfg(tmp)
        trade = {
            "pair": "LINK-USD",
            "side": "SELL",
            "reason": "take_profit_fixed_tp",
            "pnl": 4.5,
            "pnl_pct": 0.04,
            "total_fees": 0.4,
            "pnl_is_net": True,
            "order_id": "t1",
        }
        res = ppd.stamp_proof_from_sell(trade, cfg=cfg, persist=True)
        assert res.get("stamped") is True, res
        assert ppd.is_graduated("LINK-USD")
        wb = ppd.would_block_tryout("LINK-USD", cfg=cfg)
        assert wb["block"] is True
        assert wb["apply_block"] is False  # live_apply off
        sk = ppd.should_skip_scale_window_eject("LINK-USD", cfg=cfg)
        assert sk["skip"] is True
        assert sk["apply_skip"] is False


def test_eject_does_not_graduate() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _bind_tmp(tmp)
        cfg = _cfg(tmp)
        trade = {
            "pair": "HYPE-USD",
            "side": "SELL",
            "reason": "tryout_scale_window_eject",
            "pnl": 0.1,
            "total_fees": 0.4,
        }
        res = ppd.stamp_proof_from_sell(trade, cfg=cfg, persist=True)
        assert res.get("stamped") is False
        assert not ppd.is_graduated("HYPE-USD")


def test_sl_demotes() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _bind_tmp(tmp)
        cfg = _cfg(tmp)
        ppd.stamp_proof_from_sell(
            {
                "pair": "SOL-USD",
                "side": "SELL",
                "reason": "take_profit_trail",
                "pnl": 2.4,
                "pnl_pct": 0.03,
                "pnl_is_net": True,
            },
            cfg=cfg,
            persist=True,
        )
        assert ppd.is_graduated("SOL-USD")
        dem = ppd.stamp_proof_from_sell(
            {
                "pair": "SOL-USD",
                "side": "SELL",
                "reason": "stop_loss_exchange",
                "pnl": -1.2,
            },
            cfg=cfg,
            persist=True,
        )
        assert dem.get("demoted") is True
        assert not ppd.is_graduated("SOL-USD")
        wb = ppd.would_block_tryout("SOL-USD", cfg=cfg)
        assert wb["block"] is True  # post-SL ban
        assert any("tryout_ban" in r for r in wb["reasons"])


def test_expiry() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _bind_tmp(tmp)
        cfg = _cfg(tmp)
        past = _ts(200)
        ppd.stamp_proof_from_sell(
            {
                "pair": "ZEC-USD",
                "side": "SELL",
                "reason": "take_profit_fixed_tp",
                "pnl": 2.0,
                "pnl_pct": 0.05,
                "pnl_is_net": True,
            },
            cfg=cfg,
            now=past,
            persist=True,
        )
        # default 168h — 200h later expired
        assert not ppd.is_graduated("ZEC-USD", now=_ts(0))


def test_live_apply_blocks_composer() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _bind_tmp(tmp)
        cfg = _cfg(tmp, live=True)
        ppd.stamp_proof_from_sell(
            {
                "pair": "LINK-USD",
                "side": "SELL",
                "reason": "take_profit_trail",
                "pnl": 2.0,
                "pnl_is_net": True,
                "pnl_pct": 0.02,
            },
            cfg=cfg,
            persist=True,
        )
        hook = ppd.apply_to_composer_candidate(
            {"pair": "LINK-USD", "eng": 0.5, "rsi": 40},
            cfg=cfg,
            persist=True,
        )
        assert hook["would_block_if_live"] is True
        assert hook["skip_seat"] is True  # live on
        assert (tmp / "crumbs.jsonl").exists()


def test_shadow_composer_no_skip() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _bind_tmp(tmp)
        cfg = _cfg(tmp, live=False)
        ppd.stamp_proof_from_sell(
            {
                "pair": "LINK-USD",
                "side": "SELL",
                "reason": "take_profit_trail",
                "pnl": 2.0,
                "pnl_is_net": True,
                "pnl_pct": 0.02,
            },
            cfg=cfg,
            persist=True,
        )
        hook = ppd.apply_to_composer_candidate(
            {"pair": "LINK-USD", "eng": 0.5, "rsi": 40},
            cfg=cfg,
            persist=True,
        )
        assert hook["would_block_if_live"] is True
        assert hook["skip_seat"] is False  # shadow


def test_below_min_meat_not_proof() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _bind_tmp(tmp)
        cfg = _cfg(tmp)
        res = ppd.stamp_proof_from_sell(
            {
                "pair": "ADA-USD",
                "side": "SELL",
                "reason": "take_profit_fixed_tp",
                "pnl": 0.05,
                "pnl_pct": 0.002,
                "pnl_is_net": True,
            },
            cfg=cfg,
            persist=True,
        )
        assert res.get("stamped") is False


def test_snapshot_and_rebuild() -> None:
    rows = [
        {
            "pair": "LINK-USD",
            "side": "SELL",
            "reason": "take_profit_fixed_tp",
            "pnl": 4.0,
            "pnl_pct": 0.03,
            "pnl_is_net": True,
            "timestamp": _ts(10).isoformat(),
        },
        {
            "pair": "HYPE-USD",
            "side": "SELL",
            "reason": "tryout_scale_window_eject",
            "pnl": -0.2,
            "timestamp": _ts(5).isoformat(),
        },
    ]
    st = ppd.rebuild_state_from_ledger(rows, cfg=_cfg(Path("/tmp")))
    assert "LINK-USD" in (st.get("pairs") or {})
    assert (st.get("pairs") or {}).get("LINK-USD", {}).get("status") == "graduated_hold"


def main() -> None:
    tests = [
        test_tp_stamps_graduate,
        test_eject_does_not_graduate,
        test_sl_demotes,
        test_expiry,
        test_live_apply_blocks_composer,
        test_shadow_composer_no_skip,
        test_below_min_meat_not_proof,
        test_snapshot_and_rebuild,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"OK {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
            raise
    print(f"{len(tests) - failed}/{len(tests)} passed")


if __name__ == "__main__":
    main()
