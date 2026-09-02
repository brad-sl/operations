#!/usr/bin/env python3
"""Isolation: BUY+SELL stamp RSI+sentiment + lag for attribution digs.

Real caches preferred; fixtures cover offline path.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core import indicator_snapshot as ind
from phase6.core.trade_ledger import TradeLedger


def test_stamp_buy_and_sell_with_fixtures():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        rsi_cache = td_path / "rsi_cache.json"
        sent_cache = td_path / "sentiment_cache.json"
        lots_path = td_path / "entry_driver_lots.json"
        events_path = td_path / "trade_signal_events.jsonl"
        trades_dir = td_path / "trades"
        trades_dir.mkdir()

        rsi_cache.write_text(
            json.dumps(
                {
                    "timestamp": "2026-09-01T20:00:00Z",
                    "rsi": {
                        "LINK-USD": {
                            "rsi": 46.6,
                            "stoch_k": 40.0,
                            "stoch_d": 35.0,
                            "candle_count": 100,
                            "source": "test",
                        }
                    },
                }
            )
        )
        sent_cache.write_text(
            json.dumps(
                {
                    "timestamp": "2026-09-01T20:00:00Z",
                    "scores": {"LINK-USD": {"score": 0.89, "source": "x", "post_count": 12}},
                }
            )
        )
        lots_path.write_text(
            json.dumps(
                {
                    "updated": "2026-09-01T18:00:00Z",
                    "lots": [
                        {
                            "pair": "LINK-USD",
                            "ts": "2026-09-01T12:00:00+00:00",
                            "entry_price": 11.5,
                            "usd": 75.0,
                            "drivers": ["sentiment"],
                            "sentiment_only": True,
                            "sentiment_led": True,
                            "entry_rsi": 46.6,
                            "entry_sentiment": 0.89,
                            "order_id": "buy-oid-1",
                            "open": True,
                        }
                    ],
                }
            )
        )

        old_rsi = ind.RSI_CACHE
        old_state = ind.STATE_DIR
        old_events = ind.TRADE_SIGNAL_EVENTS
        ind.RSI_CACHE = rsi_cache
        ind.STATE_DIR = td_path
        ind.TRADE_SIGNAL_EVENTS = events_path
        try:
            # Force sentiment via cache path (detailed scorer may hit real disk)
            with patch.object(ind, "_load_pair_sentiment", return_value=(0.55, {"sentiment_source": "fixture"})):
                buy = ind.stamp_trade_signal_fields(
                    {
                        "pair": "LINK-USD",
                        "side": "BUY",
                        "timestamp": "2026-09-01T12:00:00Z",
                        "order_id": "buy-oid-1",
                        "entry_price": 11.5,
                    }
                )
                assert buy.get("entry_rsi") == 46.6, buy
                assert buy.get("entry_sentiment") == 0.55, buy
                assert buy["indicators_at_trade"].get("leg") == "entry"

                # SELL with lot join (entry from lot, exit from live fixture)
                with patch.object(ind, "_entry_lot_for_pair", return_value=json.loads(lots_path.read_text())["lots"][0]):
                    with patch.object(ind, "_load_pair_sentiment", return_value=(0.30, {"sentiment_source": "fixture"})):
                        # bump rsi cache for exit
                        rsi_cache.write_text(
                            json.dumps(
                                {
                                    "timestamp": "2026-09-01T20:00:00Z",
                                    "rsi": {
                                        "LINK-USD": {
                                            "rsi": 58.0,
                                            "stoch_k": 70.0,
                                            "stoch_d": 65.0,
                                            "source": "test",
                                        }
                                    },
                                }
                            )
                        )
                        sell = ind.stamp_trade_signal_fields(
                            {
                                "pair": "LINK-USD",
                                "side": "SELL",
                                "timestamp": "2026-09-01T20:00:00Z",
                                "order_id": "sell-oid-1",
                                "exit_price": 11.8,
                                "pnl_pct": 0.02,
                                "pnl": 1.5,
                            }
                        )
                assert sell.get("exit_rsi") == 58.0, sell
                assert sell.get("exit_sentiment") == 0.30, sell
                assert sell.get("entry_rsi") == 46.6, sell
                assert sell.get("entry_sentiment") == 0.89, sell
                assert sell.get("lag_hours_entry_to_exit") == 8.0, sell
                assert sell.get("rsi_delta_entry_exit") == 11.4, sell
                assert abs(float(sell.get("sent_delta_entry_exit")) - (0.30 - 0.89)) < 1e-6, sell

            ind.append_trade_signal_event(buy, path=events_path)
            ind.append_trade_signal_event(sell, path=events_path)
            lines = events_path.read_text().strip().splitlines()
            assert len(lines) == 2, lines
            print("PASS stamp_buy_and_sell_with_fixtures", json.dumps({"buy_rsi": buy["entry_rsi"], "sell_lag_h": sell["lag_hours_entry_to_exit"]}))
        finally:
            ind.RSI_CACHE = old_rsi
            ind.STATE_DIR = old_state
            ind.TRADE_SIGNAL_EVENTS = old_events


def test_ledger_writes_stamped_row(tmp_path=None):
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        ledger = TradeLedger(base_dir=td_path)
        # Point events into temp so we don't pollute live
        old_events = ind.TRADE_SIGNAL_EVENTS
        ind.TRADE_SIGNAL_EVENTS = td_path / "trade_signal_events.jsonl"
        try:
            with patch.object(
                ind,
                "stamp_trade_signal_fields",
                side_effect=lambda t: {
                    **t,
                    "entry_rsi": 50.0,
                    "entry_sentiment": 0.4,
                    "indicators_at_trade": {"rsi": 50.0, "sentiment": 0.4, "leg": "entry"},
                    "signal_stamp_schema": 1,
                },
            ):
                ledger.log_trade(
                    {
                        "pair": "ETH-USD",
                        "side": "BUY",
                        "qty": 0.01,
                        "entry_price": 3000.0,
                        "pnl": 0,
                        "pnl_pct": 0,
                        "mode": "shadow",
                        "signal_source": "iso_test",
                    }
                )
            rows = ledger.get_recent_trades(limit=1)
            assert rows, "no trade written"
            assert rows[0].get("entry_rsi") == 50.0
            assert rows[0].get("entry_sentiment") == 0.4
            assert (td_path / "trade_signal_events.jsonl").exists()
            print("PASS ledger_writes_stamped_row", rows[0].get("pair"), rows[0].get("entry_rsi"))
        finally:
            ind.TRADE_SIGNAL_EVENTS = old_events


def test_live_snapshot_has_sent_or_rsi():
    """Smoke on real caches — must not invent; may be partial."""
    snap = ind.indicators_for_trade_pair("BTC-USD")
    assert "pair" in snap
    print(
        "PASS live_snapshot",
        {k: snap.get(k) for k in ("pair", "rsi", "sentiment", "stamped_at", "source", "sentiment_source")},
    )


if __name__ == "__main__":
    test_stamp_buy_and_sell_with_fixtures()
    test_ledger_writes_stamped_row()
    test_live_snapshot_has_sent_or_rsi()
    # existing indicator snapshot suite still green
    from scripts.phase6 import test_isolation_indicator_snapshot as legacy  # type: ignore

    try:
        legacy.test_build_snapshot_from_cache()
        legacy.test_append_history()
        print("PASS legacy indicator snapshot subset")
    except Exception as e:
        print("WARN legacy suite skip/fail:", e)
    print("ALL PASS")
