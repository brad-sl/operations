#!/usr/bin/env python3
"""
Official StochRSI parallel-trial report (mid or final).

Real data only: rsi_indicator_history.jsonl, decision_context_log.jsonl,
trades/phase6_trades.jsonl (+ csv fallback), trial state JSON.

Usage:
  python3 phase6/research/run_stoch_rsi_trial_report.py --phase mid
  python3 phase6/research/run_stoch_rsi_trial_report.py --phase final
  python3 phase6/research/run_stoch_rsi_trial_report.py --phase baseline
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRIAL_ID = "STOCH-RSI-PARALLEL-20260721"
STATE_PATH = PROJECT_ROOT / "data" / "state" / "trials" / f"{TRIAL_ID}.json"
HISTORY = PROJECT_ROOT / "data" / "state" / "rsi_indicator_history.jsonl"
DECISION_LOG = PROJECT_ROOT / "data" / "state" / "decision_context_log.jsonl"
TRADES_JSONL = PROJECT_ROOT / "trades" / "phase6_trades.jsonl"
REPORTS = PROJECT_ROOT / "reports"


def _parse_ts(s: Any) -> Optional[datetime]:
    if not s or not isinstance(s, str):
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        # Normalize to aware UTC so jsonl mixes of naive/aware don't crash comparisons
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _load_trial() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"trial_id": TRIAL_ID, "status": "UNKNOWN"}


def _iter_jsonl(path: Path):
    if not path.exists():
        return
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def analyze_history(start: Optional[datetime], end: Optional[datetime]) -> dict:
    rows = []
    disagree = defaultdict(int)  # pair -> count material disagree
    total_pair_obs = defaultdict(int)
    stoch_extreme = defaultdict(int)  # pair low or high stoch
    rsi_only = 0
    with_stoch = 0
    timestamps: List[datetime] = []

    for row in _iter_jsonl(HISTORY):
        ts = _parse_ts(row.get("timestamp") or row.get("run_timestamp"))
        if ts is None:
            continue
        if start and ts < start:
            continue
        if end and ts > end:
            continue
        timestamps.append(ts)
        pairs = row.get("pairs") or {}
        for pair, ent in pairs.items():
            if not isinstance(ent, dict):
                continue
            rsi = ent.get("rsi")
            sk = ent.get("stoch_k")
            total_pair_obs[pair] += 1
            if sk is None:
                rsi_only += 1
                continue
            with_stoch += 1
            try:
                rsi_f = float(rsi) if rsi is not None else None
                sk_f = float(sk)
            except (TypeError, ValueError):
                continue
            if sk_f < 20 or sk_f > 80:
                stoch_extreme[pair] += 1
            # Material disagreement: RSI neutral band vs extreme Stoch
            if rsi_f is not None and 40 <= rsi_f <= 60 and (sk_f < 20 or sk_f > 80):
                disagree[pair] += 1
        rows.append(row)

    return {
        "history_rows": len(rows),
        "ts_min": min(timestamps).isoformat() if timestamps else None,
        "ts_max": max(timestamps).isoformat() if timestamps else None,
        "pair_obs": dict(total_pair_obs),
        "obs_with_stoch": with_stoch,
        "obs_rsi_only": rsi_only,
        "disagree_rsi_neutral_stoch_extreme": dict(sorted(disagree.items(), key=lambda x: -x[1])),
        "stoch_extreme_counts": dict(sorted(stoch_extreme.items(), key=lambda x: -x[1])),
        "disagree_total": sum(disagree.values()),
    }


def analyze_trades(start: Optional[datetime], end: Optional[datetime]) -> dict:
    n = 0
    with_ind = 0
    with_stoch = 0
    sl_exits = 0
    sl_with_stoch = 0
    sl_low_stoch = 0  # stoch_k < 30 at exit
    by_reason = defaultdict(int)

    for row in _iter_jsonl(TRADES_JSONL):
        ts = _parse_ts(row.get("timestamp"))
        if ts is None:
            continue
        if start and ts < start:
            continue
        if end and ts > end:
            continue
        n += 1
        reason = row.get("exit_reason") or row.get("reason") or row.get("side") or "unknown"
        by_reason[str(reason)] += 1
        ind = row.get("indicators_at_trade") or {}
        if ind:
            with_ind += 1
            sk = ind.get("stoch_k")
            if sk is not None:
                with_stoch += 1
            is_sl = "stop_loss" in str(reason).lower() or "stop_loss" in str(row.get("exit_reason", "")).lower()
            if is_sl:
                sl_exits += 1
                if sk is not None:
                    sl_with_stoch += 1
                    try:
                        if float(sk) < 30:
                            sl_low_stoch += 1
                    except (TypeError, ValueError):
                        pass

    return {
        "trades": n,
        "with_indicators_at_trade": with_ind,
        "with_stoch_at_trade": with_stoch,
        "sl_exits": sl_exits,
        "sl_exits_with_stoch": sl_with_stoch,
        "sl_exits_stoch_k_lt_30": sl_low_stoch,
        "by_reason_top": dict(sorted(by_reason.items(), key=lambda x: -x[1])[:12]),
    }


def analyze_decisions(start: Optional[datetime], end: Optional[datetime]) -> dict:
    n = 0
    with_snap = 0
    stoch_pairs_total = 0
    for row in _iter_jsonl(DECISION_LOG):
        ts = _parse_ts(row.get("timestamp") or row.get("ts"))
        if ts is None:
            # some logs nest
            ts = _parse_ts((row.get("meta") or {}).get("timestamp"))
        if start and ts and ts < start:
            continue
        if end and ts and ts > end:
            continue
        n += 1
        snap = row.get("indicator_snapshot") or (row.get("context") or {}).get("indicator_snapshot")
        meta = row.get("indicator_meta") or (row.get("context") or {}).get("indicator_meta")
        if snap or meta:
            with_snap += 1
        if isinstance(meta, dict) and meta.get("pairs_with_stoch_k") is not None:
            try:
                stoch_pairs_total += int(meta.get("pairs_with_stoch_k") or 0)
            except (TypeError, ValueError):
                pass
        elif isinstance(snap, dict):
            stoch_pairs_total += sum(
                1 for v in snap.values() if isinstance(v, dict) and v.get("stoch_k") is not None
            )
    return {
        "decision_rows": n,
        "with_indicator_snapshot": with_snap,
        "stoch_pair_mentions_sum": stoch_pairs_total,
    }


def recommend(hist: dict, trades: dict) -> Tuple[str, List[str]]:
    """Honest gate: default continue/observe unless evidence is strong."""
    caveats = []
    rows = hist.get("history_rows") or 0
    if rows < 50:
        caveats.append(f"thin history rows ({rows}) — do not promote")
    if (trades.get("with_stoch_at_trade") or 0) < 10:
        caveats.append("few trades carry stoch_k at fill — weak outcome linkage")
    disagree = hist.get("disagree_total") or 0
    if disagree == 0 and rows > 20:
        caveats.append("almost no RSI-neutral vs Stoch-extreme disagreements in window")

    # Default conservative
    if caveats and rows < 100:
        return "continue_observe_only", caveats + [
            "Allocator must stay plain-RSI primary until stronger evidence."
        ]
    if (trades.get("sl_exits_with_stoch") or 0) >= 8:
        # only suggest scoped experiment if we have linkage
        return "propose_scoped_sl_risk_experiment", caveats + [
            "Enough SL+stoch tags to design a *shadow* SL threshold experiment — not live allocator change."
        ]
    if rows >= 100 and disagree >= 20:
        return "extend_trial", caveats + [
            "Disagreement exists but outcome link weak — extend collection another 7–14d."
        ]
    return "continue_observe_only", caveats + [
        "Insufficient evidence to touch allocator or promote Stoch as primary."
    ]


def write_report(phase: str, trial: dict, hist: dict, trades: dict, decisions: dict, rec: str, caveats: List[str]) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stem = f"STOCH_RSI_TRIAL_{phase.upper()}_{day}"
    md_path = REPORTS / f"{stem}.md"
    json_path = REPORTS / f"{stem}.json"

    payload = {
        "trial_id": TRIAL_ID,
        "phase": phase,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trial": {
            "status": trial.get("status"),
            "start_at": trial.get("start_at"),
            "end_at": trial.get("end_at"),
            "intent": trial.get("intent"),
        },
        "history": hist,
        "trades": trades,
        "decisions": decisions,
        "recommendation": rec,
        "caveats": caveats,
        "rules": {
            "allocator_change": False,
            "requires_brad_go_for_live": True,
            "real_data_only": True,
        },
    }
    json_path.write_text(json.dumps(payload, indent=2) + "\n")

    lines = [
        f"# StochRSI Parallel Trial — {phase.upper()} report",
        "",
        f"**Trial:** `{TRIAL_ID}`  ",
        f"**Generated:** {payload['generated_at']}  ",
        f"**Recommendation:** **{rec}**  ",
        "",
        "## Intent (locked)",
        "",
        "- Run StochRSI **in parallel** with plain longer-term RSI (instrumentation + SL risk scorer).",
        "- Production **allocator stays plain RSI** — no core trade-logic change without evidence + Brad go.",
        "- Close with: continue observe | extend | scoped experiment | drop | (rare) promote blend.",
        "",
        "## History (`rsi_indicator_history.jsonl`)",
        "",
        f"- Rows in window: **{hist.get('history_rows')}**",
        f"- Range: `{hist.get('ts_min')}` → `{hist.get('ts_max')}`",
        f"- Obs with stoch: **{hist.get('obs_with_stoch')}** | rsi-only: **{hist.get('obs_rsi_only')}**",
        f"- Material disagreements (RSI 40–60 vs Stoch &lt;20 or &gt;80): **{hist.get('disagree_total')}**",
        f"- By pair: `{hist.get('disagree_rsi_neutral_stoch_extreme')}`",
        "",
        "## Trades",
        "",
        f"- Trades in window: **{trades.get('trades')}**",
        f"- With indicators_at_trade: **{trades.get('with_indicators_at_trade')}** (stoch: **{trades.get('with_stoch_at_trade')}**)",
        f"- SL exits: **{trades.get('sl_exits')}** | with stoch: **{trades.get('sl_exits_with_stoch')}** | stoch_k&lt;30: **{trades.get('sl_exits_stoch_k_lt_30')}**",
        f"- Reasons: `{trades.get('by_reason_top')}`",
        "",
        "## Decisions",
        "",
        f"- Rows: **{decisions.get('decision_rows')}** | with indicator snapshot: **{decisions.get('with_indicator_snapshot')}**",
        "",
        "## Caveats",
        "",
    ]
    for c in caveats:
        lines.append(f"- {c}")
    lines += [
        "",
        "## Honest assessment",
        "",
        "First-pass expectation remains: **not enough** to change allocator. "
        "Stoch is an *overlay signal* for risk narrative unless SL-linkage and disagreement "
        "rates are strong **and** stable across regimes.",
        "",
        f"JSON twin: `{json_path}`",
        "",
    ]
    md_path.write_text("\n".join(lines))
    return md_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["baseline", "mid", "final", "adhoc"], default="adhoc")
    ap.add_argument("--start", default=None, help="ISO start override")
    ap.add_argument("--end", default=None, help="ISO end override")
    args = ap.parse_args()

    trial = _load_trial()
    start = _parse_ts(args.start) or _parse_ts(trial.get("analysis_window_start") or trial.get("start_at"))
    end = _parse_ts(args.end) or _parse_ts(trial.get("analysis_window_end")) or datetime.now(timezone.utc)

    hist = analyze_history(start, end)
    trades = analyze_trades(start, end)
    decisions = analyze_decisions(start, end)
    rec, caveats = recommend(hist, trades)
    path = write_report(args.phase, trial, hist, trades, decisions, rec, caveats)

    # Update trial state (prefer trial_cycle transitions)
    now_s = datetime.now(timezone.utc).isoformat()
    trial.setdefault("reports", []).append(
        {"phase": args.phase, "path": str(path), "at": now_s, "recommendation": rec}
    )
    if args.phase == "baseline":
        trial["baseline_report"] = str(path)
    elif args.phase == "mid":
        trial["mid_report"] = str(path)
    elif args.phase == "final":
        trial["final_report"] = str(path)
        trial["final_report_at"] = now_s
        trial["final_recommendation"] = rec
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(trial, indent=2) + "\n")

    try:
        from phase6.research.trial_cycle import transition, write_review_request, reindex

        if args.phase == "final":
            st = trial.get("status")
            if st in ("RUNNING", "DEGRADED"):
                transition(TRIAL_ID, "REPORT_READY", note=f"final rec={rec}")
            write_review_request(TRIAL_ID)
        else:
            reindex()
    except Exception as e:
        print(f"[WARN] trial_cycle post-report: {e}")

    print(path.read_text()[:2500])
    print(f"\n---\nWrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
