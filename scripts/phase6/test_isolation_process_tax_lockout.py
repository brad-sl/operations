#!/usr/bin/env python3
"""Isolation: 72h post-SL + same-day pair lockout on evaluate path (ARCH-4 cannot bypass).

Doctrine (funnel-first / rare perma-block):
  - Default path = qualification funnel + expiring process locks
    (72h post-SL, same-day seat, missfire, novelty, regime).
  - buy_block_pairs = exceptional operator hard list only (toxic beyond funnel).
  - Live scars today: RAVE-USD, UNI-USD — not every wounded tryout name.
  - Do NOT pin LINK (etc.) into permanent buy_block to silence a gate.
    Bug-class SLs → ledger correction + time-bounded waiver, not forever ban.
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.runner_capital_events import pair_process_tax_lockout_reasons
from phase6.core.regime_cash_policy import collect_buy_block_pairs, load_policy
from phase6.core.limit_first_buy import (
    LimitFirstPolicy,
    policy_from_config,
    should_market_fallback_on_unfilled,
)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_jsonl(path: Path, rows: list) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_sl_12h_ago_blocks_tryout() -> None:
    now = datetime.now(timezone.utc)
    sl_ts = now - timedelta(hours=12)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "trades.jsonl"
        _write_jsonl(
            p,
            [
                {
                    "timestamp": _iso(sl_ts),
                    "pair": "LINK-USD",
                    "side": "SELL",
                    "qty": 5.82,
                    "reason": "stop_loss_exchange",
                    "exit_reason": "stop_loss_exchange",
                }
            ],
        )
        reasons = pair_process_tax_lockout_reasons("LINK-USD", jsonl_path=p)
        assert reasons, reasons
        assert any("sl" in r.lower() or "stop" in r.lower() or "post_sl" in r.lower() for r in reasons), reasons
        print("PASS 12h post-SL blocks LINK")


def test_same_day_buy_blocks_second_seat() -> None:
    now = datetime.now(timezone.utc)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "trades.jsonl"
        _write_jsonl(
            p,
            [
                {
                    "timestamp": _iso(now - timedelta(hours=1)),
                    "pair": "ETH-USD",
                    "side": "BUY",
                    "qty": 0.02,
                    "reason": "rebalance_buy",
                }
            ],
        )
        reasons = pair_process_tax_lockout_reasons("ETH-USD", jsonl_path=p)
        assert "same_day_pair_buy" in reasons, reasons
        print("PASS same-day pair BUY blocks second seat")


def test_old_sl_does_not_block() -> None:
    now = datetime.now(timezone.utc)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "trades.jsonl"
        _write_jsonl(
            p,
            [
                {
                    "timestamp": _iso(now - timedelta(hours=80)),
                    "pair": "SOL-USD",
                    "side": "SELL",
                    "qty": 1.0,
                    "reason": "stop_loss_exchange",
                    "exit_reason": "stop_loss_exchange",
                }
            ],
        )
        reasons = pair_process_tax_lockout_reasons("SOL-USD", jsonl_path=p)
        assert not any("post_sl" in r or "stop" in r.lower() for r in reasons), reasons
        print("PASS 80h-old SL does not block")


def test_live_config_tryout_ioc_off() -> None:
    cfg = json.loads((ROOT / "config" / "trading_config_phase6.json").read_text())
    p = policy_from_config(cfg)
    assert float(p.market_fallback_max_usd or 0) == 0.0, p
    assert should_market_fallback_on_unfilled(p, 75.0) is False
    # knob still works if explicitly set
    on = LimitFirstPolicy(market_fallback_max_usd=75.0)
    assert should_market_fallback_on_unfilled(on, 75.0) is True
    print("PASS live tryout IOC fallback OFF; knob still honours explicit 75")


def test_live_hard_block_ssot_scar_pairs_only() -> None:
    """Perma-block = exceptional. Live SSOT is RAVE/UNI scars — LINK not forever-banned.

    Soft rebalance_cap_usd may still be 75; tryout shell ($25x4) is a separate path.
    Hard list must not become a second membership jail for every process wound.
    """
    cfg = json.loads((ROOT / "config" / "trading_config_phase6.json").read_text())
    gs = cfg.get("global_settings") or {}
    cap = float(gs.get("rebalance_cap_usd") or 0)
    # Soft cap still documented at 75 in many places; fail loud only if missing/zero
    assert cap > 0, f"rebalance_cap_usd missing/zero: {cap}"
    blocks = list(gs.get("buy_block_pairs") or [])
    assert "RAVE-USD" in blocks, f"RAVE scar missing: {blocks}"
    assert "UNI-USD" in blocks, f"UNI scar missing: {blocks}"
    assert "LINK-USD" not in blocks, (
        "LINK-USD must not live in buy_block_pairs; funnel + expiring post-SL, "
        f"not perma-block. Got: {blocks}"
    )
    pol = load_policy()
    collected = collect_buy_block_pairs(pol)
    assert "RAVE-USD" in collected and "UNI-USD" in collected, collected
    assert "LINK-USD" not in collected, collected
    print("PASS hard-block SSOT = RAVE/UNI scars only (LINK not perma-blocked)")


def test_buy_block_waivers_time_bounded() -> None:
    """No unlimited scope=all waivers (AGENT_QUALITY_GATES law)."""
    path = ROOT / "data" / "state" / "buy_block_waivers.json"
    if not path.exists():
        print("PASS waivers file absent (ok)")
        return
    raw = json.loads(path.read_text(encoding="utf-8"))
    pairs = raw.get("pairs") if isinstance(raw, dict) else None
    items: list[dict] = []
    if isinstance(pairs, dict):
        for k, v in pairs.items():
            if isinstance(v, dict):
                items.append({"pair": k, **v})
    elif isinstance(raw, dict) and "waivers" in raw:
        items = [w for w in (raw.get("waivers") or []) if isinstance(w, dict)]
    for w in items:
        scope = str(w.get("scope") or "")
        exp = w.get("expires_ts")
        if scope == "all" and exp in (None, "", "null"):
            raise AssertionError(f"unlimited scope=all waiver forbidden: {w}")
    print("PASS buy_block_waivers time-bounded (no unlimited scope=all)")


def test_get_recent_trades_accepts_hours() -> None:
    from phase6.core.trade_ledger import TradeLedger

    with tempfile.TemporaryDirectory() as td:
        led = TradeLedger(base_dir=Path(td))
        rows = led.get_recent_trades(limit=5, hours=72)
        assert isinstance(rows, list)
    print("PASS TradeLedger.get_recent_trades(hours=) no longer TypeError")


if __name__ == "__main__":
    test_sl_12h_ago_blocks_tryout()
    test_same_day_buy_blocks_second_seat()
    test_old_sl_does_not_block()
    test_live_config_tryout_ioc_off()
    test_live_hard_block_ssot_scar_pairs_only()
    test_buy_block_waivers_time_bounded()
    test_get_recent_trades_accepts_hours()
    print("ALL process-tax lockout isolation PASS")
