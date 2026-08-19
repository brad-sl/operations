#!/usr/bin/env python3
"""
POOL-CYCLING-001 — Active Trading Pool ↔ Opportunity Pool swaps (shadow-first).

Purpose
-------
Replace low-potential pairs in the *active* trading basket (global_settings.pairs)
with higher-potential names from the larger *opportunity* pool
(phase_6_specific.opportunity_pool), so the runner/rebalancer can only trade a
capped set while still surfacing better candidates over time.

This was designed 2026-06-13 as a **separate script** (not inside the hot runner
path). Until this module existed, the basket never changed because nothing wrote
to config — only capital rotation *inside* the fixed 11 ran live.

Default mode is **shadow**: propose swaps, log them, never mutate live config.
Optional --write-proposed writes a sidecar JSON the operator can promote later.
--apply-config is an explicit, gated write of global_settings.pairs (still never
runs from cron without human intent).

Real data only: RSI cache, sentiment scorer, price history (via opportunity_scanner helpers).
"""
from __future__ import annotations

import json
import shutil
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from phase6.core.opportunity_scanner import (
    compute_vol_and_momentum,
    load_real_data,
    score_opportunity,
)
from phase6.core.paths import PROJECT_ROOT, TRADING_CONFIG_PHASE6, load_trading_basket
from phase6.core.regime_switcher import get_active_regime

# Sticky core: never auto-eject from active pool (still scored for reporting).
DEFAULT_STICKY = ("BTC-USD", "ETH-USD")

# Extra liquid Coinbase-style candidates scored in shadow even if not yet in config
# opportunity_pool. Active pool is never expanded from these without a proposed swap.
DEFAULT_SHADOW_CANDIDATES = (
    "MATIC-USD",
    "AAVE-USD",
    "NEAR-USD",
    "SUI-USD",
    "DOT-USD",
    "ATOM-USD",
    "LTC-USD",
    "BCH-USD",
)

DEFAULT_STATE_DIR = PROJECT_ROOT / "data" / "state"
PROPOSALS_JSONL = DEFAULT_STATE_DIR / "pool_cycling_proposals.jsonl"
LATEST_JSON = DEFAULT_STATE_DIR / "pool_cycling_latest.json"
PROPOSED_PAIRS_JSON = DEFAULT_STATE_DIR / "pool_cycling_proposed_pairs.json"


@dataclass
class PoolCyclingConfig:
    min_score_delta: float = 0.08
    weak_max_score: float = 0.35
    strong_min_score: float = 0.40
    max_swaps: int = 1
    sticky_pairs: Tuple[str, ...] = DEFAULT_STICKY
    # Prefer ejecting names with little/no held USD when holdings are known.
    prefer_flat_ejects: bool = True
    min_held_usd_to_protect: float = 40.0
    # Merge these into the scored opportunity set (shadow discovery).
    shadow_candidates: Tuple[str, ...] = DEFAULT_SHADOW_CANDIDATES


@dataclass
class PairScore:
    pair: str
    score: float
    mode: str
    rsi: float
    sentiment: float
    momentum_pct: float
    vol: float
    in_active: bool
    held_usd: float
    sticky: bool
    reason: str
    has_real_data: bool = False


@dataclass
class SwapProposal:
    remove: str
    add: str
    remove_score: float
    add_score: float
    delta: float
    reason: str
    remove_held_usd: float


@dataclass
class PoolCyclingReport:
    timestamp: str
    mode: str  # shadow | proposed_written | config_applied
    active_pool: List[str]
    opportunity_pool: List[str]
    outside_active: List[str]
    scores: List[Dict[str, Any]]
    swaps: List[Dict[str, Any]]
    proposed_active: List[str]
    gates: Dict[str, Any] = field(default_factory=dict)
    note: str = ""
    data_sources: List[str] = field(default_factory=list)


def _load_config(path: Path = TRADING_CONFIG_PHASE6) -> Dict[str, Any]:
    with open(path) as f:
        return json.load(f)


def load_active_and_opportunity(
    cfg: Optional[Dict[str, Any]] = None,
) -> Tuple[List[str], List[str]]:
    """Active = global_settings.pairs; opportunity = pool (fallback active)."""
    cfg = cfg or _load_config()
    active = [str(p) for p in (cfg.get("global_settings") or {}).get("pairs") or []]
    if not active:
        active = list(load_trading_basket())
    pool = [str(p) for p in (cfg.get("phase_6_specific") or {}).get("opportunity_pool") or []]
    if not pool:
        pool = list(active)
    # Opportunity must cover active for clean membership math.
    for p in active:
        if p not in pool:
            pool.append(p)
    return active, pool


def load_holdings_usd() -> Dict[str, float]:
    """Best-effort held notional from live state / dashboard cache. 0 if unknown."""
    holdings: Dict[str, float] = {}
    candidates = [
        PROJECT_ROOT / "data" / "state" / "phase6_live_state.json",
        PROJECT_ROOT / "data" / "state" / "dashboard_live_state.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            raw = json.loads(path.read_text())
        except Exception:
            continue
        # Common shapes
        positions = (
            raw.get("positions")
            or raw.get("holdings")
            or (raw.get("portfolio") or {}).get("positions")
            or {}
        )
        if isinstance(positions, list):
            # phase6_live_state.json: [{pair, value_usd, amount, ...}, ...]
            for meta in positions:
                if not isinstance(meta, dict):
                    continue
                pair = meta.get("pair") or meta.get("product_id") or meta.get("symbol")
                if not pair:
                    continue
                usd = meta.get("value_usd") or meta.get("usd") or meta.get("notional_usd")
                if usd is None:
                    try:
                        qty = meta.get("amount") or meta.get("quantity") or meta.get("available")
                        px = meta.get("current_price") or meta.get("price")
                        if qty is not None and px is not None:
                            usd = float(qty) * float(px)
                    except (TypeError, ValueError):
                        usd = 0.0
                try:
                    holdings[str(pair)] = float(usd or 0.0)
                except (TypeError, ValueError):
                    holdings[str(pair)] = 0.0
        elif isinstance(positions, dict):
            for pair, meta in positions.items():
                if isinstance(meta, dict):
                    usd = meta.get("value_usd") or meta.get("usd") or meta.get("notional_usd")
                    if usd is None and meta.get("quantity") is not None and meta.get("price"):
                        try:
                            usd = float(meta["quantity"]) * float(meta["price"])
                        except (TypeError, ValueError):
                            usd = 0.0
                    try:
                        holdings[str(pair)] = float(usd or 0.0)
                    except (TypeError, ValueError):
                        holdings[str(pair)] = 0.0
                else:
                    try:
                        holdings[str(pair)] = float(meta or 0.0)
                    except (TypeError, ValueError):
                        pass
        if holdings:
            break
    return holdings


def score_universe(
    pairs: Sequence[str],
    active: Sequence[str],
    sticky: Sequence[str],
    holdings: Optional[Dict[str, float]] = None,
) -> List[PairScore]:
    """Score each pair with real caches (same factors as opportunity_scanner)."""
    data = load_real_data()
    rsi_map = data.get("rsi") or {}
    sent_map = data.get("sentiment") or {}
    ph_map = data.get("price_history") or {}
    holdings = holdings or {}
    active_set = set(active)
    sticky_set = set(sticky)
    out: List[PairScore] = []

    for pair in pairs:
        rsi_entry = rsi_map.get(pair, {})
        has_rsi = False
        if isinstance(rsi_entry, dict) and rsi_entry:
            try:
                rsi = float(rsi_entry.get("rsi", 50.0) or 50.0)
                has_rsi = "rsi" in rsi_entry or "value" in rsi_entry
            except (TypeError, ValueError):
                rsi = 50.0
        elif rsi_entry not in (None, "", {}):
            try:
                rsi = float(rsi_entry)
                has_rsi = True
            except (TypeError, ValueError):
                rsi = 50.0
                has_rsi = False
        else:
            rsi = 50.0

        has_sent = pair in sent_map and sent_map.get(pair) is not None
        try:
            sent = float(sent_map.get(pair, 0.0) or 0.0) if has_sent else 0.0
        except (TypeError, ValueError):
            sent = 0.0
            has_sent = False

        prices = ph_map.get(pair, [])
        if isinstance(prices, dict):
            prices = prices.get("closes") or prices.get("prices") or []
        has_px = isinstance(prices, list) and len(prices) >= 5
        vol, mom = compute_vol_and_momentum(prices if isinstance(prices, list) else [], n=30)
        is_current = pair in active_set
        try:
            pair_mode = get_active_regime(prices if isinstance(prices, list) else [], rsi)
        except Exception:
            pair_mode = "hybrid"
        score, reason = score_opportunity(
            pair, rsi, sent, vol, mom, is_current=is_current, mode=pair_mode
        )
        has_real = bool(has_rsi or has_px or (has_sent and abs(sent) > 1e-9))
        if not has_real:
            # Do not let blank candidates look like mid-tier opportunities.
            score = min(float(score), 0.15)
            reason = f"NO_DATA (capped) | {reason}"
        out.append(
            PairScore(
                pair=pair,
                score=float(score),
                mode=str(pair_mode),
                rsi=round(rsi, 2),
                sentiment=round(sent, 4),
                momentum_pct=float(mom),
                vol=float(vol),
                in_active=is_current,
                held_usd=float(holdings.get(pair, 0.0) or 0.0),
                sticky=pair in sticky_set,
                reason=reason,
                has_real_data=has_real,
            )
        )
    out.sort(key=lambda x: x.score, reverse=True)
    return out


def propose_swaps(
    scores: Sequence[PairScore],
    active: Sequence[str],
    cfg: PoolCyclingConfig,
) -> List[SwapProposal]:
    """
    Greedy 1:1 swaps: weakest eligible active out, strongest outside in,
    only if delta and absolute gates pass.
    """
    active_set = set(active)
    by_pair = {s.pair: s for s in scores}

    eject_candidates = [
        s
        for s in scores
        if s.in_active
        and not s.sticky
        and s.score <= cfg.weak_max_score
    ]
    # Prefer lowest score; among ties prefer flatter holdings.
    def eject_key(s: PairScore) -> Tuple[float, float]:
        held_pen = s.held_usd if cfg.prefer_flat_ejects else 0.0
        return (s.score, held_pen)

    eject_candidates.sort(key=eject_key)

    add_candidates = [
        s
        for s in scores
        if (not s.in_active)
        and s.has_real_data
        and s.score >= cfg.strong_min_score
        and s.pair not in active_set
    ]
    add_candidates.sort(key=lambda s: s.score, reverse=True)

    swaps: List[SwapProposal] = []
    used_out: set = set()
    used_in: set = set()

    for out_s in eject_candidates:
        if len(swaps) >= cfg.max_swaps:
            break
        if out_s.pair in used_out:
            continue
        if cfg.prefer_flat_ejects and out_s.held_usd >= cfg.min_held_usd_to_protect:
            # Still allow if no flat weak names left — deferred to second pass
            continue
        for in_s in add_candidates:
            if in_s.pair in used_in:
                continue
            delta = in_s.score - out_s.score
            if delta < cfg.min_score_delta:
                continue
            swaps.append(
                SwapProposal(
                    remove=out_s.pair,
                    add=in_s.pair,
                    remove_score=out_s.score,
                    add_score=in_s.score,
                    delta=round(delta, 4),
                    reason=(
                        f"replace low-potential {out_s.pair} (score={out_s.score:.3f}, "
                        f"held=${out_s.held_usd:.0f}) with {in_s.pair} "
                        f"(score={in_s.score:.3f}); Δ={delta:.3f}"
                    ),
                    remove_held_usd=out_s.held_usd,
                )
            )
            used_out.add(out_s.pair)
            used_in.add(in_s.pair)
            break

    # Second pass: allow protected holdings if still need swaps and delta is strong
    if len(swaps) < cfg.max_swaps:
        for out_s in eject_candidates:
            if len(swaps) >= cfg.max_swaps:
                break
            if out_s.pair in used_out:
                continue
            for in_s in add_candidates:
                if in_s.pair in used_in:
                    continue
                delta = in_s.score - out_s.score
                if delta < max(cfg.min_score_delta, 0.12):
                    continue
                swaps.append(
                    SwapProposal(
                        remove=out_s.pair,
                        add=in_s.pair,
                        remove_score=out_s.score,
                        add_score=in_s.score,
                        delta=round(delta, 4),
                        reason=(
                            f"held-protected override: replace {out_s.pair} "
                            f"(score={out_s.score:.3f}, held=${out_s.held_usd:.0f}) "
                            f"with {in_s.pair} (score={in_s.score:.3f}); Δ={delta:.3f}"
                        ),
                        remove_held_usd=out_s.held_usd,
                    )
                )
                used_out.add(out_s.pair)
                used_in.add(in_s.pair)
                break

    return swaps


def apply_swaps_to_active(active: Sequence[str], swaps: Sequence[SwapProposal]) -> List[str]:
    result = list(active)
    for sw in swaps:
        if sw.remove in result:
            result = [sw.add if p == sw.remove else p for p in result]
        elif sw.add not in result:
            result.append(sw.add)
    # de-dupe preserve order
    seen = set()
    out: List[str] = []
    for p in result:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def run_pool_cycling(
    cfg: Optional[PoolCyclingConfig] = None,
    trading_config_path: Path = TRADING_CONFIG_PHASE6,
    write_log: bool = True,
    write_proposed: bool = False,
    apply_config: bool = False,
) -> PoolCyclingReport:
    """
    Main entry. Shadow by default.

    apply_config=True rewrites global_settings.pairs in trading config (with backup).
    write_proposed=True writes sidecar proposed pairs JSON only.
    """
    cfg = cfg or PoolCyclingConfig()
    if apply_config and not write_proposed:
        # Always materialize proposed artifact when applying.
        write_proposed = True

    tcfg = _load_config(trading_config_path)
    active, opportunity = load_active_and_opportunity(tcfg)
    # Prefer discovery contenders (emerging high-energy) over static shadow list when present.
    try:
        from phase6.core.pair_discovery import load_discovery_contender_ids

        discovered = load_discovery_contender_ids()
    except Exception:
        discovered = []
    scored_universe: List[str] = list(opportunity)
    # Discovery first (priority order preserved)
    for p in discovered:
        if p not in scored_universe:
            scored_universe.append(p)
    for p in cfg.shadow_candidates:
        if p not in scored_universe:
            scored_universe.append(p)
    holdings = load_holdings_usd()
    scores = score_universe(scored_universe, active, cfg.sticky_pairs, holdings)
    swaps = propose_swaps(scores, active, cfg)
    proposed = apply_swaps_to_active(active, swaps)
    outside = [p for p in scored_universe if p not in set(active)]
    # Report config pool separately from full scored set
    opportunity_for_report = list(scored_universe)

    mode = "shadow"
    note = (
        "Shadow only — live global_settings.pairs unchanged. "
        "Capital rotation inside the fixed basket is separate (ARCH-4)."
    )

    if write_proposed and swaps:
        DEFAULT_STATE_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "from_active": active,
            "proposed_active": proposed,
            "swaps": [asdict(s) for s in swaps],
            "sticky": list(cfg.sticky_pairs),
            "gate": "operator promote only",
        }
        PROPOSED_PAIRS_JSON.write_text(json.dumps(payload, indent=2) + "\n")
        mode = "proposed_written"
        note = f"Wrote {PROPOSED_PAIRS_JSON} (config not applied)."

    if apply_config and swaps:
        backup = trading_config_path.with_suffix(
            trading_config_path.suffix + f".bak_poolcycle_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        shutil.copy2(trading_config_path, backup)
        new_cfg = deepcopy(tcfg)
        new_cfg.setdefault("global_settings", {})["pairs"] = proposed
        # Keep opportunity pool as the broader set
        opp = list(dict.fromkeys(list(opportunity) + proposed))
        new_cfg.setdefault("phase_6_specific", {})["opportunity_pool"] = opp
        trading_config_path.write_text(json.dumps(new_cfg, indent=2) + "\n")
        mode = "config_applied"
        note = f"Applied pairs to {trading_config_path.name}; backup {backup.name}."

    # Fresh data sources list
    data = load_real_data()
    report = PoolCyclingReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        mode=mode,
        active_pool=list(active),
        opportunity_pool=opportunity_for_report,
        outside_active=outside,
        scores=[asdict(s) for s in scores],
        swaps=[asdict(s) for s in swaps],
        proposed_active=proposed,
        gates={
            "min_score_delta": cfg.min_score_delta,
            "weak_max_score": cfg.weak_max_score,
            "strong_min_score": cfg.strong_min_score,
            "max_swaps": cfg.max_swaps,
            "sticky_pairs": list(cfg.sticky_pairs),
            "apply_config": apply_config,
            "write_proposed": write_proposed,
        },
        note=note,
        data_sources=list(data.get("data_sources") or []),
    )

    if write_log:
        DEFAULT_STATE_DIR.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": report.timestamp,
            "mode": report.mode,
            "swaps": report.swaps,
            "active": report.active_pool,
            "proposed": report.proposed_active,
            "outside": report.outside_active,
            "top": [
                {"pair": s["pair"], "score": s["score"], "in_active": s["in_active"]}
                for s in report.scores[:5]
            ],
            "bottom_active": [
                {"pair": s["pair"], "score": s["score"]}
                for s in sorted(
                    [x for x in report.scores if x["in_active"]],
                    key=lambda x: x["score"],
                )[:3]
            ],
            "note": report.note,
        }
        with open(PROPOSALS_JSONL, "a") as f:
            f.write(json.dumps(entry) + "\n")
        LATEST_JSON.write_text(json.dumps(asdict(report), indent=2) + "\n")

    return report


def report_to_plain_english(report: PoolCyclingReport) -> str:
    lines = [
        f"Pool cycling ({report.mode}) @ {report.timestamp}",
        f"Active ({len(report.active_pool)}): {', '.join(report.active_pool)}",
        f"Opportunity ({len(report.opportunity_pool)}): {', '.join(report.opportunity_pool)}",
        f"Outside active: {', '.join(report.outside_active) or '(none — pool == active)'}",
    ]
    if not report.swaps:
        lines.append(
            "Swaps proposed: **none** (gates not met, or nothing outside active with edge)."
        )
        no_data = [s["pair"] for s in report.scores if not s.get("in_active") and not s.get("has_real_data")]
        if no_data:
            lines.append(
                f"Outside candidates missing RSI/price/sent coverage ({len(no_data)}): "
                f"{', '.join(no_data[:8])}{'…' if len(no_data) > 8 else ''} — warm data before swaps can fire."
            )
        if not report.outside_active:
            lines.append(
                "Why no basket changes historically: opportunity_pool ≈ active set, and no cycler was scheduled — "
                "capital rotated inside the fixed basket only."
            )
    else:
        lines.append("Swaps proposed:")
        for s in report.swaps:
            lines.append(
                f"  - OUT {s['remove']} ({s['remove_score']:.3f}) → "
                f"IN {s['add']} ({s['add_score']:.3f}) Δ={s['delta']:.3f}"
            )
        lines.append(f"Proposed active: {', '.join(report.proposed_active)}")
    lines.append(report.note)
    return "\n".join(lines)
