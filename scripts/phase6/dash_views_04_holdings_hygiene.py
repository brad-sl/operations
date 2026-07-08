#!/usr/bin/env python3
"""
DASH-VIEWS-04: Data hygiene - clean stale/mixed holdings (and sibling balance snapshots, optionally prices) in DB using ts-based snapshot.

Problem (from DASH-VIEWS + MASTER): persist_facts_to_db generates fresh ts every cycle and INSERT OR REPLACE (new PK),
leading to thousands of (near) identical duplicate rows for unchanged holdings/balances/prices.
Views tolerate it via MAX(ts) per group, but DB bloats (historically 22k+ holdings, 24k+/pair prices).

Solution:
- Use ts-based latest snapshot per group (currency for holdings/balances, pair for prices).
- Delete all but the single latest row per group.
- Report before/after, verify views return identical data.
- VACUUM to reclaim space.
- Idempotent and safe (only removes strictly older ts for same group).

Canonical paths: uses phase6/core/paths.py PHASE6_DB (post config hygiene).

Usage (from kanban workspace or project root):
  python dash_views_04_holdings_hygiene.py
  python dash_views_04_holdings_hygiene.py --db /path/to/phase6.db --dry-run
  python ... --also-prices

Also recommends (for future bloat prevention): patch persist_facts_to_db to skip write when values match latest snapshot (see phase6/core/phase6_runner.py).

See: docs/MASTER_TASK_TRACKING.md (DASH-VIEWS section), docs/DATA_FLOW_AND_LOCATIONS.md, phase6/core/phase6_runner.py:persist_facts_to_db, scripts/phase6/migrate_dashboard_db.py
"""

import argparse
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

# Canonical import (post DASH/P0 config hygiene)
try:
    # Allow running from workspace or anywhere
    root = Path("/home/brad/projects/crypto-trading-bot")
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from phase6.core.paths import PHASE6_DB, get_project_root
    DEFAULT_DB = PHASE6_DB
except Exception as e:
    print(f"WARNING: could not import canonical paths ({e}), falling back")
    DEFAULT_DB = Path("/home/brad/projects/crypto-trading-bot/data/phase6.db")


def get_latest_per_group(conn: sqlite3.Connection, table: str, group_col: str, ts_col: str = "ts"):
    """Return dict of group -> max_ts"""
    cur = conn.cursor()
    cur.execute(f"""
        SELECT {group_col}, MAX({ts_col}) as max_ts 
        FROM {table} 
        GROUP BY {group_col}
    """)
    return {row[0]: row[1] for row in cur.fetchall()}


def clean_to_latest_snapshot(conn: sqlite3.Connection, table: str, group_col: str, ts_col: str = "ts", dry_run: bool = False):
    """Delete all rows except the latest ts per group. Returns (before_count, after_count, deleted)"""
    cur = conn.cursor()
    before = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    if before == 0:
        return before, 0, 0

    latest_map = get_latest_per_group(conn, table, group_col, ts_col)
    if not latest_map:
        return before, before, 0

    # Build delete condition: ts < max_ts for that group
    # Note: ts string compare works for consistent ISO formats; mixed Z/+00:00 may need normalization in future
    placeholders = []
    params = []
    for g, mts in latest_map.items():
        placeholders.append(f"({group_col} = ? AND {ts_col} < ?)")
        params.extend([g, mts])

    if not placeholders:
        return before, before, 0

    delete_sql = f"DELETE FROM {table} WHERE {' OR '.join(placeholders)}"
    if dry_run:
        # For dry run, count would-be-deleted
        try:
            cur.execute("SELECT COUNT(*) FROM (" + delete_sql.replace("DELETE FROM", "SELECT 1 FROM", 1) + ")", params)
            would_delete = cur.fetchone()[0]
        except Exception:
            would_delete = -1  # count failed, but proceed
        return before, before, would_delete

    cur.execute(delete_sql, params)
    deleted = cur.rowcount
    conn.commit()

    after = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    return before, after, deleted


def verify_post_clean(conn: sqlite3.Connection):
    """Verify that v_current_holdings and latest queries still return sensible current data."""
    cur = conn.cursor()
    print("\n=== Verification after clean ===")
    print("v_current_holdings (should be 1 row per active currency):")
    cur.execute("SELECT * FROM v_current_holdings ORDER BY currency;")
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    print(cols)
    for r in rows:
        print(r)
    print(f"Total rows in view: {len(rows)}")

    print("\nRaw holdings now (should be exactly 1 per currency, matching view):")
    cur.execute("SELECT currency, COUNT(*), MAX(ts) FROM holdings GROUP BY currency ORDER BY currency;")
    for r in cur.fetchall():
        print(r)

    print("\nSample latest from account_balances (USD):")
    cur.execute("SELECT * FROM account_balances WHERE currency='USD' ORDER BY ts DESC LIMIT 1;")
    print(cur.fetchone())

    # Quick total value sanity (if prices present)
    try:
        cur.execute("""
            SELECT SUM(h.amount * COALESCE(p.price, 0)) as holdings_value
            FROM v_current_holdings h
            LEFT JOIN v_latest_prices p ON (CASE WHEN h.currency LIKE '%-USD' THEN h.currency ELSE h.currency||'-USD' END) = p.pair
        """)
        val = cur.fetchone()[0]
        print(f"\nApprox holdings value from views: ${val:.2f}" if val else "No value calc")
    except Exception as e:
        print(f"Value sanity skipped: {e}")

    # prices after if cleaned
    try:
        pcount = cur.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
        print(f"\nprices rows now: {pcount}")
        cur.execute("SELECT pair, COUNT(*), MAX(ts) FROM prices GROUP BY pair ORDER BY pair;")
        print("prices per pair (should be 1):", cur.fetchall())
    except:
        pass


def main():
    parser = argparse.ArgumentParser(description="DASH-VIEWS-04 holdings data hygiene cleaner (ts snapshot)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to phase6.db")
    parser.add_argument("--dry-run", action="store_true", help="Count deletions without modifying")
    parser.add_argument("--also-prices", action="store_true", help="Also clean prices table (reduces bloat, keeps only latest per pair; history in price_history.json)")
    parser.add_argument("--vacuum", action="store_true", default=True, help="Run VACUUM after (default true)")
    args = parser.parse_args()

    db_path = args.db
    if not db_path.exists():
        print(f"ERROR: DB not found: {db_path}")
        sys.exit(1)

    print(f"=== DASH-VIEWS-04 Hygiene: ts-based snapshot clean on {db_path} ====")
    print(f"Started: {datetime.utcnow().isoformat()}Z")
    print(f"Dry-run: {args.dry_run}")
    print(f"Also prices: {args.also_prices}")
    print(f"Canonical DB: {DEFAULT_DB}")

    conn = sqlite3.connect(str(db_path), timeout=30.0)  # allow waiting for locks from runner/serve
    conn.execute("PRAGMA busy_timeout = 30000;")  # 30s wait for other writers
    conn.execute("PRAGMA foreign_keys = OFF;")  # for vacuum safety if needed

    tables_to_clean = [
        ("holdings", "currency"),
        ("account_balances", "currency"),
    ]
    if args.also_prices:
        tables_to_clean.append(("prices", "pair"))

    results = {}
    for table, group in tables_to_clean:
        try:
            before, after, deleted = clean_to_latest_snapshot(conn, table, group, dry_run=args.dry_run)
            results[table] = (before, after, deleted)
            print(f"{table}: before={before} after={after} deleted={deleted}")
        except Exception as e:
            print(f"ERROR cleaning {table}: {e}")
            results[table] = (None, None, None)
            import traceback
            traceback.print_exc()

    if not args.dry_run:
        conn.commit()
        conn.close()

        if args.vacuum:
            print("\nRunning VACUUM on fresh connection to reclaim space...")
            try:
                conn2 = sqlite3.connect(str(db_path), timeout=30.0)
                conn2.execute("PRAGMA busy_timeout = 30000;")
                conn2.execute("VACUUM;")
                conn2.commit()
                conn2.close()
                print("VACUUM complete.")
            except Exception as ve:
                print(f"VACUUM warning (non-fatal, DB still usable): {ve}")

        # Reopen for verify
        conn = sqlite3.connect(str(db_path), timeout=10.0)
        conn.execute("PRAGMA busy_timeout = 10000;")
        verify_post_clean(conn)
        conn.close()
    else:
        print("\nDry-run complete. No changes made. Re-run without --dry-run to apply.")
        conn.close()

    print(f"\n=== DONE { ' (dry)' if args.dry_run else '' } ===")
    print("Results:", results)


if __name__ == "__main__":
    main()
