#!/usr/bin/env python3
"""
Code Isolation Test for DASH-SQL-005: Schema + VIEWs.

Standalone test. Uses real data from manual wrapper diagnostics and user screenshot (2026-06-12):
- USD: 613.7184425184249
- ETH: 0.08572777 (value ~142.89 at ~1666.74)
- XRP: 18.637483 (value ~21.08 at ~1.131)

Inserts facts, queries v_enriched_positions and v_phase6_dashboard, asserts correct values, no bogus keys, real data only.

Run: python phase6/core/test_isolation_dashboard_sql_schema.py
Must pass before any further changes.

Per Handoff: handoffs/phase6/Handoff_Dashboard_SQL_Schema_and_Views.md
Plan: docs/PHASE6_DASHBOARD_SQL_VIEW_REFACTOR_PLAN.md
"""

import sqlite3
import tempfile
import os
from pathlib import Path
import sys

# Known good real data from diagnostics + screenshot
REAL_DATA = {
    "usd_balance": 613.7184425184249,
    "eth_amount": 0.08572777,
    "xrp_amount": 18.637483,
    "eth_price": 1666.74,  # approx from prior enrichment
    "xrp_price": 1.131,
}

def run_isolation_test(db_path: str = None) -> bool:
    if db_path is None:
        # Use temp for isolation
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        cleanup = True
    else:
        cleanup = False

    try:
        # Run migration (idempotent)
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from scripts.phase6.migrate_dashboard_db import main as run_migration
        # Hack to run with specific db
        import argparse
        old_argv = sys.argv
        sys.argv = ["migrate", "--db", db_path]
        run_migration()
        sys.argv = old_argv

        conn = sqlite3.connect(db_path)
        ts = "2026-06-12T12:00:00"

        # Insert real facts (latest)
        conn.execute("INSERT OR REPLACE INTO account_balances (ts, currency, balance, available, hold, source) VALUES (?, 'USD', ?, ?, 0, 'live')", (ts, REAL_DATA["usd_balance"], REAL_DATA["usd_balance"]))
        conn.execute("INSERT OR REPLACE INTO holdings (ts, currency, amount, available, hold, source) VALUES (?, 'ETH', ?, 0, ?, 'live')", (ts, REAL_DATA["eth_amount"], REAL_DATA["eth_amount"]))
        conn.execute("INSERT OR REPLACE INTO holdings (ts, currency, amount, available, hold, source) VALUES (?, 'XRP', ?, ?, ?, 'live')", (ts, REAL_DATA["xrp_amount"], 0.037483, REAL_DATA["xrp_amount"] - 0.037483))
        conn.execute("INSERT OR REPLACE INTO prices (ts, pair, price, source) VALUES (?, 'ETH-USD', ?, 'price_history')", (ts, REAL_DATA["eth_price"]))
        conn.execute("INSERT OR REPLACE INTO prices (ts, pair, price, source) VALUES (?, 'XRP-USD', ?, 'price_history')", (ts, REAL_DATA["xrp_price"]))

        conn.commit()

        # Query views
        enriched = conn.execute("SELECT pair, amount, current_price, value_usd FROM v_enriched_positions ORDER BY pair;").fetchall()
        dashboard = conn.execute("SELECT cash_usd, total_holdings_value, total_usd, active_positions, positions_json FROM v_phase6_dashboard;").fetchone()

        print("=== Isolation Test Results ===")
        print("Enriched positions:")
        for row in enriched:
            print(f"  {row}")

        print(f"\nDashboard row: cash_usd={dashboard[0]}, holdings={dashboard[1]}, total={dashboard[2]}, positions={dashboard[3]}")

        # Assertions - real data match (tolerate float precision)
        assert len(enriched) == 2, f"Expected 2 positions, got {len(enriched)}"
        eth_row = [r for r in enriched if r[0] == 'ETH-USD'][0]
        xrp_row = [r for r in enriched if r[0] == 'XRP-USD'][0]

        assert abs(eth_row[1] - REAL_DATA["eth_amount"]) < 1e-6, f"ETH amount mismatch: {eth_row[1]}"
        assert abs(xrp_row[1] - REAL_DATA["xrp_amount"]) < 1e-6, f"XRP amount mismatch: {xrp_row[1]}"
        assert abs(eth_row[3] - (REAL_DATA["eth_amount"] * REAL_DATA["eth_price"])) < 0.1, "ETH value_usd mismatch"
        assert abs(xrp_row[3] - (REAL_DATA["xrp_amount"] * REAL_DATA["xrp_price"])) < 0.1, "XRP value_usd mismatch"

        assert abs(dashboard[0] - REAL_DATA["usd_balance"]) < 1e-6, "cash_usd mismatch"
        expected_holdings = (REAL_DATA["eth_amount"] * REAL_DATA["eth_price"]) + (REAL_DATA["xrp_amount"] * REAL_DATA["xrp_price"])
        assert abs(dashboard[1] - expected_holdings) < 0.1, "total_holdings_value mismatch"
        assert abs(dashboard[2] - (REAL_DATA["usd_balance"] + expected_holdings)) < 0.1, "total_usd mismatch"
        assert dashboard[3] == 2, f"active_positions mismatch: {dashboard[3]}"

        # No bogus keys
        positions_json = dashboard[4] or "[]"
        assert "positions-USD" not in positions_json, "Bogus key in positions"
        assert "verified-USD" not in positions_json, "Bogus key in positions"

        print("\n✅ All assertions passed. Real data matches screenshot + manual wrapper diagnostics.")
        print(f"Total USD: {dashboard[2]:.2f} (expected ~777.68)")
        return True

    finally:
        conn.close()
        if cleanup and os.path.exists(db_path):
            os.unlink(db_path)

if __name__ == "__main__":
    success = run_isolation_test()
    sys.exit(0 if success else 1)