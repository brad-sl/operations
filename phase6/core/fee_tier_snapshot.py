#!/usr/bin/env python3
"""Live Coinbase fee-tier snapshot (read-only). Never places orders.

Writes data/state/fee_tier_snapshot_latest.json so config constants stop being
treated as live truth. See docs/design/LIMIT_FIRST_BUY_DESIGN.md Phase A.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from phase6.core.paths import PROJECT_ROOT, STATE_DIR

logger = logging.getLogger(__name__)

LATEST = STATE_DIR / "fee_tier_snapshot_latest.json"
HISTORY = STATE_DIR / "fee_tier_snapshot_history.jsonl"
MD = PROJECT_ROOT / "reports" / "FEE_TIER_SNAPSHOT_LATEST.md"


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_transaction_summary(exchange: Any) -> Dict[str, Any]:
    """GET brokerage transaction_summary via live client. No orders."""
    out: Dict[str, Any] = {"ok": False}
    if exchange is None:
        out["error"] = "no_exchange"
        return out
    if getattr(exchange, "shadow_mode", False):
        out["error"] = "shadow_mode"
        return out
    if hasattr(exchange, "_ensure_live_client"):
        try:
            exchange._ensure_live_client()
        except Exception as e:
            out["error"] = f"ensure:{e}"[:160]
            return out
    client = getattr(exchange, "real_client", None) or getattr(exchange, "sdk_client", None)
    if client is None:
        out["error"] = "no_client"
        return out
    try:
        if hasattr(client, "get_transaction_summary"):
            resp = client.get_transaction_summary()
        elif hasattr(client, "_request"):
            resp = client._request("GET", "/api/v3/brokerage/transaction_summary", None)
        else:
            out["error"] = "no_method"
            return out
        if hasattr(resp, "to_dict"):
            resp = resp.to_dict()
        if not isinstance(resp, dict):
            out["error"] = "bad_payload"
            return out
        out["ok"] = True
        out["raw_keys"] = list(resp.keys())[:40]
        out["total_volume"] = resp.get("total_volume")
        out["total_fees"] = resp.get("total_fees")
        out["fee_tier"] = resp.get("fee_tier")
        out["next_fee_tier"] = resp.get("next_fee_tier")
        out["next_tier_threshold"] = resp.get("next_tier_threshold")
        out["fee_tier_without_promotion"] = resp.get("fee_tier_without_promotion")
        out["advanced_trade_only_volume"] = resp.get("advanced_trade_only_volume")
        out["advanced_trade_only_fees"] = resp.get("advanced_trade_only_fees")
        return out
    except Exception as e:
        out["error"] = str(e)[:240]
        return out


def normalize_tier(summary: Dict[str, Any]) -> Dict[str, Any]:
    ft = summary.get("fee_tier") or {}
    if not isinstance(ft, dict):
        ft = {}
    def rate(x) -> Optional[float]:
        try:
            if x is None or x == "":
                return None
            return float(x)
        except (TypeError, ValueError):
            return None
    taker = rate(ft.get("taker_fee_rate"))
    maker = rate(ft.get("maker_fee_rate"))
    nxt = summary.get("next_fee_tier") or {}
    return {
        "pricing_tier": ft.get("pricing_tier"),
        "taker_fee_rate": taker,
        "maker_fee_rate": maker,
        "taker_fee_pct": round(taker * 100, 4) if taker is not None else None,
        "maker_fee_pct": round(maker * 100, 4) if maker is not None else None,
        "total_volume": summary.get("total_volume"),
        "total_fees": summary.get("total_fees"),
        "next_pricing_tier": nxt.get("pricing_tier") if isinstance(nxt, dict) else None,
        "next_taker_fee_rate": rate(nxt.get("taker_fee_rate")) if isinstance(nxt, dict) else None,
        "next_maker_fee_rate": rate(nxt.get("maker_fee_rate")) if isinstance(nxt, dict) else None,
        "next_tier_threshold": summary.get("next_tier_threshold"),
        # Stale config_loader constants (documentation debt)
        "config_loader_maker_constant": 0.0025,
        "config_loader_taker_constant": 0.0040,
        "config_loader_stale": True,
        "note": "Prefer these live rates over config_loader COINBASE_* constants",
    }


def write_snapshot(payload: Dict[str, Any]) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    with HISTORY.open("a") as f:
        f.write(json.dumps({"ts": payload.get("ts"), **{k: payload.get(k) for k in ("ok", "tier")}}, default=str) + "\n")
    tier = payload.get("tier") or {}
    lines = [
        "# Fee tier snapshot (live)",
        "",
        f"**As of:** {payload.get('ts')}  ",
        f"**ok:** {payload.get('ok')}  ",
        "",
        f"- Tier: **{tier.get('pricing_tier')}**",
        f"- Taker: **{tier.get('taker_fee_pct')}%** (`{tier.get('taker_fee_rate')}`)",
        f"- Maker: **{tier.get('maker_fee_pct')}%** (`{tier.get('maker_fee_rate')}`)",
        f"- Volume: {tier.get('total_volume')}",
        f"- Next: {tier.get('next_pricing_tier')} @ {tier.get('next_tier_threshold')}",
        "",
        "`config_loader` COINBASE_* constants are **not** live truth — use this file.",
        "",
        f"State: `{LATEST.relative_to(PROJECT_ROOT)}`",
        "",
    ]
    MD.parent.mkdir(parents=True, exist_ok=True)
    MD.write_text("\n".join(lines))
    return LATEST


def run_fee_tier_snapshot(*, exchange: Any = None) -> Dict[str, Any]:
    """Fetch + persist. Constructs live client if exchange not passed."""
    own = False
    if exchange is None:
        from phase6.core.exchange_client import CoinbaseExchangeClient

        exchange = CoinbaseExchangeClient(mode="live")
        own = True
    summary = fetch_transaction_summary(exchange)
    payload: Dict[str, Any] = {
        "ts": _iso(),
        "ok": bool(summary.get("ok")),
        "error": summary.get("error"),
        "tier": normalize_tier(summary) if summary.get("ok") else {},
        "summary_keys": summary.get("raw_keys"),
        "place_orders": False,
    }
    write_snapshot(payload)
    return payload


def load_latest_tier() -> Dict[str, Any]:
    if not LATEST.exists():
        return {}
    try:
        return json.loads(LATEST.read_text())
    except Exception:
        return {}
