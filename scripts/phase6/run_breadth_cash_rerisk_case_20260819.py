#!/usr/bin/env python3
"""Case study: 2026-08-19 breadth day vs cash-idle book (paper only)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.market_breadth_breakout import (  # noqa: E402
    breadth_from_returns,
    evaluate_cash_rerisk_shadow,
)

# 24h % from Coinbase-style tape Brad shared (fractions)
TAPE_24H = {
    "BTC-USD": 0.0564,
    "ETH-USD": 0.0896,
    "XRP-USD": 0.0620,
    "SOL-USD": 0.0604,
    "LINK-USD": 0.0445,
    "DOGE-USD": 0.0341,
    "ZEC-USD": 0.0966,
    "HYPE-USD": 0.0570,
    "SUI-USD": 0.0514,
}

OUT = ROOT / "data" / "state" / "breadth_cash_rerisk_case_20260819.json"
REPORT = ROOT / "reports" / "BREADTH_CASH_RERISK_CASE_20260819.md"


def main() -> int:
    live_path = ROOT / "data" / "state" / "phase6_live_state.json"
    live = json.loads(live_path.read_text()) if live_path.exists() else {}
    cash = float(live.get("cash_usd") or 2031.8)
    total = float(live.get("total_usd") or 2434.7)

    cfg = json.loads((ROOT / "config" / "trading_config_phase6.json").read_text())
    basket = list((cfg.get("global_settings") or {}).get("pairs") or [])

    # Shadow path context
    arms = {}
    ap = ROOT / "data" / "state" / "basket_select_arms_latest.json"
    if ap.exists():
        arms = (json.loads(ap.read_text()).get("arms") or {})
    contenders = []
    cp = ROOT / "data" / "state" / "pair_discovery_contenders.json"
    if cp.exists():
        contenders = json.loads(cp.read_text()).get("contenders") or []

    b = breadth_from_returns(TAPE_24H, ret_min=0.03, k=4)
    fire = evaluate_cash_rerisk_shadow(
        cash_usd=cash,
        total_usd=total,
        breadth=b,
        btc_ret_30d=0.05,  # not bear for this case; refine later with real 30d
        buy_blocked=[],
        in_basket=basket,
    )

    # BTC rotation counterfactual (ledger clip)
    btc_exit_px = 63077.17
    btc_qty = 0.03161929
    btc_now = None
    ph_path = ROOT / "data" / "state" / "price_history.json"
    if ph_path.exists():
        hist = (json.loads(ph_path.read_text()).get("history") or {}).get("BTC-USD") or []
        if hist:
            btc_now = float(hist[-1])
    btc_missed = None
    if btc_now:
        btc_missed = round((btc_now - btc_exit_px) * btc_qty, 2)

    paper_arms = {
        name: (a.get("swaps") or [])
        for name, a in arms.items()
    }

    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "case": "2026-08-19_breadth_vs_cash_idle",
        "nav": {"cash_usd": cash, "total_usd": total, "cash_frac": round(cash / total, 4) if total else None},
        "tape_24h": TAPE_24H,
        "breadth": b.to_dict(),
        "cash_rerisk_shadow": fire.to_dict(),
        "active_basket": basket,
        "btc_rotation_20260816": {
            "qty": btc_qty,
            "exit_px": btc_exit_px,
            "mark_px": btc_now,
            "missed_mtm_usd": btc_missed,
            "realized_pnl_usd": 2.18,
            "reason": "rotation_exchange",
        },
        "shadow_membership": {
            "live_swaps_proposed": [],
            "paper_arms_swaps": paper_arms,
            "discovery_contender_ids": [c.get("product_id") for c in contenders[:10]],
            "note": "ZEC/HYPE appeared on paper arms / discovery — not live promoted",
        },
        "plain_english": (
            "Breadth ON across majors while book was cash-heavy. "
            "Cash re-risk shadow would FIRE a small paper sleeve into unblocked basket names. "
            "Separately, rotation policy paper arms had named HYPE/ZEC — encouraging but unproven."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2))

    lines = [
        "# Breadth vs cash-idle case — 2026-08-19",
        "",
        f"Generated: `{payload['ts']}`",
        "",
        "## Plain English",
        "",
        payload["plain_english"],
        "",
        f"- Cash fraction: **{payload['nav']['cash_frac']}**",
        f"- Breadth: **{'ON' if b.breadth_on else 'OFF'}** ({b.note})",
        f"- Shadow cash re-risk: **{fire.tag}** fire={fire.fire} targets={fire.paper_targets} sleeve=${fire.paper_sleeve_usd}",
        f"- BTC rotation missed MTM (clip): **${btc_missed}**" if btc_missed is not None else "- BTC missed MTM: n/a",
        "",
        "## Paper membership arms (not live)",
        "",
        "```json",
        json.dumps(paper_arms, indent=2),
        "```",
        "",
        f"Full JSON: `{OUT}`",
        "",
    ]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines))
    print(REPORT.read_text())
    print("WROTE", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
