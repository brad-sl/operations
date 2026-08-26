#!/usr/bin/env python3
"""CLI: run EXIT-H3 hard-exit vs ride counterfactual and print Telegram body."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.research.h3_hard_exit_counterfactual import (  # noqa: E402
    format_report,
    run_study,
    write_outputs,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="H3 hard-exit path counterfactual")
    ap.add_argument("--lookback-days", type=int, default=120)
    ap.add_argument("--fee-rt", type=float, default=0.0024)
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args()
    payload = run_study(lookback_days=args.lookback_days, fee_rt=args.fee_rt)
    if not args.no_write:
        js, md = write_outputs(payload)
        print(f"Wrote {js}")
        print(f"Wrote {md}")
    # Telegram-friendly short body
    d = payload.get("decision") or {}
    c = payload.get("counts") or {}
    print()
    print("=== H3 COUNTERFACTUAL ===")
    print(d.get("plain_english") or "")
    print(
        f"N_trig={d.get('n_triggered')} SL_legs={c.get('sl_legs')} "
        f"SL+hard={c.get('sl_with_prior_hard')} hard_all={c.get('hard_triggered')} "
        f"rounds={c.get('rounds')}"
    )
    if d.get("mean_excess_r") is not None:
        print(
            f"mean_excess={(d['mean_excess_r']*100):.2f}% "
            f"hit={(d.get('hit_rate_hard_better') or 0)*100:.0f}% "
            f"sum_Δ$={float(d.get('sum_delta_usd') or 0):.2f}"
        )
    print(f"status={d.get('status')} live_auto_recommend={d.get('recommend_live_h3_auto')}")
    print("Config unchanged: operator_approve stays true.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
