#!/usr/bin/env python3
"""Shadow would-block logger for trade comparison standard (TCS-002).

- Evaluates historical clean buys + optional "live probe" of current basket intents
- Appends JSONL; never blocks orders; never writes trading knobs beyond its own state files

Rule v1 (sweet spot from CF): A48 | (B48 & usd>150) | D elev_rsi_large
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.trade_comparison_standard import (  # noqa: E402
    buy_event,
    is_clean_buy,
    load_ledger_rows,
    sell_event,
    would_block_buy,
)
from phase6.research.run_trade_comparison_cf import run_cf  # noqa: E402

STATE = ROOT / "data" / "state"
LOG = STATE / "tcs_shadow_would_block.jsonl"
LATEST = STATE / "tcs_shadow_would_block_latest.json"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _eval_buy(
    pair: str,
    buy_ts: datetime,
    usd: float,
    rsi: Optional[float],
    sells: List[Dict[str, Any]],
) -> Dict[str, Any]:
    wb = would_block_buy(
        pair=pair,
        buy_ts=buy_ts,
        usd=usd,
        rsi=rsi,
        recent_sells=sells,
        sl_cooldown_h=48.0,
        tp_cooldown_h=48.0,
        tryout_usd=150.0,
        elevated_rsi=55.0,
    )
    # Align with sweet rule: post_tp only if full-size (already in would_block)
    return wb


def replay_ledger(limit: int = 500) -> Dict[str, Any]:
    rows = load_ledger_rows()
    events: List[Dict[str, Any]] = []
    by_pair_sells: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        if r.get("side") == "SELL":
            p = str(r.get("pair") or "")
            by_pair_sells.setdefault(p, []).append(sell_event(r))

    buys = [buy_event(r) for r in rows if is_clean_buy(r)]
    buys = [b for b in buys if b.get("ts")]
    buys.sort(key=lambda b: b["ts"])
    if limit and len(buys) > limit:
        buys = buys[-limit:]

    n_block = 0
    notional_block = 0.0
    for b in buys:
        pair = str(b.get("pair") or "")
        wb = _eval_buy(
            pair,
            b["ts"],
            float(b.get("usd") or 0.0),
            b.get("rsi"),
            by_pair_sells.get(pair) or [],
        )
        rec = {
            "kind": "ledger_replay",
            "as_of": _utcnow(),
            "pair": pair,
            "buy_ts": b["ts"].isoformat(),
            "usd": b.get("usd"),
            "rsi": b.get("rsi"),
            "block": wb.get("block"),
            "reasons": wb.get("reasons"),
            "live": False,
        }
        events.append(rec)
        if wb.get("block"):
            n_block += 1
            notional_block += float(b.get("usd") or 0.0)

    STATE.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        # one summary line + keep payload in latest only (avoid huge jsonl spam)
        f.write(
            json.dumps(
                {
                    "kind": "replay_batch",
                    "as_of": _utcnow(),
                    "n_buys": len(events),
                    "n_block": n_block,
                    "notional_block": round(notional_block, 2),
                    "rule": "A48|(B48&usd>tryout)|D|mega_via_would_block_api",
                }
            )
            + "\n"
        )

    summary = {
        "schema": "tcs_shadow_would_block_v1",
        "as_of": _utcnow(),
        "mode": "ledger_replay",
        "live_blocks": False,
        "n_buys": len(events),
        "n_would_block": n_block,
        "would_block_rate": round(n_block / len(events), 4) if events else 0.0,
        "notional_would_block_usd": round(notional_block, 2),
        "log": str(LOG),
        "sample_blocks": [e for e in events if e.get("block")][:20],
        "note": "Shadow only — runner buy path unchanged except LINK pair_ticket_cap",
    }
    LATEST.write_text(json.dumps(summary, indent=2, default=str) + "\n")
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="TCS shadow would-block logger")
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--with-cf", action="store_true", help="Also refresh CF artifacts")
    args = ap.parse_args(argv)

    if args.with_cf:
        cf = run_cf()
        (STATE / "trade_comparison_cf_latest.json").write_text(
            json.dumps(cf, indent=2, default=str) + "\n"
        )
        print("cf_refreshed", cf.get("recommended_shadow_rule"))

    summary = replay_ledger(limit=args.limit)
    print("TCS_SHADOW_WOULD_BLOCK")
    print(json.dumps({k: summary[k] for k in summary if k != "sample_blocks"}, indent=2))
    print(f"latest={LATEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
