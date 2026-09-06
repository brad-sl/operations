"""Recovery quality_tryout v2 — ledger-backed tryout eligibility.

Role under soft_down / declining equity:
  controlled micro-samples, not full alt reopen.

Layers:
  0 Hard veto — block lists + missfire probation
  1 Tier pool — A ballast (allowlist), B liquid majors, C rest (off by default)
  2 Ledger quality score — this account's realized process
  3 Deploy knobs (sent/RSI/size/rate) stay in regime_cash_policy.evaluate_buy_entry

Shadow scoreboard is always safe. Live path only when
  new_alt_policy startswith quality_tryout_v2  OR  quality_tryout.v2_dynamic=true
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from phase6.core.paths import PROJECT_ROOT, load_trading_basket

SCHEMA = "recovery_tryout_qualify_v2"
LEDGER_PATH = PROJECT_ROOT / "trades" / "phase6_trades.jsonl"
STATE_PATH = PROJECT_ROOT / "data" / "state" / "recovery_tryout_scoreboard_latest.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "RECOVERY_TRYOUT_SCOREBOARD_LATEST.md"
ARTIFACT_PATH = PROJECT_ROOT / "data" / "state" / "recovery_tryout_v2_20260905.json"

# Defaults (overridable via quality_tryout cfg)
DEFAULT_LOOKBACK_DAYS = 90.0
# True ballast allowlist path only (ETH is tryout-tier B — not on recovery allowlist)
DEFAULT_TIER_A = frozenset(
    {"BTC-USD", "BTC-USDC", "PAXG-USD", "PAXG-USDC", "USDC-USD", "USD-USD"}
)
# Liquid majors tryout candidates (not automatic pass — ledger still binds)
DEFAULT_TIER_B = frozenset({"ETH-USD", "ETH-USDC", "LINK-USD", "SOL-USD", "XRP-USD"})
DEFAULT_MIN_NET = 0.0
DEFAULT_MIN_RT_GRAD = 3
DEFAULT_MAX_SL_RATE = 0.50
DEFAULT_MIN_TP_RATE = 0.15
DEFAULT_MIN_RT_FOR_RATES = 5
DEFAULT_ALLOW_TIER_C = False
DEFAULT_ALLOW_FIRST_FILL_TIER_B = True  # no/low history majors: first-fill path only


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


def _norm_set(xs: Any) -> Set[str]:
    out: Set[str] = set()
    if not xs:
        return out
    if isinstance(xs, (str, bytes)):
        xs = [xs]
    for x in xs:
        n = _norm_pair(str(x))
        if n:
            out.add(n)
    return out


def load_v2_cfg(rec: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Normalize quality_tryout / v2 knobs from recovery operator_override block."""
    rec = rec if isinstance(rec, dict) else {}
    qt = rec.get("quality_tryout") if isinstance(rec.get("quality_tryout"), dict) else {}
    v2 = qt.get("v2") if isinstance(qt.get("v2"), dict) else {}
    # merge flat qt + nested v2 (v2 wins)
    src = {**qt, **v2}

    tier_a = _norm_set(src.get("tier_a") or src.get("allowlist_pairs") or DEFAULT_TIER_A)
    if not tier_a:
        tier_a = set(DEFAULT_TIER_A)
    # ballast allowlist from recovery still counts as A
    tier_a |= _norm_set(rec.get("allowlist_pairs"))

    tier_b = _norm_set(src.get("tier_b") or DEFAULT_TIER_B)
    if not tier_b:
        tier_b = set(DEFAULT_TIER_B)

    return {
        "lookback_days": float(src.get("lookback_days", DEFAULT_LOOKBACK_DAYS) or DEFAULT_LOOKBACK_DAYS),
        "tier_a": tier_a,
        "tier_b": tier_b,
        "allow_tier_c": bool(src.get("allow_tier_c", DEFAULT_ALLOW_TIER_C)),
        "allow_first_fill_tier_b": bool(
            src.get("allow_first_fill_tier_b", DEFAULT_ALLOW_FIRST_FILL_TIER_B)
        ),
        "min_net_pnl": float(src.get("min_net_pnl", DEFAULT_MIN_NET) or 0.0),
        "min_rt_graduated": int(src.get("min_rt_graduated", DEFAULT_MIN_RT_GRAD) or DEFAULT_MIN_RT_GRAD),
        "max_sl_rate": float(src.get("max_sl_rate", DEFAULT_MAX_SL_RATE) or DEFAULT_MAX_SL_RATE),
        "min_tp_rate": float(src.get("min_tp_rate", DEFAULT_MIN_TP_RATE) or DEFAULT_MIN_TP_RATE),
        "min_rt_for_rates": int(
            src.get("min_rt_for_rates", DEFAULT_MIN_RT_FOR_RATES) or DEFAULT_MIN_RT_FOR_RATES
        ),
        "hard_block": _norm_set(
            src.get("hard_block")
            or rec.get("block_new_buy_pairs")
            or ["UNI-USD", "RAVE-USD"]
        ),
        # legacy static list kept for shadow compare
        "legacy_tryout_pairs": _norm_set(qt.get("tryout_pairs") or ["ETH-USD", "LINK-USD"]),
        "min_sentiment": float(src.get("min_sentiment", qt.get("min_sentiment", 0.30)) or 0.30),
        "max_rsi": float(src.get("max_rsi", qt.get("max_rsi", 55.0)) or 55.0),
        "max_new_seats_per_day": int(
            src.get("max_new_seats_per_day", qt.get("max_new_seats_per_day", 1)) or 1
        ),
        "abs_cap_usd": float(src.get("abs_cap_usd", qt.get("abs_cap_usd", 75.0)) or 75.0),
        "live_apply": bool(src.get("live_apply", False)),
        "v2_dynamic": bool(src.get("v2_dynamic", False)),
    }


def _load_ledger_rows(path: Path = LEDGER_PATH) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
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


def _is_sl_exit(row: Dict[str, Any]) -> bool:
    reason = str(
        row.get("reason")
        or row.get("exit_reason")
        or row.get("done_reason")
        or ""
    ).lower()
    if row.get("stop_loss") or row.get("sl_fill"):
        return True
    return any(
        k in reason
        for k in ("stop_loss", "stop-loss", "sl_", "exchange_stop", "stop_loss_exchange", "sl_hit")
    )


def _is_tp_exit(row: Dict[str, Any]) -> bool:
    reason = str(row.get("reason") or row.get("exit_reason") or "").lower()
    return any(
        k in reason
        for k in ("take_profit", "fixed_tp", "trail", "tp_", "lifecycle_tp", "dual_peak")
    )


@dataclass
class PairLedgerStats:
    pair: str
    n_sell: int = 0
    n_sl: int = 0
    n_tp: int = 0
    net_pnl: float = 0.0
    sl_rate: float = 0.0
    tp_rate: float = 0.0
    n_buy: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compute_pair_ledger_stats(
    rows: Sequence[Dict[str, Any]],
    *,
    pair: str,
    since: datetime,
) -> PairLedgerStats:
    p = _norm_pair(pair)
    st = PairLedgerStats(pair=p)
    for row in rows:
        ts = _parse_ts(row.get("timestamp") or row.get("ts"))
        if ts is None or ts < since:
            continue
        rp = _norm_pair(str(row.get("pair") or ""))
        if rp != p:
            continue
        side = str(row.get("side") or row.get("action") or "").upper()
        if side == "BUY":
            st.n_buy += 1
            continue
        if side != "SELL":
            continue
        pnl = row.get("pnl")
        if pnl is None:
            pnl = row.get("realized_pnl")
        try:
            pnl_f = float(pnl) if pnl is not None else 0.0
        except (TypeError, ValueError):
            pnl_f = 0.0
        st.n_sell += 1
        st.net_pnl += pnl_f
        if _is_sl_exit(row) or pnl_f < 0 and "stop" in str(row.get("reason") or "").lower():
            st.n_sl += 1
        if _is_tp_exit(row) or (pnl_f > 0 and "tp" in str(row.get("reason") or "").lower()):
            st.n_tp += 1
    if st.n_sell > 0:
        st.sl_rate = st.n_sl / st.n_sell
        st.tp_rate = st.n_tp / st.n_sell
    return st


@dataclass
class TryoutVerdict:
    pair: str
    tier: str  # A | B | C | outside
    eligible_tryout: bool
    ledger_ok: bool
    first_fill_path: bool
    score: float
    class_: str
    reasons: List[str] = field(default_factory=list)
    stats: Optional[Dict[str, Any]] = None
    missfire_blocked: bool = False
    hard_blocked: bool = False
    in_legacy_list: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["class"] = d.pop("class_", "unknown")
        return d


def _tier_of(pair: str, cfg: Dict[str, Any], basket: Set[str]) -> str:
    p = _norm_pair(pair)
    if p in cfg["tier_a"]:
        return "A"
    if p in cfg["tier_b"]:
        return "B"
    if p in basket:
        return "C"
    return "outside"


def _ledger_ok(st: PairLedgerStats, cfg: Dict[str, Any]) -> Tuple[bool, float, str, List[str]]:
    """Return (ok, score 0..1, class, reasons)."""
    reasons: List[str] = []
    # No / thin history → first-fill path (caller decides if allowed)
    if st.n_sell < 2:
        score = 0.35 if st.n_buy > 0 or st.n_sell == 1 else 0.25
        return False, score, "thin_history", ["thin_history n_sell<%d" % 2]

    score = 0.0
    # Net component
    if st.net_pnl >= cfg["min_net_pnl"]:
        score += 0.45
        reasons.append(f"net_ok {st.net_pnl:.2f}")
    else:
        reasons.append(f"net_red {st.net_pnl:.2f}")

    # Rate component when enough samples
    if st.n_sell >= cfg["min_rt_for_rates"]:
        if st.sl_rate <= cfg["max_sl_rate"]:
            score += 0.25
            reasons.append(f"sl_rate_ok {st.sl_rate:.2f}")
        else:
            reasons.append(f"sl_rate_high {st.sl_rate:.2f}")
        if st.tp_rate >= cfg["min_tp_rate"]:
            score += 0.30
            reasons.append(f"tp_rate_ok {st.tp_rate:.2f}")
        else:
            reasons.append(f"tp_rate_low {st.tp_rate:.2f}")
    else:
        # graduated-ish with fewer sells: require non-negative net + not all SL
        if st.n_sell >= cfg["min_rt_graduated"] and st.net_pnl >= cfg["min_net_pnl"]:
            if st.sl_rate < 1.0:
                score += 0.35
                reasons.append("grad_small_n net_ok")
            else:
                reasons.append("grad_small_n all_sl")
        else:
            reasons.append(f"n_sell={st.n_sell} need_rates_or_grad")

    # Pass rules (any):
    # 1) net >= 0, n >= min_rt_graduated, sl_rate <= max_sl_rate
    # 2) n >= min_rt_for_rates and sl_rate <= max and tp_rate >= min
    # 3) n >= min_rt_for_rates and net >= 0 and sl_rate <= max
    ok = False
    cls = "ledger_fail"
    if (
        st.n_sell >= cfg["min_rt_graduated"]
        and st.net_pnl >= cfg["min_net_pnl"]
        and st.sl_rate <= cfg["max_sl_rate"]
    ):
        ok = True
        cls = "ledger_pass_net"
    if st.n_sell >= cfg["min_rt_for_rates"]:
        if st.sl_rate <= cfg["max_sl_rate"] and st.tp_rate >= cfg["min_tp_rate"]:
            ok = True
            cls = "ledger_pass_rates"
        elif st.net_pnl >= cfg["min_net_pnl"] and st.sl_rate <= cfg["max_sl_rate"]:
            ok = True
            cls = "ledger_pass_net_sl"
    if not ok:
        cls = "ledger_fail"
    score = max(0.0, min(1.0, score))
    return ok, score, cls, reasons


def evaluate_pair_tryout(
    pair: str,
    *,
    cfg: Optional[Dict[str, Any]] = None,
    rec: Optional[Dict[str, Any]] = None,
    basket: Optional[Iterable[str]] = None,
    ledger_rows: Optional[Sequence[Dict[str, Any]]] = None,
    missfire_fn: Any = None,
) -> TryoutVerdict:
    cfg = cfg or load_v2_cfg(rec)
    p = _norm_pair(pair)
    basket_set = _norm_set(basket if basket is not None else load_trading_basket())
    tier = _tier_of(p, cfg, basket_set)
    reasons: List[str] = []

    hard = p in cfg["hard_block"]
    if hard:
        return TryoutVerdict(
            pair=p,
            tier=tier,
            eligible_tryout=False,
            ledger_ok=False,
            first_fill_path=False,
            score=0.0,
            class_="hard_block",
            reasons=[f"hard_block {p}"],
            hard_blocked=True,
            in_legacy_list=p in cfg["legacy_tryout_pairs"],
        )

    # Missfire
    mf_blocked = False
    mf_reason = ""
    try:
        if missfire_fn is None:
            from phase6.core.missfire_probation import evaluate_pair_missfire

            missfire_fn = evaluate_pair_missfire
        mf = missfire_fn(p, enforce=True)
        mf_blocked = bool(getattr(mf, "blocked", False) or (isinstance(mf, dict) and mf.get("blocked")))
        if mf_blocked:
            mf_reason = str(
                (getattr(mf, "reasons", None) or (mf.get("reasons") if isinstance(mf, dict) else None) or ["missfire"])[0]
            )
    except Exception as e:
        reasons.append(f"missfire_check_error:{e}")

    if mf_blocked:
        return TryoutVerdict(
            pair=p,
            tier=tier,
            eligible_tryout=False,
            ledger_ok=False,
            first_fill_path=False,
            score=0.0,
            class_="missfire",
            reasons=[f"missfire {mf_reason}"],
            missfire_blocked=True,
            in_legacy_list=p in cfg["legacy_tryout_pairs"],
        )

    # Tier A = ballast allowlist path (not tryout seat scoring for "new alt")
    if tier == "A":
        return TryoutVerdict(
            pair=p,
            tier=tier,
            eligible_tryout=False,  # opens via allowlist, not tryout sleeve
            ledger_ok=True,
            first_fill_path=False,
            score=1.0,
            class_="ballast_allowlist",
            reasons=["tier_A_ballast_use_allowlist"],
            in_legacy_list=p in cfg["legacy_tryout_pairs"],
        )

    if tier == "outside":
        return TryoutVerdict(
            pair=p,
            tier=tier,
            eligible_tryout=False,
            ledger_ok=False,
            first_fill_path=False,
            score=0.0,
            class_="outside_basket",
            reasons=["not_in_trading_basket"],
            in_legacy_list=p in cfg["legacy_tryout_pairs"],
        )

    if tier == "C" and not cfg["allow_tier_c"]:
        return TryoutVerdict(
            pair=p,
            tier=tier,
            eligible_tryout=False,
            ledger_ok=False,
            first_fill_path=False,
            score=0.0,
            class_="tier_c_off",
            reasons=["tier_C_requires_brad_go_or_allow_tier_c"],
            in_legacy_list=p in cfg["legacy_tryout_pairs"],
        )

    # Ledger
    rows = list(ledger_rows) if ledger_rows is not None else _load_ledger_rows()
    since = _utc_now() - timedelta(days=float(cfg["lookback_days"]))
    st = compute_pair_ledger_stats(rows, pair=p, since=since)
    ok, score, cls, led_reasons = _ledger_ok(st, cfg)
    reasons.extend(led_reasons)

    first_fill = st.n_sell < 2
    eligible = False
    out_cls = cls

    if ok:
        eligible = True
        out_cls = cls
        reasons.append("ledger_qualified")
    elif first_fill and tier == "B" and cfg["allow_first_fill_tier_b"]:
        eligible = True
        out_cls = "first_fill_tier_b"
        score = max(score, 0.40)
        reasons.append("first_fill_path_tier_B")
    else:
        eligible = False
        out_cls = cls if cls != "thin_history" else "ledger_fail_or_thin"
        reasons.append("not_ledger_qualified")

    return TryoutVerdict(
        pair=p,
        tier=tier,
        eligible_tryout=bool(eligible),
        ledger_ok=bool(ok),
        first_fill_path=bool(first_fill and eligible),
        score=float(score),
        class_=out_cls,
        reasons=reasons,
        stats=st.to_dict(),
        in_legacy_list=p in cfg["legacy_tryout_pairs"],
    )


def evaluate_basket_tryout(
    *,
    rec: Optional[Dict[str, Any]] = None,
    basket: Optional[Sequence[str]] = None,
    ledger_path: Optional[Path] = None,
) -> Dict[str, Any]:
    cfg = load_v2_cfg(rec)
    basket_list = list(basket) if basket is not None else list(load_trading_basket())
    rows = _load_ledger_rows(ledger_path or LEDGER_PATH)
    verdicts: List[TryoutVerdict] = []
    for p in basket_list:
        verdicts.append(
            evaluate_pair_tryout(
                p,
                cfg=cfg,
                rec=rec,
                basket=basket_list,
                ledger_rows=rows,
            )
        )
    # Also score tier_b names not in basket (info only)
    for p in sorted(cfg["tier_b"]):
        if _norm_pair(p) not in {_norm_pair(x) for x in basket_list}:
            v = evaluate_pair_tryout(p, cfg=cfg, rec=rec, basket=basket_list, ledger_rows=rows)
            v.reasons = list(v.reasons) + ["not_in_active_basket"]
            v.eligible_tryout = False
            verdicts.append(v)

    eligible = sorted(
        [v.pair for v in verdicts if v.eligible_tryout and v.tier in ("B", "C")],
        key=lambda x: (-next(v.score for v in verdicts if v.pair == x), x),
    )
    legacy = sorted(cfg["legacy_tryout_pairs"])
    return {
        "schema": SCHEMA,
        "as_of": _utc_now().isoformat(),
        "lookback_days": cfg["lookback_days"],
        "cfg": {
            **{k: (sorted(v) if isinstance(v, set) else v) for k, v in cfg.items()},
        },
        "eligible_tryout_pairs": eligible,
        "legacy_tryout_pairs": legacy,
        "delta_vs_legacy": {
            "added_by_v2": sorted(set(eligible) - set(legacy)),
            "removed_vs_legacy": sorted(set(legacy) - set(eligible)),
            "same": sorted(set(eligible) & set(legacy)),
        },
        "verdicts": [v.to_dict() for v in verdicts],
        "plain_english": _plain_english(eligible, legacy, verdicts, cfg),
        "live_apply": bool(cfg.get("live_apply")),
        "note": (
            "eligible_tryout_pairs = Layer1–2 passers for NEW alt seats. "
            "Tier A uses ballast allowlist. Deploy still needs sent/RSI/size/rate (Layer 3)."
        ),
    }


def _plain_english(
    eligible: List[str],
    legacy: List[str],
    verdicts: List[TryoutVerdict],
    cfg: Dict[str, Any],
) -> str:
    bits = [
        f"v2 tryout eligible: {', '.join(eligible) or '(none)'}",
        f"legacy static: {', '.join(legacy) or '(none)'}",
    ]
    fails = [
        v
        for v in verdicts
        if v.tier == "B"
        and not v.eligible_tryout
        and "not_in_active_basket" not in (v.reasons or [])
    ]
    if fails:
        bits.append(
            "tier_B blocked: "
            + ", ".join(f"{v.pair}({v.class_})" for v in fails[:6])
        )
    bits.append(
        f"tier_C={'on' if cfg.get('allow_tier_c') else 'off'} · "
        f"live_apply={bool(cfg.get('live_apply'))}"
    )
    return " · ".join(bits)


def is_tryout_eligible(
    pair: str,
    *,
    rec: Optional[Dict[str, Any]] = None,
    board: Optional[Dict[str, Any]] = None,
) -> bool:
    """Fast check used by regime_cash_policy. Prefer fresh evaluate; board cache optional."""
    p = _norm_pair(pair)
    if board and isinstance(board.get("eligible_tryout_pairs"), list):
        elig = {_norm_pair(x) for x in board["eligible_tryout_pairs"]}
        if p in elig:
            return True
        # if board present and pair scored not eligible, trust board for speed
        for v in board.get("verdicts") or []:
            if _norm_pair(str(v.get("pair") or "")) == p:
                return bool(v.get("eligible_tryout"))
    v = evaluate_pair_tryout(p, rec=rec)
    return bool(v.eligible_tryout)


def write_scoreboard(
    *,
    rec: Optional[Dict[str, Any]] = None,
    state_path: Path = STATE_PATH,
    report_path: Path = REPORT_PATH,
) -> Dict[str, Any]:
    board = evaluate_basket_tryout(rec=rec)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(board, indent=2, default=str) + "\n", encoding="utf-8")
    report_path.write_text(_render_md(board), encoding="utf-8")
    return board


def _render_md(board: Dict[str, Any]) -> str:
    lines = [
        "# Recovery tryout scoreboard (v2)",
        "",
        f"_as_of {board.get('as_of')} · lookback {board.get('lookback_days')}d_",
        "",
        board.get("plain_english") or "",
        "",
        "## Eligible tryout pairs",
        "",
    ]
    elig = board.get("eligible_tryout_pairs") or []
    if elig:
        for p in elig:
            lines.append(f"- **{p}**")
    else:
        lines.append("- _(none)_")
    delta = board.get("delta_vs_legacy") or {}
    lines += [
        "",
        "## vs legacy static list",
        "",
        f"- same: {', '.join(delta.get('same') or []) or '—'}",
        f"- v2 adds: {', '.join(delta.get('added_by_v2') or []) or '—'}",
        f"- v2 drops: {', '.join(delta.get('removed_vs_legacy') or []) or '—'}",
        "",
        "## Verdicts",
        "",
        "| pair | tier | eligible | class | score | net | sl_rate | tp_rate | n_sell |",
        "|------|------|----------|-------|-------|-----|---------|---------|--------|",
    ]
    for v in board.get("verdicts") or []:
        st = v.get("stats") or {}
        lines.append(
            f"| {v.get('pair')} | {v.get('tier')} | {v.get('eligible_tryout')} | "
            f"{v.get('class')} | {float(v.get('score') or 0):.2f} | "
            f"{float(st.get('net_pnl') or 0):.1f} | {float(st.get('sl_rate') or 0):.2f} | "
            f"{float(st.get('tp_rate') or 0):.2f} | {int(st.get('n_sell') or 0)} |"
        )
    lines += [
        "",
        "## Notes",
        "",
        "- Layer 0–2 only. Deploy still needs eng sent / RSI / $75 / max 1 seat/day.",
        "- Tier A = ballast allowlist (not tryout sleeve).",
        "- Tier C off unless `allow_tier_c` + Brad GO.",
        f"- `live_apply={board.get('live_apply')}` — false means shadow scoreboard only for policy mode.",
        "",
    ]
    return "\n".join(lines) + "\n"


def v2_policy_active(rec: Optional[Dict[str, Any]]) -> bool:
    """True when recovery should use dynamic tryout eligibility."""
    if not isinstance(rec, dict):
        return False
    mode = str(rec.get("new_alt_policy") or "")
    if mode.startswith("quality_tryout_v2"):
        return True
    qt = rec.get("quality_tryout") if isinstance(rec.get("quality_tryout"), dict) else {}
    if bool(qt.get("v2_dynamic")) or bool((qt.get("v2") or {}).get("live_apply")):
        # live_apply alone shouldn't flip without mode — require v2_dynamic or mode
        return bool(qt.get("v2_dynamic")) or mode.startswith("quality_tryout_v2")
    return False


__all__ = [
    "SCHEMA",
    "evaluate_pair_tryout",
    "evaluate_basket_tryout",
    "is_tryout_eligible",
    "write_scoreboard",
    "load_v2_cfg",
    "v2_policy_active",
    "TryoutVerdict",
    "PairLedgerStats",
]
