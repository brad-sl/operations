"""Decision packet: compact state + default Jev fan-out questions for lab.

docs/plans/2026-09-18-jev-judgment-layer-lab.md
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LIVE = ROOT / "data" / "state" / "phase6_live_state.json"
DEFAULT_RSI = ROOT / "data" / "state" / "rsi_cache.json"
DEFAULT_SENT = ROOT / "data" / "state" / "sentiment_cache.json"


def _read_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _pair_norm(p: str) -> str:
    s = str(p or "").strip().upper().replace("_", "-")
    if s and "-" not in s:
        s = f"{s}-USD"
    return s


def _rsi_for_pair(cache: Any, pair: str) -> Optional[float]:
    if cache is None:
        return None
    p = _pair_norm(pair)
    if isinstance(cache, dict):
        # shapes: {pair: {rsi: n}} or {pairs: {...}} or flat
        node = cache.get(p) or cache.get(p.replace("-USD", "")) or (cache.get("pairs") or {}).get(p)
        if isinstance(node, dict):
            for k in ("rsi", "rsi_14", "value"):
                if node.get(k) is not None:
                    try:
                        return float(node[k])
                    except (TypeError, ValueError):
                        pass
        if p in cache and isinstance(cache[p], (int, float)):
            return float(cache[p])
    return None


def _sent_for_pair(cache: Any, pair: str) -> Dict[str, Any]:
    p = _pair_norm(pair)
    out: Dict[str, Any] = {"eng": None, "age_min": None, "source": None}
    if not isinstance(cache, dict):
        return out
    node = cache.get(p) or cache.get("scores", {}).get(p) if isinstance(cache.get("scores"), dict) else None
    if node is None and isinstance(cache.get("pairs"), dict):
        node = cache["pairs"].get(p)
    if isinstance(node, dict):
        for k in ("eng", "score", "sentiment", "x_score", "value"):
            if node.get(k) is not None:
                try:
                    out["eng"] = float(node[k])
                    break
                except (TypeError, ValueError):
                    pass
        out["age_min"] = node.get("age_min") or node.get("age_minutes") or node.get("age")
        out["source"] = node.get("source") or node.get("src")
    elif isinstance(node, (int, float)):
        out["eng"] = float(node)
    return out


def _held_qty(live: Dict[str, Any], pair: str) -> float:
    p = _pair_norm(pair)
    positions = live.get("positions") or []
    if isinstance(positions, list):
        for row in positions:
            if not isinstance(row, dict):
                continue
            rp = _pair_norm(str(row.get("pair") or row.get("product_id") or ""))
            if rp == p:
                try:
                    return float(row.get("qty") or row.get("quantity") or row.get("amount") or 0)
                except (TypeError, ValueError):
                    return 0.0
    return 0.0


def build_pair_state(
    pair: str,
    *,
    live_path: Optional[Path] = None,
    rsi_path: Optional[Path] = None,
    sent_path: Optional[Path] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compact state for one pair — stay well under token budget."""
    pair = _pair_norm(pair)
    live = _read_json(Path(live_path) if live_path else DEFAULT_LIVE) or {}
    if not isinstance(live, dict):
        live = {}
    rsi_c = _read_json(Path(rsi_path) if rsi_path else DEFAULT_RSI)
    sent_c = _read_json(Path(sent_path) if sent_path else DEFAULT_SENT)
    sent = _sent_for_pair(sent_c, pair)
    rsi = _rsi_for_pair(rsi_c, pair)
    # also try live.rsi map
    if rsi is None and isinstance(live.get("rsi"), dict):
        rsi = _rsi_for_pair(live["rsi"], pair)

    qty = _held_qty(live, pair)
    cash = live.get("cash_usd")
    try:
        cash_f = float(cash) if cash is not None else None
    except (TypeError, ValueError):
        cash_f = None

    state: Dict[str, Any] = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "venue": "coinbase_advanced",
        "pair": pair,
        "indicators": {
            "rsi_14": rsi,
            "eng_sentiment": sent.get("eng"),
            "sentiment_age_min": sent.get("age_min"),
            "sentiment_source": sent.get("source"),
        },
        "inventory": {
            "qty": qty,
            "held": qty > 0,
            "cash_usd": cash_f,
            "book_total_usd": live.get("total_usd"),
        },
        "platform_context": {
            "tryout_cap_usd": 75,
            "max_new_seats_per_day": 2,
            "live_membership_swaps": False,
            "note": "Spot CEX tryout book; judgment only — code owns size/gates/orders.",
        },
    }
    if extra:
        state["extra"] = extra
    return state


def default_lab_questions() -> Dict[str, Any]:
    """Atomic fan-out for lab (decompose; code combines)."""
    return {
        "action": {
            "type": "choice",
            "instructions": (
                "Given indicators and inventory only, what is the most appropriate "
                "spot action for this pair right now? Prefer hold when evidence is mixed. "
                "This is not an order — a judgment label for logging."
            ),
            "criteria": {
                "buy": "Setup favors opening or adding a small long",
                "sell": "Setup favors reducing or exiting a long",
                "hold": "No clear action; stay flat or keep current size",
                "reduce": "Trim risk but not full exit",
                "flatten": "Exit to flat urgently",
            },
        },
        "regime": {
            "type": "choice",
            "instructions": "Classify the short-horizon market regime for this pair from the state.",
            "criteria": {
                "trend_up": "Clear upward trend / continuation higher",
                "trend_down": "Clear downward trend / continuation lower",
                "range": "Sideways / mean-reverting range",
                "squeeze": "Compressed volatility, break imminent unclear",
                "liquidation_cascade": "Forced selling / cascade-like stress",
            },
        },
        "setup_quality": {
            "type": "score",
            "instructions": "Rate quality of the current trade setup for a small spot tryout.",
            "criteria": [
                "Toxic or trap-prone — avoid",
                "Thin / mediocre — only with strong filters",
                "Normal usable setup",
                "Clean high-quality setup",
            ],
        },
        "is_fakeout_or_stop_run": {
            "type": "noul",
            "instructions": (
                "Is the current move more like a fakeout or stop-run than a durable break? "
                "Use RSI and structure cues in state; if unclear, lean false."
            ),
            "criteria": {
                "true": "Likely fakeout, stop-run, or knife without reclaim",
                "false": "Not primarily a fakeout/stop-run, or insufficient evidence of one",
            },
        },
        "should_trade_name_now": {
            "type": "noul",
            "instructions": (
                "Should we open or add risk in this name right now given inventory, "
                "sentiment freshness, and RSI? Respect that tryouts are small and gated in code."
            ),
            "criteria": {
                "true": "Yes — judgment supports trading this name now",
                "false": "No — skip, wait, or do not add risk now",
            },
        },
    }


def confidence_gate_paper(
    result_answers: Dict[str, Any],
    *,
    should_trade_min: float = 0.65,
    fakeout_max: float = 0.55,
    action_conf_min: float = 0.55,
) -> Dict[str, Any]:
    """Pure paper tag — never an order. Combines noul/choice with floors."""

    def _noul(name: str) -> Optional[float]:
        a = result_answers.get(name) or {}
        if hasattr(a, "noul"):
            return a.noul
        try:
            return float(a.get("noul")) if a.get("noul") is not None else None
        except (TypeError, ValueError, AttributeError):
            return None

    def _choice(name: str):
        a = result_answers.get(name) or {}
        if hasattr(a, "choice"):
            return a.choice, a.confidence
        return a.get("choice"), a.get("confidence")

    st = _noul("should_trade_name_now")
    fk = _noul("is_fakeout_or_stop_run")
    act, act_c = _choice("action")
    try:
        act_c_f = float(act_c) if act_c is not None else None
    except (TypeError, ValueError):
        act_c_f = None

    reasons: List[str] = []
    would = False
    if st is None:
        reasons.append("missing_should_trade_noul")
    elif st < should_trade_min:
        reasons.append(f"should_trade_below_{should_trade_min}")
    if fk is not None and fk >= fakeout_max:
        reasons.append(f"fakeout_noul_ge_{fakeout_max}")
    if act not in ("buy",):
        reasons.append(f"action_not_buy:{act}")
    if act_c_f is not None and act_c_f < action_conf_min:
        reasons.append(f"action_conf_below_{action_conf_min}")

    if (
        st is not None
        and st >= should_trade_min
        and (fk is None or fk < fakeout_max)
        and act == "buy"
        and (act_c_f is None or act_c_f >= action_conf_min)
    ):
        would = True
        reasons = ["paper_would_buy_tag"]

    return {
        "would_order": False,  # hard — lab never orders
        "paper_would_buy_tag": would,
        "reasons": reasons,
        "thresholds": {
            "should_trade_min": should_trade_min,
            "fakeout_max": fakeout_max,
            "action_conf_min": action_conf_min,
        },
    }
