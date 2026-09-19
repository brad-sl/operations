"""Luck ladder R1 — knife vs wash filter shadow (measure only).

Arms on RSI-wash would-buy candidates:
  rsi_only       — baseline (enter on wash alone)
  rsi_reclaim    — require reclaim of prior 1h low within lookback
  rsi_delay_1_3  — wait 1–3 bars with no new low
  rsi_standdown_c — deny when standdown C elev_primary (r24 hot)

No orders. No live buy blocks. No knobs.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "data" / "state"
REPORTS = ROOT / "reports"
LATEST = STATE / "knife_filter_shadow_latest.json"
CRUMBS = STATE / "knife_filter_shadow_crumbs.jsonl"
MD_PATH = REPORTS / "KNIFE_FILTER_SHADOW_LATEST.md"
R0_LATEST = STATE / "rsi_event_x_tryout_shadow_latest.json"
TRYOUT_READY = STATE / "tryout_readiness_latest.json"

ARMS = ("rsi_only", "rsi_reclaim", "rsi_delay_1_3", "rsi_standdown_c")

# RT cost assumption (taker-taker-ish) for net R labels — honesty, not edge claim
DEFAULT_RT_COST = 0.016


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _utc_now()).astimezone(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n")


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(row, default=str) + "\n")


@dataclass
class KnifeConfig:
    rsi_wash_max: float = 40.0
    reclaim_lookback_bars: int = 6
    delay_bars_min: int = 1
    delay_bars_max: int = 3
    horizon_bars: int = 72  # ~3d on 1h
    sl_pct: float = 0.04
    tp_r: float = 2.0
    rt_cost: float = DEFAULT_RT_COST
    live_gate: bool = False
    paid_x: bool = False


@dataclass
class ArmVerdict:
    arm: str
    allow: bool
    reason: str
    entry_bar_offset: int = 0  # bars after wash index


@dataclass
class PathOutcome:
    pair: str
    wash_idx: int
    entry_idx: Optional[int]
    entry_px: Optional[float]
    sl_px: Optional[float]
    tp_px: Optional[float]
    exit_idx: Optional[int]
    exit_px: Optional[float]
    exit_kind: str  # sl | tp | time | none
    r_gross: Optional[float]
    r_net: Optional[float]
    hit_sl_72h: bool = False
    mae: Optional[float] = None
    mfe: Optional[float] = None


@dataclass
class PairKnifeRow:
    pair: str
    rsi: Optional[float] = None
    source: str = ""
    closes_n: int = 0
    wash_idx: Optional[int] = None
    arms: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def load_r0_would_buy_pairs(path: Path = R0_LATEST) -> List[Dict[str, Any]]:
    raw = _read_json(path)
    if not isinstance(raw, dict):
        return []
    out: List[Dict[str, Any]] = []
    cands = raw.get("candidates") or raw.get("top_k") or []
    if isinstance(cands, list):
        for c in cands:
            if not isinstance(c, dict):
                continue
            pair = c.get("pair")
            if not pair:
                continue
            selected = bool(c.get("selected_top_k") or c.get("would_query_x"))
            would_buy = c.get("would_buy_if_pass")
            # include top-k and any explicit would-buy
            if selected or would_buy is True or c.get("in_trigger_pool"):
                out.append(c)
    return out


def load_tryout_eligible_pairs() -> List[str]:
    """Mirror production tryout-eligible SSOT (same as R0)."""
    try:
        from phase6.core.rsi_event_x_tryout_shadow import production_tryout_eligible_sources

        meta = production_tryout_eligible_sources()
        u = meta.get("universe") or []
        if isinstance(u, list) and u:
            return [str(p) for p in u]
    except Exception:
        pass
    # Fallback: readiness scoreboard_summary / eligible list
    raw = _read_json(TRYOUT_READY)
    if not isinstance(raw, dict):
        return []
    top = raw.get("eligible_tryout_pairs")
    if isinstance(top, list) and top:
        return [str(p) for p in top]
    ss = raw.get("scoreboard_summary") or {}
    pairs = ss.get("thaw_active_eligible_pairs") or ss.get("eligible_pairs") or []
    if isinstance(pairs, list):
        return [str(p) for p in pairs]
    return []


def synthetic_wash_closes(
    *,
    n: int = 120,
    wash_at: int = 80,
    wash_depth: float = 0.08,
    reclaim: bool = True,
    continue_down: bool = False,
    seed_px: float = 100.0,
) -> List[float]:
    """Deterministic path for isolation tests (oldest→newest)."""
    closes = [seed_px]
    for i in range(1, n):
        px = closes[-1]
        if i < wash_at:
            px *= 1.0 - 0.001  # mild drift down into wash
        elif i == wash_at:
            px *= 1.0 - wash_depth
        elif continue_down:
            px *= 0.992
        elif reclaim and i <= wash_at + 2:
            px *= 1.012  # bounce reclaim
        else:
            px *= 1.002
        closes.append(round(px, 6))
    return closes


def find_wash_index(closes: Sequence[float], lookback: int = 24) -> Optional[int]:
    """Last bar that made a significant local low (proxy for RSI wash print)."""
    if len(closes) < 5:
        return None
    # use deepest low in last lookback as wash proxy
    start = max(1, len(closes) - lookback)
    window = list(enumerate(closes))[start:]
    if not window:
        return None
    idx, _ = min(window, key=lambda t: t[1])
    return idx


def prior_bar_low(closes: Sequence[float], idx: int) -> Optional[float]:
    if idx <= 0 or idx >= len(closes):
        return None
    # without OHLC, use min(close[idx-1], close[idx]) as prior structure low proxy
    return float(min(closes[idx - 1], closes[idx]))


def arm_rsi_only(wash_idx: int) -> ArmVerdict:
    return ArmVerdict("rsi_only", True, "wash_ok", entry_bar_offset=0)


def arm_rsi_reclaim(
    closes: Sequence[float],
    wash_idx: int,
    *,
    lookback: int = 6,
) -> ArmVerdict:
    if wash_idx is None or wash_idx < 1:
        return ArmVerdict("rsi_reclaim", False, "no_wash", 0)
    pivot = prior_bar_low(closes, wash_idx)
    if pivot is None:
        return ArmVerdict("rsi_reclaim", False, "no_pivot", 0)
    end = min(len(closes) - 1, wash_idx + lookback)
    for j in range(wash_idx + 1, end + 1):
        if closes[j] > pivot:
            return ArmVerdict(
                "rsi_reclaim", True, f"reclaim_bar+{j - wash_idx}", entry_bar_offset=j - wash_idx
            )
    return ArmVerdict("rsi_reclaim", False, "no_reclaim", 0)


def arm_rsi_delay(
    closes: Sequence[float],
    wash_idx: int,
    *,
    delay_min: int = 1,
    delay_max: int = 3,
) -> ArmVerdict:
    if wash_idx is None:
        return ArmVerdict("rsi_delay_1_3", False, "no_wash", 0)
    wash_px = closes[wash_idx]
    last = min(len(closes) - 1, wash_idx + delay_max)
    # need at least delay_min bars after wash
    if wash_idx + delay_min >= len(closes):
        return ArmVerdict("rsi_delay_1_3", False, "not_enough_bars", 0)
    # no new low through delay window
    for j in range(wash_idx + 1, last + 1):
        if closes[j] < wash_px:
            return ArmVerdict("rsi_delay_1_3", False, f"new_low_bar+{j - wash_idx}", 0)
        if j - wash_idx >= delay_min:
            return ArmVerdict(
                "rsi_delay_1_3", True, f"hold_no_ll_+{j - wash_idx}", entry_bar_offset=j - wash_idx
            )
    return ArmVerdict("rsi_delay_1_3", False, "window_end_no_entry", 0)


def arm_standdown_c(
    *,
    elev_primary: bool,
    wash_idx: int,
) -> ArmVerdict:
    if elev_primary:
        return ArmVerdict("rsi_standdown_c", False, "elev_primary_block", 0)
    return ArmVerdict("rsi_standdown_c", True, "no_elev_primary", entry_bar_offset=0)


def simulate_path(
    closes: Sequence[float],
    wash_idx: int,
    entry_offset: int,
    *,
    cfg: KnifeConfig,
) -> PathOutcome:
    entry_idx = wash_idx + max(0, entry_offset)
    pair_out = PathOutcome(
        pair="",
        wash_idx=wash_idx,
        entry_idx=None,
        entry_px=None,
        sl_px=None,
        tp_px=None,
        exit_idx=None,
        exit_px=None,
        exit_kind="none",
        r_gross=None,
        r_net=None,
    )
    if entry_idx >= len(closes) - 1:
        return pair_out
    entry_px = float(closes[entry_idx])
    if entry_px <= 0:
        return pair_out
    risk = entry_px * cfg.sl_pct
    sl_px = entry_px - risk
    tp_px = entry_px + cfg.tp_r * risk
    pair_out.entry_idx = entry_idx
    pair_out.entry_px = entry_px
    pair_out.sl_px = sl_px
    pair_out.tp_px = tp_px

    end = min(len(closes) - 1, entry_idx + cfg.horizon_bars)
    mae = 0.0
    mfe = 0.0
    exit_idx = end
    exit_px = float(closes[end])
    exit_kind = "time"
    for j in range(entry_idx + 1, end + 1):
        px = float(closes[j])
        chg = (px - entry_px) / entry_px
        mae = min(mae, chg)
        mfe = max(mfe, chg)
        if px <= sl_px:
            exit_idx, exit_px, exit_kind = j, px, "sl"
            break
        if px >= tp_px:
            exit_idx, exit_px, exit_kind = j, px, "tp"
            break
    r_gross = (exit_px - entry_px) / risk if risk > 0 else None
    r_net = (r_gross - (cfg.rt_cost / cfg.sl_pct)) if r_gross is not None else None
    # fee drag in R units ≈ rt_cost / sl_pct
    pair_out.exit_idx = exit_idx
    pair_out.exit_px = exit_px
    pair_out.exit_kind = exit_kind
    pair_out.r_gross = r_gross
    pair_out.r_net = r_net
    pair_out.hit_sl_72h = exit_kind == "sl"
    pair_out.mae = mae
    pair_out.mfe = mfe
    return pair_out


def evaluate_arms_on_closes(
    closes: Sequence[float],
    *,
    wash_idx: Optional[int] = None,
    elev_primary: bool = False,
    cfg: Optional[KnifeConfig] = None,
) -> Dict[str, Dict[str, Any]]:
    cfg = cfg or KnifeConfig()
    if wash_idx is None:
        wash_idx = find_wash_index(closes)
    if wash_idx is None:
        return {a: {"allow": False, "reason": "no_wash", "outcome": None} for a in ARMS}

    verdicts = [
        arm_rsi_only(wash_idx),
        arm_rsi_reclaim(closes, wash_idx, lookback=cfg.reclaim_lookback_bars),
        arm_rsi_delay(
            closes,
            wash_idx,
            delay_min=cfg.delay_bars_min,
            delay_max=cfg.delay_bars_max,
        ),
        arm_standdown_c(elev_primary=elev_primary, wash_idx=wash_idx),
    ]
    out: Dict[str, Dict[str, Any]] = {}
    for v in verdicts:
        row: Dict[str, Any] = {
            "allow": v.allow,
            "reason": v.reason,
            "entry_bar_offset": v.entry_bar_offset,
            "outcome": None,
        }
        if v.allow:
            oc = simulate_path(closes, wash_idx, v.entry_bar_offset, cfg=cfg)
            row["outcome"] = {
                "entry_idx": oc.entry_idx,
                "exit_kind": oc.exit_kind,
                "r_gross": oc.r_gross,
                "r_net": oc.r_net,
                "hit_sl_72h": oc.hit_sl_72h,
                "mae": oc.mae,
                "mfe": oc.mfe,
            }
        out[v.arm] = row
    return out


def summarize_arm_table(rows: Sequence[PairKnifeRow]) -> Dict[str, Dict[str, Any]]:
    table: Dict[str, Dict[str, Any]] = {}
    for arm in ARMS:
        n_allow = 0
        n_sl = 0
        r_nets: List[float] = []
        for r in rows:
            a = (r.arms or {}).get(arm) or {}
            if not a.get("allow"):
                continue
            n_allow += 1
            oc = a.get("outcome") or {}
            if oc.get("hit_sl_72h"):
                n_sl += 1
            rn = oc.get("r_net")
            if isinstance(rn, (int, float)) and not math.isnan(float(rn)):
                r_nets.append(float(rn))
        table[arm] = {
            "n_allow": n_allow,
            "n_sl": n_sl,
            "sl_rate": (n_sl / n_allow) if n_allow else None,
            "mean_r_net": (sum(r_nets) / len(r_nets)) if r_nets else None,
            "n_r": len(r_nets),
            "claim": "ATTENTION_ONLY" if n_allow < 15 else "LESS_LOSS_CANDIDATE_REVIEW",
        }
    return table


def elev_primary_from_closes(closes: Sequence[float]) -> bool:
    """Lightweight standdown-C primary: r24 >= +5% (same spirit as filter C)."""
    if len(closes) < 25:
        return False
    a, b = float(closes[-25]), float(closes[-1])
    if a <= 0:
        return False
    r24 = (b / a - 1.0) * 100.0
    return r24 >= 5.0


def try_fetch_closes(pair: str, hours: int = 120) -> Tuple[List[float], Optional[str]]:
    try:
        from phase6.core.standdown_filter_c_shadow import fetch_hourly_closes

        return fetch_hourly_closes(pair, hours)
    except Exception as e:
        return [], str(e)[:160]


def load_rsi_for_pair(pair: str) -> Optional[float]:
    try:
        from phase6.core.standdown_filter_c_shadow import load_rsi_map

        m = load_rsi_map()
        return m.get(pair)
    except Exception:
        return None


def build_universe() -> List[Tuple[str, str, Optional[float]]]:
    """Return (pair, source, rsi_hint). Prefer R0 would-buys, else tryout eligible."""
    out: List[Tuple[str, str, Optional[float]]] = []
    seen = set()
    for c in load_r0_would_buy_pairs():
        pair = str(c.get("pair"))
        if pair in seen:
            continue
        seen.add(pair)
        rsi = c.get("rsi")
        try:
            rsi_f = float(rsi) if rsi is not None else None
        except (TypeError, ValueError):
            rsi_f = None
        out.append((pair, "r0_would_buy", rsi_f))
    if not out:
        for pair in load_tryout_eligible_pairs():
            if pair in seen:
                continue
            seen.add(pair)
            out.append((pair, "tryout_eligible", None))
    return out


def run_knife_filter_shadow(
    *,
    cfg: Optional[KnifeConfig] = None,
    closes_by_pair: Optional[Dict[str, Sequence[float]]] = None,
    pairs: Optional[Sequence[str]] = None,
    write: bool = True,
) -> Dict[str, Any]:
    cfg = cfg or KnifeConfig()
    rows: List[PairKnifeRow] = []

    universe = build_universe()
    if pairs:
        want = set(pairs)
        universe = [(p, s, r) for p, s, r in universe if p in want]
        for p in pairs:
            if p not in {u[0] for u in universe}:
                universe.append((p, "explicit", None))

    for pair, source, rsi_hint in universe:
        row = PairKnifeRow(pair=pair, rsi=rsi_hint, source=source)
        closes: Sequence[float]
        err: Optional[str] = None
        if closes_by_pair and pair in closes_by_pair:
            closes = list(closes_by_pair[pair])
        else:
            closes, err = try_fetch_closes(pair)
        if err and not closes:
            row.error = err
            rows.append(row)
            continue
        row.closes_n = len(closes)
        if row.rsi is None:
            row.rsi = load_rsi_for_pair(pair)
        # optional: skip if rsi known and not washed (still score structure)
        wash_idx = find_wash_index(closes)
        row.wash_idx = wash_idx
        elev = elev_primary_from_closes(closes)
        row.arms = evaluate_arms_on_closes(
            closes, wash_idx=wash_idx, elev_primary=elev, cfg=cfg
        )
        rows.append(row)

    table = summarize_arm_table(rows)
    plain = _plain_english(rows, table, cfg)
    summary: Dict[str, Any] = {
        "kind": "knife_filter_shadow",
        "ts": _iso(),
        "live_gate": bool(cfg.live_gate),
        "paid_x": bool(cfg.paid_x),
        "claim_class": "ATTENTION_ONLY_knife_filter",
        "config": asdict(cfg),
        "n_pairs": len(rows),
        "arm_table": table,
        "rows": [r.to_dict() for r in rows],
        "plain_english": plain,
        "must_not": [
            "no_orders",
            "no_live_buy_block",
            "no_knob_change",
            "no_promote",
        ],
    }
    if write:
        _write_json(LATEST, summary)
        _append_jsonl(
            CRUMBS,
            {
                "ts": summary["ts"],
                "kind": "knife_filter_shadow_tick",
                "n_pairs": summary["n_pairs"],
                "arm_table": table,
                "plain_english": plain,
            },
        )
        _write_md(summary)
    return summary


def _plain_english(
    rows: Sequence[PairKnifeRow],
    table: Dict[str, Dict[str, Any]],
    cfg: KnifeConfig,
) -> str:
    bits = [
        f"Knife filter shadow · n_pairs={len(rows)} · live_gate={cfg.live_gate}",
    ]
    for arm in ARMS:
        t = table.get(arm) or {}
        bits.append(
            f"{arm}: allow={t.get('n_allow')} sl={t.get('n_sl')} "
            f"sl_rate={t.get('sl_rate')} mean_r_net={t.get('mean_r_net')} [{t.get('claim')}]"
        )
    # top conflicts: rsi_only allow but reclaim deny
    conflict = 0
    for r in rows:
        a0 = (r.arms or {}).get("rsi_only") or {}
        a1 = (r.arms or {}).get("rsi_reclaim") or {}
        if a0.get("allow") and not a1.get("allow"):
            conflict += 1
    bits.append(f"rsi_only_without_reclaim={conflict}")
    return " | ".join(bits)


def _write_md(summary: Dict[str, Any]) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Knife Filter Shadow — LATEST",
        "",
        f"- **ts:** {summary.get('ts')}",
        f"- **claim:** `{summary.get('claim_class')}`",
        f"- **live_gate:** {summary.get('live_gate')} · **paid_x:** {summary.get('paid_x')}",
        f"- **n_pairs:** {summary.get('n_pairs')}",
        "",
        "## Plain English",
        "",
        str(summary.get("plain_english") or ""),
        "",
        "## Arm table",
        "",
        "| Arm | n_allow | n_sl | sl_rate | mean_r_net | claim |",
        "|-----|---------|------|---------|------------|-------|",
    ]
    for arm in ARMS:
        t = (summary.get("arm_table") or {}).get(arm) or {}
        lines.append(
            f"| {arm} | {t.get('n_allow')} | {t.get('n_sl')} | {t.get('sl_rate')} | "
            f"{t.get('mean_r_net')} | {t.get('claim')} |"
        )
    lines.extend(
        [
            "",
            "## Must not",
            "",
            "- No orders / no live buy block / no knobs / no promote",
            "",
            f"State: `{LATEST}`",
            "",
        ]
    )
    MD_PATH.write_text("\n".join(lines))


def telegram_summary(summary: Dict[str, Any]) -> str:
    return str(summary.get("plain_english") or "knife_filter_shadow empty")
