"""JudgmentPort — typed multi-factor judgments (noul / choice / score).

Implementations live in phase6/adapters. Domain never imports HTTP.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class JudgmentAnswer:
    name: str
    type: str  # noul | choice | score
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def noul(self) -> Optional[float]:
        if self.type != "noul":
            return None
        v = self.raw.get("noul")
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def choice(self) -> Optional[str]:
        if self.type != "choice":
            return None
        c = self.raw.get("choice")
        return str(c) if c is not None else None

    @property
    def score(self) -> Optional[float]:
        if self.type != "score":
            return None
        v = self.raw.get("score")
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def confidence(self) -> Optional[float]:
        v = self.raw.get("confidence")
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def probabilities(self) -> Dict[str, float]:
        p = self.raw.get("probabilities") or {}
        if not isinstance(p, dict):
            return {}
        out: Dict[str, float] = {}
        for k, v in p.items():
            try:
                out[str(k)] = float(v)
            except (TypeError, ValueError):
                continue
        return out


@dataclass(frozen=True)
class JudgmentResult:
    ok: bool
    model: str
    answers: Dict[str, JudgmentAnswer] = field(default_factory=dict)
    usage: Dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0
    error: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "model": self.model,
            "answers": {k: {"type": a.type, **a.raw} for k, a in self.answers.items()},
            "usage": dict(self.usage),
            "latency_ms": self.latency_ms,
            "error": self.error,
        }


@runtime_checkable
class JudgmentPort(Protocol):
    def decide(
        self,
        state: Any,
        questions: Dict[str, Any],
        *,
        model: Optional[str] = None,
    ) -> JudgmentResult:
        ...
