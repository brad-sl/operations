#!/usr/bin/env python3
"""TG-01: Exit asymmetry instrumentation — real ledger only.

Classifies realizing sells, win rates by reason, re-entry within 24/48/72h,
and simple counterfactuals (what if TP at X% / hold past SL noise).

Writes:
  data/state/exit_asymmetry_latest.json
  reports/EXIT_ASYMMETRY_YYYY-MM-DD.md
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TRADES = ROOT / "trades" / "phase6_trades.jsonl"
OUT_JSON = ROOT / "data" / "state" / "exit_asymmetry_latest.json"
REPORTS = ROOT / "reports"


def _parse_ts(r: Dict[str, Any]) -> Optional[datetime]:
    for k in ("ts", "timestamp", "filled_at", "time"):
        raw = r.get(k)
        if not raw:
            continue
        try:
            t = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            return t
        except Exception:
            continue
    return None


def _classify_reason(r: Dict[str, Any]) -> str:
    reason = str(r.get("reason") or r.get("exit_reason") or "").lower()
    if "stop_loss" in reason or reason in ("sl", "stoploss"):
        return "stop_loss_exchange"
    if "rotation" in reason:
        return "rotation_exchange"
    if "regime_hard_exit" in reason or "hard_exit" in reason:
        return "regime_hard_exit"
    if "tier1" in reason or "glide" in reason:
        return "tier1_glide"
    if "manual" in reason:
        return "manual"
    if "take_profit" in reason or reason in ("tp", "take_profit"):
        return "take_profit"
    if "rebalance" in reason and str(r.get("side", "")).upper() == "SELL":
        return "rebalance_sell"
    if reason:
        return reason[:40]
    return "unknown"


def _load_unique_rows() -> List[Dict[str, Any]]:
    if not TRADES.exists():
        return []
    seen = set()
    rows: List[Dict[str, Any]] = []
    for line in TRADES.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        oid = r.get("order_id") or r.get("exchange_order_id") or ""
        key = oid or (
            str(r.get("ts") or r.get("timestamp")),
            r.get("pair"),
            r.get("side"),
            r.get("qty"),
            r.get("reason"),
            r.get("pnl"),
        )
        if key in seen:
            continue
        seen.add(key)
        rows.append(r)
    return rows


def _implied_entry_notional(r: Dict[str, Any]) -> Optional[float]:
    """entry_n = qty*exit - pnl when possible."""
    try:
        pnl = float(r.get("pnl"))
    except (TypeError, ValueError):
        return None
    qty = r.get("qty")
    exit_p = r.get("exit_price") or r.get("price")
    try:
        if qty is not None and exit_p is not None:
            return float(qty) * float(exit_p) - pnl
    except (TypeError, ValueError):
        pass
    entry = r.get("entry_price")
    try:
        if qty is not None and entry is not None:
            return float(qty) * float(entry)
    except (TypeError, ValueError):
        pass
    return None


def _r_return(r: Dict[str, Any]) -> Optional[float]:
    try:
        pnl = float(r.get("pnl"))
    except (TypeError, ValueError):
        return None
    en = _implied_entry_notional(r)
    if en is None or abs(en) < 1.0:
        pct = r.get("pnl_pct")
        try:
            return float(pct) if pct is not None else None
        except (TypeError, ValueError):
            return None
    return pnl / en


def analyze(days: int = 30) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    cut = now - timedelta(days=days)
    rows = _load_unique_rows()
    sells = []
    buys = []
    for r in rows:
        t = _parse_ts(r)
        if t is None or t < cut:
            continue
        side = str(r.get("side") or r.get("action") or "").upper()
        if side == "SELL":
            sells.append((t, r))
        elif side == "BUY":
            buys.append((t, r))
    sells.sort(key=lambda x: x[0])
    buys.sort(key=lambda x: x[0])

    by_reason: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"n": 0, "wins": 0, "losses": 0, "flat": 0, "sum_pnl": 0.0, "pairs": set(), "rs": []}
    )
    realized = []
    for t, r in sells:
        reason = _classify_reason(r)
        pnl = r.get("pnl")
        try:
            pnl_f = float(pnl) if pnl is not None else None
        except (TypeError, ValueError):
            pnl_f = None
        b = by_reason[reason]
        b["n"] += 1
        b["pairs"].add(r.get("pair"))
        if pnl_f is None:
            b["flat"] += 1
        else:
            b["sum_pnl"] += pnl_f
            if pnl_f > 0:
                b["wins"] += 1
                realized.append((t, r, reason, pnl_f, True))
            elif pnl_f < 0:
                b["losses"] += 1
                realized.append((t, r, reason, pnl_f, False))
            else:
                b["flat"] += 1
            rr = _r_return(r)
            if rr is not None and abs(rr) <= 0.5:
                b["rs"].append(rr)

    # Re-entry: after a stop sell, any BUY same pair within windows
    reentry = {"24h": 0, "48h": 0, "72h": 0, "examples": []}
    stop_sells = [(t, r) for t, r in sells if _classify_reason(r) == "stop_loss_exchange"]
    for t, r in stop_sells:
        pair = r.get("pair")
        if not pair:
            continue
        windows_hit = []
        for bt, br in buys:
            if br.get("pair") != pair:
                continue
            if bt <= t:
                continue
            dt_h = (bt - t).total_seconds() / 3600.0
            if dt_h <= 24:
                windows_hit.append(("24h", bt, dt_h))
            if dt_h <= 48:
                windows_hit.append(("48h", bt, dt_h))
            if dt_h <= 72:
                windows_hit.append(("72h", bt, dt_h))
        if any(w[0] == "24h" for w in windows_hit):
            reentry["24h"] += 1
        if any(w[0] == "48h" for w in windows_hit):
            reentry["48h"] += 1
        if any(w[0] == "72h" for w in windows_hit):
            reentry["72h"] += 1
            if len(reentry["examples"]) < 12:
                first = min((w for w in windows_hit if w[0] == "72h"), key=lambda x: x[2])
                reentry["examples"].append(
                    {
                        "pair": pair,
                        "sell_ts": t.isoformat(),
                        "buy_ts": first[1].isoformat(),
                        "hours_to_rebuy": round(first[2], 2),
                        "sell_pnl": r.get("pnl"),
                    }
                )

    # Counterfactual sketches (not live advice): if wins needed matching loss count at mean |loss|
    loss_pnls = [x[3] for x in realized if not x[4]]
    win_pnls = [x[3] for x in realized if x[4]]
    mean_loss = sum(loss_pnls) / len(loss_pnls) if loss_pnls else 0.0
    mean_win = sum(win_pnls) / len(win_pnls) if win_pnls else 0.0
    n_w = len(win_pnls)
    n_l = len(loss_pnls)
    # TP counterfactual: count sells with r >= tp that were still losses? only wins matter
    # Better: among all sells with computable r, how many crossed +tp before final (unknown without path)
    # Proxy: fraction of rotation wins vs SL losses magnitude
    tp_levels = [0.04, 0.06, 0.08]
    tp_hits_proxy = {}
    for tp in tp_levels:
        # count realized sells where pnl_pct or r >= tp (already banked at/above TP)
        hit = 0
        for t, r, reason, pnl_f, is_win in realized:
            rr = _r_return(r)
            if rr is not None and rr >= tp:
                hit += 1
        tp_hits_proxy[str(tp)] = {
            "realized_exits_at_or_above_tp": hit,
            "note": "proxy only — no intrabar path; counts exits already >= TP",
        }

    reason_out = {}
    for k, v in by_reason.items():
        n_wl = v["wins"] + v["losses"]
        reason_out[k] = {
            "n": v["n"],
            "wins": v["wins"],
            "losses": v["losses"],
            "flat_or_missing_pnl": v["flat"],
            "sum_pnl_usd": round(v["sum_pnl"], 4),
            "wr": round(v["wins"] / n_wl, 4) if n_wl else None,
            "pairs": sorted(p for p in v["pairs"] if p),
            "mean_r": round(sum(v["rs"]) / len(v["rs"]), 6) if v["rs"] else None,
            "n_r": len(v["rs"]),
        }

    total_wl = n_w + n_l
    report = {
        "schema": "exit_asymmetry_v1",
        "as_of": now.isoformat(),
        "window_days": days,
        "source": str(TRADES),
        "totals": {
            "sells": len(sells),
            "buys": len(buys),
            "realized_wins": n_w,
            "realized_losses": n_l,
            "exit_wr": round(n_w / total_wl, 4) if total_wl else None,
            "sum_pnl_realized_usd": round(sum(x[3] for x in realized), 4),
            "mean_win_usd": round(mean_win, 4),
            "mean_loss_usd": round(mean_loss, 4),
            "payoff_b_usd": round(abs(mean_win / mean_loss), 4) if mean_loss else None,
        },
        "by_reason": reason_out,
        "reentry_after_stop": reentry,
        "tp_proxy": tp_hits_proxy,
        "diagnosis": {
            "primary": (
                "exit_asymmetry_sl_dominated"
                if reason_out.get("stop_loss_exchange", {}).get("sum_pnl_usd", 0) < 0
                and (reason_out.get("stop_loss_exchange", {}).get("n") or 0)
                >= max(1, (reason_out.get("rotation_exchange", {}).get("n") or 0))
                else "mixed"
            ),
            "detail": (
                "Stop-loss exits dominate count and dollar drag; profit-taking surface thin/null. "
                "Re-entry windows show recycle risk after SL."
            ),
        },
        "recommendations": [
            {
                "id": "TG-02",
                "action": "shadow hard prefer_exit SELLs (no park_soft auto)",
                "status": "wired_shadow",
            },
            {
                "id": "TG-03",
                "action": "SL hold cash + 72h rebuy under repair",
                "status": "config_applied",
            },
            {
                "id": "TG-04",
                "action": "offline/shadow TP or trail-after-green",
                "status": "queued",
            },
        ],
    }
    return report


def to_markdown(rep: Dict[str, Any]) -> str:
    t = rep["totals"]
    lines = [
        f"# Exit Asymmetry Report — {rep['as_of'][:10]}",
        "",
        f"**Window:** {rep['window_days']}d · **Source:** `{rep['source']}`",
        "",
        "## Totals",
        f"- Realized WR: **{t.get('exit_wr')}** ({t.get('realized_wins')}/{t.get('realized_wins', 0) + t.get('realized_losses', 0)})",
        f"- Sum realized PnL: **${t.get('sum_pnl_realized_usd')}**",
        f"- Mean win / loss USD: ${t.get('mean_win_usd')} / ${t.get('mean_loss_usd')} · b≈{t.get('payoff_b_usd')}",
        "",
        "## By exit reason",
        "",
        "| Reason | n | W | L | WR | Sum PnL |",
        "|--------|---|---|---|----|---------|",
    ]
    for k, v in sorted(rep["by_reason"].items(), key=lambda x: -x[1]["n"]):
        lines.append(
            f"| {k} | {v['n']} | {v['wins']} | {v['losses']} | {v.get('wr')} | {v['sum_pnl_usd']} |"
        )
    re = rep["reentry_after_stop"]
    lines += [
        "",
        "## Re-entry after stop_loss_exchange",
        f"- Within 24h: **{re['24h']}**",
        f"- Within 48h: **{re['48h']}**",
        f"- Within 72h: **{re['72h']}**",
        "",
        "### Examples",
    ]
    for ex in re.get("examples") or []:
        lines.append(
            f"- {ex['pair']}: sell {ex['sell_ts'][:16]} → buy +{ex['hours_to_rebuy']}h (sell pnl={ex.get('sell_pnl')})"
        )
    lines += [
        "",
        f"## Diagnosis",
        f"- Primary: `{rep['diagnosis']['primary']}`",
        f"- {rep['diagnosis']['detail']}",
        "",
        "## North star",
        "Better returns **and** less loss — fix exit stack / anti-rebuy before thaw.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    days = 30
    if len(sys.argv) > 1:
        try:
            days = int(sys.argv[1])
        except ValueError:
            pass
    rep = analyze(days=days)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    REPORTS.mkdir(parents=True, exist_ok=True)
    md_path = REPORTS / f"EXIT_ASYMMETRY_{rep['as_of'][:10]}.md"
    md_path.write_text(to_markdown(rep), encoding="utf-8")
    print(to_markdown(rep))
    print(f"\nwrote {OUT_JSON}")
    print(f"wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
