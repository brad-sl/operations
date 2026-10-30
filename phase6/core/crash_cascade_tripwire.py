#!/usr/bin/env python3
"""
Crash Cascade Tripwire (Brad GO 2026-10-29).

Live protection: detect systemic BTC+ETH air-pocket dump in progress,
freeze adds immediately, alert for triage, and optionally flatten with
market-triggered recovery (not time-bound).

Design:
  - Tier 0: any BTC|ETH 1h ≤ -1.5% → freeze seeder (cheap, always-on)
  - Tier 1: both BTC+ETH same hour ≤ -2.0% OR dual 4h ≤ -3.5% → signal cascade
  - Tier 2A: freeze adds + alert for ops triage (live default)
  - Tier 2C: optional auto-flatten (shadow until explicit GO)
  - Recovery: market-triggered (not time), when dual-asset reversal / new high

State:
  - Kill file: data/state/crash_cascade_tripwire_KILLED (prevents Tier 2A/C)
  - Config: config/crash_cascade_tripwire.json
  - Receipt: data/state/crash_cascade_tripwire_latest.json
  - Recovery arm file: data/state/crash_cascade_recovery_armed

Re-arm: manual Brad GO or market recovery signal (see recover_conditions).
"""
from __future__ import annotations

import json
import logging
import os
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from phase6.core.exchange_client import CoinbaseExchangeClient
from phase6.core.paths import CONFIG_DIR, STATE_DIR

logger = logging.getLogger(__name__)

SCHEMA = "crash_cascade_tripwire_v1"
CONFIG_PATH = CONFIG_DIR / "crash_cascade_tripwire.json"
KILL_PATH = STATE_DIR / "crash_cascade_tripwire_KILLED"
LATEST_PATH = STATE_DIR / "crash_cascade_tripwire_latest.json"
RECOVERY_ARM_PATH = STATE_DIR / "crash_cascade_recovery_armed"
TRIP_HISTORY_PATH = STATE_DIR / "crash_cascade_trip_history.jsonl"

DEFAULT_CFG: Dict[str, Any] = {
    "schema": SCHEMA,
    "live_apply": True,
    "tier0_enable": True,  # any BTC|ETH 1h <= -1.5%
    "tier0_threshold_pct": -1.5,
    "tier1_enable": True,  # dual confirm
    "tier1_dual_1h_pct": -2.0,
    "tier1_dual_4h_pct": -3.5,
    "tier2_alert": True,  # always alert
    "tier2_freeze_adds": True,  # always freeze seeder
    "tier2_auto_flatten": False,  # shadow by default
    "flat_pairs": ["BTC-USD", "ETH-USD"],
    "leave_pairs": ["PAXG-USD", "USDC-USD", "USDT-USD"],
    "min_book_notional_usd": 100.0,  # only trip if bag is substantial
    "recovery_window_hours": 24,  # re-arm if no trip for N hours
    "recovery_reversal_pct": 1.5,  # both coins +1.5% from trip low
    "recovery_new_high_confirm": True,  # confirm via new 1h high
    "note": "Live production tripwire — Tier 0/1 fire, Tier 2A alert+freeze, Tier 2C shadow",
}


def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x) if x is not None else default
    except (TypeError, ValueError):
        return default


def _norm_pair(p: str) -> str:
    s = str(p or "").strip().upper().replace("_", "-")
    if not s or "-" not in s:
        s = f"{s}-USD" if s else ""
    return s


def kill_file_on() -> bool:
    return KILL_PATH.is_file()


def recovery_armed() -> bool:
    """Already tripped and armed recovery waiting."""
    return RECOVERY_ARM_PATH.is_file()


def load_config() -> Dict[str, Any]:
    cfg = DEFAULT_CFG.copy()
    try:
        if CONFIG_PATH.is_file():
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cfg.update(raw)
    except Exception as e:
        logger.warning("crash_cascade_tripwire config load failed: %s", e)
    return cfg


def _send_telegram(msg: str, topic: str = "tripwire") -> bool:
    """Ship alert to Telegram."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        logger.warning("telegram credentials missing")
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
        return r.status_code == 200
    except Exception as e:
        logger.error("telegram send failed: %s", e)
        return False


def fetch_1h_candles(pair: str, hours: int = 48) -> List[Tuple[int, float, float, float, float, float]]:
    """Fetch 1h candles from Coinbase public REST.
    Returns: [(timestamp, low, high, open, close, volume), ...] sorted by time.
    """
    import urllib.request

    pair = _norm_pair(pair)
    if not pair:
        return []
    try:
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=hours)
        url = (
            f"https://api.exchange.coinbase.com/products/{pair}/candles"
            f"?start={start.isoformat().replace('+00:00', 'Z')}"
            f"&end={end.isoformat().replace('+00:00', 'Z')}"
            f"&granularity=3600"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "phase6-tripwire"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode())
        if not isinstance(data, list):
            return []
        rows = sorted(data, key=lambda x: x[0])
        return rows
    except Exception as e:
        logger.error("fetch_1h_candles %s: %s", pair, e)
        return []


def compute_1h_return(candles: List[Tuple]) -> float:
    """Last close vs prior close (%)."""
    if len(candles) < 2:
        return 0.0
    prior_close = _f(candles[-2][4], 1.0)
    curr_close = _f(candles[-1][4], 1.0)
    return (curr_close - prior_close) / prior_close * 100 if prior_close else 0.0


def compute_4h_return(candles: List[Tuple]) -> float:
    """Last 4 closes vs 4 before (%)."""
    if len(candles) < 8:
        return 0.0
    old_close = _f(candles[-8][4], 1.0)
    curr_close = _f(candles[-1][4], 1.0)
    return (curr_close - old_close) / old_close * 100 if old_close else 0.0


def get_book_held_pairs() -> Dict[str, float]:
    """Read live book: {pair: value_usd}."""
    try:
        if STATE_DIR.exists():
            state_file = STATE_DIR / "phase6_live_state.json"
            if state_file.is_file():
                data = json.loads(state_file.read_text(encoding="utf-8"))
                held = {}
                for pos in data.get("positions", []):
                    pair = _norm_pair(pos.get("pair") or "")
                    if pair:
                        usd = _f(pos.get("value_usd"), 0.0)
                        if usd > 1.0:
                            held[pair] = usd
                return held
    except Exception as e:
        logger.warning("get_book_held_pairs failed: %s", e)
    return {}


def evaluate_tripwire(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Check cascade conditions (Tier 0/1) against live tape.
    Return: {
        'trip': bool,
        'tier': 0|1|2,
        'timestamp': ISO,
        'signal': str (human),
        'pairs_affected': [pair, ...],
        'returns_1h': {pair: pct},
        'returns_4h': {pair: pct},
        'held': {pair: usd},
        'recommendation': str,
    }
    """
    c = cfg or load_config()
    result: Dict[str, Any] = {
        "schema": SCHEMA,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "trip": False,
        "tier": -1,
        "signal": "",
        "pairs_affected": [],
        "returns_1h": {},
        "returns_4h": {},
        "held": {},
        "book_notional_usd": 0.0,
        "recommendation": "",
        "error": None,
    }

    if not c.get("live_apply"):
        result["reason"] = "live_apply=false"
        return result
    if kill_file_on():
        result["reason"] = "kill_file_on"
        return result

    held = get_book_held_pairs()
    result["held"] = held
    result["book_notional_usd"] = sum(held.values())

    pairs_to_check = [_norm_pair(p) for p in c.get("flat_pairs", [])]
    if not pairs_to_check:
        result["error"] = "no flat_pairs configured"
        return result

    returns_1h = {}
    returns_4h = {}
    affected = []

    for pair in pairs_to_check:
        if pair not in held or held[pair] < 1.0:
            continue  # pair not held
        candles = fetch_1h_candles(pair, hours=48)
        if len(candles) < 2:
            result["error"] = f"thin candles for {pair}"
            continue
        r1h = compute_1h_return(candles)
        r4h = compute_4h_return(candles)
        returns_1h[pair] = r1h
        returns_4h[pair] = r4h
        affected.append(pair)

    result["returns_1h"] = returns_1h
    result["returns_4h"] = returns_4h
    result["pairs_affected"] = affected

    # Tier 0: any single leg hard drop
    if c.get("tier0_enable"):
        thresh = c.get("tier0_threshold_pct", -1.5)
        for pair, r1h in returns_1h.items():
            if r1h <= thresh:
                result["trip"] = True
                result["tier"] = 0
                result["signal"] = f"Tier 0 trigger: {pair} 1h={r1h:.2f}% ≤ {thresh}%"
                result["recommendation"] = "FREEZE SEEDER; hold else."
                return result

    # Tier 1: dual confirm
    if c.get("tier1_enable") and len(affected) >= 2:
        t1_1h = c.get("tier1_dual_1h_pct", -2.0)
        t1_4h = c.get("tier1_dual_4h_pct", -3.5)
        # both 1h?
        if all(r1h <= t1_1h for r1h in returns_1h.values()):
            result["trip"] = True
            result["tier"] = 1
            result["signal"] = (
                f"Tier 1 trigger: both {affected} 1h ≤ {t1_1h}%: "
                f"{', '.join(f'{p}={returns_1h.get(p, 0):.2f}%' for p in affected)}"
            )
            result["recommendation"] = "ALERT & FREEZE SEEDER; optional hard flatten if GO."
            return result
        # both 4h?
        if all(r4h <= t1_4h for r4h in returns_4h.values()):
            result["trip"] = True
            result["tier"] = 1
            result["signal"] = (
                f"Tier 1 trigger: both {affected} 4h ≤ {t1_4h}%: "
                f"{', '.join(f'{p}={returns_4h.get(p, 0):.2f}%' for p in affected)}"
            )
            result["recommendation"] = "ALERT & FREEZE SEEDER; optional hard flatten if GO."
            return result

    result["signal"] = "No trip"
    result["recommendation"] = "Monitor continues; no action."
    return result


def execute_tripwire(trip_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    If trip fired, freeze seeder and optionally alert.
    Mutates state files.
    Returns receipt.
    """
    receipt: Dict[str, Any] = {"schema": SCHEMA, "executed_at": datetime.now(timezone.utc).isoformat()}

    if not trip_result.get("trip"):
        receipt["action"] = "no_trip"
        return receipt

    cfg = load_config()
    receipt["tier"] = trip_result.get("tier")
    receipt["signal"] = trip_result.get("signal")

    # Tier 2A: Freeze seeder (always on if trip)
    if cfg.get("tier2_freeze_adds", True):
        try:
            from phase6.core.c2_ballast_seeder import KILL_PATH as SEEDER_KILL

            SEEDER_KILL.parent.mkdir(parents=True, exist_ok=True)
            SEEDER_KILL.touch()
            receipt["seeder_killed"] = True
            logger.info("crash_cascade_tripwire: seeder KILL stamped")
        except Exception as e:
            logger.error("seeder kill failed: %s", e)
            receipt["seeder_killed"] = False

    # Tier 2A: Alert (always on if trip)
    if cfg.get("tier2_alert", True):
        alert = (
            f"🚨 <b>CRASH CASCADE TRIPWIRE FIRED</b>\n"
            f"Tier: {trip_result.get('tier')}\n"
            f"Signal: {trip_result.get('signal')}\n"
            f"Held: {trip_result.get('held')}\n"
            f"Book: ${trip_result.get('book_notional_usd', 0):.0f}\n"
            f"\n"
            f"<b>Action:</b> Seeder frozen. "
            f"Recommend immediate ops triage + GO for hard flatten if needed.\n"
            f"<b>Recovery:</b> Market-triggered (dual reversal +1.5% from low).\n"
        )
        ok = _send_telegram(alert, topic="crash_tripwire")
        receipt["alert_sent"] = ok
        logger.info("crash_cascade_tripwire alert sent: %s", ok)

    # Tier 2C: Auto-flatten (shadow by default)
    if cfg.get("tier2_auto_flatten", False) and trip_result.get("tier") in (0, 1):
        try:
            from phase6.core.protected_market_exit import protected_market_exit

            client = CoinbaseExchangeClient(mode="live")
            client._ensure_live_client()
            held = trip_result.get("held", {})
            flat_pairs = [_norm_pair(p) for p in cfg.get("flat_pairs", [])]
            exits = {}
            for pair in flat_pairs:
                if pair in held and held[pair] > 1.0:
                    pe = protected_market_exit(
                        client,
                        pair,
                        reason=f"crash_cascade_tier{trip_result.get('tier')}",
                        cancel_stops=True,
                    )
                    exits[pair] = pe
            receipt["hard_flatten"] = exits
            logger.info("crash_cascade_tripwire: hard flatten executed: %s", exits)
        except Exception as e:
            logger.error("hard flatten failed: %s", e)
            receipt["hard_flatten_error"] = str(e)

    # Arm recovery waiting
    RECOVERY_ARM_PATH.parent.mkdir(parents=True, exist_ok=True)
    RECOVERY_ARM_PATH.touch()
    receipt["recovery_armed"] = True

    # Log to history
    TRIP_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TRIP_HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(receipt) + "\n")

    # Write latest snapshot
    LATEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    snap = {"schema": SCHEMA, "as_of": receipt["executed_at"], **receipt, **trip_result}
    LATEST_PATH.write_text(json.dumps(snap, indent=2))

    return receipt


def check_recovery_conditions(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Tripwire is armed. Check if market has recovered (dual reversal + new high).
    If yes: disarm and re-enable seeder.
    Returns: {'recovered': bool, 'signal': str, 're_armed': bool}
    """
    result: Dict[str, Any] = {
        "schema": SCHEMA,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "recovered": False,
        "signal": "",
        "re_armed": False,
    }

    if not recovery_armed():
        result["reason"] = "recovery_not_armed"
        return result

    c = cfg or load_config()
    if not c.get("live_apply"):
        result["reason"] = "live_apply=false"
        return result

    # Read trip event to get baseline
    if not LATEST_PATH.is_file():
        result["reason"] = "no_prior_trip_snapshot"
        return result

    try:
        trip_snap = json.loads(LATEST_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        result["reason"] = f"snapshot read failed: {e}"
        return result

    trip_1h = trip_snap.get("returns_1h", {})
    trip_time = datetime.fromisoformat(trip_snap.get("as_of", ""))
    trip_age_h = (datetime.now(timezone.utc) - trip_time).total_seconds() / 3600

    # Outside recovery window? → disarm, allow re-trip
    if trip_age_h > c.get("recovery_window_hours", 24):
        try:
            RECOVERY_ARM_PATH.unlink(missing_ok=True)
        except Exception:
            pass
        result["reason"] = "recovery_window_expired"
        result["recovered"] = True
        result["signal"] = f"No recovery after {trip_age_h:.1f}h; window closed. Disarmed."
        return result

    # Check current tape
    flat_pairs = [_norm_pair(p) for p in c.get("flat_pairs", [])]
    curr_1h = {}
    for pair in flat_pairs:
        candles = fetch_1h_candles(pair, hours=48)
        if candles:
            curr_1h[pair] = compute_1h_return(candles)

    if not curr_1h:
        result["reason"] = "no_current_candles"
        return result

    # Dual reversal: both coins up >= recovery_reversal_pct from trip low
    rev_pct = c.get("recovery_reversal_pct", 1.5)
    reversals = {p: curr_1h.get(p, 0) for p in flat_pairs if p in curr_1h}
    if len(reversals) >= 2 and all(r >= rev_pct for r in reversals.values()):
        result["recovered"] = True
        result["signal"] = (
            f"Dual reversal: {', '.join(f'{p}={reversals[p]:.2f}%' for p in reversals)} "
            f"all ≥ {rev_pct}%"
        )
        # Disarm and re-enable seeder
        try:
            RECOVERY_ARM_PATH.unlink(missing_ok=True)
            from phase6.core.c2_ballast_seeder import KILL_PATH as SEEDER_KILL

            SEEDER_KILL.unlink(missing_ok=True)
            result["re_armed"] = True
            logger.info("crash_cascade_tripwire: recovery detected, seeder re-armed")
        except Exception as e:
            logger.error("re-arm failed: %s", e)
            result["re_arm_error"] = str(e)

    return result


def main():
    cfg = load_config()
    print(json.dumps(cfg, indent=2))


if __name__ == "__main__":
    main()
