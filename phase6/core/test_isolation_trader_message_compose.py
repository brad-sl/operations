#!/usr/bin/env python3
"""Isolation: trader messages = pure templates, deterministic, no AI path."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.trader_message_compose import (  # noqa: E402
    COMPOSER_NO_AI,
    assert_no_ai_imports,
    compose_why_cash_channels,
)


def _sample_why() -> dict:
    return {
        "headline": (
            "Markets look busy today — we're staying mostly in cash on purpose. "
            "That's the strategy, not a bug."
        ),
        "reasons": [
            {
                "code": "stance_park",
                "title": "We're holding cash on purpose",
                "detail": "Bitcoin's last month is only about +9.1% — not a clear enough uptrend.",
                "severity": "primary",
            },
            {
                "code": "cream_empty",
                "title": "Nothing looks like a good buy right now",
                "detail": "Even our picky checklist found zero coins worth buying.",
                "severity": "primary",
            },
        ],
        "heat": {"hot": True, "btc_change_24h_pct": 5.7},
        "posture": {"park": True},
        "cream": {"shadow_would_buy_count": 0},
        "book": {"held_pairs": ["LINK-USD", "PAXG-USD"]},
        "scale_faq": "We don't try to own every green day.",
    }


def test_deterministic():
    why = _sample_why()
    a = compose_why_cash_channels(why)
    b = compose_why_cash_channels(why)
    assert a["telegram"]["text"] == b["telegram"]["text"]
    assert a["email"]["html"] == b["email"]["html"]
    assert a["dashboard"]["headline"] == b["dashboard"]["headline"]
    ha = hashlib.sha256(a["telegram"]["text"].encode()).hexdigest()
    hb = hashlib.sha256(b["telegram"]["text"].encode()).hexdigest()
    assert ha == hb
    print("  deterministic OK", ha[:12])


def test_channels_present():
    out = compose_why_cash_channels(_sample_why())
    assert out["no_ai"] is True and COMPOSER_NO_AI is True
    assert out["engine"] == "template_v1"
    assert "holding cash" in out["telegram"]["text"].lower() or "cash" in out["telegram"]["text"].lower()
    assert "<li>" in out["email"]["html"]
    assert out["push"]["body"]
    assert "usdc_park" not in out["telegram"]["text"]
    assert "RSI" not in out["telegram"]["text"]
    print("  channels OK")


def test_no_ai_modules():
    assert_no_ai_imports()
    print("  no_ai_imports OK")


def test_does_not_invent_pairs():
    why = _sample_why()
    why["book"] = {"held_pairs": ["ETH-USD"]}
    out = compose_why_cash_channels(why)
    assert "ETH" in out["telegram"]["text"]
    assert "LINK" not in out["telegram"]["text"]
    print("  accuracy (no invent) OK")


if __name__ == "__main__":
    test_deterministic()
    test_channels_present()
    test_no_ai_modules()
    test_does_not_invent_pairs()
    print("trader_message_compose isolation PASS")
