"""
L2 deployability (PC-04).

Paper/CF ADD is scored "would runner buy?" via evaluate_buy_entry before promote talk.
L1 = shadow CF excess / arm pick. L2 = live gate pass under current snap + eng scores.
Measure-only — no membership swaps, no knobs.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from phase6.core.paths import PROJECT_ROOT

SCHEMA = "l2_deployability_v1"
STATE_PATH = PROJECT_ROOT / "data" / "state" / "l2_deployability_latest.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "L2_DEPLOYABILITY_LATEST.md"
CF_PATH = PROJECT_ROOT / "data" / "state" / "basket_swap_shadow_counterfactual_latest.json"
BRAD_PATH = PROJECT_ROOT / "data" / "state" / "basket_swap_brad_decision.json"
CONF_PATH = PROJECT_ROOT / "data" / "state" / "basket_swap_confidence_board_latest.json"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso() -> str:
    return _utc_now().isoformat()


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _norm_pair(p: str) -> str:
    return str(p or "").strip().upper().replace("_", "-")


@dataclass
class L2Row:
    pair: str
    arm: str
    pick_ts: Optional[str]
    l1_source: str
    l1_excess_to_now: Optional[float]
    l1_add_score: Optional[float]
    eng_sent: Optional[float]
    rsi: Optional[float]
    l2_allowed: bool
    l2_reasons: List[str] = field(default_factory=list)
    is_new_pair: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def score_l2_entry(
    *,
    pair: str,
    snap: Any,
    sentiment: Optional[float],
    rsi: Optional[float],
    is_new_pair: bool = True,
    policy: Optional[Dict[str, Any]] = None,
    lockout_pairs: Optional[set] = None,
) -> Dict[str, Any]:
    """Pure L2 gate: wrap evaluate_buy_entry into a dict."""
    from phase6.core.regime_cash_policy import evaluate_buy_entry

    d = evaluate_buy_entry(
        pair,
        snap,
        sentiment=sentiment,
        rsi=rsi,
        is_new_pair=is_new_pair,
        policy=policy,
        lockout_pairs=lockout_pairs,
    )
    return {
        "pair": _norm_pair(pair),
        "l2_allowed": bool(getattr(d, "allowed", False)),
        "l2_reasons": list(getattr(d, "reasons", None) or []),
        "sentiment": getattr(d, "sentiment", sentiment),
        "rsi": getattr(d, "rsi", rsi),
    }


def recent_arm_adds(
    cf: Mapping[str, Any],
    arm: str,
    *,
    limit: int = 12,
) -> List[Dict[str, Any]]:
    """Latest unique CF ADDs for arm (dedupe by add pair, keep newest)."""
    rows = list(cf.get("unique_results") or cf.get("results") or [])
    arm_n = str(arm or "").strip()
    filtered = [
        r
        for r in rows
        if isinstance(r, dict) and str(r.get("arm") or "") == arm_n and r.get("add")
    ]
    filtered.sort(key=lambda r: str(r.get("ts") or ""), reverse=True)
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for r in filtered:
        p = _norm_pair(str(r.get("add")))
        if not p or p in seen:
            continue
        seen.add(p)
        out.append(r)
        if len(out) >= limit:
            break
    return out


def build_l2_board(
    *,
    arm: str,
    cf_rows: Sequence[Mapping[str, Any]],
    snap: Any,
    eng_scores: Mapping[str, float],
    rsi_by_pair: Mapping[str, Optional[float]],
    policy: Optional[Dict[str, Any]] = None,
    held_pairs: Optional[set] = None,
    lockout_pairs: Optional[set] = None,
) -> List[L2Row]:
    held = {_norm_pair(p) for p in (held_pairs or set())}
    rows: List[L2Row] = []
    for r in cf_rows:
        pair = _norm_pair(str(r.get("add") or ""))
        if not pair:
            continue
        is_new = pair not in held
        sent = eng_scores.get(pair)
        if sent is None:
            # try bare base
            base = pair.split("-")[0]
            for k, v in eng_scores.items():
                if _norm_pair(k).startswith(base + "-"):
                    sent = v
                    break
        rsi = rsi_by_pair.get(pair)
        gate = score_l2_entry(
            pair=pair,
            snap=snap,
            sentiment=float(sent) if sent is not None else None,
            rsi=float(rsi) if rsi is not None else None,
            is_new_pair=is_new,
            policy=policy,
            lockout_pairs=lockout_pairs,
        )
        excess = r.get("excess_to_now")
        try:
            excess_f = float(excess) if excess is not None else None
        except (TypeError, ValueError):
            excess_f = None
        score = r.get("add_score")
        try:
            score_f = float(score) if score is not None else None
        except (TypeError, ValueError):
            score_f = None
        rows.append(
            L2Row(
                pair=pair,
                arm=arm,
                pick_ts=str(r.get("ts") or "") or None,
                l1_source=str(r.get("source") or "cf"),
                l1_excess_to_now=excess_f,
                l1_add_score=score_f,
                eng_sent=float(sent) if sent is not None else None,
                rsi=float(rsi) if rsi is not None else None,
                l2_allowed=bool(gate["l2_allowed"]),
                l2_reasons=list(gate["l2_reasons"]),
                is_new_pair=is_new,
            )
        )
    return rows


def summarize(rows: Sequence[L2Row]) -> Dict[str, Any]:
    n = len(rows)
    n_pass = sum(1 for r in rows if r.l2_allowed)
    return {
        "n_scored": n,
        "n_l2_pass": n_pass,
        "n_l2_fail": n - n_pass,
        "l2_pass_rate": (n_pass / n) if n else None,
        "verdict": (
            "L2_EMPTY"
            if n == 0
            else ("L2_PARTIAL" if 0 < n_pass < n else ("L2_GO_BOARD" if n_pass == n else "L2_BLOCKED"))
        ),
        "note": (
            "L1 CF ≠ L2 deploy. Promote packets need L2 pass rate, not paper excess alone."
        ),
    }


def render_markdown(payload: Mapping[str, Any]) -> str:
    s = payload.get("summary") or {}
    arm = payload.get("preferred_arm") or "?"
    lines = [
        f"# L2 deployability (PC-04) — {arm}",
        "",
        f"**As of:** {payload.get('as_of')}",
        f"**Schema:** `{payload.get('schema')}`",
        f"**live_membership_swaps:** `{payload.get('live_membership_swaps')}` (must stay false without Brad GO)",
        "",
        "## Summary",
        "",
        f"- Scored ADDs: **{s.get('n_scored')}**",
        f"- L2 pass: **{s.get('n_l2_pass')}** · fail: **{s.get('n_l2_fail')}**",
        f"- L2 pass rate: **{s.get('l2_pass_rate') if s.get('l2_pass_rate') is not None else 'n/a'}**",
        f"- Verdict: **{s.get('verdict')}**",
        f"- {s.get('note')}",
        "",
        "## Rows (preferred arm ADDs)",
        "",
        "| pair | L1 excess% | eng_sent | rsi | L2 | top reason |",
        "|------|------------|----------|-----|----|------------|",
    ]
    for r in payload.get("rows") or []:
        reasons = r.get("l2_reasons") or []
        top = reasons[0] if reasons else ("ok" if r.get("l2_allowed") else "—")
        if len(top) > 48:
            top = top[:45] + "..."
        ex = r.get("l1_excess_to_now")
        ex_s = f"{ex:.2f}" if isinstance(ex, (int, float)) else "—"
        sent = r.get("eng_sent")
        sent_s = f"{sent:.3f}" if isinstance(sent, (int, float)) else "—"
        rsi = r.get("rsi")
        rsi_s = f"{rsi:.1f}" if isinstance(rsi, (int, float)) else "—"
        l2 = "PASS" if r.get("l2_allowed") else "FAIL"
        lines.append(f"| {r.get('pair')} | {ex_s} | {sent_s} | {rsi_s} | {l2} | {top} |")
    lines.extend(
        [
            "",
            "## Promote gate reminder",
            "",
            "- Do **not** treat L1 CF excess as deployable.",
            "- Require L2 pass (or explicit Brad override) in promote packets.",
            "- No live membership swap from this board.",
            "",
            f"State: `{STATE_PATH.relative_to(PROJECT_ROOT)}`",
            "",
        ]
    )
    return "\n".join(lines)


def write_artifacts(payload: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(render_markdown(payload), encoding="utf-8")


def build_live_l2_deployability(*, write: bool = True, limit: int = 12) -> Dict[str, Any]:
    """Live path: preferred arm CF ADDs × evaluate_buy_entry."""
    from phase6.core.regime_cash_policy import (
        RegimeCashSnapshot,
        load_policy,
        resolve_regime_cash,
    )

    brad = _read_json(BRAD_PATH)
    cf = _read_json(CF_PATH)
    conf = _read_json(CONF_PATH)
    arm = str(brad.get("preferred_arm") or "rel_btc_stable")
    live_swaps = bool(brad.get("live_membership_swaps"))

    pol = load_policy()
    try:
        snap = resolve_regime_cash(policy=pol)
    except Exception:
        st = _read_json(PROJECT_ROOT / "data" / "state" / "regime_cash_status.json")
        entry = (st.get("entry") or {}) if isinstance(st, dict) else {}
        snap = RegimeCashSnapshot(
            regime=str(st.get("regime") or "flat"),
            confidence=float(st.get("confidence") or 0.0),
            btc_return_pct=st.get("btc_return_pct"),
            strategy_mode=str(st.get("strategy_mode") or "deploy"),
            allow_new_buys=bool(st.get("allow_new_buys", True)),
            target_max_util_pct=float(st.get("target_max_util_pct") or 50.0),
            rebalance_cap_usd=float(st.get("rebalance_cap_usd") or 75.0),
            min_cash_reserve_pct=float(st.get("min_cash_reserve_pct") or 20.0),
            entry=entry
            or {
                "min_sentiment": 0.25,
                "min_sentiment_new_pair": 0.35,
                "max_rsi": 55.0,
                "require_lockout_clear": True,
            },
            exit=st.get("exit") or {},
            label=str(st.get("label") or ""),
            detector=st.get("detector") or {},
        )

    # eng scores — prefer tryout board / sentiment store
    eng: Dict[str, float] = {}
    try:
        from phase6.core.tryout_readiness import build_live_tryout_readiness

        tr = build_live_tryout_readiness(write=False)
        for d in tr.get("doors") or []:
            if isinstance(d, dict) and d.get("pair") is not None:
                if d.get("eng_sent") is not None:
                    eng[_norm_pair(str(d["pair"]))] = float(d["eng_sent"])
    except Exception:
        pass
    if not eng:
        # fallback caches
        for name in (
            "sentiment_scores_latest.json",
            "eng_sentiment_latest.json",
            "x_sentiment_latest.json",
        ):
            blob = _read_json(PROJECT_ROOT / "data" / "state" / name)
            scores = blob.get("scores") or blob.get("pairs") or blob
            if isinstance(scores, dict):
                for k, v in scores.items():
                    if isinstance(v, (int, float)):
                        eng[_norm_pair(k)] = float(v)
                    elif isinstance(v, dict) and v.get("score") is not None:
                        try:
                            eng[_norm_pair(k)] = float(v["score"])
                        except (TypeError, ValueError):
                            pass

    rsi_by: Dict[str, Optional[float]] = {}
    try:
        from phase6.core.indicator_snapshot import indicators_for_trade_pair
    except Exception:
        indicators_for_trade_pair = None  # type: ignore

    cf_rows = recent_arm_adds(cf, arm, limit=limit)
    for r in cf_rows:
        p = _norm_pair(str(r.get("add") or ""))
        if not p or p in rsi_by:
            continue
        if indicators_for_trade_pair is None:
            rsi_by[p] = None
            continue
        try:
            ind = indicators_for_trade_pair(p) or {}
            rsi_by[p] = float(ind["rsi"]) if ind.get("rsi") is not None else None
        except Exception:
            rsi_by[p] = None

    held: set = set()
    try:
        pos = _read_json(PROJECT_ROOT / "data" / "state" / "positions_latest.json")
        for row in pos.get("positions") or pos.get("rows") or []:
            if isinstance(row, dict) and float(row.get("usd") or row.get("value") or 0) > 15:
                held.add(_norm_pair(str(row.get("pair") or row.get("product_id") or "")))
    except Exception:
        pass

    l2_rows = build_l2_board(
        arm=arm,
        cf_rows=cf_rows,
        snap=snap,
        eng_scores=eng,
        rsi_by_pair=rsi_by,
        policy=pol if isinstance(pol, dict) else None,
        held_pairs=held,
    )
    summary = summarize(l2_rows)
    payload: Dict[str, Any] = {
        "schema": SCHEMA,
        "as_of": _iso(),
        "preferred_arm": arm,
        "preferred_arm_role": brad.get("preferred_arm_role"),
        "live_membership_swaps": live_swaps,
        "cf_as_of": cf.get("as_of"),
        "confidence_status": conf.get("status"),
        "regime": getattr(snap, "regime", None),
        "strategy_mode": getattr(snap, "strategy_mode", None),
        "allow_new_buys": getattr(snap, "allow_new_buys", None),
        "summary": summary,
        "rows": [r.to_dict() for r in l2_rows],
        "measure_only": True,
        "no_live_swap": True,
    }
    if write:
        write_artifacts(payload)
    return payload
