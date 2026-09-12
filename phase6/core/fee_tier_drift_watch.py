#!/usr/bin/env python3
"""Fee-tier drift watch — alert when live maker/taker moves ≥N bps from baseline.

Baseline = live Intro-2 book as of Brad GO 2026-09-11 (0.40% maker / 0.80% taker)
after Coinbase Advanced fee-restructure email. SSOT remains fee_tier_snapshot.

Read-only. Never places orders. Cron: empty stdout = silent; body = Telegram.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from phase6.core.paths import STATE_DIR

logger = logging.getLogger(__name__)

LATEST = STATE_DIR / "fee_tier_drift_watch_latest.json"
ALERT_SEEN = STATE_DIR / "fee_tier_drift_alert_seen.json"

# Live book when Brad GO'd the watch (fee email day). Not config_loader placeholders.
BASELINE_MAKER = 0.0040  # 0.40%
BASELINE_TAKER = 0.0080  # 0.80%
DEFAULT_THRESHOLD_BPS = 5.0  # 5 bps of rate = 0.05 percentage points = 0.0005 abs
DEDUPE_HOURS = 72.0


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except Exception:
        return None


def bps_delta(live: Optional[float], baseline: float) -> Optional[float]:
    """Absolute rate delta in basis points (1 bp = 0.0001 rate = 0.01%)."""
    if live is None:
        return None
    try:
        return abs(float(live) - float(baseline)) * 10_000.0
    except (TypeError, ValueError):
        return None


def _hit(delta_bps: Optional[float], threshold_bps: float) -> bool:
    if delta_bps is None:
        return False
    # float guard: 0.0045-0.004 → 4.999… bps without round
    return round(float(delta_bps), 6) + 1e-9 >= float(threshold_bps)

def evaluate_drift(
    tier: Dict[str, Any],
    *,
    baseline_maker: float = BASELINE_MAKER,
    baseline_taker: float = BASELINE_TAKER,
    threshold_bps: float = DEFAULT_THRESHOLD_BPS,
) -> Dict[str, Any]:
    """Return structured drift verdict (no I/O)."""
    maker = tier.get("maker_fee_rate")
    taker = tier.get("taker_fee_rate")
    try:
        maker_f = float(maker) if maker is not None else None
    except (TypeError, ValueError):
        maker_f = None
    try:
        taker_f = float(taker) if taker is not None else None
    except (TypeError, ValueError):
        taker_f = None

    m_bps = bps_delta(maker_f, baseline_maker)
    t_bps = bps_delta(taker_f, baseline_taker)
    thr = float(threshold_bps)

    maker_hit = _hit(m_bps, thr)
    taker_hit = _hit(t_bps, thr)
    drifted = bool(maker_hit or taker_hit)

    def _pct(x: Optional[float]) -> Optional[float]:
        return round(float(x) * 100.0, 4) if x is not None else None

    fingerprint = (
        f"{tier.get('pricing_tier') or '?'}|"
        f"m={maker_f if maker_f is not None else 'na'}|"
        f"t={taker_f if taker_f is not None else 'na'}|"
        f"thr={thr:g}"
    )

    return {
        "schema": "fee_tier_drift_watch_v1",
        "as_of": _iso(),
        "ok": maker_f is not None and taker_f is not None,
        "drifted": drifted,
        "threshold_bps": thr,
        "baseline": {
            "maker_fee_rate": baseline_maker,
            "taker_fee_rate": baseline_taker,
            "maker_fee_pct": _pct(baseline_maker),
            "taker_fee_pct": _pct(baseline_taker),
            "note": "Intro 2 live book 2026-09-11 (pre-email apply)",
        },
        "live": {
            "pricing_tier": tier.get("pricing_tier"),
            "maker_fee_rate": maker_f,
            "taker_fee_rate": taker_f,
            "maker_fee_pct": _pct(maker_f) if maker_f is not None else tier.get("maker_fee_pct"),
            "taker_fee_pct": _pct(taker_f) if taker_f is not None else tier.get("taker_fee_pct"),
            "total_volume": tier.get("total_volume"),
            "next_pricing_tier": tier.get("next_pricing_tier"),
            "next_tier_threshold": tier.get("next_tier_threshold"),
            "next_maker_fee_rate": tier.get("next_maker_fee_rate"),
            "next_taker_fee_rate": tier.get("next_taker_fee_rate"),
        },
        "delta_bps": {
            "maker": round(m_bps, 2) if m_bps is not None else None,
            "taker": round(t_bps, 2) if t_bps is not None else None,
        },
        "hits": {"maker": maker_hit, "taker": taker_hit},
        "fingerprint": fingerprint,
    }


def _load_seen() -> Dict[str, Any]:
    if not ALERT_SEEN.exists():
        return {"fingerprints": {}}
    try:
        d = json.loads(ALERT_SEEN.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {"fingerprints": {}}
    except Exception:
        return {"fingerprints": {}}


def _save_seen(seen: Dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    ALERT_SEEN.write_text(json.dumps(seen, indent=2) + "\n", encoding="utf-8")


def should_page(
    fingerprint: str,
    *,
    seen: Optional[Dict[str, Any]] = None,
    dedupe_hours: float = DEDUPE_HOURS,
) -> Tuple[bool, Dict[str, Any]]:
    """True once per fingerprint within dedupe window; mutates seen."""
    seen = seen if seen is not None else _load_seen()
    raw = seen.get("fingerprints") if isinstance(seen.get("fingerprints"), dict) else {}
    last = _parse_ts(str(raw.get(fingerprint) or ""))
    now = datetime.now(timezone.utc)
    if last is not None and (now - last).total_seconds() < float(dedupe_hours) * 3600.0:
        return False, seen
    raw = dict(raw)
    raw[fingerprint] = now.isoformat()
    # prune > 7× window
    keep: Dict[str, str] = {}
    horizon = max(float(dedupe_hours), 24.0) * 3600.0 * 7.0
    for k, v in raw.items():
        dt = _parse_ts(str(v))
        if dt is None or (now - dt).total_seconds() < horizon:
            keep[k] = str(v)
    seen["fingerprints"] = keep
    seen["updated_at"] = now.isoformat()
    return True, seen


def format_alert(verdict: Dict[str, Any]) -> str:
    """Plain-English Telegram body (no markdown spam)."""
    live = verdict.get("live") or {}
    base = verdict.get("baseline") or {}
    d = verdict.get("delta_bps") or {}
    hits = verdict.get("hits") or {}
    bits = []
    if hits.get("maker"):
        bits.append(
            f"maker {base.get('maker_fee_pct')}% → {live.get('maker_fee_pct')}% "
            f"(Δ {d.get('maker')} bps)"
        )
    if hits.get("taker"):
        bits.append(
            f"taker {base.get('taker_fee_pct')}% → {live.get('taker_fee_pct')}% "
            f"(Δ {d.get('taker')} bps)"
        )
    change = "; ".join(bits) or "rate move"
    direction_hint = ""
    try:
        lm = float(live.get("maker_fee_rate"))
        bm = float(base.get("maker_fee_rate"))
        lt = float(live.get("taker_fee_rate"))
        bt = float(base.get("taker_fee_rate"))
        worse = (lm + lt) > (bm + bt)
        direction_hint = " (higher drag)" if worse else " (lower drag)"
    except Exception:
        pass
    lines = [
        f"FEE TIER DRIFT ≥{verdict.get('threshold_bps')} bps{direction_hint}",
        f"Tier: {live.get('pricing_tier') or '?'}",
        change,
        f"Vol 30d: {live.get('total_volume')}",
        f"Next: {live.get('next_pricing_tier')} @ {live.get('next_tier_threshold')}",
        "SSOT: data/state/fee_tier_snapshot_latest.json — no bot knob change auto-applied.",
    ]
    return "\n".join(lines)


def write_latest(verdict: Dict[str, Any]) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps(verdict, indent=2, default=str) + "\n", encoding="utf-8")
    return LATEST


def run_watch(
    *,
    refresh: bool = True,
    threshold_bps: float = DEFAULT_THRESHOLD_BPS,
    baseline_maker: float = BASELINE_MAKER,
    baseline_taker: float = BASELINE_TAKER,
    dedupe_hours: float = DEDUPE_HOURS,
    page: bool = True,
    exchange: Any = None,
) -> Dict[str, Any]:
    """Refresh snapshot (optional), evaluate drift, write state, optionally mark page."""
    snap: Dict[str, Any] = {}
    if refresh:
        from phase6.core.fee_tier_snapshot import run_fee_tier_snapshot

        snap = run_fee_tier_snapshot(exchange=exchange)
    else:
        from phase6.core.fee_tier_snapshot import load_latest_tier

        snap = load_latest_tier() or {}

    if not snap.get("ok"):
        verdict = {
            "schema": "fee_tier_drift_watch_v1",
            "as_of": _iso(),
            "ok": False,
            "drifted": False,
            "error": snap.get("error") or "snapshot_not_ok",
            "threshold_bps": threshold_bps,
            "page": False,
            "telegram_body": None,
        }
        write_latest(verdict)
        return verdict

    tier = snap.get("tier") or {}
    verdict = evaluate_drift(
        tier,
        baseline_maker=baseline_maker,
        baseline_taker=baseline_taker,
        threshold_bps=threshold_bps,
    )
    verdict["snapshot_ts"] = snap.get("ts")
    verdict["page"] = False
    verdict["telegram_body"] = None
    verdict["deduped"] = False

    if verdict.get("drifted") and page:
        do_page, seen = should_page(
            str(verdict.get("fingerprint") or ""),
            dedupe_hours=dedupe_hours,
        )
        if do_page:
            body = format_alert(verdict)
            verdict["page"] = True
            verdict["telegram_body"] = body
            _save_seen(seen)
        else:
            verdict["deduped"] = True

    write_latest(verdict)
    return verdict


__all__ = [
    "BASELINE_MAKER",
    "BASELINE_TAKER",
    "DEFAULT_THRESHOLD_BPS",
    "evaluate_drift",
    "format_alert",
    "run_watch",
    "should_page",
    "bps_delta",
]
