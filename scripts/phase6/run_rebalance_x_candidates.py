#!/usr/bin/env python3
"""CLI: rebalance X candidates (held ∪ plan) — measure / dry path for X-split Task 1."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.paths import STATE_DIR, load_trading_basket  # noqa: E402
from phase6.core.rebalance_x_candidates import (  # noqa: E402
    estimate_candidate_calls,
    estimate_full_book_calls,
    rebalance_x_candidates,
)


def _held_from_live() -> List[str]:
    path = STATE_DIR / "phase6_live_state.json"
    if not path.exists():
        return []
    try:
        live = json.loads(path.read_text())
    except Exception:
        return []
    out: List[str] = []
    for key in ("trading_positions", "positions"):
        raw = live.get(key)
        if isinstance(raw, list):
            for row in raw:
                if not isinstance(row, dict):
                    continue
                p = row.get("pair") or row.get("product_id") or row.get("symbol")
                if not p:
                    base = row.get("currency") or row.get("asset")
                    if base:
                        p = f"{str(base).upper()}-USD"
                if p:
                    out.append(str(p))
        elif isinstance(raw, dict):
            out.extend(str(k) for k in raw.keys())
    bals = live.get("balances") or []
    if isinstance(bals, list):
        for row in bals:
            if not isinstance(row, dict):
                continue
            cur = str(row.get("currency") or row.get("asset") or "").upper()
            if not cur or cur in ("USD", "USDC", "USDT", "DAI"):
                continue
            try:
                bal = float(row.get("balance") or row.get("available") or row.get("hold") or 0)
            except Exception:
                bal = 0.0
            if bal > 0:
                out.append(f"{cur}-USD")
    elif isinstance(bals, dict):
        for k, v in bals.items():
            try:
                if float(v or 0) > 0 and str(k).upper() not in ("USD", "USDC", "USDT"):
                    out.append(f"{str(k).upper()}-USD")
            except Exception:
                pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Rebalance X candidate set (no spend by default)")
    ap.add_argument("--plan-pair", action="append", default=[], help="TradePlan pair (repeatable)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument(
        "--go-fetch",
        action="store_true",
        help="Actually fetch X for candidates (paid; uses PHASE6_X_PAIRS + budget lane=rebal)",
    )
    args = ap.parse_args()

    try:
        pool = list(load_trading_basket() or [])
    except Exception:
        pool = []
    held = _held_from_live()
    plan = list(args.plan_pair or [])
    cands = sorted(
        rebalance_x_candidates(held_pairs=held, plan_pairs=plan, pool=pool or None)
    )
    full_n = len(pool) if pool else 12
    board: Dict[str, Any] = {
        "schema": "rebalance_x_candidates_v1",
        "held": sorted(set(held)),
        "plan": plan,
        "pool_n": full_n,
        "candidates": cands,
        "n_candidates": len(cands),
        "est_calls_candidates": estimate_candidate_calls(len(cands)),
        "est_calls_full_book": estimate_full_book_calls(full_n),
        "calls_saved_est": max(0, estimate_full_book_calls(full_n) - estimate_candidate_calls(len(cands))),
        "spend_x": False,
        "plain_english": (
            f"Rebalance X universe={len(cands)} (held∪plan, stables/ballast out) "
            f"vs full_book~{full_n}. Est calls {estimate_candidate_calls(len(cands))} vs "
            f"{estimate_full_book_calls(full_n)} (save ~"
            f"{max(0, estimate_full_book_calls(full_n) - estimate_candidate_calls(len(cands)))}). "
            f"No auto full-pool expand."
        ),
    }

    if args.go_fetch and cands:
        from phase6.core.x_query_budget import BudgetConfig, check_can_spend, record_spend
        from phase6.core.rsi_event_x_probe import fetch_x_for_pairs

        bcfg = BudgetConfig()
        dec = check_can_spend(cands, lane="rebal", cfg=bcfg)
        board["budget"] = dec.to_dict()
        if dec.allowed and dec.allowed_pairs:
            meta = fetch_x_for_pairs(dec.allowed_pairs)
            board["fetch_meta"] = {"ok": meta.get("ok"), "returncode": meta.get("returncode")}
            if meta.get("ok"):
                record_spend(dec.allowed_pairs, lane="rebal", cfg=bcfg, note="rebalance_x_candidates")
                board["spend_x"] = True
                board["fetched"] = list(dec.allowed_pairs)
                board["plain_english"] += f" PAID fetch {dec.allowed_pairs}."
            else:
                board["plain_english"] += " Fetch failed — budget not charged."
        else:
            board["plain_english"] += f" Budget blocked: {dec.reason}."

    out_path = STATE_DIR / "rebalance_x_candidates_latest.json"
    out_path.write_text(json.dumps(board, indent=2) + "\n")
    if args.json:
        print(json.dumps(board, indent=2))
    else:
        print(board["plain_english"])
        print(f"candidates={cands}")
        print(f"state={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
