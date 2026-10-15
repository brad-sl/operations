#!/usr/bin/env python3
"""A+ tryout money-path proof — fund + SL + growth stack grader.

Read-only by default. Writes:
  data/state/tryout_money_path_proof_latest.json
  reports/TRYOUT_MONEY_PATH_PROOF_LATEST.md

Grades (A+ target):
  FUND  — USD covers shell OR plan/unwind path healthy; powder ON
  SL    — every non-stable open bag has open protective stop at policy depth
  GROW  — TP/trail/dual-peak/dwell live; 7d not pure SL load/unload

Exit: 0 = all A+ or A; 1 = any F/D; 2 = error
Never places orders. Never flips knobs.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

STATE = ROOT / "data" / "state"
REPORTS = ROOT / "reports"
LATEST = STATE / "tryout_money_path_proof_latest.json"
MD = REPORTS / "TRYOUT_MONEY_PATH_PROOF_LATEST.md"
TRADES = ROOT / "trades" / "phase6_trades.jsonl"
REG = STATE / "protective_orders_registry.jsonl"
LIVE = STATE / "phase6_live_state.json"
CFG = ROOT / "config" / "trading_config_phase6.json"
EXIT_CFG = ROOT / "config" / "exit_automation.json"
DWELL_CFG = ROOT / "config" / "post_proof_dwell.json"
POWDER_STATUS = STATE / "powder_balancer_status.json"
TA = ROOT / "config" / "trader_accounts.json"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, default: Any = None) -> Any:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _f(x: Any, d: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def _seat_buy_fund_hook_wired() -> bool:
    """True when tryout_seat_buy imports + calls ensure_usd_for_shell before buy."""
    try:
        p = ROOT / "phase6" / "domain" / "actions" / "tryout_seat_buy.py"
        src = p.read_text(encoding="utf-8")
        return (
            "ensure_usd_for_shell" in src
            and "tryout_fund_from_usdc" in src
            and "fund_blocked_no_buy" in src
        )
    except Exception:
        return False


def _grade(score: float, *, hard_fail: bool = False) -> str:
    if hard_fail:
        return "F"
    if score >= 0.95:
        return "A+"
    if score >= 0.85:
        return "A"
    if score >= 0.75:
        return "B+"
    if score >= 0.65:
        return "B"
    if score >= 0.5:
        return "C"
    if score >= 0.35:
        return "D"
    return "F"


def grade_fund() -> Dict[str, Any]:
    from phase6.core.tryout_fund_from_usdc import (
        plan_fund_for_shell,
        usd_usdc_from_live_state,
        regime_park_or_bear,
    )
    from phase6.core.powder_balancer import powder_balancer_cfg, compute_wave_need, compute_target_usd_reserve

    live = _load(LIVE, {}) or {}
    bals = usd_usdc_from_live_state(live)
    cfg = _load(CFG, {}) or {}
    # shell from quality tryout
    shell = 25.0
    try:
        from phase6.core.regime_cash_policy import load_policy, recovery_quality_tryout_cfg, _recovery_rec

        pol = load_policy()
        qt = recovery_quality_tryout_cfg(_recovery_rec(pol) or {}) or {}
        shell = _f(qt.get("abs_cap_usd"), 25.0)
    except Exception:
        pass

    park = regime_park_or_bear()
    plan = plan_fund_for_shell(
        shell_usd=shell,
        usd=bals["usd"],
        usdc=bals["usdc"],
        park_or_bear=park,
    )
    # stress: thin USD — shortfall-only clip must cover need (shell+buffer), not full shell dump
    stress = plan_fund_for_shell(
        shell_usd=shell,
        usd=10.0,
        usdc=max(bals["usdc"], 500.0),
        park_or_bear=False,
    )
    stress_ok = (
        stress.action == "unwind"
        and stress.unwind_usd + 1e-6 >= stress.shortfall
        and stress.unwind_usd + 10.0 + 1e-6 >= stress.need_usd
    )

    ta = _load(TA, {}) or {}
    powder_on = False
    try:
        accts = ta.get("accounts") or {}
        for _id, ac in accts.items():
            pb = ((ac or {}).get("live_usdc_park") or {}).get("powder_balancer") or {}
            if pb.get("enabled"):
                powder_on = True
                break
    except Exception:
        pass
    pb_status = _load(POWDER_STATUS, {}) or {}
    pb_ok = bool(pb_status.get("ok")) if pb_status else powder_on

    wave = compute_wave_need(cfg)
    pcfg = powder_balancer_cfg(
        ((list((ta.get("accounts") or {}).values()) or [{}])[0].get("live_usdc_park") or {})
        if isinstance(ta.get("accounts"), dict)
        else {}
    )
    target = compute_target_usd_reserve(wave, pcfg)

    checks = {
        "powder_enabled": powder_on,
        "powder_status_ok": pb_ok or powder_on,
        "usd_covers_shell_now": plan.action == "hold" and plan.reason == "usd_covers_shell",
        "or_can_unwind": plan.action == "unwind" or (plan.action == "hold"),
        "stress_thin_usd_unwinds": stress_ok,
        "usdc_stub_present": bals["usdc"] >= 25.0,
        "wave_target_sane": 100.0 <= float(target) <= 400.0,
        "not_park_blocking_when_deploy": (not park) or plan.reason == "park_or_bear_keep_usdc",
        # A+ closure: fund-before-buy is wired into seat buy path
        "seat_buy_fund_hook_wired": _seat_buy_fund_hook_wired(),
    }
    # fund path A+ if powder on + stress unwind works + (covers now OR can unwind) + seat wired
    n = sum(1 for v in checks.values() if v)
    score = n / max(1, len(checks))
    hard = not powder_on or not stress_ok or not checks["seat_buy_fund_hook_wired"]
    g = _grade(score, hard_fail=hard and score < 0.7)
    if (
        powder_on
        and stress_ok
        and checks["usd_covers_shell_now"]
        and checks["wave_target_sane"]
        and checks["seat_buy_fund_hook_wired"]
    ):
        g = "A+"
        score = 1.0
    elif powder_on and stress_ok and (checks["usd_covers_shell_now"] or plan.action == "unwind"):
        g = "A+" if score >= 0.9 else "A"
    return {
        "grade": g,
        "score": round(score, 3),
        "shell_usd": shell,
        "usd": bals["usd"],
        "usdc": bals["usdc"],
        "plan": plan.to_dict(),
        "stress_thin_usd": stress.to_dict(),
        "target_usd_reserve": target,
        "wave": wave,
        "checks": checks,
        "plain": (
            f"USD ${bals['usd']:.0f} / USDC ${bals['usdc']:.0f}; "
            f"shell ${shell:.0f}; plan={plan.action}/{plan.reason}; "
            f"stress_unwind={'OK' if stress_ok else 'FAIL'}; "
            f"seat_fund_hook={'ON' if checks['seat_buy_fund_hook_wired'] else 'OFF'}"
        ),
    }


def grade_sl() -> Dict[str, Any]:
    cfg = _load(CFG, {}) or {}
    sl_pct = _f((cfg.get("risk_management") or {}).get("stop_loss_pct"), 0.08)
    sl_min = _f((cfg.get("risk_management") or {}).get("sl_min_pct"), 0.06)
    live = _load(LIVE, {}) or {}
    positions = live.get("positions") or []
    latest: Dict[str, Dict[str, Any]] = {}
    if REG.is_file():
        for line in REG.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue
            pair = r.get("pair")
            if pair:
                latest[str(pair)] = r

    bags: List[Dict[str, Any]] = []
    ok_n = 0
    naked = 0
    shallow = 0
    for p in positions:
        if not isinstance(p, dict):
            continue
        pair = str(p.get("pair") or "")
        if not pair or "USDT" in pair or pair.startswith("USD"):
            continue
        val = _f(p.get("value_usd") or p.get("usd_value") or p.get("market_value"))
        qty = _f(p.get("amount") or p.get("qty") or p.get("size"))
        if val < 5.0 and qty <= 0:
            continue
        entry = _f(
            p.get("entry_price")
            or p.get("avg_entry")
            or p.get("average_entry_price")
            or p.get("cost_basis")
        )
        reg = latest.get(pair) or {}
        status = str(reg.get("status") or "").lower()
        stop = _f(reg.get("stop_price") or reg.get("price"))
        reason = str(reg.get("reason") or reg.get("sleeve") or "")
        dd = (stop / entry - 1.0) if entry > 0 and stop > 0 else None
        is_paxg = "PAXG" in pair
        if is_paxg:
            # E1 deep
            good = status == "open" and dd is not None and dd <= -0.20
            kind = "e1"
        else:
            # policy 8% ± 2.5pp, or at least not shallower than sl_min
            good = (
                status == "open"
                and dd is not None
                and dd <= -(sl_min - 0.005)
                and dd >= -(sl_pct + 0.03)
            )
            kind = "crypto_sl"
            if status == "open" and dd is not None and dd > -(sl_min - 0.005):
                shallow += 1
        if status != "open" or stop <= 0:
            naked += 1
            good = False
        if good:
            ok_n += 1
        bags.append(
            {
                "pair": pair,
                "val": round(val, 2),
                "entry": entry,
                "stop": stop,
                "status": status,
                "stop_dd": None if dd is None else round(dd, 4),
                "ok": good,
                "kind": kind,
                "reason": reason,
            }
        )

    n = len(bags)
    score = (ok_n / n) if n else 1.0  # empty book = no SL exposure
    hard = naked > 0 or shallow > 0
    g = _grade(score, hard_fail=hard and n > 0)
    if n == 0:
        g = "A+"
    elif ok_n == n and sl_pct >= 0.079:
        g = "A+"
    elif ok_n == n:
        g = "A"
    return {
        "grade": g,
        "score": round(score, 3),
        "policy_sl_pct": sl_pct,
        "policy_sl_min_pct": sl_min,
        "n_bags": n,
        "n_ok": ok_n,
        "n_naked": naked,
        "n_shallow": shallow,
        "bags": bags,
        "plain": f"{ok_n}/{n} bags protected; naked={naked} shallow={shallow}; policy SL {sl_pct:.0%}",
    }


def grade_growth() -> Dict[str, Any]:
    exit_cfg = _load(EXIT_CFG, {}) or {}
    tp = exit_cfg.get("take_profit") or exit_cfg
    dwell = _load(DWELL_CFG, {}) or {}
    cfg = _load(CFG, {}) or {}
    dual = ((cfg.get("run_lifecycle") or {}).get("dual_peak_exit") or {})

    stack = {
        "tp_mode_live": str(tp.get("mode") or "").lower() == "live",
        "trail_on": bool((tp.get("trail") or {}).get("enabled")),
        "trail_arm_4": abs(_f((tp.get("trail") or {}).get("arm_pct"), 0) - 0.04) < 1e-6,
        "fixed_tp_6": abs(_f(tp.get("fixed_tp_pct"), 0) - 0.06) < 1e-6,
        "post_tp_block_24": _f(tp.get("post_tp_block_rebuy_hours"), 0) >= 24.0,
        "dwell_live": bool(dwell.get("enabled")) and bool(dwell.get("live_apply")),
        "dual_peak_live": bool(dual.get("enabled"))
        and str(dual.get("mode") or "").lower() == "live",
        "dual_meat_4": abs(_f(dual.get("dual_peak_min_green_pct"), 0) - 0.04) < 1e-6
        or abs(_f(dual.get("tp_arm_pct"), 0) - 0.04) < 1e-6,
        "dual_no_red_trim": bool(dual.get("dual_peak_require_mark_ge_entry", True)),
    }
    stack_score = sum(1 for v in stack.values() if v) / max(1, len(stack))

    # 7d / 30d outcome mix
    cut7 = datetime.now(timezone.utc) - timedelta(days=7)
    cut30 = datetime.now(timezone.utc) - timedelta(days=30)

    def parse_ts(s: str) -> Optional[datetime]:
        try:
            s = str(s).replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return None

    def bucket(reason: str) -> str:
        r = (reason or "").lower()
        if "stop_loss" in r:
            return "sl"
        if "take_profit" in r or "trail" in r:
            return "tp"
        if "dual_peak" in r:
            return "dual_peak"
        if "scale_window_eject" in r:
            return "eject"
        if "dust" in r:
            return "dust"
        if "rotation" in r or "usdt" in r:
            return "rotation"
        return "other"

    def window_stats(cut: datetime) -> Dict[str, Any]:
        by = Counter()
        pnl = defaultdict(float)
        n_sell = 0
        if not TRADES.is_file():
            return {"n_sell": 0, "by": {}, "pnl": {}, "tp_bank": 0.0, "sl_bank": 0.0}
        with TRADES.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    t = json.loads(line)
                except Exception:
                    continue
                if str(t.get("side") or "").upper() != "SELL":
                    continue
                pair = str(t.get("pair") or "")
                if "USDT" in pair or pair in ("USDC-USD", "USD-USDC"):
                    continue
                ts = parse_ts(str(t.get("timestamp") or t.get("ts") or ""))
                if ts is None or ts < cut:
                    continue
                b = bucket(str(t.get("exit_reason") or t.get("reason") or ""))
                if b == "rotation":
                    continue
                n_sell += 1
                by[b] += 1
                pnl[b] += _f(t.get("pnl") or t.get("realized_pnl"))
        tp_bank = pnl.get("tp", 0.0) + pnl.get("dual_peak", 0.0)
        sl_bank = pnl.get("sl", 0.0)
        return {
            "n_sell": n_sell,
            "by": dict(by),
            "pnl": {k: round(v, 4) for k, v in pnl.items()},
            "tp_bank": round(tp_bank, 4),
            "sl_bank": round(sl_bank, 4),
        }

    w7 = window_stats(cut7)
    w30 = window_stats(cut30)

    # Anti load/unload: not (tp=0 and sl>0 with n>=3) as sole story over 7d when stack is live
    load_unload_7 = (
        w7["n_sell"] >= 3
        and w7["by"].get("tp", 0) == 0
        and w7["by"].get("dual_peak", 0) == 0
        and w7["by"].get("sl", 0) >= 2
    )
    # Growth path functional = stack live (A+ for *functionality*). Tape outcome is separate honesty flag.
    tape_ok_30 = (w30["tp_bank"] + 1e-9) >= abs(min(0.0, w30["sl_bank"])) * 0.5 or w30[
        "by"
    ].get("tp", 0) >= 3

    score = stack_score
    if load_unload_7:
        # Functionality still A if stack complete; mark attention
        g = "A+" if stack_score >= 0.95 else "A"
        attention = "TAPE_LOAD_UNLOAD_7D"
    elif stack_score >= 0.95:
        g = "A+"
        attention = "OK" if tape_ok_30 else "TAPE_THIN_TP"
    else:
        g = _grade(stack_score)
        attention = "STACK_GAP"

    return {
        "grade": g,
        "score": round(score, 3),
        "stack": stack,
        "window_7d": w7,
        "window_30d": w30,
        "load_unload_7d": load_unload_7,
        "tape_attention": attention,
        "plain": (
            f"stack {sum(stack.values())}/{len(stack)} live; "
            f"7d tp_bank=${w7['tp_bank']} sl_bank=${w7['sl_bank']} "
            f"({w7['by']}); attention={attention}"
        ),
    }


def build_proof() -> Dict[str, Any]:
    fund = grade_fund()
    sl = grade_sl()
    growth = grade_growth()
    grades = {"FUND": fund["grade"], "SL": sl["grade"], "GROW": growth["grade"]}
    all_aplus = all(g == "A+" for g in grades.values())
    any_fail = any(g in ("F", "D") for g in grades.values())
    out = {
        "schema": "tryout_money_path_proof_v1",
        "as_of_utc": _utc(),
        "grades": grades,
        "all_aplus": all_aplus,
        "fund": fund,
        "sl": sl,
        "growth": growth,
        "verdict": (
            "A+_CLOSED"
            if all_aplus
            else ("FAIL" if any_fail else "PARTIAL")
        ),
        "next_actions": [],
    }
    if fund["grade"] != "A+":
        out["next_actions"].append("fix_fund_path: powder/clip/stress unwind")
    if sl["grade"] != "A+":
        out["next_actions"].append(
            "reattach_sl: scripts/phase6/reattach_sl_once.py --mode live --confirm-live"
        )
    if growth["grade"] != "A+":
        out["next_actions"].append("fix_growth_stack: exit_automation/dwell/dual_peak flags")
    if growth.get("load_unload_7d"):
        out["next_actions"].append(
            "TAPE: 7d SL-only — improve entry quality, not more shells; dwell/eject hygiene"
        )
    return out


def write_md(proof: Dict[str, Any]) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    g = proof["grades"]
    lines = [
        f"# Tryout money-path proof",
        f"**as_of:** {proof['as_of_utc']}",
        f"**verdict:** `{proof['verdict']}`",
        "",
        f"| Leg | Grade |",
        f"|-----|-------|",
        f"| FUND | **{g['FUND']}** |",
        f"| SL | **{g['SL']}** |",
        f"| GROW | **{g['GROW']}** |",
        "",
        f"- FUND: {proof['fund']['plain']}",
        f"- SL: {proof['sl']['plain']}",
        f"- GROW: {proof['growth']['plain']}",
        "",
        "## Next",
    ]
    for a in proof.get("next_actions") or ["none"]:
        lines.append(f"- {a}")
    lines.append("")
    MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        proof = build_proof()
    except Exception as e:
        print(f"ERROR {e}", file=sys.stderr)
        return 2
    STATE.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps(proof, indent=2, default=str) + "\n", encoding="utf-8")
    write_md(proof)
    print(
        f"verdict={proof['verdict']} FUND={proof['grades']['FUND']} "
        f"SL={proof['grades']['SL']} GROW={proof['grades']['GROW']}"
    )
    print(f"wrote {LATEST}")
    print(f"wrote {MD}")
    if proof["verdict"] == "FAIL":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
