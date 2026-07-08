"""
ANALYST-20260705-006 / 008: Pre-rebalance basket data refresh.

Ensures RSI + sentiment coverage for allocator decisions before rebalance window.
Hard cap on blocking time; marks stale pairs explicitly on runner._data_coverage.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from phase6.core.phase6_runner import Phase6Runner

logger = logging.getLogger(__name__)

DEFAULT_CAP_SEC = 15.0
RSI_STALE_SEC = 20 * 60
SENTIMENT_STALE_SEC = 45 * 60


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _load_rsi_map(project_root: Path) -> Dict[str, Any]:
    p = project_root / "data/state/rsi_cache.json"
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
        return data.get("rsi", {}) or {}
    except Exception:
        return {}


def _load_sentiment_map(project_root: Path) -> Dict[str, float]:
    """Parse canonical sentiment_cache.json (schema v3 ``sentiment`` block or legacy ``scores``)."""
    p = project_root / "data/state/sentiment_cache.json"
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
        out: Dict[str, float] = {}

        legacy = data.get("scores")
        if isinstance(legacy, dict):
            for k, v in legacy.items():
                if isinstance(k, str) and isinstance(v, (int, float)):
                    out[k] = float(v)

        schema_ver = data.get("schema_version", 0)
        try:
            schema_ver = int(schema_ver)
        except (TypeError, ValueError):
            schema_ver = 0

        if schema_ver >= 3:
            block = data.get("sentiment") or data.get("data") or {}
            if isinstance(block, dict):
                for pair, entry in block.items():
                    if not isinstance(pair, str) or "-USD" not in pair:
                        continue
                    if isinstance(entry, dict):
                        raw = entry.get(
                            "sentiment_score",
                            entry.get("score", entry.get("sentiment", None)),
                        )
                    else:
                        raw = entry
                    if raw is not None:
                        try:
                            out[pair] = float(raw)
                        except (TypeError, ValueError):
                            pass
        elif not out and isinstance(data, dict):
            # Pre-v3 flat pair keys at top level
            for k, v in data.items():
                if not isinstance(k, str) or "-USD" not in k:
                    continue
                if isinstance(v, (int, float)):
                    out[k] = float(v)
                elif isinstance(v, dict):
                    raw = v.get("sentiment_score", v.get("score", v.get("sentiment")))
                    if raw is not None:
                        try:
                            out[k] = float(raw)
                        except (TypeError, ValueError):
                            pass
        return out
    except Exception:
        pass
    return {}


def assess_basket_coverage(basket: List[str], project_root: Path) -> Dict[str, Any]:
    now = time.time()
    rsi_map = _load_rsi_map(project_root)
    sent_map = _load_sentiment_map(project_root)
    missing_from_cache = [p for p in basket if sent_map.get(p) is None and sent_map.get(p.replace("-USD", "")) is None]
    if missing_from_cache:
        try:
            from phase6.core.sentiment_scorer import load_sentiment_scores

            loaded = load_sentiment_scores(basket) or {}
            for k, v in loaded.items():
                if v is not None and k not in sent_map:
                    sent_map[k] = float(v)
        except Exception:
            pass
    rsi_m = _mtime(project_root / "data/state/rsi_cache.json")
    sent_m = _mtime(project_root / "data/state/sentiment_cache.json")

    per_pair: Dict[str, Dict[str, Any]] = {}
    missing_rsi = []
    missing_sent = []
    stale_rsi = []
    stale_sent = []

    for pair in basket:
        rsi_entry = rsi_map.get(pair, {})
        rsi_val = rsi_entry.get("rsi") if isinstance(rsi_entry, dict) else None
        sent_val = sent_map.get(pair)
        if sent_val is None:
            sent_val = sent_map.get(pair.replace("-USD", ""))

        status = "ok"
        if rsi_val is None:
            missing_rsi.append(pair)
            status = "rsi_missing"
        elif now - rsi_m > RSI_STALE_SEC:
            stale_rsi.append(pair)
            status = "rsi_stale" if status == "ok" else status

        if sent_val is None:
            missing_sent.append(pair)
            status = "sentiment_missing" if status == "ok" else status + "+sentiment_missing"
        elif now - sent_m > SENTIMENT_STALE_SEC:
            stale_sent.append(pair)
            if status == "ok":
                status = "sentiment_stale"

        per_pair[pair] = {
            "rsi": rsi_val,
            "sentiment": sent_val,
            "status": status,
        }

    return {
        "per_pair": per_pair,
        "missing_rsi": missing_rsi,
        "missing_sentiment": missing_sent,
        "stale_rsi": stale_rsi,
        "stale_sentiment": stale_sent,
        "complete": not (missing_rsi or missing_sent),
    }


def _run_refresh_script(project_root: Path, rel: str, timeout: float) -> bool:
    script = project_root / rel
    if not script.exists():
        logger.warning(f"[PRE-REBAL REFRESH] missing script {script}")
        return False
    try:
        subprocess.run(
            ["python3", str(script)],
            cwd=str(project_root),
            timeout=timeout,
            capture_output=True,
            check=False,
        )
        return True
    except subprocess.TimeoutExpired:
        logger.warning(f"[PRE-REBAL REFRESH] timeout {rel} after {timeout}s")
        return False
    except Exception as e:
        logger.warning(f"[PRE-REBAL REFRESH] failed {rel}: {e}")
        return False


def ensure_basket_signals_ready(
    runner: "Phase6Runner",
    *,
    cap_sec: float = DEFAULT_CAP_SEC,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    Blocking pre-rebalance refresh (parallel scripts, hard cap).
    Updates runner.rsi_values from cache after refresh attempt.
    """
    from phase6.core.paths import PROJECT_ROOT

    basket = list(getattr(runner, "FIXED_UNIVERSE", []))
    started = time.time()
    report = assess_basket_coverage(basket, PROJECT_ROOT)
    runner._data_coverage = report  # type: ignore[attr-defined]

    need_refresh = force_refresh or not report["complete"] or report["stale_rsi"] or report["stale_sentiment"]
    if need_refresh:
        remaining = max(2.0, cap_sec - (time.time() - started))
        half = remaining / 2
        logger.info(
            f"[PRE-REBAL REFRESH] starting (cap={cap_sec}s) missing_rsi={report['missing_rsi']} "
            f"missing_sent={report['missing_sentiment']}"
        )
        _run_refresh_script(PROJECT_ROOT, "scripts/refresh_rsi_prices.py", half)
        _run_refresh_script(PROJECT_ROOT, "phase6/scripts/refresh_sentiment.py", half)
        runner._update_price_history_and_calculate_rsi()
        report = assess_basket_coverage(basket, PROJECT_ROOT)
        runner._data_coverage = report  # type: ignore[attr-defined]

    elapsed = time.time() - started
    if not report["complete"]:
        logger.warning(
            f"[PRE-REBAL REFRESH] partial coverage after {elapsed:.1f}s — proceeding with stale flags: "
            f"{report['per_pair']}"
        )
    else:
        logger.info(f"[PRE-REBAL REFRESH] basket ready in {elapsed:.1f}s")
    return report