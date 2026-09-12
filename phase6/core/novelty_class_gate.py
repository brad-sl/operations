#!/usr/bin/env python3
"""Novelty class gate for promote / membership shortlist (reversible).

Meme/narrative today ≠ forever ban. Class is time-bounded with graduation + demotion.

Classes
-------
  sticky_core         BTC/ETH/PAXG — always contenders
  liquid_core         known liquid majors allowlist — normal path
  graduated           was novelty; cleared graduation packet — normal path
  novelty_restricted  default non-core unknown — paper/CF OK; auto-rotation blocked
  novelty_blocked     hard pin denylist (operator) — blocked until unpin

Scope
-----
- Shortlist / membership M5 / promote annotate only.
- Does NOT place orders. Does NOT flip live_membership_swaps.
- Brad GO force_eligible / force_graduated is separate and does not auto-write graduated
  unless promote_pair() is called explicitly.

State SSOT: data/state/novelty_class_registry.json
Board:      data/state/novelty_class_latest.json
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from phase6.core.paths import PROJECT_ROOT

logger = logging.getLogger(__name__)

SCHEMA = "novelty_class_gate_v1"
REGISTRY_PATH = PROJECT_ROOT / "data/state/novelty_class_registry.json"
LATEST_PATH = PROJECT_ROOT / "data/state/novelty_class_latest.json"
LEDGER_PATH = PROJECT_ROOT / "trades" / "phase6_trades.jsonl"

STICKY_CORE = frozenset({"BTC-USD", "ETH-USD", "PAXG-USD"})

# Liquid majors — slow-edit allowlist (not meme lottery tickets).
LIQUID_CORE = frozenset(
    {
        "BTC-USD",
        "ETH-USD",
        "PAXG-USD",
        "SOL-USD",
        "XRP-USD",
        "ADA-USD",
        "LINK-USD",
        "DOT-USD",
        "ATOM-USD",
        "NEAR-USD",
        "UNI-USD",
        "AAVE-USD",
        "LTC-USD",
        "BCH-USD",
        "AVAX-USD",
        "APT-USD",
        "SUI-USD",
        "SEI-USD",
        "INJ-USD",
        "OP-USD",
        "ARB-USD",
        "TIA-USD",
        "FIL-USD",
        "ICP-USD",
        "RENDER-USD",
        "FET-USD",
        "LDO-USD",
        "MKR-USD",
        "CRV-USD",
        "DYDX-USD",
        "ALGO-USD",
        "XLM-USD",
        "ETC-USD",
        "ZEC-USD",
        "XMR-USD",
        "KAS-USD",
        "HBAR-USD",
        "VET-USD",
        "IMX-USD",
        "STX-USD",
        "RUNE-USD",
        "GRT-USD",
        "SNX-USD",
        "COMP-USD",
        "YFI-USD",
        "BAL-USD",
        "SUSHI-USD",
        "LPT-USD",
        "BLUR-USD",
        "GMX-USD",
        "PENDLE-USD",
        "JUP-USD",
        "PYTH-USD",
        "WLD-USD",
        "ONDO-USD",
        "ENA-USD",
        "EIGEN-USD",
        "STRK-USD",
        "ZK-USD",
        "POL-USD",
        "MATIC-USD",
        "BNB-USD",
        "TRX-USD",
        "TON-USD",
        "DOGE-USD",  # dual: liquid enough; not hard-blocked
        "SHIB-USD",
    }
)

# Seed restricted novelty (toxic L1 winners / narrative lottery). Not permanent —
# can graduate via packet or Brad promote. Hard pin is separate.
SEED_NOVELTY_RESTRICTED = frozenset(
    {
        "PUMP-USD",
        "USELESS-USD",
        "LIGHTER-USD",
        "SKR-USD",
        "HYPE-USD",
        "TRUMP-USD",
        "RAVE-USD",
        "PENGU-USD",
        "WIF-USD",
        "BONK-USD",
        "PEPE-USD",
        "FLOKI-USD",
        "MOG-USD",
        "MEW-USD",
        "POPCAT-USD",
        "NEIRO-USD",
        "GOAT-USD",
        "PNUT-USD",
        "CHILLGUY-USD",
        "FARTCOIN-USD",
        "MOODENG-USD",
        "GIGA-USD",
        "SPX-USD",
        "BRETT-USD",
        "TOSHI-USD",
        "MEO-USD",
    }
)

# Graduation packet defaults (all must hold for auto-graduate)
MIN_AGE_DAYS = 45.0
MIN_QUOTE_VOL_24H = 5_000_000.0
MAX_RET_24H_T0 = 0.12  # anti-chase at proposal time
MAX_RET_7D_T0 = 0.35
MIN_CLEAN_CF_WINDOWS = 2  # optional external counter on registry
MIN_RT = 3
MAX_SL_RATE_GRAD = 0.55
MIN_TP_OR_ROT_RATE = 0.20
MIN_NET_PNL_GRAD = 0.0

# Demotion (graduated → restricted)
DEMOTE_MIN_RT = 3
DEMOTE_SL_RATE = 0.67
DEMOTE_MAX_TP_RATE = 0.15


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


def _f(x: Any, default: Optional[float] = None) -> Optional[float]:
    if x is None:
        return default
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def empty_registry() -> Dict[str, Any]:
    return {
        "schema": SCHEMA,
        "updated_at": _utc_now().isoformat(),
        "hard_pin_block": [],  # permanent until unpin
        "force_graduated": [],  # Brad GO list (treated as graduated without auto evidence)
        "force_restricted": [],  # operator soft pin (restricted even if liquid)
        "graduated": {},  # pair -> {graduated_at, reasons, source}
        "demoted": {},  # pair -> {demoted_at, reasons, prev_class}
        "first_seen": {},  # pair -> iso ts
        "clean_contacts": {},  # pair -> int count of clean M-ok/CF windows
        "notes": "novelty_class_gate: meme today can graduate later; hard_pin is the only forever ban",
    }


def load_registry(path: Path = REGISTRY_PATH) -> Dict[str, Any]:
    base = empty_registry()
    if not path.exists():
        return base
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return base
    if not isinstance(raw, dict):
        return base
    out = dict(base)
    out.update(raw)
    out["schema"] = SCHEMA
    for k in ("hard_pin_block", "force_graduated", "force_restricted"):
        out[k] = [_norm_pair(x) for x in (out.get(k) or []) if _norm_pair(x)]
    for k in ("graduated", "demoted", "first_seen", "clean_contacts"):
        if not isinstance(out.get(k), dict):
            out[k] = {}
    return out


def save_registry(reg: Dict[str, Any], path: Path = REGISTRY_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(reg)
    payload["schema"] = SCHEMA
    payload["updated_at"] = _utc_now().isoformat()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def touch_first_seen(pair: str, reg: Dict[str, Any], *, now: Optional[datetime] = None) -> Dict[str, Any]:
    p = _norm_pair(pair)
    if not p:
        return reg
    fs = dict(reg.get("first_seen") or {})
    if p not in fs:
        fs[p] = (now or _utc_now()).isoformat()
        reg = dict(reg)
        reg["first_seen"] = fs
    return reg


def record_clean_contact(pair: str, reg: Dict[str, Any], *, n: int = 1) -> Dict[str, Any]:
    p = _norm_pair(pair)
    if not p:
        return reg
    cc = dict(reg.get("clean_contacts") or {})
    cc[p] = int(cc.get(p) or 0) + int(n)
    reg = dict(reg)
    reg["clean_contacts"] = cc
    return reg


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


def _pair_ledger_stats(
    pair: str,
    rows: Sequence[Dict[str, Any]],
    *,
    lookback_days: float = 90.0,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    p = _norm_pair(pair)
    now = now or _utc_now()
    since = now - timedelta(days=lookback_days)
    sells = []
    first_any: Optional[datetime] = None
    for r in rows:
        rp = _norm_pair(str(r.get("pair") or r.get("product_id") or ""))
        if rp != p:
            continue
        ts = _parse_ts(r.get("timestamp") or r.get("ts") or r.get("filled_at"))
        if ts is None:
            continue
        if first_any is None or ts < first_any:
            first_any = ts
        side = str(r.get("side") or r.get("action") or "").lower()
        if side not in ("sell", "exit", "stop", "tp", "rotation"):
            # also accept reason-tagged exits
            reason = str(r.get("reason") or r.get("exit_reason") or "").lower()
            if not any(x in reason for x in ("sl", "stop", "tp", "rotat", "sell")):
                continue
        if ts < since:
            continue
        sells.append(r)

    n_rt = 0
    n_sl = 0
    n_tp = 0
    net = 0.0
    for r in sells:
        reason = str(r.get("reason") or r.get("exit_reason") or r.get("tag") or "").lower()
        pnl = _f(r.get("realized_pnl") or r.get("pnl") or r.get("net_pnl"), 0.0) or 0.0
        # count as RT if sell-like
        n_rt += 1
        net += pnl
        if "sl" in reason or "stop" in reason:
            n_sl += 1
        elif "tp" in reason or "rotat" in reason or "take" in reason:
            n_tp += 1
    sl_rate = (n_sl / n_rt) if n_rt else 0.0
    tp_rate = (n_tp / n_rt) if n_rt else 0.0
    age_days = None
    if first_any is not None:
        age_days = max(0.0, (now - first_any).total_seconds() / 86400.0)
    return {
        "pair": p,
        "n_rt": n_rt,
        "n_sl": n_sl,
        "n_tp_or_rot": n_tp,
        "net_pnl": round(net, 4),
        "sl_rate": round(sl_rate, 4),
        "tp_rate": round(tp_rate, 4),
        "first_ledger_at": first_any.isoformat() if first_any else None,
        "age_days_ledger": age_days,
    }


@dataclass
class NoveltyVerdict:
    pair: str
    class_: str  # sticky_core|liquid_core|graduated|novelty_restricted|novelty_blocked
    blocked: bool  # True => block auto membership / promote shortlist
    reasons: List[str] = field(default_factory=list)
    can_graduate: bool = False
    graduation_reasons: List[str] = field(default_factory=list)
    stats: Optional[Dict[str, Any]] = None
    enforce: bool = True

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["class"] = d.pop("class_", self.class_)
        return d


def resolve_base_class(pair: str, reg: Dict[str, Any]) -> str:
    p = _norm_pair(pair)
    hard = set(reg.get("hard_pin_block") or [])
    if p in hard:
        return "novelty_blocked"
    force_r = set(reg.get("force_restricted") or [])
    if p in force_r:
        return "novelty_restricted"
    if p in STICKY_CORE:
        return "sticky_core"
    force_g = set(reg.get("force_graduated") or [])
    graduated = set((reg.get("graduated") or {}).keys())
    demoted = set((reg.get("demoted") or {}).keys())
    if p in force_g or (p in graduated and p not in demoted):
        # demoted overrides prior graduate until re-graduated
        if p in demoted and p not in force_g:
            pass
        else:
            return "graduated"
    if p in LIQUID_CORE and p not in SEED_NOVELTY_RESTRICTED:
        return "liquid_core"
    if p in SEED_NOVELTY_RESTRICTED or p not in LIQUID_CORE:
        return "novelty_restricted"
    return "novelty_restricted"


def graduation_packet_ok(
    pair: str,
    *,
    reg: Dict[str, Any],
    stats: Dict[str, Any],
    quote_vol_24h: Optional[float] = None,
    ret_24h: Optional[float] = None,
    ret_7d: Optional[float] = None,
    now: Optional[datetime] = None,
    missfire_blocked: Optional[bool] = None,
) -> tuple[bool, List[str]]:
    """All gates must hold for auto-graduation. No single L1 jackpot."""
    p = _norm_pair(pair)
    now = now or _utc_now()
    reasons: List[str] = []
    hard = set(reg.get("hard_pin_block") or [])
    if p in hard:
        return False, ["hard_pin_block"]

    if missfire_blocked is True:
        reasons.append("missfire_blocked")

    # age: registry first_seen or ledger
    age_days = None
    fs = (reg.get("first_seen") or {}).get(p)
    fs_dt = _parse_ts(fs)
    if fs_dt is not None:
        age_days = max(0.0, (now - fs_dt).total_seconds() / 86400.0)
    led_age = _f(stats.get("age_days_ledger"))
    if led_age is not None:
        age_days = max(age_days or 0.0, led_age)
    if age_days is None:
        reasons.append("age_unknown")
    elif age_days < MIN_AGE_DAYS:
        reasons.append(f"age_too_young_{age_days:.1f}d")

    vol = _f(quote_vol_24h)
    if vol is None:
        reasons.append("volume_unknown")
    elif vol < MIN_QUOTE_VOL_24H:
        reasons.append(f"volume_too_low_{vol:.0f}")

    r24 = _f(ret_24h)
    if r24 is not None and r24 > MAX_RET_24H_T0:
        reasons.append(f"extended_24h_{r24:.3f}")
    r7 = _f(ret_7d)
    if r7 is not None and r7 > MAX_RET_7D_T0:
        reasons.append(f"extended_7d_{r7:.3f}")

    contacts = int((reg.get("clean_contacts") or {}).get(p) or 0)
    n_rt = int(stats.get("n_rt") or 0)
    sl_rate = float(stats.get("sl_rate") or 0.0)
    tp_rate = float(stats.get("tp_rate") or 0.0)
    net = float(stats.get("net_pnl") or 0.0)

    # behavior bar: either enough clean CF contacts OR clean ledger RTs
    behavior_ok = False
    if contacts >= MIN_CLEAN_CF_WINDOWS:
        behavior_ok = True
    if n_rt >= MIN_RT and sl_rate <= MAX_SL_RATE_GRAD and tp_rate >= MIN_TP_OR_ROT_RATE and net >= MIN_NET_PNL_GRAD:
        behavior_ok = True
    if not behavior_ok:
        reasons.append(
            f"behavior_thin_contacts={contacts}_rt={n_rt}_sl={sl_rate:.2f}_tp={tp_rate:.2f}_net={net:.2f}"
        )

    ok = not reasons
    if ok:
        reasons.append("graduation_packet_ok")
    return ok, reasons


def should_demote_graduated(
    pair: str,
    *,
    stats: Dict[str, Any],
    missfire_blocked: Optional[bool] = None,
) -> tuple[bool, List[str]]:
    reasons: List[str] = []
    if missfire_blocked is True:
        return True, ["missfire_blocked"]
    n_rt = int(stats.get("n_rt") or 0)
    if n_rt < DEMOTE_MIN_RT:
        return False, ["demote_n_thin"]
    sl_rate = float(stats.get("sl_rate") or 0.0)
    tp_rate = float(stats.get("tp_rate") or 0.0)
    if sl_rate >= DEMOTE_SL_RATE and tp_rate <= DEMOTE_MAX_TP_RATE:
        reasons.append(f"sl_dominated_{sl_rate:.2f}")
    net = float(stats.get("net_pnl") or 0.0)
    if net < 0 and sl_rate >= DEMOTE_SL_RATE:
        reasons.append(f"net_red_{net:.2f}")
    return (len(reasons) > 0), reasons or ["demote_clear"]


def evaluate_pair_novelty(
    pair: str,
    *,
    enforce: bool = True,
    registry: Optional[Dict[str, Any]] = None,
    registry_path: Path = REGISTRY_PATH,
    ledger_path: Path = LEDGER_PATH,
    ledger_rows: Optional[Sequence[Dict[str, Any]]] = None,
    quote_vol_24h: Optional[float] = None,
    ret_24h: Optional[float] = None,
    ret_7d: Optional[float] = None,
    now: Optional[datetime] = None,
    persist_first_seen: bool = False,
    auto_graduate: bool = False,
    auto_demote: bool = False,
    missfire_blocked: Optional[bool] = None,
) -> NoveltyVerdict:
    """Classify pair and decide auto-rotation block.

    blocked=True for novelty_restricted / novelty_blocked when enforce=True.
    graduated/liquid/sticky => not blocked by this gate.
    """
    p = _norm_pair(pair)
    now = now or _utc_now()
    if not p:
        return NoveltyVerdict("", "novelty_blocked", True, reasons=["empty_pair"], enforce=enforce)

    reg = dict(registry if registry is not None else load_registry(registry_path))
    if persist_first_seen:
        reg = touch_first_seen(p, reg, now=now)
        if registry is None:
            save_registry(reg, registry_path)

    rows = list(ledger_rows) if ledger_rows is not None else _load_ledger_rows(ledger_path)
    stats = _pair_ledger_stats(p, rows, now=now)

    if missfire_blocked is None:
        try:
            from phase6.core.missfire_probation import evaluate_pair_missfire

            mf = evaluate_pair_missfire(p, enforce=True)
            missfire_blocked = bool(mf.blocked)
        except Exception:  # noqa: BLE001
            missfire_blocked = None

    base = resolve_base_class(p, reg)
    reasons: List[str] = [f"base:{base}"]
    class_ = base
    can_grad = False
    grad_reasons: List[str] = []

    # Hard block
    if base == "novelty_blocked":
        reasons.append("hard_pin_block")
        return NoveltyVerdict(
            p,
            class_,
            blocked=bool(enforce),
            reasons=reasons,
            stats=stats,
            enforce=enforce,
        )

    # Demotion check for graduated
    if base == "graduated":
        demote, d_reasons = should_demote_graduated(p, stats=stats, missfire_blocked=missfire_blocked)
        if demote:
            reasons.extend([f"demote:{r}" for r in d_reasons])
            class_ = "novelty_restricted"
            if auto_demote:
                demoted = dict(reg.get("demoted") or {})
                demoted[p] = {
                    "demoted_at": now.isoformat(),
                    "reasons": d_reasons,
                    "prev_class": "graduated",
                }
                graduated = dict(reg.get("graduated") or {})
                graduated.pop(p, None)
                reg["demoted"] = demoted
                reg["graduated"] = graduated
                if registry is None:
                    save_registry(reg, registry_path)
                reasons.append("auto_demoted")
        else:
            reasons.append("graduated_hold")
            return NoveltyVerdict(
                p,
                "graduated",
                blocked=False,
                reasons=reasons,
                stats=stats,
                enforce=enforce,
            )

    if class_ in ("sticky_core", "liquid_core"):
        reasons.append("core_path")
        return NoveltyVerdict(
            p,
            class_,
            blocked=False,
            reasons=reasons,
            stats=stats,
            enforce=enforce,
        )

    # novelty_restricted path — check graduation packet
    ok, g_reasons = graduation_packet_ok(
        p,
        reg=reg,
        stats=stats,
        quote_vol_24h=quote_vol_24h,
        ret_24h=ret_24h,
        ret_7d=ret_7d,
        now=now,
        missfire_blocked=missfire_blocked,
    )
    can_grad = ok
    grad_reasons = g_reasons
    reasons.extend([f"grad:{r}" for r in g_reasons])

    if ok and auto_graduate:
        graduated = dict(reg.get("graduated") or {})
        graduated[p] = {
            "graduated_at": now.isoformat(),
            "reasons": g_reasons,
            "source": "auto",
        }
        demoted = dict(reg.get("demoted") or {})
        demoted.pop(p, None)
        reg["graduated"] = graduated
        reg["demoted"] = demoted
        if registry is None:
            save_registry(reg, registry_path)
        class_ = "graduated"
        reasons.append("auto_graduated")
        return NoveltyVerdict(
            p,
            class_,
            blocked=False,
            reasons=reasons,
            can_graduate=True,
            graduation_reasons=grad_reasons,
            stats=stats,
            enforce=enforce,
        )

    blocked = bool(enforce)  # restricted blocks auto-rotation
    return NoveltyVerdict(
        p,
        "novelty_restricted" if class_ != "graduated" else class_,
        blocked=blocked if class_ != "graduated" else False,
        reasons=reasons,
        can_graduate=can_grad,
        graduation_reasons=grad_reasons,
        stats=stats,
        enforce=enforce,
    )


def promote_pair(
    pair: str,
    *,
    reason: str = "brad_go_promote",
    registry_path: Path = REGISTRY_PATH,
    as_force: bool = False,
) -> Dict[str, Any]:
    """Explicit graduate (Brad GO). Does not enable live swaps."""
    p = _norm_pair(pair)
    reg = load_registry(registry_path)
    now = _utc_now().isoformat()
    if as_force:
        fg = list(reg.get("force_graduated") or [])
        if p not in fg:
            fg.append(p)
        reg["force_graduated"] = fg
    graduated = dict(reg.get("graduated") or {})
    graduated[p] = {"graduated_at": now, "reasons": [reason], "source": "brad_go" if as_force else "manual"}
    demoted = dict(reg.get("demoted") or {})
    demoted.pop(p, None)
    fr = [x for x in (reg.get("force_restricted") or []) if x != p]
    reg["graduated"] = graduated
    reg["demoted"] = demoted
    reg["force_restricted"] = fr
    save_registry(reg, registry_path)
    return {"pair": p, "class": "graduated", "reason": reason}


def demote_pair(
    pair: str,
    *,
    reason: str = "brad_go_demote",
    registry_path: Path = REGISTRY_PATH,
    hard_pin: bool = False,
) -> Dict[str, Any]:
    p = _norm_pair(pair)
    reg = load_registry(registry_path)
    now = _utc_now().isoformat()
    graduated = dict(reg.get("graduated") or {})
    graduated.pop(p, None)
    demoted = dict(reg.get("demoted") or {})
    demoted[p] = {"demoted_at": now, "reasons": [reason], "prev_class": "graduated"}
    fg = [x for x in (reg.get("force_graduated") or []) if x != p]
    reg["graduated"] = graduated
    reg["demoted"] = demoted
    reg["force_graduated"] = fg
    if hard_pin:
        hp = list(reg.get("hard_pin_block") or [])
        if p not in hp:
            hp.append(p)
        reg["hard_pin_block"] = hp
    else:
        fr = list(reg.get("force_restricted") or [])
        if p not in fr:
            fr.append(p)
        reg["force_restricted"] = fr
    save_registry(reg, registry_path)
    return {"pair": p, "class": "novelty_blocked" if hard_pin else "novelty_restricted", "reason": reason}


def unpin_pair(pair: str, *, registry_path: Path = REGISTRY_PATH) -> Dict[str, Any]:
    p = _norm_pair(pair)
    reg = load_registry(registry_path)
    reg["hard_pin_block"] = [x for x in (reg.get("hard_pin_block") or []) if x != p]
    reg["force_restricted"] = [x for x in (reg.get("force_restricted") or []) if x != p]
    save_registry(reg, registry_path)
    return {"pair": p, "unpinned": True}


def annotate_swap(
    swap: Dict[str, Any],
    *,
    enforce: bool = True,
    registry: Optional[Dict[str, Any]] = None,
    registry_path: Path = REGISTRY_PATH,
) -> Dict[str, Any]:
    """Tag a proposal swap with novelty class; optionally clear membership_ok."""
    out = dict(swap)
    add = _norm_pair(str(out.get("add") or out.get("pair") or out.get("inbound") or ""))
    if not add:
        out["novelty_class"] = None
        out["novelty_blocked"] = False
        return out
    vol = _f(out.get("quote_vol_24h") or out.get("volume_24h") or out.get("add_quote_vol_24h"))
    r24 = _f(out.get("ret_24h") or out.get("add_ret_24h") or out.get("r24"))
    r7 = _f(out.get("ret_7d") or out.get("add_ret_7d") or out.get("r7"))
    v = evaluate_pair_novelty(
        add,
        enforce=enforce,
        registry=registry,
        registry_path=registry_path,
        quote_vol_24h=vol,
        ret_24h=r24,
        ret_7d=r7,
        persist_first_seen=False,
    )
    out["novelty_class"] = v.class_
    out["novelty_blocked"] = bool(v.blocked)
    out["novelty_reasons"] = list(v.reasons[:8])
    out["novelty_can_graduate"] = bool(v.can_graduate)
    if v.blocked:
        # Do not claim membership ok for auto shortlist
        if out.get("membership_ok") is True:
            out["membership_ok"] = False
            out["membership_ok_suppressed_by"] = "novelty_class_gate"
        tag = f"novelty={v.class_}"
        notes = str(out.get("notes") or "")
        if tag not in notes:
            out["notes"] = (notes + " | " + tag).strip(" |")
    return out


def build_board(
    pairs: Optional[Iterable[str]] = None,
    *,
    registry_path: Path = REGISTRY_PATH,
    ledger_path: Path = LEDGER_PATH,
    write: bool = True,
) -> Dict[str, Any]:
    reg = load_registry(registry_path)
    known: Set[str] = set()
    known |= set(STICKY_CORE) | set(LIQUID_CORE) | set(SEED_NOVELTY_RESTRICTED)
    known |= set(reg.get("hard_pin_block") or [])
    known |= set(reg.get("force_graduated") or [])
    known |= set(reg.get("force_restricted") or [])
    known |= set((reg.get("graduated") or {}).keys())
    known |= set((reg.get("demoted") or {}).keys())
    known |= set((reg.get("first_seen") or {}).keys())
    if pairs:
        known |= {_norm_pair(x) for x in pairs if _norm_pair(x)}

    rows = _load_ledger_rows(ledger_path)
    buckets: Dict[str, List[Dict[str, Any]]] = {
        "sticky_core": [],
        "liquid_core": [],
        "graduated": [],
        "novelty_restricted": [],
        "novelty_blocked": [],
    }
    blocked_n = 0
    for p in sorted(known):
        v = evaluate_pair_novelty(
            p,
            enforce=True,
            registry=reg,
            registry_path=registry_path,
            ledger_path=ledger_path,
            ledger_rows=rows,
        )
        item = v.to_dict()
        buckets.setdefault(v.class_, []).append(item)
        if v.blocked:
            blocked_n += 1

    board = {
        "schema": SCHEMA,
        "asof": _utc_now().isoformat(),
        "counts": {k: len(vals) for k, vals in buckets.items()},
        "blocked_for_auto_rotation": blocked_n,
        "buckets": buckets,
        "registry_path": str(registry_path),
        "notes": [
            "novelty_restricted/blocked => blocked for auto membership shortlist",
            "paper CF / shadow arms still measure restricted names",
            "graduate via promote_pair or auto when graduation_packet_ok",
            "live_membership_swaps unchanged by this gate",
        ],
    }
    if write:
        LATEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        LATEST_PATH.write_text(json.dumps(board, indent=2, sort_keys=True) + "\n")
    return board


def format_board_lines(board: Optional[Dict[str, Any]] = None) -> str:
    b = board or (json.loads(LATEST_PATH.read_text()) if LATEST_PATH.exists() else build_board())
    lines = [
        f"novelty_class schema={b.get('schema')} asof={b.get('asof')}",
        f"counts={b.get('counts')} blocked_auto={b.get('blocked_for_auto_rotation')}",
    ]
    for name in ("novelty_blocked", "novelty_restricted", "graduated", "liquid_core", "sticky_core"):
        items = (b.get("buckets") or {}).get(name) or []
        if not items:
            continue
        sample = ", ".join(x.get("pair", "?") for x in items[:12])
        more = f" +{len(items) - 12}" if len(items) > 12 else ""
        lines.append(f"  {name} ({len(items)}): {sample}{more}")
    return "\n".join(lines)
