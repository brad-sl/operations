#!/usr/bin/env python3
"""Dig prior trades impacted by ledger SSOT / live-TP ghost-lot class bugs.

Classes:
  A) Live TP sell shortly after BUY where BUY missing from ledger (or BUY after sell)
  B) Live TP sell with claimed r high but ledger fill round-trip ~flat/negative
  C) UNI-class stale peak trail (known 2026-08-23)
  D) SELL rows that never reduced FIFO (no exit_price) — inventory ghosts
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
TRADES = ROOT / "trades" / "phase6_trades.jsonl"
LIVE_EXITS = ROOT / "data" / "state" / "shadow_tp_live_exits.jsonl"
EVENTS = ROOT / "data" / "state" / "shadow_tp_events.jsonl"


def parse_ts(s: Any) -> Optional[datetime]:
    if not s:
        return None
    try:
        t = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t.astimezone(timezone.utc)
    except Exception:
        return None


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def side_of(t: Dict[str, Any]) -> str:
    return str(t.get("side") or t.get("action") or "").upper()


def qty_of(t: Dict[str, Any]) -> float:
    for k in ("qty", "size", "amount", "filled_size", "base_size"):
        try:
            q = float(t.get(k) or 0)
            if q > 0:
                return q
        except (TypeError, ValueError):
            pass
    return 0.0


def buy_px(t: Dict[str, Any]) -> Optional[float]:
    for k in ("average_filled_price", "fill_price", "entry_price", "price"):
        try:
            px = float(t.get(k) or 0)
            if px > 0 and abs(px - 100.0) > 0.01:
                return px
        except (TypeError, ValueError):
            pass
    return None


def sell_px(t: Dict[str, Any]) -> Optional[float]:
    for k in ("exit_price", "average_filled_price", "fill_price", "price", "entry_price"):
        try:
            px = float(t.get(k) or 0)
            if px > 0 and abs(px - 100.0) > 0.01:
                return px
        except (TypeError, ValueError):
            pass
    return None


def is_tp_sell(t: Dict[str, Any]) -> bool:
    blob = " ".join(
        str(t.get(k) or "")
        for k in ("reason", "exit_reason", "signal_source", "tp_kind", "detail")
    ).lower()
    if side_of(t) != "SELL":
        return False
    return any(
        x in blob
        for x in (
            "take_profit",
            "shadow_tp_live",
            "fixed_tp",
            "trail",
            "live_tp",
            "tp_kind",
        )
    ) or str(t.get("signal_source") or "") == "shadow_tp_live"


def main() -> None:
    trades = load_jsonl(TRADES)
    live_exits = load_jsonl(LIVE_EXITS)

    print("=== LEDGER SSOT / LIVE-TP IMPACT DIG ===")
    print(f"ledger_rows={len(trades)} live_exit_log_rows={len(live_exits)}")
    print("sides", Counter(side_of(t) for t in trades))
    print("top signal_source", Counter(str(t.get("signal_source") or "?") for t in trades).most_common(20))

    # Annotate trades with ts
    rows = []
    for t in trades:
        ts = parse_ts(t.get("timestamp") or t.get("ts"))
        rows.append({**t, "_ts": ts, "_side": side_of(t), "_qty": qty_of(t)})

    buys = [r for r in rows if r["_side"] == "BUY" and r["_ts"]]
    sells = [r for r in rows if r["_side"] == "SELL" and r["_ts"]]
    tp_sells = [r for r in sells if is_tp_sell(r)]
    print(f"\nBUY={len(buys)} SELL={len(sells)} TP_class_SELL={len(tp_sells)}")

    # Index buys by pair chronological
    buys_by_pair: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for b in sorted(buys, key=lambda x: x["_ts"]):
        pair = str(b.get("pair") or "")
        if pair:
            buys_by_pair[pair].append(b)

    all_by_pair: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in sorted(rows, key=lambda x: x["_ts"] or datetime.min.replace(tzinfo=timezone.utc)):
        pair = str(r.get("pair") or "")
        if pair and r["_ts"]:
            all_by_pair[pair].append(r)

    # --- Class A: TP sell with no prior BUY in ledger within lookback, or BUY after sell ---
    # Also: TP sell within N minutes of a BUY where claimed pnl_pct >> actual fill RT
    class_a: List[Dict[str, Any]] = []
    class_b: List[Dict[str, Any]] = []  # bogus r / wrong basis
    class_fast: List[Dict[str, Any]] = []  # sell < 10 min after matching buy

    for s in tp_sells:
        pair = str(s.get("pair") or "")
        if not pair or not s["_ts"]:
            continue
        prior_buys = [b for b in buys_by_pair.get(pair, []) if b["_ts"] <= s["_ts"]]
        # matching buy: same-ish qty within 24h before sell
        sq = s["_qty"]
        candidates = []
        for b in prior_buys:
            age_s = (s["_ts"] - b["_ts"]).total_seconds()
            if age_s < 0 or age_s > 86400 * 7:
                continue
            bq = b["_qty"]
            qty_ok = True
            if sq > 0 and bq > 0:
                qty_ok = abs(bq - sq) / max(sq, bq) < 0.25 or abs(bq - sq) < 0.05
            candidates.append((age_s, b, qty_ok))

        matched = None
        for age_s, b, qty_ok in sorted(candidates, key=lambda x: x[0]):
            if qty_ok:
                matched = (age_s, b)
                break
        if matched is None and candidates:
            # nearest prior buy even if qty mismatch
            age_s, b, _ = min(candidates, key=lambda x: x[0])
            matched = (age_s, b)

        sp = sell_px(s)
        claimed_pnl_pct = s.get("pnl_pct")
        try:
            claimed = float(claimed_pnl_pct) if claimed_pnl_pct is not None else None
        except (TypeError, ValueError):
            claimed = None
        # normalize claimed if stored as fraction vs percent
        if claimed is not None and abs(claimed) > 2:
            claimed = claimed / 100.0

        if matched is None:
            class_a.append(
                {
                    "pair": pair,
                    "sell_ts": s["_ts"].isoformat(),
                    "sell_qty": sq,
                    "sell_px": sp,
                    "order_id": s.get("order_id"),
                    "reason": s.get("reason") or s.get("exit_reason"),
                    "signal_source": s.get("signal_source"),
                    "issue": "tp_sell_no_prior_buy_7d",
                    "claimed_pnl_pct": claimed,
                }
            )
            continue

        age_s, b = matched
        bp = buy_px(b)
        actual_rt = None
        if bp and sp and bp > 0:
            actual_rt = (sp - bp) / bp

        rec = {
            "pair": pair,
            "sell_ts": s["_ts"].isoformat(),
            "buy_ts": b["_ts"].isoformat(),
            "hold_sec": round(age_s, 1),
            "hold_min": round(age_s / 60.0, 2),
            "buy_qty": b["_qty"],
            "sell_qty": sq,
            "buy_px": bp,
            "sell_px": sp,
            "actual_rt_pct": round(actual_rt * 100, 3) if actual_rt is not None else None,
            "claimed_pnl_pct": round(claimed * 100, 3) if claimed is not None else None,
            "buy_oid": b.get("order_id"),
            "sell_oid": s.get("order_id"),
            "reason": s.get("reason") or s.get("exit_reason") or s.get("tp_kind"),
            "buy_src": b.get("signal_source"),
            "sell_src": s.get("signal_source"),
        }

        if age_s <= 600:  # 10 min
            class_fast.append(rec)

        # Class B: claimed big win but actual RT near flat or negative, OR
        # hold < 30min and claimed >= 5% while actual < 2%
        if actual_rt is not None:
            bogus = False
            if claimed is not None and claimed >= 0.04 and actual_rt < 0.015:
                bogus = True
            if claimed is not None and (claimed - actual_rt) >= 0.04:
                bogus = True
            if age_s <= 1800 and actual_rt < 0.01 and (
                claimed is None or claimed >= 0.05 or age_s <= 120
            ):
                # very fast exit with no real edge — suspicious if fixed_tp style
                if age_s <= 300 or (claimed is not None and claimed >= 0.05):
                    bogus = True
            if bogus:
                class_b.append({**rec, "issue": "bogus_or_stale_basis_suspect"})

        # BUY missing relative to exchange fill story: sell oid known, buy not in ledger
        # already handled if no match

    # Also scan live_exits log
    print("\n--- live_exits.jsonl (authoritative live TP fire log) ---")
    for e in live_exits:
        print(
            json.dumps(
                {
                    k: e.get(k)
                    for k in (
                        "timestamp",
                        "ts",
                        "pair",
                        "kind",
                        "success",
                        "r",
                        "entry_px",
                        "mark_px",
                        "exit_price",
                        "qty",
                        "order_id",
                        "dry_run",
                        "detail",
                    )
                    if e.get(k) is not None
                },
                default=str,
            )
        )

    # Class D: SELL without usable exit price (ghost inventory risk)
    ghost_sells = []
    for r in sells:
        if sell_px(r) is None and r["_qty"] > 0:
            ghost_sells.append(
                {
                    "ts": r["_ts"].isoformat() if r["_ts"] else None,
                    "pair": r.get("pair"),
                    "qty": r["_qty"],
                    "entry_price": r.get("entry_price"),
                    "exit_price": r.get("exit_price"),
                    "signal_source": r.get("signal_source"),
                    "order_id": r.get("order_id"),
                    "reason": r.get("reason") or r.get("exit_reason"),
                }
            )

    print("\n=== CLASS FAST: TP sell within 10 min of matched BUY ===")
    print(f"count={len(class_fast)}")
    for r in sorted(class_fast, key=lambda x: x["sell_ts"]):
        print(
            f"  {r['sell_ts']} {r['pair']} hold={r['hold_min']}m "
            f"buy@{r['buy_px']} sell@{r['sell_px']} actual_rt={r['actual_rt_pct']}% "
            f"claimed={r['claimed_pnl_pct']}% reason={r['reason']} "
            f"buy_oid={r['buy_oid']} sell_oid={r['sell_oid']}"
        )

    print("\n=== CLASS B: bogus/stale basis suspects (claimed edge vs fill RT) ===")
    print(f"count={len(class_b)}")
    for r in sorted(class_b, key=lambda x: x["sell_ts"]):
        print(
            f"  {r['sell_ts']} {r['pair']} hold={r['hold_min']}m "
            f"actual_rt={r['actual_rt_pct']}% claimed={r['claimed_pnl_pct']}% "
            f"buy@{r['buy_px']}→sell@{r['sell_px']} reason={r['reason']}"
        )

    print("\n=== CLASS A: TP sell with no prior BUY in ledger (7d) ===")
    print(f"count={len(class_a)}")
    for r in class_a:
        print(
            f"  {r['sell_ts']} {r['pair']} qty={r['sell_qty']} px={r['sell_px']} "
            f"claimed={r['claimed_pnl_pct']} reason={r['reason']} oid={r['order_id']}"
        )

    print("\n=== CLASS D: SELL rows with qty but no usable sell price (FIFO ghost fuel) ===")
    print(f"count={len(ghost_sells)}")
    for r in ghost_sells[:30]:
        print(
            f"  {r['ts']} {r['pair']} qty={r['qty']} entry_price={r['entry_price']} "
            f"src={r['signal_source']} reason={r['reason']} oid={r['order_id']}"
        )
    if len(ghost_sells) > 30:
        print(f"  ... +{len(ghost_sells)-30} more")

    # Summary unique pairs / estimated $ damage on class B+fast where actual < 0 or << claimed
    impacted = {}
    for r in class_b + class_fast:
        key = (r["pair"], r["sell_ts"], r.get("sell_oid"))
        impacted[key] = r

    # de-dupe class_b and class_fast
    uniq = list(impacted.values())
    dollar = 0.0
    for r in uniq:
        bp, sp, q = r.get("buy_px"), r.get("sell_px"), r.get("sell_qty") or 0
        if bp and sp and q:
            dollar += (sp - bp) * float(q)

    print("\n=== SUMMARY ===")
    print(f"unique_suspect_tp_exits={len(uniq)}")
    print(f"fast_lt_10m={len(class_fast)}")
    print(f"bogus_basis_suspects={len(class_b)}")
    print(f"tp_no_prior_buy={len(class_a)}")
    print(f"ghost_sells_no_px={len(ghost_sells)}")
    print(f"approx_fill_rt_pnl_usd_on_suspects={round(dollar, 2)} (sum of sell-buy on matched pairs)")
    print("pairs", sorted({r['pair'] for r in uniq}))

    # Known named incidents
    print("\n=== KNOWN NAMED ===")
    for r in uniq:
        if r["pair"] in ("LINK-USD", "UNI-USD") or (r.get("hold_min") is not None and r["hold_min"] <= 2):
            print(f"  HIGH {r}")


if __name__ == "__main__":
    main()
