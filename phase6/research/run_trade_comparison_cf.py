#!/usr/bin/env python3
"""Matched-dollar would-block counterfactual for trade comparison standard.

Paper only. Expands correlation/boundary work into $ avoided vs $ missed.

Metrics (honest):
- association: pair SL within H hours after buy (not FIFO lot PnL)
- notional_blocked / notional_on_sl_path
- precision = P(sl_Hh | would_block)
- lift vs baseline
- false-negative rate among sl events
- boundary table for A/B/D/mega rule variants

No orders. No live evaluate_buy_entry writes.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.trade_comparison_standard import (  # noqa: E402
    buy_event,
    exit_class,
    is_clean_buy,
    load_ledger_rows,
    sell_event,
    would_block_buy,
)

STATE = ROOT / "data" / "state"
REPORTS = ROOT / "reports"

FOCUS = [
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "XRP-USD",
    "DOGE-USD",
    "LINK-USD",
    "AVAX-USD",
    "UNI-USD",
    "ADA-USD",
    "ARB-USD",
    "ICP-USD",
    "NEAR-USD",
    "ZEC-USD",
    "STX-USD",
]


def _build_records(rows: List[Dict[str, Any]], pairs: List[str], sl_h: float = 72.0) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for pair in pairs:
        pr = [r for r in rows if r.get("pair") == pair]
        buys = [buy_event(r) for r in pr if is_clean_buy(r)]
        sells = [sell_event(r) for r in pr if r.get("side") == "SELL"]
        sls = [s for s in sells if exit_class(s.get("reason") or "") == "stop_loss" and s.get("ts")]
        tps = [s for s in sells if exit_class(s.get("reason") or "") == "take_profit" and s.get("ts")]
        for b in buys:
            if not b.get("ts"):
                continue
            usd = float(b.get("usd") or 0.0)
            rsi = b.get("rsi")
            hrs_sl = None
            for s in reversed(sls):
                if s["ts"] < b["ts"]:
                    hrs_sl = (b["ts"] - s["ts"]).total_seconds() / 3600.0
                    break
            hrs_tp = None
            for s in reversed(tps):
                if s["ts"] < b["ts"]:
                    hrs_tp = (b["ts"] - s["ts"]).total_seconds() / 3600.0
                    break
            sl_soon = any(
                s["ts"] > b["ts"] and (s["ts"] - b["ts"]).total_seconds() <= sl_h * 3600 for s in sls
            )
            # next sell pnl window 10d (book stress, not lot match)
            win_sells = [
                s
                for s in sells
                if s.get("ts") and s["ts"] > b["ts"] and (s["ts"] - b["ts"]).days <= 10
            ]
            pnl_10 = sum(float(s.get("pnl") or 0.0) for s in win_sells)
            winb = [
                x
                for x in buys
                if x.get("ts") and b["ts"] - timedelta(days=7) <= x["ts"] <= b["ts"]
            ]
            cum7 = sum(float(x.get("usd") or 0.0) for x in winb)
            out.append(
                {
                    "pair": pair,
                    "ts": b["ts"],
                    "usd": usd,
                    "rsi": rsi,
                    "hrs_sl": hrs_sl,
                    "hrs_tp": hrs_tp,
                    "sl_soon": sl_soon,
                    "pnl_10": pnl_10,
                    "post_sl_48": hrs_sl is not None and 0 < hrs_sl <= 48,
                    "post_sl_72": hrs_sl is not None and 0 < hrs_sl <= 72,
                    "post_tp_48": hrs_tp is not None and 0 < hrs_tp <= 48,
                    "elev_rsi_large": rsi is not None and float(rsi) >= 55 and usd >= 150,
                    "rsi_ge60": rsi is not None and float(rsi) >= 60,
                    "mega": usd >= 500,
                    "large": usd >= 150,
                    "pile_on": len(winb) >= 3 and cum7 >= 450,
                    "majors": pair in ("BTC-USD", "ETH-USD"),
                    "alt": pair not in ("BTC-USD", "ETH-USD"),
                }
            )
    return out


RuleFn = Callable[[Dict[str, Any]], bool]


def _rules() -> Dict[str, RuleFn]:
    return {
        "A48_post_sl": lambda r: r["post_sl_48"],
        "A72_post_sl": lambda r: r["post_sl_72"],
        "B48_post_tp": lambda r: r["post_tp_48"],
        "B48_post_tp_large": lambda r: r["post_tp_48"] and r["usd"] > 150,
        "D_elev_rsi_large": lambda r: r["elev_rsi_large"],
        "D_rsi60_any": lambda r: r["rsi_ge60"],
        "C_mega": lambda r: r["mega"],
        "OR_A48_B48_D": lambda r: r["post_sl_48"] or r["post_tp_48"] or r["elev_rsi_large"],
        "OR_A48_B48_D_mega": lambda r: r["post_sl_48"]
        or r["post_tp_48"]
        or r["elev_rsi_large"]
        or r["mega"],
        "OR_A72_D_mega": lambda r: r["post_sl_72"] or r["elev_rsi_large"] or r["mega"],
        "OR_A48_alts_only": lambda r: r["post_sl_48"] and r["alt"],
        "sweet_A48_B_large_D": lambda r: r["post_sl_48"]
        or (r["post_tp_48"] and r["usd"] > 150)
        or r["elev_rsi_large"],
    }


def _score_rule(records: List[Dict[str, Any]], pred: RuleFn) -> Dict[str, Any]:
    n = len(records)
    base = sum(1 for r in records if r["sl_soon"]) / n if n else 0.0
    blk = [r for r in records if pred(r)]
    allow = [r for r in records if not pred(r)]
    nb, na = len(blk), len(allow)
    p_blk = sum(1 for r in blk if r["sl_soon"]) / nb if nb else 0.0
    p_all = sum(1 for r in allow if r["sl_soon"]) / na if na else 0.0
    notional_blk = sum(r["usd"] for r in blk)
    notional_risk = sum(r["usd"] for r in blk if r["sl_soon"])
    sl_events = [r for r in records if r["sl_soon"]]
    caught = sum(1 for r in sl_events if pred(r))
    missed = len(sl_events) - caught
    fp = sum(1 for r in blk if not r["sl_soon"])
    return {
        "n_block": nb,
        "coverage_pct": round(100.0 * nb / n, 2) if n else 0.0,
        "precision_sl": round(p_blk, 4),
        "baseline_sl": round(base, 4),
        "lift": round(p_blk / base, 3) if base > 0 else None,
        "allow_sl_rate": round(p_all, 4),
        "notional_blocked_usd": round(notional_blk, 2),
        "notional_blocked_on_sl_path_usd": round(notional_risk, 2),
        "sl_events_caught": caught,
        "sl_events_missed": missed,
        "recall_sl": round(caught / len(sl_events), 4) if sl_events else None,
        "false_positives": fp,
        "mean_usd_blocked": round(notional_blk / nb, 2) if nb else 0.0,
        "mean_pnl10_blocked": round(sum(r["pnl_10"] for r in blk) / nb, 2) if nb else None,
        "mean_pnl10_allow": round(sum(r["pnl_10"] for r in allow) / na, 2) if na else None,
    }


def _boundary_sweeps(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    base = sum(1 for r in records if r["sl_soon"]) / len(records) if records else 0.0
    sl_hours = []
    for H in (6, 12, 24, 36, 48, 72, 96, 168):
        flagged = [r for r in records if r["hrs_sl"] is not None and 0 < r["hrs_sl"] <= H]
        if len(flagged) < 3:
            sl_hours.append({"H": H, "n": len(flagged), "sparse": True})
            continue
        p = sum(1 for r in flagged if r["sl_soon"]) / len(flagged)
        sl_hours.append(
            {
                "H": H,
                "n": len(flagged),
                "p_sl": round(p, 4),
                "lift": round(p / base, 3) if base else None,
            }
        )
    usd_floor = []
    for thr in (50, 100, 150, 250, 500, 1000):
        flagged = [r for r in records if r["usd"] >= thr]
        if len(flagged) < 3:
            continue
        p = sum(1 for r in flagged if r["sl_soon"]) / len(flagged)
        usd_floor.append(
            {
                "usd_ge": thr,
                "n": len(flagged),
                "p_sl": round(p, 4),
                "lift": round(p / base, 3) if base else None,
                "notional": round(sum(r["usd"] for r in flagged), 2),
            }
        )
    rsi_large = [r for r in records if r["usd"] >= 150 and r["rsi"] is not None]
    rsi_rows = []
    if rsi_large:
        bL = sum(1 for r in rsi_large if r["sl_soon"]) / len(rsi_large)
        for thr in (40, 45, 50, 55, 60, 65):
            flagged = [r for r in rsi_large if float(r["rsi"]) >= thr]
            if len(flagged) < 2:
                continue
            p = sum(1 for r in flagged if r["sl_soon"]) / len(flagged)
            rsi_rows.append(
                {
                    "rsi_ge": thr,
                    "n": len(flagged),
                    "p_sl": round(p, 4),
                    "lift_vs_large": round(p / bL, 3) if bL else None,
                }
            )
    majors = [r for r in records if r["majors"]]
    alts = [r for r in records if r["alt"]]

    def slice_stats(name: str, sub: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not sub:
            return {"name": name, "n": 0}
        p = sum(1 for r in sub if r["sl_soon"]) / len(sub)
        return {
            "name": name,
            "n": len(sub),
            "p_sl": round(p, 4),
            "notional": round(sum(r["usd"] for r in sub), 2),
            "notional_sl_path": round(sum(r["usd"] for r in sub if r["sl_soon"]), 2),
        }

    return {
        "post_sl_hours": sl_hours,
        "usd_floor": usd_floor,
        "rsi_on_large": rsi_rows,
        "book_split": [
            slice_stats("majors", majors),
            slice_stats("alts", alts),
            slice_stats("LINK", [r for r in records if r["pair"] == "LINK-USD"]),
        ],
        "pile_on_horizon": {
            "note": "pile_on inverse at 72h; catches up 7–14d — inventory cap not timing OR",
            "pile_n": sum(1 for r in records if r["pile_on"]),
            "pile_p72": round(
                sum(1 for r in records if r["pile_on"] and r["sl_soon"])
                / max(1, sum(1 for r in records if r["pile_on"])),
                4,
            ),
        },
    }


def run_cf(
    pairs: Optional[List[str]] = None,
    sl_h: float = 72.0,
) -> Dict[str, Any]:
    rows = load_ledger_rows()
    present = {str(r.get("pair") or "") for r in rows}
    pairs = [p for p in (pairs or FOCUS) if p in present]
    records = _build_records(rows, pairs, sl_h=sl_h)
    n = len(records)
    base = sum(1 for r in records if r["sl_soon"]) / n if n else 0.0
    rule_scores = {name: _score_rule(records, fn) for name, fn in _rules().items()}
    sweet = rule_scores.get("sweet_A48_B_large_D") or rule_scores.get("OR_A48_B48_D") or {}

    # would_block_buy API check on a sample of large buys
    api_sample = []
    for r in sorted(records, key=lambda x: -x["usd"])[:15]:
        sells = [
            sell_event(x)
            for x in load_ledger_rows(pair=r["pair"])
            if x.get("side") == "SELL"
        ]
        wb = would_block_buy(
            pair=r["pair"],
            buy_ts=r["ts"],
            usd=r["usd"],
            rsi=r["rsi"],
            recent_sells=sells,
            sl_cooldown_h=48,
            tp_cooldown_h=48,
            tryout_usd=150,
            elevated_rsi=55,
        )
        api_sample.append(
            {
                "pair": r["pair"],
                "ts": r["ts"].isoformat(),
                "usd": r["usd"],
                "sl_soon": r["sl_soon"],
                "would_block": wb.get("block"),
                "reasons": wb.get("reasons"),
            }
        )

    payload = {
        "schema": "trade_comparison_cf_v1",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "edge_class": "ATTENTION_ONLY_less_loss_path",
        "live": False,
        "metric_note": (
            "sl_soon = pair stop_loss sell within sl_h after buy — association not FIFO lot PnL. "
            "Dollar figures are notional on path, not guaranteed saved PnL."
        ),
        "sl_horizon_h": sl_h,
        "n_buys": n,
        "n_pairs": len(pairs),
        "pairs": pairs,
        "baseline_p_sl": round(base, 4),
        "total_notional_usd": round(sum(r["usd"] for r in records), 2),
        "notional_on_sl_path_usd": round(sum(r["usd"] for r in records if r["sl_soon"]), 2),
        "rule_scores": rule_scores,
        "recommended_shadow_rule": "sweet_A48_B_large_D",
        "recommended_score": sweet,
        "boundaries": _boundary_sweeps(records),
        "concentration": {
            k: Counter(r["pair"] for r in records if r[k]).most_common(6)
            for k in ("post_sl_48", "post_tp_48", "elev_rsi_large", "mega", "pile_on")
        },
        "would_block_api_sample": api_sample,
        "operator_readout": {
            "primary": "A48 post-SL cooldown multipair lift ~2×; alts ≫ majors",
            "severity": "B post-TP + mega = low n, high $ damage (LINK-class)",
            "rsi": "D fires ≥55 on large; missing RSI on most buys = pass-through",
            "do_not": "OR pile_on into 72h would-block (inverse short-term)",
            "shadow_v1": "sweet_A48_B_large_D — ~18% cov, ~2× lift, no live block",
            "link_tonight": "pair_ticket_cap $150; flat regime effective $75",
        },
    }
    return payload


def render_md(cf: Dict[str, Any]) -> str:
    lines = [
        "# Trade comparison CF (matched would-block)",
        "",
        f"**As of:** {cf.get('as_of')}",
        f"**Schema:** `{cf.get('schema')}`",
        f"**Edge:** `{cf.get('edge_class')}` — paper/shadow only",
        f"**n_buys:** {cf.get('n_buys')} · baseline P(sl@{cf.get('sl_horizon_h')}h)={cf.get('baseline_p_sl')}",
        f"**Notional:** ${cf.get('total_notional_usd')} · on sl-path ${cf.get('notional_on_sl_path_usd')}",
        "",
        f"> {cf.get('metric_note')}",
        "",
        "## Recommended shadow rule",
        "",
        f"**{cf.get('recommended_shadow_rule')}**",
        "",
        "```",
        json.dumps(cf.get("recommended_score"), indent=2),
        "```",
        "",
        "## Rule scoreboard",
        "",
        "| Rule | n | cov% | P(sl|blk) | lift | $blk | $blk@sl | recall |",
        "|------|---|------|-----------|------|------|---------|--------|",
    ]
    for name, s in (cf.get("rule_scores") or {}).items():
        lines.append(
            f"| {name} | {s.get('n_block')} | {s.get('coverage_pct')} | {s.get('precision_sl')} | "
            f"{s.get('lift')} | {s.get('notional_blocked_usd')} | {s.get('notional_blocked_on_sl_path_usd')} | "
            f"{s.get('recall_sl')} |"
        )
    lines.extend(["", "## Boundaries", "", "### Post-SL hours", ""])
    for row in (cf.get("boundaries") or {}).get("post_sl_hours") or []:
        lines.append(f"- {row}")
    lines.extend(["", "### Book split", ""])
    for row in (cf.get("boundaries") or {}).get("book_split") or []:
        lines.append(f"- {row}")
    lines.extend(
        [
            "",
            "## Operator readout",
            "",
        ]
    )
    for k, v in (cf.get("operator_readout") or {}).items():
        lines.append(f"- **{k}:** {v}")
    lines.extend(
        [
            "",
            "## Test plan (next)",
            "",
            "1. Shadow logger only (`run_tcs_shadow_would_block.py`) — no evaluate block.",
            "2. Watch 7d: log would-block on natural buy attempts + compare to fills.",
            "3. LINK pair_ticket_cap $150 live; flat effective $75 tonight.",
            "4. Finalize-report → Brad decide live cooldown (default NO).",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="TCS matched would-block CF (paper)")
    ap.add_argument("--sl-h", type=float, default=72.0)
    ap.add_argument("--out-json", default="")
    ap.add_argument("--out-md", default="")
    args = ap.parse_args(argv)

    cf = run_cf(sl_h=args.sl_h)
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_json = Path(args.out_json) if args.out_json else STATE / "trade_comparison_cf_latest.json"
    out_md = Path(args.out_md) if args.out_md else REPORTS / f"TRADE_COMPARISON_CF_{day}.md"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(cf, indent=2, default=str) + "\n")
    md = render_md(cf)
    out_md.write_text(md)
    (REPORTS / "TRADE_COMPARISON_CF_LATEST.md").write_text(md)

    rec = cf.get("recommended_score") or {}
    print("TRADE_COMPARISON_CF")
    print(f"n_buys={cf.get('n_buys')} baseline_p_sl={cf.get('baseline_p_sl')}")
    print(f"recommended={cf.get('recommended_shadow_rule')} score={json.dumps(rec)}")
    print(f"json={out_json}")
    print(f"md={out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
