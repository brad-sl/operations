#!/usr/bin/env python3
"""
Pair-level funding / positioning sentiment from public perps ($0).

Primary: OKX (works on this host). Fallback: Gate.io, Bitget.
Bybit/Binance often geo-blocked here — not primary.

Writes data/state/funding_sentiment_cache.json
Policy (locked for shadow): mild CONTRARian — positive funding → slight negative score
  score = -tanh(funding_rate / k), k=0.0008
Optional OI attention boost from OKX open interest usd (normalized lightly).
"""
from __future__ import annotations

import json
import math
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase6.core.paths import FUNDING_SENTIMENT_CACHE, load_trading_basket

UA = "phase6-free-sentiment/1.0 (+local research)"
K_FUNDING = 0.0008  # scale for tanh
TIMEOUT = 25


def _get_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def pair_to_base(pair: str) -> str:
    return pair.replace("-USD", "").replace("-USDT", "").upper()


def okx_inst(base: str) -> str:
    return f"{base}-USDT-SWAP"


def fetch_okx_funding(base: str) -> Optional[Tuple[float, str]]:
    url = f"https://www.okx.com/api/v5/public/funding-rate?instId={okx_inst(base)}"
    try:
        data = _get_json(url)
        rows = data.get("data") or []
        if not rows:
            return None
        fr = float(rows[0]["fundingRate"])
        return fr, "okx"
    except Exception:
        return None


def fetch_okx_oi_usd(base: str) -> Optional[float]:
    url = f"https://www.okx.com/api/v5/public/open-interest?instType=SWAP&instId={okx_inst(base)}"
    try:
        data = _get_json(url)
        rows = data.get("data") or []
        if not rows:
            return None
        return float(rows[0].get("oiUsd") or 0.0)
    except Exception:
        return None


def fetch_gate_funding(base: str) -> Optional[Tuple[float, str]]:
    # Gate uses BTC_USDT
    url = f"https://api.gateio.ws/api/v4/futures/usdt/contracts/{base}_USDT"
    try:
        data = _get_json(url)
        # funding_rate field or funding_rate_indicative
        fr = data.get("funding_rate")
        if fr is None:
            fr = data.get("funding_rate_indicative")
        if fr is None:
            return None
        return float(fr), "gate"
    except Exception:
        return None


def fetch_bitget_funding(base: str) -> Optional[Tuple[float, str]]:
    url = (
        "https://api.bitget.com/api/v2/mix/market/current-fund-rate"
        f"?symbol={base}USDT&productType=USDT-FUTURES"
    )
    try:
        data = _get_json(url)
        rows = data.get("data") or []
        if not rows:
            return None
        return float(rows[0]["fundingRate"]), "bitget"
    except Exception:
        return None


def funding_to_score(fr: float) -> float:
    # mild contrarian
    s = -math.tanh(fr / K_FUNDING)
    return max(-0.5, min(0.5, s))


def main() -> int:
    basket = load_trading_basket()
    now = datetime.now(timezone.utc).isoformat()
    out: Dict[str, Any] = {}
    oi_vals: List[float] = []
    oi_by_pair: Dict[str, float] = {}

    for pair in basket:
        base = pair_to_base(pair)
        got = fetch_okx_funding(base) or fetch_gate_funding(base) or fetch_bitget_funding(base)
        if not got:
            out[pair] = {
                "sentiment": 0.0,
                "funding_rate": None,
                "source": "none",
                "error": "no_funding",
            }
            continue
        fr, src = got
        score = funding_to_score(fr)
        entry = {
            "sentiment": round(score, 4),
            "funding_rate": fr,
            "source": src,
            "policy": "contrarian_tanh",
            "k": K_FUNDING,
        }
        oi = fetch_okx_oi_usd(base) if src == "okx" else None
        if oi is not None and oi > 0:
            entry["oi_usd"] = oi
            oi_by_pair[pair] = oi
            oi_vals.append(oi)
        out[pair] = entry

    # light OI relative attention: do not flip sign; scale magnitude slightly
    if oi_vals:
        log_ois = {p: math.log10(v + 1.0) for p, v in oi_by_pair.items()}
        mean = sum(log_ois.values()) / len(log_ois)
        for pair, entry in out.items():
            if pair not in log_ois:
                continue
            rel = log_ois[pair] - mean
            # ±10% magnitude tweak
            boost = 1.0 + max(-0.1, min(0.1, rel * 0.15))
            entry["sentiment"] = round(
                max(-0.5, min(0.5, entry["sentiment"] * boost)), 4
            )
            entry["oi_boost"] = round(boost, 4)

    payload = {
        "timestamp": now,
        "schema_version": 1,
        "meta": {
            "primary": "okx",
            "fallbacks": ["gate", "bitget"],
            "policy": "contrarian_tanh",
            "basket_size": len(basket),
        },
        "pairs": out,
    }
    # also flat pair keys for simple loaders
    for pair, entry in out.items():
        payload[pair] = entry

    FUNDING_SENTIMENT_CACHE.parent.mkdir(parents=True, exist_ok=True)
    FUNDING_SENTIMENT_CACHE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    nz = sum(1 for p in basket if abs((out.get(p) or {}).get("sentiment") or 0) > 1e-6)
    print(
        f"FUNDING OK pairs={len(basket)} non_zero={nz} "
        f"→ {FUNDING_SENTIMENT_CACHE}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
