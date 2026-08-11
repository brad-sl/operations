"""
Hot-reload global_settings.pairs into a running Phase6Runner without process restart.

Membership only: updates FIXED_UNIVERSE + config_dict pairs; seeds prices for adds;
never places orders or liquidates removed pairs.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from phase6.core.paths import STATE_DIR, TRADING_CONFIG_PHASE6, load_trading_basket

logger = logging.getLogger("phase6.basket_hot_reload")

STICKY = ("BTC-USD", "ETH-USD")
MIN_PAIRS = 6
RELOAD_FLAG = STATE_DIR / "basket_reload.flag"
RECEIPT = STATE_DIR / "basket_hot_reload_latest.json"

PathLike = Union[str, Path]


def pairs_changed(old: Sequence[str], new: Sequence[str]) -> bool:
    return list(old) != list(new)


def apply_basket_hot_reload(
    runner: Any,
    new_pairs: Sequence[str],
    *,
    reason: str = "unspecified",
    seed_prices: bool = True,
    sticky: Sequence[str] = STICKY,
    min_pairs: int = MIN_PAIRS,
) -> Dict[str, Any]:
    """Apply a new pairs list onto runner. Safe no-op if unchanged."""
    new_list = [str(p).strip() for p in new_pairs if str(p).strip()]
    old_list = list(getattr(runner, "FIXED_UNIVERSE", []) or [])

    if len(new_list) < min_pairs:
        logger.error(
            "[BASKET-RELOAD] refuse short list n=%s reason=%s",
            len(new_list),
            reason,
        )
        return {"ok": False, "error": "too_short", "n": len(new_list), "changed": False}

    for s in sticky:
        if s not in new_list:
            logger.error(
                "[BASKET-RELOAD] refuse missing sticky %s reason=%s",
                s,
                reason,
            )
            return {
                "ok": False,
                "error": "missing_sticky",
                "pair": s,
                "changed": False,
            }

    if not pairs_changed(old_list, new_list):
        return {"ok": True, "changed": False, "pairs": new_list}

    old_set, new_set = set(old_list), set(new_list)
    added = [p for p in new_list if p not in old_set]
    removed = [p for p in old_list if p not in new_set]

    runner.FIXED_UNIVERSE = list(new_list)
    cfg = getattr(runner, "config_dict", None)
    if isinstance(cfg, dict):
        gs = cfg.setdefault("global_settings", {})
        if isinstance(gs, dict):
            gs["pairs"] = list(new_list)

    seeded: List[str] = []
    if seed_prices:
        ex = getattr(runner, "exchange", None)
        ph = getattr(runner, "price_history", None)
        for p in added:
            try:
                if ex is None or ph is None:
                    break
                recent = ex.get_recent_prices(p, limit=20)
                if recent:
                    for price in recent:
                        ph.add_price(p, price)
                    seeded.append(p)
            except Exception as e:
                logger.warning("[BASKET-RELOAD] seed failed %s: %s", p, e)

    receipt: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "ok": True,
        "changed": True,
        "reason": reason,
        "before": old_list,
        "after": list(new_list),
        "added": added,
        "removed": removed,
        "seeded": seeded,
    }
    try:
        RECEIPT.parent.mkdir(parents=True, exist_ok=True)
        RECEIPT.write_text(json.dumps(receipt, indent=2) + "\n")
    except Exception as e:
        logger.debug("receipt write: %s", e)

    logger.info(
        "[BASKET-RELOAD] added=%s removed=%s n=%s reason=%s",
        added,
        removed,
        len(new_list),
        reason,
    )
    return receipt


def maybe_reload_trading_basket(
    runner: Any,
    config_path: Optional[PathLike] = None,
) -> Dict[str, Any]:
    """
    No-op if config mtime unchanged and no flag.
    Otherwise load pairs from disk and apply_basket_hot_reload.
    """
    path = Path(
        config_path
        or getattr(runner, "config_path", None)
        or TRADING_CONFIG_PHASE6
    )
    force = RELOAD_FLAG.exists()
    try:
        mtime = path.stat().st_mtime
    except OSError as e:
        logger.warning("[BASKET-RELOAD] stat failed: %s", e)
        return {"ok": False, "error": "stat", "changed": False}

    last = getattr(runner, "_basket_config_mtime", None)
    if not force and last is not None and mtime == last:
        return {"ok": True, "changed": False, "skipped": "mtime"}

    try:
        default_path = Path(TRADING_CONFIG_PHASE6).resolve()
        if path.resolve() == default_path:
            new_pairs = load_trading_basket()
        else:
            cfg = json.loads(path.read_text())
            new_pairs = list((cfg.get("global_settings") or {}).get("pairs") or [])
    except Exception as e:
        logger.warning("[BASKET-RELOAD] load pairs failed: %s", e)
        return {"ok": False, "error": "load", "detail": str(e), "changed": False}

    reason = "flag" if force else "config_mtime"
    result = apply_basket_hot_reload(
        runner, new_pairs, reason=reason, seed_prices=True
    )
    # Always advance mtime marker after a successful read attempt so we don't
    # spin on a refused short list every cycle — unless force flag and refuse.
    if result.get("ok") is not False or not force:
        runner._basket_config_mtime = mtime
    if force:
        try:
            RELOAD_FLAG.unlink(missing_ok=True)  # type: ignore[call-arg]
        except TypeError:
            if RELOAD_FLAG.exists():
                RELOAD_FLAG.unlink()
        except OSError as e:
            logger.debug("flag unlink: %s", e)
    return result
