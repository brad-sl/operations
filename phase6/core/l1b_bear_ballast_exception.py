#!/usr/bin/env python3
"""L1b — scoped bear ballast exception (Brad GO 2026-11-21).

Under full REGIME-CASH usdc_park (cap $0), Option B C2 seeder is armed but
starved (zero_step / c2_seed_park). L1b allows **BTC/ETH micro ballast only**
while park + shell freeze stay for everything else.

Live when:
  data/state/l1b_bear_ballast_exception_LIVE exists
  AND data/state/l1b_bear_ballast_exception_KILL does NOT exist

Clip default $35 (soft-down proven). Does not lift global allow_new_buys.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from phase6.core.paths import CONFIG_DIR, STATE_DIR

logger = logging.getLogger(__name__)

SCHEMA = "l1b_bear_ballast_exception_v1"
LIVE_FLAG = STATE_DIR / "l1b_bear_ballast_exception_LIVE"
KILL_PATH = STATE_DIR / "l1b_bear_ballast_exception_KILL"
CONFIG_PATH = CONFIG_DIR / "l1b_bear_ballast_exception.json"
LATEST_PATH = STATE_DIR / "ops_l1b_go_latest.json"

DEFAULT_CLIP_USD = 35.0
DEFAULT_HARD_MAX_USD = 75.0
BALLAST_PAIRS = frozenset({"BTC-USD", "ETH-USD", "BTC-USDC", "ETH-USDC"})

DEFAULT_CFG: Dict[str, Any] = {
    "schema": SCHEMA,
    "clip_usd": DEFAULT_CLIP_USD,
    "hard_max_usd": DEFAULT_HARD_MAX_USD,
    "pairs": ["BTC-USD", "ETH-USD"],
    "max_buys_per_plan": 1,
    "brad_go": "2026-11-21_l1b_bear_ballast_exception",
    "note": "Scoped BTC/ETH micro under usdc_park; shell freeze stays",
}


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return float(default)
        return float(x)
    except (TypeError, ValueError):
        return float(default)


def load_config() -> Dict[str, Any]:
    cfg = dict(DEFAULT_CFG)
    try:
        if CONFIG_PATH.is_file():
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cfg.update(raw)
    except Exception as e:
        logger.warning("l1b config load failed: %s", e)
    return cfg


def kill_file_on(path: Optional[Path] = None) -> bool:
    try:
        return (path or KILL_PATH).is_file()
    except Exception:
        return False


def live_flag_on(path: Optional[Path] = None) -> bool:
    try:
        return (path or LIVE_FLAG).is_file()
    except Exception:
        return False


def is_live(cfg: Optional[Dict[str, Any]] = None) -> bool:
    """True only with LIVE flag present and KILL absent."""
    _ = cfg  # reserved for future config force-off
    if kill_file_on():
        return False
    return live_flag_on()


def clip_usd(cfg: Optional[Dict[str, Any]] = None) -> float:
    c = cfg or load_config()
    clip = _f(c.get("clip_usd"), DEFAULT_CLIP_USD)
    hard = _f(c.get("hard_max_usd"), DEFAULT_HARD_MAX_USD)
    if hard < 25.0:
        hard = DEFAULT_HARD_MAX_USD
    clip = max(25.0, min(clip, hard))
    return float(clip)


def is_ballast_pair(pair: str) -> bool:
    p = str(pair or "").strip().upper().replace("_", "-")
    if p and "-" not in p:
        p = f"{p}-USD"
    return p in BALLAST_PAIRS


def effective_flat_cap_for_c2(
    regime_cap_usd: float,
    *,
    cfg: Optional[Dict[str, Any]] = None,
) -> float:
    """
    Seeder / C2 floor flat_cap.
    If L1b live and regime cap is starved (<=0), return L1b clip.
    Else return max(regime_cap, 0) (Option B soft-down path unchanged).
    """
    rc = max(0.0, _f(regime_cap_usd, 0.0))
    if is_live(cfg) and rc <= 1e-9:
        return clip_usd(cfg)
    return rc


def c2_seed_step_cap(
    proposed_usd: float,
    regime_cap_usd: Optional[float],
    *,
    cfg: Optional[Dict[str, Any]] = None,
) -> float:
    """
    ADD-RISK hard-pass size for tagged C2 seed.
    Under L1b + zero regime cap → clip to L1b; else min(proposed, regime_or_75, 75).
    """
    proposed = max(0.0, _f(proposed_usd, 0.0))
    if regime_cap_usd is None:
        base = 75.0
    else:
        base = _f(regime_cap_usd, 0.0)
    if is_live(cfg) and base <= 1e-9:
        return min(proposed, clip_usd(cfg), _f((cfg or load_config()).get("hard_max_usd"), 75.0))
    if base <= 1e-9:
        return 0.0
    return min(proposed, base, 75.0)


def arm_live_flag(*, note: str = "") -> Path:
    LIVE_FLAG.parent.mkdir(parents=True, exist_ok=True)
    body = note.strip() or "L1b LIVE"
    LIVE_FLAG.write_text(body + "\n", encoding="utf-8")
    if KILL_PATH.is_file():
        try:
            KILL_PATH.unlink()
        except Exception:
            pass
    return LIVE_FLAG


def clear_live_on_trip(*, reason: str = "tripwire") -> bool:
    """Tripwire / abort: remove LIVE flag so park starvation returns immediately."""
    cleared = False
    try:
        if LIVE_FLAG.is_file():
            LIVE_FLAG.unlink()
            cleared = True
            logger.warning("[L1b] LIVE flag cleared reason=%s", reason)
    except Exception as e:
        logger.warning("[L1b] clear LIVE failed: %s", e)
    try:
        KILL_PATH.write_text(f"auto_clear:{reason}\n", encoding="utf-8")
    except Exception:
        pass
    return cleared
