#!/usr/bin/env python3
"""Dig-further: layered bull re-entry arm on FLAT-KNOBS trial.

1) Re-runs breakout/layered stress (shared module + harness)
2) Merges flat-knobs primary conclusions
3) Writes dig report + updates trial REVIEW bundle
4) No live config writes

Spec: docs/research/BULL_REENTRY_LAYERED_SPEC.md
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TRIAL_ID = "ANALYST-REGIME-FLAT-KNOBS-20260730-TRIAL"
MASTER_ID = "ANALYST-REGIME-FLAT-KNOBS-20260730"
SPEC = "docs/research/BULL_REENTRY_LAYERED_SPEC.md"
STRESS_JSON = ROOT / "data/state/analyst_breakout_reentry_stress_latest.json"
FLAT_JSON = ROOT / "reports/REGIME_FLAT_KNOBS_TEST_2026-07-30.json"
REPORTS = ROOT / "reports"
DAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
OUT_MD = REPORTS / f"REGIME_FLAT_KNOBS_DIG_LAYERED_{DAY}.md"
OUT_JSON = REPORTS / f"REGIME_FLAT_KNOBS_DIG_LAYERED_{DAY}.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def run_stress() -> Dict[str, Any]:
    script = ROOT / "scripts/phase6/run_breakout_reentry_stress.py"
    env = {"OPENBLAS_CORETYPE": "GENERIC", **dict(**{k: v for k, v in __import__("os").environ.items()})}
    py = ROOT / ".venv/bin/python3"
    cmd = [str(py if py.exists() else "python3"), str(script)]
    subprocess.run(cmd, cwd=str(ROOT), check=False, env=env)
    data = _load(STRESS_JSON)
    if not data:
        raise RuntimeError("stress JSON missing after run")
    return data


def pick(pack: Dict[str, List[dict]], win: str, pid: str) -> Optional[dict]:
    for r in pack.get(win) or []:
        if r.get("policy_id") == pid:
            return r
    return None


def evaluate(stress: Dict[str, Any], flat: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    pa = stress.get("pack_a") or {}
    pb = stress.get("pack_b") or {}

    def snap(win: str) -> Dict[str, Any]:
        return {
            "current": pick(pb, win, "current_policy_regime_cash"),
            "layered_boost": pick(pb, win, "layered_brk_rsi_bear_flatb_bullboost"),
            "layered_pure": pick(pb, win, "layered_pure_brk_rsi_bear_flatb"),
            "layered_brk200": pick(pb, win, "layered_brk_rsi_bear_bullcap"),
            "brk75": pick(pa, win, "breakout_reentry_cap75"),
            "brk200": pick(pa, win, "breakout_reentry_cap200"),
            "only3015": pick(pa, win, "current_30d15_only"),
            "flat_always": pick(pa, win, "flat_b_always"),
        }

    windows = {
        w: snap(w)
        for w in (
            "full_sample",
            "live_overlap",
            "flat_chop",
            "bear_stress",
            "recent",
            "bull_ex",
        )
    }

    cur_f = windows["full_sample"]["current"] or {}
    lay_f = windows["full_sample"]["layered_boost"] or {}
    cur_lo = windows["live_overlap"]["current"] or {}
    lay_lo = windows["live_overlap"]["layered_boost"] or {}
    cur_be = windows["bear_stress"]["current"] or {}
    lay_be = windows["bear_stress"]["layered_boost"] or {}
    brk200_f = windows["full_sample"]["brk200"] or {}

    # Spec GO shadow checks
    checks = []

    def add(name: str, ok: bool, detail: str):
        checks.append({"name": name, "pass": ok, "detail": detail})

    if lay_f and cur_f:
        ret_ok = lay_f["total_return_pct"] >= cur_f["total_return_pct"] - 0.25
        dd_ok = lay_f["max_drawdown_pct"] >= cur_f["max_drawdown_pct"] - 2.0
        add(
            "full_sample_layered_vs_current",
            bool(ret_ok and dd_ok),
            f"lay ret={lay_f['total_return_pct']} dd={lay_f['max_drawdown_pct']} "
            f"cur ret={cur_f['total_return_pct']} dd={cur_f['max_drawdown_pct']}",
        )
    if lay_be and cur_be:
        add(
            "bear_dd_not_much_worse",
            lay_be["max_drawdown_pct"] >= cur_be["max_drawdown_pct"] - 3.0,
            f"lay dd={lay_be['max_drawdown_pct']} cur dd={cur_be['max_drawdown_pct']}",
        )
    if lay_lo and cur_lo:
        add(
            "live_overlap_not_disaster",
            lay_lo["total_return_pct"] >= cur_lo["total_return_pct"] - 1.0
            or lay_lo["max_drawdown_pct"] > cur_lo["max_drawdown_pct"] + 0.5,
            f"lay ret={lay_lo['total_return_pct']} dd={lay_lo['max_drawdown_pct']} "
            f"cur ret={cur_lo['total_return_pct']} dd={cur_lo['max_drawdown_pct']}",
        )
    if brk200_f:
        add(
            "reject_breakout_cap200_full_sample",
            brk200_f["total_return_pct"] < 0 or brk200_f["max_drawdown_pct"] < -3,
            f"brk200 full ret={brk200_f['total_return_pct']} dd={brk200_f['max_drawdown_pct']}",
        )

    shadow_core = all(
        c["pass"]
        for c in checks
        if c["name"]
        in (
            "full_sample_layered_vs_current",
            "bear_dd_not_much_worse",
            "live_overlap_not_disaster",
        )
    )
    # Live promote never from dig alone
    go_live = False
    # Shadow: core pass and not recommending brk200
    go_shadow = bool(shadow_core)

    flat_primary = None
    if isinstance(flat, dict):
        flat_primary = {
            "recommendation": flat.get("recommendation")
            or (flat.get("rec") or {}).get("enum"),
            "go_shadow": flat.get("go_shadow"),
            "primary_hypothesis_supported": flat.get("primary_hypothesis_supported"),
            "plain_english": (flat.get("executive") or flat.get("plain_english") or "")[:500],
        }
        # try nested
        if not flat_primary["recommendation"]:
            rec = flat.get("recommendation_block") or flat.get("rec") or {}
            if isinstance(rec, dict):
                flat_primary["recommendation"] = rec.get("enum") or rec.get("recommendation")

    # Combined recommendation for trial dig
    # Flat B rebalance stay; layered → propose_scoped_experiment (shadow path)
    if go_shadow:
        enum = "propose_scoped_experiment"
        plain = (
            "Keep flat option B rebalance (not rotation). ADD scoped shadow experiment: "
            "layered bull re-entry (bear veto + breakout + RSI 50–70 @ $75 rebalance; "
            "30d≥15% size-up $200 only). Do NOT live-edit regime_cash_policy. "
            "Reject breakout @$200 and 5d+RSI full bull flip."
        )
    else:
        enum = "continue_observe_only"
        plain = (
            "Keep flat B rebalance. Layered re-entry did not clear shadow gates on this dig — "
            "observe only; spec remains frozen for next OHLCV refresh."
        )

    return {
        "checks": checks,
        "go_shadow_layered": go_shadow,
        "go_live": go_live,
        "recommendation_enum": enum,
        "plain_english": plain,
        "windows": {
            w: {
                k: (
                    {
                        "ret": v.get("total_return_pct"),
                        "dd": v.get("max_drawdown_pct"),
                        "tin": v.get("time_in_market_pct"),
                        "mean_cap": v.get("mean_cap_usd"),
                    }
                    if v
                    else None
                )
                for k, v in rows.items()
            }
            for w, rows in windows.items()
        },
        "flat_primary": flat_primary,
        "spec": SPEC,
    }


def render_md(ev: Dict[str, Any], stress: Dict[str, Any]) -> str:
    lines = [
        f"# Regime Flat Knobs — DIG layered re-entry — {DAY}",
        "",
        f"**Trial:** `{TRIAL_ID}`  ",
        f"**Master:** `{MASTER_ID}`  ",
        f"**Spec:** `{SPEC}`  ",
        f"**Generated:** {_now()}  ",
        f"**Live config writes:** False",
        "",
        "## Plain English",
        "",
        ev["plain_english"],
        "",
        f"- **Dig recommendation enum:** `{ev['recommendation_enum']}`",
        f"- **Shadow layered?** **{ev['go_shadow_layered']}**",
        f"- **Live promote?** **{ev['go_live']}**",
        "",
        "### Flat primary (prior report)",
        "",
        f"```json\n{json.dumps(ev.get('flat_primary'), indent=2)}\n```",
        "",
        "## Spec gates",
        "",
    ]
    for c in ev["checks"]:
        flag = "PASS" if c["pass"] else "FAIL"
        lines.append(f"- **{flag}** `{c['name']}` — {c['detail']}")
    lines.extend(
        [
            "",
            "## Window snapshot (ret% / dd% / time-in%)",
            "",
        ]
    )
    for w, rows in (ev.get("windows") or {}).items():
        lines.append(f"### `{w}`")
        lines.append("")
        lines.append("| Arm | Ret% | MaxDD% | Time-in% | Mean cap$ |")
        lines.append("|-----|------|--------|----------|-----------|")
        for name, v in rows.items():
            if not v:
                continue
            lines.append(
                f"| {name} | {v['ret']} | {v['dd']} | {v['tin']} | {v['mean_cap']} |"
            )
        lines.append("")
    meta = stress.get("meta") or {}
    lines.extend(
        [
            "## Signal base rates",
            "",
            f"- Breakout share: **{meta.get('breakout_share_pct')}%** of bars",
            f"- Bull label (30d/15) share: **{meta.get('bull_share_pct')}%**",
            f"- Stress JSON: `{STRESS_JSON.relative_to(ROOT)}`",
            "",
            "## Must / must not",
            "",
            "- **Must:** re-entry size $75 rebalance; pair RSI/sent gates remain; param_audit clean before any shadow activate",
            "- **Must not:** live regime_cash_policy edit; breakout @$200 default; 5d+RSI bull flip",
            "",
            "## Decide",
            "",
            "```bash",
            f"cd {ROOT}",
            f"python3 phase6/research/trial_cycle.py decide {TRIAL_ID} {ev['recommendation_enum']} \\",
            f"  --note 'flat B rebalance keep; layered shadow per {OUT_MD.name}'",
            "```",
            "",
            f"_module:_ `phase6/research/bull_reentry_layered.py`",
            "",
        ]
    )
    return "\n".join(lines)


def update_trial(ev: Dict[str, Any]) -> None:
    from phase6.research.trial_cycle import load_trial, save_trial, write_review_request, reindex

    t = load_trial(TRIAL_ID)
    report_entry = {
        "phase": "offline_dig_layered",
        "path": str(OUT_MD.relative_to(ROOT)),
        "json": str(OUT_JSON.relative_to(ROOT)),
        "recommendation": ev["recommendation_enum"],
        "go_shadow": ev["go_shadow_layered"],
        "go_live": False,
        "spec": SPEC,
        "at": _now(),
        "plain_english": ev["plain_english"],
        "checks": ev["checks"],
    }
    t.setdefault("reports", []).append(report_entry)
    t["dig_layered_report"] = report_entry["path"]
    t["dig_layered_report_json"] = report_entry["json"]
    t["final_recommendation"] = ev["recommendation_enum"]
    t["final_report"] = report_entry["path"]
    t["final_report_json"] = report_entry["json"]
    t["final_report_at"] = _now()
    t.setdefault("notes", []).append(
        {"at": _now(), "text": f"dig layered → {report_entry['path']} rec={ev['recommendation_enum']} shadow={ev['go_shadow_layered']}"}
    )
    # stay REVIEW_PENDING
    if t.get("status") not in ("REVIEW_PENDING", "REPORT_READY"):
        t["status"] = "REVIEW_PENDING"
    save_trial(t)
    write_review_request(TRIAL_ID)
    reindex()


def update_handoff(ev: Dict[str, Any]) -> None:
    path = ROOT / f"handoffs/analyst/Handoff_{MASTER_ID}.md"
    extra = f"""

---

## DIG 2026-07-30 — Layered bull re-entry arm

**Spec:** `{SPEC}`  
**Module:** `phase6/research/bull_reentry_layered.py`  
**Dig report:** `{OUT_MD.relative_to(ROOT)}`  
**Stress:** `data/state/analyst_breakout_reentry_stress_latest.json`

### Extended hypothesis
Bear veto + breakout ON + BTC RSI∈[50,70] → cap **$75 rebalance**; BTC 30d≥15% → size-up **$200**. Catch more short bulls than 30d/15-only without full-size breakout.

### Dig result
- Enum: `{ev['recommendation_enum']}`
- Shadow layered: **{ev['go_shadow_layered']}**
- Live: **False**

{ev['plain_english']}
"""
    if path.exists():
        text = path.read_text()
        if "DIG 2026-07-30 — Layered" not in text:
            path.write_text(text.rstrip() + "\n" + extra)
    else:
        path.write_text(extra)


def patch_master(ev: Dict[str, Any]) -> None:
    master = ROOT / "docs/MASTER_TASK_TRACKING.md"
    if not master.exists():
        return
    text = master.read_text()
    marker = f"## {MASTER_ID}"
    note = (
        f"\n**DIG layered (2026-07-30):** `{OUT_MD.name}` → `{ev['recommendation_enum']}` "
        f"shadow_layered={ev['go_shadow_layered']} live=false. Spec: `{SPEC}`.\n"
    )
    if marker in text and "DIG layered (2026-07-30)" not in text:
        # insert after first status line of section
        idx = text.find(marker)
        # find end of first paragraph block
        nl = text.find("\n\n", idx)
        if nl > 0:
            text = text[:nl] + note + text[nl:]
            master.write_text(text)


def main() -> int:
    print("Running breakout/layered stress...")
    stress = run_stress()
    flat = _load(FLAT_JSON)
    ev = evaluate(stress, flat if isinstance(flat, dict) else None)
    payload = {
        "generated_at": _now(),
        "trial_id": TRIAL_ID,
        "master_id": MASTER_ID,
        "spec": SPEC,
        "policy_fingerprint": {
            "regime_cash_policy_sha256": _sha(ROOT / "config/regime_cash_policy.json"),
            "regime_knob_map_sha256": _sha(ROOT / "config/regime_knob_map.json"),
        },
        "evaluation": ev,
        "stress_meta": stress.get("meta"),
        "live_writes": False,
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n")
    OUT_MD.write_text(render_md(ev, stress))
    update_handoff(ev)
    update_trial(ev)
    patch_master(ev)
    print(f"Wrote {OUT_MD}")
    print(f"Wrote {OUT_JSON}")
    print(json.dumps({"recommendation": ev["recommendation_enum"], "go_shadow": ev["go_shadow_layered"], "checks": ev["checks"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
