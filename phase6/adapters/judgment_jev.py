"""OpenRouter Decisions API adapter for TypeSafe Jev.

Endpoint: POST https://openrouter.ai/api/alpha/decisions
Default model: ~typesafe/jev-latest (pin via JEV_MODEL / config).

Never places orders. Lab/shadow only until Brad GO on gate use.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

from phase6.domain.ports.judgment import JudgmentAnswer, JudgmentPort, JudgmentResult

DEFAULT_URL = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_MODEL = "~typesafe/jev-latest"
# Prefer pinned when set; latest is Brad-provided default for lab start.
PINNED_MODEL = "typesafe/jev-1.13"


def _load_dotenv_keys() -> None:
    for p in (
        Path.home() / ".hermes" / ".env",
        Path(__file__).resolve().parents[2] / ".env",
    ):
        if not p.is_file():
            continue
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
        except OSError:
            continue


def resolve_api_key() -> str:
    _load_dotenv_keys()
    return (
        os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("OPENROUTER_KEY")
        or ""
    ).strip()


def parse_answers(payload: Dict[str, Any]) -> Dict[str, JudgmentAnswer]:
    raw_answers = payload.get("answers") or {}
    if not isinstance(raw_answers, dict):
        return {}
    out: Dict[str, JudgmentAnswer] = {}
    for name, body in raw_answers.items():
        if not isinstance(body, dict):
            continue
        t = str(body.get("type") or "").lower()
        out[str(name)] = JudgmentAnswer(name=str(name), type=t, raw=dict(body))
    return out


class OpenRouterJevAdapter:
    """Concrete JudgmentPort via OpenRouter alpha decisions."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        url: str = DEFAULT_URL,
        timeout_s: float = 30.0,
        referer: str = "https://github.com/brad/crypto-trading-bot",
        title: str = "phase6-jev-lab",
    ) -> None:
        self.api_key = (api_key if api_key is not None else resolve_api_key()).strip()
        self.model = (model or os.environ.get("JEV_MODEL") or DEFAULT_MODEL).strip()
        self.url = url
        self.timeout_s = float(timeout_s)
        self.referer = referer
        self.title = title

    def decide(
        self,
        state: Any,
        questions: Dict[str, Any],
        *,
        model: Optional[str] = None,
    ) -> JudgmentResult:
        m = (model or self.model).strip()
        if not self.api_key:
            return JudgmentResult(
                ok=False,
                model=m,
                error="missing_OPENROUTER_API_KEY",
            )
        if not questions or not isinstance(questions, dict):
            return JudgmentResult(ok=False, model=m, error="empty_questions")

        body = {
            "model": m,
            "state": state,
            "questions": questions,
        }
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            self.url,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": self.referer,
                "X-OpenRouter-Title": self.title,
            },
        )
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                raw_text = resp.read().decode("utf-8", errors="replace")
                status = getattr(resp, "status", 200)
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8", errors="replace")[:800]
            except Exception:  # noqa: BLE001
                pass
            return JudgmentResult(
                ok=False,
                model=m,
                latency_ms=int((time.perf_counter() - t0) * 1000),
                error=f"http_{e.code}:{err_body or e.reason}",
            )
        except Exception as e:  # noqa: BLE001
            return JudgmentResult(
                ok=False,
                model=m,
                latency_ms=int((time.perf_counter() - t0) * 1000),
                error=f"{type(e).__name__}:{e}",
            )

        latency = int((time.perf_counter() - t0) * 1000)
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError:
            return JudgmentResult(
                ok=False,
                model=m,
                latency_ms=latency,
                error=f"bad_json:{raw_text[:200]}",
                raw={"status": status, "text": raw_text[:500]},
            )

        # OpenRouter may wrap under data
        if isinstance(payload.get("data"), dict) and "answers" not in payload:
            payload = payload["data"]

        answers = parse_answers(payload)
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        model_out = str(payload.get("model") or m)
        ok = bool(answers) and not payload.get("error")
        err = ""
        if not ok:
            err = str(payload.get("error") or payload.get("message") or "no_answers")
        return JudgmentResult(
            ok=ok,
            model=model_out,
            answers=answers,
            usage=dict(usage),
            latency_ms=latency,
            error=err,
            raw=payload if isinstance(payload, dict) else {},
        )


def mock_from_fixture(answers: Dict[str, Any], *, model: str = "mock-jev") -> JudgmentResult:
    """Build a JudgmentResult without HTTP (tests / offline)."""
    payload = {"model": model, "answers": answers, "usage": {"input_tokens": 0}}
    return JudgmentResult(
        ok=True,
        model=model,
        answers=parse_answers(payload),
        usage=payload["usage"],
        latency_ms=0,
        raw=payload,
    )


# Type check helper — adapter satisfies port structurally
def as_port(adapter: OpenRouterJevAdapter) -> JudgmentPort:
    return adapter  # type: ignore[return-value]
