#!/usr/bin/env python3
"""
Retroactive decision_context rows from legacy trade clusters (rotation param-audit backfill).

For each verified rotation_exchange SELL without a nearby decision log, synthesize one
decision_context from trades/phase6_trades.jsonl in a ±6h window.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from phase6.core.paths import DECISION_CONTEXT_LOG, PROJECT_ROOT as ROOT, TRADING_LOG_DIR
from phase6.core.trading_log_store import iter_verified_fills, default_account_id


def _all_account_ids() -> list[str]:
    ids: list[str] = []
    if TRADING_LOG_DIR.exists():
        for d in TRADING_LOG_DIR.iterdir():
            if d.is_dir() and (d / "order_id_index.json").exists():
                ids.append(d.name)
    if not ids:
        ids.append(default_account_id())
    return ids


def _parse_ts(ts: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _load_legacy_trades() -> list[dict]:
    p = ROOT / "trades/phase6_trades.jsonl"
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _existing_decision_times() -> list[datetime]:
    if not DECISION_CONTEXT_LOG.exists():
        return []
    out = []
    for line in DECISION_CONTEXT_LOG.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
            t = _parse_ts(str(d.get("timestamp") or ""))
            if t:
                out.append(t)
        except json.JSONDecodeError:
            continue
    return out


def _has_near_decision(ts: datetime, existing: list[datetime], hours: float = 8.0) -> bool:
    for e in existing:
        if abs((ts - e).total_seconds()) <= hours * 3600:
            return True
    return False


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--hours-window", type=float, default=6.0)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    account_ids = _all_account_ids()
    legacy = _load_legacy_trades()
    existing = _existing_decision_times()
    added = 0
    skipped = 0

    rotation_sells: list[dict] = []
    for account_id in account_ids:
        rotation_sells.extend(
            [
                r
                for r in iter_verified_fills(account_id)
                if str(r.get("side", "")).upper() == "SELL"
                and str(r.get("reason") or r.get("exit_reason")) == "rotation_exchange"
            ]
        )

    account_id = account_ids[0] if account_ids else default_account_id()

    DECISION_CONTEXT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(DECISION_CONTEXT_LOG, "a", encoding="utf-8") as out_f:
        for sell in sorted(rotation_sells, key=lambda x: x.get("timestamp", "")):
            ts_s = str(sell.get("timestamp") or "")
            ts = _parse_ts(ts_s)
            if not ts:
                skipped += 1
                continue
            if _has_near_decision(ts, existing):
                skipped += 1
                continue

            win = timedelta(hours=args.hours_window)
            cluster: list[dict] = []
            cluster_times: list[datetime] = []
            for t in legacy:
                tt = _parse_ts(str(t.get("timestamp") or ""))
                if not tt or abs((tt - ts).total_seconds()) > win.total_seconds():
                    continue
                side = str(t.get("side", "")).upper()
                pair = t.get("pair")
                if not pair or side not in ("BUY", "SELL"):
                    continue
                cluster_times.append(tt)
                cluster.append(
                    {
                        "pair": pair,
                        "action": side,
                        "usd": float(
                            t.get("usd_amount")
                            or (t.get("qty", 0) or 0)
                            * (t.get("entry_price") or t.get("exit_price") or 0)
                            or 0
                        ),
                        "reason": t.get("reason", "legacy_trade"),
                    }
                )

            if not cluster:
                skipped += 1
                continue

            cluster_ts = min(cluster_times) if cluster_times else ts
            ctx = {
                "timestamp": (cluster_ts or ts).isoformat(),
                "decision_id": f"backfill_{uuid.uuid4().hex[:12]}",
                "rebalance_path": "backfill_legacy_cluster",
                "actions_taken": cluster,
                "type": "decision_context",
                "source": "backfill_decision_context_from_trades",
                "backfilled": True,
                "anchor_sell_order_id": sell.get("order_id"),
                "anchor_pair": sell.get("pair"),
            }
            if args.dry_run:
                print(json.dumps(ctx, indent=2)[:500])
            else:
                out_f.write(json.dumps(ctx) + "\n")
                existing.append(cluster_ts or ts)
            added += 1

    print(json.dumps({"ok": True, "added": added, "skipped": skipped, "dry_run": args.dry_run}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())