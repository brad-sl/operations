#!/usr/bin/env python3
"""
Discovery retro board — lookback instrumentation (shadow / research only).

Question
--------
For names that are exploding *now*, did any of our funnels name them
early enough to matter — and when we *did* name names a week ago, did
those cohorts actually outperform?

This is the honest half of the "holy grail" early-detect wish. It does
**not** place orders, mutate config, or write runtime trading SSOT.

Surfaces (write targets — research only)
----------------------------------------
- data/state/discovery_retro_board_latest.json
- data/state/discovery_retro_board_runs.jsonl  (append)
- reports/DISCOVERY_RETRO_BOARD_LATEST.md

Inputs (read-only)
------------------
- data/state/pair_discovery_runs.jsonl
- data/state/discovery_pipeline_runs.jsonl
- data/state/basket_swap_shadow_counterfactual_latest.json (optional)
- Coinbase public product stats + candles

See docs/DATA_FLOW_AND_LOCATIONS.md. Reporters never write production settings.
"""
from __future__ import annotations

import json
import math
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import requests

from phase6.core.paths import PROJECT_ROOT, STATE_DIR

PUBLIC = "https://api.exchange.coinbase.com"
UA = {"User-Agent": "phase6-discovery-retro-board/1.0 (shadow; research; no-trade)"}

DISCOVERY_RUNS = STATE_DIR / "pair_discovery_runs.jsonl"
PIPELINE_RUNS = STATE_DIR / "discovery_pipeline_runs.jsonl"
CF_LATEST = STATE_DIR / "basket_swap_shadow_counterfactual_latest.json"
DISCOVERY_LATEST = STATE_DIR / "pair_discovery_latest.json"
CONTENDERS_LATEST = STATE_DIR / "pair_discovery_contenders.json"

OUT_JSON = STATE_DIR / "discovery_retro_board_latest.json"
OUT_JSONL = STATE_DIR / "discovery_retro_board_runs.jsonl"
OUT_MD = PROJECT_ROOT / "reports" / "DISCOVERY_RETRO_BOARD_LATEST.md"

# Lead-time classes (hours before as_of / latest discovery run)
CLASS_NEVER = "NEVER"
CLASS_COINCIDENT = "COINCIDENT"  # < 24h
CLASS_SHORT = "SHORT"  # 1–3d
CLASS_MEDIUM = "MEDIUM"  # 3–7d
CLASS_EARLY = "EARLY"  # ≥ 7d

# Default discovery gates (mirror pair_discovery.DiscoveryConfig)
DEFAULT_MIN_QUOTE_VOL = 2_000_000.0
DEFAULT_PREQUAL_TOP_N = 40
DEFAULT_MIN_QUALITY = 0.35
DEFAULT_PUMP_BRAKE = 0.80
DEFAULT_CONTENDER_TOP_N = 8  # pipeline often fetches extra then brakes


@dataclass
class RetroConfig:
    top_gainers_n: int = 15
    min_gainer_volume_usd: float = 100_000.0
    min_gainer_ret_pct: float = 8.0
    anchor_hours: Tuple[int, ...] = (24 * 7, 24 * 3, 24, 0)  # T-7, T-3, T-1, T0
    anchor_window_hours: float = 18.0
    forward_book_lookback_days: float = 7.0
    candle_granularity: int = 3600
    request_pause_s: float = 0.12
    timeout_s: float = 12.0
    max_workers_stats: int = 8
    # Discovery gate mirrors (for why-not autopsy)
    min_quote_volume_24h_usd: float = DEFAULT_MIN_QUOTE_VOL
    prequal_top_n: int = DEFAULT_PREQUAL_TOP_N
    min_quality_score: float = DEFAULT_MIN_QUALITY
    pump_brake_ret_24h: float = DEFAULT_PUMP_BRAKE
    # Research-only writes
    write: bool = True
    fetch_prices: bool = True
    run_why_not_autopsy: bool = True
    run_quiet_features: bool = True


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(s: Any) -> Optional[datetime]:
    if s is None:
        return None
    if isinstance(s, datetime):
        return s if s.tzinfo else s.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(UA)
    return s


def _get_json(sess: requests.Session, url: str, timeout: float) -> Any:
    r = sess.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()


def load_discovery_runs(path: Path = DISCOVERY_RUNS) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = _parse_ts(o.get("ts") or o.get("timestamp") or o.get("as_of"))
        if not ts:
            continue
        cont = o.get("contenders") or []
        if cont and isinstance(cont[0], dict):
            cont = [
                c.get("product_id") or c.get("pair") or c.get("symbol")
                for c in cont
                if isinstance(c, dict)
            ]
        cont = [str(x) for x in cont if x]
        # v2 stage ledger (optional — older runs lack these)
        prequal_top = o.get("prequal_top") or []
        quality_pass = o.get("quality_pass") or []
        quality_fail = o.get("quality_fail") or []
        contenders_detail = o.get("contenders_detail") or []
        out.append(
            {
                "ts": ts,
                "schema": o.get("schema") or "pair_discovery_run_v1",
                "contenders": cont,
                "universe_n": o.get("universe_n"),
                "prequal_n": o.get("prequal_n"),
                "quality_n": o.get("quality_n"),
                "prequal_top": prequal_top if isinstance(prequal_top, list) else [],
                "quality_pass": quality_pass if isinstance(quality_pass, list) else [],
                "quality_fail": quality_fail if isinstance(quality_fail, list) else [],
                "contenders_detail": contenders_detail
                if isinstance(contenders_detail, list)
                else [],
                "active_basket": list(o.get("active_basket") or []),
                "cfg_min_quote_volume_24h_usd": o.get("cfg_min_quote_volume_24h_usd"),
                "cfg_prequal_top_n": o.get("cfg_prequal_top_n"),
                "cfg_min_quality_score": o.get("cfg_min_quality_score"),
            }
        )
    out.sort(key=lambda r: r["ts"])
    return out


def stage_history_for_pair(
    disc_runs: Sequence[Dict[str, Any]], pair: str, last_n: int = 12
) -> Dict[str, Any]:
    """Scan recent discovery runs for stage hits (v2 fields preferred)."""
    hits: List[Dict[str, Any]] = []
    for r in disc_runs[-last_n:]:
        entry: Dict[str, Any] = {"ts": r["ts"].isoformat()}
        found = False
        for row in r.get("contenders_detail") or []:
            if isinstance(row, dict) and row.get("product_id") == pair:
                entry["stage"] = "contender"
                entry["row"] = row
                found = True
                break
        if not found and pair in (r.get("contenders") or []):
            entry["stage"] = "contender"
            found = True
        if not found:
            for row in r.get("quality_pass") or []:
                if isinstance(row, dict) and row.get("product_id") == pair:
                    entry["stage"] = "quality_pass"
                    entry["row"] = row
                    found = True
                    break
        if not found:
            for row in r.get("quality_fail") or []:
                if isinstance(row, dict) and row.get("product_id") == pair:
                    entry["stage"] = "quality_fail"
                    entry["row"] = row
                    found = True
                    break
        if not found:
            for row in r.get("prequal_top") or []:
                if isinstance(row, dict) and row.get("product_id") == pair:
                    entry["stage"] = "prequal"
                    entry["row"] = row
                    found = True
                    break
        if found:
            hits.append(entry)
    stages = [h.get("stage") for h in hits]
    return {
        "n_stage_hits": len(hits),
        "stages_seen": sorted(set(s for s in stages if s)),
        "hits": hits[-6:],
        "best_stage": (
            "contender"
            if "contender" in stages
            else (
                "quality_pass"
                if "quality_pass" in stages
                else (
                    "quality_fail"
                    if "quality_fail" in stages
                    else ("prequal" if "prequal" in stages else None)
                )
            )
        ),
    }


def load_pipeline_runs(path: Path = PIPELINE_RUNS) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = _parse_ts(o.get("ts") or o.get("timestamp"))
        if not ts:
            continue
        out.append(
            {
                "ts": ts,
                "eligible": [str(x) for x in (o.get("eligible") or []) if x],
                "swaps": [str(x) for x in (o.get("swaps") or []) if x],
            }
        )
    out.sort(key=lambda r: r["ts"])
    return out


def load_cf_add_arms(path: Path = CF_LATEST) -> Dict[str, Dict[str, Any]]:
    """pair -> {arms: set-as-list, n} from shadow CF ledger (read-only)."""
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    bag: Dict[str, Dict[str, Any]] = {}
    for r in raw.get("results") or []:
        if not isinstance(r, dict):
            continue
        add = r.get("add")
        arm = r.get("arm")
        if not add:
            continue
        slot = bag.setdefault(str(add), {"arms": set(), "n": 0})
        if arm:
            slot["arms"].add(str(arm))
        slot["n"] += 1
    return {
        k: {"arms": sorted(v["arms"]), "n": v["n"]} for k, v in bag.items()
    }


def load_discovery_latest(path: Path = DISCOVERY_LATEST) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _index_latest_discovery(latest: Dict[str, Any]) -> Dict[str, Any]:
    """Maps product_id -> stage rows from pair_discovery_latest.json."""
    prequal = {
        r["product_id"]: r
        for r in (latest.get("prequal_top") or [])
        if isinstance(r, dict) and r.get("product_id")
    }
    quality = {
        r["product_id"]: r
        for r in (latest.get("quality_ranked") or [])
        if isinstance(r, dict) and r.get("product_id")
    }
    contenders = {
        r["product_id"]: r
        for r in (latest.get("contenders") or [])
        if isinstance(r, dict) and r.get("product_id")
    }
    active = set(latest.get("active_basket") or [])
    return {
        "prequal": prequal,
        "quality": quality,
        "contenders": contenders,
        "active": active,
        "ts": latest.get("timestamp"),
        "prequal_n_listed": len(prequal),
        "cfg": latest.get("config") or {},
    }


def _fetch_candles_list(
    sess: requests.Session, pair: str, gran: int, timeout: float
) -> List[list]:
    try:
        data = _get_json(
            sess,
            f"{PUBLIC}/products/{pair}/candles?granularity={gran}",
            timeout,
        )
        if not isinstance(data, list):
            return []
        # API newest-first → oldest-first
        rows = list(reversed(data))
        return rows
    except Exception:
        return []


def compute_quiet_features(
    candles: Sequence[list],
    btc_candles: Optional[Sequence[list]] = None,
) -> Dict[str, Any]:
    """
    Earlier/quieter probes — research features, not live gates.

    candles: oldest-first [time, low, high, open, close, volume]
    """
    out: Dict[str, Any] = {
        "ok": False,
        "n_candles": len(candles) if candles else 0,
    }
    if not candles or len(candles) < 72:
        out["reason"] = "insufficient_candles"
        return out

    closes = [float(c[4]) for c in candles if len(c) >= 5]
    highs = [float(c[2]) for c in candles if len(c) >= 3]
    lows = [float(c[1]) for c in candles if len(c) >= 2]
    vols = [float(c[5]) for c in candles if len(c) >= 6]
    n = len(closes)
    if n < 72:
        out["reason"] = "insufficient_closes"
        return out

    last = closes[-1]

    def ret_h(hours: int) -> float:
        idx = max(0, n - 1 - hours)
        base = closes[idx]
        return (last / base - 1.0) if base > 0 else 0.0

    mom_3d = ret_h(72)
    mom_5d = ret_h(min(120, n - 1))
    mom_7d = ret_h(min(167, n - 1))

    def band(start: int, end: int) -> float:
        if end <= start:
            return 0.0
        h = max(highs[start:end])
        lo = min(lows[start:end])
        mid = (h + lo) / 2 if h and lo else 0.0
        return ((h - lo) / mid) if mid > 0 else 0.0

    # Compression window: hours -96..-24 (quiet body) vs last 24h expand
    quiet_band = band(max(0, n - 96), max(0, n - 24)) or 1e-9
    recent_band = band(max(0, n - 24), n)
    compression_then_expand = recent_band / quiet_band if quiet_band else None

    v_last24 = sum(vols[max(0, n - 24) :]) or 0.0
    v_prior72 = sum(vols[max(0, n - 96) : max(0, n - 24)]) or 1e-9
    # dry-up: was prior quieter than a longer baseline?
    v_baseline = sum(vols[max(0, n - 168) : max(0, n - 96)]) / max(
        1, min(72, max(0, n - 96) - max(0, n - 168))
    ) if n > 96 else (v_prior72 / 72.0)
    v_quiet_avg = v_prior72 / max(1, min(72, (n - 24) - max(0, n - 96)))
    vol_dry_ratio = (v_quiet_avg / v_baseline) if v_baseline else None  # <1 = dried
    liq_jump = (v_last24 / (v_quiet_avg * 24 / max(1, min(72, n)))) if v_quiet_avg else None
    # simpler liq jump: last 24h vol / avg prior day vol over 3d
    prior_day_vols = []
    for d in range(1, 4):
        sl = sum(vols[max(0, n - 24 * (d + 1)) : max(0, n - 24 * d)])
        prior_day_vols.append(sl)
    avg_prior_day = (sum(prior_day_vols) / len(prior_day_vols)) if prior_day_vols else 1e-9
    liq_jump_24_vs_3d = v_last24 / avg_prior_day if avg_prior_day else None

    btc_rel_3d = None
    if btc_candles and len(btc_candles) >= 72:
        bc = [float(c[4]) for c in btc_candles if len(c) >= 5]
        if len(bc) >= 72:
            b_last = bc[-1]
            b_base = bc[max(0, len(bc) - 1 - 72)]
            btc_mom = (b_last / b_base - 1.0) if b_base > 0 else 0.0
            btc_rel_3d = mom_3d - btc_mom

    # Quiet-early score sketch (0..1-ish): dry tape + mild positive RS + not already vertical
    score_parts = []
    if vol_dry_ratio is not None:
        # reward mild dry-up (0.4–0.9), not collapse
        score_parts.append(max(0.0, min(1.0, (0.95 - abs(vol_dry_ratio - 0.7)) / 0.5)))
    if liq_jump_24_vs_3d is not None:
        # early jump 1.3–2.5x; huge jump = already exploding
        j = liq_jump_24_vs_3d
        if 1.2 <= j <= 2.8:
            score_parts.append(0.8)
        elif 2.8 < j <= 4.0:
            score_parts.append(0.4)
        elif j > 4.0:
            score_parts.append(0.15)  # late
        else:
            score_parts.append(0.2)
    if btc_rel_3d is not None:
        # modest outperformance before melt-up
        if 0.02 <= btc_rel_3d <= 0.15:
            score_parts.append(0.85)
        elif btc_rel_3d > 0.15:
            score_parts.append(0.35)  # already ran
        elif btc_rel_3d > 0:
            score_parts.append(0.5)
        else:
            score_parts.append(0.15)
    if compression_then_expand is not None:
        if 1.2 <= compression_then_expand <= 3.0:
            score_parts.append(0.75)
        elif compression_then_expand > 3.0:
            score_parts.append(0.3)
        else:
            score_parts.append(0.25)

    quiet_score = round(sum(score_parts) / len(score_parts), 4) if score_parts else None

    out.update(
        {
            "ok": True,
            "mom_3d": round(mom_3d, 6),
            "mom_5d": round(mom_5d, 6),
            "mom_7d": round(mom_7d, 6),
            "compression_then_expand": round(compression_then_expand, 4)
            if compression_then_expand is not None
            else None,
            "vol_dry_ratio": round(vol_dry_ratio, 4) if vol_dry_ratio is not None else None,
            "liq_jump_24_vs_3d": round(liq_jump_24_vs_3d, 4)
            if liq_jump_24_vs_3d is not None
            else None,
            "btc_rel_3d": round(btc_rel_3d, 6) if btc_rel_3d is not None else None,
            "quiet_early_score": quiet_score,
            "note": (
                "quiet_early_score is a research sketch only — not a gate. "
                "High after a +50% day often means 'already loud', not 'early'."
            ),
        }
    )
    return out


def autopsy_why_not(
    pair: str,
    *,
    gainer_meta: Dict[str, Any],
    lead_class: str,
    n_contender_runs: int,
    methods: Sequence[str],
    idx: Dict[str, Any],
    cfg: RetroConfig,
    sess: Optional[requests.Session] = None,
    btc_candles: Optional[Sequence[list]] = None,
    stage_hist: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Explain pick / miss against discovery stages.

    Primary codes (stable for boards):
      picked | active_basket | pump_brake | thin_liquidity | below_prequal_cutoff |
      quality_fail | contender_cutoff | promote_blocked | never_evaluated |
      coincident_late | unknown
    """
    reasons: List[str] = []
    primary = "unknown"
    detail: Dict[str, Any] = {}
    stage_seen = "none"
    stage_hist = stage_hist or {}

    pq = (idx.get("prequal") or {}).get(pair)
    qrow = (idx.get("quality") or {}).get(pair)
    crow = (idx.get("contenders") or {}).get(pair)
    active = idx.get("active") or set()
    cfg_disc = idx.get("cfg") or {}
    min_vol = float(
        cfg_disc.get("min_quote_volume_24h_usd") or cfg.min_quote_volume_24h_usd
    )
    prequal_top_n = int(cfg_disc.get("prequal_top_n") or cfg.prequal_top_n)
    min_q = float(cfg_disc.get("min_quality_score") or cfg.min_quality_score)

    ret24 = gainer_meta.get("ret_24h_pct")
    if ret24 is not None:
        ret24 = float(ret24) / 100.0
    vol = gainer_meta.get("volume_quote_usd")

    # Prefer historical v2 stage hits when latest snapshot lacks the name
    best_hist = stage_hist.get("best_stage")
    hist_fail_row = None
    for h in reversed(stage_hist.get("hits") or []):
        if h.get("stage") == "quality_fail" and isinstance(h.get("row"), dict):
            hist_fail_row = h["row"]
            break

    # --- picked path ---
    if n_contender_runs > 0 or crow or "pair_discovery_contenders" in methods:
        stage_seen = "contender"
        if crow and crow.get("promote_eligible") is False:
            rs = crow.get("reasons") or []
            if any("pump_brake" in str(x) for x in rs) or (
                ret24 is not None and abs(ret24) > cfg.pump_brake_ret_24h
            ):
                primary = "pump_brake"
                reasons.append(
                    "on contender list but promote blocked by pump brake / extended ret"
                )
            elif any("no_upside" in str(x) for x in rs):
                primary = "promote_blocked"
                reasons.append("contender but blocked_no_upside_impulse")
            else:
                primary = "picked"
                reasons.append(
                    "on contender list (promote_eligible false — see reasons)"
                )
            detail["contender"] = {
                k: crow.get(k)
                for k in (
                    "quality_score",
                    "prequal_energy",
                    "promote_eligible",
                    "ret_24h",
                    "mom_3d",
                    "reasons",
                )
            }
        else:
            primary = "picked"
            reasons.append(
                f"named as contender ({n_contender_runs} run(s)); lead_class={lead_class}"
            )
            if lead_class == CLASS_COINCIDENT:
                reasons.append(
                    "timing=COINCIDENT — funnel lit up during/after the rip, not week-early"
                )
                primary = "coincident_late"
    elif pair in active:
        primary = "active_basket"
        stage_seen = "active"
        reasons.append("already in active basket — excluded from emerging contenders")
    else:
        # miss path — walk stages using latest snapshot + live gates + hist
        if hist_fail_row and not qrow:
            qrow = hist_fail_row
            detail["quality_from"] = "stage_history"
        if best_hist == "prequal" and not pq:
            # reconstruct slim pq from last hist hit
            for h in reversed(stage_hist.get("hits") or []):
                if h.get("stage") == "prequal" and isinstance(h.get("row"), dict):
                    pq = h["row"]
                    detail["prequal_from"] = "stage_history"
                    break

        if vol is not None and float(vol) < min_vol:
            primary = "thin_liquidity"
            stage_seen = "prequal_volume"
            reasons.append(
                f"24h quote vol ${float(vol):,.0f} < discovery floor ${min_vol:,.0f}"
            )
        elif pq or qrow or best_hist in ("prequal", "quality_pass", "quality_fail"):
            if pq:
                stage_seen = "prequal"
                detail["prequal"] = {
                    k: pq.get(k)
                    for k in ("energy", "rank_energy", "ret_24h", "volume_quote_usd")
                }
            if qrow or best_hist in ("quality_pass", "quality_fail"):
                stage_seen = "quality"
                src = qrow or {}
                detail["quality"] = {
                    k: src.get(k)
                    for k in (
                        "quality_score",
                        "pass_gate",
                        "reason",
                        "mom_3d",
                        "mom_7d",
                        "vol_expand",
                        "vol_accel",
                        "prequal_energy",
                    )
                }
                failed = (
                    (qrow is not None and not qrow.get("pass_gate", True))
                    or best_hist == "quality_fail"
                    or (src.get("reason") and src.get("pass_gate") is False)
                )
                if failed:
                    primary = "quality_fail"
                    reasons.append(
                        f"made prequal/energy screen but quality fail: "
                        f"{src.get('reason') or 'below_min_quality'} "
                        f"(q={src.get('quality_score')})"
                    )
                elif best_hist == "quality_pass" or (
                    qrow and qrow.get("pass_gate")
                ):
                    primary = "contender_cutoff"
                    reasons.append(
                        f"quality pass (q={src.get('quality_score')}) but not in "
                        f"contender top-N / emerging list this snapshot"
                    )
                else:
                    primary = "quality_not_in_latest_top"
                    rank = (pq or {}).get("rank_energy")
                    reasons.append(
                        f"in prequal snapshot (rank={rank}, e={(pq or {}).get('energy')}) "
                        f"but not in quality_ranked top listing — mid-pack or fail not stored"
                    )
            else:
                rank = (pq or {}).get("rank_energy")
                if rank and int(rank) > prequal_top_n:
                    primary = "below_prequal_cutoff"
                    reasons.append(f"prequal rank {rank} > top_n {prequal_top_n}")
                else:
                    primary = "quality_not_in_latest_top"
                    reasons.append(
                        f"in prequal snapshot (rank={rank}, e={(pq or {}).get('energy')}) "
                        f"but quality path incomplete in stored snapshot"
                    )
        else:
            stage_seen = "universe_or_below_prequal"
            if vol is not None and float(vol) >= min_vol:
                primary = "below_prequal_cutoff"
                reasons.append(
                    f"vol ok (${float(vol):,.0f}≥${min_vol:,.0f}) but absent from "
                    f"latest prequal_top listing (energy rank not in stored top "
                    f"{idx.get('prequal_n_listed') or 15}) — lost the wide energy screen "
                    f"or not loud enough vs peers that day"
                )
            elif vol is None:
                primary = "never_evaluated"
                reasons.append("no volume meta; cannot classify")
            else:
                primary = "thin_liquidity"
                reasons.append(f"vol ${float(vol):,.0f} under floor")

        if ret24 is not None and abs(ret24) > cfg.pump_brake_ret_24h and primary not in (
            "picked",
            "coincident_late",
            "pump_brake",
        ):
            reasons.append(
                f"note: |ret24h|={abs(ret24):.0%} would hit pump_brake even if contender"
            )

    if stage_hist.get("n_stage_hits"):
        detail["stage_history"] = {
            "n_stage_hits": stage_hist.get("n_stage_hits"),
            "stages_seen": stage_hist.get("stages_seen"),
            "best_stage": stage_hist.get("best_stage"),
            "hits": stage_hist.get("hits"),
        }

    # Quiet / early features (live candle probe — post-move biased; still useful for autopsy)
    quiet: Dict[str, Any] = {}
    if cfg.run_quiet_features and sess is not None and cfg.fetch_prices:
        candles = _fetch_candles_list(
            sess, pair, cfg.candle_granularity, cfg.timeout_s
        )
        time.sleep(cfg.request_pause_s)
        quiet = compute_quiet_features(candles, btc_candles=btc_candles)
        detail["quiet_features"] = quiet
        if quiet.get("ok") and quiet.get("quiet_early_score") is not None:
            qs = quiet["quiet_score"] if "quiet_score" in quiet else quiet["quiet_early_score"]
            reasons.append(
                f"quiet_early_score_now={qs} "
                f"(btc_rel_3d={quiet.get('btc_rel_3d')}, "
                f"liq_jump={quiet.get('liq_jump_24_vs_3d')}, "
                f"vol_dry={quiet.get('vol_dry_ratio')}, "
                f"compress→expand={quiet.get('compression_then_expand')}) — "
                f"post-move; research tail only"
            )

    # One-line board column
    why_line = f"{primary}"
    if reasons:
        why_line = f"{primary}: {reasons[0]}"
        if len(reasons) > 1 and not reasons[1].startswith("quiet_"):
            why_line += f" · {reasons[1]}"

    return {
        "primary": primary,
        "stage_seen": stage_seen,
        "why_not": why_line,
        "reasons": reasons,
        "detail": detail,
        "discovery_latest_ts": idx.get("ts"),
        "quiet_early_score": (quiet or {}).get("quiet_early_score"),
        "btc_rel_3d": (quiet or {}).get("btc_rel_3d"),
        "liq_jump_24_vs_3d": (quiet or {}).get("liq_jump_24_vs_3d"),
        "vol_dry_ratio": (quiet or {}).get("vol_dry_ratio"),
        "compression_then_expand": (quiet or {}).get("compression_then_expand"),
        "gates": {
            "min_quote_volume_24h_usd": min_vol,
            "prequal_top_n": prequal_top_n,
            "min_quality_score": min_q,
            "pump_brake_ret_24h": cfg.pump_brake_ret_24h,
        },
    }


def fetch_top_gainers(
    sess: requests.Session,
    cfg: RetroConfig,
) -> List[Dict[str, Any]]:
    """Coinbase public stats → top 24h % gainers above volume floor."""
    products = _get_json(sess, f"{PUBLIC}/products", cfg.timeout_s)
    usd = [
        p["id"]
        for p in products
        if isinstance(p, dict)
        and p.get("quote_currency") == "USD"
        and p.get("status") == "online"
        and not p.get("trading_disabled")
        and "-" in str(p.get("id") or "")
    ]
    # Skip pure stables
    skip_base = {
        "USDT",
        "USDC",
        "DAI",
        "EURC",
        "PYUSD",
        "GUSD",
        "TUSD",
        "FDUSD",
        "USDP",
        "PAX",
    }
    usd = [p for p in usd if p.split("-")[0] not in skip_base]

    rows: List[Dict[str, Any]] = []

    def one(pid: str) -> Optional[Dict[str, Any]]:
        try:
            # per-call session-ish via shared sess (requests.Session is not fully
            # thread-safe for all adapters; use bare get on failure path)
            r = sess.get(f"{PUBLIC}/products/{pid}/stats", timeout=cfg.timeout_s)
            if r.status_code == 429:
                time.sleep(1.5)
                r = sess.get(f"{PUBLIC}/products/{pid}/stats", timeout=cfg.timeout_s)
            r.raise_for_status()
            st = r.json()
            last = float(st.get("last") or 0)
            open_ = float(st.get("open") or 0)
            vol = float(st.get("volume") or 0)
            if last <= 0 or open_ <= 0:
                return None
            quote_vol = vol * last
            ret = (last / open_ - 1.0) * 100.0
            if quote_vol < cfg.min_gainer_volume_usd:
                return None
            if ret < cfg.min_gainer_ret_pct:
                return None
            return {
                "product_id": pid,
                "last": last,
                "open_24h": open_,
                "ret_24h_pct": round(ret, 4),
                "volume_quote_usd": round(quote_vol, 2),
            }
        except Exception:
            return None

    from concurrent.futures import ThreadPoolExecutor, as_completed

    workers = max(1, min(cfg.max_workers_stats, 12))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(one, pid): pid for pid in usd}
        for fut in as_completed(futs):
            row = fut.result()
            if row:
                rows.append(row)

    rows.sort(key=lambda r: r["ret_24h_pct"], reverse=True)
    return rows[: cfg.top_gainers_n]


def _nearest_run(
    runs: Sequence[Dict[str, Any]],
    target: datetime,
    window_hours: float,
) -> Optional[Dict[str, Any]]:
    best: Optional[Tuple[float, Dict[str, Any]]] = None
    for r in runs:
        dt = abs((r["ts"] - target).total_seconds())
        if dt <= window_hours * 3600:
            if best is None or dt < best[0]:
                best = (dt, r)
    if best:
        return best[1]
    prior = [r for r in runs if r["ts"] <= target]
    return prior[-1] if prior else None


def _pair_in_swap_label(pair: str, label: str) -> bool:
    """Exact product_id match inside 'AAA-USD→BBB-USD' (no substring traps like O-USD∈AERO-USD)."""
    if not label or not pair:
        return False
    parts = (
        label.replace("→", " ")
        .replace("->", " ")
        .replace(",", " ")
        .replace("|", " ")
        .split()
    )
    return pair in parts


def first_contender_hit(
    runs: Sequence[Dict[str, Any]], pair: str
) -> Optional[Dict[str, Any]]:
    for r in runs:
        if pair in r["contenders"]:
            return {
                "ts": r["ts"],
                "rank": r["contenders"].index(pair),
                "contenders": list(r["contenders"]),
            }
    return None


def all_contender_hits(
    runs: Sequence[Dict[str, Any]], pair: str
) -> List[Dict[str, Any]]:
    out = []
    for r in runs:
        if pair in r["contenders"]:
            out.append(
                {
                    "ts": r["ts"].isoformat(),
                    "rank": r["contenders"].index(pair),
                }
            )
    return out


def lead_class(lead_hours: Optional[float]) -> str:
    if lead_hours is None:
        return CLASS_NEVER
    if lead_hours < 24:
        return CLASS_COINCIDENT
    if lead_hours < 72:
        return CLASS_SHORT
    if lead_hours < 168:
        return CLASS_MEDIUM
    return CLASS_EARLY


def candle_close_near(
    sess: requests.Session,
    pair: str,
    when: datetime,
    cfg: RetroConfig,
) -> Optional[float]:
    try:
        candles = _get_json(
            sess,
            f"{PUBLIC}/products/{pair}/candles?granularity={cfg.candle_granularity}",
            cfg.timeout_s,
        )
        if not isinstance(candles, list) or not candles:
            return None
        target = int(when.timestamp())
        best = min(candles, key=lambda c: abs(int(c[0]) - target))
        return float(best[4])
    except Exception:
        return None


def forward_return_pct(
    sess: requests.Session,
    pair: str,
    start: datetime,
    end: datetime,
    cfg: RetroConfig,
) -> Optional[float]:
    a = candle_close_near(sess, pair, start, cfg)
    time.sleep(cfg.request_pause_s)
    b = candle_close_near(sess, pair, end, cfg)
    if a is None or b is None or a <= 0:
        return None
    return (b / a - 1.0) * 100.0


def daily_return_approx(
    sess: requests.Session, pair: str, days: int, cfg: RetroConfig
) -> Optional[float]:
    try:
        candles = _get_json(
            sess,
            f"{PUBLIC}/products/{pair}/candles?granularity=86400",
            cfg.timeout_s,
        )
        if not isinstance(candles, list) or len(candles) < days + 1:
            return None
        c0 = float(candles[0][4])
        cN = float(candles[min(days, len(candles) - 1)][4])
        if cN <= 0:
            return None
        return (c0 / cN - 1.0) * 100.0
    except Exception:
        return None


def classify_gainer(
    pair: str,
    gainer_meta: Dict[str, Any],
    disc_runs: Sequence[Dict[str, Any]],
    pipe_runs: Sequence[Dict[str, Any]],
    cf_arms: Dict[str, Dict[str, Any]],
    as_of: datetime,
    cfg: RetroConfig,
    sess: Optional[requests.Session] = None,
    *,
    discovery_idx: Optional[Dict[str, Any]] = None,
    btc_candles: Optional[Sequence[list]] = None,
) -> Dict[str, Any]:
    first = first_contender_hit(disc_runs, pair)
    hits = all_contender_hits(disc_runs, pair)
    lead_h: Optional[float] = None
    if first:
        lead_h = (as_of - first["ts"]).total_seconds() / 3600.0

    anchors: Dict[str, Any] = {}
    for hours in cfg.anchor_hours:
        label = f"T-{hours // 24}d" if hours >= 24 else "T0"
        if hours == 0:
            label = "T0"
        target = as_of - timedelta(hours=hours)
        run = _nearest_run(disc_runs, target, cfg.anchor_window_hours)
        present = bool(run and pair in run["contenders"])
        anchors[label] = {
            "present": present,
            "run_ts": run["ts"].isoformat() if run else None,
            "rank": (run["contenders"].index(pair) if run and pair in run["contenders"] else None),
        }

    # Pipeline
    first_elig = None
    pipe_swaps: List[str] = []
    for r in pipe_runs:
        if pair in r["eligible"] and first_elig is None:
            first_elig = r["ts"]
        for s in r["swaps"]:
            if _pair_in_swap_label(pair, s):
                pipe_swaps.append(f"{r['ts'].date()}:{s}")

    methods: List[str] = []
    if first:
        methods.append("pair_discovery_contenders")
    if first_elig:
        methods.append("discovery_pipeline_eligible")
    if pipe_swaps:
        methods.append("discovery_pipeline_swap_proposal")
    cf = cf_arms.get(pair)
    if cf:
        methods.append("basket_swap_cf:" + ",".join(cf["arms"]))

    # Chronic = named in ≥30% of discovery runs (watchlist regular, not fresh early-detect)
    n_runs = max(1, len(disc_runs))
    frac = len(hits) / n_runs
    if len(hits) == 0:
        watch_style = "absent"
    elif frac >= 0.30 or len(hits) >= 8:
        watch_style = "chronic"
    elif len(hits) >= 3:
        watch_style = "episodic"
    else:
        watch_style = "fresh"

    # EARLY + chronic is "always on the list", not week-ago explode radar
    lc = lead_class(lead_h)
    early_quality = None
    if lc == CLASS_EARLY:
        early_quality = (
            "chronic_watchlist"
            if watch_style == "chronic"
            else "true_early_flag"
        )

    post_flag_ret = None
    if first and sess is not None and cfg.fetch_prices:
        post_flag_ret = forward_return_pct(sess, pair, first["ts"], as_of, cfg)
        time.sleep(cfg.request_pause_s)

    stage_hist = stage_history_for_pair(disc_runs, pair)
    autopsy: Dict[str, Any] = {}
    if cfg.run_why_not_autopsy:
        autopsy = autopsy_why_not(
            pair,
            gainer_meta=gainer_meta,
            lead_class=lc,
            n_contender_runs=len(hits),
            methods=methods,
            idx=discovery_idx or {},
            cfg=cfg,
            sess=sess if cfg.fetch_prices else None,
            btc_candles=btc_candles,
            stage_hist=stage_hist,
        )

    return {
        "product_id": pair,
        "ret_24h_pct": gainer_meta.get("ret_24h_pct"),
        "volume_quote_usd": gainer_meta.get("volume_quote_usd"),
        "last": gainer_meta.get("last"),
        "lead_class": lc,
        "early_quality": early_quality,
        "watch_style": watch_style,
        "contender_run_frac": round(frac, 3),
        "lead_hours": round(lead_h, 2) if lead_h is not None else None,
        "first_contender_ts": first["ts"].isoformat() if first else None,
        "first_contender_rank": first["rank"] if first else None,
        "n_contender_runs": len(hits),
        "appearances": hits,
        "anchors": anchors,
        "first_pipeline_eligible_ts": first_elig.isoformat() if first_elig else None,
        "pipeline_swaps": pipe_swaps,
        "cf_arms": (cf or {}).get("arms") or [],
        "cf_n": (cf or {}).get("n") or 0,
        "methods": methods,
        "post_first_flag_return_pct": round(post_flag_ret, 3)
        if post_flag_ret is not None
        else None,
        "why_not_primary": autopsy.get("primary"),
        "why_not": autopsy.get("why_not"),
        "why_not_stage": autopsy.get("stage_seen"),
        "why_not_reasons": autopsy.get("reasons") or [],
        "why_not_detail": autopsy.get("detail") or {},
        "quiet_early_score": autopsy.get("quiet_early_score"),
        "btc_rel_3d": autopsy.get("btc_rel_3d"),
        "liq_jump_24_vs_3d": autopsy.get("liq_jump_24_vs_3d"),
        "vol_dry_ratio": autopsy.get("vol_dry_ratio"),
        "compression_then_expand": autopsy.get("compression_then_expand"),
        "stage_history": stage_hist,
    }


def build_forward_book(
    disc_runs: Sequence[Dict[str, Any]],
    as_of: datetime,
    cfg: RetroConfig,
    sess: requests.Session,
) -> Dict[str, Any]:
    """Contenders near T-7 → realized ~forward_book_lookback_days return."""
    target = as_of - timedelta(days=cfg.forward_book_lookback_days)
    window_runs = [
        r
        for r in disc_runs
        if abs((r["ts"] - target).total_seconds()) <= 36 * 3600
    ]
    union: List[str] = []
    seen = set()
    run_snapshots = []
    for r in window_runs:
        run_snapshots.append(
            {"ts": r["ts"].isoformat(), "contenders": list(r["contenders"])}
        )
        for p in r["contenders"]:
            if p not in seen:
                seen.add(p)
                union.append(p)

    rows = []
    rets: List[float] = []
    for p in union:
        ret = daily_return_approx(
            sess, p, int(round(cfg.forward_book_lookback_days)), cfg
        )
        time.sleep(cfg.request_pause_s)
        row = {"product_id": p, f"ret_{int(cfg.forward_book_lookback_days)}d_pct": ret}
        rows.append(row)
        if isinstance(ret, (int, float)):
            rets.append(float(ret))

    summary: Dict[str, Any] = {
        "n": len(rets),
        "mean_pct": round(sum(rets) / len(rets), 3) if rets else None,
        "hit_gt0": round(sum(1 for x in rets if x > 0) / len(rets), 4) if rets else None,
        "hit_gt15": round(sum(1 for x in rets if x > 15) / len(rets), 4) if rets else None,
        "best_pct": round(max(rets), 3) if rets else None,
        "worst_pct": round(min(rets), 3) if rets else None,
    }
    rows.sort(
        key=lambda r: (
            r.get(f"ret_{int(cfg.forward_book_lookback_days)}d_pct")
            if isinstance(r.get(f"ret_{int(cfg.forward_book_lookback_days)}d_pct"), (int, float))
            else -9999
        ),
        reverse=True,
    )
    return {
        "anchor_ts": target.isoformat(),
        "lookback_days": cfg.forward_book_lookback_days,
        "window_runs": run_snapshots,
        "contenders_union": union,
        "rows": rows,
        "summary": summary,
    }


def method_hypotheses(gainer_rows: Sequence[Dict[str, Any]], forward: Dict[str, Any]) -> List[str]:
    """Plain-English research hypotheses — not promote claims."""
    n = len(gainer_rows)
    by_class = Counter(r["lead_class"] for r in gainer_rows)
    week_hits = by_class.get(CLASS_EARLY, 0)
    true_early = sum(
        1
        for r in gainer_rows
        if r.get("lead_class") == CLASS_EARLY and r.get("early_quality") == "true_early_flag"
    )
    chronic_early = sum(
        1
        for r in gainer_rows
        if r.get("early_quality") == "chronic_watchlist"
    )
    coincident = by_class.get(CLASS_COINCIDENT, 0)
    never = by_class.get(CLASS_NEVER, 0)
    short = by_class.get(CLASS_SHORT, 0) + by_class.get(CLASS_MEDIUM, 0)
    fwd = forward.get("summary") or {}

    lines = [
        "Hypotheses to test next (instrumentation → evidence → only then promote path):",
        f"1. Current discovery is late-by-design on explode days: "
        f"NEVER={never}/{n}, COINCIDENT={coincident}/{n}, SHORT/MED={short}/{n}, "
        f"EARLY≥7d={week_hits}/{n} (of which true_early={true_early}, chronic_watchlist={chronic_early}).",
    ]
    if true_early == 0 and n:
        lines.append(
            "2. **True** week-ahead explode detection (fresh name, not chronic watchlist) "
            "is absent on this tape with energy/mom quality. Do not add buy paths that assume it."
        )
    if chronic_early:
        lines.append(
            "2b. Chronic contenders (PUMP/ZEC/HYPE-class) can look EARLY by first-seen clock — "
            "that is watchlist persistence, not pre-impulse radar. Score them separately."
        )
    if coincident and n and coincident >= max(1, n // 3):
        lines.append(
            "3. Day-of quality hits are common on melt-ups — treat as **chase confirmation**, "
            "pair with pump-brake / membership M1 extended checks (already partially wired)."
        )
    mean = fwd.get("mean_pct")
    hit = fwd.get("hit_gt0")
    if mean is not None and hit is not None:
        lines.append(
            f"4. T-7 contender forward book: mean={mean}% hit>0={hit:.0%} "
            f"(n={fwd.get('n')}). If mean≤0 and hit≪50%, contender list is **not** an alpha sleeve — "
            "it's an attention list."
        )
    lines.append(
        "5. Feature direction worth shadow-testing (no live bind): "
        "(a) pre-impulse vol dry-up → expand, (b) relative strength vs BTC on 3–5d *before* "
        "energy tops the board, (c) liquidity regime break (quote vol percentile jump) with "
        "**muted** 24h ret (catch compression, not the green candle). "
        "Board now logs quiet_early_score / btc_rel_3d / liq_jump / vol_dry / compression "
        "on each gainer (post-move biased today). pair_discovery_runs schema v2 stores "
        "prequal/quality reject ledgers going forward for true why-not."
    )
    why_counts = Counter(
        r.get("why_not_primary") for r in gainer_rows if r.get("why_not_primary")
    )
    if why_counts:
        top_why = ", ".join(f"{k}={v}" for k, v in why_counts.most_common(6))
        lines.append(
            f"5b. Why-not distribution on this board: {top_why}. "
            "thin_liquidity + below_prequal_cutoff = energy funnel never saw them; "
            "quality_fail = saw energy but structure gate; pump_brake/coincident_late = saw but too late to size."
        )
    quiet_scores = [
        float(r["quiet_early_score"])
        for r in gainer_rows
        if isinstance(r.get("quiet_early_score"), (int, float))
    ]
    if quiet_scores:
        lines.append(
            f"5c. quiet_early_score on today's gainers: mean={sum(quiet_scores)/len(quiet_scores):.3f} "
            f"(n={len(quiet_scores)}). High after a rip ≠ early — score must be validated on "
            "T−3/T−7 frozen snapshots before trusting."
        )
    lines.append(
        "6. Process bar for 'game changer': standing forward book must beat liquid-universe "
        "base rate on 7d excess **and** survive fees/SL shadow before any seat path."
    )
    return lines


def plain_english(board: Dict[str, Any]) -> str:
    g = board.get("gainer_retro") or []
    fwd = (board.get("forward_book") or {}).get("summary") or {}
    by_class = Counter(r.get("lead_class") for r in g)
    why = board.get("why_not_counts") or Counter(
        r.get("why_not_primary") for r in g if r.get("why_not_primary")
    )
    lines = [
        f"Discovery retro board as_of {board.get('as_of')}",
        f"Top gainers scored: {len(g)} (vol≥${board.get('config', {}).get('min_gainer_volume_usd', 0):,.0f}, "
        f"ret≥{board.get('config', {}).get('min_gainer_ret_pct', 0)}%).",
        "Lead classes: "
        + ", ".join(f"{k}={by_class[k]}" for k in (
            CLASS_EARLY, CLASS_MEDIUM, CLASS_SHORT, CLASS_COINCIDENT, CLASS_NEVER
        ) if by_class.get(k)),
        f"Week-ahead (EARLY) hits: {by_class.get(CLASS_EARLY, 0)}/{len(g)}.",
        "Why-not: "
        + (", ".join(f"{k}={v}" for k, v in sorted(why.items(), key=lambda kv: -kv[1])) if why else "n/a"),
        f"T-7 forward book: n={fwd.get('n')} mean={fwd.get('mean_pct')}% "
        f"hit>0={fwd.get('hit_gt0')} hit>+15%={fwd.get('hit_gt15')}.",
        "Shadow only — no config writes, no orders.",
    ]
    return "\n".join(lines)


def render_markdown(board: Dict[str, Any]) -> str:
    g = board.get("gainer_retro") or []
    fwd = board.get("forward_book") or {}
    hyp = board.get("method_hypotheses") or []
    lines = [
        "# Discovery retro board (shadow)",
        "",
        f"**as_of:** `{board.get('as_of')}`  ",
        f"**status:** research / read-only  ",
        f"**discovery runs used:** {board.get('discovery_runs_n')} "
        f"({board.get('discovery_runs_from')} → {board.get('discovery_runs_to')})  ",
        "",
        "## Plain English",
        "",
        "```",
        plain_english(board),
        "```",
        "",
        "## Why this exists",
        "",
        "Work **backwards** from names exploding today → did we flag them at T−7 / T−3 / T−1?  ",
        "Work **forwards** from names we flagged a week ago → did that cohort win?  ",
        "That is the only honest test of early-detect. Not a buy signal.",
        "",
        "## Gainer lookback (today's rippers × frozen contender lists)",
        "",
        "| Pair | 24h % | Vol $ | Lead | Style | Why not | Quiet | T-7 | T-3 | T-1 | T0 | Methods |",
        "|---|---:|---:|---|---|---|---:|---|---|---|---|---|",
    ]
    for r in g:
        a = r.get("anchors") or {}
        def yn(label: str) -> str:
            slot = a.get(label) or {}
            return "Y" if slot.get("present") else "·"

        methods = ",".join(r.get("methods") or []) or "—"
        style = r.get("watch_style") or "—"
        eq = r.get("early_quality")
        lc = r.get("lead_class")
        if eq:
            lc = f"{lc} ({eq})"
        why = r.get("why_not_primary") or "—"
        # Keep table cells short; full line in JSON / section below
        why_short = why
        quiet = r.get("quiet_early_score")
        quiet_s = f"{quiet:.2f}" if isinstance(quiet, (int, float)) else "—"
        lines.append(
            f"| {r.get('product_id')} | {r.get('ret_24h_pct')} | "
            f"{r.get('volume_quote_usd')} | **{lc}** | {style} | "
            f"`{why_short}` | {quiet_s} | "
            f"{yn('T-7d')} | {yn('T-3d')} | {yn('T-1d')} | {yn('T0')} | "
            f"{methods} |"
        )

    lines += [
        "",
        "### Why not (detail)",
        "",
    ]
    for r in g:
        full = r.get("why_not") or r.get("why_not_primary") or "—"
        lines.append(f"- **{r.get('product_id')}**: {full}")

    lines += [
        "",
        "### Quiet features (research sketch — post-move biased)",
        "",
        "| Pair | quiet_early | btc_rel_3d | liq_jump | vol_dry | compress→expand |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in g:
        def fmt(x: Any) -> str:
            if isinstance(x, (int, float)):
                return f"{x:.4f}"
            return "—"

        lines.append(
            f"| {r.get('product_id')} | {fmt(r.get('quiet_early_score'))} | "
            f"{fmt(r.get('btc_rel_3d'))} | {fmt(r.get('liq_jump_24_vs_3d'))} | "
            f"{fmt(r.get('vol_dry_ratio'))} | {fmt(r.get('compression_then_expand'))} |"
        )

    lines += [
        "",
        "### Lead class legend",
        "",
        "- **EARLY** ≥7d before as_of — only class that could be 'week-ago identify'",
        "- **MEDIUM** 3–7d — early impulse, not full week",
        "- **SHORT** 1–3d — often already moving",
        "- **COINCIDENT** <24h — found during/after the green day",
        "- **NEVER** — exchange tape only; our funnels never named it",
        "",
        "### Why-not codes",
        "",
        "- `picked` / `coincident_late` / `pump_brake` / `promote_blocked` — funnel saw it",
        "- `thin_liquidity` — below discovery $ vol floor",
        "- `below_prequal_cutoff` — vol ok but lost energy top-N vs peers",
        "- `quality_fail` — made energy screen, failed mom/vol structure",
        "- `contender_cutoff` — quality pass, not top contenders",
        "- `active_basket` — already seated (excluded from emerging list)",
        "",
        "## Forward book (T−7 contenders → realized ~7d)",
        "",
        f"Anchor ~ `{fwd.get('anchor_ts')}`  ",
        f"Union size: **{len(fwd.get('contenders_union') or [])}**  ",
        "",
    ]
    sm = fwd.get("summary") or {}
    lines.append(
        f"Summary: n={sm.get('n')} · mean={sm.get('mean_pct')}% · "
        f"hit>0={sm.get('hit_gt0')} · hit>+15%={sm.get('hit_gt15')} · "
        f"best={sm.get('best_pct')} · worst={sm.get('worst_pct')}"
    )
    lines += [
        "",
        "| Pair | ~7d ret % |",
        "|---|---:|",
    ]
    for row in (fwd.get("rows") or [])[:40]:
        k = [x for x in row.keys() if x.startswith("ret_")][0]
        lines.append(f"| {row.get('product_id')} | {row.get(k)} |")

    lines += ["", "## Method hypotheses (not GO)", ""]
    for h in hyp:
        lines.append(f"- {h}")

    lines += [
        "",
        "## SSOT / safety",
        "",
        "- Writes **only**: `data/state/discovery_retro_board_*.json*` + this report",
        "- Does **not** write `config/*`, live basket, exit automation, or runner state",
        "- Gainers source: Coinbase public stats (same family as discovery prequal)",
        "- Contender truth: frozen `pair_discovery_runs.jsonl` (no hindsight re-rank)",
        "",
        f"*Generated by `phase6.core.discovery_retro_board` · {board.get('as_of')}*",
        "",
    ]
    return "\n".join(lines)


def build_board(
    cfg: Optional[RetroConfig] = None,
    *,
    gainers_override: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    cfg = cfg or RetroConfig()
    sess = _session()
    disc = load_discovery_runs()
    pipe = load_pipeline_runs()
    cf_arms = load_cf_add_arms()
    disc_idx = _index_latest_discovery(load_discovery_latest())

    as_of = disc[-1]["ts"] if disc else _now()

    btc_candles: Optional[List[list]] = None
    if cfg.fetch_prices and cfg.run_quiet_features:
        btc_candles = _fetch_candles_list(
            sess, "BTC-USD", cfg.candle_granularity, cfg.timeout_s
        )
        time.sleep(cfg.request_pause_s)

    if gainers_override is not None:
        gainers = gainers_override
    elif cfg.fetch_prices:
        gainers = fetch_top_gainers(sess, cfg)
    else:
        gainers = []

    gainer_rows = []
    for g in gainers:
        pid = g["product_id"]
        row = classify_gainer(
            pid,
            g,
            disc,
            pipe,
            cf_arms,
            as_of,
            cfg,
            sess=sess if cfg.fetch_prices else None,
            discovery_idx=disc_idx,
            btc_candles=btc_candles,
        )
        gainer_rows.append(row)

    forward: Dict[str, Any] = {
        "anchor_ts": None,
        "contenders_union": [],
        "rows": [],
        "summary": {},
    }
    if cfg.fetch_prices and disc:
        forward = build_forward_book(disc, as_of, cfg, sess)

    why_counts = dict(Counter(r.get("why_not_primary") for r in gainer_rows if r.get("why_not_primary")))

    board: Dict[str, Any] = {
        "schema": "discovery_retro_board_v2",
        "as_of": _now().isoformat(),
        "reference_discovery_ts": as_of.isoformat(),
        "status": "shadow_research_only",
        "mutates_config": False,
        "places_orders": False,
        "config": {
            "top_gainers_n": cfg.top_gainers_n,
            "min_gainer_volume_usd": cfg.min_gainer_volume_usd,
            "min_gainer_ret_pct": cfg.min_gainer_ret_pct,
            "forward_book_lookback_days": cfg.forward_book_lookback_days,
            "run_why_not_autopsy": cfg.run_why_not_autopsy,
            "run_quiet_features": cfg.run_quiet_features,
        },
        "discovery_runs_n": len(disc),
        "discovery_runs_from": disc[0]["ts"].isoformat() if disc else None,
        "discovery_runs_to": disc[-1]["ts"].isoformat() if disc else None,
        "discovery_latest_ts": disc_idx.get("ts"),
        "pipeline_runs_n": len(pipe),
        "gainer_retro": gainer_rows,
        "forward_book": forward,
        "lead_class_counts": dict(Counter(r["lead_class"] for r in gainer_rows)),
        "why_not_counts": why_counts,
        "method_hypotheses": [],
        "plain_english": "",
    }
    board["method_hypotheses"] = method_hypotheses(gainer_rows, forward)
    board["plain_english"] = plain_english(board)
    return board


def persist_board(board: Dict[str, Any]) -> Dict[str, str]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (PROJECT_ROOT / "reports").mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(board, indent=2, default=str) + "\n", encoding="utf-8")
    with OUT_JSONL.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "ts": board.get("as_of"),
                    "schema": board.get("schema"),
                    "lead_class_counts": board.get("lead_class_counts"),
                    "why_not_counts": board.get("why_not_counts"),
                    "forward_summary": (board.get("forward_book") or {}).get("summary"),
                    "n_gainers": len(board.get("gainer_retro") or []),
                    "week_ahead_hits": (board.get("lead_class_counts") or {}).get(
                        CLASS_EARLY, 0
                    ),
                },
                default=str,
            )
            + "\n"
        )
    md = render_markdown(board)
    OUT_MD.write_text(md, encoding="utf-8")
    return {
        "json": str(OUT_JSON),
        "jsonl": str(OUT_JSONL),
        "md": str(OUT_MD),
    }


def run_retro_board(cfg: Optional[RetroConfig] = None) -> Dict[str, Any]:
    cfg = cfg or RetroConfig()
    board = build_board(cfg)
    paths = {}
    if cfg.write:
        paths = persist_board(board)
    board["wrote"] = paths
    return board
