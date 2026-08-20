#!/usr/bin/env python3
"""Boundary-layer shadow — labels + would-buy under cream gates. NO live orders.

Option-1 path (2026-08-20): evidence before any regime_cash / knob promote.

Writes:
  data/state/regime_boundary_layer_shadow_latest.json
  reports/REGIME_BOUNDARY_LAYER_SHADOW_LATEST.md

Live REGIME-CASH park/deploy is unchanged. This only answers:
  - What layer are we in?
  - Which basket pairs would pass proposed soft_up/climb/pre_bull gates?
  - How does that compare to live park (usually blocks all BUYs)?
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.paths import PROJECT_ROOT, STATE_DIR, load_trading_basket  # noqa: E402
from phase6.core.regime_cash_policy import (  # noqa: E402
    evaluate_buy_entry,
    persist_status,
    resolve_regime_cash,
)
from phase6.core.runner_capital_events import load_buy_block_status  # noqa: E402

SHADOW_PATH = STATE_DIR / "regime_boundary_layer_shadow_latest.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "REGIME_BOUNDARY_LAYER_SHADOW_LATEST.md"
JSONL_PATH = STATE_DIR / "regime_boundary_layer_shadow.jsonl"

# Cream-skim gates (shadow only). Stricter than "buy anything green".
SHADOW_GATES: Dict[str, Dict[str, Any]] = {
    "soft_up": {
        "label": "flat_b_tight",
        "allow": True,
        "cap_usd": 50.0,
        "max_util": 0.55,
        "max_rsi": 55.0,
        "min_sentiment": 0.28,
        "min_sentiment_new": 0.38,
    },
    "climb": {
        "label": "micro_climb",
        "allow": True,
        "cap_usd": 60.0,
        "max_util": 0.50,
        "max_rsi": 55.0,
        "min_sentiment": 0.30,
        "min_sentiment_new": 0.40,
    },
    "pre_bull": {
        "label": "micro_pre_bull",
        "allow": True,
        "cap_usd": 75.0,
        "max_util": 0.60,
        "max_rsi": 58.0,
        "min_sentiment": 0.25,
        "min_sentiment_new": 0.35,
    },
    "flat": {
        "label": "flat_b_ref",
        "allow": True,
        "cap_usd": 75.0,
        "max_util": 0.65,
        "max_rsi": 55.0,
        "min_sentiment": 0.25,
        "min_sentiment_new": 0.35,
    },
    # park layers — shadow would-buy always empty by stance
    "bear": {"label": "park", "allow": False},
    "soft_down": {"label": "park", "allow": False},
    "transition_core": {"label": "park", "allow": False},
    "unknown": {"label": "park", "allow": False},
    "bull": {
        "label": "deploy_ref",
        "allow": True,
        "cap_usd": 150.0,
        "max_util": 0.85,
        "max_rsi": 65.0,
        "min_sentiment": 0.20,
        "min_sentiment_new": 0.30,
    },
}


def _load_rsi_sent() -> Tuple[Dict[str, float], Dict[str, float]]:
    rsi_map: Dict[str, float] = {}
    sent_map: Dict[str, float] = {}
    # Prefer live_state caches if present
    live_p = STATE_DIR / "phase6_live_state.json"
    if live_p.exists():
        try:
            st = json.loads(live_p.read_text(encoding="utf-8"))
            for k, v in (st.get("rsi") or st.get("rsi_map") or {}).items():
                try:
                    rsi_map[str(k)] = float(v)
                except (TypeError, ValueError):
                    pass
            for k, v in (st.get("sentiment") or st.get("sentiment_map") or {}).items():
                try:
                    sent_map[str(k)] = float(v if not isinstance(v, dict) else v.get("score", v.get("sentiment")))
                except (TypeError, ValueError):
                    pass
        except (json.JSONDecodeError, OSError):
            pass
    # Dashboard-style files
    for name, target in (
        ("rsi_cache.json", rsi_map),
        ("sentiment_cache.json", sent_map),
    ):
        p = PROJECT_ROOT / name if name.startswith("sentiment") else STATE_DIR / name
        if not p.exists() and name == "sentiment_cache.json":
            p = PROJECT_ROOT / "sentiment_cache.json"
        if not p.exists():
            p = STATE_DIR / name
        if not p.exists():
            continue
        try:
            blob = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(blob, dict):
                data = blob.get("pairs") or blob.get("data") or blob
                for k, v in data.items():
                    if not isinstance(k, str) or not k.endswith("-USD"):
                        continue
                    try:
                        if isinstance(v, dict):
                            val = v.get("rsi") or v.get("score") or v.get("sentiment") or v.get("value")
                        else:
                            val = v
                        if val is not None:
                            target[k] = float(val)
                    except (TypeError, ValueError):
                        continue
        except (json.JSONDecodeError, OSError):
            continue
    return rsi_map, sent_map


def _held_pairs() -> Set[str]:
    live_p = STATE_DIR / "phase6_live_state.json"
    held: Set[str] = set()
    if not live_p.exists():
        return held
    try:
        st = json.loads(live_p.read_text(encoding="utf-8"))
        for pos in st.get("trading_positions") or st.get("positions") or []:
            if not isinstance(pos, dict):
                continue
            pair = pos.get("pair")
            val = float(pos.get("value_usd") or 0)
            if pair and pair not in ("USD", "USDC", "PAXG-USD") and val >= 5.0:
                held.add(str(pair))
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        pass
    return held


def _util_and_cash() -> Dict[str, float]:
    live_p = STATE_DIR / "phase6_live_state.json"
    out = {"total_usd": 0.0, "holdings_usd": 0.0, "cash_usd": 0.0, "util": 0.0}
    if not live_p.exists():
        return out
    try:
        st = json.loads(live_p.read_text(encoding="utf-8"))
        total = float(st.get("total_usd") or st.get("total_balance") or 0)
        hold = float(st.get("total_holdings_value") or 0)
        cash = float(st.get("cash_usd") or 0)
        out["total_usd"] = total
        out["holdings_usd"] = hold
        out["cash_usd"] = cash
        out["util"] = (hold / total) if total > 0 else 0.0
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        pass
    return out


def evaluate_shadow_gates(
    *,
    layer: str,
    pair: str,
    rsi: Optional[float],
    sentiment: Optional[float],
    is_new_pair: bool,
    blocked: bool,
    util: float,
) -> Dict[str, Any]:
    g = SHADOW_GATES.get(layer) or SHADOW_GATES["unknown"]
    reasons: List[str] = []
    if not g.get("allow"):
        return {
            "pair": pair,
            "would_buy": False,
            "reasons": [f"shadow_stance_park layer={layer}"],
            "gate": g.get("label"),
        }
    if blocked:
        reasons.append("buy_blocked_cooldown")
    max_rsi = float(g.get("max_rsi") or 100)
    min_s = float(g.get("min_sentiment_new" if is_new_pair else "min_sentiment") or -1)
    max_util = float(g.get("max_util") or 1.0)
    if util >= max_util:
        reasons.append(f"util {util:.3f} >= max {max_util}")
    if rsi is None:
        reasons.append("rsi_missing")
    elif float(rsi) > max_rsi:
        reasons.append(f"rsi {float(rsi):.1f} > max {max_rsi}")
    if sentiment is None:
        reasons.append("sentiment_missing")
    elif float(sentiment) < min_s:
        reasons.append(f"sentiment {float(sentiment):.3f} < min {min_s}")
    would = len(reasons) == 0
    if would:
        reasons.append("shadow_entry_ok")
    return {
        "pair": pair,
        "would_buy": would,
        "reasons": reasons,
        "gate": g.get("label"),
        "cap_usd": g.get("cap_usd"),
        "rsi": rsi,
        "sentiment": sentiment,
        "is_new_pair": is_new_pair,
    }


def run_shadow() -> Dict[str, Any]:
    snap = resolve_regime_cash()
    # Refresh status file so dashboard picks up layer fields on next metrics read
    try:
        persist_status(snap)
    except Exception as e:
        print(f"persist_status warn: {e}", file=sys.stderr)

    layer = snap.regime_layer or snap.regime
    book = _util_and_cash()
    held = _held_pairs()
    rsi_map, sent_map = _load_rsi_sent()
    blocks = load_buy_block_status() or {}
    blocked_pairs = {
        p for p, info in blocks.items() if isinstance(info, dict) and info.get("blocked")
    }
    basket = list(load_trading_basket())

    # Live enforce path (usually park → no buys)
    live_rows: List[Dict[str, Any]] = []
    for pair in basket:
        dec = evaluate_buy_entry(
            pair,
            snap,
            sentiment=sent_map.get(pair),
            rsi=rsi_map.get(pair),
            lockout_pairs=blocked_pairs,
            is_new_pair=pair not in held,
        )
        live_rows.append(
            {
                "pair": pair,
                "allowed": dec.allowed,
                "reasons": list(dec.reasons),
                "rsi": dec.rsi,
                "sentiment": dec.sentiment,
            }
        )

    shadow_rows: List[Dict[str, Any]] = []
    for pair in basket:
        shadow_rows.append(
            evaluate_shadow_gates(
                layer=layer,
                pair=pair,
                rsi=rsi_map.get(pair),
                sentiment=sent_map.get(pair),
                is_new_pair=pair not in held,
                blocked=pair in blocked_pairs,
                util=float(book.get("util") or 0),
            )
        )

    would = [r for r in shadow_rows if r.get("would_buy")]
    live_ok = [r for r in live_rows if r.get("allowed")]
    gate = SHADOW_GATES.get(layer) or SHADOW_GATES["unknown"]

    out: Dict[str, Any] = {
        "schema_version": 1,
        "mode": "shadow_only",
        "live_orders": False,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "regime": snap.regime,
        "regime_layer": layer,
        "layer_label": snap.layer_label,
        "shadow_stance": snap.shadow_stance or gate.get("label"),
        "btc_return_pct": snap.btc_return_pct,
        "live": {
            "strategy_mode": snap.strategy_mode,
            "allow_new_buys": snap.allow_new_buys,
            "rebalance_cap_usd": snap.rebalance_cap_usd,
            "enforce": snap.enforce,
            "would_buy_count": len(live_ok),
            "would_buy_pairs": [r["pair"] for r in live_ok],
        },
        "shadow_gates": gate,
        "book": book,
        "held_pairs": sorted(held),
        "buy_blocked_pairs": sorted(blocked_pairs),
        "shadow_would_buy_count": len(would),
        "shadow_would_buy_pairs": [r["pair"] for r in would],
        "shadow_rows": shadow_rows,
        "live_rows": live_rows,
        "cream_note": (
            "Skim cream = shadow would-buy under strict layer gates; "
            "live stays park until promote. No auto-apply."
        ),
        "design_ref": "reports/REGIME_BOUNDARY_LAYERS_DESIGN_20260820.md",
    }
    return out


def write_report(payload: Dict[str, Any]) -> str:
    lines = [
        "# Regime boundary layer shadow",
        "",
        f"**As of:** {payload.get('as_of')}",
        f"**Mode:** shadow only — **no live orders**",
        "",
        "## Layer",
        "",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| Coarse regime | `{payload.get('regime')}` |",
        f"| Layer | `{payload.get('regime_layer')}` |",
        f"| Label | {payload.get('layer_label')} |",
        f"| BTC 30d % | {payload.get('btc_return_pct')} |",
        f"| Shadow stance | `{payload.get('shadow_stance')}` |",
        "",
        "## Live vs shadow",
        "",
        f"| | Live REGIME-CASH | Shadow cream gates |",
        f"|--|------------------|--------------------|",
        f"| Mode | `{payload['live'].get('strategy_mode')}` cap ${payload['live'].get('rebalance_cap_usd')} | `{payload.get('shadow_stance')}` cap ${((payload.get('shadow_gates') or {}).get('cap_usd'))} |",
        f"| Would-buy count | **{payload['live'].get('would_buy_count')}** | **{payload.get('shadow_would_buy_count')}** |",
        f"| Pairs | {', '.join(payload['live'].get('would_buy_pairs') or []) or '—'} | {', '.join(payload.get('shadow_would_buy_pairs') or []) or '—'} |",
        "",
        "## Book",
        "",
        f"- Util: {payload['book'].get('util')}",
        f"- Cash: ${payload['book'].get('cash_usd')}",
        f"- Held: {', '.join(payload.get('held_pairs') or []) or '—'}",
        f"- Blocked: {', '.join(payload.get('buy_blocked_pairs') or []) or '—'}",
        "",
        "## Shadow rows (basket)",
        "",
        "| Pair | Would buy | RSI | Sent | Reasons |",
        "|------|-----------|-----|------|---------|",
    ]
    for r in payload.get("shadow_rows") or []:
        lines.append(
            f"| {r.get('pair')} | {'YES' if r.get('would_buy') else 'no'} | "
            f"{r.get('rsi')} | {r.get('sentiment')} | "
            f"{'; '.join(r.get('reasons') or [])} |"
        )
    lines.extend(
        [
            "",
            "## Next",
            "",
            "- Accumulate shadow ticks (jsonl) before any climb promote.",
            "- Promote only with Brad go + expectancy vs park — not this file alone.",
            "",
            f"Design: `{payload.get('design_ref')}`",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    payload = run_shadow()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SHADOW_PATH.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    with JSONL_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, default=str) + "\n")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(write_report(payload), encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "regime": payload.get("regime"),
                "regime_layer": payload.get("regime_layer"),
                "live_would_buy": payload["live"].get("would_buy_count"),
                "shadow_would_buy": payload.get("shadow_would_buy_count"),
                "shadow_pairs": payload.get("shadow_would_buy_pairs"),
                "path": str(SHADOW_PATH),
                "report": str(REPORT_PATH),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
