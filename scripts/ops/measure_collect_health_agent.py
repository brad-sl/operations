#!/usr/bin/env python3
"""
Measure-collect health agent — catch frozen meters and initiate repair.

Part of ops-engineer mandate (Brad 2026-10-25):
  shadow/measure streams that never populate should not burn 14d clocks unnoticed.

Deterministic (no LLM):
  1. evaluate_all_streams()
  2. for each frozen/bad stream: write repair packet + optional auto-repair hooks
  3. alert once per stream/code (idempotent via ops state)
  4. never flip live_apply / money path

Auto-repair (safe only):
  - w2_would_arm sensor_degenerate / thin: re-run would-arm collector + stamp post_fix
  - bank_trail sensor_thin only: no auto CF (needs OHLCV / cost) — packet only
  - others: packet + MASTER note only

Usage:
  python scripts/ops/measure_collect_health_agent.py
  python scripts/ops/measure_collect_health_agent.py --no-repair
  python scripts/ops/measure_collect_health_agent.py --quiet
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path("/home/brad/projects/crypto-trading-bot")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

STATE_DIR = PROJECT_ROOT / "data" / "state"
LOGS_DIR = PROJECT_ROOT / "logs"
MASTER_TASKS = PROJECT_ROOT / "docs" / "MASTER_TASK_TRACKING.md"
OPS_STATE = Path.home() / ".hermes" / "ops_engineer_state.json"
ROLLUP_PATH = STATE_DIR / "measure_collect_health_rollup_latest.json"
REPAIR_DIR = STATE_DIR / "measure_health_repairs"
AGENT_LOG = LOGS_DIR / "measure_collect_health_agent.log"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_ops() -> dict:
    if not OPS_STATE.exists():
        return {"seen_troubles": {}, "measure_health": {}}
    try:
        o = json.loads(OPS_STATE.read_text(encoding="utf-8"))
        return o if isinstance(o, dict) else {"seen_troubles": {}, "measure_health": {}}
    except Exception:
        return {"seen_troubles": {}, "measure_health": {}}


def _save_ops(state: dict) -> None:
    OPS_STATE.parent.mkdir(parents=True, exist_ok=True)
    OPS_STATE.write_text(json.dumps(state, indent=2, default=str) + "\n", encoding="utf-8")


def _log(msg: str, quiet: bool = False) -> None:
    line = f"[{_utc()}] {msg}"
    if not quiet:
        print(line)
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        with AGENT_LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _send_telegram(message: str) -> None:
    # load env like ops_engineer
    try:
        from dotenv import load_dotenv

        load_dotenv(PROJECT_ROOT / ".env")
        load_dotenv(Path.home() / ".hermes" / ".env")
    except Exception:
        pass
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        _log("Telegram not configured — alert printed only")
        print(message)
        return
    try:
        import requests

        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": message[:3500]},
            timeout=10,
        )
    except Exception as e:
        _log(f"Telegram failed: {e}")


def _append_master(packet: dict) -> None:
    entry = f"""

---

**MEASURE HEALTH — REPAIR PACKET {packet['id']}** (opened {packet['as_of']})
**Stream**: `{packet['stream']}`
**Severity**: {packet['severity']}
**Health code**: `{packet['code']}` · clock={'OK' if packet.get('collect_clock_ok') else 'FROZEN'}
**Plain**: {packet['plain_english']}
**Repair hint**: {packet.get('repair_hint') or '(none)'}
**Auto-repair attempted**: {packet.get('auto_repair') or 'none'}
**Status**: OPEN (measure_collect_health_agent)

Do **not** GO this stream while clock_FROZEN / sensor_degenerate. Fix meter first; then post_fix stamp + new sensor_ok_days.
"""
    try:
        with MASTER_TASKS.open("a", encoding="utf-8") as f:
            f.write(entry)
        _log(f"Appended {packet['id']} to MASTER_TASK_TRACKING.md")
    except OSError as e:
        _log(f"MASTER append failed: {e}")


def _write_repair_packet(packet: dict) -> Path:
    REPAIR_DIR.mkdir(parents=True, exist_ok=True)
    path = REPAIR_DIR / f"{packet['id']}.json"
    path.write_text(json.dumps(packet, indent=2, default=str) + "\n", encoding="utf-8")
    latest = REPAIR_DIR / "latest.json"
    latest.write_text(json.dumps(packet, indent=2, default=str) + "\n", encoding="utf-8")
    return path


def _auto_repair_w2() -> dict:
    """Safe: re-run would-arm collector + stamp post_fix marker."""
    out: dict = {"action": "w2_rerun_collector", "ok": False}
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "phase6" / "run_sl_width_would_arm_shadow.py"),
    ]
    try:
        p = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        out["exit_code"] = p.returncode
        out["stdout"] = (p.stdout or "")[-800:]
        out["stderr"] = (p.stderr or "")[-400:]
        out["ok"] = p.returncode == 0
    except Exception as e:
        out["error"] = str(e)
        return out
    try:
        from phase6.research.measure_collect_health import stamp_w2_post_fix

        out["post_fix_since"] = stamp_w2_post_fix()
    except Exception as e:
        out["stamp_error"] = str(e)
    # re-score live
    try:
        from phase6.research.measure_collect_health import health_w2_would_arm

        h = health_w2_would_arm()
        out["after_health"] = {
            "code": h.get("code"),
            "collect_clock_ok": h.get("collect_clock_ok"),
            "live_meter": h.get("live_meter"),
            "sensor_ok_day_estimate": h.get("sensor_ok_day_estimate"),
        }
    except Exception as e:
        out["after_health_error"] = str(e)
    return out


AUTO_REPAIR = {
    "w2_would_arm": {
        "codes": {"sensor_degenerate", "sensor_broken", "sensor_thin"},
        "fn": _auto_repair_w2,
    },
}


def run(*, do_repair: bool = True, quiet: bool = False, alert: bool = True) -> dict:
    from phase6.research.measure_collect_health import (
        evaluate_all_streams,
        telegram_health_line,
    )

    _log("measure_collect_health_agent start", quiet=quiet)
    roll = evaluate_all_streams()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    ROLLUP_PATH.write_text(json.dumps(roll, indent=2, default=str) + "\n", encoding="utf-8")
    _log(roll.get("plain_english") or "rollup done", quiet=quiet)

    ops = _load_ops()
    mh_seen = ops.setdefault("measure_health", {})
    if not isinstance(mh_seen, dict):
        mh_seen = {}
        ops["measure_health"] = mh_seen

    packets: list = []
    streams = roll.get("streams") or {}
    for name, h in streams.items():
        if not isinstance(h, dict):
            continue
        code = str(h.get("code") or "")
        clock_ok = bool(h.get("collect_clock_ok"))
        ok = bool(h.get("ok"))
        needs = (not clock_ok) or (not ok) or code in {
            "sensor_degenerate",
            "sensor_broken",
            "sensor_thin",
        }
        _log(f"  · {telegram_health_line(h)}", quiet=quiet)
        if not needs:
            # clear sticky open if recovered
            key = f"{name}:{code or 'ok'}"
            if name in mh_seen and mh_seen[name].get("status") == "OPEN":
                mh_seen[name]["status"] = "CLEARED"
                mh_seen[name]["cleared_at"] = _utc()
                mh_seen[name]["cleared_code"] = code
            continue

        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        packet_id = f"MH-{name.upper()}-{code.upper()}-{day}"
        # idempotent: one open packet per stream per day+code
        prev = mh_seen.get(name) or {}
        if (
            prev.get("packet_id") == packet_id
            and prev.get("status") == "OPEN"
            and prev.get("code") == code
        ):
            _log(f"  skip duplicate {packet_id}", quiet=quiet)
            continue

        severity = h.get("severity_if_bad") or "WARNING"
        if code == "sensor_degenerate":
            severity = "HIGH"
        if code == "sensor_broken":
            severity = "CRITICAL"

        packet = {
            "id": packet_id,
            "schema": "measure_health_repair_packet_v1",
            "as_of": _utc(),
            "stream": name,
            "code": code,
            "ok": ok,
            "collect_clock_ok": clock_ok,
            "severity": severity,
            "plain_english": h.get("plain_english"),
            "repair_hint": h.get("repair_hint"),
            "metrics": h.get("metrics") or h.get("live_meter"),
            "auto_repair": None,
        }

        if do_repair and name in AUTO_REPAIR:
            meta = AUTO_REPAIR[name]
            if code in meta["codes"]:
                _log(f"  auto-repair {name}…", quiet=quiet)
                packet["auto_repair"] = meta["fn"]()

        path = _write_repair_packet(packet)
        packet["path"] = str(path)
        _append_master(packet)
        packets.append(packet)

        mh_seen[name] = {
            "packet_id": packet_id,
            "code": code,
            "status": "OPEN",
            "opened": _utc(),
            "path": str(path),
            "auto_repair_ok": (packet.get("auto_repair") or {}).get("ok"),
        }

        if alert:
            ar = packet.get("auto_repair") or {}
            ar_line = ""
            if ar:
                ar_line = (
                    f"\nAuto-repair: ok={ar.get('ok')} "
                    f"after={((ar.get('after_health') or {}).get('code'))}"
                )
            _send_telegram(
                f"🩺 {severity} MEASURE HEALTH: {packet_id}\n"
                f"{name} · {code} · clock={'OK' if clock_ok else 'FROZEN'}\n"
                f"{(h.get('plain_english') or '')[:400]}\n"
                f"Repair: {(h.get('repair_hint') or '')[:300]}"
                f"{ar_line}\n"
                f"Packet: {path}"
            )

    ops["measure_health"] = mh_seen
    ops["last_measure_health_run"] = _utc()
    ops["last_measure_health_rollup"] = {
        "n_frozen": roll.get("n_frozen"),
        "n_bad": roll.get("n_bad"),
        "frozen": roll.get("frozen"),
        "bad": roll.get("bad"),
    }
    _save_ops(ops)

    result = {
        "as_of": _utc(),
        "rollup": {
            "n_streams": roll.get("n_streams"),
            "n_frozen": roll.get("n_frozen"),
            "n_bad": roll.get("n_bad"),
            "frozen": roll.get("frozen"),
            "bad": roll.get("bad"),
            "plain_english": roll.get("plain_english"),
        },
        "new_packets": [p["id"] for p in packets],
        "packets": packets,
        "rollup_path": str(ROLLUP_PATH),
    }
    (STATE_DIR / "measure_collect_health_agent_latest.json").write_text(
        json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8"
    )
    _log(
        f"done · new_packets={len(packets)} frozen={roll.get('n_frozen')} bad={roll.get('n_bad')}",
        quiet=quiet,
    )
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-repair", action="store_true", help="Detect + packet only; no auto-repair")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--no-alert", action="store_true")
    args = ap.parse_args()
    run(do_repair=not args.no_repair, quiet=args.quiet, alert=not args.no_alert)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
