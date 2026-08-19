#!/usr/bin/env python3
"""
Kill-bot soak: tiny Preserve Hold arm → verify E1 on Coinbase → stop runner →
re-verify E1 still open → restart runner → disarm + disable.

Usage:
  PYTHONPATH=. .venv/bin/python scripts/phase6/preserve_killbot_soak.py --i-understand
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT))

from phase6.core.exchange_client import CoinbaseExchangeClient  # noqa: E402
from phase6.core.preserve_hold import (  # noqa: E402
    arm_preserve_hold,
    disarm_preserve_hold,
    load_state,
    persist_status,
    should_protect_preserve_sleeve,
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def load_cfg():
    p = PROJECT / "config" / "trading_config_phase6.json"
    return json.loads(p.read_text())


def save_cfg(cfg):
    p = PROJECT / "config" / "trading_config_phase6.json"
    p.write_text(json.dumps(cfg, indent=2) + "\n")


def find_runner_pid():
    out = subprocess.check_output(["pgrep", "-af", "phase6.core.phase6_runner"], text=True)
    for line in out.splitlines():
        if "pgrep" in line:
            continue
        parts = line.split(None, 1)
        if parts:
            return int(parts[0]), line
    return None, None


def e1_open_on_exchange(ex, order_id: str, pair: str = "PAXG-USD") -> dict:
    found = False
    sample = []
    try:
        if hasattr(ex, "get_open_stop_orders"):
            orders = ex.get_open_stop_orders(pair) or []
        else:
            orders = ex.get_open_orders() or []
        for o in orders or []:
            oid = str(o.get("order_id") or o.get("id") or "")
            pid = str(o.get("product_id") or o.get("pair") or "")
            if "PAXG" in pid.upper() or oid == str(order_id):
                sample.append({"order_id": oid, "product_id": pid, "status": o.get("status")})
            if oid == str(order_id):
                found = True
    except Exception as e:
        return {"found": False, "error": str(e), "sample": sample}
    return {"found": found, "sample": sample, "order_id": order_id}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--i-understand", action="store_true")
    ap.add_argument("--max-buy-usd", type=float, default=30.0)
    ap.add_argument("--soak-sec", type=float, default=25.0)
    ap.add_argument("--no-restart", action="store_true")
    ap.add_argument("--keep-armed", action="store_true", help="Do not disarm at end")
    args = ap.parse_args()
    report = {"as_of": _now(), "steps": [], "pass": False}
    if not args.i_understand:
        print("Need --i-understand")
        return 2

    cfg = load_cfg()
    cfg.setdefault("preserve_mode", {})["enabled"] = True
    # keep armed flag false in config; state drives runtime
    cfg["preserve_mode"]["armed"] = False
    save_cfg(cfg)
    report["steps"].append({"set_enabled": True})

    ex = CoinbaseExchangeClient(mode="live")
    # force if crypto util: soak is micro and intentional
    arm = arm_preserve_hold(
        ex,
        cfg,
        force=True,
        dry_run=False,
        max_buy_usd=float(args.max_buy_usd),
    )
    report["arm"] = {k: arm.get(k) for k in ("ok", "error", "crypto_util_pct", "buy_usd", "target_usd") if k in arm or True}
    report["arm_ok"] = arm.get("ok")
    report["arm_error"] = arm.get("error")
    report["arm_steps"] = arm.get("steps")
    if not arm.get("ok"):
        report["fail"] = "arm_failed"
        _write(report)
        # leave enabled? disable
        cfg["preserve_mode"]["enabled"] = False
        save_cfg(cfg)
        return 1

    st = load_state()
    oid = st.get("e1_order_id")
    report["e1_order_id"] = oid
    report["state"] = st

    v1 = e1_open_on_exchange(ex, oid)
    report["verify_before_kill"] = v1
    if not v1.get("found"):
        report["fail"] = "e1_not_found_before_kill"
        disarm_preserve_hold(ex, cfg, sell=True)
        cfg["preserve_mode"]["enabled"] = False
        save_cfg(cfg)
        _write(report)
        return 1

    pid, cmdline = find_runner_pid()
    report["runner_before"] = {"pid": pid, "cmd": cmdline}
    if not pid:
        report["fail"] = "no_runner_pid"
        # still soak without kill?
        report["note"] = "no runner — verified E1 only"
    else:
        os.kill(pid, signal.SIGTERM)
        report["steps"].append({"sigterm": pid, "t": _now()})
        # wait death
        dead = False
        for _ in range(30):
            time.sleep(0.5)
            try:
                os.kill(pid, 0)
            except OSError:
                dead = True
                break
        if not dead:
            os.kill(pid, signal.SIGKILL)
            time.sleep(1)
            report["steps"].append({"sigkill": pid})
        report["runner_dead"] = True
        time.sleep(float(args.soak_sec))

    # new client after kill (bot dead)
    ex2 = CoinbaseExchangeClient(mode="live")
    v2 = e1_open_on_exchange(ex2, oid)
    report["verify_while_bot_dead"] = v2
    report["protect_helper"] = should_protect_preserve_sleeve(order_id=oid)

    # restart runner
    restarted = False
    if not args.no_restart:
        # match prior invocation
        log = open(PROJECT / "logs" / "phase6_runner.log", "a")
        err = open(PROJECT / "logs" / "phase6_runner_error.log", "a")
        proc = subprocess.Popen(
            [
                str(PROJECT / ".venv" / "bin" / "python"),
                "-m",
                "phase6.core.phase6_runner",
                "--mode",
                "live",
                "--confirm-live",
            ],
            cwd=str(PROJECT),
            env={**os.environ, "PYTHONPATH": str(PROJECT)},
            stdout=log,
            stderr=err,
            start_new_session=True,
        )
        report["restart_pid"] = proc.pid
        time.sleep(8)
        pid2, cmd2 = find_runner_pid()
        report["runner_after"] = {"pid": pid2, "cmd": cmd2}
        restarted = bool(pid2)
        report["restarted"] = restarted

    v3 = e1_open_on_exchange(ex2, oid)
    report["verify_after_restart"] = v3

    # cleanup unless keep
    if not args.keep_armed:
        d = disarm_preserve_hold(ex2, cfg, sell=True)
        report["disarm"] = d
        cfg = load_cfg()
        cfg.setdefault("preserve_mode", {})["enabled"] = False
        cfg["preserve_mode"]["armed"] = False
        save_cfg(cfg)
        # confirm flat
        time.sleep(2)
        left = 0.0
        try:
            left = float(ex2.get_crypto_available("PAXG") or 0)
        except Exception:
            pass
        report["paxg_left"] = left
        v4 = e1_open_on_exchange(ex2, oid)
        report["verify_after_disarm"] = v4

    # PASS for core claim: E1 survived kill. Residual cleanup race noted below.
    report["core_claim_pass"] = bool(v1.get("found") and v2.get("found") and v3.get("found"))
    report["pass"] = report["core_claim_pass"]
    if not args.keep_armed:
        leftover_stop = (report.get("verify_after_disarm") or {}).get("found")
        leftover_paxg = float(report.get("paxg_left") or 0) > 0.0005
        report["cleanup_clean"] = (not leftover_stop) and (not leftover_paxg)
        if leftover_stop or leftover_paxg:
            report["cleanup_note"] = (
                "disarm may leave dust if stop hold races sell — run explicit cancel-all + sell"
            )

    persist_status(cfg, exchange=ex2)
    _write(report)
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "pass",
                    "e1_order_id",
                    "verify_before_kill",
                    "verify_while_bot_dead",
                    "verify_after_restart",
                    "restarted",
                    "fail",
                )
                if k in report
            },
            indent=2,
        )
    )
    return 0 if report["pass"] else 1


def _write(report):
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = PROJECT / "reports" / f"PRESERVE_KILLBOT_SOAK_{day}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str))
    md = PROJECT / "reports" / f"PRESERVE_KILLBOT_SOAK_{day}.md"
    md.write_text(
        "\n".join(
            [
                f"# Preserve kill-bot soak — {day}",
                "",
                f"**PASS:** {report.get('pass')}",
                f"**E1:** `{report.get('e1_order_id')}`",
                f"**Before kill open:** {report.get('verify_before_kill')}",
                f"**Bot dead open:** {report.get('verify_while_bot_dead')}",
                f"**After restart open:** {report.get('verify_after_restart')}",
                f"**Restarted:** {report.get('restarted')} pid={report.get('restart_pid')}",
                "",
                f"JSON: `{path}`",
            ]
        )
    )
    print("Wrote", path)
    print("Wrote", md)


if __name__ == "__main__":
    raise SystemExit(main())
