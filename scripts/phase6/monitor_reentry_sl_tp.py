#!/usr/bin/env python3
"""Monitor re-entries for SL attach + lot-bound TP peak hygiene.

Quiet when healthy (stdout empty → no_agent cron silent).
Prints ALERT lines when something violates expectations after a BUY.

Checks (per new BUY since cursor / lookback):
  1. SL attached on exchange (or ledger sl_attached true) within grace window
  2. SL stop price is BELOW entry (~2–6% for crypto long; not above mark/entry)
  3. peak_lot bound for held pair; peak_r not wildly above mark_r (stale peak)
  4. No LIVE-TP trail fire within minutes of BUY while mark_r < arm (stale-peak pattern)
  5. Cash hold not silently re-armed; LINK post-TP block still 24h-class

Usage:
  PYTHONPATH=. .venv/bin/python scripts/phase6/monitor_reentry_sl_tp.py
  PYTHONPATH=. .venv/bin/python scripts/phase6/monitor_reentry_sl_tp.py --lookback-hours 6
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

STATE = ROOT / "data" / "state"
LEDGER = ROOT / "trades" / "phase6_trades.jsonl"
CURSOR = STATE / "reentry_sl_tp_monitor_cursor.json"
OUT = STATE / "reentry_sl_tp_monitor_latest.json"
LOG = ROOT / "logs" / "phase6_runner.log"

# Trail arm default (exit_automation) — trail fire below this right after buy = bug smell
DEFAULT_ARM_PCT = 0.04
STALE_PEAK_GAP = 0.08  # peak_r - mark_r
FAST_TP_MINUTES = 10
SL_GRACE_MINUTES = 15


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    try:
        s = str(raw).strip().replace("Z", "+00:00")
        if " " in s and "T" not in s:
            s = s.replace(" ", "T", 1)
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _load_ledger_since(since: datetime) -> List[dict]:
    if not LEDGER.exists():
        return []
    out: List[dict] = []
    for line in LEDGER.read_text().splitlines():
        if not line.strip():
            continue
        try:
            t = json.loads(line)
        except json.JSONDecodeError:
            continue
        dt = _parse_ts(str(t.get("timestamp") or ""))
        if dt is None or dt < since:
            continue
        out.append(t)
    out.sort(key=lambda t: _parse_ts(str(t.get("timestamp") or "")) or datetime.min.replace(tzinfo=timezone.utc))
    return out


def _held_positions() -> Dict[str, Dict[str, float]]:
    """pair -> {qty, value_usd, entry_px?} from live state."""
    path = STATE / "phase6_live_state.json"
    if not path.exists():
        return {}
    try:
        live = json.loads(path.read_text())
    except Exception:
        return {}
    raw = live.get("positions") or live.get("active_positions") or {}
    if isinstance(raw, dict) and "positions" in raw:
        raw = raw.get("positions") or {}
    held: Dict[str, Dict[str, float]] = {}

    def _add(pair: str, usd: float, qty: float, entry: float) -> None:
        p = str(pair)
        if not p.endswith("-USD") and not p.endswith("-USDC"):
            p = f"{p}-USD"
        if usd >= 5.0 or qty > 0:
            held[p] = {"value_usd": usd, "qty": qty, "entry_px": entry}

    if isinstance(raw, list):
        for v in raw:
            if not isinstance(v, dict):
                continue
            pair = str(v.get("pair") or v.get("product_id") or "")
            if not pair:
                continue
            usd = float(v.get("value_usd") or v.get("notional_usd") or 0.0 or 0.0)
            qty = float(v.get("quantity") or v.get("qty") or v.get("size") or v.get("amount") or 0.0 or 0.0)
            entry = float(v.get("entry_price") or v.get("avg_entry") or v.get("entry_px") or 0.0 or 0.0)
            _add(pair, usd, qty, entry)
        return held

    if not isinstance(raw, dict):
        return held
    for k, v in raw.items():
        if isinstance(v, dict):
            usd = float(v.get("value_usd") or v.get("notional_usd") or 0.0 or 0.0)
            qty = float(v.get("quantity") or v.get("qty") or v.get("size") or v.get("amount") or 0.0 or 0.0)
            entry = float(v.get("entry_price") or v.get("avg_entry") or v.get("entry_px") or 0.0 or 0.0)
            _add(str(k), usd, qty, entry)
        else:
            _add(str(k), float(v or 0.0), 0.0, 0.0)
    return held


def _shadow_tp_status() -> dict:
    p = STATE / "shadow_tp_status.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _cash_hold() -> float:
    try:
        from phase6.core.capital_controls_api import get_capital_controls_status

        st = get_capital_controls_status("brad-primary")
        return float(st.get("manual_liquidation_cash_hold_usd") or 0.0)
    except Exception:
        rs = STATE / "phase6_runner_state.json"
        if rs.exists():
            try:
                return float(json.loads(rs.read_text()).get("manual_liquidation_cash_hold_usd") or 0.0)
            except Exception:
                return 0.0
        return 0.0


def _exchange_stops(pairs: List[str]) -> Dict[str, List[dict]]:
    if not pairs:
        return {}
    try:
        from phase6.core.config_loader import ConfigLoader
        from phase6.core.exchange_client import CoinbaseExchangeClient
        from phase6.core.stop_loss_manager import StopLossManager

        loader = ConfigLoader()
        client = CoinbaseExchangeClient(mode="live")
        slm = StopLossManager(client, loader._config, mode="live")
        return slm.detect_active_protective_orders(sorted(set(pairs))) or {}
    except Exception as exc:
        return {"__error__": [{"error": str(exc)[:200]}]}


def _recent_live_tp_from_log(since: datetime) -> List[Tuple[datetime, str, str]]:
    """Parse [LIVE-TP] lines from runner log."""
    if not LOG.exists():
        return []
    out: List[Tuple[datetime, str, str]] = []
    # log format: 2026-08-23 09:01:45,707 - phase6.shadow_tp - INFO - [LIVE-TP] UNI-USD trail ...
    try:
        # only last ~200KB
        data = LOG.read_bytes()
        if len(data) > 200_000:
            data = data[-200_000:]
        text = data.decode("utf-8", errors="replace")
    except Exception:
        return []
    for line in text.splitlines():
        if "[LIVE-TP]" not in line:
            continue
        try:
            ts_part = line.split(" - ", 1)[0].strip()
            # local log wall may be PT — treat as naive local; compare loosely via string date
            dt = datetime.strptime(ts_part[:19], "%Y-%m-%d %H:%M:%S")
            # assume America/Los_Angeles wall for this host
            try:
                from zoneinfo import ZoneInfo

                dt = dt.replace(tzinfo=ZoneInfo("America/Los_Angeles")).astimezone(timezone.utc)
            except Exception:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if dt < since - timedelta(hours=1):
            continue
        rest = line.split("[LIVE-TP]", 1)[-1].strip()
        bits = rest.split()
        pair = bits[0] if bits else "?"
        kind = bits[1] if len(bits) > 1 else "?"
        out.append((dt, pair, kind))
    return out


def evaluate(lookback_hours: float = 12.0) -> Dict[str, Any]:
    now = _utc_now()
    since = now - timedelta(hours=lookback_hours)
    cursor_ts = None
    if CURSOR.exists():
        try:
            cursor_ts = _parse_ts(json.loads(CURSOR.read_text()).get("last_ts") or "")
        except Exception:
            cursor_ts = None
    # Always scan lookback; cursor only for "new since last run" annotation
    trades = _load_ledger_since(since)
    buys = [t for t in trades if str(t.get("side") or "").upper() == "BUY"]
    sells = [t for t in trades if str(t.get("side") or "").upper() == "SELL"]

    held = _held_positions()
    st = _shadow_tp_status()
    peak_r = dict(st.get("peak_r") or {})
    peak_lot = dict(st.get("peak_lot") or {})
    marks = {m.get("pair"): m for m in (st.get("marks") or []) if isinstance(m, dict)}

    alerts: List[str] = []
    notes: List[str] = []

    hold = _cash_hold()
    if hold > 1.0:
        alerts.append(f"CASH_HOLD_REARMED ${hold:.2f} (expected 0 after operator release)")

    # Blocks snapshot
    try:
        from phase6.core.runner_capital_events import load_buy_block_status

        blocks = load_buy_block_status() or {}
    except Exception as exc:
        blocks = {}
        notes.append(f"buy_block_status_error={exc}")

    # LINK should be post_tp 24h if blocked; UNI/RAVE should NOT be blocked (waived)
    for p in ("UNI-USD", "RAVE-USD"):
        if p in blocks:
            alerts.append(f"BLOCK_SHOULD_BE_CLEAR {p} still blocked reason={blocks[p].get('reason')}")
    if "LINK-USD" in blocks:
        b = blocks["LINK-USD"]
        if b.get("reason") != "post_tp_rebuy_block" or float(b.get("block_hours") or 0) > 24.5:
            alerts.append(
                f"LINK_BLOCK_NOT_24H reason={b.get('reason')} block_hours={b.get('block_hours')}"
            )
        else:
            notes.append(
                f"LINK post-TP OK hours_left={b.get('hours_remaining')} exp={b.get('expires_at')}"
            )

    # Peak hygiene for currently held bags
    for pair, h in held.items():
        if pair.startswith("PAXG"):
            continue
        m = marks.get(pair) or {}
        mark_r = m.get("r")
        if mark_r is None and h.get("entry_px") and h.get("value_usd") and h.get("qty"):
            try:
                px = h["value_usd"] / h["qty"]
                mark_r = (px / h["entry_px"]) - 1.0
            except Exception:
                mark_r = None
        pr = peak_r.get(pair)
        pl = peak_lot.get(pair)
        if pair in held and h.get("value_usd", 0) >= 25 and pl is None and pr is not None:
            alerts.append(f"PEAK_LOT_UNBOUND {pair} peak_r={pr} (no peak_lot meta)")
        if pr is not None and mark_r is not None:
            gap = float(pr) - float(mark_r)
            if gap > STALE_PEAK_GAP and float(mark_r) < DEFAULT_ARM_PCT:
                alerts.append(
                    f"STALE_PEAK_SMELL {pair} peak_r={float(pr):.4f} mark_r={float(mark_r):.4f} gap={gap:.4f}"
                )

    # Pair exchange SL for held non-dust
    check_pairs = [p for p, h in held.items() if h.get("value_usd", 0) >= 25 and not p.startswith("PAXG")]
    stops = _exchange_stops(check_pairs) if check_pairs else {}
    if "__error__" in stops:
        notes.append(f"exchange_sl_check_error={stops['__error__'][0].get('error')}")
        stops = {}

    for pair in check_pairs:
        orders = stops.get(pair) or []
        entry = float((marks.get(pair) or {}).get("entry_px") or held[pair].get("entry_px") or 0.0)
        if not orders:
            alerts.append(f"SL_MISSING_EXCHANGE {pair} held_usd={held[pair].get('value_usd'):.2f}")
            continue
        # pick lowest stop for long
        stop_pxs = []
        for o in orders:
            try:
                stop_pxs.append(float(o.get("stop_price") or o.get("price") or 0))
            except (TypeError, ValueError):
                pass
        stop_pxs = [s for s in stop_pxs if s > 0]
        if not stop_pxs:
            alerts.append(f"SL_NO_PRICE {pair} orders={len(orders)}")
            continue
        sp = min(stop_pxs)
        if entry > 0 and sp >= entry * 0.995:
            alerts.append(
                f"SL_ABOVE_OR_AT_ENTRY {pair} stop={sp:.6g} entry={entry:.6g} (stale anchor?)"
            )
        elif entry > 0:
            dd = (sp / entry) - 1.0
            # expect roughly -1.5% to -6% band for adaptive SL
            if dd > -0.01:
                alerts.append(f"SL_TOO_TIGHT_OR_WRONG {pair} stop={sp:.6g} entry={entry:.6g} dd={dd:.3%}")
            elif dd < -0.12:
                notes.append(f"SL_WIDE {pair} stop={sp:.6g} entry={entry:.6g} dd={dd:.3%} (check preserve/ratchet)")
            else:
                notes.append(f"SL_OK {pair} stop={sp:.6g} entry={entry:.6g} dd={dd:.3%}")

    # Ignore pre-fix incident noise (UNI stale peak + TP-as-manual disposition).
    # Monitor is for re-entries AFTER operator release / lot-bind fix.
    FIX_FLOOR = datetime(2026, 8, 23, 17, 50, 0, tzinfo=timezone.utc)

    # New buys: SL attach flag + fast TP
    live_tps = _recent_live_tp_from_log(max(since, FIX_FLOOR - timedelta(hours=1)))
    for b in buys:
        pair = str(b.get("pair") or "")
        bdt = _parse_ts(str(b.get("timestamp") or ""))
        if not pair or bdt is None:
            continue
        if bdt < FIX_FLOOR:
            continue  # historical; already handled
        age_m = (now - bdt).total_seconds() / 60.0
        sl_ok = b.get("sl_attached") is True
        if b.get("sl_attached") is False and age_m >= SL_GRACE_MINUTES:
            # confirm exchange
            ex = (_exchange_stops([pair]) or {}).get(pair) or []
            if not ex:
                alerts.append(
                    f"BUY_NO_SL {pair} age_min={age_m:.1f} ts={b.get('timestamp')} order={str(b.get('order_id') or '')[:10]}"
                )
            else:
                notes.append(f"BUY_SL_EXCHANGE_OK ledger_false {pair}")
        elif sl_ok:
            notes.append(f"BUY_SL_LEDGER_OK {pair} ts={b.get('timestamp')}")

        # Fast TP after buy while likely not armed
        for tdt, tpair, kind in live_tps:
            if tpair != pair:
                continue
            if tdt < FIX_FLOOR:
                continue
            delta_m = (tdt - bdt).total_seconds() / 60.0
            if 0 <= delta_m <= FAST_TP_MINUTES:
                alerts.append(
                    f"FAST_TP_AFTER_BUY {pair} kind={kind} delta_min={delta_m:.1f} buy_ts={b.get('timestamp')} "
                    f"(stale peak / misfire pattern)"
                )

    # Disposition mis-tag: capital event manual on TP pairs (post-fix only)
    ce = STATE / "capital_events_runner.jsonl"
    if ce.exists():
        try:
            lines = ce.read_text().splitlines()[-30:]
            for ln in lines:
                try:
                    ev = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                edt = _parse_ts(str(ev.get("ts") or ""))
                if edt is None or edt < max(since, FIX_FLOOR):
                    continue
                if ev.get("event_type") != "manual_liquidation_to_cash":
                    continue
                manual = ev.get("pairs_manual_intent") or []
                tp = ev.get("pairs_take_profit") or []
                for p in manual:
                    for s in sells:
                        if s.get("pair") != p:
                            continue
                        sdt = _parse_ts(str(s.get("timestamp") or ""))
                        if sdt is None:
                            continue
                        if abs((sdt - edt).total_seconds()) > 600:
                            continue
                        reason = str(s.get("reason") or s.get("exit_reason") or "").lower()
                        if "take_profit" in reason:
                            alerts.append(
                                f"DISPOSITION_TP_AS_MANUAL {p} event_ts={ev.get('ts')} "
                                f"action={ev.get('action')} (should be take_profit_no_cash_hold)"
                            )
                if tp and ev.get("action") == "take_profit_no_cash_hold":
                    notes.append(f"DISPOSITION_TP_OK {tp} ts={ev.get('ts')}")
        except Exception as exc:
            notes.append(f"capital_events_scan_error={exc}")

    result = {
        "ts": now.isoformat(),
        "lookback_hours": lookback_hours,
        "held_pairs": sorted(held.keys()),
        "held_usd": {k: round(v.get("value_usd", 0), 2) for k, v in held.items()},
        "cash_hold_usd": hold,
        "blocks": {k: {"reason": v.get("reason"), "hours_remaining": v.get("hours_remaining")} for k, v in blocks.items()},
        "buys_in_window": len(buys),
        "alerts": alerts,
        "notes": notes[:40],
        "peak_r": peak_r,
        "peak_lot_pairs": sorted(peak_lot.keys()),
        "ok": len(alerts) == 0,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    # advance cursor to newest trade ts
    newest = None
    for t in trades:
        dt = _parse_ts(str(t.get("timestamp") or ""))
        if dt and (newest is None or dt > newest):
            newest = dt
    CURSOR.write_text(
        json.dumps({"last_ts": (newest or now).isoformat(), "updated_at": now.isoformat()}, indent=2)
        + "\n"
    )
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lookback-hours", type=float, default=12.0)
    ap.add_argument("--json", action="store_true", help="Always print full JSON")
    args = ap.parse_args()
    result = evaluate(lookback_hours=args.lookback_hours)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1
    # no_agent quiet when healthy
    if result.get("ok"):
        return 0
    print(f"REENTRY_SL_TP_ALERT n={len(result['alerts'])} ts={result['ts']}")
    for a in result["alerts"]:
        print(f"  ALERT: {a}")
    for n in (result.get("notes") or [])[:8]:
        print(f"  note: {n}")
    print(f"  detail: {OUT}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
