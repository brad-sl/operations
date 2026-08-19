#!/usr/bin/env python3
"""One-off: explain win ratio vs 24h/7d period returns."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.dashboard_serve_helpers import compute_period_performance, win_ratio_from_positions
from phase6.core.trade_ledger import TradeLedger

DB = ROOT / "data/state/phase6.db"
live_path = ROOT / "data/state/phase6_live_state.json"
if not live_path.exists():
    live_path = ROOT / "data/cache/phase6_dashboard_cache.json"

st = json.loads(live_path.read_text()) if live_path.exists() else {}
total = float(st.get("total_usd") or st.get("total_balance") or 0)
trading = st.get("trading_positions") or st.get("positions") or []

periods = compute_period_performance(total, DB, 5.0)
open_wr = win_ratio_from_positions(trading)

ledger = TradeLedger()
trades = ledger.get_recent_trades(limit=500)
closed = [t for t in trades if t.get("pnl") is not None and float(t.get("pnl") or 0) != 0]
closed_wr = (sum(1 for t in closed if float(t.get("pnl") or 0) > 0) / len(closed)) if closed else None

now = datetime.now(timezone.utc)


def parse_ts(t):
    s = t.get("timestamp") or t.get("ts") or ""
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except Exception:
        return None


def bucket_pnl(hours):
    cutoff = now - timedelta(hours=hours)
    sub = [t for t in closed if (dt := parse_ts(t)) and dt >= cutoff]
    pnl = sum(float(t.get("pnl") or 0) for t in sub)
    wr = sum(1 for t in sub if float(t.get("pnl") or 0) > 0) / len(sub) if sub else None
    return len(sub), round(pnl, 2), wr


wins = [t for t in closed if float(t.get("pnl") or 0) > 0]
losses = [t for t in closed if float(t.get("pnl") or 0) < 0]
sum_win = sum(float(t.get("pnl") or 0) for t in wins)
sum_loss = sum(float(t.get("pnl") or 0) for t in losses)

pos_rows = []
for p in trading:
    pair = p.get("pair") or ""
    if pair in ("USD", "USDC") or float(p.get("value_usd") or 0) < 0.01:
        continue
    pos_rows.append(
        {
            "pair": pair,
            "value_usd": round(float(p.get("value_usd") or 0), 2),
            "unrealized_pnl_pct": round(float(p.get("unrealized_pnl_pct") or 0), 3),
            "unrealized_pnl_usd": round(float(p.get("unrealized_pnl_usd") or p.get("pnl_usd") or 0), 2),
        }
    )

r24 = bucket_pnl(24)
r7 = bucket_pnl(24 * 7)

# Top losses/wins
sorted_closed = sorted(closed, key=lambda t: float(t.get("pnl") or 0))
worst = [{"pair": t.get("pair"), "pnl": t.get("pnl"), "ts": t.get("timestamp")} for t in sorted_closed[:5]]
best = [{"pair": t.get("pair"), "pnl": t.get("pnl"), "ts": t.get("timestamp")} for t in sorted_closed[-5:]][::-1]

out = {
    "total_usd": round(total, 2),
    "live_state_file": str(live_path),
    "periods_api": periods,
    "win_ratio_open_book": open_wr,
    "win_ratio_closed_trades": round(closed_wr, 3) if closed_wr is not None else None,
    "closed_trade_count": len(closed),
    "sum_realized_wins_usd": round(sum_win, 2),
    "sum_realized_losses_usd": round(sum_loss, 2),
    "net_realized_usd": round(sum_win + sum_loss, 2),
    "realized_24h": {"trades": r24[0], "pnl_usd": r24[1], "win_rate": r24[2]},
    "realized_7d": {"trades": r7[0], "pnl_usd": r7[1], "win_rate": r7[2]},
    "positions": pos_rows,
    "best_closed": best,
    "worst_closed": worst,
}
print(json.dumps(out, indent=2))