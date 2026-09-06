#!/usr/bin/env python3
"""Monitor re-entries for SL attach + lot-bound TP peak hygiene.

Quiet when healthy (stdout empty → no_agent cron silent).
Prints ALERT lines when something violates expectations after a BUY.

Checks (per new BUY since cursor / lookback):
  1. SL attached on exchange (or ledger sl_attached true) within grace window
  2. SL stop price is BELOW entry (~2–6% for crypto long; not above mark/entry)
  3. peak_lot bound for held pair; peak_r not wildly above mark_r (stale peak)
  4. No LIVE-TP trail fire within minutes of BUY while mark_r < arm (stale-peak pattern)
  5. Cash hold: page only on NEW/increased arm (sticky same-$ is silent note)
  6. Live dual-peak/extension failures: page once per fingerprint (6h dedupe)

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
ALERT_SEEN = STATE / "reentry_sl_tp_monitor_alert_seen.json"
LOG = ROOT / "logs" / "phase6_runner.log"

# Trail arm default (exit_automation) — trail fire below this right after buy = bug smell
DEFAULT_ARM_PCT = 0.04
STALE_PEAK_GAP = 0.08  # peak_r - mark_r
FAST_TP_MINUTES = 10
SL_GRACE_MINUTES = 15
# Sticky cash hold is normal policy after disposition; only page on NEW/increased arm.
CASH_HOLD_ALERT_EPS_USD = 1.0
# Live dual-peak / extension failures: page once per fingerprint, then quiet.
LIVE_EXIT_FAIL_DEDUPE_HOURS = 6.0
# CR-03 suspend/reattach leaves bags briefly naked (~10–30s). Monitor is */10 and
# collides with 09:00/21:00 PT rebalance → daily SL_MISSING_EXCHANGE false pages.
# Suppress page when suspend is in-flight or inventory is stop-locked on venue.
CR03_SUSPEND_GRACE_SEC = 180.0
CR03_SCHEDULE_GRACE_SEC = 120.0  # ± around 09:00/09:06 and 21:00/21:06 PT
HOLD_LOCKED_FRAC_MIN = 0.90  # hold/amount ≥ this ⇒ exchange stop is locking size


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


def _load_alert_seen() -> Dict[str, Any]:
    if not ALERT_SEEN.exists():
        return {}
    try:
        data = json.loads(ALERT_SEEN.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_alert_seen(data: Dict[str, Any]) -> None:
    ALERT_SEEN.parent.mkdir(parents=True, exist_ok=True)
    ALERT_SEEN.write_text(json.dumps(data, indent=2) + "\n")


def _should_page_cash_hold(hold: float, seen: Dict[str, Any]) -> Tuple[bool, str]:
    """Return (page?, note_or_alert_text). Sticky same-hold is silent note only."""
    prev = float(seen.get("cash_hold_usd") or 0.0)
    if hold <= CASH_HOLD_ALERT_EPS_USD:
        return False, ""
    # New arm or material increase → one page; otherwise sticky policy note.
    if hold > prev + CASH_HOLD_ALERT_EPS_USD:
        return True, (
            f"CASH_HOLD_ARMED ${hold:.2f} (was ${prev:.2f}; deploy blocked until Release)"
        )
    return False, (
        f"CASH_HOLD_ACTIVE ${hold:.2f} (sticky policy after disposition — silent unless $ rises)"
    )


def _should_page_fingerprint(key: str, seen: Dict[str, Any], hours: float) -> bool:
    raw = seen.get("fingerprints") or {}
    if not isinstance(raw, dict):
        raw = {}
    last = _parse_ts(str(raw.get(key) or ""))
    now = _utc_now()
    if last is not None and (now - last).total_seconds() < hours * 3600.0:
        return False
    raw[key] = now.isoformat()
    # prune old
    keep: Dict[str, str] = {}
    for k, v in raw.items():
        dt = _parse_ts(str(v))
        if dt is None or (now - dt).total_seconds() < max(hours, 24.0) * 3600.0 * 7:
            keep[k] = str(v)
    seen["fingerprints"] = keep
    return True


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


def _log_wall_to_utc(ts_part: str) -> Optional[datetime]:
    """Parse runner log wall clock (America/Los_Angeles on this host) → UTC."""
    try:
        dt = datetime.strptime(ts_part[:19], "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None
    try:
        from zoneinfo import ZoneInfo

        return dt.replace(tzinfo=ZoneInfo("America/Los_Angeles")).astimezone(timezone.utc)
    except Exception:
        return dt.replace(tzinfo=timezone.utc)


def _cr03_schedule_near(now: datetime, grace_sec: float = CR03_SCHEDULE_GRACE_SEC) -> bool:
    """True near daily CR-03 rebalance slots (09:00/09:06 and 21:00/21:06 PT)."""
    try:
        from zoneinfo import ZoneInfo

        local = now.astimezone(ZoneInfo("America/Los_Angeles"))
    except Exception:
        local = now
    slots = ((9, 0), (9, 6), (21, 0), (21, 6))
    for hh, mm in slots:
        slot = local.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if abs((local - slot).total_seconds()) <= grace_sec:
            return True
    return False


def _cr03_suspend_in_flight(
    now: datetime,
    log_path: Path = LOG,
    grace_sec: float = CR03_SUSPEND_GRACE_SEC,
    log_tail_bytes: int = 250_000,
) -> Tuple[bool, str]:
    """Detect open CR-03 suspend window from runner log.

    Entered suspend without a later Re-attached (or still within grace of Entered)
    ⇒ bags may be intentionally naked. Returns (active, reason).
    """
    if not log_path.exists():
        return False, ""
    try:
        data = log_path.read_bytes()
        if len(data) > log_tail_bytes:
            data = data[-log_tail_bytes:]
        text = data.decode("utf-8", errors="replace")
    except Exception:
        return False, ""

    last_enter: Optional[datetime] = None
    last_reattach: Optional[datetime] = None
    for line in text.splitlines():
        if "Entered suspend_reattach_context" in line:
            ts = _log_wall_to_utc(line.split(" - ", 1)[0].strip())
            if ts is not None:
                last_enter = ts
        elif "[CR-03] Re-attached stops" in line or "Restoration re-attach" in line:
            ts = _log_wall_to_utc(line.split(" - ", 1)[0].strip())
            if ts is not None:
                last_reattach = ts

    if last_enter is None:
        return False, ""
    age = (now - last_enter).total_seconds()
    if age < 0 or age > grace_sec:
        return False, ""
    if last_reattach is None or last_reattach < last_enter:
        return True, f"suspend_open age_s={age:.0f}"
    # Reattach landed but exchange list can lag a few seconds
    lag = (now - last_reattach).total_seconds()
    if 0 <= lag <= 45.0:
        return True, f"reattach_settle age_s={lag:.0f}"
    return False, ""


def _holdings_lock_fracs(pairs: List[str]) -> Dict[str, float]:
    """pair → hold/amount from venue (stop-locked inventory). Empty on error."""
    if not pairs:
        return {}
    try:
        from phase6.core.exchange_client import CoinbaseExchangeClient

        client = CoinbaseExchangeClient(mode="live")
        hv = client.get_holdings_verified() or {}
        positions = hv.get("positions") or {}
        out: Dict[str, float] = {}
        want = {p.replace("-USD", "").replace("-USDC", "") for p in pairs}
        for raw_k, v in positions.items():
            if not isinstance(v, dict):
                continue
            base = str(raw_k).upper().replace("-USD", "").replace("-USDC", "")
            if base not in want:
                continue
            try:
                amt = float(v.get("amount") or 0.0)
                hold = float(v.get("hold") or 0.0)
            except (TypeError, ValueError):
                continue
            if amt <= 0:
                continue
            pair = f"{base}-USD"
            out[pair] = hold / amt
        return out
    except Exception:
        return {}


def classify_sl_missing(
    *,
    has_open_stop: bool,
    hold_frac: Optional[float],
    cr03_active: bool,
    hold_locked_min: float = HOLD_LOCKED_FRAC_MIN,
) -> str:
    """Classify exchange SL check for a held bag.

    Returns one of:
      ok_orders | note_cr03 | note_hold_locked | alert_missing
    """
    if has_open_stop:
        return "ok_orders"
    if cr03_active:
        return "note_cr03"
    if hold_frac is not None and hold_frac >= hold_locked_min:
        return "note_hold_locked"
    return "alert_missing"


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
    alert_seen = _load_alert_seen()

    hold = _cash_hold()
    page_hold, hold_msg = _should_page_cash_hold(hold, alert_seen)
    if hold_msg:
        if page_hold:
            alerts.append(hold_msg)
        else:
            notes.append(hold_msg)
    # Always remember last observed hold so sticky same-$ stays silent next tick.
    alert_seen["cash_hold_usd"] = float(hold)
    alert_seen["cash_hold_updated_at"] = now.isoformat()
    _save_alert_seen(alert_seen)

    # Blocks snapshot
    try:
        from phase6.core.runner_capital_events import load_buy_block_status

        blocks = load_buy_block_status() or {}
    except Exception as exc:
        blocks = {}
        notes.append(f"buy_block_status_error={exc}")

    # Buy-block hygiene (policy, not hardcodes to one pair):
    #   post_tp_rebuy_block  → ~24h
    #   post_sl_rebuy_block  → ~72h (default)
    # Stale one-off: UNI/RAVE were waived — still flag if those reappear blocked.
    for p in ("UNI-USD", "RAVE-USD"):
        if p in blocks:
            alerts.append(
                f"BLOCK_SHOULD_BE_CLEAR {p} still blocked reason={blocks[p].get('reason')}"
            )
    for pair, b in (blocks or {}).items():
        if pair in ("UNI-USD", "RAVE-USD"):
            continue  # handled above
        reason = str(b.get("reason") or "")
        try:
            hours = float(b.get("block_hours") or 0)
        except (TypeError, ValueError):
            hours = 0.0
        if reason == "post_tp_rebuy_block" and hours <= 24.5:
            notes.append(
                f"{pair} post-TP OK hours_left={b.get('hours_remaining')} exp={b.get('expires_at')}"
            )
        elif reason == "post_sl_rebuy_block" and hours <= 72.5:
            notes.append(
                f"{pair} post-SL OK hours_left={b.get('hours_remaining')} "
                f"block_hours={hours} exp={b.get('expires_at')}"
            )
        elif reason in ("post_tp_rebuy_block", "post_sl_rebuy_block"):
            alerts.append(
                f"BLOCK_HOURS_UNEXPECTED {pair} reason={reason} block_hours={hours}"
            )
        else:
            # unknown block class — note only (not page every 10m)
            notes.append(f"{pair} block reason={reason} hours={hours}")

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

    cr03_flight, cr03_why = _cr03_suspend_in_flight(now)
    cr03_active = cr03_flight or _cr03_schedule_near(now)
    if cr03_active:
        notes.append(
            f"CR03_WINDOW active flight={cr03_flight} why={cr03_why or 'schedule_slot'}"
        )
    lock_fracs = _holdings_lock_fracs(check_pairs) if check_pairs else {}

    for pair in check_pairs:
        orders = stops.get(pair) or []
        entry = float((marks.get(pair) or {}).get("entry_px") or held[pair].get("entry_px") or 0.0)
        cls = classify_sl_missing(
            has_open_stop=bool(orders),
            hold_frac=lock_fracs.get(pair),
            cr03_active=cr03_active,
        )
        if cls != "ok_orders":
            if cls == "note_cr03":
                notes.append(
                    f"SL_MISSING_CR03_WINDOW {pair} held_usd={held[pair].get('value_usd'):.2f} "
                    f"({cr03_why or 'schedule'})"
                )
            elif cls == "note_hold_locked":
                notes.append(
                    f"SL_HOLD_LOCKED_OK {pair} hold_frac={lock_fracs.get(pair):.3f} "
                    f"held_usd={held[pair].get('value_usd'):.2f} (list lag; not naked)"
                )
            else:
                alerts.append(
                    f"SL_MISSING_EXCHANGE {pair} held_usd={held[pair].get('value_usd'):.2f}"
                )
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
    # P1 sentiment-fade shadow (no live sell; dual_peak owns live structure exits)
    try:
        from phase6.core.rsi_primary_deploy import run_sentiment_fade_shadow
        import json as _json
        from pathlib import Path as _Path

        _cfg = {}
        _cp = _Path("config/trading_config_phase6.json")
        if _cp.exists():
            _cfg = _json.loads(_cp.read_text())
        fade_rows = run_sentiment_fade_shadow(config_dict=_cfg, notify=True)
        result["sentiment_fade_shadow"] = fade_rows
        for fr in fade_rows:
            notes.append(
                f"SENT_FADE_SHADOW {fr.get('pair')} would_trim=${fr.get('would_trim_usd')} "
                f"sent {fr.get('entry_sentiment')}→{fr.get('current_sentiment')}"
            )
        result["notes"] = notes[:40]
    except Exception as _fe:
        result["sentiment_fade_error"] = str(_fe)

    # P2 dual-peak: shadow board always; LIVE trims when mode=live
    try:
        from phase6.core.run_lifecycle import (
            apply_lifecycle_exits_live,
            run_dual_peak_exit_shadow,
            load_lifecycle_config,
        )
        import json as _json2
        from pathlib import Path as _Path2

        _cfg2 = {}
        _cp2 = _Path2("config/trading_config_phase6.json")
        if _cp2.exists():
            _cfg2 = _json2.loads(_cp2.read_text())
        p2_mode = str(
            (load_lifecycle_config(_cfg2).get("dual_peak_exit") or {}).get("mode") or "shadow"
        ).lower()
        if p2_mode == "live":
            # Prefer exchange already built in this monitor if present
            ex = None
            try:
                from phase6.core.exchange_client import CoinbaseExchangeClient

                ex = CoinbaseExchangeClient(mode="live")
            except Exception:
                ex = None
            live_out = apply_lifecycle_exits_live(
                config_dict=_cfg2, exchange=ex, dry_run=False, notify=True
            )
            result["dual_peak_exit_live"] = {
                "events": live_out.get("events") or [],
                "executed": live_out.get("executed") or [],
                "skipped": live_out.get("skipped") or [],
                "error": live_out.get("error"),
                "note": live_out.get("note"),
            }
            for er in live_out.get("executed") or []:
                notes.append(
                    f"DUAL_PEAK_LIVE {er.get('kind')} {er.get('pair')} "
                    f"qty={er.get('filled_qty') or er.get('qty')} oid={er.get('order_id')}"
                )
            for sk in live_out.get("skipped") or []:
                pair = str(sk.get("pair") or "?")
                kind = str(sk.get("kind") or "dual_peak")
                err = str(sk.get("error") or sk.get("reason") or "skipped")
                # Compress common Coinbase preview failures
                if "INSUFFICIENT_FUND" in err:
                    err_short = "INSUFFICIENT_FUND (likely stop-locked size)"
                else:
                    err_short = err[:120]
                fp = f"live_exit_fail:{pair}:{kind}:{err_short[:40]}"
                msg = f"LIVE_EXIT_FAIL {kind} {pair} {err_short}"
                if _should_page_fingerprint(fp, alert_seen, LIVE_EXIT_FAIL_DEDUPE_HOURS):
                    alerts.append(msg)
                else:
                    notes.append(msg + " (deduped)")
            for dr in live_out.get("events") or []:
                if not any(
                    (x.get("pair") == dr.get("pair") and x.get("kind") == dr.get("kind"))
                    for x in (live_out.get("executed") or [])
                ):
                    notes.append(
                        f"DUAL_PEAK_SIGNAL {dr.get('kind')} {dr.get('pair')} "
                        f"would_trim=${dr.get('would_trim_usd')} phase={dr.get('phase_name')}"
                    )
            _save_alert_seen(alert_seen)
        else:
            dp_rows = run_dual_peak_exit_shadow(config_dict=_cfg2, notify=True)
            result["dual_peak_exit_shadow"] = dp_rows
            for dr in dp_rows:
                notes.append(
                    f"DUAL_PEAK_SHADOW {dr.get('kind')} {dr.get('pair')} "
                    f"would_trim=${dr.get('would_trim_usd')} phase={dr.get('phase_name')}"
                )
        result["notes"] = notes[:50]
    except Exception as _de:
        result["dual_peak_exit_error"] = str(_de)

    # P1 ignition scout board refresh (propose/shadow)
    try:
        from phase6.core.run_lifecycle import run_ignition_scout
        import json as _json3
        from pathlib import Path as _Path3

        _cfg3 = {}
        _cp3 = _Path3("config/trading_config_phase6.json")
        if _cp3.exists():
            _cfg3 = _json3.loads(_cp3.read_text())
        pool = list(
            (_cfg3.get("phase_6_specific") or {}).get("opportunity_pool")
            or (_cfg3.get("global_settings") or {}).get("pairs")
            or []
        )
        if pool:
            board = run_ignition_scout(pool, config_dict=_cfg3, write_board=True)
            result["ignition_scout_top"] = board.get("top") or []
            result["ignition_scout_mode"] = (
                ((_cfg3.get("run_lifecycle") or {}).get("ignition_scout") or {}).get("mode")
            )
            for t in (board.get("top") or [])[:5]:
                notes.append(
                    f"IGNITION_SCOUT {t.get('pair')} score={t.get('score')} "
                    f"phase={t.get('phase_name')} struct={t.get('structure_ok')}"
                )
            result["notes"] = notes[:50]
    except Exception as _ie:
        result["ignition_scout_error"] = str(_ie)

    # Recompute ok after late hooks (dual-peak / fade / scout) may append alerts.
    result["alerts"] = alerts
    result["notes"] = notes[:50]
    result["ok"] = len(alerts) == 0

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
    try:
        result = evaluate(lookback_hours=args.lookback_hours)
    except Exception as exc:
        # Real failure → exit 1 so Hermes pages
        print(f"REENTRY_SL_TP_MONITOR_ERROR: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    # no_agent + telegram: exit 0 always on successful eval.
    # Empty stdout = silent (healthy). Non-empty = deliver alert body.
    # Exit 1 was wrongly treated as "cron failed 9×" for policy alerts.
    if result.get("ok"):
        return 0
    print(f"REENTRY_SL_TP_ALERT n={len(result['alerts'])} ts={result['ts']}")
    for a in result["alerts"]:
        print(f"  ALERT: {a}")
    for n in (result.get("notes") or [])[:8]:
        print(f"  note: {n}")
    print(f"  detail: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
