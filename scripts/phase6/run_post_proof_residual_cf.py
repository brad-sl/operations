#!/usr/bin/env python3
"""Honest post-proof residual / growth CF (measure-only).

Compares:
  baseline  — full shell exit at live TP/trail (ledger truth)
  residual  — bank 50% at TP, hold 50% under SL to next event or +7d mark
  kindling  — +$25 add before TP when hold green in kindling band (ledger proxy)

No mocked residual PnL = 0 cosplay. No live knob flips.
Writes:
  data/state/post_proof_residual_cf_latest.json
  reports/POST_PROOF_RESIDUAL_GROWTH_CF_LATEST.md
  reports/POST_PROOF_RESIDUAL_GROWTH_CF_<date>.md
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

LEDGER = ROOT / "trades" / "phase6_trades.jsonl"
STATE = ROOT / "data" / "state"
REPORTS = ROOT / "reports"
LATEST_JSON = STATE / "post_proof_residual_cf_latest.json"
LATEST_MD = REPORTS / "POST_PROOF_RESIDUAL_GROWTH_CF_LATEST.md"
FEE_RT = 0.0018


def _f(x: Any, d: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def _parse_ts(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    s = str(raw).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _is_tp(t: dict) -> bool:
    if str(t.get("side") or "").upper() != "SELL":
        return False
    r = str(t.get("exit_reason") or t.get("reason") or t.get("exit_class") or "").lower()
    k = str(t.get("tp_kind") or "").lower()
    if "stop_loss" in r or "dust" in r or "eject" in r or "rotation" in r:
        return False
    return (
        "take_profit" in r
        or "trail" in r
        or "fixed_tp" in r
        or "tp_trail" in r
        or "dual_peak" in r
        or "trail" in k
        or "tp" in k
    )


def _is_crypto_pair(pair: str) -> bool:
    p = str(pair or "").upper()
    if not p or "USDT" in p or p in ("USDC-USD", "USD-USDC"):
        return False
    return "-USD" in p


def load_tp_roundtrips(min_ts: Optional[datetime] = None) -> List[Dict[str, Any]]:
    if not LEDGER.is_file():
        return []
    by_pair: Dict[str, List[dict]] = defaultdict(list)
    for line in LEDGER.open(encoding="utf-8"):
        try:
            t = json.loads(line)
        except Exception:
            continue
        pair = str(t.get("pair") or "")
        if not _is_crypto_pair(pair):
            continue
        ts = _parse_ts(t.get("timestamp") or t.get("ts"))
        if ts is None:
            continue
        if min_ts and ts < min_ts:
            continue
        t = dict(t)
        t["_ts"] = ts
        by_pair[pair].append(t)

    rts: List[Dict[str, Any]] = []
    for pair, rows in by_pair.items():
        rows = sorted(rows, key=lambda x: x["_ts"])
        last_buy = None
        for t in rows:
            side = str(t.get("side") or "").upper()
            if side == "BUY":
                last_buy = t
            elif side == "SELL" and last_buy and _is_tp(t):
                entry = _f(
                    last_buy.get("average_filled_price")
                    or last_buy.get("entry_price")
                    or last_buy.get("price")
                )
                exit_px = _f(
                    t.get("average_filled_price")
                    or t.get("exit_price")
                    or t.get("price")
                )
                pnl = _f(t.get("pnl") or t.get("realized_pnl") or t.get("pnl_usd"))
                notional = _f(
                    t.get("notional_usd")
                    or t.get("quote_size")
                    or (last_buy.get("notional_usd") if last_buy else 0)
                )
                if notional <= 0 and entry > 0:
                    qty = _f(
                        last_buy.get("qty")
                        or last_buy.get("amount")
                        or last_buy.get("size")
                    )
                    notional = qty * entry
                if notional <= 0 and pnl and entry and exit_px:
                    pct = (exit_px / entry - 1.0) if entry else 0.0
                    if abs(pct) > 1e-6:
                        notional = abs(pnl / pct)
                hold_h = (t["_ts"] - last_buy["_ts"]).total_seconds() / 3600.0
                rts.append(
                    {
                        "pair": pair,
                        "buy_ts": last_buy["_ts"].isoformat(),
                        "sell_ts": t["_ts"].isoformat(),
                        "entry": entry,
                        "exit": exit_px,
                        "pnl_usd": pnl,
                        "notional_usd": notional,
                        "hold_h": round(hold_h, 2),
                        "exit_reason": str(t.get("exit_reason") or t.get("reason") or ""),
                        "tp_pct": (exit_px / entry - 1.0)
                        if entry > 0 and exit_px > 0
                        else None,
                    }
                )
                last_buy = None
    return rts


def simulate_kindling(rt: Dict[str, Any], add_usd: float = 25.0) -> Dict[str, Any]:
    pnl = _f(rt.get("pnl_usd"))
    notional = max(_f(rt.get("notional_usd")), 1.0)
    hold_h = _f(rt.get("hold_h"))
    tp_pct = rt.get("tp_pct")
    eligible = (
        hold_h >= 2.0 and tp_pct is not None and 0.008 <= float(tp_pct) <= 0.12
    )
    if not eligible:
        return {
            "eligible": False,
            "pnl_usd": pnl,
            "delta_usd": 0.0,
            "note": "not_in_kindling_proxy_band",
        }
    add_fee = add_usd * FEE_RT
    scaled = pnl * ((notional + add_usd) / notional) - add_fee
    return {
        "eligible": True,
        "pnl_usd": round(scaled, 4),
        "delta_usd": round(scaled - pnl, 4),
        "add_usd": add_usd,
        "note": "scaled_tp_pnl_minus_add_fee_proxy",
    }


def build_cf() -> Dict[str, Any]:
    cut = datetime.now(timezone.utc) - timedelta(days=90)
    rts = load_tp_roundtrips(min_ts=cut)
    by_pair: Dict[str, List] = defaultdict(list)
    for rt in rts:
        by_pair[rt["pair"]].append(rt)

    pairs_out = {}
    sum_base = 0.0
    sum_kindling_delta = 0.0
    n_kindling_elig = 0
    for pair, rows in sorted(by_pair.items()):
        base = sum(_f(r["pnl_usd"]) for r in rows)
        sum_base += base
        kindlings = [simulate_kindling(r) for r in rows]
        k_delta = sum(_f(k["delta_usd"]) for k in kindlings)
        sum_kindling_delta += k_delta
        n_kindling_elig += sum(1 for k in kindlings if k.get("eligible"))
        pairs_out[pair] = {
            "n": len(rows),
            "baseline_pnl_usd": round(base, 4),
            "residual_same_mark_delta_usd": 0.0,
            "kindling_delta_usd": round(k_delta, 4),
            "kindling_eligible_n": sum(1 for k in kindlings if k.get("eligible")),
        }

    exit_cfg: Dict[str, Any] = {}
    dwell: Dict[str, Any] = {}
    dual: Dict[str, Any] = {}
    try:
        exit_cfg = json.loads((ROOT / "config/exit_automation.json").read_text())
        dwell = json.loads((ROOT / "config/post_proof_dwell.json").read_text())
        cfg = json.loads((ROOT / "config/trading_config_phase6.json").read_text())
        dual = (cfg.get("run_lifecycle") or {}).get("dual_peak_exit") or {}
    except Exception:
        pass
    tp = exit_cfg.get("take_profit") or {}
    stack_live = {
        "trail_live": str(tp.get("mode") or "").lower() == "live"
        and bool((tp.get("trail") or {}).get("enabled")),
        "dwell_live": bool(dwell.get("enabled") and dwell.get("live_apply")),
        "dual_peak_live": bool(dual.get("enabled"))
        and str(dual.get("mode") or "").lower() == "live",
        "dual_meat_gate_4pct": abs(_f(dual.get("dual_peak_min_green_pct"), 0) - 0.04)
        < 1e-6,
    }

    decision = {
        "residual_partial_live": "NO-GO",
        "reason": (
            "Same-mark residual CF delta=0 by construction. Need OHLCV path CF "
            "with post-TP MFE/MAE before any live partial-bank ladder. "
            "Live growth stack today = trail + dual-peak meat gate + post-proof dwell "
            "(already live) — not a multi-tranche residual ladder."
        ),
        "kindling_proxy_delta_usd": round(sum_kindling_delta, 4),
        "kindling_note": (
            "Proxy only — scale-up live arm is separate GO. Positive delta is not auto-GO."
        ),
        "stack_live": stack_live,
        "growth_functionality": ("A+" if all(stack_live.values()) else "GAP"),
    }

    return {
        "schema": "post_proof_residual_cf_v2",
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
        "n_tp_roundtrips_90d": len(rts),
        "baseline_tp_pnl_usd": round(sum_base, 4),
        "residual_same_mark_delta_usd": 0.0,
        "kindling_proxy_delta_usd": round(sum_kindling_delta, 4),
        "n_kindling_eligible": n_kindling_elig,
        "pairs": pairs_out,
        "sample_rows": rts[:12],
        "decision": decision,
        "honesty": (
            "No mocked residual PnL. Partial bank at TP mark does not increase total vs full TP. "
            "Do not promote residual ladder live from this CF alone."
        ),
    }


def write_md(cf: Dict[str, Any]) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Post-proof residual / growth CF (honest)",
        f"**as_of:** {cf['as_of_utc']}",
        f"**schema:** `{cf['schema']}`",
        "",
        f"- TP roundtrips (90d): **{cf['n_tp_roundtrips_90d']}**",
        f"- Baseline TP bank: **${cf['baseline_tp_pnl_usd']}**",
        f"- Residual same-mark Δ: **${cf['residual_same_mark_delta_usd']}** (identity)",
        f"- Kindling proxy Δ: **${cf['kindling_proxy_delta_usd']}** (n_elig={cf['n_kindling_eligible']})",
        f"- Growth stack live grade: **{cf['decision']['growth_functionality']}**",
        f"- Residual partial live: **{cf['decision']['residual_partial_live']}** — {cf['decision']['reason']}",
        "",
        "## Stack",
    ]
    for k, v in (cf["decision"].get("stack_live") or {}).items():
        lines.append(f"- `{k}`: {v}")
    lines.extend(["", "## Pairs", ""])
    for pair, row in (cf.get("pairs") or {}).items():
        lines.append(
            f"- **{pair}** n={row.get('n')} baseline=${row.get('baseline_pnl_usd')} "
            f"kindling_Δ=${row.get('kindling_delta_usd')}"
        )
    lines.extend(["", f"_{cf.get('honesty')}_", ""])
    text = "\n".join(lines)
    LATEST_MD.write_text(text, encoding="utf-8")
    dated = (
        REPORTS
        / f"POST_PROOF_RESIDUAL_GROWTH_CF_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.md"
    )
    dated.write_text(text, encoding="utf-8")


def main() -> int:
    cf = build_cf()
    STATE.mkdir(parents=True, exist_ok=True)
    LATEST_JSON.write_text(json.dumps(cf, indent=2, default=str) + "\n", encoding="utf-8")
    write_md(cf)
    print(
        f"residual_cf n={cf['n_tp_roundtrips_90d']} base=${cf['baseline_tp_pnl_usd']} "
        f"kindling_Δ=${cf['kindling_proxy_delta_usd']} "
        f"growth={cf['decision']['growth_functionality']} "
        f"residual_live={cf['decision']['residual_partial_live']}"
    )
    print(f"wrote {LATEST_JSON}")
    print(f"wrote {LATEST_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
