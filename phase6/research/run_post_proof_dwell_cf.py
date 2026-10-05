#!/usr/bin/env python3
"""Post-proof dwell counterfactual pack (Tier A + B). Paper only — no orders.

Tier A: block tryout re-seat N hours after TP → avoided eject tax vs missed shell.
Tier B: hold-after-TP mark @7d with fee drag + simple SL path (context only).

Edge class forced: ATTENTION_ONLY_less_loss_path (never HIT_10 from this pack alone).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.post_proof_dwell import (  # noqa: E402
    SCHEMA,
    fee_aware_net_pnl,
    load_config,
    proof_from_sell,
    rebuild_state_from_ledger,
    snapshot,
)
from phase6.research.trade_comparison_standard import (  # noqa: E402
    buy_event,
    exit_class,
    is_clean_buy,
    load_ledger_rows,
    sell_event,
)

STATE = ROOT / "data" / "state"
REPORTS = ROOT / "reports"
OUT_JSON = STATE / "post_proof_dwell_cf_latest.json"
OUT_MD = REPORTS / "POST_PROOF_DWELL_CF_LATEST.md"

FOCUS = [
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "LINK-USD",
    "ZEC-USD",
    "HYPE-USD",
    "TIA-USD",
    "XRP-USD",
    "AVAX-USD",
    "DOGE-USD",
    "UNI-USD",
    "ADA-USD",
]

FEE_RT_FRAC = 0.018  # 0.9% * 2 sides default intro rate
SL_PATH_FRAC = 0.03  # ~3% adverse for Tier B stress


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, (int, float)):
        # Coinbase-style unix seconds (or ms)
        v = float(raw)
        if v > 1e12:
            v = v / 1000.0
        try:
            return datetime.fromtimestamp(v, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    s = str(raw).strip()
    if not s:
        return None
    # bare int string
    try:
        if s.isdigit() or (s.replace(".", "", 1).isdigit() and s.count(".") <= 1):
            return _parse_ts(float(s))
    except ValueError:
        pass
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _f(v: Any, d: float = 0.0) -> float:
    try:
        return float(v) if v is not None else d
    except (TypeError, ValueError):
        return d


def _load_close_series(pair: str) -> List[Tuple[datetime, float]]:
    """Best-effort 1h OHLCV closes."""
    base = pair.replace("-USD", "").replace("-", "_")
    # files look like LINK_USD_1h.json
    candidates = [
        ROOT / "data" / "ohlcv" / "1h" / f"{pair.replace('-', '_')}_1h.json",
        ROOT / "data" / "ohlcv" / "1h" / f"{base}_USD_1h.json",
        ROOT / "data" / "ohlcv" / "1h" / f"{base}_1h.json",
    ]
    for p in candidates:
        if not p.exists():
            continue
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows = raw if isinstance(raw, list) else (
            raw.get("candles") or raw.get("data") or raw.get("ohlcv") or []
        )
        out: List[Tuple[datetime, float]] = []
        for c in rows:
            if isinstance(c, dict):
                ts = _parse_ts(
                    c.get("timestamp") or c.get("t") or c.get("time") or c.get("ts")
                )
                cl = c.get("close") if c.get("close") is not None else c.get("c")
            elif isinstance(c, (list, tuple)) and len(c) >= 5:
                ts = _parse_ts(c[0])
                cl = c[4]
            else:
                continue
            if ts is None or cl is None:
                continue
            try:
                out.append((ts, float(cl)))
            except (TypeError, ValueError):
                continue
        if out:
            out.sort(key=lambda x: x[0])
            return out
    return []


def _px_at(series: List[Tuple[datetime, float]], ts: datetime) -> Optional[float]:
    if not series:
        return None
    # last close at or before ts
    best = None
    for t, px in series:
        if t <= ts:
            best = px
        else:
            break
    return best


def _px_after(
    series: List[Tuple[datetime, float]], ts: datetime, hours: float
) -> Optional[float]:
    target = ts + timedelta(hours=hours)
    return _px_at(series, target)


def run_cf(
    *,
    pairs: Optional[Sequence[str]] = None,
    ban_hours: Sequence[float] = (24.0, 48.0, 168.0),
    hold_hours: float = 168.0,
) -> Dict[str, Any]:
    rows = load_ledger_rows()
    focus = list(pairs) if pairs else FOCUS
    # include any pair that had TP in ledger
    all_pairs = sorted({str(r.get("pair") or "") for r in rows if r.get("pair")})
    for p in all_pairs:
        if p not in focus and any(
            exit_class(str(x.get("reason") or "")) == "take_profit"
            for x in rows
            if x.get("pair") == p and str(x.get("side") or "").upper() == "SELL"
        ):
            focus.append(p)

    cfg = load_config()
    rebuilt = rebuild_state_from_ledger(rows, cfg=cfg)
    snap = snapshot(cfg=cfg, state=rebuilt)

    # --- Tier A: post-TP tryout ban arms ---
    arms: Dict[str, Any] = {}
    per_pair_tax: Dict[str, Dict[str, Any]] = {}

    for ban_h in ban_hours:
        blocked_buys = 0
        blocked_usd = 0.0
        avoided_eject_pnl = 0.0  # sum of subsequent eject pnl (usually neg) avoided
        avoided_eject_fees = 0.0
        n_eject_after_blocked = 0
        missed_tp_after = 0.0
        n_missed_tp = 0
        false_block_green_shell = 0
        examples: List[Dict[str, Any]] = []

        for pair in focus:
            pr = [r for r in rows if r.get("pair") == pair]
            buys = [buy_event(r) for r in pr if is_clean_buy(r)]
            sells = [sell_event(r) for r in pr if r.get("side") == "SELL"]
            tps = [
                s
                for s in sells
                if exit_class(str(s.get("reason") or "")) == "take_profit" and s.get("ts")
            ]
            ejects = [
                s
                for s in sells
                if (
                    "scale_window" in str(s.get("reason") or "").lower()
                    or "eject" in str(s.get("reason") or "").lower()
                )
                and s.get("ts")
            ]
            # pair tax board
            if pair not in per_pair_tax:
                tp_meat = sum(_f(s.get("pnl")) for s in tps)
                ej_pnl = sum(_f(s.get("pnl")) for s in ejects)
                per_pair_tax[pair] = {
                    "n_tp": len(tps),
                    "tp_pnl_sum": round(tp_meat, 4),
                    "n_eject": len(ejects),
                    "eject_pnl_sum": round(ej_pnl, 4),
                    "n_post_tp_tryout_48h": 0,
                }

            for b in buys:
                if not b.get("ts"):
                    continue
                usd = _f(b.get("usd"), 25.0)
                # tryout-ish: small shell
                is_tryoutish = usd <= 80.0
                if not is_tryoutish:
                    continue
                # hours since last TP before this buy
                hrs_tp = None
                last_tp = None
                for s in reversed(tps):
                    if s["ts"] < b["ts"]:
                        hrs_tp = (b["ts"] - s["ts"]).total_seconds() / 3600.0
                        last_tp = s
                        break
                if hrs_tp is None or not (0 < hrs_tp <= float(ban_h)):
                    continue
                if ban_h == 48.0:
                    per_pair_tax[pair]["n_post_tp_tryout_48h"] += 1

                blocked_buys += 1
                blocked_usd += usd
                # next eject within ban window after buy (or 7d)
                win_end = b["ts"] + timedelta(hours=max(float(ban_h), 168.0))
                ej_hit = [
                    e
                    for e in ejects
                    if e["ts"] > b["ts"] and e["ts"] <= win_end
                ]
                if ej_hit:
                    e0 = ej_hit[0]
                    pnl_e = _f(e0.get("pnl"))
                    # fee estimate if not stamped
                    fees = abs(_f(e0.get("total_fees")))
                    if fees <= 0:
                        fees = usd * FEE_RT_FRAC
                    avoided_eject_pnl += pnl_e  # often small pos gross
                    avoided_eject_fees += fees
                    n_eject_after_blocked += 1
                # TP after blocked buy?
                tp_hit = [
                    t
                    for t in tps
                    if t["ts"] > b["ts"] and t["ts"] <= b["ts"] + timedelta(days=10)
                ]
                if tp_hit:
                    missed_tp_after += _f(tp_hit[0].get("pnl"))
                    n_missed_tp += 1
                    false_block_green_shell += 1
                if len(examples) < 12:
                    examples.append(
                        {
                            "pair": pair,
                            "buy_ts": b["ts"].isoformat(),
                            "hrs_since_tp": round(hrs_tp, 2),
                            "usd": usd,
                            "had_eject_after": bool(ej_hit),
                            "had_tp_after": bool(tp_hit),
                            "last_tp_pnl": _f((last_tp or {}).get("pnl")),
                        }
                    )

        # net process benefit sketch: fees avoided on eject path - missed TP
        # Prefer fee-aware: ejects that looked green gross often net red
        net_tax_avoided_est = avoided_eject_fees - max(0.0, missed_tp_after)
        arms[f"ban_{int(ban_h)}h"] = {
            "ban_hours": ban_h,
            "n_blocked_tryout_buys": blocked_buys,
            "blocked_usd": round(blocked_usd, 2),
            "n_with_eject_after": n_eject_after_blocked,
            "sum_eject_gross_pnl_on_those": round(avoided_eject_pnl, 4),
            "est_eject_fees_avoided": round(avoided_eject_fees, 4),
            "n_with_tp_after_blocked": n_missed_tp,
            "sum_tp_pnl_after_blocked": round(missed_tp_after, 4),
            "false_block_green_shell": false_block_green_shell,
            "net_process_benefit_sketch": round(net_tax_avoided_est, 4),
            "note": (
                "Benefit sketch = est eject RT fees avoided − TP pnl after blocked buy. "
                "Not lot-matched alpha. ATTENTION_ONLY."
            ),
            "examples": examples,
        }

    # --- Tier B: hold after TP mark @ hold_hours ---
    tier_b: List[Dict[str, Any]] = []
    for pair in focus:
        series = _load_close_series(pair)
        pr = [r for r in rows if r.get("pair") == pair]
        sells = [sell_event(r) for r in pr if r.get("side") == "SELL"]
        tps = [
            s
            for s in sells
            if exit_class(str(s.get("reason") or "")) == "take_profit" and s.get("ts")
        ]
        for s in tps:
            # sell_event uses keys exit/entry (not exit_price)
            px0 = _f(
                s.get("exit")
                or s.get("exit_price")
                or s.get("price")
                or s.get("average_filled_price")
            )
            if px0 <= 0 and series:
                px0 = _f(_px_at(series, s["ts"]))
            # Still record the TP event even without a mark path (honesty: thin mark N)
            mark_ret = None
            path_min_ret = None
            sl_hit = False
            if px0 > 0 and series:
                px7 = _px_after(series, s["ts"], hold_hours)
                mark_ret = None if px7 is None else (px7 / px0 - 1.0)
                end = s["ts"] + timedelta(hours=hold_hours)
                window = [px for t, px in series if s["ts"] < t <= end]
                if window:
                    path_min_ret = min(window) / px0 - 1.0
                sl_hit = path_min_ret is not None and path_min_ret <= -SL_PATH_FRAC
            fee_drag = FEE_RT_FRAC
            mark_after_fee = None if mark_ret is None else mark_ret - fee_drag
            tier_b.append(
                {
                    "pair": pair,
                    "tp_ts": s["ts"].isoformat(),
                    "tp_pnl": _f(s.get("pnl")),
                    "exit_px": px0 if px0 > 0 else None,
                    "mark_ret_7d": None if mark_ret is None else round(mark_ret, 4),
                    "mark_ret_7d_after_rt_fee": (
                        None if mark_after_fee is None else round(mark_after_fee, 4)
                    ),
                    "path_min_ret": None if path_min_ret is None else round(path_min_ret, 4),
                    "sl_path_hit_3pct": sl_hit,
                    "ohlcv": bool(series),
                }
            )

    n_b = len(tier_b)
    n_green_mark = sum(
        1 for x in tier_b if x.get("mark_ret_7d_after_rt_fee") is not None and x["mark_ret_7d_after_rt_fee"] > 0
    )
    n_sl_path = sum(1 for x in tier_b if x.get("sl_path_hit_3pct"))
    n_with_px = sum(1 for x in tier_b if x.get("mark_ret_7d") is not None)

    # proof rebuild summary
    proof_sells = []
    for r in rows:
        if str(r.get("side") or "").upper() != "SELL":
            continue
        pr = proof_from_sell(r, cfg=cfg)
        if pr.get("is_proof"):
            proof_sells.append(
                {
                    "pair": r.get("pair"),
                    "ts": r.get("timestamp"),
                    "reason": r.get("reason") or r.get("exit_reason"),
                    "net": pr.get("net"),
                }
            )

    payload = {
        "schema": "post_proof_dwell_cf_v1",
        "as_of": _utc_now().isoformat().replace("+00:00", "Z"),
        "edge_class": "ATTENTION_ONLY_less_loss_path",
        "policy_schema": SCHEMA,
        "live_apply": False,
        "tier_a_tryout_ban_arms": arms,
        "tier_b_hold_after_tp": {
            "hold_hours": hold_hours,
            "n_tp_events": n_b,
            "n_with_ohlcv_mark": n_with_px,
            "n_mark_green_after_rt_fee": n_green_mark,
            "n_sl_path_3pct": n_sl_path,
            "frac_mark_green": round(n_green_mark / n_with_px, 3) if n_with_px else None,
            "frac_sl_path": round(n_sl_path / n_with_px, 3) if n_with_px else None,
            "rows": tier_b,
            "note": (
                "Mark CF is path context only — not lot PnL, not proof of buy/hold alpha. "
                "Green run-up + red end = trap; always report both mark and path min."
            ),
        },
        "per_pair_tax": per_pair_tax,
        "rebuild_snapshot": {
            "n_graduated_active": snap.get("n_graduated_active"),
            "active_pairs": snap.get("active_pairs"),
            "n_proof_sells_hist": len(proof_sells),
            "proof_sells": proof_sells[-20:],
        },
        "honesty": {
            "edge_class": "ATTENTION_ONLY_less_loss_path",
            "not_hit_10": True,
            "cannot_prove": [
                "long-term higher returns",
                "buy/hold beats TP banking on every path",
                "fee-blind MTM as profit",
            ],
            "can_support": [
                "less tryout reincarnation after TP",
                "lower eject fee thrash on proven names",
                "multipair process-tax reduction",
            ],
        },
        "plain_english": (
            "Post-proof dwell CF: blocking tryout re-seats after TP would have stopped "
            f"several same-name shells (see ban arms). Hold-after-TP 7d marks are context only "
            f"({n_green_mark}/{n_with_px or 0} green after RT fee estimate). "
            "Edge stays ATTENTION_ONLY_less_loss_path until live shadow cycles clear."
        ),
    }
    return payload


def render_md(payload: Dict[str, Any]) -> str:
    lines = [
        "# Post-Proof Dwell CF (Tier A + B)",
        "",
        f"**As of:** {payload.get('as_of')}",
        f"**Edge class:** `{payload.get('edge_class')}` (forced — not HIT_10)",
        f"**live_apply:** false (CF pack never arms money)",
        "",
        "## Plain English",
        "",
        str(payload.get("plain_english") or ""),
        "",
        "## Tier A — block tryout re-seat after TP",
        "",
        "| Arm | Blocked buys | USD blocked | Eject-after | Est fees avoided | TP-after (miss) | Net sketch |",
        "|-----|-------------:|------------:|------------:|-----------------:|----------------:|-----------:|",
    ]
    arms = payload.get("tier_a_tryout_ban_arms") or {}
    for k in sorted(arms.keys()):
        a = arms[k]
        lines.append(
            f"| {k} | {a.get('n_blocked_tryout_buys')} | {a.get('blocked_usd')} | "
            f"{a.get('n_with_eject_after')} | {a.get('est_eject_fees_avoided')} | "
            f"{a.get('n_with_tp_after_blocked')} ({a.get('sum_tp_pnl_after_blocked')}) | "
            f"{a.get('net_process_benefit_sketch')} |"
        )
    lines.extend(
        [
            "",
            "_Net sketch = est eject RT fees avoided − TP pnl on shells after a blocked buy. Not alpha._",
            "",
            "## Tier B — hold-after-TP mark @7d",
            "",
        ]
    )
    tb = payload.get("tier_b_hold_after_tp") or {}
    lines.append(
        f"- TP events: **{tb.get('n_tp_events')}** · with OHLCV mark: **{tb.get('n_with_ohlcv_mark')}**"
    )
    lines.append(
        f"- Mark green after RT fee est: **{tb.get('n_mark_green_after_rt_fee')}** "
        f"({tb.get('frac_mark_green')})"
    )
    lines.append(
        f"- Path hit ~−3% SL band: **{tb.get('n_sl_path_3pct')}** ({tb.get('frac_sl_path')})"
    )
    lines.append("")
    lines.append(str(tb.get("note") or ""))
    lines.extend(["", "### Tier B rows", "", "| Pair | TP ts | TP pnl | Mark 7d | Mark−fee | Path min | SL path |", "|------|-------|-------:|--------:|---------:|---------:|:-------:|"])
    for r in (tb.get("rows") or [])[:40]:
        lines.append(
            f"| {r.get('pair')} | {str(r.get('tp_ts') or '')[:19]} | {r.get('tp_pnl')} | "
            f"{r.get('mark_ret_7d')} | {r.get('mark_ret_7d_after_rt_fee')} | "
            f"{r.get('path_min_ret')} | {r.get('sl_path_hit_3pct')} |"
        )
    lines.extend(["", "## Per-pair tax sketch", ""])
    lines.append("| Pair | n TP | TP $ | n eject | eject $ | post-TP tryout≤48h |")
    lines.append("|------|-----:|-----:|--------:|--------:|-------------------:|")
    for p, v in sorted((payload.get("per_pair_tax") or {}).items()):
        lines.append(
            f"| {p} | {v.get('n_tp')} | {v.get('tp_pnl_sum')} | {v.get('n_eject')} | "
            f"{v.get('eject_pnl_sum')} | {v.get('n_post_tp_tryout_48h')} |"
        )
    rb = payload.get("rebuild_snapshot") or {}
    lines.extend(
        [
            "",
            "## Ledger rebuild → would-be graduated (as-of now)",
            "",
            f"- Proof sells hist: **{rb.get('n_proof_sells_hist')}**",
            f"- Active graduated (if stamped continuously): **{rb.get('n_graduated_active')}** → {rb.get('active_pairs')}",
            "",
            "## Honesty bars",
            "",
        ]
    )
    h = payload.get("honesty") or {}
    lines.append("**Can support:** " + ", ".join(h.get("can_support") or []))
    lines.append("")
    lines.append("**Cannot prove:** " + ", ".join(h.get("cannot_prove") or []))
    lines.extend(
        [
            "",
            "## Next",
            "",
            "1. Shadow crumbs accumulate on composer + scale-window (`live_apply=false`).",
            "2. Re-run this CF weekly; promote only after multipair less-tax holds.",
            "3. Brad GO required for `config/post_proof_dwell.json` → `live_apply: true`.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="Write JSON + MD outputs")
    args = ap.parse_args()
    payload = run_cf()
    md = render_md(payload)
    print(payload.get("plain_english"))
    print("---")
    print(md[:2500])
    if args.write:
        STATE.mkdir(parents=True, exist_ok=True)
        REPORTS.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
        OUT_MD.write_text(md, encoding="utf-8")
        print(f"wrote {OUT_JSON}")
        print(f"wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
