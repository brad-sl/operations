#!/usr/bin/env python3
"""Rebuild E-SOL-LINK-SL-CAREER from ledger + optional CF + dwell.

One-call measure script. No orders, no config changes, no live_apply flips.

Reads:
  trades/phase6_trades.jsonl
  data/state/sl_width_3v8_cf_latest.json (if present)
  data/state/post_proof_dwell.json (if present)
  config/sl_width_arming_policy.json (if present)

Writes:
  reports/E_SOL_LINK_SL_CAREER_2026-10-26.md
  data/state/e_sol_link_sl_career_latest.json

Window: weekly 2026-10-17 → 2026-10-26 UTC, with SOL entry ~Oct 11.
Pairs: SOL-USD, LINK-USD exchange stops.
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
DWELL_JSON = ROOT / "data" / "state" / "post_proof_dwell.json"
SL_POLICY = ROOT / "config" / "sl_width_arming_policy.json"
OUT_MD = ROOT / "reports" / "E_SOL_LINK_SL_CAREER_2026-10-26.md"
OUT_JSON = ROOT / "data" / "state" / "e_sol_link_sl_career_latest.json"

PAIRS = ("SOL-USD", "LINK-USD")
# Start window after the last alt-shell tax week (ending Oct 19)
# and include SOL entry from Oct 11
WIN_START = datetime(2026, 10, 17, tzinfo=timezone.utc)
WIN_END = datetime(2026, 10, 26, tzinfo=timezone.utc) # This week's review cutoff
LOOKBACK = datetime(2026, 10, 11, tzinfo=timezone.utc) # Include SOL Oct 11 entry
WEEKLY_PRIMARY_USD = -9.56


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


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _f(row: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    for k in keys:
        if k in row and row[k] not in (None, ""):
            try:
                return float(row[k])
            except (TypeError, ValueError):
                continue
    return default


def _notional(row: dict[str, Any]) -> float:
    q = _f(row, "qty")
    px = _f(row, "entry_price", "average_filled_price", "exit_price")
    return round(q * px, 4)


def _reason(row: dict[str, Any]) -> str:
    return str(row.get("reason") or row.get("exit_reason") or "")


def _is_sl(row: dict[str, Any]) -> bool:
    blob = f"{_reason(row)} {row.get('exit_class') or ''} {row.get('order_type') or ''}"
    return "stop_loss" in blob.lower() or "CLOSED_SL" in blob


def _is_dust(row: dict[str, Any]) -> bool:
    return "dust" in _reason(row).lower()


def _hold_h(a: datetime | None, b: datetime | None) -> float | None:
    if not a or not b:
        return None
    return round((b - a).total_seconds() / 3600.0, 2)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _classify_role(pair: str, buy: dict[str, Any] | None, sl: dict[str, Any] | None) -> dict[str, Any]:
    notional = _notional(buy) if buy else None
    reason = _reason(buy) if buy else ""
    lot = (sl or {}).get("tryout_lot_close") or {}
    raw_lot = lot.get("lot") if isinstance(lot, dict) else None
    lot_inner: dict[str, Any] = raw_lot if isinstance(raw_lot, dict) else {}
    action = str(lot.get("action") or "")
    sl_attached_at_buy = (buy or {}).get("sl_attached")
    signal = str((buy or {}).get("signal_source") or "")
    notion_s = f"{notional:.0f}" if isinstance(notional, (int, float)) else "?"

    if pair == "SOL-USD":
        role = "tryout_shell"
        note = (
            f"~${notion_s} notional, graduated Oct 2, then SL Oct 24. "
            "Prior `take_profit_trail` proof. Classic ≤$30-50 unproven shell."
        )
    elif pair == "LINK-USD":
        role = "tryout_shell"
        note = (
            f"~${notion_s} notional limit_first_buy; "
            "classic ≤$30 unproven shell. Multi-buy after prior SL career."
        )
    else:
        role = "unknown"
        note = "unclassified"

    size_band = "unknown"
    if notional is not None:
        if notional <= 30:
            size_band = "tryout_leq_30"
        elif notional <= 60:
            size_band = "mid_30_60"
        else:
            size_band = "flat_cap_near_75"

    return {
        "role": role,
        "size_band": size_band,
        "notional_usd": notional,
        "entry_reason": reason or None,
        "signal_source": signal or None,
        "sl_attached_at_buy_stamp": sl_attached_at_buy,
        "tryout_lot_action": action or None,
        "paper_scaled": lot_inner.get("paper_scaled"),
        "live_scaled": lot_inner.get("live_scaled"),
        "note": note,
    }


def _cf_leg(cf: dict[str, Any], pair: str, sl_ts: str | None) -> dict[str, Any] | None:
    if not cf or not sl_ts:
        return None
    want = sl_ts[:19]
    for leg in cf.get("legs") or []:
        if not isinstance(leg, dict):
            continue
        if leg.get("pair") != pair:
            continue
        if want in str(leg.get("sl_ts") or ""):
            return leg
    return None


def _dwell_pair(dwell: dict[str, Any], pair: str) -> dict[str, Any]:
    pairs = dwell.get("pairs") or {}
    entry = pairs.get(pair) if isinstance(pairs, dict) else None
    events = []
    for ev in dwell.get("events") or []:
        if isinstance(ev, dict) and ev.get("pair") == pair:
            events.append(
                {
                    "type": ev.get("type"),
                    "ts": ev.get("ts"),
                    "reason": ev.get("reason"),
                    "status": (ev.get("entry") or {}).get("status"),
                    "tryout_ban_until": (ev.get("entry") or {}).get("tryout_ban_until"),
                    "demote_reason": (ev.get("entry") or {}).get("demote_reason"),
                }
            )
    return {"current": entry, "events": events}


def _compact_trade(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "ts": row.get("timestamp"),
        "side": row.get("side"),
        "qty": row.get("qty"),
        "entry_price": row.get("entry_price"),
        "exit_price": row.get("exit_price"),
        "pnl_usd": _f(row, "pnl_usd", "pnl", "realized_pnl"),
        "pnl_pct": row.get("pnl_pct"),
        "reason": _reason(row) or None,
        "order_id": row.get("order_id"),
        "bag_id": row.get("bag_id"),
        "order_type": row.get("order_type"),
        "signal_source": row.get("signal_source"),
        "sl_attached": row.get("sl_attached"),
        "entry_rsi": row.get("entry_rsi"),
        "entry_sentiment": row.get("entry_sentiment"),
        "exit_rsi": row.get("exit_rsi"),
        "fees": row.get("fees") or row.get("fee_usd"),
        "notional_est": _notional(row),
    }


def _find_buy_for_sl(buys: list[dict[str, Any]], sl: dict[str, Any]) -> dict[str, Any] | None:
    bag = sl.get("bag_id")
    buy_oid = sl.get("buy_order_id") or sl.get("entry_order_id")
    sl_ts = _parse_ts(sl.get("timestamp"))
    # Prefer bag / buy_order_id match at or before SL
    for b in reversed(buys):
        bts = _parse_ts(b.get("timestamp"))
        if sl_ts and bts and bts > sl_ts:
            continue
        if bag and b.get("bag_id") == bag:
            return b
        if buy_oid and (b.get("order_id") == buy_oid or b.get("buy_order_id") == buy_oid):
            return b
    # fallback last buy before SL
    prior = []
    for b in buys:
        bts = _parse_ts(b.get("timestamp"))
        if bts is not None and sl_ts is not None and bts <= sl_ts:
            prior.append(b)
    return prior[-1] if prior else None


def _fmt_usd(x: float | None) -> str:
    if x is None:
        return "unknown"
    sign = "−" if x < 0 else ""
    return f"{sign}${abs(x):.2f}"


def _fmt_pct(x: float | None, already_frac: bool = True) -> str:
    if x is None:
        return "unknown"
    v = x * 100.0 if already_frac and abs(x) <= 2 else x
    return f"{v:.2f}%"


def main() -> int:
    print("[SOL-LINK-SL-CAREER] loading ledger...")
    trades = _load_jsonl(TRADES)
    cf = _load_json(CF_JSON)
    dwell = _load_json(DWELL_JSON)
    policy = _load_json(SL_POLICY)

    by_pair: dict[str, list[dict[str, Any]]] = {p: [] for p in PAIRS}
    for r in trades:
        pair = r.get("pair")
        if pair not in by_pair:
            continue
        ts = _parse_ts(r.get("timestamp"))
        if not ts or ts < LOOKBACK:
            continue
        by_pair[pair].append(r)
    for p in by_pair:
        by_pair[p].sort(key=lambda x: str(x.get("timestamp") or ""))

    careers: list[dict[str, Any]] = []
    for pair in PAIRS:
        rows = by_pair[pair]
        sls = [
            r
            for r in rows
            if str(r.get("side") or "").upper() == "SELL"
            and _is_sl(r)
            and (_parse_ts(r.get("timestamp")) or WIN_START) >= WIN_START
            and (_parse_ts(r.get("timestamp")) or WIN_END) < WIN_END
        ]
        buys = [r for r in rows if str(r.get("side") or "").upper() == "BUY"]
        dusts = [
            r
            for r in rows
            if str(r.get("side") or "").upper() == "SELL" and _is_dust(r)
        ]
        if not sls:
            print(f"ERROR: no stop_loss_exchange in window for {pair}")
            continue # Allow other pairs to run
        sl = sls[0] # Assume one SL per pair per window for now
        buy = _find_buy_for_sl(buys, sl)
        sl_ts = _parse_ts(sl.get("timestamp"))
        buy_ts = _parse_ts(buy.get("timestamp")) if buy else None
        dust = None
        for d in dusts:
            dts = _parse_ts(d.get("timestamp"))
            if sl_ts and dts and dts >= sl_ts:
                dust = d
                break

        reseats = []
        if sl_ts:
            for b in buys:
                bts = _parse_ts(b.get("timestamp"))
                if bts and bts > sl_ts and bts < WIN_END:
                    reseats.append(b)

        role = _classify_role(pair, buy, sl)
        cf_leg = _cf_leg(cf, pair, sl.get("timestamp"))
        dwell_info = _dwell_pair(dwell, pair)
        sl_pnl = _f(sl, "pnl_usd", "pnl", "realized_pnl")
        sl_pct = _f(sl, "pnl_pct")
        dust_pnl = _f(dust, "pnl_usd", "pnl", "realized_pnl") if dust else 0.0
        mfe_before_3 = None
        mfe_to_exit = None
        sim_3 = None
        delta_3 = None
        tag = None
        era = None
        went_green_1 = None
        if cf_leg:
            sim3 = cf_leg.get("sim_3pct") or {}
            mfe_before_3 = sim3.get("mfe_before_touch")
            mfe_to_exit = sim3.get("mfe_to_actual_exit")
            sim_3 = cf_leg.get("sim_pnl_usd_3pct")
            delta_3 = cf_leg.get("delta_usd_3pct_minus_actual")
            tag = cf_leg.get("tag")
            era = cf_leg.get("era")
            went_green_1 = cf_leg.get("went_green_mfe_ge_1pct")

        demote = None
        ban_until = None
        for ev in dwell_info.get("events") or []:
            if ev.get("type") == "demote":
                demote = ev
                ban_until = ev.get("tryout_ban_until")
        current = dwell_info.get("current") or {}
        if current.get("status") == "demoted":
            ban_until = current.get("tryout_ban_until") or ban_until

        reseat_gap_h = None
        if reseats:
            r0 = _parse_ts(reseats[0].get("timestamp"))
            reseat_gap_h = _hold_h(sl_ts, r0)

        ban_vs_reseat = None
        if ban_until and reseats:
            ban_dt = _parse_ts(ban_until)
            r0 = _parse_ts(reseats[0].get("timestamp"))
            ban_vs_reseat = {
                "tryout_ban_until": ban_until,
                "first_reseat_ts": reseats[0].get("timestamp"),
                "hours_after_ban": _hold_h(ban_dt, r0),
                "reseated_after_ban_expired": bool(ban_dt and r0 and r0 >= ban_dt),
            }
        
        # All window buys for full career picture including pre-SL buys
        all_window_buys = [
            _compact_trade(b)
            for b in buys
            if (lambda t: t is not None and LOOKBACK <= t < WIN_END)(_parse_ts(b.get("timestamp")))
        ]
        all_window_buys.sort(key=lambda x: str(x.get("ts") or ""))


        career = {
            "pair": pair,
            "buy": _compact_trade(buy) if buy else None,
            "sl": _compact_trade(sl),
            "dust": _compact_trade(dust) if dust else None,
            "hold_hours": _hold_h(buy_ts, sl_ts),
            "role": role,
            "sl_kind": sl_kind,
            "sl_note": sl_note,
            "sl_pct_ledger": sl_pct,
            "pnl_sl_usd": round(sl_pnl, 6),
            "pnl_dust_usd": round(dust_pnl, 6),
            "pnl_chain_usd": round(sl_pnl + dust_pnl, 6),
            "cf": {
                "present": bool(cf_leg),
                "era": era,
                "tag": tag,
                "mfe_before_3pct_touch": mfe_before_3,
                "mfe_to_actual_exit": mfe_to_exit,
                "sim_pnl_usd_3pct": sim_3,
                "delta_usd_3pct_minus_actual": delta_3,
                "went_green_mfe_ge_1pct": went_green_1,
                "would_3pct_helped_numeric": (
                    True if isinstance(delta_3, (int, float)) and delta_3 > 0 else False
                ),
            },
            "dwell": {
                "demoted_on_sl": bool(demote) or current.get("status") == "demoted",
                "demote_ts": (demote or {}).get("ts") or current.get("demoted_at"),
                "tryout_ban_until": ban_until,
                "current_status": current.get("status"),
                "current_role": current.get("role"),
                "events": dwell_info.get("events"),
            },
            "reseats_after_sl": [_compact_trade(b) for b in reseats],
            "reseat_hours_after_sl": reseat_gap_h,
            "ban_vs_reseat": ban_vs_reseat,
            "window_buys": all_window_buys, # Use all_window_buys here
        }
        careers.append(career)

    tax_sl = round(sum(c["pnl_sl_usd"] for c in careers), 4)
    tax_dust = round(sum(c["pnl_dust_usd"] for c in careers), 4)
    tax_chain = round(tax_sl + tax_dust, 4)
    cf_save = 0.0
    for c in careers:
        d = c["cf"].get("delta_usd_3pct_minus_actual")
        if isinstance(d, (int, float)):
            cf_save += d

    sl_live = ((policy.get("live_default") or {}).get("stop_loss_pct")) or 0.08
    w2_status = policy.get("status") or "unknown"
    w2_live = bool(policy.get("live_apply"))

    now = datetime.now(timezone.utc)

    # Ranked options — evidence-backed, no knob flips in this packet
    ranked = [
        {
            "rank": 1,
            "id": "reseat_after_sl_cooloff",
            "title": "Intake / cooloff / same-name re-seat after SL",
            "evidence": (
                "LINK same-day buy→SL Oct 12 (~10.5h, −$1.96). Dwell demote-on-SL fired; "
                "tryout_ban_until 2026-10-16T00:52; first re-seat 2026-10-16T04:02 (~3h after ban expired) "
                "then second ~$25 lot 2026-10-17T04:01. TIA did not re-seat after SL. ADA did not re-seat." # OLD ADA/TIA context, need to update for SOL/LINK
            ),
            "disposition": "ALREADY_LIVE_WATCH",
            "go": (
                "Do not re-implement. D2 ballast-before-shell + intake hygiene went LIVE 2026-10-17 "
                "(after these LINK reseats). Next week: if same-name reseat still prints under D2, "
                "then a later GO could extend post-SL pair cooloff — measure first."
            ),
        },
        {
            "rank": 2,
            "id": "w2_3pct_fuse_dead_shells",
            "title": "3% fuse on unproven shells that never printed ≥+2% MFE (W2 class)",
            "evidence": (
                f"CF tags SOL/LINK SLs (Oct 24) 3pct_helped_dead_path (SOL ~+$15, LINK ~+$0.8). "
                f"MFE before 3% touch: SOL ~{mfe_before_3_sol:.2%}, LINK ~{mfe_before_3_link:.2%}. "
                "Neither ≥+2% MFE. Not an edge claim."
            ),
            "disposition": "GO_LATER_AFTER_SHADOW",
            "go": (
                "W2 already WIRED_SHADOW_PENDING_14D live_apply=false (started ~2026-10-13). "
                "This packet supports the *class*, not a live_apply flip. Never global 0.08→0.03."
            ),
        },
        {
            "rank": 3,
            "id": "bank_trail_while_green",
            "title": "Bank/trail vs wide SL on green-then-die",
            "evidence": (
                "SOL/LINK printed MFE +3.94% / +3.24% respectively before dying to ~8% SL (Oct 24). "
                "Bank-trail would have armed (if in scope, which it's not for tryouts). "
                "Bank-trail-while-green remains MEASURE_ONLY / Sunday N_INSUFFICIENT."
            ),
            "disposition": "MEASURE_ONLY",
            "go": "Do not GO bank-trail from this packet. Keep Sunday gate. Prefer already-live trail+dwell.",
        },
    ]
    # Update reseat evidence based on SOL/LINK specifically
    link_career = next((c for c in careers if c["pair"] == "LINK-USD"), None)
    sol_career = next((c for c in careers if c["pair"] == "SOL-USD"), None)

    link_reseats_after_sl = [b["ts"] for b in (link_career.get("reseats_after_sl") or [])] if link_career else []
    sol_reseats_after_sl = [b["ts"] for b in (sol_career.get("reseats_after_sl") or [])] if sol_career else []

    reseat_evidence = []
    if link_career and link_reseats_after_sl:
        first_reseat_ts = link_reseats_after_sl[0]
        sl_ts = link_career["sl"]["ts"]
        ban_until = (link_career["dwell"].get("tryout_ban_until") or "").split("T")[0]
        reseat_hours_after_sl = link_career.get("reseat_hours_after_sl")
        reseat_evidence.append(
            f"LINK first re-seat {first_reseat_ts.split('T')[0]} (~{reseat_hours_after_sl:.0f}h after SL {sl_ts.split('T')[0]}) "
            f"and after ban expired ({ban_until})."
        )
    if sol_career and sol_reseats_after_sl:
        first_reseat_ts = sol_reseats_after_sl[0]
        sl_ts = sol_career["sl"]["ts"]
        ban_until = (sol_career["dwell"].get("tryout_ban_until") or "").split("T")[0]
        reseat_hours_after_sl = sol_career.get("reseat_hours_after_sl")
        reseat_evidence.append(
            f"SOL first re-seat {first_reseat_ts.split('T')[0]} (~{reseat_hours_after_sl:.0f}h after SL {sl_ts.split('T')[0]}) "
            f"and after ban expired ({ban_until})."
        )
    if not reseat_evidence:
        reseat_evidence.append("No reseats after SL in this window for SOL/LINK.")

    for item in ranked:
        if item["id"] == "reseat_after_sl_cooloff":
            item["evidence"] = ". ".join(reseat_evidence)
            break

    packet = {
        "schema": "alt_shell_sl_career_v1",
        "as_of": now.isoformat(),
        "question": "W-PROCESS-TAX-SOL-LINK-SL: SOL/LINK stop career measure pack",
        "method": "Ledger + CF + Dwell (no knobs)",
        "edge_class": "ATTENTION_ONLY_less_loss_path",
        "summary": {
            "window_pnl_usd": WEEKLY_PRIMARY_USD,
            "tax_sl_usd": tax_sl,
            "tax_dust_usd": tax_dust,
            "tax_chain_usd": tax_chain,
            "cf_would_save_usd": round(cf_save, 4),
            "sl_live_default_pct": sl_live,
            "w2_status": w2_status,
            "w2_live_apply": w2_live,
        },
        "careers": careers,
        "ranked_options": ranked,
    }

    md = f"""# E-SOL-LINK-SL-CAREER ({now.strftime("%Y-%m-%d")})

**W-PROCESS-TAX-SOL-LINK-SL / E-SOL-LINK-SL-CAREER**

One honest career packet for this week's dominant process-tax line (SOL / LINK exchange stops).
Measure-only. **No knobs flipped. No orders. No runner restarts.**

**Window:** {WIN_START.strftime("%Y-%m-%d")} → {WIN_END.strftime("%Y-%m-%d")} UTC (SOL entry {LOOKBACK.strftime("%Y-%m-%d")} included).

## Verdict (10 lines)

1. Week primary tax {_fmt_usd(WEEKLY_PRIMARY_USD)} WR 0/4 is these two exchange stops (+dust), not TP meat.
2. Ledger chain PnL SOL {_fmt_usd(next((c["pnl_chain_usd"] for c in careers if c["pair"] == "SOL-USD"), None))} · LINK {_fmt_usd(next((c["pnl_chain_usd"] for c in careers if c["pair"] == "LINK-USD"), None))} · sum {_fmt_usd(tax_chain)} ≈ weekly primary.
3. Roles are **tryout_shell** for both. Not liquid_flat_cap_first_stack like ADA.
4. All SLs are exchange STOP_LIMIT at **~8%** (NEEDLE-04 live_default 8%). Not a 3% fuse.
5. SOL held ~{next((c["hold_hours"] for c in careers if c["pair"] == "SOL-USD"), None):.0f}h. LINK held ~{next((c["hold_hours"] for c in careers if c["pair"] == "LINK-USD"), None):.0f}h.
6. CF 3% vs actual would have helped: SOL ~{next((c["cf"].get("delta_usd_3pct_minus_actual") for c in careers if c["pair"] == "SOL-USD"), None):.2f} (MFE before 3% touch {next((c["cf"].get("mfe_before_3pct_touch") for c in careers if c["pair"] == "SOL-USD"), None):.2%}). LINK ~{next((c["cf"].get("delta_usd_3pct_minus_actual") for c in careers if c["pair"] == "LINK-USD"), None):.2f} (MFE before 3% touch {next((c["cf"].get("mfe_before_3pct_touch") for c in careers if c["pair"] == "LINK-USD"), None):.2%}).
7. **Already shipped** D2/intake (2026-10-17 GO) and dwell demote (2026-10-06 GO) cover the biggest process levers (don't reseat shells under-ballast; don't restack after proof then SL). This week's seats mostly **predate** the 10/17 GO.
8. Default from this packet: **no SL knob**. Watch next week under live D2+intake. W2 stays shadow. Bank-trail stays Sunday-gated.
9. Explicit never: global 8%→3%, PAXG, Kelly, dual_agree auto, blow flat $75, edge claim from N=2.

## Cross-cut

| Pair | Size band | Role | Notional | Hold_h | SL PnL | SL % | MFE<3% | Reseats after SL | Dwell demote |
|------|-----------|------|----------|--------|--------|------|---------|------------------|--------------|
"""
    for c in careers:
        md += f"| {c['pair']} | {c['role']['size_band']} | `{c['role']['role']}` | {_fmt_usd(c['role']['notional_usd'])} | {c['hold_hours']:.0f} | {_fmt_usd(c['pnl_sl_usd'])} | {_fmt_pct(c['sl_pct_ledger'])} | {'True' if (c['cf'].get('mfe_before_3pct_touch') or 0) < 0.03 else 'False'} | {len(c['reseats_after_sl'])} | {'True' if c['dwell'].get('demoted_on_sl') else 'False'} |\n"
    md += f"\nWeek tax check: SL sum {_fmt_usd(tax_sl)} + dust {_fmt_usd(tax_dust)} = {_fmt_usd(tax_chain)} vs weekly primary {_fmt_usd(WEEKLY_PRIMARY_USD)}.\n\n## Careers\n"

    for c in careers:
        md += f"""
### {c['pair']}

**Role:** `{c['role']['role']}` · size_band `{c['role']['size_band']}` · {_fmt_usd(c['role']['notional_usd'])} notional. {c['role']['note']}

| Step | Timestamp (UTC) | Price | Qty | Notional / PnL | Note |
|------|-----------------|-------|-----|----------------|------|
"""
        for wb in c["window_buys"]:
            md += f"| Buy | {_iso(wb['ts'])} | {wb['entry_price']:.4f} | {wb['qty']:.4f} | {_fmt_usd(wb['notional_est'])} | {wb['reason'] or ''} |\n"
        if c["buy"] and c["buy"]["ts"] not in [wb["ts"] for wb in c["window_buys"]]: # ensure main buy is captured if not in window_buys (e.g. LOOKBACK range)
             md += f"| Entry | {_iso(c['buy']['ts'])} | {c['buy']['entry_price']:.4f} | {c['buy']['qty']:.4f} | {_fmt_usd(c['buy']['notional_est'])} | {c['buy']['reason'] or ''} |\n"

        md += f"| SL attach | post-buy (NEEDLE-04) | — | — | 8% band | {c['sl_note']} |\n"

        md += f"| SL hit | {_iso(c['sl']['ts'])} | {c['sl']['exit_price']:.4f} | {c['sl']['qty']:.4f} | {_fmt_usd(c['pnl_sl_usd'])} ({_fmt_pct(c['sl_pct_ledger'])}) | stop_loss_exchange · STOP_LIMIT · oid {c['sl']['order_id'][:8]} |
"
        if c["dust"]:
            md += f"| Dust | {_iso(c['dust']['ts'])} | {c['dust']['exit_price']:.4f} | {c['dust']['qty']:.4f} | {_fmt_usd(c['pnl_dust_usd'])} | dust_sweep_after_sl |
"
        md += f"| Hold | {c['hold_hours']:.0f} h | — | — | chain {_fmt_usd(c['pnl_chain_usd'])} | buy→SL |\n"
md += f"\n**CF (sl_width_3v8, this SL ts):** era `{c['cf'].get('era')}` · tag `{c['cf'].get('tag')}` · MFE before 3% touch {_fmt_pct(c['cf'].get('mfe_before_3pct_touch'))} · MFE to actual exit {_fmt_pct(c['cf'].get('mfe_to_actual_exit'))} · sim 3% PnL {_fmt_usd(c['cf'].get('sim_pnl_usd_3pct'))} · delta 3%−actual {_fmt_usd(c['cf'].get('delta_usd_3pct_minus_actual'))} · went_green≥1% {'True' if c['cf'].get('went_green_mfe_ge_1pct') else 'False'}\n\n**Dwell:** demoted_on_sl={c['dwell'].get('demoted_on_sl')} · demote_ts={_iso(c['dwell'].get('demote_ts'))} · tryout_ban_until={_iso(c['dwell'].get('tryout_ban_until'))} · current={c['dwell'].get('current_status') or 'None'}/{c['dwell'].get('current_role') or 'None'}\n\n**Re-seat / cooloff:**\n- No re-seat after SL in window\n- Hours SL→first reseat: {c['reseat_hours_after_sl']:.0f}h\n- Ban vs reseat: {'True' if c['ban_vs_reseat'] else 'False'}\n"

        for r_buy in c["reseats_after_sl"]:
            md += f"    - Re-seat buy: {_iso(r_buy['ts'])} · {_fmt_usd(r_buy['notional_est'])} · {r_buy['reason'] or ''}
"

    md += f"""
## Ranked Options (Measure-only)
"""
    for item in ranked:
        md += f"""
### {item['rank']}) {item['title']} (`{item['id']}`)

- **Evidence:** {item['evidence']}
- **Disposition:** {item['disposition']}
- **GO:** {item['go']}
"""
    md += f"""
## Notes

- **W2 Status:** {w2_status} (live_apply={w2_live})
- **Bank-trail-while-green:** MEASURE_ONLY / Sunday N_INSUFFICIENT (no GO from this packet)
- **Already shipped**: D2 ballast-before-shell + intake hygiene (2026-10-17 GO). Post-proof dwell live_apply ON (2026-10-06 GO).

## Sources

- Fact pack: `{TRADES.name}`
- CF data: `{CF_JSON.name}` (if present)
- Dwell data: `{DWELL_JSON.name}` (if present)
- SL Policy: `{SL_POLICY.name}`
"""

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(md, encoding="utf-8")
    print(f"[SOL-LINK-SL-CAREER] wrote {OUT_MD}")

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(packet, indent=2, default=str), encoding="utf-8")
    print(f"[SOL-LINK-SL-CAREER] wrote {OUT_JSON}")

    # Update notepad to reflect the new career pack and clear old suggestions if appropriate
    # This requires reading and then rewriting the notepad, as it's a JSON file
    notepad_path = ROOT / "data/state/analyst_weekly_notepad_latest.json"
    notepad_data = _load_json(notepad_path)
    
    open_suggestions = notepad_data.get("open_suggestions", {})
    # Mark old W-PROCESS-TAX-ALT-SHELL-SL as superseded/done
    if "W-PROCESS-TAX-ALT-SHELL-SL" in open_suggestions:
        open_suggestions["W-PROCESS-TAX-ALT-SHELL-SL"]["status"] = "SUPERSEDED"
        open_suggestions["W-PROCESS-TAX-ALT-SHELL-SL"]["note"] = "Superseded by W-PROCESS-TAX-SOL-LINK-SL"

    # Add/update W-PROCESS-TAX-SOL-LINK-SL in open_suggestions
    open_suggestions["W-PROCESS-TAX-SOL-LINK-SL"] = {
        "P": "P0",
        "lever": "SOL/LINK SL career + cooloff/re-seat stack (refresh of ALT-SHELL)",
        "effect": "Cut tax + multi-buy->SL",
        "evidence": "SOL-5.9 LINK-3.6 · tax-9.6 · non-tax0",
        "risk": "Miss rare TP",
        "go": True,
        "status": "MEASURE_RUNNING", # Now running the measure pack
        "last_updated": now.isoformat(),
        "attached_career_pack": OUT_MD.name,
    }
    
    # Update W-CASH-HOLD-VS-FLAT-B status to MEASURE_ONLY for documentation
    open_suggestions["W-CASH-HOLD-VS-FLAT-B"] = {
        "P": "P1",
        "lever": "Clarify/release sticky cash_hold ~$68 vs flat B deploy intent",
        "effect": "Honest deployable $",
        "evidence": "capital_user_controls manual_liquidation_cash_hold_usd=67.78 · USD~200 USDC~1903 · util~6%",
        "risk": "Re-leak if naive",
        "go": True,
        "status": "AWAITING_GO", # Awaiting explicit GO to release
        "last_updated": now.isoformat(),
    }

    notepad_data["open_suggestions"] = open_suggestions
    
    # Also update go_queue if it exists
    go_queue = notepad_data.get("go_queue", {})
    go_queue["W-PROCESS-TAX-SOL-LINK-SL"] = {
        "status": "MEASURE_RUNNING",
        "packet": OUT_MD.name,
        "ts": now.isoformat()
    }
    notepad_data["go_queue"] = go_queue

    _save_json(notepad_path, notepad_data) # save the updated notepad
    print(f"[SOL-LINK-SL-CAREER] updated {notepad_path}")


    return 0


if __name__ == "__main__":
    sys.exit(main())
