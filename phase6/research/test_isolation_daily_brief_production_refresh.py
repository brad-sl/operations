"""Daily brief refreshes live production metrics (not stale leaderboard snapshot)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.optimization_brief import build_daily_opt_brief, load_leaderboard, refresh_live_production_metrics


def main() -> int:
    live = refresh_live_production_metrics()
    m = live.get("metrics") or {}
    assert m.get("total_return_pct") is not None, "expected live return_pct"

    lb = load_leaderboard() or {}
    stale = (lb.get("production_since_go_live") or {}).get("metrics") or {}
    stale_ret = stale.get("total_return_pct")
    fresh_ret = m.get("total_return_pct")
    if stale_ret is not None and fresh_ret is not None:
        # Stale leaderboard may be unadjusted; fresh should be deposit-adjusted.
        assert m.get("deposit_adjusted") is True
        if m.get("net_external_flows_usd") and float(m["net_external_flows_usd"]) > 100:
            unadj = m.get("total_return_pct_unadjusted")
            if unadj is not None:
                assert float(unadj) > float(fresh_ret), (unadj, fresh_ret)

    _, brief = build_daily_opt_brief(lb)
    assert brief.get("production_refreshed_at")
    assert brief.get("production_since_go_live_return_pct") == fresh_ret
    print("daily brief production refresh isolation PASS", fresh_ret, m.get("trade_count"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())