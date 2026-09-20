#!/usr/bin/env python3
"""PLAN-BEAR-PARK-001 offline runner — park vs tactical on bear tape + live fingerprint.

No live config writes. Reuses historical dig premise math and stamps a
live-regime confirm board for the current bear episode.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research import run_regime_bear_bull_historical_dig as dig  # noqa: E402

REPORTS = ROOT / "reports"
STATE = ROOT / "data" / "state"
POLICY = ROOT / "config" / "regime_cash_policy.json"
STATUS = STATE / "regime_cash_status.json"
DAY = datetime.now(timezone.utc).strftime("%Y%m%d")
OUT_STEM = f"REGIME_BEAR_PARK_TEST_{DAY}"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _policy_hash() -> Dict[str, Any]:
    raw = POLICY.read_bytes() if POLICY.exists() else b""
    return {
        "path": str(POLICY.relative_to(ROOT)) if POLICY.exists() else None,
        "sha256": hashlib.sha256(raw).hexdigest() if raw else None,
        "bytes": len(raw),
    }


def _live_fingerprint() -> Dict[str, Any]:
    st: Dict[str, Any] = {}
    if STATUS.exists():
        try:
            st = json.loads(STATUS.read_text())
        except Exception as e:
            st = {"error": str(e)}
    det = st.get("detector") or {}
    return {
        "as_of": st.get("as_of") or st.get("written_at"),
        "regime": st.get("regime"),
        "strategy_mode": st.get("strategy_mode"),
        "allow_new_buys": st.get("allow_new_buys"),
        "rebalance_cap_usd": st.get("rebalance_cap_usd"),
        "target_max_util_pct": st.get("target_max_util_pct"),
        "min_cash_reserve_pct": st.get("min_cash_reserve_pct"),
        "confidence": st.get("confidence"),
        "label": st.get("label"),
        "btc_return_pct": det.get("btc_return_pct"),
        "regime_layer": st.get("regime_layer") or det.get("regime_layer"),
        "entry": st.get("entry"),
        "live_is_bear": str(st.get("regime") or "").lower().startswith("bear"),
    }


def _run_bear_paths() -> Dict[str, Any]:
    closes = dig._load_closes(dig.LONG_BTC)
    pol = json.loads(POLICY.read_text()) if POLICY.exists() else {}
    det = pol.get("detector") or {}
    thr = det.get("thresholds") or {}
    bull = float(thr.get("bull_return_pct", 15.0))
    bear = float(thr.get("bear_return_pct", -10.0))
    flat = float(thr.get("flat_abs_pct", 8.0))
    lookback = int(det.get("lookback_days") or dig.LOOKBACK)
    series = dig._rolling_series(closes, lookback, bull, bear, flat)
    usdc_apy = dig.load_usdc_apy_pct()
    usdc_daily = (1.0 + float(usdc_apy) / 100.0) ** (1.0 / 365.25) - 1.0
    bear_rets = dig._day_returns(series, "bear")
    bear_util = 0.25
    paths = {
        "full_park_usdc": dig._path(bear_rets, 0.0, usdc_daily, "full_park_usdc"),
        "tactical_util_0_25": dig._path(bear_rets, bear_util, usdc_daily, f"tactical_util_{bear_util}"),
        "flat_like_0_65": dig._path(bear_rets, 0.65, usdc_daily, "flat_like_0_65"),
        "full_btc": dig._path(bear_rets, 1.0, usdc_daily, "full_btc"),
    }
    eps = dig._episodes(series, "bear")
    premise = dig._judge_bear(paths, n_days=len(bear_rets), n_eps=len(eps))
    return {
        "n_closes": len(closes),
        "n_bear_days": len(bear_rets),
        "n_bear_episodes": len(eps),
        "bear_paths": paths,
        "bear_premise": premise,
        "detector_thresholds": {"bull": bull, "bear": bear, "flat": flat, "lookback": lookback},
    }


def _outcome_from_bear(bear_block: Dict[str, Any], n_days: int, n_eps: int) -> Dict[str, Any]:
    primary_pass = bool(bear_block.get("primary_pass"))
    # dig._judge_bear uses keys: class / plain (not outcome_class / plain_english)
    outcome_class = str(
        bear_block.get("class")
        or bear_block.get("outcome_class")
        or "process_incomplete"
    )
    plain = str(
        bear_block.get("plain")
        or bear_block.get("plain_english")
        or bear_block.get("note")
        or ""
    )
    # success_criteria min_n_trades=15 — labeled days as N proxy for park test
    if n_days < 15 and not primary_pass:
        outcome_class = "inconclusive_sparse_N"
        primary_pass = False
    return {
        "class": outcome_class,
        "primary_pass": primary_pass,
        "enum": bear_block.get("enum")
        or ("propose_scoped_experiment" if primary_pass else "hold_measure"),
        "plain_english": plain,
        "n_labeled_days": n_days,
        "n_episodes": n_eps,
        "live_promote_allowed": False,
        "follow_on": "scoped_shadow" if primary_pass else "collect_more",
    }


def run(write: bool = True) -> Dict[str, Any]:
    dig_part = _run_bear_paths()
    bear_premise = dig_part["bear_premise"]
    bear_paths = dig_part["bear_paths"]
    live_fp = _live_fingerprint()
    outcome = _outcome_from_bear(
        bear_premise if isinstance(bear_premise, dict) else {},
        n_days=int(dig_part["n_bear_days"]),
        n_eps=int(dig_part["n_bear_episodes"]),
    )

    payload: Dict[str, Any] = {
        "schema": "regime_bear_park_test_v1",
        "plan_id": "PLAN-BEAR-PARK-001",
        "family": "regime_bear_park",
        "as_of": _utc(),
        "live_writes": False,
        "policy_fingerprint": _policy_hash(),
        "live_fingerprint": live_fp,
        "live_confirm": {
            "live_is_bear": bool(live_fp.get("live_is_bear")),
            "allow_new_buys": live_fp.get("allow_new_buys"),
            "strategy_mode": live_fp.get("strategy_mode"),
            "note": (
                "Live bear fingerprint recorded. Hist premise is primary; live confirm is "
                "observational (park knobs already enforce allow_new_buys=false). No live writes."
            ),
        },
        "arms": ["USDC_full_park", "tactical_small_deploy", "live_bear_fingerprint"],
        "detector_thresholds": dig_part.get("detector_thresholds"),
        "n_bear_days": dig_part["n_bear_days"],
        "n_bear_episodes": dig_part["n_bear_episodes"],
        "bear_paths": bear_paths,
        "bear_premise": bear_premise,
        "outcome": outcome,
        "success_criteria": {
            "primary_window": "bear_historical_slices",
            "min_n_trades": 15,
            "must_beat_baseline_ret_pp": 0.0,
            "must_beat_baseline_dd_pp": 0.0,
            "require_both_ret_and_dd": True,
            "usdc_hurdle": True,
            "live_promote_allowed": False,
        },
        "recommendation": {
            "enum": outcome.get("enum"),
            "class": outcome.get("class"),
            "primary_pass": outcome.get("primary_pass"),
            "live_promote": False,
            "plain": (
                f"{outcome.get('plain_english')} Live regime={live_fp.get('regime')} "
                f"allow_new_buys={live_fp.get('allow_new_buys')} "
                f"mode={live_fp.get('strategy_mode')}."
            ),
        },
    }

    md_lines = [
        f"# Regime bear park test — {DAY}",
        "",
        f"**As of:** `{payload['as_of']}`  ",
        f"**Plan:** `PLAN-BEAR-PARK-001`  ",
        f"**Live writes:** none  ",
        f"**Policy sha256:** `{payload['policy_fingerprint'].get('sha256')}`  ",
        "",
        "## Live fingerprint",
        "",
        f"- regime: **{live_fp.get('regime')}** · mode `{live_fp.get('strategy_mode')}`",
        f"- allow_new_buys: **{live_fp.get('allow_new_buys')}** · cap `{live_fp.get('rebalance_cap_usd')}`",
        f"- BTC 30d: `{live_fp.get('btc_return_pct')}` · conf `{live_fp.get('confidence')}`",
        f"- live_is_bear: **{live_fp.get('live_is_bear')}**",
        "",
        "## Outcome",
        "",
        f"- class: `{outcome.get('class')}` · primary_pass: **{outcome.get('primary_pass')}**",
        f"- enum: `{outcome.get('enum')}` · N_days={outcome.get('n_labeled_days')} · eps={outcome.get('n_episodes')}",
        f"- {outcome.get('plain_english')}",
        "",
        "## Bear paths (labeled days)",
        "",
        "| Arm | util | ret% | maxDD% |",
        "|-----|------|------|--------|",
    ]
    for name, row in (bear_paths or {}).items():
        if not isinstance(row, dict):
            continue
        md_lines.append(
            f"| {name} | {row.get('util')} | {row.get('total_return_pct')} | {row.get('max_dd_pct')} |"
        )
    md_lines.extend(
        [
            "",
            "## Decision",
            "",
            "**No live promote.** Hist premise + live fingerprint only.",
            f"Follow-on: `{outcome.get('follow_on')}`.",
            "",
            f"JSON: `reports/{OUT_STEM}.json`",
            "",
        ]
    )
    md = "\n".join(md_lines) + "\n"

    if write:
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / f"{OUT_STEM}.json").write_text(json.dumps(payload, indent=2, default=str) + "\n")
        (REPORTS / f"{OUT_STEM}.md").write_text(md)
        (REPORTS / "REGIME_BEAR_PARK_TEST_LATEST.md").write_text(md)
        (REPORTS / "REGIME_BEAR_PARK_TEST_LATEST.json").write_text(
            json.dumps(payload, indent=2, default=str) + "\n"
        )
        STATE.mkdir(parents=True, exist_ok=True)
        (STATE / "regime_bear_park_test_latest.json").write_text(
            json.dumps(payload, indent=2, default=str) + "\n"
        )
    payload["_md_path"] = f"reports/{OUT_STEM}.md"
    payload["_json_path"] = f"reports/{OUT_STEM}.json"
    return payload


def main() -> int:
    p = run(write=True)
    print(
        json.dumps(
            {
                "ok": True,
                "plan_id": p.get("plan_id"),
                "outcome": p.get("outcome"),
                "live_regime": (p.get("live_fingerprint") or {}).get("regime"),
                "allow_new_buys": (p.get("live_fingerprint") or {}).get("allow_new_buys"),
                "md": p.get("_md_path"),
                "json": p.get("_json_path"),
                "live_promote": False,
            },
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
