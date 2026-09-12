#!/usr/bin/env python3
"""One-shot E2E platform validation after PC-01..03."""
from __future__ import annotations

import json
import os
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
now = datetime.now(timezone.utc)


def jload(rel: str):
    p = ROOT / rel
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"_error": str(e)}


def main() -> int:
    report = {
        "as_of_utc": now.isoformat(),
        "checks": [],
        "blockers": [],
        "gaps": [],
        "ok": [],
    }

    pid = None
    alive = False
    try:
        pid = int((ROOT / "data/state/phase6_runner.pid").read_text().strip().split()[0])
        os.kill(pid, 0)
        alive = True
    except Exception:
        alive = False
    report["checks"].append({"runner_alive": alive, "pid": pid})
    if alive:
        report["ok"].append(f"runner pid={pid}")
    else:
        report["blockers"].append("runner not alive")

    tr = jload("data/state/tryout_readiness_latest.json") or {}
    esp = jload("data/state/exit_stack_proof_latest.json") or {}
    bsd = jload("data/state/basket_swap_brad_decision.json") or {}
    fee = jload("data/state/fee_tier_snapshot_latest.json") or {}

    report["tryout"] = {
        "can_buy": tr.get("can_buy_before_next_rebalance"),
        "eligible": tr.get("eligible_tryout_pairs"),
        "floor": (tr.get("entry_floors") or {}).get("live_floor_used"),
        "sensor_broken": (tr.get("sensor_verdict") or {}).get("broken"),
        "mode": tr.get("sent_mode"),
        "cash": tr.get("cash_usd"),
    }
    g = esp.get("go_nogo") or {}
    w30 = (esp.get("windows") or {}).get("30d") or {}
    report["exits"] = {
        "headline": g.get("headline"),
        "tp_bank": w30.get("tp_bank_usd"),
        "sl_bank": w30.get("sl_bank_usd"),
        "tp_sl": w30.get("tp_vs_sl_count"),
        "blank": w30.get("blank_untagged"),
        "n_sell": w30.get("n_sell"),
    }
    report["paper"] = {
        "arm": bsd.get("preferred_arm"),
        "live_swaps": bsd.get("live_membership_swaps"),
    }
    report["fee_keys"] = list(fee.keys())[:12] if isinstance(fee, dict) else None

    if tr.get("can_buy_before_next_rebalance") is False:
        report["gaps"].append(
            {
                "id": "G-FUNNEL-SENT",
                "severity": "P0_ops",
                "title": "Tryout open but eng sent below floor — no seat can fill",
                "detail": (tr.get("plain_english") or "")[:240],
                "inhibits": "green-day pickup / tryout BUY→SL proof",
            }
        )
    if (tr.get("sensor_verdict") or {}).get("broken"):
        report["blockers"].append("sentiment sensor broken")
    else:
        report["ok"].append("sensor not broken")

    sl = float(w30.get("sl_bank_usd") or 0)
    tp = float(w30.get("tp_bank_usd") or 0)
    if sl < -1:
        report["gaps"].append(
            {
                "id": "G-EXIT-TAX",
                "severity": "P0_money",
                "title": "30d SL tax still material vs TP bank",
                "detail": (
                    f"SL ${sl:.2f} vs TP ${tp:.2f} counts {w30.get('tp_sl') or w30.get('tp_vs_sl_count')} "
                    f"n_sell={w30.get('n_sell')}"
                ),
                "inhibits": "month_path less-loss / exit quality trust",
            }
        )

    dq: deque = deque(maxlen=600)
    p = ROOT / "trades/phase6_trades.jsonl"
    if p.exists():
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    dq.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    def pts(r):
        s = r.get("timestamp") or r.get("ts")
        if not s:
            return None
        try:
            dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            return None

    since = now - timedelta(days=7)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    recent = [r for r in dq if (pts(r) or epoch) >= since]
    buys = [r for r in recent if str(r.get("side", "")).upper() == "BUY"]
    sells = [r for r in recent if str(r.get("side", "")).upper() == "SELL"]
    bag_b = sum(1 for r in buys if r.get("bag_id"))
    report["ledger_7d"] = {
        "buys": len(buys),
        "sells": len(sells),
        "buy_bag_id": f"{bag_b}/{len(buys)}",
    }
    if buys and bag_b / len(buys) < 0.5:
        report["gaps"].append(
            {
                "id": "G-BAGID-ADOPTION",
                "severity": "P1",
                "title": "Recent BUYs lack bag_id (need runner reload or no post-A2 fills)",
                "detail": f"{bag_b}/{len(buys)}",
                "inhibits": "live lot-bind proof",
            }
        )
    elif not buys:
        report["ok"].append("no 7d buys — bag_id N/A until seat")

    for gap in [
        {
            "id": "G-L2-DEPLOY",
            "severity": "P1",
            "title": "L2 deployability scorer missing (PC-04)",
            "detail": "no would-runner-buy on paper ADDs",
            "inhibits": "honest arm promote",
        },
        {
            "id": "G-LIMIT-EVIDENCE",
            "severity": "P1",
            "title": "Limit-first evidence starved (PC-05)",
            "detail": "zero tryout attempts → no fill-rate denominator",
            "inhibits": "execution maturity",
        },
        {
            "id": "G-ATTR-LOOP",
            "severity": "P1",
            "title": "Attribution weekly RT loop not staffed (PC-06)",
            "detail": "stamps exist in code; weekly table/process not closed",
            "inhibits": "learn tax vs edge",
        },
        {
            "id": "G-PROCESS-BOOK",
            "severity": "P1_watch",
            "title": "14d process book still WATCH (PC-09)",
            "detail": "need manufactured SL leakage calendar",
            "inhibits": "claim money-path complete",
        },
        {
            "id": "G-PROMOTE-GATE",
            "severity": "P2",
            "title": "Shadow→live promote gate packet missing (PC-08)",
            "detail": "auto_promote=false only",
            "inhibits": "safe scale",
        },
        {
            "id": "G-RISK-KERNEL",
            "severity": "P2_parked",
            "title": "Portfolio risk kernel multi-file (PC-07)",
            "detail": "caps/tryout/park not one SSOT",
            "inhibits": "multi-book",
        },
        {
            "id": "G-RUNNER-RESTART",
            "severity": "P0_ops",
            "title": "Runner may predate A1/A2 deploy",
            "detail": f"pid={pid}; restart to load bag_id+settle",
            "inhibits": "protect next tryout fill",
        },
    ]:
        report["gaps"].append(gap)

    if bsd.get("live_membership_swaps"):
        report["blockers"].append("live_membership_swaps true")
    else:
        report["ok"].append(f"paper_primary={bsd.get('preferred_arm')} swaps_off")

    sev = {
        "P0_money": 0,
        "P0_ops": 1,
        "P1": 2,
        "P1_watch": 3,
        "P2": 4,
        "P2_parked": 5,
    }
    report["gaps"].sort(key=lambda x: sev.get(x["severity"], 9))

    md = ROOT / "reports/PLATFORM_E2E_VALIDATION_20260911.md"
    lines = [
        f"# Platform E2E validation — {now.isoformat()}",
        "",
        "**SHA:** `dcb1bbb9` (PC-02/03) · A2 `cec08fd8`",
        "",
        "## Verdict",
        "",
        "**CONDITIONAL lab GO / money-path NO-GO scale.** Infra + integrity slices landed; "
        "funnel drought + exit tax + a few proof loops still inhibit ~5%/mo realization.",
        "",
        f"> tryout can_buy=`{tr.get('can_buy_before_next_rebalance')}` · {g.get('headline')}",
        "",
        "## OK",
        "",
    ]
    lines += [f"- {x}" for x in report["ok"]] + [""]
    if report["blockers"]:
        lines += ["## Blockers", ""] + [f"- {b}" for b in report["blockers"]] + [""]
    lines += ["## Ranked missing / inhibiting functionality", ""]
    for i, gap in enumerate(report["gaps"], 1):
        lines += [
            f"### {i}. [{gap['severity']}] {gap['title']}",
            f"- **id:** `{gap['id']}`",
            f"- **detail:** {gap['detail']}",
            f"- **inhibits:** {gap['inhibits']}",
            "",
        ]
    lines += [
        "## Snapshots",
        f"- tryout: `{json.dumps(report['tryout'])}`",
        f"- exits: `{json.dumps(report['exits'])}`",
        f"- ledger_7d: `{json.dumps(report['ledger_7d'])}`",
        f"- paper: `{json.dumps(report['paper'])}`",
        "",
        "## Staff next (recommended)",
        "1. Runner restart (A1/A2 load) — Brad OK",
        "2. PC-04 L2 deployability",
        "3. PC-05 limit-first counters (honest zero-attempt OK)",
        "4. PC-06 attribution weekly",
        "5. PC-09 14d process book watch",
        "6. Hold PC-07/08 until above green",
        "",
    ]
    md.write_text("\n".join(lines), encoding="utf-8")
    (ROOT / "data/state/platform_e2e_validation_latest.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print("wrote", md)
    print("blockers", report["blockers"])
    print("top", [g["id"] for g in report["gaps"][:6]])
    print("can_buy", tr.get("can_buy_before_next_rebalance"), "alive", alive)
    print("ledger", report["ledger_7d"])
    print("exits", report["exits"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
