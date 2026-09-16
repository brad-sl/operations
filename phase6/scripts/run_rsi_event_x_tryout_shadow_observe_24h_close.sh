#!/usr/bin/env bash
# 24h observe closeout for RSI-event X tryout shadow — measure only.
set -euo pipefail
ROOT="${PHASE6_ROOT:-/home/brad/projects/crypto-trading-bot}"
cd "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec "$ROOT/.venv/bin/python3" - <<'PY'
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/brad/projects/crypto-trading-bot")
STATE = ROOT / "data" / "state"
EVENTS = STATE / "rsi_event_x_tryout_shadow_events.jsonl"
OBSERVE = STATE / "rsi_event_x_tryout_shadow_observe_24h.json"
LATEST = STATE / "rsi_event_x_tryout_shadow_latest.json"
REPORT = ROOT / "reports" / "RSI_EVENT_X_TRYOUT_SHADOW_OBSERVE_24H.md"


def _load(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> int:
    obs = _load(OBSERVE) or {}
    start = str(obs.get("started_at_utc") or "")
    rows = []
    if EVENTS.exists():
        for line in EVENTS.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            ts = str(r.get("ts") or "")
            if start and ts and ts < start:
                continue
            rows.append(r)

    # exclude meta crumbs from tick stats
    ticks = [r for r in rows if r.get("event") not in ("observe_24h_start", "observe_24h_end")]
    n_ticks = len(ticks)
    trigger_hits = sum(1 for r in ticks if int(r.get("n_trigger_pool") or 0) > 0)
    topk_hits = sum(1 for r in ticks if int(r.get("n_selected") or 0) > 0)
    would_buy_hits = sum(1 for r in ticks if int(r.get("n_would_buy") or 0) > 0)
    pair_counts: dict[str, int] = {}
    for r in ticks:
        for p in r.get("selected") or []:
            pair_counts[str(p)] = pair_counts.get(str(p), 0) + 1

    latest = _load(LATEST) or {}
    # high bar for "interesting enough to discuss X probe" — not promote
    bar_pass = (
        n_ticks >= 3
        and trigger_hits >= 2
        and topk_hits >= 2
    )
    verdict = (
        "OBSERVE_PASS_discuss_X_probe"
        if bar_pass
        else "OBSERVE_THIN_keep_shadow"
    )
    if not bar_pass and n_ticks < 3:
        verdict = "OBSERVE_INCOMPLETE_rerun_window"

    window_label = str(obs.get("target_window_label") or "observe window")
    plain = (
        f"RSI-event shadow closeout ({window_label}): ticks={n_ticks} "
        f"trigger_hits={trigger_hits} topK_hits={topk_hits} "
        f"would_buy_hits={would_buy_hits}. "
        f"Top pairs: {pair_counts or '{}'}. "
        f"Verdict **{verdict}** — still no paid X / no orders unless Brad GO."
    )

    out = {
        "schema": "rsi_event_x_tryout_shadow_observe_24h_close_v1",
        "closed_at_utc": datetime.now(timezone.utc).isoformat(),
        "observe": obs,
        "n_ticks": n_ticks,
        "trigger_hits": trigger_hits,
        "topk_hits": topk_hits,
        "would_buy_hits": would_buy_hits,
        "pair_counts": pair_counts,
        "bar": {
            "min_ticks": 3,
            "min_trigger_hits": 2,
            "min_topk_hits": 2,
            "pass": bar_pass,
        },
        "verdict": verdict,
        "edge_class": "ATTENTION_ONLY_sensor_clock",
        "live_gate": "OFF",
        "plain_english": plain,
        "latest_as_of": latest.get("as_of"),
        "latest_plain": latest.get("plain_english"),
        "next_step_if_pass": "Brad GO optional: single-pair paid X probe with hard daily budget; still no auto-buy",
        "next_step_if_thin": "Keep 4x/day shadow; no X spend",
    }
    OBSERVE.write_text(json.dumps({**obs, "closeout": out}, indent=2) + "\n", encoding="utf-8")
    with EVENTS.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "ts": out["closed_at_utc"],
                    "event": "observe_24h_end",
                    "verdict": verdict,
                    "n_ticks": n_ticks,
                    "trigger_hits": trigger_hits,
                    "topk_hits": topk_hits,
                }
            )
            + "\n"
        )

    lines = [
        "# RSI-event X tryout shadow — observe closeout",
        "",
        f"- closed: `{out['closed_at_utc']}`",
        f"- window: `{obs.get('target_window_label') or 'observe'}`",
        f"- started: `{obs.get('started_at_pt') or obs.get('started_at_utc')}`",
        f"- ends target: `{obs.get('ends_at_pt') or obs.get('ends_at_utc')}`",
        f"- extended: `{obs.get('extended_at_pt') or 'n/a'}`",
        f"- verdict: **{verdict}**",
        f"- edge_class: `ATTENTION_ONLY_sensor_clock`",
        f"- live_gate: **OFF**",
        "",
        "## Counts",
        "",
        f"| metric | n |",
        f"|---|---:|",
        f"| ticks in window | {n_ticks} |",
        f"| ticks with trigger_pool>0 | {trigger_hits} |",
        f"| ticks with top-K selected | {topk_hits} |",
        f"| ticks with would_buy>0 | {would_buy_hits} |",
        "",
        "## Selected pair frequency",
        "",
    ]
    if pair_counts:
        for p, n in sorted(pair_counts.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"- `{p}`: {n}")
    else:
        lines.append("_none_")
    lines.extend(
        [
            "",
            "## Plain English",
            "",
            plain,
            "",
            "## Bar (discuss X probe only — not promote)",
            "",
            f"- min_ticks≥3, trigger_hits≥2, topK_hits≥2 → pass={bar_pass}",
            "",
            "## Next",
            "",
            f"- if pass: {out['next_step_if_pass']}",
            f"- if thin: {out['next_step_if_thin']}",
            "",
        ]
    )
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # Telegram body (always print closeout — this is the one-shot ping)
    print(plain)
    print(f"report: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
PY
