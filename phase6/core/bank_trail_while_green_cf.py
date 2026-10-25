"""Bank/trail-while-green triple shadow CF (A / C / A→C) — measure-only.

Replays ballast/core legs on 1h OHLCV and compares:
  - control: actual SL (or ride path)
  - A: partial bank at arm MFE
  - C: soft trail after arm MFE
  - AC: partial then trail on residual

No live orders. live_apply is always false here.
"""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path("/home/brad/projects/crypto-trading-bot")
DEFAULT_CFG = ROOT / "config" / "bank_trail_while_green_shadow.json"
DEFAULT_OUT_JSON = ROOT / "data" / "state" / "bank_trail_while_green_cf_latest.json"
DEFAULT_OUT_MD = ROOT / "reports" / "BANK_TRAIL_WHILE_GREEN_CF_LATEST.md"
TRADES = ROOT / "trades" / "phase6_trades.jsonl"

# Reuse candle helpers from SL width CF (same 1h cache + fetch)
from scripts.phase6 import run_sl_width_3v8_cf as slw  # type: ignore


def load_policy(path: Path | None = None) -> dict[str, Any]:
    p = path or DEFAULT_CFG
    return json.loads(p.read_text(encoding="utf-8"))


def _parse_ts(s: Any) -> datetime | None:
    return slw._parse_ts(s)


def _fee(notional: float, fee_frac: float) -> float:
    return abs(notional) * fee_frac


def _in_scope(pair: str, notional: float, cfg: dict[str, Any]) -> bool:
    scope = cfg.get("scope") or {}
    excl = {str(x).upper() for x in (scope.get("exclude_pairs") or [])}
    if pair.upper() in excl:
        return False
    core = {str(x).upper() for x in (scope.get("core_pairs") or [])}
    min_n = float(scope.get("min_notional_usd") or 75.0)
    if pair.upper() in core and scope.get("include_core_even_if_below_min_notional", True):
        return True
    return notional >= min_n


def _iter_candles_window(
    candles: list[list[float]], entry_ts: float, exit_ts: float
) -> list[list[float]]:
    out = []
    for c in candles:
        t = c[0]
        if t + 3600 < entry_ts:
            continue
        if t > exit_ts + 3600:
            break
        out.append(c)
    return out


def _arm_bar(
    window: list[list[float]], entry_px: float, arm_mfe: float
) -> dict[str, Any] | None:
    """First bar whose high reaches entry*(1+arm_mfe). Arm mark = entry*(1+arm_mfe)."""
    if entry_px <= 0 or not window:
        return None
    target = entry_px * (1.0 + arm_mfe)
    peak = 0.0
    for c in window:
        t, low, high = c[0], c[1], c[2]
        peak = max(peak, high / entry_px - 1.0)
        if high >= target:
            return {
                "ts": t,
                "ts_iso": datetime.fromtimestamp(t, tz=timezone.utc).isoformat(),
                "arm_px": target,
                "bar_high": high,
                "bar_low": low,
                "mfe_at_arm": peak,
            }
    return None


def _path_mfe(window: list[list[float]], entry_px: float) -> float:
    if entry_px <= 0:
        return 0.0
    mfe = 0.0
    for c in window:
        mfe = max(mfe, c[2] / entry_px - 1.0)
    return mfe


def sim_control(
    *,
    entry_px: float,
    qty: float,
    actual_pnl: float,
    actual_exit_px: float | None,
) -> dict[str, Any]:
    return {
        "arm": "control",
        "pnl_usd": float(actual_pnl),
        "exit_px": actual_exit_px,
        "events": [{"kind": "actual_exit", "pnl_usd": float(actual_pnl)}],
        "would_arm": False,
    }


def sim_A(
    window: list[list[float]],
    *,
    entry_px: float,
    qty: float,
    actual_exit_px: float,
    actual_exit_ts: float,
    arm_mfe: float,
    partial_frac: float,
    residual_sl_pct: float,
    fee_frac: float,
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    arm = _arm_bar(window, entry_px, arm_mfe)
    if arm is None:
        # no arm — same as riding to actual
        pnl = qty * (actual_exit_px - entry_px) - _fee(qty * entry_px, fee_frac) - _fee(
            qty * actual_exit_px, fee_frac
        )
        return {
            "arm": "A",
            "would_arm": False,
            "pnl_usd": pnl,
            "events": [{"kind": "no_arm_ride_actual", "pnl_usd": pnl}],
            "partial_usd": 0.0,
            "residual_pnl_usd": pnl,
        }

    q_part = qty * partial_frac
    q_res = qty - q_part
    arm_px = float(arm["arm_px"])
    # bank partial at arm (fee both sides on that slice)
    part_gross = q_part * (arm_px - entry_px)
    part_fee = _fee(q_part * entry_px, fee_frac) + _fee(q_part * arm_px, fee_frac)
    part_net = part_gross - part_fee
    events.append(
        {
            "kind": "partial_bank",
            "ts_iso": arm["ts_iso"],
            "px": arm_px,
            "qty": q_part,
            "pnl_usd": part_net,
        }
    )

    # residual: first touch of entry*(1-residual_sl) after arm, else actual exit
    stop_px = entry_px * (1.0 - residual_sl_pct)
    res_exit_px = actual_exit_px
    res_kind = "residual_actual"
    for c in window:
        if c[0] < arm["ts"]:
            continue
        if c[0] > actual_exit_ts + 3600:
            break
        if c[1] <= stop_px:
            res_exit_px = stop_px if c[3] >= stop_px else float(c[3])
            res_kind = "residual_8pct_sl"
            events.append(
                {
                    "kind": res_kind,
                    "ts_iso": datetime.fromtimestamp(c[0], tz=timezone.utc).isoformat(),
                    "px": res_exit_px,
                    "qty": q_res,
                }
            )
            break
    else:
        events.append(
            {
                "kind": res_kind,
                "px": res_exit_px,
                "qty": q_res,
            }
        )

    res_gross = q_res * (res_exit_px - entry_px)
    res_fee = _fee(q_res * entry_px, fee_frac) + _fee(q_res * res_exit_px, fee_frac)
    res_net = res_gross - res_fee
    total = part_net + res_net
    return {
        "arm": "A",
        "would_arm": True,
        "pnl_usd": total,
        "partial_usd": part_net,
        "residual_pnl_usd": res_net,
        "arm_ts_iso": arm["ts_iso"],
        "arm_px": arm_px,
        "events": events,
    }


def _trail_stop(entry_px: float, peak_px: float, lock_frac: float, be_buffer: float) -> float:
    """Stop = max(BE+buffer, peak - lock_frac * (peak-entry) in price space)."""
    be = entry_px * (1.0 + be_buffer)
    if peak_px <= entry_px:
        return be
    gain = peak_px - entry_px
    locked = peak_px - lock_frac * gain  # keep (1-lock_frac) of gain from peak... 
    # Spec: lock_frac_of_mfe means lock that fraction of peak gain from entry
    # stop = entry + lock_frac * (peak - entry)  → locks lock_frac of MFE
    stop_lock = entry_px + lock_frac * (peak_px - entry_px)
    return max(be, stop_lock)


def sim_C(
    window: list[list[float]],
    *,
    entry_px: float,
    qty: float,
    actual_exit_px: float,
    actual_exit_ts: float,
    arm_mfe: float,
    lock_frac: float,
    be_buffer: float,
    fee_frac: float,
) -> dict[str, Any]:
    arm = _arm_bar(window, entry_px, arm_mfe)
    if arm is None:
        pnl = qty * (actual_exit_px - entry_px) - _fee(qty * entry_px, fee_frac) - _fee(
            qty * actual_exit_px, fee_frac
        )
        return {
            "arm": "C",
            "would_arm": False,
            "pnl_usd": pnl,
            "events": [{"kind": "no_arm_ride_actual", "pnl_usd": pnl}],
        }

    peak_px = float(arm["arm_px"])
    stop = _trail_stop(entry_px, peak_px, lock_frac, be_buffer)
    events: list[dict[str, Any]] = [
        {
            "kind": "trail_arm",
            "ts_iso": arm["ts_iso"],
            "peak_px": peak_px,
            "stop_px": stop,
        }
    ]
    exit_px = None
    exit_ts_iso = None
    for c in window:
        if c[0] < arm["ts"]:
            continue
        if c[0] > actual_exit_ts + 3600:
            break
        # ratchet peak/stop on highs
        if c[2] > peak_px:
            peak_px = c[2]
            new_stop = _trail_stop(entry_px, peak_px, lock_frac, be_buffer)
            if new_stop > stop:
                stop = new_stop
                events.append(
                    {
                        "kind": "trail_ratchet",
                        "ts_iso": datetime.fromtimestamp(c[0], tz=timezone.utc).isoformat(),
                        "peak_px": peak_px,
                        "stop_px": stop,
                    }
                )
        if c[1] <= stop:
            exit_px = stop if c[3] >= stop else float(c[3])
            exit_ts_iso = datetime.fromtimestamp(c[0], tz=timezone.utc).isoformat()
            events.append(
                {
                    "kind": "trail_exit",
                    "ts_iso": exit_ts_iso,
                    "px": exit_px,
                    "qty": qty,
                }
            )
            break

    if exit_px is None:
        exit_px = actual_exit_px
        events.append({"kind": "trail_never_hit_use_actual", "px": exit_px, "qty": qty})

    pnl = qty * (exit_px - entry_px) - _fee(qty * entry_px, fee_frac) - _fee(
        qty * exit_px, fee_frac
    )
    return {
        "arm": "C",
        "would_arm": True,
        "pnl_usd": pnl,
        "exit_px": exit_px,
        "arm_ts_iso": arm["ts_iso"],
        "final_stop_px": stop,
        "events": events,
    }


def sim_AC(
    window: list[list[float]],
    *,
    entry_px: float,
    qty: float,
    actual_exit_px: float,
    actual_exit_ts: float,
    arm_mfe: float,
    partial_frac: float,
    lock_frac: float,
    be_buffer: float,
    fee_frac: float,
    residual_sl_pct: float = 0.08,
) -> dict[str, Any]:
    """Partial at arm, then trail residual (disaster floor still 8% until trail tighter)."""
    arm = _arm_bar(window, entry_px, arm_mfe)
    fee = fee_frac
    if arm is None:
        pnl = qty * (actual_exit_px - entry_px) - _fee(qty * entry_px, fee) - _fee(
            qty * actual_exit_px, fee
        )
        return {
            "arm": "AC",
            "would_arm": False,
            "pnl_usd": pnl,
            "events": [{"kind": "no_arm_ride_actual", "pnl_usd": pnl}],
        }

    q_part = qty * partial_frac
    q_res = qty - q_part
    arm_px = float(arm["arm_px"])
    part_gross = q_part * (arm_px - entry_px)
    part_net = part_gross - _fee(q_part * entry_px, fee) - _fee(q_part * arm_px, fee)
    events: list[dict[str, Any]] = [
        {
            "kind": "partial_bank",
            "ts_iso": arm["ts_iso"],
            "px": arm_px,
            "qty": q_part,
            "pnl_usd": part_net,
        }
    ]

    peak_px = arm_px
    trail = _trail_stop(entry_px, peak_px, lock_frac, be_buffer)
    floor8 = entry_px * (1.0 - residual_sl_pct)
    # effective stop = max(trail, floor8) once trail armed above floor — actually
    # trail should protect green: use max(trail, floor8) only if trail < floor? 
    # Disaster floor is the *lower bound of patience*: we exit at whichever hits first
    # among trail (above) and 8% (below). So stop_eff for downside = max(trail, floor8)
    # when trail > floor8 (trail is tighter/higher). When trail still near BE, floor8 is lower.
    stop_eff = max(trail, floor8) if trail > floor8 else trail
    # clearer: exit if low <= trail (profit lock) OR low <= floor8 (disaster)
    res_exit = None
    for c in window:
        if c[0] < arm["ts"]:
            continue
        if c[0] > actual_exit_ts + 3600:
            break
        if c[2] > peak_px:
            peak_px = c[2]
            trail = _trail_stop(entry_px, peak_px, lock_frac, be_buffer)
            events.append(
                {
                    "kind": "trail_ratchet",
                    "ts_iso": datetime.fromtimestamp(c[0], tz=timezone.utc).isoformat(),
                    "peak_px": peak_px,
                    "stop_px": trail,
                }
            )
        hit_trail = c[1] <= trail
        hit_floor = c[1] <= floor8
        if hit_trail or hit_floor:
            if hit_trail and (not hit_floor or trail >= floor8):
                res_exit = trail if c[3] >= trail else float(c[3])
                kind = "residual_trail_exit"
            else:
                res_exit = floor8 if c[3] >= floor8 else float(c[3])
                kind = "residual_8pct_sl"
            events.append(
                {
                    "kind": kind,
                    "ts_iso": datetime.fromtimestamp(c[0], tz=timezone.utc).isoformat(),
                    "px": res_exit,
                    "qty": q_res,
                }
            )
            break

    if res_exit is None:
        res_exit = actual_exit_px
        events.append({"kind": "residual_actual", "px": res_exit, "qty": q_res})

    res_net = q_res * (res_exit - entry_px) - _fee(q_res * entry_px, fee) - _fee(
        q_res * res_exit, fee
    )
    total = part_net + res_net
    return {
        "arm": "AC",
        "would_arm": True,
        "pnl_usd": total,
        "partial_usd": part_net,
        "residual_pnl_usd": res_net,
        "arm_ts_iso": arm["ts_iso"],
        "events": events,
    }


def _reconcile_sl_pnl(leg: dict[str, Any]) -> None:
    """Prefer path economics when ledger PnL is fantasy on an SL fill."""
    ledger_entry = float(leg.get("entry_price") or 0)
    ledger_qty = float(leg.get("qty") or 0)
    exit_px = float(leg.get("exit_price") or 0)
    if exit_px <= 0 or ledger_entry <= 0 or ledger_qty <= 0:
        return
    path_pnl = ledger_qty * (exit_px - ledger_entry)
    ap = float(leg.get("actual_pnl_usd") or 0)
    disagree = abs(ap - path_pnl) > max(5.0, 0.5 * abs(path_pnl) + 1.0)
    # Stop-loss with large positive ledger PnL while path is red/flat = poison
    sl_fantasy = ap > 5.0 and path_pnl <= abs(ap) * 0.25
    if disagree or sl_fantasy:
        leg["pnl_reconcile_warn"] = {
            "ledger_pnl": ap,
            "path_pnl": round(path_pnl, 4),
            "sl_fantasy": sl_fantasy,
            "note": "prefer path_pnl for CF deltas when ledger disagrees",
        }
        leg["actual_pnl_usd_ledger"] = ap
        leg["actual_pnl_usd"] = path_pnl


def load_sl_legs_scoped(since: datetime, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Exchange SL sells in scope (ballast/core)."""
    legs = []
    for t in slw._load_jsonl(TRADES):
        side = str(t.get("side") or t.get("type") or "").lower()
        if side != "sell":
            continue
        reason = str(t.get("reason") or "").lower()
        if "stop_loss" not in reason:
            continue
        ts = _parse_ts(t.get("ts") or t.get("timestamp") or t.get("filled_at"))
        if ts is None or ts < since:
            continue
        pair = str(t.get("pair") or t.get("product_id") or "")
        if not pair:
            continue
        entry = float(t.get("entry_price") or 0)
        qty = float(t.get("qty") or t.get("size") or t.get("filled_size") or 0)
        if entry <= 0 or qty <= 0:
            continue
        notional = entry * qty
        if not _in_scope(pair, notional, cfg):
            continue
        exit_px = float(t.get("exit_price") or t.get("price") or t.get("fill_price") or 0)
        pnl = t.get("pnl")
        if pnl is None:
            pnl = t.get("pnl_usd")
        if pnl is None and exit_px:
            pnl = qty * (exit_px - entry)
        legs.append(
            {
                "pair": pair,
                "sl_ts": ts.isoformat(),
                "sl_ts_epoch": ts.timestamp(),
                "entry_price": entry,
                "qty": qty,
                "notional_usd": notional,
                "exit_price": exit_px,
                "actual_pnl_usd": float(pnl or 0),
                "reason": t.get("reason"),
                "entry_ts": None,  # filled below from matching buys
            }
        )
    # attach entry_ts from prior buys (LIFO-ish: last buy before SL)
    buys_by_pair: dict[str, list[tuple[datetime, dict]]] = {}
    for t in slw._load_jsonl(TRADES):
        side = str(t.get("side") or t.get("type") or "").lower()
        if side != "buy":
            continue
        pair = str(t.get("pair") or t.get("product_id") or "")
        ts = _parse_ts(t.get("ts") or t.get("timestamp") or t.get("filled_at"))
        if not pair or ts is None:
            continue
        buys_by_pair.setdefault(pair, []).append((ts, t))
    for leg in legs:
        pair = leg["pair"]
        sl_ts = datetime.fromisoformat(leg["sl_ts"])
        # SSOT size/entry/pnl stay on the SL sell row. Buy cluster only stamps entry_ts
        # (rewriting qty from all history buys poisons multi-lot careers — LINK ghost).
        ledger_entry = float(leg["entry_price"])
        ledger_qty = float(leg["qty"])
        cands = [b for b in buys_by_pair.get(pair, []) if b[0] <= sl_ts]
        if not cands:
            leg["entry_ts"] = sl_ts.timestamp() - 14 * 86400
            leg["entry_ts_iso"] = datetime.fromtimestamp(
                leg["entry_ts"], tz=timezone.utc
            ).isoformat()
            leg["entry_ts_source"] = "fallback_14d"
            _reconcile_sl_pnl(leg)
            continue
        last_ts, _last_b = cands[-1]
        # Walk back while buys are contiguous-ish (gap <= 48h) AND cumulative qty
        # stays within ~15% of ledger SL qty (don't swallow prior careers).
        cluster_rev: list[tuple[datetime, dict]] = []
        q_acc = 0.0
        prev_ts = last_ts
        for ts_b, b in reversed(cands):
            if (prev_ts - ts_b).total_seconds() > 48 * 3600 and cluster_rev:
                break
            q = float(b.get("qty") or b.get("size") or 0)
            if q <= 0:
                continue
            if cluster_rev and ledger_qty > 0 and (q_acc + q) > ledger_qty * 1.15:
                break
            cluster_rev.append((ts_b, b))
            q_acc += q
            prev_ts = ts_b
            if ledger_qty > 0 and q_acc >= ledger_qty * 0.85:
                # enough mass for this bag
                # still allow same-hour siblings
                continue
        cluster = list(reversed(cluster_rev)) or [cands[-1]]
        first_ts = cluster[0][0]
        leg["entry_ts"] = first_ts.timestamp()
        leg["entry_ts_iso"] = first_ts.isoformat()
        leg["entry_ts_source"] = "buy_cluster_ts_only"
        leg["entry_price"] = ledger_entry
        leg["qty"] = ledger_qty
        leg["notional_usd"] = ledger_entry * ledger_qty
        _reconcile_sl_pnl(leg)
    return legs


def run_leg(
    leg: dict[str, Any], cfg: dict[str, Any], candles: list[list[float]]
) -> dict[str, Any]:
    arms_cfg = cfg.get("arms") or {}
    a = arms_cfg.get("A") or {}
    c = arms_cfg.get("C") or {}
    ac = arms_cfg.get("AC") or {}
    entry_px = float(leg["entry_price"])
    qty = float(leg["qty"])
    exit_px = float(leg.get("exit_price") or 0)
    if exit_px <= 0:
        exit_px = entry_px * 0.92
    entry_ts = float(leg["entry_ts"])
    exit_ts = float(leg["sl_ts_epoch"])
    window = _iter_candles_window(candles, entry_ts, exit_ts)
    mfe = _path_mfe(window, entry_px)

    control = sim_control(
        entry_px=entry_px,
        qty=qty,
        actual_pnl=float(leg["actual_pnl_usd"]),
        actual_exit_px=exit_px,
    )
    # Prefer fee-aware path control for fair delta: rebuild control from path too
    fee = float(a.get("fee_frac_per_leg") or 0.003)
    control_path = qty * (exit_px - entry_px) - _fee(qty * entry_px, fee) - _fee(
        qty * exit_px, fee
    )
    control["pnl_usd_path_fee"] = control_path
    # deltas vs ledger actual (operator-facing) and vs path-fee control
    base_actual = float(leg["actual_pnl_usd"])

    res_a = sim_A(
        window,
        entry_px=entry_px,
        qty=qty,
        actual_exit_px=exit_px,
        actual_exit_ts=exit_ts,
        arm_mfe=float(a.get("arm_mfe_pct") or 0.03),
        partial_frac=float(a.get("partial_frac") or 0.33),
        residual_sl_pct=float(a.get("residual_sl_pct") or 0.08),
        fee_frac=fee,
    )
    res_c = sim_C(
        window,
        entry_px=entry_px,
        qty=qty,
        actual_exit_px=exit_px,
        actual_exit_ts=exit_ts,
        arm_mfe=float(c.get("arm_mfe_pct") or 0.03),
        lock_frac=float(c.get("lock_frac_of_mfe") or 0.35),
        be_buffer=float(c.get("be_buffer_pct") or 0.005),
        fee_frac=float(c.get("fee_frac_per_leg") or fee),
    )
    res_ac = sim_AC(
        window,
        entry_px=entry_px,
        qty=qty,
        actual_exit_px=exit_px,
        actual_exit_ts=exit_ts,
        arm_mfe=float(ac.get("arm_mfe_pct") or 0.03),
        partial_frac=float(ac.get("partial_frac") or 0.33),
        lock_frac=float(ac.get("lock_frac_of_mfe") or 0.35),
        be_buffer=float(ac.get("be_buffer_pct") or 0.005),
        fee_frac=float(ac.get("fee_frac_per_leg") or fee),
        residual_sl_pct=0.08,
    )

    def pack(r: dict[str, Any]) -> dict[str, Any]:
        pnl = float(r.get("pnl_usd") or 0)
        return {
            **{k: v for k, v in r.items() if k != "events"},
            "events_n": len(r.get("events") or []),
            "events": r.get("events") or [],
            "delta_vs_actual_usd": pnl - base_actual,
            "delta_vs_path_fee_usd": pnl - control_path,
        }

    return {
        "pair": leg["pair"],
        "sl_ts": leg["sl_ts"],
        "entry_ts_iso": leg.get("entry_ts_iso"),
        "entry_ts_source": leg.get("entry_ts_source"),
        "entry_price": entry_px,
        "qty": qty,
        "notional_usd": round(entry_px * qty, 2),
        "exit_price": exit_px,
        "actual_pnl_usd": base_actual,
        "path_mfe": round(mfe, 5),
        "n_bars": len(window),
        "control": control,
        "A": pack(res_a),
        "C": pack(res_c),
        "AC": pack(res_ac),
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def arm_stats(key: str, subset: list[dict[str, Any]]) -> dict[str, Any]:
        if not subset:
            return {
                "n": 0,
                "n_would_arm": 0,
                "sum_pnl_usd": 0.0,
                "sum_delta_vs_actual_usd": 0.0,
                "median_delta_vs_actual_usd": 0.0,
            }
        deltas = [float(r[key]["delta_vs_actual_usd"]) for r in subset]
        pnls = [float(r[key]["pnl_usd"]) for r in subset]
        armed = sum(1 for r in subset if r[key].get("would_arm"))
        s = sorted(deltas)
        med = s[len(s) // 2] if s else 0.0
        return {
            "n": len(subset),
            "n_would_arm": armed,
            "sum_pnl_usd": round(sum(pnls), 4),
            "sum_delta_vs_actual_usd": round(sum(deltas), 4),
            "median_delta_vs_actual_usd": round(med, 4),
        }

    armed_rows = [r for r in rows if r.get("A", {}).get("would_arm") or r.get("C", {}).get("would_arm")]
    actual_sum = round(sum(float(r["actual_pnl_usd"]) for r in rows), 4)
    actual_armed = round(sum(float(r["actual_pnl_usd"]) for r in armed_rows), 4)

    def winner(subset_stats: dict) -> str | None:
        if not rows:
            return None
        return max(
            (
                ("A", subset_stats["A"]["sum_delta_vs_actual_usd"]),
                ("C", subset_stats["C"]["sum_delta_vs_actual_usd"]),
                ("AC", subset_stats["AC"]["sum_delta_vs_actual_usd"]),
            ),
            key=lambda x: x[1],
        )[0]

    all_stats = {k: arm_stats(k, rows) for k in ("A", "C", "AC")}
    arm_only = {k: arm_stats(k, armed_rows) for k in ("A", "C", "AC")}
    return {
        "n_legs": len(rows),
        "n_would_arm_legs": len(armed_rows),
        "actual_pnl_sum": actual_sum,
        "actual_pnl_sum_would_arm_legs": actual_armed,
        "A": all_stats["A"],
        "C": all_stats["C"],
        "AC": all_stats["AC"],
        "would_arm_only": arm_only,
        "winner_by_sum_delta": winner(all_stats),
        "winner_would_arm_only": winner(arm_only) if armed_rows else None,
        "note": (
            "Primary promote read = would_arm_only (legs that actually printed ≥ arm MFE). "
            "All-legs board includes fee drag on never-armed dead paths."
        ),
    }


def format_md(payload: dict[str, Any]) -> str:
    s = payload.get("summary") or {}
    lines = [
        "# Bank / trail while green — triple shadow CF",
        "",
        f"**Status:** MEASURE_ONLY · `live_apply: false`",
        f"**As of:** {payload.get('as_of')}",
        f"**Since:** {payload.get('since')}",
        f"**n legs (ballast/core SL):** {s.get('n_legs')} · **would-arm legs:** {s.get('n_would_arm_legs')}",
        f"**Actual SL PnL sum (all):** {s.get('actual_pnl_sum')} · **would-arm subset:** {s.get('actual_pnl_sum_would_arm_legs')}",
        "",
        "## Primary scoreboard — would-arm legs only (printed ≥ arm MFE)",
        "",
        "| Arm | n | sum Δ$ vs actual | median Δ$ | sum pnl |",
        "|-----|---|------------------|-----------|---------|",
    ]
    wo = s.get("would_arm_only") or {}
    for key, label in (("A", "A partial only"), ("C", "C soft trail"), ("AC", "A→C combo")):
        a = wo.get(key) or {}
        lines.append(
            f"| **{label}** | {a.get('n')} | "
            f"{a.get('sum_delta_vs_actual_usd')} | {a.get('median_delta_vs_actual_usd')} | "
            f"{a.get('sum_pnl_usd')} |"
        )
    lines += [
        "",
        f"**Winner (would-arm only):** `{s.get('winner_would_arm_only')}`",
        "",
        "## Secondary — all scoped SL legs (includes never-armed fee drag)",
        "",
        "| Arm | would_arm | sum Δ$ | median Δ$ | sum pnl |",
        "|-----|-----------|--------|-----------|---------|",
    ]
    for key, label in (("A", "A partial only"), ("C", "C soft trail"), ("AC", "A→C combo")):
        a = s.get(key) or {}
        lines.append(
            f"| **{label}** | {a.get('n_would_arm')}/{a.get('n')} | "
            f"{a.get('sum_delta_vs_actual_usd')} | {a.get('median_delta_vs_actual_usd')} | "
            f"{a.get('sum_pnl_usd')} |"
        )
    lines += [
        "",
        f"**Winner (all legs, sample only):** `{s.get('winner_by_sum_delta')}`",
        "",
        f"_{s.get('note')}_",
        "",
        "## Per leg",
        "",
    ]
    for r in payload.get("legs") or []:
        lines.append(
            f"### {r['pair']} · SL {r['sl_ts'][:19]} · notional ~${r['notional_usd']} · "
            f"MFE {r['path_mfe']:.2%} · actual {r['actual_pnl_usd']:.2f}"
        )
        lines.append("")
        lines.append("| Arm | would_arm | pnl | Δ vs actual |")
        lines.append("|-----|-----------|-----|-------------|")
        for k in ("A", "C", "AC"):
            a = r[k]
            lines.append(
                f"| {k} | {a.get('would_arm')} | {a.get('pnl_usd'):.4f} | "
                f"{a.get('delta_vs_actual_usd'):.4f} |"
            )
        lines.append("")
    lines += [
        "## Rules",
        "",
        "- No live apply from this report.",
        "- Scope: core BTC/ETH or notional ≥ $75; PAXG excluded.",
        "- Tryout shells are out of scope (trail TP + W2 fuse).",
        "- Promote only with Brad GO after n and net clear fees.",
        "",
    ]
    return "\n".join(lines) + "\n"


def run_cf(
    *,
    since: datetime | None = None,
    cfg_path: Path | None = None,
    write: bool = True,
) -> dict[str, Any]:
    cfg = load_policy(cfg_path)
    if since is None:
        since = datetime(2026, 8, 6, tzinfo=timezone.utc)
    legs = load_sl_legs_scoped(since, cfg)
    rows = []
    for leg in legs:
        entry_ts = float(leg["entry_ts"])
        exit_ts = float(leg["sl_ts_epoch"])
        start = datetime.fromtimestamp(entry_ts, tz=timezone.utc)
        end = datetime.fromtimestamp(exit_ts, tz=timezone.utc)
        candles = slw._ensure_candles(leg["pair"], start, end)
        if not candles:
            rows.append({**leg, "error": "no_candles", "A": {}, "C": {}, "AC": {}})
            continue
        rows.append(run_leg(leg, cfg, candles))

    # drop errored from summary
    ok = [r for r in rows if "error" not in r and r.get("A")]
    summary = summarize(ok)
    payload = {
        "schema": "bank_trail_while_green_cf_v1",
        "status": "MEASURE_ONLY",
        "live_apply": False,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "since": since.isoformat(),
        "policy": str(cfg_path or DEFAULT_CFG),
        "summary": summary,
        "legs": ok,
        "n_skipped": len(rows) - len(ok),
        "verdict": (
            "ATTENTION_ONLY — compare A vs C vs AC on ballast SL legs; "
            "no live GO; do not read single-leg winner as promote."
        ),
    }
    if write:
        DEFAULT_OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_OUT_MD.parent.mkdir(parents=True, exist_ok=True)
        # Embed measure-collect health so GO packets see meter first
        try:
            from phase6.research.measure_collect_health import health_bank_trail

            # write first so health_bank_trail can read latest
            DEFAULT_OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            bh = health_bank_trail()
            payload["measure_health"] = bh
            payload["collect_clock_ok"] = bool(bh.get("collect_clock_ok"))
            payload["measure_health_code"] = bh.get("code")
            DEFAULT_OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            (ROOT / "data" / "state" / "measure_collect_health_bank_trail_latest.json").write_text(
                json.dumps(bh, indent=2, default=str) + "\n", encoding="utf-8"
            )
        except Exception as e:
            payload["measure_health"] = {
                "ok": False,
                "code": "sensor_broken",
                "plain_english": f"bank_trail health attach failed: {e}",
                "collect_clock_ok": False,
            }
            DEFAULT_OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        DEFAULT_OUT_MD.write_text(format_md(payload), encoding="utf-8")
        payload["wrote_json"] = str(DEFAULT_OUT_JSON)
        payload["wrote_md"] = str(DEFAULT_OUT_MD)
    return payload
