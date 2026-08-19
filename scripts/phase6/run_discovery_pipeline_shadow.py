#!/usr/bin/env python3
"""
PAIR-DISCOVERY pipeline (shadow only) — inject dynamic trade candidates safely.

Steps
-----
1. Discovery funnel (public market data; **0 sentiment**)
2. RSI warm for top promote-eligible contenders only (merge into rsi_cache; no wipe)
3. Pool cycling shadow (score + propose weak→strong; **never apply live config**)

Anti-bleed (hard)
-----------------
- Does NOT mutate trading_config_phase6.json
- Does NOT place orders
- Cycler sticky BTC/ETH; max 1 swap proposal; holdings prefer flat ejects
- Pump brake: discovery contenders with insane 24h ret flagged / optional drop
- X/Reddit sentiment never called here

Exit codes
----------
0 = ran clean (even if 0 swaps)
1 = hard failure in a required stage
"""
from __future__ import annotations

from dataclasses import asdict
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.pair_discovery import (  # noqa: E402
    CONTENDERS_JSON,
    DiscoveryConfig,
    load_discovery_contender_ids,
    report_plain_english,
    run_discovery,
)
from phase6.core.pool_cycling import (  # noqa: E402
    PoolCyclingConfig,
    report_to_plain_english,
    run_pool_cycling,
)
from phase6.core.paths import PROJECT_ROOT  # noqa: E402

STATE = PROJECT_ROOT / "data" / "state"
PIPELINE_LATEST = STATE / "discovery_pipeline_latest.json"
PIPELINE_JSONL = STATE / "discovery_pipeline_runs.jsonl"
REFRESH_SCRIPT = PROJECT_ROOT / "scripts" / "refresh_rsi_prices.py"

# Anti-bleed: drop hyper-pumps from promote set before RSI/cycle (still logged)
DEFAULT_MAX_RET_24H_FOR_PROMOTE = 0.80  # 80% daily — above = casino tape


def _filter_contenders_pump_brake(
    contenders: List[Dict[str, Any]],
    max_ret_24h: float,
) -> List[Dict[str, Any]]:
    kept: List[Dict[str, Any]] = []
    for c in contenders:
        ret = float(c.get("ret_24h") or 0.0)
        if abs(ret) > max_ret_24h:
            c = dict(c)
            c["promote_eligible"] = False
            reasons = list(c.get("reasons") or [])
            reasons.append(f"pump_brake_|ret24h|>{max_ret_24h:.0%}")
            c["reasons"] = reasons
            kept.append(c)
            continue
        if c.get("promote_eligible"):
            kept.append(c)
        else:
            kept.append(c)
    return kept


def _rewrite_contenders_file(contenders: List[Dict[str, Any]], ts: str) -> List[str]:
    eligible = [
        c["product_id"]
        for c in contenders
        if c.get("promote_eligible")
    ]
    STATE.mkdir(parents=True, exist_ok=True)
    CONTENDERS_JSON.write_text(
        json.dumps(
            {
                "ts": ts,
                "contenders": contenders,
                "promote_eligible": eligible,
                "note": (
                    "Pipeline post pump-brake. Feed to pool_cycling. Shadow only."
                ),
            },
            indent=2,
        )
        + "\n"
    )
    return eligible


def _warm_rsi(pairs: List[str], dry_run: bool = False) -> Dict[str, Any]:
    if not pairs:
        return {"ok": True, "skipped": True, "pairs": [], "returncode": 0, "stdout": "no pairs"}
    cmd = [sys.executable, str(REFRESH_SCRIPT), "--pairs", ",".join(pairs), "--merge"]
    if dry_run:
        cmd.append("--dry-run")
    proc = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=300,
    )
    return {
        "ok": proc.returncode == 0,
        "skipped": False,
        "pairs": pairs,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[-4000:],
        "stderr": (proc.stderr or "")[-2000:],
    }


def run_pipeline(
    contenders_n: int = 5,
    min_volume_usd: float = 2_000_000.0,
    max_ret_24h: float = DEFAULT_MAX_RET_24H_FOR_PROMOTE,
    skip_rsi: bool = False,
    skip_cycle: bool = False,
    dry_run_rsi: bool = False,
    write: bool = True,
) -> Dict[str, Any]:
    ts = datetime.now(timezone.utc).isoformat()
    out: Dict[str, Any] = {
        "timestamp": ts,
        "mode": "shadow",
        "anti_bleed": {
            "mutates_config": False,
            "places_orders": False,
            "sentiment_calls": 0,
            "max_swaps_proposed": 1,
            "sticky": ["BTC-USD", "ETH-USD"],
            "pump_brake_abs_ret_24h": max_ret_24h,
        },
        "stages": {},
        "plain_english": "",
        "ok": True,
    }

    # --- Stage 1: discovery ---
    dcfg = DiscoveryConfig(
        min_quote_volume_24h_usd=min_volume_usd,
        contender_top_n=max(contenders_n, 8),  # fetch a few extra then brake
        exclude_active_from_contenders=True,
        run_deep=False,
    )
    dreport = run_discovery(cfg=dcfg, write=write)
    contenders = list(dreport.contenders)
    contenders = _filter_contenders_pump_brake(contenders, max_ret_24h)
    # Keep top N promote-eligible after brake; still store full list
    eligible = _rewrite_contenders_file(contenders, ts) if write else [
        c["product_id"] for c in contenders if c.get("promote_eligible")
    ]
    eligible = eligible[:contenders_n]

    out["stages"]["discovery"] = {
        "universe_n": dreport.universe_n,
        "prequal_n": dreport.prequal_n,
        "quality_n": dreport.quality_n,
        "contenders_raw": [c.get("product_id") for c in dreport.contenders],
        "promote_eligible_after_brake": eligible,
        "sentiment_calls": dreport.sentiment_calls,
        "note": dreport.note,
    }
    pe_lines = [
        "=== Discovery pipeline (SHADOW) ===",
        report_plain_english(dreport),
        "",
        f"Pump brake |ret24h|>{max_ret_24h:.0%}: promote set → {eligible or '(none)'}",
    ]

    # --- Stage 2: RSI warm contenders only ---
    if skip_rsi:
        warm = {"ok": True, "skipped": True, "pairs": eligible}
    else:
        warm = _warm_rsi(eligible, dry_run=dry_run_rsi)
        if not warm.get("ok") and eligible:
            out["ok"] = False
    out["stages"]["rsi_warm"] = {
        k: warm.get(k)
        for k in ("ok", "skipped", "pairs", "returncode")
    }
    if warm.get("stdout"):
        out["stages"]["rsi_warm"]["stdout_tail"] = warm["stdout"][-1500:]
    pe_lines.append("")
    pe_lines.append(
        f"RSI warm: {'SKIP' if warm.get('skipped') else ('OK' if warm.get('ok') else 'FAIL')} "
        f"pairs={warm.get('pairs')}"
    )

    # --- Stage 3: pool cycling shadow ---
    cycle_summary: Dict[str, Any] = {"skipped": True}
    if not skip_cycle:
        ccfg = PoolCyclingConfig(max_swaps=1)
        creport = run_pool_cycling(
            cfg=ccfg,
            write_log=write,
            write_proposed=write,
            apply_config=False,  # HARD anti-bleed
        )
        cycle_summary = {
            "skipped": False,
            "swaps": list(creport.swaps),  # already list[dict]
            "n_swaps": len(creport.swaps),
            "active": creport.active_pool,
            "outside": creport.outside_active,
            "note": creport.note,
        }
        pe_lines.append("")
        pe_lines.append(report_to_plain_english(creport))
    out["stages"]["pool_cycling"] = cycle_summary

    pe_lines.append("")
    pe_lines.append(
        "Anti-bleed: no config write, no orders, no X/Reddit. "
        "Review swaps in data/state/pool_cycling_latest.json before any promote."
    )
    out["plain_english"] = "\n".join(pe_lines)
    out["promote_eligible"] = eligible
    out["swaps_proposed"] = cycle_summary.get("swaps") or []

    if write:
        STATE.mkdir(parents=True, exist_ok=True)
        PIPELINE_LATEST.write_text(json.dumps(out, indent=2) + "\n")
        with open(PIPELINE_JSONL, "a") as f:
            f.write(
                json.dumps(
                    {
                        "ts": ts,
                        "ok": out["ok"],
                        "eligible": eligible,
                        "n_swaps": len(out["swaps_proposed"]),
                        "swaps": [
                            f"{s.get('remove')}→{s.get('add')}"
                            for s in out["swaps_proposed"]
                        ],
                    }
                )
                + "\n"
            )
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Discovery→RSI warm→cycle shadow pipeline")
    p.add_argument("--contenders", type=int, default=5)
    p.add_argument("--min-volume-usd", type=float, default=2_000_000.0)
    p.add_argument(
        "--max-ret-24h",
        type=float,
        default=DEFAULT_MAX_RET_24H_FOR_PROMOTE,
        help="Pump brake: abs 24h return above this drops promote eligibility",
    )
    p.add_argument("--skip-rsi", action="store_true")
    p.add_argument("--skip-cycle", action="store_true")
    p.add_argument("--dry-run-rsi", action="store_true")
    p.add_argument("--no-write", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    result = run_pipeline(
        contenders_n=args.contenders,
        min_volume_usd=args.min_volume_usd,
        max_ret_24h=args.max_ret_24h,
        skip_rsi=args.skip_rsi,
        skip_cycle=args.skip_cycle,
        dry_run_rsi=args.dry_run_rsi,
        write=not args.no_write,
    )
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(result["plain_english"])
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
