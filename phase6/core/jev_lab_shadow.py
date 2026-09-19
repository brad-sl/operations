"""Jev lab shadow runner — measure-only decision packets.

No orders. No tryout knobs. Logs crumbs for calibration.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from phase6.adapters.judgment_jev import OpenRouterJevAdapter, mock_from_fixture
from phase6.domain.ports.judgment import JudgmentPort, JudgmentResult
from phase6.domain.services.decision_packet import (
    build_pair_state,
    confidence_gate_paper,
    default_lab_questions,
)

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT = ROOT / "data" / "state" / "jev_lab_latest.json"
DEFAULT_CRUMBS = ROOT / "data" / "state" / "jev_lab_crumbs.jsonl"
DEFAULT_BUDGET = ROOT / "data" / "state" / "jev_lab_budget.json"


@dataclass
class LabConfig:
    pairs: List[str] = field(default_factory=lambda: ["BTC-USD", "ETH-USD"])
    max_calls_per_day: int = 24
    model: str = "~typesafe/jev-latest"
    dry_run: bool = False  # dry_run = mock, no HTTP
    write_crumbs: bool = True
    budget_path: Path = field(default_factory=lambda: DEFAULT_BUDGET)
    crumbs_path: Path = field(default_factory=lambda: DEFAULT_CRUMBS)
    latest_path: Path = field(default_factory=lambda: DEFAULT_OUT)


def _day_key(now: Optional[datetime] = None) -> str:
    n = now or datetime.now(timezone.utc)
    return n.strftime("%Y-%m-%d")


def load_budget(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {"day": _day_key(), "calls": 0}
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        if d.get("day") != _day_key():
            return {"day": _day_key(), "calls": 0}
        return d
    except (OSError, json.JSONDecodeError):
        return {"day": _day_key(), "calls": 0}


def save_budget(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def run_lab(
    *,
    cfg: Optional[LabConfig] = None,
    port: Optional[JudgmentPort] = None,
    pairs: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    cfg = cfg or LabConfig()
    pair_list = [str(p).upper() for p in (pairs or cfg.pairs)]
    questions = default_lab_questions()
    budget = load_budget(cfg.budget_path)
    calls_left = max(0, int(cfg.max_calls_per_day) - int(budget.get("calls") or 0))

    adapter: JudgmentPort
    if cfg.dry_run and port is None:
        # offline fixture path handled per pair below
        adapter = None  # type: ignore
    else:
        adapter = port or OpenRouterJevAdapter(model=cfg.model)

    results: List[Dict[str, Any]] = []
    blocked_budget = False

    for pair in pair_list:
        if not cfg.dry_run and calls_left <= 0:
            blocked_budget = True
            results.append(
                {
                    "pair": pair,
                    "ok": False,
                    "error": "lab_daily_call_budget_exhausted",
                    "paper": {"paper_would_buy_tag": False, "would_order": False},
                }
            )
            continue

        state = build_pair_state(pair)
        t0 = time.perf_counter()
        if cfg.dry_run and port is None:
            jr = mock_from_fixture(
                {
                    "action": {
                        "type": "choice",
                        "choice": "hold",
                        "confidence": 0.7,
                        "probabilities": {"hold": 0.7, "buy": 0.2, "sell": 0.1},
                    },
                    "regime": {
                        "type": "choice",
                        "choice": "range",
                        "confidence": 0.6,
                        "probabilities": {"range": 0.6, "trend_up": 0.2, "trend_down": 0.2},
                    },
                    "setup_quality": {
                        "type": "score",
                        "score": 1.2,
                        "confidence": 0.5,
                        "probabilities": {"0": 0.2, "1": 0.5, "2": 0.25, "3": 0.05},
                    },
                    "is_fakeout_or_stop_run": {"type": "noul", "noul": 0.4},
                    "should_trade_name_now": {"type": "noul", "noul": 0.35},
                }
            )
        else:
            assert adapter is not None
            jr = adapter.decide(state, questions, model=cfg.model)

        paper = confidence_gate_paper(jr.answers)
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "pair": pair,
            "ok": jr.ok,
            "model": jr.model,
            "latency_ms": jr.latency_ms or int((time.perf_counter() - t0) * 1000),
            "error": jr.error,
            "usage": jr.usage,
            "state_compact": {
                "rsi": (state.get("indicators") or {}).get("rsi_14"),
                "eng": (state.get("indicators") or {}).get("eng_sentiment"),
                "qty": (state.get("inventory") or {}).get("qty"),
            },
            "answers": {k: {"type": a.type, **a.raw} for k, a in jr.answers.items()},
            "paper": paper,
            "would_order": False,
        }
        results.append(row)

        if jr.ok and not cfg.dry_run:
            budget["calls"] = int(budget.get("calls") or 0) + 1
            budget["day"] = _day_key()
            calls_left = max(0, int(cfg.max_calls_per_day) - int(budget["calls"]))
            save_budget(cfg.budget_path, budget)

        if cfg.write_crumbs:
            cfg.crumbs_path.parent.mkdir(parents=True, exist_ok=True)
            with cfg.crumbs_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, separators=(",", ":")) + "\n")

    summary = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "lab": "jev_judgment",
        "measure_only": True,
        "would_order_always_false": True,
        "model": cfg.model,
        "dry_run": cfg.dry_run,
        "budget": load_budget(cfg.budget_path),
        "max_calls_per_day": cfg.max_calls_per_day,
        "blocked_budget": blocked_budget,
        "n_pairs": len(pair_list),
        "n_ok": sum(1 for r in results if r.get("ok")),
        "paper_buy_tags": sum(1 for r in results if (r.get("paper") or {}).get("paper_would_buy_tag")),
        "results": results,
        "plain": _plain(results, blocked_budget),
    }

    if cfg.write_crumbs:
        cfg.latest_path.parent.mkdir(parents=True, exist_ok=True)
        cfg.latest_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    return summary


def _plain(results: List[Dict[str, Any]], blocked: bool) -> str:
    parts = ["Jev lab (measure-only, no orders)."]
    if blocked:
        parts.append("Daily call budget hit.")
    for r in results:
        pair = r.get("pair")
        if not r.get("ok"):
            parts.append(f"{pair}: ERR {r.get('error')}")
            continue
        ans = r.get("answers") or {}
        act = (ans.get("action") or {}).get("choice")
        st = (ans.get("should_trade_name_now") or {}).get("noul")
        fk = (ans.get("is_fakeout_or_stop_run") or {}).get("noul")
        tag = "paper_buy" if (r.get("paper") or {}).get("paper_would_buy_tag") else "skip"
        parts.append(
            f"{pair}: action={act} should_trade={st} fakeout={fk} tag={tag} "
            f"lat={r.get('latency_ms')}ms"
        )
    return " ".join(parts)
