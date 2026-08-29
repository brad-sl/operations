"""Miss-fire probation for promote / intake (ledger-backed).

Miss-fire = pair *qualified* (bought) but never exploded (little/no TP/rotation),
then dug a hole (stop-loss dominated, net red).

Distinct from discovery "duds" (pre-screened by energy/pump brakes). This layer
uses **realized trade history** after first contact.

Default: enforce on promote + membership intake; shadow-tag everywhere.
No orders. No auto config apply.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from phase6.core.paths import PROJECT_ROOT

SCHEMA = "missfire_probation_v1"
LEDGER_PATH = PROJECT_ROOT / "trades" / "phase6_trades.jsonl"
LATEST_PATH = PROJECT_ROOT / "data/state/missfire_probation_latest.json"
STICKY_CORE = frozenset({"BTC-USD", "ETH-USD", "PAXG-USD"})

# --- thresholds (Brad 2026-08-28: miss-fire = launch, no explode, dig hole) ---
LOOKBACK_DAYS = 45.0
FAST_HOLE_HOURS = 2.0
# Fast hole: same-session / quick SL after buy
MIN_FAST_HOLES = 2  # ≥2 fast SL → probation
# Dig hole: repeated SL, almost no winners, net red
MIN_RT_FOR_DIG = 3
MIN_SL_RATE_DIG = 0.67
MAX_TP_RATE_DIG = 0.20  # "never explode"
# Single brutal first contact (n small but ugly)
MIN_FAST_HOLES_SINGLE_CLASS = 1  # with n_rt>=2 and net<0 and tp==0


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(s: Any) -> Optional[datetime]:
    if not s:
        return None
    t = str(s).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(t)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _norm_pair(p: str) -> str:
    s = str(p or "").strip().upper().replace("_", "-")
    if not s:
        return ""
    if "-" not in s:
        s = f"{s}-USD"
    return s


def _load_ledger_rows(path: Path = LEDGER_PATH) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    try:
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return out


@dataclass
class PairMissfireStats:
    pair: str
    n_rt: int = 0
    n_sl: int = 0
    n_tp_or_rot: int = 0
    n_fast_hole: int = 0  # SL within FAST_HOLE_HOURS, pnl<=0
    n_slow_hole: int = 0  # SL after FAST_HOLE_HOURS, pnl<=0
    net_pnl: float = 0.0
    sl_rate: float = 0.0
    tp_rate: float = 0.0
    med_hold_h: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MissfireVerdict:
    pair: str
    blocked: bool
    class_: str = "clear"  # clear | fast_hole | dig_hole | sticky_exempt
    reasons: List[str] = field(default_factory=list)
    stats: Optional[Dict[str, Any]] = None
    enforce: bool = True

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["class"] = d.pop("class_", "clear")
        return d


def _round_trips(
    rows: Sequence[Dict[str, Any]],
    *,
    since: datetime,
) -> Dict[str, List[Dict[str, Any]]]:
    """BUY→next SELL pairs after `since` (by buy time)."""
    by: Dict[str, List[Tuple[datetime, Dict[str, Any]]]] = {}
    for r in rows:
        ts = _parse_ts(r.get("timestamp") or r.get("ts"))
        if ts is None or ts < since:
            continue
        pair = _norm_pair(str(r.get("pair") or ""))
        if not pair:
            continue
        by.setdefault(pair, []).append((ts, r))

    out: Dict[str, List[Dict[str, Any]]] = {}
    for pair, evs in by.items():
        evs = sorted(evs, key=lambda x: x[0])
        buys = [(t, r) for t, r in evs if str(r.get("side") or "").upper() == "BUY"]
        sells = [(t, r) for t, r in evs if str(r.get("side") or "").upper() == "SELL"]
        if not buys:
            continue
        si = 0
        rts: List[Dict[str, Any]] = []
        for bt, br in buys:
            matched = None
            for j in range(si, len(sells)):
                st, sr = sells[j]
                if st >= bt:
                    matched = (st, sr)
                    si = j + 1
                    break
            if not matched:
                continue
            st, sr = matched
            reason = str(sr.get("exit_reason") or sr.get("reason") or "")
            try:
                pnl = float(sr.get("pnl") if sr.get("pnl") is not None else 0.0)
            except (TypeError, ValueError):
                pnl = 0.0
            hold_h = (st - bt).total_seconds() / 3600.0
            rts.append(
                {
                    "buy_ts": bt.isoformat(),
                    "sell_ts": st.isoformat(),
                    "hold_h": hold_h,
                    "pnl": pnl,
                    "reason": reason,
                }
            )
        if rts:
            out[pair] = rts
    return out


def compute_pair_stats(
    rows: Optional[Sequence[Dict[str, Any]]] = None,
    *,
    lookback_days: float = LOOKBACK_DAYS,
    now: Optional[datetime] = None,
) -> Dict[str, PairMissfireStats]:
    now = now or _utc_now()
    since = now - timedelta(days=float(lookback_days))
    rows = list(rows) if rows is not None else _load_ledger_rows()
    rts_by = _round_trips(rows, since=since)
    stats: Dict[str, PairMissfireStats] = {}
    for pair, rts in rts_by.items():
        n = len(rts)
        n_sl = 0
        n_tp = 0
        n_fast = 0
        n_slow = 0
        net = 0.0
        holds: List[float] = []
        for rt in rts:
            pnl = float(rt["pnl"])
            net += pnl
            hold = float(rt["hold_h"])
            holds.append(hold)
            low = str(rt["reason"]).lower()
            is_sl = "stop_loss" in low
            is_tp = ("take_profit" in low) or ("rotation" in low)
            if is_sl:
                n_sl += 1
                if pnl <= 0:
                    if hold <= FAST_HOLE_HOURS:
                        n_fast += 1
                    else:
                        n_slow += 1
            if is_tp:
                n_tp += 1
        holds_s = sorted(holds)
        med = holds_s[len(holds_s) // 2] if holds_s else None
        stats[pair] = PairMissfireStats(
            pair=pair,
            n_rt=n,
            n_sl=n_sl,
            n_tp_or_rot=n_tp,
            n_fast_hole=n_fast,
            n_slow_hole=n_slow,
            net_pnl=round(net, 4),
            sl_rate=round(n_sl / n, 4) if n else 0.0,
            tp_rate=round(n_tp / n, 4) if n else 0.0,
            med_hold_h=round(med, 3) if med is not None else None,
        )
    return stats


def evaluate_pair_missfire(
    pair: str,
    *,
    stats_map: Optional[Dict[str, PairMissfireStats]] = None,
    enforce: bool = True,
    sticky: Optional[Iterable[str]] = None,
) -> MissfireVerdict:
    """Return probation verdict for an ADD / new-buy candidate."""
    p = _norm_pair(pair)
    sticky_set = set(sticky) if sticky is not None else set(STICKY_CORE)
    if p in sticky_set:
        return MissfireVerdict(
            pair=p,
            blocked=False,
            class_="sticky_exempt",
            reasons=["sticky_core_exempt"],
            enforce=enforce,
        )

    smap = stats_map if stats_map is not None else compute_pair_stats()
    st = smap.get(p)
    if st is None or st.n_rt <= 0:
        return MissfireVerdict(
            pair=p,
            blocked=False,
            class_="clear",
            reasons=["no_ledger_history"],
            stats=None,
            enforce=enforce,
        )

    reasons: List[str] = []
    class_ = "clear"

    # Fast hole: launch → immediate ground
    if st.n_fast_hole >= MIN_FAST_HOLES:
        class_ = "fast_hole"
        reasons.append(
            f"fast_hole n={st.n_fast_hole} (BUY→SL ≤{FAST_HOLE_HOURS:.0f}h)"
        )
    elif (
        st.n_fast_hole >= MIN_FAST_HOLES_SINGLE_CLASS
        and st.n_rt >= 2
        and st.net_pnl < 0
        and st.n_tp_or_rot == 0
    ):
        class_ = "fast_hole"
        reasons.append(
            f"fast_hole_single_class n_fast={st.n_fast_hole} n_rt={st.n_rt} "
            f"net={st.net_pnl:.2f} tp=0"
        )

    # Dig hole: launched, never exploded, repeated SL, net red
    if (
        st.n_rt >= MIN_RT_FOR_DIG
        and st.sl_rate >= MIN_SL_RATE_DIG
        and st.tp_rate <= MAX_TP_RATE_DIG
        and st.net_pnl < 0
    ):
        if class_ == "clear":
            class_ = "dig_hole"
        reasons.append(
            f"dig_hole sl_rate={st.sl_rate:.0%} tp_rate={st.tp_rate:.0%} "
            f"net={st.net_pnl:.2f} n={st.n_rt}"
        )

    blocked = bool(reasons) and enforce
    if not reasons:
        reasons.append("clear")
    return MissfireVerdict(
        pair=p,
        blocked=blocked,
        class_=class_ if reasons and reasons[0] != "clear" else "clear",
        reasons=reasons,
        stats=st.to_dict(),
        enforce=enforce,
    )


def probation_block_pairs(
    *,
    stats_map: Optional[Dict[str, PairMissfireStats]] = None,
    enforce: bool = True,
) -> Set[str]:
    smap = stats_map if stats_map is not None else compute_pair_stats()
    out: Set[str] = set()
    for pair in smap:
        v = evaluate_pair_missfire(pair, stats_map=smap, enforce=enforce)
        if v.blocked:
            out.add(v.pair)
    return out


def annotate_swap(
    swap: Dict[str, Any],
    *,
    stats_map: Optional[Dict[str, PairMissfireStats]] = None,
    enforce: bool = True,
) -> Dict[str, Any]:
    """Attach missfire_probation fields; mark membership fail if blocked."""
    sw = dict(swap)
    add = _norm_pair(str(sw.get("add") or ""))
    v = evaluate_pair_missfire(add, stats_map=stats_map, enforce=enforce)
    sw["missfire_probation"] = v.to_dict()
    sw["missfire_probation_ok"] = not v.blocked
    if v.blocked:
        sw["missfire_blocked"] = True
        tag = f"missfire_probation={v.class_}:{','.join(v.reasons[:3])}"
        sw["reason"] = (sw.get("reason") or "") + f" | {tag}"
        # Align with membership gate consumers
        if sw.get("membership_potential_ok") is True:
            sw["membership_potential_ok"] = False
        mp = dict(sw.get("membership_potential") or {})
        if mp:
            mp["ok"] = False
            mp["layer_failed"] = mp.get("layer_failed") or "M4"
            rs = list(mp.get("reasons") or [])
            rs.extend([f"M4:{r}" for r in v.reasons[:4]])
            mp["reasons"] = rs
            sw["membership_potential"] = mp
    return sw


def build_board(
    *,
    persist: bool = True,
    lookback_days: float = LOOKBACK_DAYS,
) -> Dict[str, Any]:
    smap = compute_pair_stats(lookback_days=lookback_days)
    verdicts = {
        p: evaluate_pair_missfire(p, stats_map=smap, enforce=True).to_dict()
        for p in sorted(smap.keys())
    }
    blocked = sorted(p for p, v in verdicts.items() if v.get("blocked"))
    board = {
        "schema": SCHEMA,
        "as_of": _utc_now().isoformat(),
        "lookback_days": lookback_days,
        "thresholds": {
            "fast_hole_hours": FAST_HOLE_HOURS,
            "min_fast_holes": MIN_FAST_HOLES,
            "min_rt_dig": MIN_RT_FOR_DIG,
            "min_sl_rate_dig": MIN_SL_RATE_DIG,
            "max_tp_rate_dig": MAX_TP_RATE_DIG,
        },
        "blocked_pairs": blocked,
        "verdicts": verdicts,
        "stats": {p: s.to_dict() for p, s in smap.items()},
        "note": (
            "Miss-fire = qualified fill that never exploded (low TP) then dug "
            "SL hole. Enforced on promote/intake; sticky BTC/ETH/PAXG exempt."
        ),
    }
    if persist:
        try:
            LATEST_PATH.parent.mkdir(parents=True, exist_ok=True)
            LATEST_PATH.write_text(json.dumps(board, indent=2) + "\n")
        except OSError:
            pass
    return board


def format_board_lines(board: Optional[Dict[str, Any]] = None) -> str:
    b = board or {}
    if not b:
        b = build_board(persist=False)
    lines = [
        "=== Miss-fire probation ===",
        f"Blocked ADD/intake: {', '.join(b.get('blocked_pairs') or ['(none)'])}",
    ]
    for p in b.get("blocked_pairs") or []:
        v = (b.get("verdicts") or {}).get(p) or {}
        lines.append(
            f"• {p}: {v.get('class')} — {'; '.join((v.get('reasons') or [])[:2])}"
        )
    return "\n".join(lines)


def main() -> int:
    board = build_board(persist=True)
    print(format_board_lines(board))
    print(json.dumps({"blocked": board["blocked_pairs"], "n_pairs": len(board.get("stats") or {})}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
