#!/usr/bin/env python3
"""Isolation check: dashboard API shapes for phase6_dashboard.html consumers."""
from __future__ import annotations

import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8502"


def get(path: str, timeout: float = 3.0) -> tuple[float, dict]:
    t0 = time.time()
    with urllib.request.urlopen(f"{BASE}{path}", timeout=timeout) as resp:
        body = json.loads(resp.read().decode())
    return time.time() - t0, body


def main() -> int:
    errors = []
    bal_t, bal = get("/api/balances")
    for key in ("total_usd", "total_balance", "cash_positions", "trading_positions", "last_updated"):
        if key not in bal:
            errors.append(f"/api/balances missing {key}")
    if not bal.get("total_usd"):
        errors.append(f"/api/balances total_usd empty: {bal.get('total_usd')}")

    met_t, met = get("/api/metrics", timeout=2.0)
    if met_t > 1.0:
        errors.append(f"/api/metrics slow: {met_t:.3f}s")
    if not met.get("metrics"):
        errors.append("/api/metrics missing metrics object")

    print("balances", round(bal_t, 3), "s total_usd=", bal.get("total_usd"))
    print("metrics", round(met_t, 3), "s status=", met.get("status"), "util=", met.get("metrics", {}).get("utilization"))
    if errors:
        print("FAIL:", "; ".join(errors))
        return 1
    print("PASS dashboard composition API contract")
    return 0


if __name__ == "__main__":
    sys.exit(main())