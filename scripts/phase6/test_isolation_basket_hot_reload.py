#!/usr/bin/env python3
"""Isolation: basket hot-reload updates FIXED_UNIVERSE without full runner restart."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from phase6.core.basket_hot_reload import (  # noqa: E402
    apply_basket_hot_reload,
    maybe_reload_trading_basket,
    pairs_changed,
)


def test_pairs_changed_detects_swap():
    assert pairs_changed(
        ["BTC-USD", "ETH-USD", "OP-USD"],
        ["BTC-USD", "ETH-USD", "ICP-USD"],
    )
    assert not pairs_changed(["A", "B"], ["A", "B"])


def test_apply_updates_universe_and_config_dict():
    runner = SimpleNamespace(
        FIXED_UNIVERSE=["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD", "OP-USD"],
        config_dict={
            "global_settings": {
                "pairs": [
                    "BTC-USD",
                    "ETH-USD",
                    "SOL-USD",
                    "XRP-USD",
                    "DOGE-USD",
                    "OP-USD",
                ]
            }
        },
        price_history=MagicMock(),
        exchange=MagicMock(),
        rsi_values={},
    )
    runner.exchange.get_recent_prices.return_value = [1.0] * 20

    new = [
        "BTC-USD",
        "ETH-USD",
        "SOL-USD",
        "XRP-USD",
        "DOGE-USD",
        "ICP-USD",
    ]
    result = apply_basket_hot_reload(
        runner,
        new,
        reason="test",
        seed_prices=True,
    )
    assert result.get("ok") is True
    assert result.get("changed") is True
    assert runner.FIXED_UNIVERSE == new
    assert runner.config_dict["global_settings"]["pairs"] == runner.FIXED_UNIVERSE
    assert result["added"] == ["ICP-USD"]
    assert result["removed"] == ["OP-USD"]
    assert runner.exchange.get_recent_prices.called


def test_refuse_empty_or_missing_sticky():
    base = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD", "OP-USD"]
    runner = SimpleNamespace(
        FIXED_UNIVERSE=list(base),
        config_dict={"global_settings": {"pairs": list(base)}},
        price_history=MagicMock(),
        exchange=MagicMock(),
        rsi_values={},
    )
    r1 = apply_basket_hot_reload(runner, [], reason="test")
    assert r1.get("ok") is False
    assert runner.FIXED_UNIVERSE[0] == "BTC-USD"

    r2 = apply_basket_hot_reload(
        runner,
        ["SOL-USD", "XRP-USD", "DOGE-USD", "ADA-USD", "AVAX-USD", "ICP-USD"],
        reason="test",
    )
    assert r2.get("ok") is False
    assert "BTC-USD" in runner.FIXED_UNIVERSE


def test_maybe_reload_respects_mtime_and_custom_path():
    pairs_a = [
        "BTC-USD",
        "ETH-USD",
        "SOL-USD",
        "XRP-USD",
        "DOGE-USD",
        "OP-USD",
    ]
    pairs_b = [
        "BTC-USD",
        "ETH-USD",
        "SOL-USD",
        "XRP-USD",
        "DOGE-USD",
        "ICP-USD",
    ]
    with tempfile.TemporaryDirectory() as td:
        cfg_path = Path(td) / "trading_config_phase6.json"
        cfg_path.write_text(
            json.dumps({"global_settings": {"pairs": pairs_a}}, indent=2) + "\n"
        )
        runner = SimpleNamespace(
            FIXED_UNIVERSE=list(pairs_a),
            config_dict={"global_settings": {"pairs": list(pairs_a)}},
            price_history=MagicMock(),
            exchange=MagicMock(),
            rsi_values={},
            config_path=str(cfg_path),
            _basket_config_mtime=None,
        )
        runner.exchange.get_recent_prices.return_value = [2.0] * 20

        r0 = maybe_reload_trading_basket(runner, cfg_path)
        assert r0.get("ok") is True
        assert r0.get("changed") is False  # same pairs
        assert getattr(runner, "_basket_config_mtime") is not None

        r_skip = maybe_reload_trading_basket(runner, cfg_path)
        assert r_skip.get("skipped") == "mtime"

        cfg_path.write_text(
            json.dumps({"global_settings": {"pairs": pairs_b}}, indent=2) + "\n"
        )
        r1 = maybe_reload_trading_basket(runner, cfg_path)
        assert r1.get("ok") is True
        assert r1.get("changed") is True
        assert runner.FIXED_UNIVERSE == pairs_b
        assert "ICP-USD" in runner.FIXED_UNIVERSE
        assert "OP-USD" not in runner.FIXED_UNIVERSE


if __name__ == "__main__":
    test_pairs_changed_detects_swap()
    test_apply_updates_universe_and_config_dict()
    test_refuse_empty_or_missing_sticky()
    test_maybe_reload_respects_mtime_and_custom_path()
    print("PASS")
