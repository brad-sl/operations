#!/usr/bin/env python3
"""
Normalized rolling return-entropy shadow — regime / soft-filter research only.

Doctrine (Brad 2026-08-30)
--------------------------
Shannon entropy on a return histogram is a **distribution concentration** feature,
not a direction oracle and not a Two-Sigma monopoly story.

  H_raw  = -Σ p_i log2(p_i)
  H_norm = H_raw / log2(k)   ∈ [0, 1] when k bins are used

Low H_norm  → returns piled in few bins (structure / low dispersion shape)
High H_norm → flatter histogram (more uniform across bins)

Pre-registered cutoffs (arbitrary implementation knobs — NOT Shannon constants):
  structure_max = 0.35   # tweet-ish "structure"
  noise_min     = 0.70   # tweet-ish "noise"
  mid band      = no opinion

Never mutates config. Never places orders. Never seats / buys / promotes.
RVOL/turnover spirit: scout → evaluate only.

Live board writes labels + H_norm for basket (+ optional extras).
Offline dig (research/return_entropy_filter_shadow.py) owns edge claims.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests

from phase6.core.paths import PROJECT_ROOT, load_trading_basket

PUBLIC = "https://api.exchange.coinbase.com"
UA = {"User-Agent": "phase6-return-entropy-shadow/1.0 (research; no orders)"}

STATE_DIR = PROJECT_ROOT / "data" / "state"
LATEST = STATE_DIR / "return_entropy_shadow_latest.json"
HISTORY = STATE_DIR / "return_entropy_shadow_history.jsonl"
MD_REPORT = PROJECT_ROOT / "reports" / "RETURN_ENTROPY_SHADOW_LATEST.md"
METRICS_MD = PROJECT_ROOT / "reports" / "RETURN_ENTROPY_SUCCESS_METRICS.md"

# ---------------------------------------------------------------------------
# Pre-registered knobs (freeze before any promote talk)
# ---------------------------------------------------------------------------


@dataclass
class EntropyConfig:
    window: int = 48  # hourly bars for live board; dig may use daily 30
    n_bins: int = 10
    structure_max: float = 0.35  # H_norm < this → structure
    noise_min: float = 0.70  # H_norm > this → noise
    # Bin edges:
    #   fixed (default) — absolute return grid so low-dispersion windows can
    #     actually land in few bins (adaptive ±kσ re-scales and often keeps H high).
    #   adaptive_std — ±edge_scale_k * window std around mean (shape-only).
    edge_mode: str = "fixed"  # fixed | adaptive_std
    fixed_lo: float = -0.025  # hourly simple-return grid default
    fixed_hi: float = 0.025
    edge_scale_k: float = 3.0  # used when edge_mode=adaptive_std
    min_returns: int = 20
    pairs: Tuple[str, ...] = ()  # empty → load basket + anchors
    always_include: Tuple[str, ...] = ("BTC-USD", "ETH-USD")
    lookback_hours: int = 48 * 3  # fetch headroom
    sleep_s: float = 0.05
    candle_workers: int = 6


@dataclass
class PairEntropy:
    pair: str
    h_norm: Optional[float]
    h_raw: Optional[float]
    n_returns: int
    label: str  # structure | mid | noise | insufficient
    last_ret: Optional[float]
    window: int
    n_bins: int
    ok: bool
    error: Optional[str] = None
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Pure math (isolation-tested; no I/O)
# ---------------------------------------------------------------------------


def simple_returns(closes: Sequence[float]) -> List[float]:
    """Close-to-close simple returns. Skips non-positive prices."""
    out: List[float] = []
    for a, b in zip(closes, closes[1:]):
        try:
            a_f, b_f = float(a), float(b)
        except (TypeError, ValueError):
            continue
        if a_f <= 0 or b_f <= 0:
            continue
        out.append((b_f / a_f) - 1.0)
    return out


def log_returns(closes: Sequence[float]) -> List[float]:
    out: List[float] = []
    for a, b in zip(closes, closes[1:]):
        try:
            a_f, b_f = float(a), float(b)
        except (TypeError, ValueError):
            continue
        if a_f <= 0 or b_f <= 0:
            continue
        out.append(math.log(b_f / a_f))
    return out


def _std(xs: Sequence[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    return math.sqrt(max(var, 0.0))


def histogram_probs(
    values: Sequence[float],
    n_bins: int,
    lo: float,
    hi: float,
) -> List[float]:
    """Equal-width histogram probabilities over [lo, hi]; tails clamp into edge bins."""
    if n_bins < 2 or hi <= lo or not values:
        return []
    counts = [0] * n_bins
    width = (hi - lo) / n_bins
    if width <= 0:
        return []
    for v in values:
        if v <= lo:
            idx = 0
        elif v >= hi:
            idx = n_bins - 1
        else:
            idx = int((v - lo) / width)
            idx = max(0, min(n_bins - 1, idx))
        counts[idx] += 1
    total = float(sum(counts))
    if total <= 0:
        return []
    return [c / total for c in counts]


def shannon_entropy_raw(probs: Sequence[float]) -> float:
    h = 0.0
    for p in probs:
        if p > 0.0:
            h -= p * math.log(p, 2)
    return h


def shannon_entropy_normalized(
    values: Sequence[float],
    n_bins: int = 10,
    *,
    lo: Optional[float] = None,
    hi: Optional[float] = None,
    edge_scale_k: float = 3.0,
    edge_mode: str = "fixed",
    fixed_lo: float = -0.025,
    fixed_hi: float = 0.025,
) -> Tuple[Optional[float], Optional[float], Dict[str, Any]]:
    """
    Return (H_norm, H_raw, meta).

    H_norm = H_raw / log2(n_bins) so theoretical max is 1.0 when all bins equal
    and the support spans the full bin grid. Degenerate (all mass one bin) → 0.

    Prefer edge_mode='fixed' for regime filters: absolute return bins let quiet
    windows concentrate. adaptive_std measures shape only and often stays high.
    """
    meta: Dict[str, Any] = {"n": len(values), "n_bins": n_bins, "edge_mode": edge_mode}
    if len(values) < 2 or n_bins < 2:
        return None, None, {**meta, "error": "short"}
    std = _std(values)
    mean = sum(values) / len(values)
    if lo is None or hi is None:
        if edge_mode == "adaptive_std":
            half = max(edge_scale_k * std, 1e-6)
            lo = mean - half
            hi = mean + half
        else:
            lo = float(fixed_lo)
            hi = float(fixed_hi)
            if hi <= lo:
                return None, None, {**meta, "error": "bad_fixed_edges"}
    meta["lo"] = lo
    meta["hi"] = hi
    meta["std"] = std
    probs = histogram_probs(values, n_bins, lo, hi)
    if not probs:
        return None, None, {**meta, "error": "hist_fail"}
    h_raw = shannon_entropy_raw(probs)
    denom = math.log(n_bins, 2)
    h_norm = h_raw / denom if denom > 0 else None
    meta["nonzero_bins"] = sum(1 for p in probs if p > 0)
    return h_norm, h_raw, meta


def label_entropy(
    h_norm: Optional[float],
    cfg: EntropyConfig,
) -> str:
    if h_norm is None:
        return "insufficient"
    if h_norm < cfg.structure_max:
        return "structure"
    if h_norm > cfg.noise_min:
        return "noise"
    return "mid"


def rolling_entropy_series(
    returns: Sequence[float],
    window: int,
    n_bins: int = 10,
    edge_scale_k: float = 3.0,
    *,
    edge_mode: str = "fixed",
    fixed_lo: float = -0.025,
    fixed_hi: float = 0.025,
) -> List[Optional[float]]:
    """
    Causal rolling H_norm: at index i, uses returns[i-window+1 : i+1] only.
    First window-1 entries are None.
    """
    out: List[Optional[float]] = [None] * len(returns)
    if window < 5 or len(returns) < window:
        return out
    for i in range(window - 1, len(returns)):
        chunk = returns[i - window + 1 : i + 1]
        h_n, _, _ = shannon_entropy_normalized(
            chunk,
            n_bins=n_bins,
            edge_scale_k=edge_scale_k,
            edge_mode=edge_mode,
            fixed_lo=fixed_lo,
            fixed_hi=fixed_hi,
        )
        out[i] = h_n
    return out


def entropy_for_closes(
    closes: Sequence[float],
    cfg: Optional[EntropyConfig] = None,
    *,
    use_log: bool = False,
) -> PairEntropy:
    """Compute latest-window entropy for a close series (pair filled by caller)."""
    cfg = cfg or EntropyConfig()
    rets = log_returns(closes) if use_log else simple_returns(closes)
    if len(rets) < max(cfg.min_returns, cfg.window // 2):
        return PairEntropy(
            pair="",
            h_norm=None,
            h_raw=None,
            n_returns=len(rets),
            label="insufficient",
            last_ret=rets[-1] if rets else None,
            window=cfg.window,
            n_bins=cfg.n_bins,
            ok=False,
            error="short_returns",
        )
    chunk = rets[-cfg.window :] if len(rets) >= cfg.window else rets
    h_n, h_r, meta = shannon_entropy_normalized(
        chunk,
        n_bins=cfg.n_bins,
        edge_scale_k=cfg.edge_scale_k,
        edge_mode=cfg.edge_mode,
        fixed_lo=cfg.fixed_lo,
        fixed_hi=cfg.fixed_hi,
    )
    lab = label_entropy(h_n, cfg)
    reasons = []
    if h_n is not None:
        reasons.append(f"H_norm={h_n:.3f}")
        reasons.append(f"bins_used={meta.get('nonzero_bins')}/{cfg.n_bins}")
    return PairEntropy(
        pair="",
        h_norm=h_n,
        h_raw=h_r,
        n_returns=len(rets),
        label=lab,
        last_ret=rets[-1] if rets else None,
        window=cfg.window,
        n_bins=cfg.n_bins,
        ok=h_n is not None,
        error=meta.get("error"),
        reasons=reasons,
    )


# ---------------------------------------------------------------------------
# Market data
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _utc_now()).astimezone(timezone.utc).isoformat()


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(UA)
    return s


def fetch_hourly_closes(
    pid: str,
    hours: int,
    sess: Optional[requests.Session] = None,
) -> Tuple[List[float], Optional[str]]:
    """Oldest→newest hourly closes from Coinbase public API."""
    sess = sess or _session()
    end = _utc_now()
    start = end - timedelta(hours=hours + 6)
    gran = 3600
    out: List[list] = []
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + timedelta(seconds=gran * 280), end)
        params = {
            "granularity": gran,
            "start": cursor.isoformat().replace("+00:00", "Z"),
            "end": chunk_end.isoformat().replace("+00:00", "Z"),
        }
        try:
            r = sess.get(f"{PUBLIC}/products/{pid}/candles", params=params, timeout=25)
        except Exception as e:
            return [], str(e)[:160]
        if r.status_code != 200:
            return [], f"http_{r.status_code}"
        batch = r.json() or []
        if not isinstance(batch, list):
            return [], "bad_payload"
        out.extend(batch)
        cursor = chunk_end
        time.sleep(0.03)
    by_t: Dict[int, float] = {}
    for c in out:
        try:
            t, close = int(c[0]), float(c[4])
            by_t[t] = close
        except Exception:
            continue
    closes = [by_t[k] for k in sorted(by_t.keys())]
    if len(closes) < 24:
        return closes, "short_history"
    return closes, None


def resolve_pairs(cfg: EntropyConfig) -> List[str]:
    pairs: List[str] = []
    if cfg.pairs:
        pairs.extend(list(cfg.pairs))
    else:
        try:
            basket = load_trading_basket() or []
        except Exception:
            basket = []
        pairs.extend(list(basket))
    for p in cfg.always_include:
        if p not in pairs:
            pairs.append(p)
    # de-dupe preserve order
    seen = set()
    out: List[str] = []
    for p in pairs:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


# ---------------------------------------------------------------------------
# Shadow run
# ---------------------------------------------------------------------------


def compute_pair(pid: str, cfg: EntropyConfig, sess: requests.Session) -> PairEntropy:
    closes, err = fetch_hourly_closes(pid, cfg.lookback_hours, sess)
    pe = entropy_for_closes(closes, cfg, use_log=False)
    pe.pair = pid
    if err and not pe.ok:
        pe.error = err
        pe.ok = False
    elif err:
        pe.reasons.append(f"fetch_note={err}")
    return pe


def run_return_entropy_shadow(cfg: Optional[EntropyConfig] = None) -> Dict[str, Any]:
    """
    Live shadow board: H_norm + label per pair. No orders / no config writes.
    """
    cfg = cfg or EntropyConfig()
    now = _utc_now()
    sess = _session()
    pairs = resolve_pairs(cfg)
    rows: List[PairEntropy] = []
    for pid in pairs:
        try:
            rows.append(compute_pair(pid, cfg, sess))
        except Exception as e:
            rows.append(
                PairEntropy(
                    pair=pid,
                    h_norm=None,
                    h_raw=None,
                    n_returns=0,
                    label="insufficient",
                    last_ret=None,
                    window=cfg.window,
                    n_bins=cfg.n_bins,
                    ok=False,
                    error=str(e)[:160],
                )
            )
        time.sleep(cfg.sleep_s)

    by_label = {"structure": 0, "mid": 0, "noise": 0, "insufficient": 0}
    for r in rows:
        by_label[r.label] = by_label.get(r.label, 0) + 1

    summary: Dict[str, Any] = {
        "ts": _iso(now),
        "plain_english": (
            "Return-entropy shadow only — concentration of recent returns, "
            "not a buy signal. structure=low H_norm, noise=high H_norm. "
            "No orders, no promote."
        ),
        "config": {
            "window": cfg.window,
            "n_bins": cfg.n_bins,
            "structure_max": cfg.structure_max,
            "noise_min": cfg.noise_min,
            "edge_mode": cfg.edge_mode,
            "fixed_lo": cfg.fixed_lo,
            "fixed_hi": cfg.fixed_hi,
            "edge_scale_k": cfg.edge_scale_k,
            "note": "cutoffs pre-registered / arbitrary — not Shannon constants; fixed edges default",
        },
        "n_pairs": len(rows),
        "by_label": by_label,
        "pairs": [r.to_dict() for r in rows],
        "success_metrics_doc": str(METRICS_MD.relative_to(PROJECT_ROOT))
        if METRICS_MD.exists()
        else "reports/RETURN_ENTROPY_SUCCESS_METRICS.md",
        "live_hooks": "none — evaluate-only research board",
    }

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps(summary, indent=2, default=str))
    with HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": summary["ts"], "by_label": by_label, "n": len(rows)}) + "\n")

    _write_md(summary)
    return summary


def _write_md(summary: Dict[str, Any]) -> None:
    MD_REPORT.parent.mkdir(parents=True, exist_ok=True)
    cfg = summary.get("config") or {}
    lines = [
        "# Return entropy shadow (latest)",
        "",
        f"- **ts:** {summary.get('ts')}",
        f"- **plain:** {summary.get('plain_english')}",
        f"- **window / bins:** {cfg.get('window')} / {cfg.get('n_bins')}",
        f"- **cutoffs:** structure < {cfg.get('structure_max')} ; noise > {cfg.get('noise_min')}",
        f"- **counts:** {json.dumps(summary.get('by_label'))}",
        "",
        "| pair | H_norm | label | n_ret | last_ret |",
        "|------|--------|-------|-------|----------|",
    ]
    for r in summary.get("pairs") or []:
        hn = r.get("h_norm")
        hn_s = f"{hn:.3f}" if isinstance(hn, (int, float)) else "—"
        lr = r.get("last_ret")
        lr_s = f"{lr:.4f}" if isinstance(lr, (int, float)) else "—"
        lines.append(
            f"| {r.get('pair')} | {hn_s} | {r.get('label')} | {r.get('n_returns')} | {lr_s} |"
        )
    lines += [
        "",
        "## Doctrine",
        "- Shadow only. No seat / buy / promote.",
        "- Success metrics: see `reports/RETURN_ENTROPY_SUCCESS_METRICS.md`.",
        "- Offline dig: `phase6/research/return_entropy_filter_shadow.py`.",
        "",
    ]
    MD_REPORT.write_text("\n".join(lines))


def telegram_summary(summary: Dict[str, Any]) -> str:
    """Short TG body; empty if nothing interesting."""
    by = summary.get("by_label") or {}
    n_s = int(by.get("structure") or 0)
    n_n = int(by.get("noise") or 0)
    if n_s == 0 and n_n == 0:
        return ""
    pairs = summary.get("pairs") or []
    struct = [p["pair"] for p in pairs if p.get("label") == "structure"][:6]
    noise = [p["pair"] for p in pairs if p.get("label") == "noise"][:6]
    bits = [f"ENTROPY shadow struct={n_s} noise={n_n}"]
    if struct:
        bits.append("structure: " + ", ".join(struct))
    if noise:
        bits.append("noise: " + ", ".join(noise))
    bits.append("evaluate-only — no orders")
    return "\n".join(bits)


if __name__ == "__main__":
    s = run_return_entropy_shadow()
    print(json.dumps({"by_label": s.get("by_label"), "n": s.get("n_pairs")}, indent=2))
