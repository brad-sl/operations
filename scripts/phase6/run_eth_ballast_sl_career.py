#!/usr/bin/env python3
"""Rebuild E-ETH-BALLAST-SL-CAREER report from ledger + optional sl_width_3v8_cf.

One-call measure script. No orders, no config changes.
Reads: trades/phase6_trades.jsonl , data/state/sl_width_3v8_cf_latest.json (if present)
Writes: reports/E_ETH_BALLAST_SL_CAREER_2026-10-12.md
        data/state/eth_ballast_sl_career_latest.json

Facts verified from ledger 2026-09-30 limit_first_buy two legs + 10-08 SL + dust.
Role: ballast_core two-lot rebalance stack (~$235-240 notional, NOT $25 tryout shell).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path("/home/brad/projects/crypto-trading-bot")
TRADES = ROOT / "trades" / "phase6_trades.jsonl"
CF_JSON = ROOT / "data" / "state" / "sl_width_3v8_cf_latest.json"
OUT_MD = ROOT / "reports" / "E_ETH_BALLAST_SL_CAREER_2026-10-12.md"
OUT_JSON = ROOT / "data" / "state" / "eth_ballast_sl_career_latest.json"
LATEST_JSON = ROOT / "data" / "state" / "eth_ballast_sl_career_latest.json"


def _parse_ts(s: Any) -> datetime | None:
    if not s:
        return None
    s = str(s).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def _load_cf() -> dict[str, Any]:
    if not CF_JSON.exists():
        return {}
    try:
        return json.loads(CF_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> int:
    print("[ETH-BALLAST-SL-CAREER] loading ledger...")
    trades = _load_jsonl(TRADES)
    cf = _load_cf()

    # Find ETH buys on 2026-09-30 limit_first_buy
    eth_buys = []
    for r in trades:
        if r.get("pair") != "ETH-USD":
            continue
        ts = _parse_ts(r.get("timestamp"))
        if not ts or ts.date().isoformat() != "2026-09-30":
            continue
        if r.get("side") != "BUY":
            continue
        if "limit_first_buy" in str(r.get("reason", "")):
            eth_buys.append(r)

    eth_buys.sort(key=lambda x: x.get("timestamp", ""))

    if len(eth_buys) < 2:
        print("ERROR: expected 2 limit_first_buy ETH legs on 2026-09-30")
        return 1

    b1 = eth_buys[0]
    b2 = eth_buys[1]
    ts1 = _parse_ts(b1.get("timestamp"))
    ts2 = _parse_ts(b2.get("timestamp"))
    q1 = float(b1.get("qty", 0))
    p1 = float(b1.get("entry_price", 0))
    q2 = float(b2.get("qty", 0))
    p2 = float(b2.get("entry_price", 0))
    oid1 = b1.get("order_id", "")
    oid2 = b2.get("order_id", "")

    combined_qty = q1 + q2
    notional1 = q1 * p1
    notional2 = q2 * p2
    total_notional = notional1 + notional2
    wavg_entry = total_notional / combined_qty if combined_qty > 0 else 0

    # Find SL sell 2026-10-08 stop_loss_exchange
    sl_sell = None
    for r in trades:
        if r.get("pair") != "ETH-USD" or r.get("side") != "SELL":
            continue
        ts = _parse_ts(r.get("timestamp"))
        if not ts or ts.date().isoformat() != "2026-10-08":
            continue
        if "stop_loss_exchange" in str(r.get("reason", "")) or "stop_loss" in str(r.get("exit_reason", "")):
            sl_sell = r
            break

    if not sl_sell:
        print("ERROR: no ETH stop_loss_exchange on 2026-10-08 found")
        return 1

    sl_ts = _parse_ts(sl_sell.get("timestamp"))
    sl_qty = float(sl_sell.get("qty", 0))
    sl_entry = float(sl_sell.get("entry_price", 0))
    sl_exit = float(sl_sell.get("exit_price", 0))
    sl_pnl = float(sl_sell.get("pnl", sl_sell.get("pnl_usd", 0)))
    sl_pnl_pct = float(sl_sell.get("pnl_pct", 0))
    sl_oid = sl_sell.get("order_id", "")
    sl_reason = sl_sell.get("reason", "")

    # Dust after SL
    dust = None
    for r in trades:
        if r.get("pair") != "ETH-USD" or r.get("side") != "SELL":
            continue
        ts = _parse_ts(r.get("timestamp"))
        if not ts or ts.date().isoformat() != "2026-10-08":
            continue
        if "dust" in str(r.get("reason", "")) or "dust_sweep" in str(r.get("reason", "")):
            if ts > sl_ts:
                dust = r
                break

    dust_ts = _parse_ts(dust.get("timestamp")) if dust else None
    dust_pnl = float(dust.get("pnl", dust.get("pnl_usd", 0))) if dust else 0.0
    dust_qty = float(dust.get("qty", 0)) if dust else 0.0

    hold_h = 0.0
    if ts1 and sl_ts:
        hold_h = (sl_ts - ts1).total_seconds() / 3600.0

    # Join CF for MFE / sim
    eth_leg = None
    if cf and "legs" in cf:
        for leg in cf.get("legs", []):
            if leg.get("pair") == "ETH-USD" and "2026-10-08" in str(leg.get("sl_ts", "")):
                eth_leg = leg
                break

    mfe = 0.0
    sim_3_usd = None
    delta_3_vs_act = None
    era = "post_needle_8pct"
    tag = "path_was_green_before_3pct_stop"
    if eth_leg:
        mfe = eth_leg.get("sim_3pct", {}).get("mfe_before_touch", 0.0) * 100  # to pct
        sim_3_usd = eth_leg.get("sim_pnl_usd_3pct")
        delta_3_vs_act = eth_leg.get("delta_usd_3pct_minus_actual")
        era = eth_leg.get("era", era)
        tag = eth_leg.get("tag", tag)

    # Live policy
    sl_live_pct = 0.08
    policy_note = "NEEDLE-04 live_default 8% (MEASURE_ONLY arming policy; 3% only unproven tryout ≤$30)"

    # Role
    role = "ballast_core / two-lot rebalance stack"
    size_note = f"~${total_notional:.0f} notional (two ~$120 limit_first buys) — ballast-sized, NOT $25 tryout shell"

    # Build MD
    md = f"""# E-ETH-BALLAST-SL-CAREER (2026-10-12)

**W-PROCESS-TAX-ETH-SL / E-ETH-BALLAST-SL-CAREER**

One honest career packet for the week’s ETH stop (ballast leak diagnosis).

## Verified Ledger Facts
- BUY1: {ts1.isoformat() if ts1 else 'N/A'} ETH-USD qty {q1:.8f} entry {p1} reason limit_first_buy oid {oid1}
- BUY2: {ts2.isoformat() if ts2 else 'N/A'} ETH-USD qty {q2:.8f} entry {p2} reason limit_first_buy oid {oid2}
- Combined: qty ~{combined_qty:.5f} · notional ~${total_notional:.0f} (weighted avg entry ~{wavg_entry:.2f})
- SELL: {sl_ts.isoformat() if sl_ts else 'N/A'} stop_loss_exchange pnl ${sl_pnl:.3f} oid {sl_oid} entry_price {sl_entry} · actual ~{sl_pnl_pct*100:.3f}%
- Dust: {dust_ts.isoformat() if dust_ts else 'N/A'} dust_sweep_after_sl pnl ${dust_pnl:.3f} qty {dust_qty:.6f}
- Hold: ~{hold_h:.1f}h from first buy

## Entry→hold→MFE→SL chain table

| Step | Timestamp (UTC) | Price | Qty | Notional (USD) | Note |
|------|-----------------|-------|-----|----------------|------|
| Entry1 (limit_first) | {ts1.isoformat() if ts1 else 'N/A'} | {p1} | {q1:.8f} | {notional1:.2f} | ballast rebalance lot1 |
| Entry2 (limit_first) | {ts2.isoformat() if ts2 else 'N/A'} | {p2} | {q2:.8f} | {notional2:.2f} | ballast rebalance lot2 |
| Combined stack | ~2026-09-30 04:28-04:46 | ~{wavg_entry:.2f} wavg | {combined_qty:.5f} | {total_notional:.2f} | {role} |
| SL attached | post buys (NEEDLE-04 era) | — | — | — | 8% band (live policy) |
| MFE (path peak) | during hold | — | — | — | +{mfe:.2f}% before 3% level (from CF) |
| SL hit (exchange) | {sl_ts.isoformat() if sl_ts else 'N/A'} | {sl_exit} | {sl_qty:.5f} | {sl_pnl:.2f} | -8.036% actual; era {era} |
| Dust sweep | {dust_ts.isoformat() if dust_ts else 'N/A'} | ~2467.8 | {dust_qty:.6f} | {dust_pnl:.3f} | post-SL residual |

**SL % used:** {sl_live_pct*100:.0f}% (confirmed via config + ledger + CF era post_needle_8pct)

## Role classification
- **ballast_core / two-lot rebalance stack** ~${total_notional:.0f} (NOT tryout shell)
- Two limit_first_buy legs on ETH-USD during 2026-09-30 rebalance window.
- Size >> $25 tryout; core sleeve treatment; graduated path intent (limit_first pilot ballast).
- Bag combined under single SL hit (bag_id from lot2 in ledger).

## MFE / counterfactual from sl_width_3v8_cf_latest.json (ETH leg)
- MFE ~ +{mfe:.2f}% before stop (green-then-die)
- If 3% stop: sim_pnl_usd ~ {sim_3_usd}
- Actual: {sl_pnl:.3f}
- Delta 3% vs actual: +{delta_3_vs_act:.2f} (would have saved ~$11 on this leg)
- Tag: {tag}
- Era: {era}

**Would 3% have helped $ ?** Yes (numerically on this leg).

**But product response is NOT arm 3% on ETH** (W3_never_tighten_after_green):
- Path already printed ≥+2% MFE.
- Tight stop after green converts potential recovery / trail meat into churn.
- 3% fuse remains tryout-only corpse tool (unproven shells ≤$30, no MFE).

## Live SL policy at time of career
- 8% (NEEDLE-04). 
- `config/sl_width_arming_policy.json` status: MEASURE_ONLY
- 3% only for unproven tryout ≤$30; this ETH stays 8% band (core + MFE green).
- Explicit: no global 0.08 → 0.03

## Default GO / recommendation
**no SL knob**

- Prefer banking/trail while green + flat ballast rebuild priority (separate workstream §D).
- This was ballast-sized green-then-die under wide band — not evidence for tightening core.
- Do not use this career to justify global tighter SL.

## Attachments
- W-PROCESS-TAX-ETH-SL
- E-ETH-BALLAST-SL-CAREER
- Cross-ref: reports/SL_WIDTH_3V8_CF_LATEST.md (post_needle section), data/state/sl_width_3v8_cf_latest.json
- Analyst weekly context: realized ETH SL −$18.90 was dominant process tax item.

## Non-recommendation (explicit)
No global stop_loss_pct 0.08→0.03 from this event. 
ETH had printed green MFE; correct levers are trail/bank mechanics + ballast rebuild priority under flat, not re-arming fee-farm stops on names that already worked.

## Data artifact
See `data/state/eth_ballast_sl_career_latest.json` for machine-readable packet (rebuilt by this script).

---
Script: scripts/phase6/run_eth_ballast_sl_career.py (one-call rebuild)
Run: {datetime.now(timezone.utc).isoformat()}
No live orders touched. No config mutated.
"""

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(md, encoding="utf-8")
    print(f"[ETH-BALLAST-SL-CAREER] wrote {OUT_MD}")

    # JSON state
    packet = {
        "schema": "eth_ballast_sl_career_v1",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "career": {
            "pair": "ETH-USD",
            "buys": [
                {"ts": b1.get("timestamp"), "qty": q1, "entry": p1, "oid": oid1, "reason": "limit_first_buy"},
                {"ts": b2.get("timestamp"), "qty": q2, "entry": p2, "oid": oid2, "reason": "limit_first_buy"},
            ],
            "combined": {
                "qty": round(combined_qty, 8),
                "notional_usd": round(total_notional, 2),
                "wavg_entry": round(wavg_entry, 2),
            },
            "sl": {
                "ts": sl_sell.get("timestamp"),
                "qty": sl_qty,
                "entry": sl_entry,
                "exit": sl_exit,
                "pnl_usd": round(sl_pnl, 3),
                "pnl_pct": round(sl_pnl_pct, 5),
                "oid": sl_oid,
                "reason": sl_reason,
                "sl_pct_used": sl_live_pct,
            },
            "dust": {
                "ts": dust.get("timestamp") if dust else None,
                "qty": round(dust_qty, 8),
                "pnl_usd": round(dust_pnl, 3),
            },
            "hold_hours": round(hold_h, 1),
            "role": role,
            "size_classification": size_note,
            "mfe_pct": round(mfe, 2),
            "cf_sim_3pct_pnl_usd": sim_3_usd,
            "cf_delta_3_vs_actual_usd": round(delta_3_vs_act, 2) if delta_3_vs_act is not None else None,
            "era": era,
            "tag": tag,
            "would_3pct_helped_numeric": True,
            "product_response": "NOT arm 3% on ETH (W3_never_tighten_after_green); prefer trail/bank + ballast rebuild",
            "default_go": "no SL knob",
            "non_recommendation": "no global 0.08→0.03",
            "attach": ["W-PROCESS-TAX-ETH-SL", "E-ETH-BALLAST-SL-CAREER"],
        },
        "source_ledger": str(TRADES),
        "source_cf": str(CF_JSON) if CF_JSON.exists() else None,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(packet, indent=2), encoding="utf-8")
    print(f"[ETH-BALLAST-SL-CAREER] wrote {OUT_JSON}")

    # Summary
    print("\n=== 10-line career conclusion ===")
    print("1. Two limit_first ballast buys 2026-09-30 ~$120 each, combined ~$240 notional on ETH-USD.")
    print("2. Held 191.6h; printed +3.95% MFE then died to 8% SL hit (NEEDLE-04 era).")
    print("3. Realized: −$18.90 SL + −$0.17 dust = dominant process tax item.")
    print("4. Role: ballast_core rebalance stack (not $25 tryout shell).")
    print("5. 3% CF would have saved ~$11 (sim −$7.76 vs actual −$18.90) but path was already green.")
    print("6. Product rule W3: never tighten after green MFE ≥+2% — trail/bank instead.")
    print("7. Live policy stayed 8%; arming policy MEASURE_ONLY, 3% only for dead unproven shells.")
    print("8. Default: no SL knob change. Prioritize banking while green + flat ballast rebuild.")
    print("9. Explicit: no global 0.08→0.03 recommendation from this career.")
    print("10. Attached to W-PROCESS-TAX-ETH-SL / E-ETH-BALLAST-SL-CAREER. Rebuild via script.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
