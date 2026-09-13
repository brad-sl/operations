"""Tryout sentiment latch (A2) — hold X-clear through rebalance window.

Problem: X refresh then 15m half-life zeros eng scores before ~09:05/21:05 rebalance
even when raw/eng cleared the tryout floor at refresh.

Rule (tryout pairs only):
- At latch write time, if usable score >= tryout floor → record latch.
- Until expires_at (default 45m), evaluate_buy_entry may treat sentiment as
  meeting the floor when eng-aged has decayed below floor.
- Never latches non-tryout, never bypasses buy_block / missfire / RSI / seat caps.
- Free/tee never writes latches (X or lightly-aged eng only).

Brad GO 2026-09-13 with A1+B1 empty-funnel package.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Set

from phase6.core.paths import PROJECT_ROOT

SCHEMA = "tryout_sent_latch_v1"
STATE_PATH = PROJECT_ROOT / "data" / "state" / "tryout_sent_latch.json"
DEFAULT_TTL_MIN = 45.0


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _norm_pair(p: str) -> str:
    return str(p or "").strip().upper().replace("_", "-")


def _parse_ts(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    s = str(raw).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def load_latch(path: Optional[Path] = None) -> Dict[str, Any]:
    p = path or STATE_PATH
    if not p.exists():
        return {"schema": SCHEMA, "updated_at": None, "pairs": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"schema": SCHEMA, "updated_at": None, "pairs": {}}
    if not isinstance(data, dict):
        return {"schema": SCHEMA, "updated_at": None, "pairs": {}}
    pairs = data.get("pairs") if isinstance(data.get("pairs"), dict) else {}
    return {
        "schema": str(data.get("schema") or SCHEMA),
        "updated_at": data.get("updated_at"),
        "pairs": { _norm_pair(k): v for k, v in pairs.items() if isinstance(v, dict) },
        "meta": data.get("meta") if isinstance(data.get("meta"), dict) else {},
    }


def save_latch(data: Mapping[str, Any], path: Optional[Path] = None) -> Path:
    p = path or STATE_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    out = {
        "schema": SCHEMA,
        "updated_at": _utc_now().isoformat(),
        "pairs": dict(data.get("pairs") or {}),
        "meta": dict(data.get("meta") or {}),
    }
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(p)
    return p


def extract_pair_score(blob: Any) -> Optional[float]:
    """Best-effort score from cache row or float."""
    if blob is None:
        return None
    if isinstance(blob, (int, float)):
        return float(blob)
    if not isinstance(blob, dict):
        return None
    for k in (
        "sentiment",
        "sentiment_score",
        "score",
        "eng_sent",
        "value",
        "aged",
        "raw",
    ):
        v = blob.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return None


def write_latches_from_scores(
    scores: Mapping[str, Any],
    *,
    tryout_pairs: Iterable[str],
    floor: float,
    source: str = "x_refresh",
    ttl_min: float = DEFAULT_TTL_MIN,
    now: Optional[datetime] = None,
    path: Optional[Path] = None,
    existing: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    For each tryout pair with score >= floor, set/refresh latch.
    Pairs below floor are left unchanged (do not clear a still-valid prior latch here;
    expiry handles that). Returns full state written.
    """
    now = now or _utc_now()
    ttl_min = float(os.environ.get("TRYOUT_SENT_LATCH_TTL_MIN", ttl_min) or ttl_min)
    expires = now + timedelta(minutes=float(ttl_min))
    state = dict(existing or load_latch(path))
    pairs: Dict[str, Any] = dict(state.get("pairs") or {})
    try_set = {_norm_pair(p) for p in tryout_pairs if p}
    written = 0
    for pair in sorted(try_set):
        raw = scores.get(pair) or scores.get(pair.replace("-USD", ""))
        sc = extract_pair_score(raw)
        if sc is None or float(sc) < float(floor):
            continue
        pairs[pair] = {
            "pair": pair,
            "cleared_sent": float(sc),
            "floor": float(floor),
            "source": str(source),
            "latched_at": now.isoformat(),
            "expires_at": expires.isoformat(),
            "ttl_min": float(ttl_min),
        }
        written += 1
    # Drop expired leftovers
    final: Dict[str, Any] = {}
    for k, v in pairs.items():
        exp = _parse_ts((v or {}).get("expires_at"))
        if exp is not None and exp < now:
            continue
        final[_norm_pair(k)] = v
    out = {
        "schema": SCHEMA,
        "pairs": final,
        "meta": {
            "last_write_source": source,
            "last_write_floor": float(floor),
            "last_write_count": written,
            "ttl_min": float(ttl_min),
        },
    }
    save_latch(out, path=path)
    return out


def active_latch_for_pair(
    pair: str,
    *,
    floor: Optional[float] = None,
    now: Optional[datetime] = None,
    path: Optional[Path] = None,
    state: Optional[Mapping[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Return latch row if unexpired and cleared_sent still meets floor (if given)."""
    now = now or _utc_now()
    st = state or load_latch(path)
    row = (st.get("pairs") or {}).get(_norm_pair(pair))
    if not isinstance(row, dict):
        return None
    exp = _parse_ts(row.get("expires_at"))
    if exp is None or exp < now:
        return None
    cleared = extract_pair_score(row.get("cleared_sent"))
    if cleared is None:
        return None
    fl = float(floor) if floor is not None else float(row.get("floor") or 0.0)
    if float(cleared) < fl:
        return None
    return dict(row)


def apply_latch_to_sentiment(
    pair: str,
    sentiment: Optional[float],
    *,
    floor: float,
    now: Optional[datetime] = None,
    path: Optional[Path] = None,
) -> tuple[Optional[float], Optional[str]]:
    """
    If eng sentiment is below floor but an active latch cleared the floor,
    return (latched_sent, reason_tag). Else (sentiment, None).
    """
    if sentiment is not None and float(sentiment) >= float(floor):
        return sentiment, None
    latch = active_latch_for_pair(pair, floor=floor, now=now, path=path)
    if not latch:
        return sentiment, None
    cleared = float(latch["cleared_sent"])
    return cleared, (
        f"tryout_sent_latch {cleared:.3f}>={float(floor):.2f} "
        f"src={latch.get('source')} exp={latch.get('expires_at')}"
    )


def refresh_tryout_latches_from_x_cache(
    *,
    x_cache_path: Optional[Path] = None,
    policy: Optional[Mapping[str, Any]] = None,
    path: Optional[Path] = None,
    ttl_min: float = DEFAULT_TTL_MIN,
) -> Dict[str, Any]:
    """Called after live X refresh: latch tryout pairs that clear tryout floor on raw X."""
    from phase6.core.regime_cash_policy import (
        _recovery_rec,
        load_policy,
        recovery_quality_tryout_cfg,
        recovery_tryout_pairs_effective,
    )

    pol = policy if isinstance(policy, dict) else load_policy()
    rec = _recovery_rec(pol) or {}
    qt = recovery_quality_tryout_cfg(rec) if rec else {"min_sentiment": 0.30}
    floor = float(qt.get("min_sentiment") or 0.30)
    try:
        tryout = recovery_tryout_pairs_effective(rec) if rec else set()
    except Exception:
        tryout = set(qt.get("tryout_pairs") or [])
    if not tryout:
        tryout = set(qt.get("tryout_pairs") or [])

    x_path = x_cache_path or (PROJECT_ROOT / "data" / "state" / "x_sentiment_cache.json")
    scores: Dict[str, Any] = {}
    if x_path.exists():
        try:
            raw = json.loads(x_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                # pair-keyed cache
                for k, v in raw.items():
                    if k in ("timestamp", "schema_version", "meta", "sentiment"):
                        continue
                    if isinstance(v, dict) and (
                        "sentiment" in v or "sentiment_score" in v or "post_count" in v
                    ):
                        scores[_norm_pair(k)] = v
                sent = raw.get("sentiment")
                if isinstance(sent, dict):
                    for k, v in sent.items():
                        scores.setdefault(_norm_pair(k), v)
        except Exception:
            scores = {}

    return write_latches_from_scores(
        scores,
        tryout_pairs=tryout,
        floor=floor,
        source="x_refresh",
        ttl_min=ttl_min,
        path=path,
    )


__all__ = [
    "SCHEMA",
    "STATE_PATH",
    "DEFAULT_TTL_MIN",
    "load_latch",
    "save_latch",
    "write_latches_from_scores",
    "active_latch_for_pair",
    "apply_latch_to_sentiment",
    "refresh_tryout_latches_from_x_cache",
    "extract_pair_score",
]
