#!/usr/bin/env python3
"""Isolation: limit-first buy shadow CF math + no-order fence."""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def test_cf_fee_delta() -> None:
    from phase6.core.limit_first_buy_shadow import cf_fee_delta

    d = cf_fee_delta(100.0, actual_fee=None, taker_rate=0.008, maker_rate=0.004)
    assert d["ok"] is True
    assert abs(d["actual_fee"] - 0.8) < 1e-9
    assert abs(d["maker_fee_if_rested"] - 0.4) < 1e-9
    assert abs(d["fee_delta_if_maker_upper_bound"] - 0.4) < 1e-9
    assert d["fillability"] == "unknown_until_pilot"
    assert d["cf_class"] == "fee_delta_if_rested_upper_bound"
    d2 = cf_fee_delta(200.0, actual_fee=1.6, taker_rate=0.008, maker_rate=0.004)
    assert abs(d2["fee_delta_if_maker_upper_bound"] - 0.8) < 1e-9
    assert d2["actual_fee_imputed"] is False


def test_would_limit_price() -> None:
    from phase6.core.limit_first_buy_shadow import would_limit_price

    assert would_limit_price(fill_px=100.0, bid=99.5) == 99.5
    w = would_limit_price(fill_px=100.0, bid=None, last=100.0)
    assert w is not None and w < 100.0


def test_log_market_buy_cf(tmp_path, monkeypatch=None) -> None:
    import phase6.core.limit_first_buy_shadow as m

    # Redirect events to tmp
    m.EVENTS = tmp_path / "events.jsonl"
    m.STATE_DIR = tmp_path
    m.LATEST = tmp_path / "latest.json"
    m.MD_REPORT = tmp_path / "report.md"
    m.FEE_TIER = tmp_path / "missing.json"

    ev = m.log_market_buy_counterfactual(
        {
            "pair": "BTC-USD",
            "entry_price": 100.0,
            "size": 1.0,
            "usd_value": 100.0,
            "order_id": "t1",
            "execution_style": "market_ioc",
        }
    )
    assert ev.get("fee_delta_if_maker_upper_bound") == 0.4
    assert m.EVENTS.exists()
    text = m.EVENTS.read_text()
    assert "market_buy_cf" in text
    assert "place_orders" in text


def test_skip_limit_style() -> None:
    from phase6.core.limit_first_buy_shadow import log_market_buy_counterfactual

    r = log_market_buy_counterfactual(
        {"pair": "ETH-USD", "execution_style": "limit_post_only", "usd_value": 50}
    )
    assert r.get("skipped") is True


def test_module_no_order_api_in_run() -> None:
    import phase6.core.limit_first_buy_shadow as m

    src = inspect.getsource(m)
    # Must not call place_* order APIs (place_orders flag string is ok)
    banned = [
        "place_market_buy(",
        "place_limit_buy(",
        "place_market_sell(",
        "create_order(",
    ]
    for b in banned:
        assert b not in src, f"banned {b}"
    assert "PLACE_ORDERS = False" in src or "place_orders: bool = False" in src


def test_summarize_and_board(tmp_path) -> None:
    import phase6.core.limit_first_buy_shadow as m
    from phase6.core.limit_first_buy_shadow import FeeRates, summarize_buys

    m.EVENTS = tmp_path / "e.jsonl"
    m.STATE_DIR = tmp_path
    m.LATEST = tmp_path / "latest.json"
    m.MD_REPORT = tmp_path / "r.md"
    m.FEE_TIER = tmp_path / "nope.json"
    m.TRADES_JSONL = tmp_path / "no_trades.jsonl"
    m.FILLS_JSONL = tmp_path / "no_fills.jsonl"

    buys = [
        {
            "pair": "BTC-USD",
            "usd_value": 100.0,
            "entry_price": 50.0,
            "fee_usd": None,
            "ts": "2026-08-31T00:00:00+00:00",
            "source": "test",
        }
    ]
    s = summarize_buys(buys, FeeRates(taker=0.008, maker=0.004))
    assert s["n_buys"] == 1
    assert abs(s["sum_fee_delta_upper_bound"] - 0.4) < 1e-6
    payload = m.run_limit_first_buy_shadow()
    assert payload["place_orders"] is False
    assert payload["live_gate"] == "OFF"
    assert m.LATEST.exists()
    assert "upper bound" in m.MD_REPORT.read_text().lower() or "Upper-bound" in m.MD_REPORT.read_text()


def main() -> None:
    from pathlib import Path
    import tempfile

    test_cf_fee_delta()
    test_would_limit_price()
    test_skip_limit_style()
    test_module_no_order_api_in_run()
    with tempfile.TemporaryDirectory() as td:
        test_log_market_buy_cf(Path(td))
        test_summarize_and_board(Path(td))
    print("PASS test_isolation_limit_first_buy_shadow")


if __name__ == "__main__":
    main()
