#!/usr/bin/env python3
"""Signal data-quality monitor: rebalance defer streaks + basket coverage.

Deterministic (no LLM). Intended for scripts/phase6/monitor_phase6_runner.py
and optional ops hooks.

Design:
- Detect repeated [REBALANCE DEFER] with the same reason fingerprint
- Snapshot current RSI/sentiment coverage
- Alert once per fingerprint with cooldown (default 60m)
- Clear streak state when a rebalance completes or gate allows
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOG = PROJECT_ROOT / "logs" / "phase6_runner.log"
DEFAULT_STATE = PROJECT_ROOT / "data" / "state" / "signal_dq_monitor.json"
DEFAULT_RSI_CACHE = PROJECT_ROOT / "data" / "state" / "rsi_cache.json"
DEFAULT_SENT_CACHE = PROJECT_ROOT / "data" / "state" / "sentiment_cache.json"

DEFER_RE = re.compile(
    r"\[REBALANCE DEFER\]\s+slot=(?P<slot>\S+)\s+reasons=(?P<reasons>.+)$"
)
GATE_ALLOWED_RE = re.compile(r"\[REBALANCE GATE\]\s+allowed")
REBAL_DONE_RE = re.compile(
    r"(Daily rebalance completed|=== Daily Rebalance ===|\[REBALANCE DEFER\] cleared)"
)
MISSING_RSI_RE = re.compile(r"missing_rsi=(\[[^\]]*\])")
PRE_INCOMPLETE_RE = re.compile(
    r"\[PRE-REBAL REFRESH\] incomplete coverage.*?reasons=(?P<reasons>\[[^\]]*\])"
)


@dataclass
class CoverageSnapshot:
    basket_size: int = 0
    rsi_ok: int = 0
    sent_ok: int = 0
    missing_rsi: List[str] = field(default_factory=list)
    missing_sent: List[str] = field(default_factory=list)
    complete: bool = False

    def summary(self) -> str:
        return (
            f"RSI {self.rsi_ok}/{self.basket_size} missing={self.missing_rsi or '[]'}; "
            f"sent {self.sent_ok}/{self.basket_size} missing={self.missing_sent or '[]'}"
        )


@dataclass
class DeferStreak:
    fingerprint: str
    count: int
    slot: str
    reasons: str
    first_line: str = ""
    last_line: str = ""
    sample_missing_rsi: List[str] = field(default_factory=list)


@dataclass
class AlertDecision:
    should_alert: bool
    level: str  # ok | warning | critical
    message: str
    fingerprint: str = ""
    streak: Optional[DeferStreak] = None
    coverage: Optional[CoverageSnapshot] = None
    state: Dict[str, Any] = field(default_factory=dict)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_list_literal(raw: str) -> List[str]:
    raw = (raw or "").strip()
    if not raw or raw == "[]":
        return []
    try:
        val = json.loads(raw.replace("'", '"'))
        if isinstance(val, list):
            return [str(x) for x in val]
    except Exception:
        pass
    inner = raw.strip("[]")
    if not inner:
        return []
    return [p.strip().strip("'\"") for p in inner.split(",") if p.strip()]


def load_state(path: Path = DEFAULT_STATE) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: Dict[str, Any], path: Path = DEFAULT_STATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def read_log_tail(log_path: Path = DEFAULT_LOG, max_lines: int = 4000) -> List[str]:
    if not log_path.exists():
        return []
    try:
        # Efficient-ish tail for multi-MB logs
        with open(log_path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            block = 256 * 1024
            data = b""
            while size > 0 and data.count(b"\n") <= max_lines:
                step = min(block, size)
                size -= step
                f.seek(size)
                data = f.read(step) + data
                if size == 0:
                    break
        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()
        return lines[-max_lines:]
    except Exception:
        try:
            return log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:]
        except Exception:
            return []


def detect_defer_streak(
    lines: Sequence[str],
    *,
    min_streak: int = 3,
) -> Optional[DeferStreak]:
    """Find trailing consecutive REBALANCE DEFER events with same fingerprint.

    Resets when gate allowed / rebalance completed appears after a defer.
    """
    events: List[Tuple[str, str, str, List[str]]] = []  # kind, slot, reasons, missing_rsi
    pending_missing: List[str] = []

    for line in lines:
        m_miss = MISSING_RSI_RE.search(line)
        if m_miss:
            pending_missing = _parse_list_literal(m_miss.group(1))

        if GATE_ALLOWED_RE.search(line):
            events.append(("clear", "", "", []))
            pending_missing = []
            continue
        if "[REBALANCE DEFER] cleared" in line:
            events.append(("clear", "", "", []))
            pending_missing = []
            continue
        if "Daily rebalance completed" in line or "=== Daily Rebalance ===" in line:
            events.append(("clear", "", "", []))
            pending_missing = []
            continue

        m = DEFER_RE.search(line)
        if m and "cleared" not in line:
            slot = m.group("slot").strip()
            reasons = m.group("reasons").strip()
            events.append(("defer", slot, reasons, list(pending_missing)))
            continue

        m2 = PRE_INCOMPLETE_RE.search(line)
        if m2:
            # strengthen fingerprint with pre-rebal reason when present
            events.append(("pre_incomplete", "", m2.group("reasons").strip(), list(pending_missing)))

    # Walk from end: require trailing defers without intervening clear
    trailing: List[Tuple[str, str, str, List[str]]] = []
    for ev in reversed(events):
        if ev[0] == "clear":
            break
        if ev[0] == "defer":
            trailing.append(ev)
        # ignore pre_incomplete for streak count but keep missing hints
    trailing.reverse()
    if len(trailing) < min_streak:
        return None

    # Same fingerprint = slot + reasons
    last = trailing[-1]
    fp = f"{last[1]}|{last[2]}"
    same = [e for e in trailing if f"{e[1]}|{e[2]}" == fp]
    # Count contiguous same-fp from the end
    count = 0
    for e in reversed(trailing):
        if f"{e[1]}|{e[2]}" == fp:
            count += 1
        else:
            break
    if count < min_streak:
        return None

    missing: List[str] = []
    for e in reversed(same):
        if e[3]:
            missing = e[3]
            break

    return DeferStreak(
        fingerprint=fp,
        count=count,
        slot=last[1],
        reasons=last[2],
        sample_missing_rsi=missing,
    )


def assess_live_coverage(
    basket: Optional[Sequence[str]] = None,
    *,
    rsi_cache: Path = DEFAULT_RSI_CACHE,
    sent_cache: Path = DEFAULT_SENT_CACHE,
    project_root: Path = PROJECT_ROOT,
) -> CoverageSnapshot:
    if basket is None:
        try:
            from phase6.core.paths import load_trading_basket

            basket = load_trading_basket()
        except Exception:
            basket = [
                "BTC-USD",
                "ETH-USD",
                "SOL-USD",
                "XRP-USD",
                "DOGE-USD",
                "ADA-USD",
                "AVAX-USD",
                "LINK-USD",
                "UNI-USD",
                "ARB-USD",
                "OP-USD",
            ]
    basket = list(basket)
    missing_rsi: List[str] = []
    missing_sent: List[str] = []
    rsi_ok = 0
    sent_ok = 0

    rsi_block: Dict[str, Any] = {}
    if rsi_cache.exists():
        try:
            raw = json.loads(rsi_cache.read_text(encoding="utf-8"))
            rsi_block = raw.get("rsi") or raw
        except Exception:
            rsi_block = {}

    sent_block: Dict[str, Any] = {}
    if sent_cache.exists():
        try:
            raw = json.loads(sent_cache.read_text(encoding="utf-8"))
            sent_block = raw.get("sentiment") or raw.get("data") or raw
        except Exception:
            sent_block = {}

    # Prefer scorer for sentiment if available (free_fallback aware)
    scorer_scores: Dict[str, float] = {}
    try:
        import sys

        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        from phase6.core.sentiment_scorer import load_sentiment_scores

        scorer_scores = load_sentiment_scores(universe=list(basket))
    except Exception:
        scorer_scores = {}

    for pair in basket:
        entry = rsi_block.get(pair)
        rsi_val = None
        if isinstance(entry, dict):
            rsi_val = entry.get("rsi")
        elif isinstance(entry, (int, float)):
            rsi_val = entry
        if rsi_val is None:
            missing_rsi.append(pair)
        else:
            rsi_ok += 1

        if pair in scorer_scores:
            # observed score (0.0 allowed if free path produced it intentionally)
            sent_ok += 1
            continue
        sent_e = sent_block.get(pair)
        if sent_e is None:
            missing_sent.append(pair)
            continue
        if isinstance(sent_e, dict):
            # presence of pair in cache counts as covered for DQ (value can be 0)
            sent_ok += 1
        else:
            sent_ok += 1

    return CoverageSnapshot(
        basket_size=len(basket),
        rsi_ok=rsi_ok,
        sent_ok=sent_ok,
        missing_rsi=missing_rsi,
        missing_sent=missing_sent,
        complete=(len(missing_rsi) == 0 and len(missing_sent) == 0 and len(basket) > 0),
    )


def evaluate_signal_dq(
    *,
    log_path: Path | str = DEFAULT_LOG,
    state_path: Path | str = DEFAULT_STATE,
    min_streak: int = 3,
    cooldown_minutes: int = 60,
    max_log_lines: int = 4000,
    now: Optional[datetime] = None,
) -> AlertDecision:
    """Main entry: returns whether to Telegram-alert and updates state file."""
    log_path = Path(log_path)
    state_path = Path(state_path)
    now = now or datetime.now(timezone.utc)
    lines = read_log_tail(log_path, max_lines=max_log_lines)
    streak = detect_defer_streak(lines, min_streak=min_streak)
    coverage = assess_live_coverage()
    state = load_state(state_path)

    # Always refresh coverage snapshot in state
    state["last_check_ts"] = now.isoformat()
    state["coverage"] = asdict(coverage)

    if streak is None:
        # Healthy path: clear active streak
        if state.get("active_fingerprint"):
            state["last_clear_ts"] = now.isoformat()
            state["last_cleared_fingerprint"] = state.get("active_fingerprint")
        state["active_fingerprint"] = None
        state["active_streak_count"] = 0
        save_state(state, state_path)
        msg = f"[SIGNAL-DQ] OK — no defer streak. {coverage.summary()}"
        return AlertDecision(
            should_alert=False,
            level="ok",
            message=msg,
            coverage=coverage,
            state=state,
        )

    state["active_fingerprint"] = streak.fingerprint
    state["active_streak_count"] = streak.count
    state["active_slot"] = streak.slot
    state["active_reasons"] = streak.reasons
    state["active_missing_rsi"] = streak.sample_missing_rsi or coverage.missing_rsi

    last_alert_fp = state.get("last_alert_fingerprint")
    last_alert_ts = state.get("last_alert_ts")
    cooled = True
    if last_alert_fp == streak.fingerprint and last_alert_ts:
        try:
            prev = datetime.fromisoformat(str(last_alert_ts).replace("Z", "+00:00"))
            if prev.tzinfo is None:
                prev = prev.replace(tzinfo=timezone.utc)
            cooled = (now - prev).total_seconds() >= cooldown_minutes * 60
        except Exception:
            cooled = True

    miss = streak.sample_missing_rsi or coverage.missing_rsi
    miss_s = ",".join(miss) if miss else "n/a"
    body = (
        f"⚠️ SIGNAL-DQ: rebalance deferred {streak.count}× consecutive\n"
        f"slot={streak.slot}\n"
        f"reasons={streak.reasons}\n"
        f"missing_rsi≈{miss_s}\n"
        f"coverage: {coverage.summary()}\n"
        f"Action: check logs/phase6_runner.log + scripts/refresh_rsi_prices.py; "
        f"run ensure_full_basket_coverage if needed."
    )

    if not cooled:
        save_state(state, state_path)
        return AlertDecision(
            should_alert=False,
            level="warning",
            message=f"[SIGNAL-DQ] streak={streak.count} (cooldown active) {coverage.summary()}",
            fingerprint=streak.fingerprint,
            streak=streak,
            coverage=coverage,
            state=state,
        )

    state["last_alert_fingerprint"] = streak.fingerprint
    state["last_alert_ts"] = now.isoformat()
    state["last_alert_count"] = streak.count
    save_state(state, state_path)

    level = "critical" if streak.count >= max(min_streak * 2, 6) else "warning"
    return AlertDecision(
        should_alert=True,
        level=level,
        message=body,
        fingerprint=streak.fingerprint,
        streak=streak,
        coverage=coverage,
        state=state,
    )


def format_coverage_kpi(coverage: Optional[CoverageSnapshot] = None) -> str:
    cov = coverage or assess_live_coverage()
    status = "PASS" if cov.complete else "FAIL"
    return f"Signal coverage KPI [{status}]: {cov.summary()}"


if __name__ == "__main__":
    d = evaluate_signal_dq()
    print(d.level, d.should_alert)
    print(d.message)
    if d.coverage:
        print(format_coverage_kpi(d.coverage))
