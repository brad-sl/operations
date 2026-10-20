#!/usr/bin/env python3
"""Rebuild E-ALT-SHELL-SL-CAREER from ledger + optional CF + dwell.

One-call measure script. No orders, no config changes, no live_apply flips.

Reads:
  trades/phase6_trades.jsonl
  data/state/sl_width_3v8_cf_latest.json (if present)
  data/state/post_proof_dwell.json (if present)
  config/sl_width_arming_policy.json (if present)

Writes:
  reports/E_ALT_SHELL_SL_CAREER_2026-10-19.md
  data/state/e_alt_shell_sl_career_latest.json

Window: weekly 2026-10-12 → 2026-10-19 UTC, plus TIA entry 10-11 and LINK
re-seat chain. Pairs: ADA-USD, TIA-USD, LINK-USD exchange stops.
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
OUT_MD = ROOT / "reports" / "E_ALT_SHELL_SL_CAREER_2026-10-19.md"
OUT_JSON = ROOT / "data" / "state" / "e_alt_shell_sl_career_latest.json"

PAIRS = ("ADA-USD", "TIA-USD", "LINK-USD")
WIN_START = datetime(2026, 10, 12, tzinfo=timezone.utc)
WIN_END = datetime(2026, 10, 19, tzinfo=timezone.utc)
LOOKBACK = datetime(2026, 10, 11, tzinfo=timezone.utc)
WEEKLY_PRIMARY_USD = -12.03


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

    if pair == "ADA-USD":
        role = "liquid_flat_cap_first_stack"
        note = (
            f"~${notion_s} notional at flat B cap $75; tryout_lot {action or 'absent'}; "
            "NOT $25 tryout shell. order_executor_buy, RSI-oversold + sentiment."
        )
    elif pair == "TIA-USD":
        paper_s = lot_inner.get("paper_scaled")
        live_s = lot_inner.get("live_scaled")
        note = (
            f"~${notion_s} notional (~2×$25 step). paper_scaled="
            f"{paper_s} live_scaled={live_s}; "
            "post-proof graduated then re-seated; sentiment-led."
        )
        role = "tryout_shell_paper_kindled"
    elif pair == "LINK-USD":
        role = "tryout_shell"
        note = (
            f"~${notion_s} notional limit_first_buy; tryout_lot {action or 'absent'}; "
            "classic ≤$30 unproven shell."
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
    print("[ALT-SHELL-SL-CAREER] loading ledger...")
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
            return 1
        sl = sls[0]
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

        sl_kind = "exchange_stop_limit_8pct"
        if sl.get("order_type") == "STOP_LIMIT" or "stop_loss_exchange" in _reason(sl):
            sl_kind = "exchange STOP_LIMIT ~8% (NEEDLE-04 live_default)"
        if buy and buy.get("sl_attached") is False:
            sl_note = "buy stamp sl_attached=false (naked at fill); SL later realized as exchange STOP_LIMIT"
        else:
            sl_note = "SL attach at buy unknown; exit is exchange stop"

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
            "window_buys": [
                _compact_trade(b)
                for b in buys
                if (lambda t: t is not None and LOOKBACK <= t < WIN_END)(_parse_ts(b.get("timestamp")))
            ],
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
                "then second ~$25 lot 2026-10-17T04:01. TIA did not re-seat after SL. ADA did not re-seat."
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
            "id": "role_missize_ada_flat_cap",
            "title": "Role mis-size: ADA $75 liquid first-stack vs $25 tryout shell",
            "evidence": (
                "ADA notional ~$75 (flat B cap), tryout_lot noop_absent, order_executor_buy. "
                "SL −$5.89 is the week's largest tax line because size was cap-full on an unproven alt "
                "while ETH$0 / BTC~$53."
            ),
            "disposition": "ALREADY_LIVE",
            "go": (
                "D2 flat_deploy_priority live_apply=true (reserve_before_shell). "
                "C2 ballast floor live. Do not re-implement. Do not blow cap $75."
            ),
        },
        {
            "rank": 3,
            "id": "tia_post_proof_then_sl",
            "title": "TIA post-proof dwell then re-seat then SL demote",
            "evidence": (
                "TIA TP-trail proofs Oct 6 (+$0.64) and Oct 8 (+$0.59), graduated, re-seated Oct 11 ~$50 "
                "(paper_scaled=true, live_scaled=false), SL Oct 12 −$4.01, demote-on-SL + 72h tryout ban. "
                "No post-SL reseat in window."
            ),
            "disposition": "ALREADY_LIVE",
            "go": "post_proof_dwell live_apply already ON (GO 2026-10-06). Do not touch dwell knobs.",
        },
        {
            "rank": 4,
            "id": "w2_3pct_fuse_dead_shells",
            "title": "3% fuse on unproven shells that never printed ≥+2% MFE (W2 class)",
            "evidence": (
                f"CF tags all three week SLs 3pct_helped_dead_path. Numeric 3% vs actual ≈ +${cf_save:.2f} "
                "(ADA ~+$3.46, TIA ~+$2.38, LINK ~+$1.16). MFE before 3% touch: ADA +0.57%, TIA +0.71%, "
                "LINK +0.94% — none ≥+2%. TIA later printed +3.47% MFE-to-exit (would have been cut by 3%). "
                "Thin N=3. Not an edge claim."
            ),
            "disposition": "GO_LATER_AFTER_SHADOW",
            "go": (
                "W2 already WIRED_SHADOW_PENDING_14D live_apply=false (started ~2026-10-13). "
                "This packet supports the *class*, not a live_apply flip. Never global 0.08→0.03."
            ),
        },
        {
            "rank": 5,
            "id": "bank_trail_while_green",
            "title": "Bank/trail vs wide SL on green-then-die",
            "evidence": (
                "None of the three printed ≥+2% MFE before a 3% fuse would cut. TIA had modest later green "
                "(+3.47% MFE-to-exit) then died to 8%. ETH prior-week career is the green-then-die ballast case "
                "(do not mix). Bank-trail-while-green remains MEASURE_ONLY / Sunday N_INSUFFICIENT."
            ),
            "disposition": "MEASURE_ONLY",
            "go": "Do not GO bank-trail from this packet. Keep Sunday gate. Prefer already-live trail+dwell.",
        },
        {
            "rank": 6,
            "id": "door_quality_intake",
            "title": "Door quality / intake hygiene",
            "evidence": (
                "ADA RSI 23.16 + sentiment 0.96 (not sentiment-only). TIA sentiment-only. "
                "LINK Oct 12 RSI 53.64 / sent 0.043 (weak sent, limit_first). "
                "Intake bars raised Brad GO 2026-10-17 (eng≥0.40 / setup≥1.7 / conf≥0.60) after these seats."
            ),
            "disposition": "ALREADY_LIVE",
            "go": "Do not re-implement tryout_decision_discipline. Watch next week under raised bars + D2.",
        },
    ]

    never = [
        "global stop_loss_pct 0.08 → 0.03",
        "PAXG preserve / scale_path",
        "Kelly / deploy_pct promote",
        "dual_agree auto-promote",
        "blow flat cap $75",
        "live_apply flips in this card",
        "edge/promote claim from N=3",
        "re-implement C2/D2/intake/dwell",
    ]

    already_shipped = [
        "C2 ballast_under_target_floor live_apply=true (2026-10-17)",
        "D2 flat_deploy_priority live_apply=true reserve_before_shell (2026-10-17)",
        "tryout_decision_discipline intake bars raised + live_apply (2026-10-17)",
        "post_proof_dwell live_apply ON + demote on_sl (GO 2026-10-06)",
        "tryout_scale_window live + 24h post-eject cooloff (not the SL path)",
        "E-ETH-BALLAST-SL-CAREER 2026-10-12 (no SL knob)",
        "W2 3% shell fuse wired shadow, live_apply=false",
        "bank-trail-while-green MEASURE_ONLY",
    ]

    go_later = [
        "W2 live_apply only after 14d shadow gate + Brad letter GO — not from this packet",
        "If next week still reseats LINK/ADA after D2+intake, measure an extended post-SL pair cooloff",
        "Bank-trail-while-green only via Sunday gate, not this RCA",
    ]

    # Build MD
    def _career_md(c: dict[str, Any]) -> str:
        b = c["buy"] or {}
        s = c["sl"]
        d = c["dust"] or {}
        role = c["role"]
        cf_ = c["cf"]
        mfe3 = cf_.get("mfe_before_3pct_touch")
        mfe3s = f"{mfe3*100:.2f}%" if isinstance(mfe3, (int, float)) else "unknown"
        mfe_x = cf_.get("mfe_to_actual_exit")
        mfe_xs = f"{mfe_x*100:.2f}%" if isinstance(mfe_x, (int, float)) else "unknown"
        reseat_lines = []
        for r in c["reseats_after_sl"]:
            reseat_lines.append(
                f"- Re-seat BUY {r.get('ts')} qty {r.get('qty')} entry {r.get('entry_price')} "
                f"notional ~${r.get('notional_est')} reason {r.get('reason') or r.get('signal_source')} "
                f"oid {r.get('order_id')}"
            )
        if not reseat_lines:
            reseat_lines = ["- No re-seat after SL in window"]
        ban = c.get("ban_vs_reseat") or {}
        ban_line = "n/a (no reseat)"
        if ban:
            ban_line = (
                f"ban until {ban.get('tryout_ban_until')}; first reseat {ban.get('first_reseat_ts')}; "
                f"hours after ban {ban.get('hours_after_ban')}; expired={ban.get('reseated_after_ban_expired')}"
            )
        sim3 = cf_.get("sim_pnl_usd_3pct")
        dlt = cf_.get("delta_usd_3pct_minus_actual")
        return f"""### {c['pair']}

**Role:** `{role['role']}` · size_band `{role['size_band']}` · {role['note']}

| Step | Timestamp (UTC) | Price | Qty | Notional / PnL | Note |
|------|-----------------|-------|-----|----------------|------|
| Entry | {b.get('ts') or 'unknown'} | {b.get('entry_price')} | {b.get('qty')} | ~${b.get('notional_est')} | {b.get('reason') or b.get('signal_source') or 'unknown'} · rsi {b.get('entry_rsi')} sent {b.get('entry_sentiment')} |
| SL attach | post-buy (NEEDLE-04) | — | — | 8% band | {c['sl_note']} |
| SL hit | {s.get('ts')} | {s.get('exit_price')} | {s.get('qty')} | {_fmt_usd(c['pnl_sl_usd'])} ({_fmt_pct(c['sl_pct_ledger'])}) | {s.get('reason')} · {s.get('order_type')} · oid {s.get('order_id')} |
| Dust | {d.get('ts') or 'none'} | {d.get('exit_price') or '—'} | {d.get('qty') or '—'} | {_fmt_usd(c['pnl_dust_usd']) if d else '$0'} | {d.get('reason') or 'none'} |
| Hold | {c['hold_hours']} h | — | — | chain {_fmt_usd(c['pnl_chain_usd'])} | buy→SL |

**CF (sl_width_3v8, this SL ts):** era `{cf_.get('era')}` · tag `{cf_.get('tag')}` · MFE before 3% touch {mfe3s} · MFE to actual exit {mfe_xs} · sim 3% PnL {sim3} · delta 3%−actual {dlt} · went_green≥1% {cf_.get('went_green_mfe_ge_1pct')}

**Dwell:** demoted_on_sl={c['dwell']['demoted_on_sl']} · demote_ts={c['dwell']['demote_ts']} · tryout_ban_until={c['dwell']['tryout_ban_until']} · current={c['dwell']['current_status']}/{c['dwell']['current_role']}

**Re-seat / cooloff:**
{chr(10).join(reseat_lines)}
- Hours SL→first reseat: {c['reseat_hours_after_sl']}
- Ban vs reseat: {ban_line}

Ledger oids: buy `{b.get('order_id')}` · SL `{s.get('order_id')}` · bag `{s.get('bag_id') or b.get('bag_id')}`
"""

    cross_rows = []
    for c in careers:
        r = c["role"]
        cf_ = c["cf"]
        mfe3 = cf_.get("mfe_before_3pct_touch")
        mfe3s = f"{mfe3*100:.2f}%" if isinstance(mfe3, (int, float)) else "unknown"
        cross_rows.append(
            f"| {c['pair']} | {r['size_band']} | `{r['role']}` | ~${r['notional_usd']:.0f} | "
            f"{c['hold_hours']} | {_fmt_usd(c['pnl_sl_usd'])} | {_fmt_pct(c['sl_pct_ledger'])} | "
            f"{mfe3s} | {len(c['reseats_after_sl'])} | {c['dwell']['demoted_on_sl']} |"
        )

    ranked_md = []
    for item in ranked:
        ranked_md.append(
            f"**{item['rank']}. {item['title']}** — `{item['disposition']}`\n"
            f"- Evidence: {item['evidence']}\n"
            f"- {item['go']}\n"
        )

    md = f"""# E-ALT-SHELL-SL-CAREER (2026-10-19)

**W-PROCESS-TAX-ALT-SHELL-SL / E-ALT-SHELL-SL-CAREER**

One honest career packet for this week's dominant process-tax line (ADA / TIA / LINK exchange stops).
Measure-only. **No knobs flipped. No orders. No runner restarts.**

**Window:** 2026-10-12 → 2026-10-19 UTC (TIA entry 2026-10-11 and LINK re-seat chain included).

## Verdict (10 lines)

1. Week primary tax {_fmt_usd(WEEKLY_PRIMARY_USD)} WR 0/6 is these three exchange stops (+dust), not TP meat.
2. Ledger chain PnL ADA {_fmt_usd(careers[0]['pnl_chain_usd'])} · TIA {_fmt_usd(careers[1]['pnl_chain_usd'])} · LINK {_fmt_usd(careers[2]['pnl_chain_usd'])} · sum {_fmt_usd(tax_chain)} (SL { _fmt_usd(tax_sl) } + dust {_fmt_usd(tax_dust)} ) ≈ weekly primary.
3. Roles are **not the same**: ADA = liquid flat-cap first stack ~$75; TIA = paper-kindled tryout ~$50 after TP proofs; LINK = $25 tryout shell.
4. All three SLs are exchange STOP_LIMIT at **~8%** (NEEDLE-04 live_default {sl_live*100:.0f}%). Not a 3% fuse. Buy stamps on ADA/TIA showed `sl_attached=false` (naked at fill); stop still filled later as exchange SL.
5. LINK is the re-seat leak: same-day buy→SL Oct 12, dwell demote 72h ban, then two ~$25 buys Oct 16 (ban just expired) + Oct 17.
6. TIA demote-on-SL fired correctly; no post-SL reseat. ADA never tryout-lot; no demote; no reseat.
7. CF 3% vs actual would have lost ~${cf_save:.2f} less on these three (dead-path tags) but MFE before 3% touch was &lt;1% on all three — W2 *class*, not a live GO. TIA later printed +3.5% MFE-to-exit (3% would have cut a path that went green).
8. **Already shipped** C2/D2/intake (2026-10-17) and dwell demote (2026-10-06) cover the two biggest process levers (don't reseat shells under-ballast; don't restack after proof then SL). This week's seats mostly **predate** the 10/17 GO.
9. Default from this packet: **no SL knob**. Watch next week under live D2+intake. W2 stays shadow. Bank-trail stays Sunday-gated.
10. Explicit never: global 8%→3%, PAXG, Kelly, dual_agree auto, blow flat $75, edge claim from N=3.

## Cross-cut

| Pair | Size band | Role | Notional | Hold_h | SL PnL | SL % | MFE&lt;3% | Reseats after SL | Dwell demote |
|------|-----------|------|----------|--------|--------|------|---------|------------------|--------------|
{chr(10).join(cross_rows)}

Week tax check: SL sum {_fmt_usd(tax_sl)} + dust {_fmt_usd(tax_dust)} = {_fmt_usd(tax_chain)} vs weekly primary {_fmt_usd(WEEKLY_PRIMARY_USD)}.

## Careers

{_career_md(careers[0])}
{_career_md(careers[1])}
{_career_md(careers[2])}

## LINK re-seat chain (cooloff / intake facts)

1. 2026-10-11 02:16 limit_first ~$25 then 04:46 **scale-window eject** −$0.34 (prior-day, not this week's primary tax).
2. 2026-10-12 05:31 limit_first ~$25 → 16:02 exchange SL −$1.96 (~10.5h, same calendar day). Dust orphan 10-13 00:53 −$0.04.
3. Dwell demote `sl_exit` 2026-10-13T00:52 · `tryout_ban_until` 2026-10-16T00:52 (72h, matches config `demote.post_sl_cooloff_hours=72`).
4. 2026-10-16 04:02 limit_first ~$25 — **~3.2h after ban expired** (not a ban breach; an immediate re-seat at expiry).
5. 2026-10-17 04:01 order_executor_buy ~$25, `sl_attached=false` at stamp — second lot (book later shows LINK ~$48).
6. Scale-window post-eject cooloff is 24h and applies to **eject**, not SL. SL path uses dwell 72h ban. Intake hygiene + D2 went live **later the same day** as the second reseat (2026-10-17 GO ~23:38). Honest read: this leak is **pre-GO residual**, not proof that live D2/intake failed.

## Optimize returns / reduce losses (ranked)

{chr(10).join(ranked_md)}

## GO / already-live / NO-GO

### Already shipped (do not duplicate)

{chr(10).join('- ' + x for x in already_shipped)}

### What Brad could GO later (not this card)

{chr(10).join('- ' + x for x in go_later)}

### Never from this packet

{chr(10).join('- ' + x for x in never)}

### Default GO

**no SL knob · no live_apply flips · CAREER_DONE measure**

Watch one more week under already-live D2 + intake. If LINK/ADA still reseat after SL while ETH$0, then a **new** measure card on post-SL cooloff length — still not a global 8→3.

## Attachments

- W-PROCESS-TAX-ALT-SHELL-SL
- E-ALT-SHELL-SL-CAREER
- Weekly: reports/ANALYST_WEEKLY_TRADE_REVIEW_AGENT_LATEST.md
- ETH context (not this week's $): reports/E_ETH_BALLAST_SL_CAREER_2026-10-12.md
- CF: data/state/sl_width_3v8_cf_latest.json
- Dwell: data/state/post_proof_dwell.json
- Verify-close (C2/D2/intake already LIVE): reports/WEEKLY_SUGGESTIONS_VERIFY_CLOSE_2026-10-19.md

## Data artifact

See `data/state/e_alt_shell_sl_career_latest.json` (rebuilt by this script).

## Notepad (measure notes)

- open_suggestions: W-PROCESS-TAX-ALT-SHELL-SL → **CAREER_DONE** (this packet); other weekly IDs already LIVE/CAREER_DONE per verify-close.
- go_queue: nothing new from this RCA. Do not enqueue global SL, PAXG, Kelly, dual_agree, cap $75.

---
Script: scripts/phase6/run_alt_shell_sl_career.py (one-call rebuild)
Run: {now.isoformat()}
No live orders touched. No config mutated.
"""

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(md, encoding="utf-8")
    print(f"[ALT-SHELL-SL-CAREER] wrote {OUT_MD}")

    packet = {
        "schema": "alt_shell_sl_career_v1",
        "as_of": now.isoformat(),
        "attach": ["W-PROCESS-TAX-ALT-SHELL-SL", "E-ALT-SHELL-SL-CAREER"],
        "measure_only": True,
        "no_knobs": True,
        "window": {"start": WIN_START.isoformat(), "end": WIN_END.isoformat(), "lookback": LOOKBACK.isoformat()},
        "weekly_primary_usd": WEEKLY_PRIMARY_USD,
        "tax": {
            "sl_usd": tax_sl,
            "dust_usd": tax_dust,
            "chain_usd": tax_chain,
            "vs_weekly_primary_usd": round(tax_chain - WEEKLY_PRIMARY_USD, 4),
        },
        "sl_live_pct": sl_live,
        "w2_status": w2_status,
        "w2_live_apply": w2_live,
        "cf_numeric_save_if_3pct_usd": round(cf_save, 4),
        "careers": careers,
        "ranked_options": ranked,
        "already_shipped": already_shipped,
        "go_later": go_later,
        "never": never,
        "default_go": "no SL knob",
        "notepad": {
            "open_suggestions": "W-PROCESS-TAX-ALT-SHELL-SL CAREER_DONE measure; others LIVE per verify-close",
            "go_queue": "nothing new from this RCA",
        },
        "source_ledger": str(TRADES),
        "source_cf": str(CF_JSON) if CF_JSON.exists() else None,
        "source_dwell": str(DWELL_JSON) if DWELL_JSON.exists() else None,
        "knobs_flipped": False,
        "orders_placed": False,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(packet, indent=2, default=str), encoding="utf-8")
    print(f"[ALT-SHELL-SL-CAREER] wrote {OUT_JSON}")

    print("\n=== career conclusion ===")
    print(f"1. ADA/TIA/LINK chain tax {tax_chain} vs weekly {WEEKLY_PRIMARY_USD}")
    for c in careers:
        print(
            f"   {c['pair']}: role={c['role']['role']} hold={c['hold_hours']}h "
            f"sl={c['pnl_sl_usd']} reseats={len(c['reseats_after_sl'])} demote={c['dwell']['demoted_on_sl']}"
        )
    print("8. default_go=no SL knob; W2 shadow; D2/intake already live")
    print("9. never global 0.08→0.03")
    print("10. no knobs / no orders")
    return 0


if __name__ == "__main__":
    sys.exit(main())
