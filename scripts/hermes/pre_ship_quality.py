#!/usr/bin/env python3
"""Pre-ship quality gate — catch class bugs before they hit the live book.

Exit 0: clean (stdout empty when PRE_SHIP_QUIET=1 — nightly fail-only Telegram)
Exit 2: P0 fail (print findings)
Exit 1: usage / import error

Brad GO 2026-09-09: Hermes environment quality loop.
"""
from __future__ import annotations

import ast
import inspect
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

MONEY_PY = [
    ROOT / "phase6/core/trade_ledger.py",
    ROOT / "phase6/core/runner_capital_events.py",
    ROOT / "phase6/core/regime_cash_policy.py",
    ROOT / "phase6/core/stop_loss_manager.py",
    ROOT / "phase6/core/sl_floor_ratchet.py",
    ROOT / "phase6/core/phase6_runner.py",
    ROOT / "trading/executor.py",
]

ISOLATION = [
    "scripts/phase6/test_isolation_process_tax_lockout.py",
    "scripts/phase6/test_isolation_sl_floor_ratchet.py",
    "scripts/phase6/test_isolation_post_sl_block_enforce.py",
    "phase6/core/test_isolation_buy_block_pairs.py",
    "phase6/core/test_isolation_ledger_write_path.py",
]


def _rg(pattern: str, paths: list[Path]) -> str:
    cmd = ["rg", "-n", "--glob", "*.py", pattern]
    cmd.extend(str(p) for p in paths)
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return (r.stdout or "").strip()


def check_trade_ledger_hours(fails: list[str]) -> None:
    try:
        from phase6.core.trade_ledger import TradeLedger

        sig = inspect.signature(TradeLedger.get_recent_trades)
        if "hours" not in sig.parameters:
            fails.append("P0 TradeLedger.get_recent_trades missing hours= (72h cooldown hole)")
    except Exception as e:
        fails.append(f"P0 cannot import TradeLedger.get_recent_trades: {e}")


def check_evaluate_wires_process_tax(fails: list[str]) -> None:
    src = (ROOT / "phase6/core/regime_cash_policy.py").read_text(encoding="utf-8")
    if "pair_process_tax_lockout_reasons" not in src or "def evaluate_buy_entry" not in src:
        fails.append("P0 evaluate_buy_entry missing pair_process_tax_lockout_reasons wire")
    if "collect_buy_block_pairs" not in src:
        fails.append("P0 evaluate_buy_entry missing collect_buy_block_pairs")


def check_swallowed_empty_list(fails: list[str]) -> None:
    """except Exception + return [] on money files — the hours= TypeError class."""
    needle_files = [
        ROOT / "phase6/core/phase6_runner.py",
        ROOT / "phase6/core/runner_capital_events.py",
        ROOT / "phase6/core/trade_ledger.py",
    ]
    for path in needle_files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as e:
            fails.append(f"P0 syntax {path.name}: {e}")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            # except Exception / except:
            is_broad = node.type is None or (
                isinstance(node.type, ast.Name) and node.type.id == "Exception"
            )
            if not is_broad:
                continue
            body = node.body
            if len(body) == 1 and isinstance(body[0], ast.Return):
                val = body[0].value
                if isinstance(val, ast.List) and len(val.elts) == 0:
                    fails.append(
                        f"P0 swallowed empty-list {path.relative_to(ROOT)}:{node.lineno} "
                        "(except Exception: return [] with no log — 72h hours= class)"
                    )


def check_waivers(fails: list[str]) -> None:
    p = ROOT / "data/state/buy_block_waivers.json"
    if not p.exists():
        return
    import json

    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        fails.append(f"P0 waivers JSON unreadable: {e}")
        return
    pairs = (raw.get("pairs") or {}) if isinstance(raw, dict) else {}
    for pair, meta in (pairs.items() if isinstance(pairs, dict) else []):
        if not isinstance(meta, dict):
            continue
        exp = meta.get("expires_ts")
        scope = str(meta.get("scope") or "post_tp").lower()
        if exp is None and scope in ("all", "*", "any"):
            fails.append(
                f"P0 waiver {pair} expires_ts=null scope={scope} "
                "(unlimited SL wipe — LINK 2026-09-09 class)"
            )


def check_config_cap_ssot(warns: list[str]) -> None:
    import json

    tc = ROOT / "config/trading_config_phase6.json"
    try:
        gs = (json.loads(tc.read_text()).get("global_settings") or {})
        cap = float(gs.get("rebalance_cap_usd") or 0)
        if cap not in (0.0, 75.0):
            warns.append(f"WARN global_settings.rebalance_cap_usd={cap} (live policy is usually 75)")
    except Exception:
        pass


def run_isolation(fails: list[str]) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env.setdefault("OPENBLAS_CORETYPE", "GENERIC")
    py = ROOT / ".venv/bin/python"
    exe = str(py) if py.exists() else sys.executable
    for rel in ISOLATION:
        path = ROOT / rel
        if not path.exists():
            fails.append(f"P0 missing isolation script {rel}")
            continue
        r = subprocess.run(
            [exe, str(path)],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if r.returncode != 0:
            tail = (r.stdout or "")[-400:] + (r.stderr or "")[-400:]
            fails.append(f"P0 isolation FAIL {rel} rc={r.returncode}\n{tail.strip()}")


def main() -> int:
    quiet = os.environ.get("PRE_SHIP_QUIET", "").strip() in ("1", "true", "yes")
    skip_iso = os.environ.get("PRE_SHIP_SKIP_ISOLATION", "").strip() in ("1", "true", "yes")
    fails: list[str] = []
    warns: list[str] = []
    check_trade_ledger_hours(fails)
    check_evaluate_wires_process_tax(fails)
    check_swallowed_empty_list(fails)
    check_waivers(fails)
    check_config_cap_ssot(warns)
    if not skip_iso:
        run_isolation(fails)

    if fails:
        print("PRE-SHIP QUALITY FAIL")
        for f in fails:
            print(f"- {f}")
        for w in warns:
            print(f"- {w}")
        print("See docs/AGENT_QUALITY_GATES.md")
        return 2
    if not quiet:
        print("PRE-SHIP QUALITY PASS")
        for w in warns:
            print(f"- {w}")
        if not skip_iso:
            print(f"isolation ok ({len(ISOLATION)} scripts)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.TimeoutExpired:
        print("PRE-SHIP QUALITY FAIL")
        print("- isolation timed out")
        raise SystemExit(2)
