"""Liquidation partial-redeploy shadow — pure decisions, never places orders.

Modes (caller-enforced):
  off | shadow | live_partial  — this module only evaluates + logs for shadow.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

logger = logging.getLogger(__name__)


DEFAULT_CFG: dict[str, Any] = {
    "mode": "shadow",
    "portion_pct": 0.25,
    "max_usd": 75.0,
    "min_proceeds_usd": 100.0,
    "max_legs": 1,
    "fee_rt_assumed": 0.006,
    "min_expected_edge_multiple_of_fee": 2.0,
    "allow_after": ["rotation_exchange"],
    "deny_after": ["stop_loss_exchange"],
    "require_regime_allow_new_buys": True,
    "require_entry_gates": True,
    "block_same_pair": True,
    # Soft score floor when using SignalGenerator-style confidence (0-1)
    "min_candidate_score": 0.30,
    # If expected_edge_pct unknown, skip fee-edge gate (size still capped)
    "skip_fee_edge_if_no_edge_model": True,
}


def merge_cfg(overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    out = dict(DEFAULT_CFG)
    if overrides:
        out.update(dict(overrides))
    # normalize lists
    for k in ("allow_after", "deny_after"):
        v = out.get(k) or []
        out[k] = [str(x).lower() for x in v]
    out["portion_pct"] = float(out["portion_pct"])
    out["max_usd"] = float(out["max_usd"])
    out["min_proceeds_usd"] = float(out["min_proceeds_usd"])
    out["fee_rt_assumed"] = float(out["fee_rt_assumed"])
    out["min_expected_edge_multiple_of_fee"] = float(
        out["min_expected_edge_multiple_of_fee"]
    )
    out["min_candidate_score"] = float(out.get("min_candidate_score") or 0.0)
    return out


def size_usd(proceeds_usd: float, cfg: Mapping[str, Any] | None = None) -> float:
    c = merge_cfg(cfg)
    p = max(0.0, float(proceeds_usd))
    if p < float(c["min_proceeds_usd"]):
        return 0.0
    raw = p * float(c["portion_pct"])
    return round(min(raw, float(c["max_usd"])), 2)


def reason_allowed(sell_reason: str, cfg: Mapping[str, Any] | None = None) -> tuple[bool, str]:
    c = merge_cfg(cfg)
    r = (sell_reason or "").lower()
    for d in c["deny_after"]:
        if d and d in r:
            return False, f"deny_after:{d}"
    allowed = False
    for a in c["allow_after"]:
        if a and a in r:
            allowed = True
            break
    if not allowed:
        return False, "reason_not_in_allow_after"
    return True, "ok"


@dataclass
class Candidate:
    pair: str
    score: float
    rsi: float | None = None
    sentiment: float | None = None
    is_new_pair: bool = True
    expected_edge_pct: float | None = None  # decimal, e.g. 0.02 = 2%
    notes: str = ""


@dataclass
class ShadowDecision:
    fire: bool
    skip_reason: str | None
    sell_pair: str
    sell_reason: str
    proceeds_usd: float
    size_usd: float
    candidate_pair: str | None
    candidate_score: float | None
    regime: str | None
    fee_usd: float
    filters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_shadow(
    *,
    sell_pair: str,
    sell_reason: str,
    proceeds_usd: float,
    regime: str | None,
    allow_new_buys: bool,
    entry_gates: Mapping[str, Any] | None,
    candidates: Sequence[Candidate],
    cfg: Mapping[str, Any] | None = None,
    cooldown_pairs: Sequence[str] | None = None,
) -> ShadowDecision:
    """Pure shadow decision. Never mutates external state."""
    c = merge_cfg(cfg)
    cooldown = {str(p).upper() for p in (cooldown_pairs or [])}
    sell_pair_u = str(sell_pair or "").upper()
    sell_reason_s = str(sell_reason or "")
    proceeds = float(proceeds_usd)
    sz = size_usd(proceeds, c)
    fee = round(sz * float(c["fee_rt_assumed"]), 4)

    def _dec(
        fire: bool,
        skip_reason: str | None,
        filters: dict[str, Any],
        candidate_pair: str | None = None,
        candidate_score: float | None = None,
    ) -> ShadowDecision:
        return ShadowDecision(
            fire=fire,
            skip_reason=skip_reason,
            sell_pair=sell_pair_u,
            sell_reason=sell_reason_s,
            proceeds_usd=proceeds,
            size_usd=sz,
            candidate_pair=candidate_pair,
            candidate_score=candidate_score,
            regime=regime,
            fee_usd=fee,
            filters=filters,
        )

    ok_r, why = reason_allowed(sell_reason_s, c)
    if not ok_r:
        return _dec(False, why, {"reason": why})

    if sz <= 0:
        return _dec(
            False,
            "below_min_proceeds_or_zero_size",
            {"min_proceeds_usd": c["min_proceeds_usd"]},
        )

    if c["require_regime_allow_new_buys"] and not allow_new_buys:
        return _dec(
            False,
            "regime_blocks_new_buys",
            {"allow_new_buys": False, "regime": regime},
        )

    eg = dict(entry_gates or {})
    max_rsi = float(eg.get("max_rsi") or 100.0)
    min_sent = float(eg.get("min_sentiment") or -1.0)
    min_sent_new = float(eg.get("min_sentiment_new_pair") or min_sent)

    ranked: list[Candidate] = []
    reject_notes: list[str] = []
    for cand in candidates:
        pair = str(cand.pair or "").upper()
        if not pair:
            continue
        if c["block_same_pair"] and pair == sell_pair_u:
            reject_notes.append(f"{pair}:same_pair")
            continue
        if pair in cooldown:
            reject_notes.append(f"{pair}:cooldown")
            continue
        if float(cand.score) < float(c["min_candidate_score"]):
            reject_notes.append(f"{pair}:score<{c['min_candidate_score']}")
            continue
        if c["require_entry_gates"]:
            rsi = cand.rsi
            if rsi is not None and float(rsi) > max_rsi:
                reject_notes.append(f"{pair}:rsi>{max_rsi}")
                continue
            sent = cand.sentiment
            floor = min_sent_new if cand.is_new_pair else min_sent
            if sent is not None and float(sent) < floor:
                reject_notes.append(f"{pair}:sent<{floor}")
                continue
        if cand.expected_edge_pct is not None:
            need = float(c["fee_rt_assumed"]) * float(c["min_expected_edge_multiple_of_fee"])
            if float(cand.expected_edge_pct) < need:
                reject_notes.append(f"{pair}:edge<{need}")
                continue
        elif not c.get("skip_fee_edge_if_no_edge_model", True):
            reject_notes.append(f"{pair}:no_edge_model")
            continue
        ranked.append(cand)

    if not ranked:
        return _dec(
            False,
            "no_eligible_candidate",
            {"rejects": reject_notes[:20], "n_in": len(candidates)},
        )

    ranked.sort(key=lambda x: float(x.score), reverse=True)
    best = ranked[0]
    return _dec(
        True,
        None,
        {
            "n_eligible": len(ranked),
            "rejects_sample": reject_notes[:12],
            "portion_pct": c["portion_pct"],
            "max_usd": c["max_usd"],
        },
        candidate_pair=str(best.pair).upper(),
        candidate_score=float(best.score),
    )


# --- Live auto-append (shadow only; never places orders) ---

SHADOW_LOG_PATH = Path("data/state/liquidation_redeploy_shadow.jsonl")
_REGIME_STATUS = Path("data/state/regime_cash_status.json")
_SENT_CACHE = Path("data/state/sentiment_cache.json")
_RSI_CACHE = Path("data/state/rsi_cache.json")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        if not path.exists():
            return {}
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def load_live_candidates_from_caches(
    *,
    sent_path: Path = _SENT_CACHE,
    rsi_path: Path = _RSI_CACHE,
) -> list[Candidate]:
    sent = _read_json(sent_path).get("sentiment") or {}
    rsi = _read_json(rsi_path).get("rsi") or {}
    pairs: set[str] = set()
    if isinstance(sent, dict):
        pairs |= {str(k).upper() for k in sent}
    if isinstance(rsi, dict):
        pairs |= {str(k).upper() for k in rsi}
    out: list[Candidate] = []
    for pair in sorted(pairs):
        s_raw = sent.get(pair) if isinstance(sent, dict) else None
        if isinstance(s_raw, dict):
            s_val = s_raw.get("score", s_raw.get("sentiment"))
        else:
            s_val = s_raw
        r_raw = rsi.get(pair) if isinstance(rsi, dict) else None
        if isinstance(r_raw, dict):
            r_val = r_raw.get("rsi", r_raw.get("value"))
        else:
            r_val = r_raw
        try:
            s_f = float(s_val) if s_val is not None else None
        except Exception:
            s_f = None
        try:
            r_f = float(r_val) if r_val is not None else None
        except Exception:
            r_f = None
        score = 0.0
        if s_f is not None:
            score += max(-0.5, min(0.5, s_f)) * 0.6 + 0.3
        if r_f is not None:
            if r_f <= 55:
                score += 0.25
            elif r_f <= 65:
                score += 0.05
            else:
                score -= 0.2
        out.append(
            Candidate(
                pair=pair,
                score=round(score, 4),
                rsi=r_f,
                sentiment=s_f,
                is_new_pair=True,
            )
        )
    return out


def append_shadow_log_line(record: Mapping[str, Any], path: Path | None = None) -> Path:
    """Append one JSON line. Never raises to callers (best-effort)."""
    out = path or SHADOW_LOG_PATH
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(dict(record), default=str) + "\n")
    except Exception as exc:
        logger.warning("[LIQ-REDEPLOY-SHADOW] append failed: %s", exc)
    return out


def record_free_capital_shadow(
    *,
    sell_pair: str,
    sell_reason: str,
    proceeds_usd: float,
    source: str,
    event_ts: str | None = None,
    extra: Mapping[str, Any] | None = None,
    cfg: Mapping[str, Any] | None = None,
    log_path: Path | None = None,
) -> dict[str, Any]:
    """Evaluate shadow hop and auto-append. **orders_placed always 0.**"""
    c = merge_cfg(cfg)
    # Live auto path is shadow-only even if someone sets mode live_partial in cfg copy
    c["mode"] = "shadow"
    st = _read_json(_REGIME_STATUS)
    entry = st.get("entry") if isinstance(st.get("entry"), dict) else {}
    try:
        cands = load_live_candidates_from_caches()
    except Exception:
        cands = []
    dec = evaluate_shadow(
        sell_pair=sell_pair,
        sell_reason=sell_reason,
        proceeds_usd=float(proceeds_usd or 0),
        regime=str(st.get("regime") or "unknown"),
        allow_new_buys=bool(st.get("allow_new_buys", True)),
        entry_gates=entry or {
            "max_rsi": 55.0,
            "min_sentiment": 0.25,
            "min_sentiment_new_pair": 0.35,
        },
        candidates=cands,
        cfg=c,
        cooldown_pairs=[str(sell_pair or "").upper()],
    )
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    payload: dict[str, Any] = {
        "type": "live_auto",
        "schema": "liquidation_redeploy_shadow_event_v1",
        "as_of": now,
        "event_ts": event_ts or now,
        "source": source,
        "orders_placed": 0,
        "mode": "shadow",
        "regime": st.get("regime"),
        "allow_new_buys": st.get("allow_new_buys"),
        "rebalance_cap_usd": st.get("rebalance_cap_usd"),
        "decision": dec.to_dict(),
    }
    if extra:
        payload["extra"] = dict(extra)
    append_shadow_log_line(payload, path=log_path)
    try:
        logger.info(
            "[LIQ-REDEPLOY-SHADOW] source=%s sell=%s reason=%s proceeds=%.2f "
            "fire=%s skip=%s size=%.2f -> %s orders=0",
            source,
            dec.sell_pair,
            dec.sell_reason,
            dec.proceeds_usd,
            dec.fire,
            dec.skip_reason,
            dec.size_usd,
            dec.candidate_pair,
        )
    except Exception:
        pass
    return payload


def record_from_disposition_event(disp: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Hook for runner capital disposition records."""
    out: list[dict[str, Any]] = []
    et = str(disp.get("event_type") or "")
    sold = disp.get("pairs_sold") or disp.get("sold") or []
    if isinstance(sold, str):
        sold = [sold]
    # proceeds: prefer cash delta / amount fields
    proceeds = (
        disp.get("proceeds_usd")
        or disp.get("amount_usd")
        or disp.get("delta_cash")
        or 0.0
    )
    try:
        proceeds_f = abs(float(proceeds or 0))
    except Exception:
        proceeds_f = 0.0
    # map disposition to sell reason for allow/deny
    if et == "manual_liquidation_to_cash":
        reason = "rotation_exchange"  # free capital hop policy treats as rotation-class
    elif et == "manual_crypto_swap":
        reason = "manual_crypto_swap"
    else:
        reason = et or "unknown"
    pairs = [str(p).upper() for p in sold if p] or ["UNKNOWN"]
    # split proceeds across sold pairs if multiple
    n = max(1, len([p for p in pairs if p != "UNKNOWN"]))
    per = proceeds_f / n if proceeds_f else 0.0
    for pair in pairs:
        if pair == "UNKNOWN" and proceeds_f <= 0:
            continue
        rec = record_free_capital_shadow(
            sell_pair=pair,
            sell_reason=reason,
            proceeds_usd=per if per > 0 else proceeds_f,
            source="runner_disposition",
            event_ts=str(disp.get("ts") or "") or None,
            extra={"event_type": et, "action": disp.get("action"), "raw_keys": list(disp.keys())[:20]},
        )
        out.append(rec)
    return out


def record_from_ledger_sell_row(row: Mapping[str, Any], *, source: str = "fill_recon") -> dict[str, Any] | None:
    """Hook after a SELL is written to the ledger (rotation / stop)."""
    if str(row.get("side") or "").upper() != "SELL":
        return None
    reason = str(row.get("reason") or row.get("exit_reason") or "")
    pair = str(row.get("pair") or "")
    qty = row.get("qty") if row.get("qty") is not None else row.get("quantity")
    px = row.get("exit_price") or row.get("entry_price") or row.get("price")
    try:
        usd = float(qty) * float(px) if qty is not None and px is not None else float(row.get("usd") or 0)
    except Exception:
        usd = 0.0
    if usd < 50 and "rotation" not in reason.lower() and "stop" not in reason.lower():
        return None
    return record_free_capital_shadow(
        sell_pair=pair,
        sell_reason=reason,
        proceeds_usd=usd,
        source=source,
        event_ts=str(row.get("timestamp") or "") or None,
        extra={"order_id": row.get("order_id"), "pnl": row.get("pnl")},
    )
