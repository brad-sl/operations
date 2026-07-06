"""Isolation: stop order detection + attach sizing (INSUFFICIENT_FUND class)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from phase6.core.sl_preflight import (
    order_configuration_is_stop,
    resolve_sl_attach_size,
)


class _Ex:
    def __init__(self, avail, total, q=1.0):
        self.avail = avail
        self.total = total
        self.q = q

    def get_crypto_available(self, asset):
        return self.avail

    def get_holdings_verified(self):
        return {"positions": {"LINK": self.total}, "verified": True}

    def quantize_size(self, pair, size):
        return f"{float(size):.2f}"


def test_stop_limit_gtc_key_detected():
    oc = {"stop_limit_stop_limit_gtc": {"stop_price": "10", "base_size": "1"}}
    assert order_configuration_is_stop(oc)


def test_resolve_size_zero_when_all_on_hold():
    ex = _Ex(avail=0.0, total=18.37)
    sz, meta = resolve_sl_attach_size(ex, "LINK-USD", 18.37)
    assert sz == 0.0 and meta.get("holds_entire_balance")


def test_resolve_size_caps_to_available():
    ex = _Ex(avail=10.0, total=18.37)
    sz, meta = resolve_sl_attach_size(ex, "LINK-USD", 18.37)
    assert sz <= 10.0 * 0.98 + 0.01
    assert meta.get("capped")


if __name__ == "__main__":
    test_stop_limit_gtc_key_detected()
    test_resolve_size_zero_when_all_on_hold()
    test_resolve_size_caps_to_available()
    print("OK")