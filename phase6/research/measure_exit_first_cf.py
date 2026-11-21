#!/usr/bin/env python3
"""Alt C — Exit-first redesign measure CF (no live knobs).

On real closed legs (ledger SELL with PnL + matched BUY), replay 1h OHLCV and compare:
  - actual exit PnL
  - fixed_tp_6 (first touch +6%, else actual)
  - trail_after_arm (arm +4% MFE, trail 2% off peak; else actual)
  - time_stop_5d (close at bar close after 5d if still open)
  - exit_first_gate: skip entry (PnL=0) if MAE hits -3% before MFE +4%
  - bank_trail_C reuse note when available

Honesty:
  - Winsorize Δ$ ±$50/leg for headline sums
  - Medians primary; one-leg owners called out
  - Not a live TP/trail GO
  - edge_class less-loss / attention only until multipair WF

Artifacts:
  data/state/measure_exit_first_cf_latest.json
  reports/MEASURE_EXIT_FIRST_CF_LATEST.md
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STATE = ROOT / "data" / "state"
REPORTS = ROOT / "reports"
TRADES = ROOT / "trades" / "phase6_trades.jsonl"
OUT_JSON = STATE / "measure_exit_first_cf_latest.json"
OUT_MD = REPORTS / "MEASURE_EXIT_FIRST_CF_LATEST.md"
SCHEMA = "measure_exit_first_cf_v1"
LIVE_APPLY = False

STABLE = {"USDT-USD", "USDC-USD", "USD-USD", "DAI-USD"}
WINSOR = 50.0
FEE_RT = 0.016  # ~0.8%*2 taker default haircut when simulating synthetic exit notional


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(raw: Any) -> Optional[datetime]:
    if not raw:
        return None
    try:
        t = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t.astimezone(timezone.utc)
    except Exception:
        return None


def _f(x: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def _winsor(x: float, lim: float = WINSOR) -> float:
    return max(-lim, min(lim, x))


def load_rows() -> List[Dict[str, Any]]:
    if not TRADES.exists():
        return []
    out = []
    seen = set()
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
            r.get("pnl"),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _side(r: Dict[str, Any]) -> str:
    return str(r.get("side") or "").upper()


def _pair(r: Dict[str, Any]) -> str:
    return str(r.get("pair") or r.get("product_id") or "").upper()


def _pnl(r: Dict[str, Any]) -> Optional[float]:
    return _f(r.get("pnl") if r.get("pnl") is not None else r.get("pnl_usd"))


def _reason(r: Dict[str, Any]) -> str:
    return str(r.get("reason") or r.get("exit_reason") or "").lower()


def _qty(r: Dict[str, Any]) -> Optional[float]:
    return _f(r.get("qty") or r.get("size") or r.get("filled_size"))


def _px(r: Dict[str, Any], *keys: str) -> Optional[float]:
    for k in keys:
        v = _f(r.get(k))
        if v is not None and v > 0:
            return v
    return None


def match_legs(
    rows: List[Dict[str, Any]],
    *,
    since: datetime,
    until: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Match SELL with prior BUY on same pair (FIFO clean-ish)."""
    buys_by: Dict[str, List[Dict[str, Any]]] = {}
    legs: List[Dict[str, Any]] = []
    until = until or _now()

    dated: List[Tuple[datetime, Dict[str, Any]]] = []
    for r in rows:
        ts = _parse_ts(r.get("ts") or r.get("timestamp") or r.get("filled_at"))
        if not ts:
            continue
        dated.append((ts, r))
    dated.sort(key=lambda x: x[0])

    for ts, r in dated:
        p = _pair(r)
        if not p or p in STABLE or p.startswith("TEST"):
            continue
        if _side(r) == "BUY":
            if "fresh_start" in _reason(r) and not _f(r.get("price") or r.get("entry_price")):
                continue
            buys_by.setdefault(p, []).append({"ts": ts, "row": r})
            continue
        if _side(r) != "SELL":
            continue
        if ts < since or ts > until:
            continue
        pnl = _pnl(r)
        if pnl is None:
            continue
        # skip pure dust pennies without path value unless SL/TP
        reason = _reason(r)
        if "dust" in reason and abs(pnl) < 0.5:
            continue

        entry = None
        pool = buys_by.get(p) or []
        # take last buy before sell
        while pool and pool[-1]["ts"] > ts:
            pool.pop()
        if pool:
            entry = pool.pop()
            buys_by[p] = pool

        entry_px = None
        qty = _qty(r)
        exit_px = _px(r, "exit_price", "price", "fill_price")
        if entry:
            er = entry["row"]
            entry_px = _px(er, "price", "entry_price", "fill_price", "avg_price")
            if qty is None:
                qty = _qty(er)
            if entry_px is None and qty and exit_px is not None and pnl is not None:
                # entry_n = qty*exit - pnl → entry_px
                try:
                    entry_n = float(qty) * float(exit_px) - float(pnl)
                    if qty:
                        entry_px = entry_n / float(qty)
                except Exception:
                    pass
        if entry_px is None and qty and exit_px is not None and pnl is not None:
            try:
                entry_n = float(qty) * float(exit_px) - float(pnl)
                if qty:
                    entry_px = entry_n / float(qty)
            except Exception:
                pass

        if not entry_px or not qty or not exit_px or entry_px <= 0:
            continue

        legs.append(
            {
                "pair": p,
                "entry_ts": entry["ts"] if entry else ts - timedelta(days=1),
                "exit_ts": ts,
                "entry_px": float(entry_px),
                "exit_px": float(exit_px),
                "qty": float(qty),
                "actual_pnl_usd": float(pnl),
                "reason": reason[:60],
                "notional_entry": float(qty) * float(entry_px),
            }
        )
    return legs


def _window(candles: List[List[float]], entry_ts: float, exit_ts: float) -> List[List[float]]:
    out = []
    for c in candles:
        t = c[0]
        if t + 3600 < entry_ts:
            continue
        if t > exit_ts + 3600:
            break
        out.append(c)
    return out


def path_mfe_mae(window: List[List[float]], entry_px: float) -> Tuple[float, float]:
    mfe = 0.0
    mae = 0.0
    if entry_px <= 0:
        return 0.0, 0.0
    for c in window:
        lo, hi = c[1], c[2]
        mfe = max(mfe, hi / entry_px - 1.0)
        mae = min(mae, lo / entry_px - 1.0)
    return mfe, mae


def sim_fixed_tp(
    window: List[List[float]],
    *,
    entry_px: float,
    qty: float,
    tp_pct: float,
    actual_pnl: float,
    exit_px: float,
    fee_frac: float = FEE_RT / 2,
) -> Dict[str, Any]:
    target = entry_px * (1.0 + tp_pct)
    for c in window:
        if c[2] >= target:
            fill = target
            gross = (fill - entry_px) * qty
            fee = abs(fill * qty) * fee_frac + abs(entry_px * qty) * fee_frac
            pnl = gross - fee
            return {
                "fired": True,
                "pnl_usd": pnl,
                "delta_vs_actual": pnl - actual_pnl,
                "fill_px": fill,
            }
    # never touched — actual
    return {
        "fired": False,
        "pnl_usd": actual_pnl,
        "delta_vs_actual": 0.0,
        "fill_px": exit_px,
    }


def sim_trail(
    window: List[List[float]],
    *,
    entry_px: float,
    qty: float,
    arm_mfe: float = 0.04,
    trail_pct: float = 0.02,
    actual_pnl: float = 0.0,
    exit_px: float = 0.0,
    fee_frac: float = FEE_RT / 2,
) -> Dict[str, Any]:
    if entry_px <= 0 or not window:
        return {"fired": False, "pnl_usd": actual_pnl, "delta_vs_actual": 0.0}
    arm_px = entry_px * (1.0 + arm_mfe)
    armed = False
    peak = entry_px
    for c in window:
        lo, hi = c[1], c[2]
        if not armed:
            if hi >= arm_px:
                armed = True
                peak = max(peak, hi)
            continue
        peak = max(peak, hi)
        stop = peak * (1.0 - trail_pct)
        if lo <= stop:
            fill = min(stop, c[3] if len(c) > 3 else stop)  # open gap-ish
            if c[3] < stop:
                fill = float(c[3])
            else:
                fill = stop
            gross = (fill - entry_px) * qty
            fee = abs(fill * qty) * fee_frac + abs(entry_px * qty) * fee_frac
            pnl = gross - fee
            return {
                "fired": True,
                "pnl_usd": pnl,
                "delta_vs_actual": pnl - actual_pnl,
                "fill_px": fill,
                "peak_px": peak,
            }
    return {
        "fired": False,
        "pnl_usd": actual_pnl,
        "delta_vs_actual": 0.0,
        "fill_px": exit_px,
        "armed": armed,
    }


def sim_time_stop(
    window: List[List[float]],
    *,
    entry_ts: float,
    entry_px: float,
    qty: float,
    hours: float = 5 * 24,
    actual_pnl: float,
    exit_ts: float,
    fee_frac: float = FEE_RT / 2,
) -> Dict[str, Any]:
    deadline = entry_ts + hours * 3600
    if exit_ts <= deadline:
        return {"fired": False, "pnl_usd": actual_pnl, "delta_vs_actual": 0.0}
    for c in window:
        if c[0] + 3600 >= deadline:
            fill = float(c[4] if len(c) > 4 else c[3])
            gross = (fill - entry_px) * qty
            fee = abs(fill * qty) * fee_frac + abs(entry_px * qty) * fee_frac
            pnl = gross - fee
            return {
                "fired": True,
                "pnl_usd": pnl,
                "delta_vs_actual": pnl - actual_pnl,
                "fill_px": fill,
            }
    return {"fired": False, "pnl_usd": actual_pnl, "delta_vs_actual": 0.0}


def exit_first_gate(
    mfe: float,
    mae: float,
    *,
    arm_mfe: float = 0.04,
    kill_mae: float = -0.03,
) -> Dict[str, Any]:
    """Would exit-first doctrine skip this entry?

    Skip if path hits kill MAE before ever printing arm MFE.
    Approximation: if mae <= kill and mfe < arm → skip (bad geometry).
    If mfe >= arm → allow (had room for planned exit).
    """
    allow = mfe >= arm_mfe
    skip = (not allow) and (mae <= kill_mae)
    # also skip if never greened meaningfully and finished via deep loss path
    if mfe < 0.01 and mae <= kill_mae:
        skip = True
        allow = False
    return {
        "allow": allow and not skip,
        "skip": skip,
        "mfe": mfe,
        "mae": mae,
        "arm_mfe": arm_mfe,
        "kill_mae": kill_mae,
    }


def _agg(deltas: List[float], pnls: List[float], n_fire: int, n: int) -> Dict[str, Any]:
    if not deltas:
        return {
            "n": 0,
            "n_fired_or_skip": n_fire,
            "sum_delta": 0.0,
            "sum_delta_winsor": 0.0,
            "median_delta": None,
            "sum_pnl": 0.0,
        }
    w = [_winsor(x) for x in deltas]
    return {
        "n": n,
        "n_fired_or_skip": n_fire,
        "sum_delta": round(sum(deltas), 4),
        "sum_delta_winsor": round(sum(w), 4),
        "median_delta": round(statistics.median(deltas), 4),
        "sum_pnl": round(sum(pnls), 4),
        "mean_delta": round(sum(deltas) / len(deltas), 4),
    }


def run_cf(
    *,
    since: Optional[datetime] = None,
    days: int = 120,
    allow_network: bool = True,
    write: bool = True,
    max_legs: int = 80,
) -> Dict[str, Any]:
    since = since or (_now() - timedelta(days=days))
    rows = load_rows()
    legs = match_legs(rows, since=since)
    # prefer SL + TP + rotation with real size
    legs = [L for L in legs if L["notional_entry"] >= 20.0]
    legs = legs[-max_legs:]

    # candle helper
    from scripts.phase6 import run_sl_width_3v8_cf as slw  # type: ignore

    detailed: List[Dict[str, Any]] = []
    d_tp: List[float] = []
    d_tr: List[float] = []
    d_ts: List[float] = []
    d_ef: List[float] = []
    p_tp: List[float] = []
    p_tr: List[float] = []
    p_ts: List[float] = []
    p_ef: List[float] = []
    n_tp = n_tr = n_ts = n_skip = 0
    n_candle_fail = 0

    for L in legs:
        pair = L["pair"]
        entry_ts = L["entry_ts"].timestamp()
        exit_ts = L["exit_ts"].timestamp()
        try:
            if allow_network:
                candles = slw._ensure_candles(pair, L["entry_ts"] - timedelta(hours=6), L["exit_ts"] + timedelta(hours=6))
            else:
                candles = slw._load_candles(pair)
        except Exception:
            candles = []
        window = _window(candles, entry_ts, exit_ts) if candles else []
        if len(window) < 2:
            n_candle_fail += 1
            # still score exit-first gate as unknown; skip sims
            detailed.append({**{k: v for k, v in L.items() if k != "row"}, "status": "no_candles"})
            continue

        mfe, mae = path_mfe_mae(window, L["entry_px"])
        gate = exit_first_gate(mfe, mae)
        tp = sim_fixed_tp(
            window,
            entry_px=L["entry_px"],
            qty=L["qty"],
            tp_pct=0.06,
            actual_pnl=L["actual_pnl_usd"],
            exit_px=L["exit_px"],
        )
        tr = sim_trail(
            window,
            entry_px=L["entry_px"],
            qty=L["qty"],
            actual_pnl=L["actual_pnl_usd"],
            exit_px=L["exit_px"],
        )
        ts = sim_time_stop(
            window,
            entry_ts=entry_ts,
            entry_px=L["entry_px"],
            qty=L["qty"],
            actual_pnl=L["actual_pnl_usd"],
            exit_ts=exit_ts,
        )

        # exit-first: if skip, pnl=0 (never entered) vs actual
        if gate["skip"]:
            ef_pnl = 0.0
            ef_delta = 0.0 - L["actual_pnl_usd"]
            n_skip += 1
        else:
            # allowed: take better of trail or fixed tp if fired else actual
            cands = [L["actual_pnl_usd"]]
            if tp["fired"]:
                cands.append(tp["pnl_usd"])
            if tr["fired"]:
                cands.append(tr["pnl_usd"])
            ef_pnl = max(cands)
            ef_delta = ef_pnl - L["actual_pnl_usd"]

        if tp["fired"]:
            n_tp += 1
        if tr["fired"]:
            n_tr += 1
        if ts["fired"]:
            n_ts += 1

        d_tp.append(tp["delta_vs_actual"])
        d_tr.append(tr["delta_vs_actual"])
        d_ts.append(ts["delta_vs_actual"])
        d_ef.append(ef_delta)
        p_tp.append(tp["pnl_usd"])
        p_tr.append(tr["pnl_usd"])
        p_ts.append(ts["pnl_usd"])
        p_ef.append(ef_pnl)

        detailed.append(
            {
                "pair": pair,
                "entry_ts": L["entry_ts"].isoformat(),
                "exit_ts": L["exit_ts"].isoformat(),
                "reason": L["reason"],
                "actual_pnl_usd": round(L["actual_pnl_usd"], 4),
                "notional_entry": round(L["notional_entry"], 2),
                "mfe": round(mfe, 4),
                "mae": round(mae, 4),
                "exit_first_skip": gate["skip"],
                "tp6_delta": round(tp["delta_vs_actual"], 4),
                "trail_delta": round(tr["delta_vs_actual"], 4),
                "time5d_delta": round(ts["delta_vs_actual"], 4),
                "exit_first_delta": round(ef_delta, 4),
                "status": "ok",
            }
        )

    n_ok = sum(1 for d in detailed if d.get("status") == "ok")
    arms = {
        "fixed_tp_6": _agg(d_tp, p_tp, n_tp, n_ok),
        "trail_after_arm_4": _agg(d_tr, p_tr, n_tr, n_ok),
        "time_stop_5d": _agg(d_ts, p_ts, n_ts, n_ok),
        "exit_first_composite": _agg(d_ef, p_ef, n_skip, n_ok),
    }
    actual_sum = round(sum(L["actual_pnl_usd"] for L in legs if any(
        d.get("pair") == L["pair"] and d.get("status") == "ok" for d in detailed
    )), 4)
    # simpler actual sum on ok legs
    ok_pairs_ts = {(d["pair"], d["exit_ts"]) for d in detailed if d.get("status") == "ok"}
    actual_sum = 0.0
    for L in legs:
        key = (L["pair"], L["exit_ts"].isoformat())
        if key in ok_pairs_ts:
            actual_sum += L["actual_pnl_usd"]
    actual_sum = round(actual_sum, 4)

    # pick winner by winsorized sum delta
    winner = None
    best = None
    for name, a in arms.items():
        s = a.get("sum_delta_winsor")
        if s is None:
            continue
        if best is None or s > best:
            best = s
            winner = name

    # edge tag
    ef = arms["exit_first_composite"]
    if n_ok < 8:
        edge_class = "inconclusive_sparse_N"
    elif (ef.get("sum_delta_winsor") or 0) > 15 and (ef.get("median_delta") or 0) > 0:
        edge_class = "ATTENTION_ONLY_less_loss_path"
    elif (ef.get("sum_delta_winsor") or 0) > 0:
        edge_class = "ATTENTION_ONLY"
    else:
        edge_class = "unstable_or_no_edge"

    # bank_trail cross-read
    bt_note = None
    bt_path = STATE / "bank_trail_while_green_cf_latest.json"
    if bt_path.exists():
        try:
            bt = json.loads(bt_path.read_text(encoding="utf-8"))
            s = bt.get("summary") or {}
            bt_note = {
                "verdict": bt.get("verdict"),
                "winner_would_arm_only": s.get("winner_would_arm_only"),
                "C_sum_delta_would_arm": ((s.get("would_arm_only") or {}).get("C") or {}).get(
                    "sum_delta_vs_actual_usd"
                ),
            }
        except Exception:
            pass

    plain = (
        f"Alt C exit-first CF since {since.date()}: n_ok={n_ok} skips={n_skip} · "
        f"exit_first winsor Δ$={ef.get('sum_delta_winsor')} med={ef.get('median_delta')} · "
        f"winner={winner} · edge={edge_class} · LIVE_APPLY=false · not a GO."
    )

    payload: Dict[str, Any] = {
        "schema": SCHEMA,
        "as_of": _now().isoformat(),
        "live_apply": LIVE_APPLY,
        "window": {"since": since.isoformat(), "days": days},
        "n_legs_matched": len(legs),
        "n_ok_candles": n_ok,
        "n_candle_fail": n_candle_fail,
        "n_exit_first_skips": n_skip,
        "actual_pnl_sum_ok_legs": actual_sum,
        "arms": arms,
        "winner_by_winsor_sum_delta": winner,
        "edge_class": edge_class,
        "bank_trail_crossread": bt_note,
        "legs_sample": detailed[:15],
        "legs_worst_actual": sorted(
            [d for d in detailed if d.get("status") == "ok"],
            key=lambda x: x.get("actual_pnl_usd") or 0,
        )[:8],
        "plain_english": plain,
        "does_not_claim": [
            "Not live trail/TP promote",
            "Not proof exit-first beats all regimes",
            "Synthetic fills use fee haircut; path order of MFE vs MAE is bar-level not tick",
            "Skip=never entered is counterfactual capital timing — opportunity cost not fully modeled",
        ],
        "next_measure_step": [
            "Half-sample / by regime when stamps denser",
            "Join bank_trail would_arm legs only for promote read",
            "Keep live trail as-is until Brad GO",
        ],
    }

    md = _render_md(payload)
    if write:
        STATE.mkdir(parents=True, exist_ok=True)
        REPORTS.mkdir(parents=True, exist_ok=True)
        # store more legs in json
        payload_write = dict(payload)
        payload_write["legs"] = detailed
        OUT_JSON.write_text(json.dumps(payload_write, indent=2, default=str) + "\n", encoding="utf-8")
        OUT_MD.write_text(md, encoding="utf-8")
        payload["wrote_json"] = str(OUT_JSON)
        payload["wrote_md"] = str(OUT_MD)
    payload["md"] = md
    return payload


def _render_md(p: Dict[str, Any]) -> str:
    lines = [
        "# Measure CF — Alt C Exit-First Redesign",
        "",
        f"**As of:** {p.get('as_of')}  ",
        f"**Since:** {(p.get('window') or {}).get('since')}  ",
        f"**live_apply:** `{p.get('live_apply')}`  ",
        f"**Edge class:** `{p.get('edge_class')}`  ",
        f"**Winner (winsor Δ$):** `{p.get('winner_by_winsor_sum_delta')}`  ",
        "",
        "## Plain English",
        "",
        str(p.get("plain_english") or ""),
        "",
        f"- Legs matched: **{p.get('n_legs_matched')}** · ok candles: **{p.get('n_ok_candles')}** · "
        f"exit-first skips: **{p.get('n_exit_first_skips')}**",
        f"- Actual PnL sum (ok legs): **${p.get('actual_pnl_sum_ok_legs')}**",
        "",
        "## Arms vs actual (Δ$)",
        "",
        "| Arm | n_fire/skip | sum Δ$ | winsor sum Δ$ | median Δ$ | sum PnL |",
        "|-----|-------------|--------|---------------|-----------|---------|",
    ]
    for name, a in (p.get("arms") or {}).items():
        lines.append(
            f"| `{name}` | {a.get('n_fired_or_skip')} | {a.get('sum_delta')} | "
            f"{a.get('sum_delta_winsor')} | {a.get('median_delta')} | {a.get('sum_pnl')} |"
        )
    if p.get("bank_trail_crossread"):
        lines += [
            "",
            "## Bank-trail cross-read",
            "",
            "```json",
            json.dumps(p.get("bank_trail_crossread"), indent=2),
            "```",
        ]
    lines += [
        "",
        "## Does NOT claim",
        "",
    ]
    for x in p.get("does_not_claim") or []:
        lines.append(f"- {x}")
    lines += [
        "",
        f"JSON: `{OUT_JSON.relative_to(ROOT)}`",
        "",
    ]
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Alt C exit-first measure CF")
    ap.add_argument("--days", type=int, default=120)
    ap.add_argument("--since", default=None)
    ap.add_argument("--no-network", action="store_true")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--max-legs", type=int, default=80)
    ap.add_argument("--json-stdout", action="store_true")
    args = ap.parse_args(argv)
    since = _parse_ts(args.since) if args.since else None
    payload = run_cf(
        since=since,
        days=args.days,
        allow_network=not args.no_network,
        write=not args.no_write,
        max_legs=args.max_legs,
    )
    print(payload.get("plain_english"))
    if payload.get("wrote_md"):
        print(f"Report: {payload['wrote_md']}")
    if args.json_stdout:
        slim = {k: v for k, v in payload.items() if k not in ("md", "legs_sample")}
        print(json.dumps(slim, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
