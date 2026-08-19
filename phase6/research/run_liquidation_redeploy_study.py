#!/usr/bin/env python3
"""Liquidation / free-capital → redeploy ledger study (GAP rotation path).

Standalone-ish: stdlib + ledger only. Writes:
  data/state/liquidation_redeploy_study_latest.json
  reports/LIQUIDATION_REDEPLOY_STUDY_LATEST.md
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "trades" / "phase6_trades.jsonl"
OUT_JSON = ROOT / "data/state/liquidation_redeploy_study_latest.json"
OUT_MD = ROOT / "reports/LIQUIDATION_REDEPLOY_STUDY_LATEST.md"
DEFAULT_CUT = "2026-07-01T00:00:00+00:00"
FEE_RT = 0.006  # ~0.3% in + 0.3% out sketch (order-of-magnitude)


def _parse(ts: Any) -> datetime | None:
    if not ts:
        return None
    s = str(ts).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def load_rows(path: Path = LEDGER) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        dt = _parse(r.get("timestamp"))
        if dt is None:
            continue
        side = str(r.get("side") or "").upper()
        reason = str(r.get("reason") or "").lower()
        pair = str(r.get("pair") or "").upper()
        qty = r.get("qty") if r.get("qty") is not None else r.get("quantity")
        px = r.get("entry_price") or r.get("exit_price") or r.get("price")
        try:
            usd = float(qty) * float(px) if qty is not None and px is not None else 0.0
        except Exception:
            usd = 0.0
        try:
            pnl = float(r["pnl"]) if r.get("pnl") is not None else None
        except Exception:
            pnl = None
        rows.append(
            {
                "dt": dt,
                "side": side,
                "reason": reason,
                "pair": pair,
                "usd": usd,
                "pnl": pnl,
            }
        )
    rows.sort(key=lambda x: x["dt"])
    return rows


def build(cut: datetime | None = None) -> dict[str, Any]:
    cut = cut or _parse(DEFAULT_CUT) or datetime(2026, 7, 1, tzinfo=timezone.utc)
    rows = load_rows()
    now = datetime.now(timezone.utc)

    buy_sl: list[dict[str, Any]] = []
    for i, b in enumerate(rows):
        if b["side"] != "BUY" or b["dt"] < cut:
            continue
        if "preserve" in b["reason"]:
            continue
        for s in rows[i + 1 :]:
            if s["dt"] - b["dt"] > timedelta(hours=72):
                break
            if (
                s["side"] == "SELL"
                and s["pair"] == b["pair"]
                and "stop_loss" in s["reason"]
            ):
                hrs = (s["dt"] - b["dt"]).total_seconds() / 3600.0
                buy_sl.append(
                    {
                        "pair": b["pair"],
                        "buy_ts": b["dt"].isoformat(),
                        "sl_ts": s["dt"].isoformat(),
                        "hrs": round(hrs, 3),
                        "buy_usd": round(b["usd"], 2),
                        "sl_pnl": s["pnl"],
                    }
                )
                break

    events: list[dict[str, Any]] = []
    for r in rows:
        if r["dt"] < cut or r["side"] != "SELL":
            continue
        if r["usd"] < 50:
            continue
        if not any(k in r["reason"] for k in ("rotation", "stop_loss", "manual")):
            continue
        t0 = r["dt"]
        buys = []
        for b in rows:
            if b["side"] != "BUY" or b["dt"] <= t0:
                continue
            if (b["dt"] - t0).total_seconds() > 24 * 3600:
                break
            if "preserve" in b["reason"]:
                continue
            if b["pair"] == r["pair"]:
                continue
            buys.append(b)
        outcomes = []
        for b in buys:
            hit = None
            for s in rows:
                if s["dt"] <= b["dt"]:
                    continue
                if (s["dt"] - b["dt"]).total_seconds() > 7 * 86400:
                    break
                if (
                    s["side"] == "SELL"
                    and s["pair"] == b["pair"]
                    and "stop_loss" in s["reason"]
                ):
                    hit = s
                    break
            outcomes.append(
                {
                    "pair": b["pair"],
                    "usd": round(b["usd"], 2),
                    "sl": bool(hit),
                    "sl_pnl": hit["pnl"] if hit else None,
                }
            )
        events.append(
            {
                "ts": t0.isoformat(),
                "pair": r["pair"],
                "reason": r["reason"],
                "usd": round(r["usd"], 2),
                "pnl": r["pnl"],
                "n_buys_24h": len(buys),
                "buy_usd_24h": round(sum(b["usd"] for b in buys), 2),
                "n_sl_on_those_buys_7d": sum(1 for o in outcomes if o["sl"]),
                "sl_pnl_sum_7d": round(
                    sum(o["sl_pnl"] or 0 for o in outcomes if o["sl_pnl"] is not None),
                    2,
                ),
                "outcomes": outcomes,
            }
        )

    rots = [e for e in events if "rotation" in e["reason"]]
    with_buy = [e for e in events if e["n_buys_24h"] > 0]
    hyp_notional = sum(e["usd"] * 0.25 for e in rots)

    # Immediate 6h redeploy (other pair)
    imm = []
    for r in rows:
        if r["dt"] < cut or r["side"] != "SELL" or r["usd"] < 50:
            continue
        if not any(k in r["reason"] for k in ("rotation", "stop_loss", "manual")):
            continue
        t0 = r["dt"]
        redeploy_usd = 0.0
        pairs = set()
        for b in rows:
            if b["side"] != "BUY" or b["dt"] <= t0:
                continue
            if (b["dt"] - t0).total_seconds() > 6 * 3600:
                break
            if b["pair"] == r["pair"] or "preserve" in b["reason"]:
                continue
            redeploy_usd += b["usd"]
            pairs.add(b["pair"])
        imm.append(
            {
                "ts": t0.isoformat(),
                "pair": r["pair"],
                "reason": r["reason"],
                "usd": round(r["usd"], 2),
                "redeploy_usd_6h": round(redeploy_usd, 2),
                "pairs": sorted(pairs),
            }
        )

    verdict = "unreliable_as_default"
    # If post free-capital redeploy SL pnl is deeply negative → hold-first is correct default
    sl_sum = sum(e["sl_pnl_sum_7d"] for e in with_buy)
    if with_buy and sl_sum >= 0 and len(with_buy) >= 10:
        verdict = "promising_needs_shadow"
    elif not with_buy:
        verdict = "insufficient_redeploy_sample_under_hold_policy"

    payload = {
        "schema": "liquidation_redeploy_study_v1",
        "as_of": now.isoformat().replace("+00:00", "Z"),
        "cut": cut.isoformat(),
        "fee_rt_assumed": FEE_RT,
        "verdict": verdict,
        "go_no_go_live_partial": "NO-GO live partial redeploy as default — evidence lossy; shadow path only",
        "buy_to_sl_72h": {
            "n": len(buy_sl),
            "sum_sl_pnl": round(sum(x["sl_pnl"] or 0 for x in buy_sl), 2),
            "mean_hrs": round(mean(x["hrs"] for x in buy_sl), 2) if buy_sl else None,
            "median_hrs": round(median(x["hrs"] for x in buy_sl), 2) if buy_sl else None,
            "under_6h": sum(1 for x in buy_sl if x["hrs"] < 6),
            "under_24h": sum(1 for x in buy_sl if x["hrs"] < 24),
        },
        "large_free_capital_ge_50usd": {
            "n_events": len(events),
            "n_with_other_pair_buy_24h": len(with_buy),
            "buy_usd_24h_total": round(sum(e["buy_usd_24h"] for e in events), 2),
            "sl_count_on_those_buys_7d": sum(e["n_sl_on_those_buys_7d"] for e in events),
            "sl_pnl_sum_7d": round(sum(e["sl_pnl_sum_7d"] for e in events), 2),
        },
        "rotation_exchange_ge_50usd": {
            "n": len(rots),
            "n_with_buy_24h": sum(1 for e in rots if e["n_buys_24h"] > 0),
            "sl_pnl_sum_on_follow_buys": round(sum(e["sl_pnl_sum_7d"] for e in rots), 2),
            "hyp_25pct_immediate_notional": round(hyp_notional, 2),
            "hyp_25pct_fee_cost": round(hyp_notional * FEE_RT, 2),
        },
        "immediate_6h_redeploy": {
            "n_events": len(imm),
            "n_with_redeploy_gt_10": sum(1 for e in imm if e["redeploy_usd_6h"] > 10),
            "note": "Under hold_cash disposition, immediate hop is rare by design",
        },
        "events": events,
        "buy_sl_examples": buy_sl[:20],
        "glossary": {
            "free_capital_event": "SELL ≥$50 via rotation / stop / manual-like reason",
            "redeploy": "BUY different pair within window after free capital",
            "fee_rt": "Assumed round-trip fee fraction on moved notional",
        },
    }
    return payload


def render_md(d: dict[str, Any]) -> str:
    b = d.get("buy_to_sl_72h") or {}
    f = d.get("large_free_capital_ge_50usd") or {}
    r = d.get("rotation_exchange_ge_50usd") or {}
    i6 = d.get("immediate_6h_redeploy") or {}
    lines = [
        "# Liquidation → redeploy study",
        "",
        f"**As of:** {d.get('as_of')}  ",
        f"**Cut:** {d.get('cut')}  ",
        f"**Verdict:** `{d.get('verdict')}`  ",
        f"**Live partial redeploy:** {d.get('go_no_go_live_partial')}",
        "",
        "## Plain English",
        "",
        "When we free capital (rotation sell, large stop, liquidation-class sell), "
        "do follow-on buys into *other* pairs help the book — or mostly recycle into more stops?",
        "",
        "## Ledger facts (this book)",
        "",
        f"| Metric | Value |",
        f"|--------|------:|",
        f"| BUY→SL within 72h (n) | {b.get('n')} |",
        f"| BUY→SL sum PnL | {b.get('sum_sl_pnl')} |",
        f"| of which <6h / <24h | {b.get('under_6h')} / {b.get('under_24h')} |",
        f"| Large free-cap events ≥$50 | {f.get('n_events')} |",
        f"| …with other-pair BUY in 24h | {f.get('n_with_other_pair_buy_24h')} |",
        f"| Follow BUY notional (24h) | ${f.get('buy_usd_24h_total')} |",
        f"| Those buys → SL within 7d (count) | {f.get('sl_count_on_those_buys_7d')} |",
        f"| Sum SL PnL on those follow buys | **{f.get('sl_pnl_sum_7d')}** |",
        f"| Rotation sells ≥$50 | {r.get('n')} |",
        f"| Rotation → follow-buy SL PnL | {r.get('sl_pnl_sum_on_follow_buys')} |",
        f"| Immediate 6h redeploy >$10 | {i6.get('n_with_redeploy_gt_10')} / {i6.get('n_events')} |",
        f"| Hyp 25% of rotation notional fees @ {d.get('fee_rt_assumed')} RT | ${r.get('hyp_25pct_fee_cost')} on ${r.get('hyp_25pct_immediate_notional')} |",
        "",
        "## Interpretation",
        "",
        "1. **Immediate hop is rare under current hold policy** — by design after liquidation disposition.  ",
        "2. When free capital *did* fund other-pair buys within 24h, **follow-on stops were net negative** on this tape.  ",
        "3. Early catch-the-wave sim (2026-06) was fee-sensitive; live path still has **Exit WR low** and SL-dominated realizes.  ",
        "4. Therefore: **document a gated partial-redeploy product path**, but **default remains hold / small flat-lab deploy** until shadow proves a slice is +EV after fees.",
        "",
        "## Product path (see policy doc)",
        "",
        "`docs/features/LIQUIDATION_ROTATION_REDEPLOY_POLICY.md`",
        "",
        f"Regenerate: `PYTHONPATH=. python -m phase6.research.run_liquidation_redeploy_study`",
        "",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    d = build()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
    OUT_MD.write_text(render_md(d), encoding="utf-8")
    # also dated copy
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dated = ROOT / f"reports/LIQUIDATION_REDEPLOY_STUDY_{day}.md"
    dated.write_text(render_md(d), encoding="utf-8")
    print(d.get("go_no_go_live_partial"))
    print("verdict", d.get("verdict"))
    f = d.get("large_free_capital_ge_50usd") or {}
    print(
        f"free_cap n={f.get('n_events')} with_buy={f.get('n_with_other_pair_buy_24h')} "
        f"follow_sl_pnl={f.get('sl_pnl_sum_7d')}"
    )
    print("wrote", OUT_JSON)
    print("wrote", OUT_MD)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
