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
from concurrent.futures import ThreadPoolExecutor, as_completed
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
            from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
            from phase6.core.sentiment_scorer import load_sentiment_scores

            def _load() -> Dict[str, float]:
                return load_sentiment_scores(basket) or {}

            with ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(_load)
                try:
                    loaded = fut.result(timeout=5.0)
                except FuturesTimeout:
                    logger.warning(
                        "[PRE-REBAL REFRESH] load_sentiment_scores timed out after 5s; using cache only"
                    )
                    loaded = {}
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


def _python_executable(project_root: Path) -> str:
    venv = project_root / ".venv/bin/python3"
    if venv.is_file():
        return str(venv)
    return os.environ.get("PYTHON", "python3")


def _run_refresh_script(project_root: Path, rel: str, timeout: float, extra_env: Dict[str, str] | None = None) -> bool:
    script = project_root / rel
    if not script.exists():
        logger.warning(f"[PRE-REBAL REFRESH] missing script {script}")
        return False
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    try:
        proc = subprocess.run(
            [_python_executable(project_root), str(script)],
            cwd=str(project_root),
            timeout=timeout,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        if proc.returncode != 0:
            err_tail = (proc.stderr or proc.stdout or "").strip()[-500:]
            logger.warning(
                f"[PRE-REBAL REFRESH] {rel} exit {proc.returncode}: {err_tail or '(no output)'}"
            )
            return False
        return True
    except subprocess.TimeoutExpired:
        logger.warning(f"[PRE-REBAL REFRESH] timeout {rel} after {timeout}s")
        return False
    except Exception as e:
        logger.warning(f"[PRE-REBAL REFRESH] failed {rel}: {e}")
        return False


def _refresh_missing_pairs_on_demand(
    project_root: Path,
    missing_rsi: List[str],
    missing_sent: List[str],
    timeout: float,
) -> None:
    """Lightweight second pass: full refresher scripts (cap already enforced by caller)."""
    if not missing_rsi and not missing_sent:
        return
    logger.info(
        f"[PRE-REBAL REFRESH] on-demand pass missing_rsi={missing_rsi} missing_sent={missing_sent}"
    )
    half = max(2.0, timeout / 2)
    if missing_rsi:
        _run_refresh_script(project_root, "scripts/refresh_rsi_prices.py", half)
    if missing_sent:
        _run_refresh_script(project_root, "phase6/scripts/refresh_sentiment.py", half)


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
        per_script = max(3.0, remaining * 0.45)
        logger.info(
            f"[PRE-REBAL REFRESH] starting parallel (cap={cap_sec}s) missing_rsi={report['missing_rsi']} "
            f"missing_sent={report['missing_sentiment']}"
        )
        futures = {}
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures[pool.submit(
                _run_refresh_script, PROJECT_ROOT, "scripts/refresh_rsi_prices.py", per_script
            )] = "rsi"
            futures[pool.submit(
                _run_refresh_script, PROJECT_ROOT, "phase6/scripts/refresh_sentiment.py", per_script
            )] = "sentiment"
            for fut in as_completed(futures, timeout=remaining):
                try:
                    fut.result()
                except Exception as exc:
                    logger.warning(f"[PRE-REBAL REFRESH] parallel task {futures[fut]}: {exc}")
        runner._update_price_history_and_calculate_rsi()
        report = assess_basket_coverage(basket, PROJECT_ROOT)
        runner._data_coverage = report  # type: ignore[attr-defined]
        if report["missing_rsi"] or report["missing_sentiment"]:
            leftover = max(2.0, cap_sec - (time.time() - started))
            _refresh_missing_pairs_on_demand(
                PROJECT_ROOT,
                report["missing_rsi"],
                report["missing_sentiment"],
                leftover,
            )
            runner._update_price_history_and_calculate_rsi()
            report = assess_basket_coverage(basket, PROJECT_ROOT)
            runner._data_coverage = report  # type: ignore[attr-defined]

    elapsed = time.time() - started
    from phase6.core.rebalance_quality_gate import assess_data_readiness

    data_ready, data_reasons = assess_data_readiness(runner, report)
    report["decision_ready"] = data_ready
    report["decision_block_reasons"] = data_reasons
    enforced = bool((runner.config_dict.get("global_settings", {}) or {}).get("signal_freshness_enforced"))
    if not report["complete"]:
        if enforced:
            logger.warning(
                f"[PRE-REBAL REFRESH] incomplete coverage after {elapsed:.1f}s — "
                f"rebalance blocked while signal_freshness_enforced: {data_reasons}"
            )
        else:
            logger.warning(
                f"[PRE-REBAL REFRESH] partial coverage after {elapsed:.1f}s — proceeding with stale flags: "
                f"{report['per_pair']}"
            )
    else:
        logger.info(f"[PRE-REBAL REFRESH] basket ready in {elapsed:.1f}s (decision_ready={data_ready})")
    try:
        from phase6.core.basket_signal_coverage import assess_pair_signal_coverage

        sig = assess_pair_signal_coverage(basket)
        report["signal_full_count"] = sig.get("full_count")
        report["signal_complete"] = sig.get("complete")
        if not sig.get("complete"):
            logger.warning(
                "[PRE-REBAL REFRESH] signal coverage %s/%s FULL missing=%s",
                sig.get("full_count"),
                sig.get("basket_size"),
                sig.get("missing_sentiment_fetch"),
            )
    except Exception as e:
        logger.debug("signal coverage assess: %s", e)
    return report