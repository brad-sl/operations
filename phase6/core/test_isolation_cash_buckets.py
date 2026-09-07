"""Isolation: USDC is one preserve cash row, never a USDC-USD trade seat."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core.cash_buckets import (  # noqa: E402
    cash_bucket_for,
    is_cash_like_pair,
    merge_cash_rows,
    split_cash_and_trading,
    trading_holdings_usd,
)


def test_usdc_usd_is_cash_like():
    assert is_cash_like_pair("USDC-USD")
    assert is_cash_like_pair("USDC")
    assert is_cash_like_pair("USDT-USD")
    assert not is_cash_like_pair("PAXG-USD")
    assert not is_cash_like_pair("BTC-USD")
    assert cash_bucket_for("USDC") == "preserve"
    assert cash_bucket_for("USD") == "powder"
    assert cash_bucket_for("USDT") == "hop"


def test_split_drops_usdc_pair_from_trading():
    cash, trade = split_cash_and_trading(
        [
            {"pair": "USDC-USD", "amount": 2010.42, "value_usd": 2010.42, "sleeve": "trade"},
            {"pair": "PAXG-USD", "amount": 0.018, "value_usd": 81.0, "sleeve": "preserve"},
            {"pair": "USD", "amount": 200.0, "value_usd": 200.0},
        ]
    )
    assert [c["pair"] for c in cash] == ["USDC", "USD"] or set(c["pair"] for c in cash) == {"USDC", "USD"}
    assert all(c.get("bucket") for c in cash)
    usdc = next(c for c in cash if c["pair"] == "USDC")
    assert usdc["sleeve"] == "preserve"
    assert [t["pair"] for t in trade] == ["PAXG-USD"]
    assert trading_holdings_usd(cash + trade) == 81.0


def test_merge_one_usdc_row_from_balances_and_pair():
    rows = merge_cash_rows(
        [
            {"currency": "USD", "balance": 200.0},
            {"currency": "USDC", "balance": 2010.42},
        ],
        [
            {"pair": "USDC-USD", "amount": 2010.42, "value_usd": 2010.42},
        ],
    )
    pairs = [r["pair"] for r in rows]
    assert pairs.count("USDC") == 1
    assert "USD" in pairs
    assert next(r for r in rows if r["pair"] == "USDC")["bucket"] == "preserve"


def test_enrich_live_state_no_double_usdc():
    # Import after path fix
    import importlib.util

    spec = importlib.util.spec_from_file_location("serve_dashboard", ROOT / "serve_dashboard.py")
    mod = importlib.util.module_from_spec(spec)
    # Minimal: call cash path without spinning server
    from phase6.core.cash_buckets import merge_cash_rows, split_cash_and_trading, trading_holdings_usd

    state = {
        "balances": [
            {"currency": "USD", "balance": 200.0, "available": 200.0},
            {"currency": "USDC", "balance": 2010.42, "available": 2010.42},
        ],
        "positions": [
            {"pair": "PAXG-USD", "amount": 0.01834, "value_usd": 81.34, "sleeve": "preserve"},
            {"pair": "USDC-USD", "amount": 2010.4174, "value_usd": 2010.42, "sleeve": "trade"},
        ],
        "total_usd": 4302.18,
        "total_holdings_value": 2091.76,
        "cash_usd": 200.0,
    }
    cash_from_pos, trade = split_cash_and_trading(state["positions"])
    cash = merge_cash_rows(state["balances"], cash_from_pos)
    hold = trading_holdings_usd(trade)
    total = sum(float(c["value_usd"]) for c in cash) + hold
    assert abs(total - 2291.76) < 0.02
    assert len([c for c in cash if c["pair"] == "USDC"]) == 1
    assert not any(t["pair"] == "USDC-USD" for t in trade)


if __name__ == "__main__":
    test_usdc_usd_is_cash_like()
    test_split_drops_usdc_pair_from_trading()
    test_merge_one_usdc_row_from_balances_and_pair()
    test_enrich_live_state_no_double_usdc()
    print("test_isolation_cash_buckets: OK")
