#!/usr/bin/env python3
"""GAP-01: Exit promote scoreboard — go/no-go for live TP / regime-map flip.

Aggregates real collection + SL-vs-shadow counterfactual into one weekly-style
scoreboard. Never writes live exit config.

Writes:
  reports/EXIT_PROMOTE_SCOREBOARD_LATEST.md
  data/state/exit_promote_scoreboard_latest.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

COLLECTION = ROOT / "data/state/regime_exit_shadow_collection.json"
STATUS = ROOT / "data/state/regime_exit_shadow_status.json"
MAP_CFG = ROOT / "config/regime_exit_policy_map.json"
TP_CFG = ROOT / "config/exit_automation.json"
OUT_JSON = ROOT / "data/state/exit_promote_scoreboard_latest.json"
OUT_MD = ROOT / "reports/EXIT_PROMOTE_SCOREBOARD_LATEST.md"

# Product gates (see phase6-exit-profit-shadow skill)
DEFAULT_DAYS_NEEDED = 60
EARLY_REVIEW_DAYS = 45
MIN_EPISODES_PER_REGIME = 5
REQUIRED_REGIMES = ("bull", "bear", "flat")


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _parse_ts(s: Any) -> datetime | None:
    if not s:
        return None
    t = str(s).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(t)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _sl_cf_summary() -> dict[str, Any]:
    """Reuse weekly CF builder when available (real ledger + events)."""
    try:
        import importlib.util

        path = ROOT / "scripts/phase6/sl_exit_counterfactual_report.py"
        spec = importlib.util.spec_from_file_location("sl_exit_cf_mod", path)
        if spec is None or spec.loader is None:
            return {"available": False, "error": "no_spec"}
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        since = mod._parse_ts(mod.DEFAULT_SINCE) or datetime(
            2026, 8, 6, tzinfo=timezone.utc
        )
        d = mod.build(since)
        return {
            "available": True,
            "go_no_go_cf": d.get("go_no_go"),
            "shadow_days": d.get("shadow_days"),
            "n_sl_legs": d.get("n_sl_legs"),
            "n_sl_with_prior_shadow": d.get("n_sl_with_prior_shadow"),
            "sum_delta_usd_best_shadow_vs_sl": d.get(
                "sum_delta_usd_best_shadow_vs_sl"
            ),
            "ready_for_settings_flip_review": d.get("ready_for_settings_flip_review"),
            "promotion_per_regime": (d.get("promotion") or {}).get("per_regime"),
        }
    except Exception as e:
        return {"available": False, "error": str(e)[:200]}


def evaluate_gates(
    *,
    collection: dict[str, Any],
    status: dict[str, Any],
    map_cfg: dict[str, Any],
    tp_cfg: dict[str, Any],
    now: datetime | None = None,
    days_needed: float = DEFAULT_DAYS_NEEDED,
    min_episodes: int = MIN_EPISODES_PER_REGIME,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    started = _parse_ts(collection.get("started_at"))
    shadow_days = None
    if started:
        shadow_days = round((now - started).total_seconds() / 86400.0, 2)
    prom = status.get("promotion") or {}
    if prom.get("shadow_days") is not None:
        try:
            shadow_days = float(prom["shadow_days"])
        except Exception:
            pass

    by_reg = collection.get("by_regime") or {}
    days_seen = collection.get("days_regime_seen") or {}
    per_regime: dict[str, Any] = {}
    regimes_pass_episodes: list[str] = []
    for reg in REQUIRED_REGIMES:
        block = by_reg.get(reg) or {}
        ep = int(block.get("would_fire_episodes") or 0)
        dcount = len(days_seen.get(reg) or [])
        # Prefer status promotion closed-leg hints when present
        st_reg = (prom.get("per_regime") or {}).get(reg) or {}
        closed = st_reg.get("closed_legs_observed")
        closed_need = st_reg.get("closed_legs_needed") or 5
        ep_ok = ep >= min_episodes
        if ep_ok:
            regimes_pass_episodes.append(reg)
        per_regime[reg] = {
            "would_fire_episodes": ep,
            "episodes_needed": min_episodes,
            "episodes_ok": ep_ok,
            "distinct_days_seen": dcount if dcount else st_reg.get("distinct_days_seen"),
            "closed_legs_observed": closed,
            "closed_legs_needed": closed_need,
            "status_ready_hint": bool(st_reg.get("ready_hint")),
            "by_kind": block.get("by_kind") or {},
            "pairs": block.get("pairs") or {},
        }

    n_regimes_episode_ok = len(regimes_pass_episodes)
    multi_regime_ok = all(r in regimes_pass_episodes for r in REQUIRED_REGIMES)
    days_ok = shadow_days is not None and shadow_days >= days_needed
    early_ok = shadow_days is not None and shadow_days >= EARLY_REVIEW_DAYS

    mode = str(status.get("mode") or map_cfg.get("mode") or "shadow")
    live_apply_status = bool(status.get("live_apply"))
    # Map hard-block + config
    map_mode = str(map_cfg.get("mode") or "shadow")
    map_live = bool(map_cfg.get("live_apply"))
    auto_promote = bool(map_cfg.get("auto_promote"))
    tp = tp_cfg.get("take_profit") or {}
    tp_mode = str(tp.get("mode") or "shadow")

    hard_blocks: list[str] = []
    if auto_promote:
        hard_blocks.append("map auto_promote=true (must be false)")
    if map_live or live_apply_status:
        hard_blocks.append("live_apply already true somewhere — audit before promote talk")
    if tp_mode == "live":
        hard_blocks.append("global take_profit.mode=live")

    # Gate checklist
    checks = {
        "shadow_days_ge_60": {
            "pass": bool(days_ok),
            "value": shadow_days,
            "need": days_needed,
        },
        "shadow_days_ge_45_early": {
            "pass": bool(early_ok),
            "value": shadow_days,
            "need": EARLY_REVIEW_DAYS,
        },
        "flat_episodes_ge_min": {
            "pass": bool(per_regime["flat"]["episodes_ok"]),
            "value": per_regime["flat"]["would_fire_episodes"],
            "need": min_episodes,
        },
        "bull_episodes_ge_min": {
            "pass": bool(per_regime["bull"]["episodes_ok"]),
            "value": per_regime["bull"]["would_fire_episodes"],
            "need": min_episodes,
        },
        "bear_episodes_ge_min": {
            "pass": bool(per_regime["bear"]["episodes_ok"]),
            "value": per_regime["bear"]["would_fire_episodes"],
            "need": min_episodes,
        },
        "multi_regime_bull_bear_flat": {
            "pass": multi_regime_ok,
            "value": regimes_pass_episodes,
            "need": list(REQUIRED_REGIMES),
        },
        "mode_still_shadow": {
            "pass": mode in ("shadow", "off") and map_mode in ("shadow", "off"),
            "value": {"status_mode": mode, "map_mode": map_mode},
            "need": "shadow|off",
        },
        "auto_promote_false": {
            "pass": not auto_promote,
            "value": auto_promote,
            "need": False,
        },
        "tp_not_live": {
            "pass": tp_mode != "live",
            "value": tp_mode,
            "need": "shadow|off",
        },
        "no_hard_blocks": {
            "pass": len(hard_blocks) == 0,
            "value": hard_blocks,
            "need": [],
        },
    }

    # Decision enum (product)
    if hard_blocks:
        decision = "blocked_misconfig"
        go = "NO-GO — config hard block; fix before any promote discussion"
    elif multi_regime_ok and days_ok and not hard_blocks:
        decision = "ready_for_brad_review"
        go = (
            "REVIEW ONLY — collection gates met on paper; "
            "still needs Brad OK + offline re-study. Not auto-live."
        )
    elif n_regimes_episode_ok >= 1 and early_ok and not multi_regime_ok:
        decision = "collecting_partial_regime"
        go = (
            "NO-GO live exits — partial regime evidence only "
            f"({', '.join(regimes_pass_episodes) or 'none'}); need bull+bear+flat."
        )
    elif not days_ok:
        decision = "collecting_calendar"
        go = (
            f"NO-GO live exits — calendar "
            f"{shadow_days if shadow_days is not None else '?'}/{days_needed}d; shadow only."
        )
    else:
        decision = "collecting"
        go = "NO-GO live exits — keep shadow; gates incomplete."

    # Pass count for scoreboard UI
    core_keys = [
        "shadow_days_ge_60",
        "flat_episodes_ge_min",
        "bull_episodes_ge_min",
        "bear_episodes_ge_min",
        "multi_regime_bull_bear_flat",
        "mode_still_shadow",
        "auto_promote_false",
        "tp_not_live",
        "no_hard_blocks",
    ]
    n_pass = sum(1 for k in core_keys if checks[k]["pass"])
    n_core = len(core_keys)

    return {
        "shadow_days": shadow_days,
        "days_needed": days_needed,
        "min_episodes_per_regime": min_episodes,
        "per_regime": per_regime,
        "regimes_episode_ok": regimes_pass_episodes,
        "n_regimes_episode_ok": n_regimes_episode_ok,
        "checks": checks,
        "core_pass": n_pass,
        "core_total": n_core,
        "hard_blocks": hard_blocks,
        "decision": decision,
        "go_no_go": go,
        "live_tp_allowed": False,  # never true from this scoreboard alone
        "brad_ok_required": True,
        "regime_now": status.get("regime"),
        "plain_english_status": status.get("plain_english"),
        "map_mode": map_mode,
        "tp_mode": tp_mode,
        "status_mode": mode,
    }


def build_scoreboard(
    *,
    now: datetime | None = None,
    include_sl_cf: bool = True,
    collection_path: Path | None = None,
    status_path: Path | None = None,
    map_path: Path | None = None,
    tp_path: Path | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    collection = _load(collection_path or COLLECTION)
    status = _load(status_path or STATUS)
    map_cfg = _load(map_path or MAP_CFG)
    tp_cfg = _load(tp_path or TP_CFG)

    gates = evaluate_gates(
        collection=collection,
        status=status,
        map_cfg=map_cfg,
        tp_cfg=tp_cfg,
        now=now,
    )
    sl_cf = _sl_cf_summary() if include_sl_cf else {"available": False, "skipped": True}

    # Optional: rescue-rate style from CF
    rescue = None
    if sl_cf.get("available"):
        n_sl = int(sl_cf.get("n_sl_legs") or 0)
        n_sig = int(sl_cf.get("n_sl_with_prior_shadow") or 0)
        rescue = {
            "n_sl_legs": n_sl,
            "n_with_prior_shadow": n_sig,
            "prior_shadow_rate": round(n_sig / n_sl, 3) if n_sl else None,
            "sum_delta_usd_best_shadow_vs_sl": sl_cf.get(
                "sum_delta_usd_best_shadow_vs_sl"
            ),
            "note": (
                "Positive sum_delta ≈ early shadow exit would have beaten riding to SL "
                "(order-of-magnitude; not a live order)."
            ),
        }

    return {
        "schema": "exit_promote_scoreboard_v1",
        "gap_id": "P6-SCALE-GAP-01-EXIT-PROMOTE-SCOREBOARD-20260816",
        "as_of": now.isoformat().replace("+00:00", "Z"),
        "collection_started_at": collection.get("started_at"),
        "gates": gates,
        "sl_counterfactual": sl_cf,
        "rescue_summary": rescue,
        "open_would_fire_now": [
            {
                "pair": s.get("pair"),
                "kind": s.get("kind"),
                "r": s.get("r"),
            }
            for s in (status.get("signals") or [])[:12]
        ],
        "open_peak_r": status.get("peak_r") or {},
        "glossary": {
            "would_fire_episode": "Pair+kind shadow signal with ≥~30m gap (not every tick)",
            "SL": "Exchange stop ~3% — live floor",
            "go_no_go": "Live TP/map flip readiness — never auto-enables",
            "decision": gates.get("decision"),
        },
        "flag": _flag_from_decision(gates.get("decision")),
    }


def _flag_from_decision(decision: str | None) -> str:
    d = decision or ""
    if d == "ready_for_brad_review":
        return "NEEDS_DECIDE"
    if d == "blocked_misconfig":
        return "NEEDS_VALIDATE"
    if d in ("collecting", "collecting_calendar", "collecting_partial_regime"):
        return "COLLECTING"
    return "OK"


def render_md(d: dict[str, Any]) -> str:
    g = d.get("gates") or {}
    lines = [
        "# Exit promote scoreboard (GAP-01)",
        "",
        f"**As of:** {d.get('as_of')}  ",
        f"**Schema:** `{d.get('schema')}`  ",
        f"**MASTER:** `{d.get('gap_id')}`  ",
        "",
        "## Plain English",
        "",
        f"**Go/no-go:** {g.get('go_no_go')}  ",
        f"**Decision enum:** `{g.get('decision')}`  ",
        f"**Flag:** `{d.get('flag')}`  ",
        f"**Live TP allowed by this board alone:** **{g.get('live_tp_allowed')}** "
        f"(Brad OK still required: {g.get('brad_ok_required')})",
        "",
        f"Shadow calendar: **{g.get('shadow_days')}** / {g.get('days_needed')} days  ",
        f"Regime now: **{g.get('regime_now')}**  ",
        f"Core gates: **{g.get('core_pass')}/{g.get('core_total')}** pass  ",
        "",
    ]
    pe = g.get("plain_english_status")
    if pe:
        lines.extend([f"> {pe}", ""])

    lines.extend(
        [
            "## Per-regime episodes",
            "",
            "| Regime | Episodes | Need | OK | Days seen | Closed legs |",
            "|--------|----------|------|----|-----------|-------------|",
        ]
    )
    for reg in REQUIRED_REGIMES:
        pr = (g.get("per_regime") or {}).get(reg) or {}
        lines.append(
            f"| {reg} | {pr.get('would_fire_episodes')} | {pr.get('episodes_needed')} | "
            f"{'yes' if pr.get('episodes_ok') else 'no'} | {pr.get('distinct_days_seen')} | "
            f"{pr.get('closed_legs_observed')}/{pr.get('closed_legs_needed')} |"
        )

    lines.extend(["", "## Gate checklist", ""])
    for k, c in (g.get("checks") or {}).items():
        mark = "PASS" if c.get("pass") else "FAIL"
        lines.append(f"- **{mark}** `{k}` — value=`{c.get('value')}` need=`{c.get('need')}`")

    rs = d.get("rescue_summary")
    if rs:
        lines.extend(
            [
                "",
                "## SL vs prior shadow (rescue sketch)",
                "",
                f"- SL legs in CF window: **{rs.get('n_sl_legs')}**",
                f"- With prior shadow signal: **{rs.get('n_with_prior_shadow')}** "
                f"(rate {rs.get('prior_shadow_rate')})",
                f"- Sum Δ$ best-shadow vs SL: **{rs.get('sum_delta_usd_best_shadow_vs_sl')}**",
                f"- Note: {rs.get('note')}",
            ]
        )

    ow = d.get("open_would_fire_now") or []
    if ow:
        lines.extend(["", "## Open would-fire now", ""])
        for s in ow:
            lines.append(f"- {s.get('pair')} · {s.get('kind')} · r={s.get('r')}")

    lines.extend(
        [
            "",
            "## Non-goals",
            "",
            "- Does **not** set `take_profit.mode=live` or map `live_apply`",
            "- Does **not** replace multi-regime offline threshold re-study before Brad OK",
            "",
            f"Artifacts: `{OUT_JSON}` · `{OUT_MD}`",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Exit promote scoreboard (GAP-01)")
    ap.add_argument("--no-sl-cf", action="store_true", help="Skip SL counterfactual import")
    ap.add_argument("--stdout-only", action="store_true")
    args = ap.parse_args(argv)

    d = build_scoreboard(include_sl_cf=not args.no_sl_cf)
    md = render_md(d)
    if not args.stdout_only:
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_MD.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
        OUT_MD.write_text(md, encoding="utf-8")

    g = d.get("gates") or {}
    print(f"EXIT_PROMOTE decision={g.get('decision')} flag={d.get('flag')}")
    print(g.get("go_no_go"))
    print(
        f"core_gates={g.get('core_pass')}/{g.get('core_total')} "
        f"shadow_days={g.get('shadow_days')} regimes_ok={g.get('regimes_episode_ok')}"
    )
    if not args.stdout_only:
        print(f"wrote {OUT_JSON}")
        print(f"wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
