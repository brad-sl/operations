#!/usr/bin/env python3
"""
Stand-down filter C shadow — elevated-tape process would-block logger.

Doctrine (Brad 2026-08-31 C dig)
--------------------------------
C = when tape is already elevated, do NOT let process machinery enter
(rebalance / allocator / runner buys). Not chase-whale. Not buy-the-FOMO-leg.

This module is **shadow only**:
  - Never mutates config
  - Never places orders
  - Never wires evaluate_buy_entry / runner / knobs
  - Logs would-block on frozen primary def: process + r24 >= 5%

Edge class from dig: ATTENTION_ONLY_less_loss_path — not HIT abs.
Promote bar: Brad GO + longer OOS + capital-reuse CF. Default: log only.

Artifacts:
  data/state/standdown_filter_c_shadow_latest.json
  data/state/standdown_filter_c_shadow_events.jsonl
  reports/STANDDOWN_FILTER_C_SHADOW_LATEST.md
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests

from phase6.core.paths import PROJECT_ROOT, STATE_DIR, load_trading_basket

PUBLIC = "https://api.exchange.coinbase.com"
UA = {"User-Agent": "phase6-standdown-filter-c-shadow/1.0 (research; no orders)"}

LATEST = STATE_DIR / "standdown_filter_c_shadow_latest.json"
EVENTS = STATE_DIR / "standdown_filter_c_shadow_events.jsonl"
MD_REPORT = PROJECT_ROOT / "reports" / "STANDDOWN_FILTER_C_SHADOW_LATEST.md"
RSI_CACHE = STATE_DIR / "rsi_cache.json"
RECENT_BUYS_LOOKBACK_H = 36

# Frozen primary from dig (reports/STANDDOWN_FILTER_C_DIG.md)
PRIMARY_R24_PCT = 5.0  # r24 >= 5%
SOFT_R24_PCT = 3.0
STRICT_R24_PCT = 12.0
STRICT_R24_RSI = (8.0, 70.0)  # r24>=8 and RSI>=70
STRICT_R6_PCT = 8.0


@dataclass
class StanddownConfig:
    r24_primary_pct: float = PRIMARY_R24_PCT
    r24_soft_pct: float = SOFT_R24_PCT
    r6_soft_pct: float = 3.0
    rsi_soft: float = 65.0
    r24_strict_pct: float = STRICT_R24_PCT
    r24_strict_rsi_pair: Tuple[float, float] = STRICT_R24_RSI
    r6_strict_pct: float = STRICT_R6_PCT
    max_abs_ret_sanity_pct: float = 200.0
    pairs: Tuple[str, ...] = ()
    always_include: Tuple[str, ...] = ("BTC-USD", "ETH-USD")
    lookback_hours: int = 48
    sleep_s: float = 0.05
    # Never true in this module — hard fence
    place_orders: bool = False
    mutate_config: bool = False


@dataclass
class PairTape:
    pair: str
    r24_pct: Optional[float]
    r6_pct: Optional[float]
    rsi: Optional[float]
    last_px: Optional[float]
    elev_primary: bool
    elev_soft: bool
    elev_strict: bool
    elev_why: List[str] = field(default_factory=list)
    would_block_process: bool = False  # primary C
    ok: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Pure rules (isolation-tested; no I/O)
# ---------------------------------------------------------------------------


def pct_return(older: float, newer: float) -> Optional[float]:
    try:
        a, b = float(older), float(newer)
    except (TypeError, ValueError):
        return None
    if a <= 0 or b <= 0:
        return None
    return (b / a - 1.0) * 100.0


def tape_from_closes(
    closes_oldest_first: Sequence[float],
    *,
    rsi: Optional[float] = None,
    cfg: Optional[StanddownConfig] = None,
) -> Dict[str, Any]:
    """Compute r6/r24 and elevation flags from hourly closes (oldest→newest)."""
    cfg = cfg or StanddownConfig()
    out: Dict[str, Any] = {
        "r6_pct": None,
        "r24_pct": None,
        "last_px": None,
        "elev_primary": False,
        "elev_soft": False,
        "elev_strict": False,
        "elev_why": [],
        "ok": False,
        "error": None,
    }
    if not closes_oldest_first:
        out["error"] = "no_closes"
        return out
    closes = [float(c) for c in closes_oldest_first if c and float(c) > 0]
    if len(closes) < 7:
        out["error"] = "short_history"
        out["last_px"] = closes[-1] if closes else None
        return out
    last = closes[-1]
    out["last_px"] = last
    r6 = pct_return(closes[-7], last) if len(closes) >= 7 else None
    r24 = pct_return(closes[-25], last) if len(closes) >= 25 else (
        pct_return(closes[0], last) if len(closes) >= 2 else None
    )
    # Sanity — drop absurd DB/API spikes
    if r6 is not None and abs(r6) > cfg.max_abs_ret_sanity_pct:
        r6 = None
    if r24 is not None and abs(r24) > cfg.max_abs_ret_sanity_pct:
        r24 = None
    out["r6_pct"] = r6
    out["r24_pct"] = r24

    why: List[str] = []
    elev_p = r24 is not None and r24 >= cfg.r24_primary_pct
    if elev_p:
        why.append(f"r24={r24:.1f}>={cfg.r24_primary_pct:g}")

    elev_soft = False
    if r24 is not None and r24 >= cfg.r24_soft_pct:
        elev_soft = True
        why.append(f"soft_r24={r24:.1f}")
    if r6 is not None and r6 >= cfg.r6_soft_pct:
        elev_soft = True
        why.append(f"soft_r6={r6:.1f}")
    if rsi is not None and rsi >= cfg.rsi_soft:
        elev_soft = True
        why.append(f"soft_rsi={rsi:.0f}")

    elev_strict = False
    if r24 is not None and r24 >= cfg.r24_strict_pct:
        elev_strict = True
        why.append(f"strict_r24={r24:.1f}")
    thr_r24, thr_rsi = cfg.r24_strict_rsi_pair
    if r24 is not None and rsi is not None and r24 >= thr_r24 and rsi >= thr_rsi:
        elev_strict = True
        why.append(f"strict_r24_rsi={r24:.1f}/{rsi:.0f}")
    if r6 is not None and r6 >= cfg.r6_strict_pct:
        elev_strict = True
        why.append(f"strict_r6={r6:.1f}")

    out["elev_primary"] = bool(elev_p)
    out["elev_soft"] = bool(elev_soft)
    out["elev_strict"] = bool(elev_strict)
    out["elev_why"] = why
    out["ok"] = r24 is not None or r6 is not None
    return out


def would_block_process(elev_primary: bool) -> bool:
    """Primary C: block process entry when elev_r24_5 fires."""
    return bool(elev_primary)


def process_hint(src: str, reason: str) -> bool:
    """Same spirit as dig: machinery entries, not bare reconcile/signal."""
    blob = f"{src} {reason}".lower()
    if "reconcile" in blob and "rebalance" not in blob and "rsi" not in blob:
        if not any(k in blob for k in ("rebalance_buy", "rotation", "allocator", "runner")):
            return False
    keys = (
        "rebalance",
        "rebalance_buy",
        "rsi_primary",
        "arch4",
        "phase6",
        "trade_plan",
        "allocator",
        "runner",
        "rotation",
        "deploy",
    )
    return any(k in blob for k in keys)


# ---------------------------------------------------------------------------
# I/O helpers
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
    if len(closes) < 7:
        return closes, "short_history"
    return closes, None


def load_rsi_map() -> Dict[str, float]:
    if not RSI_CACHE.exists():
        return {}
    try:
        raw = json.loads(RSI_CACHE.read_text())
    except Exception:
        return {}
    out: Dict[str, float] = {}
    if isinstance(raw, dict):
        # shapes: {pair: rsi} or {pair: {rsi: n}} or nested
        for k, v in raw.items():
            if isinstance(v, (int, float)):
                out[str(k)] = float(v)
            elif isinstance(v, dict):
                for kk in ("rsi", "rsi_1h", "value", "RSI"):
                    if kk in v and isinstance(v[kk], (int, float)):
                        out[str(k)] = float(v[kk])
                        break
    return out


def resolve_pairs(cfg: StanddownConfig) -> List[str]:
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
    # held seats from live state if present
    live = STATE_DIR / "phase6_live_state.json"
    if live.exists():
        try:
            st = json.loads(live.read_text())
            holdings = st.get("holdings") or st.get("positions") or {}
            if isinstance(holdings, dict):
                for k in holdings:
                    kk = str(k)
                    if "-USD" not in kk and kk.upper() not in ("USDC", "USD", "CASH"):
                        kk = f"{kk}-USD" if not kk.endswith("-USD") else kk
                    if kk.endswith("-USD") and kk not in pairs:
                        pairs.append(kk)
        except Exception:
            pass
    seen = set()
    out: List[str] = []
    for p in pairs:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _load_recent_process_buys(hours: int = RECENT_BUYS_LOOKBACK_H) -> List[Dict[str, Any]]:
    """Best-effort recent BUY rows that look like process — for would-have-blocked note."""
    path = PROJECT_ROOT / "trades" / "phase6_exchange_fills.jsonl"
    if not path.exists():
        path = PROJECT_ROOT / "trades" / "phase6_trades.jsonl"
    if not path.exists():
        return []
    cut = _utc_now() - timedelta(hours=hours)
    rows: List[Dict[str, Any]] = []
    try:
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                side = str(r.get("side") or r.get("Side") or "").upper()
                if side not in ("BUY", "B"):
                    continue
                ts_raw = r.get("ts") or r.get("time") or r.get("created_at") or r.get("timestamp")
                ts = None
                if isinstance(ts_raw, (int, float)):
                    ts = datetime.fromtimestamp(float(ts_raw) / (1000 if ts_raw > 1e12 else 1), tz=timezone.utc)
                elif isinstance(ts_raw, str):
                    try:
                        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=timezone.utc)
                    except Exception:
                        ts = None
                if ts is None or ts < cut:
                    continue
                pair = r.get("pair") or r.get("product_id") or r.get("symbol") or ""
                src = str(r.get("signal_source") or r.get("source") or "")
                reason = str(r.get("reason") or r.get("trade_reason") or "")
                if not process_hint(src, reason):
                    # still keep if reason empty but product looks process-ish later — skip
                    continue
                rows.append(
                    {
                        "pair": pair,
                        "ts": ts.isoformat(),
                        "src": src,
                        "reason": reason,
                        "notional": r.get("notional") or r.get("size_usd") or r.get("funds"),
                    }
                )
    except Exception:
        return rows
    return rows[-40:]


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(row, default=str) + "\n")


def _write_md(summary: Dict[str, Any]) -> None:
    MD_REPORT.parent.mkdir(parents=True, exist_ok=True)
    blocks = summary.get("would_block") or []
    soft = summary.get("elev_soft_pairs") or []
    lines = [
        "# Stand-down filter C — shadow board",
        "",
        f"**As of:** {summary.get('ts')}  ",
        f"**Mode:** shadow only · **no orders · no config**  ",
        f"**Primary rule:** process entry would-block when `r24 ≥ {summary.get('r24_primary_pct')}%`",
        "",
        "## Plain English",
        "",
        f"- Would-block now (primary): **{len(blocks)}** pairs",
        f"- Soft elevated: **{len(soft)}** pairs",
        f"- Strict heat: **{len(summary.get('elev_strict_pairs') or [])}** pairs",
        f"- Edge class (from dig): `{summary.get('edge_class')}`",
        f"- Live gate: **NO** (shadow log only)",
        "",
        "C is a **less-loss stand-down** candidate, not a money printer.",
        "",
        "## Would-block (primary)",
        "",
    ]
    if not blocks:
        lines.append("_None this run._")
    else:
        for b in blocks:
            lines.append(
                f"- **{b.get('pair')}** r24={b.get('r24_pct')} r6={b.get('r6_pct')} "
                f"rsi={b.get('rsi')} · {', '.join(b.get('elev_why') or [])}"
            )
    lines += ["", "## Caveats", ""]
    for c in summary.get("caveats") or []:
        lines.append(f"- {c}")
    lines += [
        "",
        "## Artifacts",
        "",
        f"- `{LATEST.relative_to(PROJECT_ROOT)}`",
        f"- `{EVENTS.relative_to(PROJECT_ROOT)}`",
        f"- `{MD_REPORT.relative_to(PROJECT_ROOT)}`",
        "",
    ]
    MD_REPORT.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------


def run_standdown_filter_c_shadow(
    cfg: Optional[StanddownConfig] = None,
) -> Dict[str, Any]:
    """Scan basket tape; log would-block. Never orders / never config."""
    cfg = cfg or StanddownConfig()
    assert cfg.place_orders is False
    assert cfg.mutate_config is False

    pairs = resolve_pairs(cfg)
    rsi_map = load_rsi_map()
    sess = _session()
    tapes: List[PairTape] = []

    for pid in pairs:
        closes, err = fetch_hourly_closes(pid, cfg.lookback_hours, sess=sess)
        rsi = rsi_map.get(pid)
        if rsi is None:
            # try bare base
            rsi = rsi_map.get(pid.replace("-USD", ""))
        feat = tape_from_closes(closes, rsi=rsi, cfg=cfg)
        if err and not feat.get("ok"):
            feat["error"] = err
        wb = would_block_process(bool(feat.get("elev_primary")))
        tapes.append(
            PairTape(
                pair=pid,
                r24_pct=feat.get("r24_pct"),
                r6_pct=feat.get("r6_pct"),
                rsi=rsi,
                last_px=feat.get("last_px"),
                elev_primary=bool(feat.get("elev_primary")),
                elev_soft=bool(feat.get("elev_soft")),
                elev_strict=bool(feat.get("elev_strict")),
                elev_why=list(feat.get("elev_why") or []),
                would_block_process=wb,
                ok=bool(feat.get("ok")),
                error=feat.get("error"),
            )
        )
        time.sleep(cfg.sleep_s)

    would_block = [t.to_dict() for t in tapes if t.would_block_process]
    elev_soft = [t.to_dict() for t in tapes if t.elev_soft]
    elev_strict = [t.to_dict() for t in tapes if t.elev_strict]

    recent_buys = _load_recent_process_buys()
    # Annotate recent process buys against *current* tape (approx — not historical CF)
    blocked_recent_note: List[Dict[str, Any]] = []
    by_pair = {t.pair: t for t in tapes}
    for b in recent_buys:
        t = by_pair.get(str(b.get("pair")))
        if t and t.would_block_process:
            blocked_recent_note.append(
                {
                    "pair": b.get("pair"),
                    "buy_ts": b.get("ts"),
                    "note": "pair_currently_primary_elevated_if_process_reentered_would_block",
                    "r24_pct": t.r24_pct,
                }
            )

    event = {
        "ts": _iso(),
        "kind": "standdown_c_shadow_tick",
        "n_pairs": len(tapes),
        "n_would_block": len(would_block),
        "would_block_pairs": [w["pair"] for w in would_block],
        "elev_strict_pairs": [w["pair"] for w in elev_strict],
        "place_orders": False,
        "mutate_config": False,
    }
    _append_jsonl(EVENTS, event)
    for w in would_block:
        _append_jsonl(
            EVENTS,
            {
                "ts": _iso(),
                "kind": "would_block_process",
                "pair": w["pair"],
                "r24_pct": w.get("r24_pct"),
                "r6_pct": w.get("r6_pct"),
                "rsi": w.get("rsi"),
                "elev_why": w.get("elev_why"),
                "rule": f"r24>={cfg.r24_primary_pct}",
                "live_gate": False,
            },
        )

    summary: Dict[str, Any] = {
        "ts": _iso(),
        "mode": "shadow_only",
        "live_gate": False,
        "edge_class": "ATTENTION_ONLY_less_loss_path",
        "r24_primary_pct": cfg.r24_primary_pct,
        "n_pairs": len(tapes),
        "would_block": would_block,
        "elev_soft_pairs": elev_soft,
        "elev_strict_pairs": elev_strict,
        "pairs": [t.to_dict() for t in tapes],
        "recent_process_buys_scanned": len(recent_buys),
        "recent_buys_on_currently_elevated": blocked_recent_note,
        "dig_ref": "reports/STANDDOWN_FILTER_C_DIG.md",
        "caveats": [
            "Shadow only — does not block live fills",
            "Primary rule frozen at r24>=5 from 90d dig; N elevated exits was small",
            "Calm process was also red on dig sample — C is less-loss on heat, not a printer",
            "No capital-reuse path CF; fees still dominate churn",
            "No evaluate_buy_entry / runner / knobs wiring without Brad GO",
        ],
        "place_orders": False,
        "mutate_config": False,
    }

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps(summary, indent=2, default=str) + "\n")
    _write_md(summary)
    return summary


def telegram_summary(summary: Dict[str, Any]) -> str:
    """Quiet by default; only speak when would-block non-empty."""
    blocks = summary.get("would_block") or []
    if not blocks:
        return ""
    names = ", ".join(b.get("pair", "?") for b in blocks[:8])
    return (
        f"C shadow would-block ({len(blocks)}): {names}\n"
        f"rule r24≥{summary.get('r24_primary_pct')}% · live gate OFF · less-loss only"
    )
