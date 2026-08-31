#!/usr/bin/env python3
"""Attach crude buy→sell outcomes from verified fills; refresh summary md."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACC = "3176ac3f-deca-4fca-9c67-87ba91f96558"


def parse_ts(s):
    if not s:
        return None
    s = str(s)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def main() -> int:
    labels = json.loads(
        (ROOT / "reports/ENTRY_PROCESS_VS_HEAT_LABELS_90D.json").read_text()
    )
    sells = []
    vdir = ROOT / f"data/state/trading_log/{ACC}"
    for p in sorted(vdir.glob("verified_fills_*.jsonl")):
        for ln in p.read_text().strip().splitlines():
            d = json.loads(ln)
            if (d.get("side") or "").upper() != "SELL":
                continue
            ts = parse_ts(d.get("timestamp"))
            if not ts:
                continue
            sells.append(
                {
                    "ts": ts,
                    "pair": d.get("pair"),
                    "pnl": d.get("pnl"),
                    "pnl_pct": d.get("pnl_pct"),
                    "fees": d.get("fees"),
                    "reason": d.get("reason") or d.get("exit_reason"),
                }
            )
    sells_by = defaultdict(list)
    for s in sells:
        sells_by[s["pair"]].append(s)
    for p in sells_by:
        sells_by[p].sort(key=lambda x: x["ts"])

    for lab in labels:
        ts = parse_ts(lab["ts"])
        pair = lab["pair"]
        matched = None
        for s in sells_by.get(pair, []):
            if s["ts"] > ts:
                # within 21d window
                if (s["ts"] - ts).days <= 21:
                    matched = s
                break
        if matched and matched.get("pnl") is not None:
            lab["next_sell_pnl"] = float(matched["pnl"])
            lab["next_sell_pnl_pct"] = (
                float(matched["pnl_pct"]) if matched.get("pnl_pct") is not None else None
            )
            lab["next_sell_ts"] = matched["ts"].isoformat()
            lab["next_sell_reason"] = matched.get("reason")
        else:
            lab["next_sell_pnl"] = lab.get("next_sell_pnl")
            lab["next_sell_reason"] = lab.get("next_sell_reason")

    pnl_by = defaultdict(list)
    for lab in labels:
        if lab.get("next_sell_pnl") is not None:
            pnl_by[lab["label"]].append(float(lab["next_sell_pnl"]))

    outcome = {}
    for lab, pnls in pnl_by.items():
        wins = sum(1 for p in pnls if p > 0)
        outcome[lab] = {
            "n_with_exit": len(pnls),
            "win_rate": round(wins / len(pnls), 3) if pnls else None,
            "sum_pnl": round(sum(pnls), 2),
            "avg_pnl": round(sum(pnls) / len(pnls), 2) if pnls else None,
        }

    (ROOT / "reports/ENTRY_PROCESS_VS_HEAT_LABELS_90D.json").write_text(
        json.dumps(labels, indent=2, default=str) + "\n"
    )

    audit = json.loads((ROOT / "reports/FEE_DRAG_AUDIT_LATEST.json").read_text())
    audit["entry_labels_90d"]["outcome_by_label_crude"] = outcome
    audit["entry_labels_90d"]["counts"] = dict(Counter(x["label"] for x in labels))
    audit["entry_labels_90d"]["sample_newest_40"] = labels[:40]
    audit["entry_labels_90d"]["outcome_note"] = (
        "Matched first verified SELL on same pair within 21d after BUY; imperfect lots."
    )
    # fee vs nav
    nav = audit.get("nav_usd_snapshot")
    fr30 = audit["fee_drag"]["30d"]
    fr90 = audit["fee_drag"]["90d"]
    if nav:
        audit["fee_vs_nav"] = {
            "nav_usd": nav,
            "fees_30d_pct_nav": round(fr30["total_fees_usd"] / float(nav) * 100, 3),
            "fees_90d_pct_nav": round(fr90["total_fees_usd"] / float(nav) * 100, 3),
            "note": "Fees / current NAV snapshot — path-dependent; not annualized return.",
        }
    (ROOT / "reports/FEE_DRAG_AUDIT_LATEST.json").write_text(
        json.dumps(audit, indent=2, default=str) + "\n"
    )

    # Rewrite markdown brief with honesty
    now = audit.get("as_of")
    lines = [
        "# Fee drag + entry label audit",
        "",
        f"**As of:** {now}  ",
        f"**NAV snapshot:** ${nav:,.2f}" if isinstance(nav, (int, float)) else f"**NAV:** {nav}",
        "",
        "Read-only. No live changes. Full JSON: `reports/FEE_DRAG_AUDIT_LATEST.json`.",
        "",
        "## Headline (plain English)",
        "",
    ]
    if nav and fr30:
        lines += [
            f"- **Last 30d Coinbase fees paid: ${fr30['total_fees_usd']:.2f}** "
            f"on ~${fr30['total_notional_usd']:,.0f} notional "
            f"(**{fr30['fee_pct_of_notional']}% of notional**).",
            f"- That is **~{audit.get('fee_vs_nav', {}).get('fees_30d_pct_nav')}% of current book NAV** "
            f"(~${nav:,.0f}) in one month of **house cut alone** — before spreads/slippage.",
            f"- **90d fees: ${fr90['total_fees_usd']:.2f}** "
            f"(~{audit.get('fee_vs_nav', {}).get('fees_90d_pct_nav')}% of NAV).",
            f"- Fill mix 30d: **{fr30['by_liq_count']}** — order types are "
            f"**MARKET + STOP_LIMIT only** in verified set (no LIMIT/maker path observed here).",
            f"- Median fee rate on sized fills: **{fr30['fee_pct_median']}%** (p75 {fr30['fee_pct_p75']}%) "
            "→ sits in **taker / high-tier retail** territory, not maker 0.05–0.25%.",
            "",
            "### What this means for the macro discussion",
            "",
            "1. **The house is already winning on this book via turnover style** — "
            "even when individual trades look small.",
            "2. **Aspiration ‘we are makers’ ≠ realized path** on verified fills "
            "(rebalance buys as MARKET; exits often STOP_LIMIT).",
            "3. Cutting **unnecessary round-trips** and preferring true maker entries "
            "is direct edge vs the toll booth — independent of signal IQ.",
            "",
        ]
    lines += [
        "## Fee drag detail",
        "",
        "### 30d",
        f"- Fills: {fr30['n_fills']} (~{fr30['fills_per_day']}/day)",
        f"- Fees by class: `{fr30['fees_by_liq']}`",
        f"- Reasons: `{fr30['top_reasons']}`",
        f"- Order types: `{fr30['order_types']}`",
        f"- Top pairs by fee: `{fr30['top_pairs_by_fee']}`",
        f"- By month (inside 90d window): `{fr90['by_month']}`",
        "",
        "### Method caveats",
        "",
        "- Maker/taker from **order_type heuristic** (LIMIT→maker, STOP→taker_stop, MARKET→taker). "
        "Coinbase liquidity flag not present on these rows.",
        "- Deduped `phase6_exchange_fills.jsonl` + `verified_fills_*.jsonl` by `order_id`.",
        "- August notional/fees jumped vs June–July — check whether larger tickets or more churn.",
        "",
        "## Entry labels (90d)",
        "",
        "Frozen rules:",
        "",
        "- **heat_reaction:** 24h return ≥12% OR (24h ≥8% and RSI ≥70) OR 6h return ≥8% at buy time",
        "- **process:** signal/source hints rebalance/runner/rsi/… AND 24h return <5%",
        "- **process_in_elevated_tape:** process machinery but tape already up",
        "- **ambiguous:** else (often fill-reconcile without clean source tag)",
        "",
        f"**Counts:** `{dict(Counter(x['label'] for x in labels))}`  ",
        f"**Buys labeled:** {len(labels)}",
        "",
        f"**Crude exit outcome** (first verified SELL same pair within 21d): `{outcome}`",
        "",
        "### Read of labels",
        "",
        "- **Heat-chase buys are rare** under these thresholds (good vs pure FOMO narrative).",
        "- Large **process** bucket is mostly `phase6_fresh_start` / `arch4_rebalance` / reconcile — "
        "machinery entries, not Twitter-chase. Still can be *late* on a name without tripping heat rules.",
        "- **ambiguous** needs cleaner `signal_source` on ledger rows for future audits.",
        "- Outcome PnL is **lot-imperfect**; use as directional only. phase6.db `trades` table "
        "is BUY-heavy and not usable for exit WR here.",
        "",
        "### Newest 15",
        "",
    ]
    for row in labels[:15]:
        lines.append(
            f"- `{row.get('ts')}` **{row.get('pair')}** `{row.get('label')}` "
            f"r24={row.get('r24_pct')} r6={row.get('r6_pct')} rsi={row.get('rsi')} "
            f"src=`{(row.get('signal_source') or '')[:28]}` "
            f"next_pnl={row.get('next_sell_pnl')} reason={row.get('next_sell_reason')}"
        )
    lines += [
        "",
        "## Artifacts",
        "",
        "| File | Role |",
        "|------|------|",
        "| `reports/FEE_DRAG_AND_ENTRY_LABEL_AUDIT.md` | This brief |",
        "| `reports/FEE_DRAG_AUDIT_LATEST.json` | Full fee + summary JSON |",
        "| `reports/ENTRY_PROCESS_VS_HEAT_LABELS_90D.json` | Per-buy labels |",
        "| `scripts/phase6/audit_fee_drag_and_entry_labels.py` | Re-run audit |",
        "| `docs/discussions/MACRO_HOUSE_SIZE_REACTION_ONGOING.md` | Macro discussion SSOT |",
        "| `docs/faq/External_Client_FAQ.md` | Client “who gets paid” |",
        "",
        "## Follow-ups (not done tonight)",
        "",
        "1. Why verified path is MARKET-heavy — limit entry path regression?  ",
        "2. Maker fee tier on live Coinbase account vs 0.8% median realized.  ",
        "3. Tighter heat label using discovery score / contender flags.  ",
        "4. Proper lot-matched round-trip PnL after fees.",
        "",
    ]
    (ROOT / "reports/FEE_DRAG_AND_ENTRY_LABEL_AUDIT.md").write_text("\n".join(lines) + "\n")
    print("outcomes", outcome)
    print("fee_vs_nav", audit.get("fee_vs_nav"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
