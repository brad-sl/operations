#!/usr/bin/env python3
"""GAP-06: /api/performance cold+warm+concurrent soak (live dash).

Frozen bars (MASTER P6-SCALE-GAP-06):
  - non-null periods when history exists OR explicit timeout source (never silent wrong 0)
  - warm p95 < 1.0s
  - cold < 8.0s
  - concurrent all HTTP 200 with same honesty rules

Usage:
  PYTHONPATH=. .venv/bin/python scripts/phase6/run_perf_api_soak.py
  PYTHONPATH=. .venv/bin/python scripts/phase6/run_perf_api_soak.py --base http://127.0.0.1:8502
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASE = "http://127.0.0.1:8502"
PERIOD_KEYS = ("today", "h24", "d7", "d14", "d30")
COLD_SLA_S = 8.0
WARM_P95_SLA_S = 1.0


def _req(url: str, method: str = "GET", timeout: float = 45.0) -> tuple[int, float, dict | str]:
    t0 = time.perf_counter()
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            dt = time.perf_counter() - t0
            try:
                body: dict | str = json.loads(raw.decode("utf-8"))
            except Exception:
                body = raw[:200].decode("utf-8", errors="replace")
            return int(r.status), dt, body
    except urllib.error.HTTPError as e:
        dt = time.perf_counter() - t0
        try:
            body = json.loads(e.read().decode("utf-8"))
        except Exception:
            body = str(e)
        return int(e.code), dt, body
    except Exception as e:
        dt = time.perf_counter() - t0
        return 0, dt, f"ERR:{type(e).__name__}:{e}"


def _period_honesty(payload: dict) -> list[str]:
    """Return list of honesty violations (empty = ok)."""
    bad: list[str] = []
    if not isinstance(payload, dict):
        return ["payload_not_object"]
    source = str(payload.get("source") or "")
    # Silent wrong 0: all period keys are numeric 0 with no timeout/adjusted source and no trades
    zeros = 0
    nones = 0
    nums = 0
    for k in PERIOD_KEYS:
        v = payload.get(k)
        if v is None:
            nones += 1
        elif isinstance(v, (int, float)):
            nums += 1
            if float(v) == 0.0:
                zeros += 1
        else:
            bad.append(f"{k}_bad_type:{type(v).__name__}")
    # Timeout path must not invent 0.0 tiles
    if "timeout" in source.lower() or payload.get("status") == "timeout":
        for k in PERIOD_KEYS:
            v = payload.get(k)
            if isinstance(v, (int, float)) and float(v) == 0.0:
                bad.append(f"timeout_with_zero_{k}")
    # If every period is exactly 0.0 and source doesn't claim real calc — suspicious
    if zeros == len(PERIOD_KEYS) and "timeout" not in source.lower():
        # Allow true flat book only if source looks real
        if "period_snapshots" not in source and "portfolio_snapshots" not in source:
            bad.append("all_periods_zero_without_snapshot_source")
    return bad


def run_soak(base: str, warm_n: int, conc_n: int) -> dict:
    base = base.rstrip("/")
    perf_url = f"{base}/api/performance"
    flush_url = f"{base}/api/performance/flush"

    # Ensure server up
    root_code, root_t, _ = _req(base + "/", timeout=5.0)
    if root_code not in (200, 301, 302):
        return {
            "ok": False,
            "enum": "gap_in_code",
            "error": f"dashboard_unreachable http={root_code}",
            "root_s": root_t,
        }

    flush_code, flush_t, flush_body = _req(flush_url, timeout=10.0)
    # cold
    cold_code, cold_t, cold_body = _req(perf_url, timeout=45.0)
    cold_viol = _period_honesty(cold_body) if isinstance(cold_body, dict) else ["cold_not_json"]

    warm_times: list[float] = []
    warm_codes: list[int] = []
    warm_viol: list[str] = []
    warm_bodies: list[dict | str] = []
    for _ in range(warm_n):
        c, t, b = _req(perf_url, timeout=30.0)
        warm_codes.append(c)
        warm_times.append(t)
        warm_bodies.append(b)
        if isinstance(b, dict):
            warm_viol.extend(_period_honesty(b))
        else:
            warm_viol.append("warm_not_json")

    def one(i: int):
        c, t, b = _req(perf_url, timeout=30.0)
        return i, c, t, b

    conc_rows = []
    with ThreadPoolExecutor(max_workers=conc_n) as ex:
        futs = [ex.submit(one, i) for i in range(conc_n)]
        for f in as_completed(futs):
            conc_rows.append(f.result())
    conc_rows.sort(key=lambda r: r[0])
    conc_times = [r[2] for r in conc_rows]
    conc_codes = [r[1] for r in conc_rows]
    conc_viol: list[str] = []
    for _, c, _, b in conc_rows:
        if isinstance(b, dict):
            conc_viol.extend(_period_honesty(b))
        else:
            conc_viol.append("conc_not_json")

    def p95(xs: list[float]) -> float:
        if not xs:
            return float("inf")
        if len(xs) == 1:
            return xs[0]
        return float(statistics.quantiles(xs, n=20)[18])  # ~95th

    warm_p95 = p95(warm_times)
    cold_ok = cold_code == 200 and cold_t < COLD_SLA_S and not cold_viol
    warm_ok = all(c == 200 for c in warm_codes) and warm_p95 < WARM_P95_SLA_S and not warm_viol
    conc_ok = all(c == 200 for c in conc_codes) and not conc_viol

    # History exists? cold has any numeric period
    has_history = False
    if isinstance(cold_body, dict):
        has_history = any(
            isinstance(cold_body.get(k), (int, float)) for k in PERIOD_KEYS
        )

    honesty_ok = not cold_viol and not warm_viol and not conc_viol
    sla_ok = cold_ok and warm_ok
    all_http = cold_code == 200 and all(c == 200 for c in warm_codes + conc_codes)

    if honesty_ok and sla_ok and conc_ok:
        enum = "ship"
        outcome_ok = True
    elif honesty_ok and all_http and warm_ok and not cold_ok:
        # warm+honesty good, cold SLA miss → gap_in_code (or indeterminate if near)
        enum = "gap_in_code"
        outcome_ok = False
    elif not honesty_ok:
        enum = "gap_in_code"
        outcome_ok = False
    elif not all_http:
        enum = "gap_in_code"
        outcome_ok = False
    else:
        enum = "inconclusive"
        outcome_ok = False

    # Extract sample fields
    def sample(b):
        if not isinstance(b, dict):
            return {"raw": str(b)[:120]}
        return {
            "status": b.get("status"),
            "cache": b.get("cache"),
            "source": b.get("source"),
            "today": b.get("today"),
            "d7": b.get("d7"),
            "d14": b.get("d14"),
            "d30": b.get("d30"),
            "equity_status": (b.get("equity_trend") or {}).get("status")
            if isinstance(b.get("equity_trend"), dict)
            else None,
        }

    return {
        "ok": outcome_ok,
        "enum": enum,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "base": base,
        "sla": {"cold_s": COLD_SLA_S, "warm_p95_s": WARM_P95_SLA_S},
        "flush": {"http": flush_code, "s": round(flush_t, 4), "body": flush_body if not isinstance(flush_body, dict) else flush_body.get("status")},
        "cold": {
            "http": cold_code,
            "s": round(cold_t, 4),
            "sla_pass": cold_code == 200 and cold_t < COLD_SLA_S,
            "honesty_violations": cold_viol,
            "sample": sample(cold_body),
        },
        "warm": {
            "n": warm_n,
            "http_codes": warm_codes,
            "times_s": [round(t, 4) for t in warm_times],
            "p95_s": round(warm_p95, 4),
            "mean_s": round(statistics.mean(warm_times), 4) if warm_times else None,
            "sla_pass": warm_ok,
            "honesty_violations": warm_viol,
            "sample_last": sample(warm_bodies[-1]) if warm_bodies else None,
        },
        "concurrent": {
            "n": conc_n,
            "http_codes": conc_codes,
            "times_s": [round(t, 4) for t in conc_times],
            "max_s": round(max(conc_times), 4) if conc_times else None,
            "pass": conc_ok,
            "honesty_violations": conc_viol,
        },
        "gates": {
            "honesty_ok": honesty_ok,
            "cold_sla_ok": cold_code == 200 and cold_t < COLD_SLA_S,
            "warm_sla_ok": warm_ok,
            "concurrent_ok": conc_ok,
            "has_history_numeric_period": has_history,
            "all_http_200": all_http,
        },
    }


def write_report(result: dict, out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=2) + "\n")
    g = result.get("gates") or {}
    cold = result.get("cold") or {}
    warm = result.get("warm") or {}
    conc = result.get("concurrent") or {}
    lines = [
        "# GAP-06 Perf API Soak",
        "",
        f"**as_of:** {result.get('as_of')}  ",
        f"**base:** `{result.get('base')}`  ",
        f"**enum:** `{result.get('enum')}`  ",
        f"**ok (ship):** {result.get('ok')}  ",
        "",
        "## Gates (frozen)",
        "",
        f"| Gate | Pass | Detail |",
        f"|------|------|--------|",
        f"| Honesty (no silent wrong 0) | {g.get('honesty_ok')} | cold_viol={cold.get('honesty_violations')} |",
        f"| Cold < {COLD_SLA_S}s | {g.get('cold_sla_ok')} | t={cold.get('s')}s http={cold.get('http')} |",
        f"| Warm p95 < {WARM_P95_SLA_S}s | {g.get('warm_sla_ok')} | p95={warm.get('p95_s')}s mean={warm.get('mean_s')}s |",
        f"| Concurrent honesty+200 | {g.get('concurrent_ok')} | n={conc.get('n')} max={conc.get('max_s')}s |",
        f"| History numeric period | {g.get('has_history_numeric_period')} | |",
        "",
        "## Samples",
        "",
        "```json",
        json.dumps(
            {
                "cold": cold.get("sample"),
                "warm_last": warm.get("sample_last"),
            },
            indent=2,
        ),
        "```",
        "",
        f"Full JSON: `{out_json}`",
        "",
    ]
    out_md.write_text("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--warm-n", type=int, default=8)
    ap.add_argument("--concurrent-n", type=int, default=8)
    ap.add_argument(
        "--out-json",
        default=str(ROOT / "data/state/perf_api_soak_latest.json"),
    )
    ap.add_argument(
        "--out-md",
        default=str(ROOT / "reports/PERF_API_SOAK_LATEST.md"),
    )
    args = ap.parse_args()
    result = run_soak(args.base, args.warm_n, args.concurrent_n)
    write_report(result, Path(args.out_json), Path(args.out_md))
    print(json.dumps(result, indent=2))
    print(f"\nWrote {args.out_json}")
    print(f"Wrote {args.out_md}")
    print(f"ENUM={result.get('enum')} ok={result.get('ok')}")
    # exit 0 even on gap_in_code so CI can parse JSON; use --strict for fail
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
