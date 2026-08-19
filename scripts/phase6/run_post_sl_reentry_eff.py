#!/usr/bin/env python3
"""GAP-05: offline post-SL re-entry effectiveness on real ledger.

Frozen bars (MASTER P6-SCALE-GAP-05):
  - primary_window: real ledger post-SL episodes
  - min_n: ≥15 re-entry episodes or honest inconclusive
  - metrics: rebuy@24/48/72h, second SL rate, $ PnL recycle
  - enum: hold_ok | tighten | gap_in_code | inconclusive
  - live_promote_allowed: false

No live config / order writes.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEDGER = ROOT / "trades" / "phase6_trades.jsonl"
DEFAULT_OUT_JSON = ROOT / "data" / "state" / "post_sl_reentry_eff_latest.json"
DEFAULT_OUT_MD = ROOT / "reports" / "POST_SL_REENTRY_EFF_LATEST.md"
DEFAULT_DECIDE = ROOT / "reports" / "DECIDE_P6_SCALE_GAP_05_POST_SL_REENTRY_EFF_20260818.md"

SL_REASONS = {
    "stop_loss_exchange",
    "stop_loss",
    "stop_loss_fill",
    "protective_stop",
}
BUY_SIDES = {"BUY", "buy"}
SELL_SIDES = {"SELL", "sell"}


def parse_ts(raw: Any) -> datetime | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def is_sl_sell(row: dict) -> bool:
    side = str(row.get("side") or "").upper()
    if side not in {"SELL"}:
        return False
    reason = str(row.get("reason") or row.get("exit_reason") or "").strip()
    return reason in SL_REASONS or reason.startswith("stop_loss")


def is_buy(row: dict) -> bool:
    return str(row.get("side") or "") in BUY_SIDES


def notional_usd(row: dict) -> float | None:
    for k in ("usd_value", "notional_usd", "filled_value_usd"):
        v = row.get(k)
        if v is not None:
            try:
                return abs(float(v))
            except (TypeError, ValueError):
                pass
    try:
        qty = float(row.get("qty") or 0)
        px = float(row.get("exit_price") or row.get("entry_price") or 0)
        if qty and px:
            return abs(qty * px)
    except (TypeError, ValueError):
        return None
    return None


def pnl_usd(row: dict) -> float | None:
    v = row.get("pnl")
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


@dataclass
class Episode:
    pair: str
    sl_ts: str
    sl_pnl_usd: float | None
    sl_notional_usd: float | None
    sl_order_id: str | None
    rebuy: bool
    rebuy_hours: float | None
    rebuy_ts: str | None
    rebuy_within_24h: bool
    rebuy_within_48h: bool
    rebuy_within_72h: bool
    second_sl: bool
    second_sl_hours_after_rebuy: float | None
    second_sl_pnl_usd: float | None
    dust_sl: bool


def load_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    rows.sort(key=lambda r: (parse_ts(r.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc)).isoformat())
    return rows


def build_episodes(
    rows: list[dict],
    *,
    dust_usd: float = 5.0,
    max_rebuy_look_hours: float = 14 * 24,
) -> list[Episode]:
    # Index chronological events per pair
    by_pair: dict[str, list[tuple[datetime, dict]]] = {}
    for r in rows:
        pair = str(r.get("pair") or "")
        ts = parse_ts(r.get("timestamp"))
        if not pair or ts is None:
            continue
        by_pair.setdefault(pair, []).append((ts, r))

    episodes: list[Episode] = []
    for pair, events in by_pair.items():
        for i, (ts, r) in enumerate(events):
            if not is_sl_sell(r):
                continue
            notion = notional_usd(r)
            dust = notion is not None and notion < dust_usd
            rebuy = False
            rebuy_hours = None
            rebuy_ts = None
            second_sl = False
            second_sl_h = None
            second_sl_pnl = None
            rebuy_row_idx = None
            for j in range(i + 1, len(events)):
                ts2, r2 = events[j]
                hours = (ts2 - ts).total_seconds() / 3600.0
                if hours > max_rebuy_look_hours:
                    break
                if is_buy(r2):
                    rebuy = True
                    rebuy_hours = hours
                    rebuy_ts = ts2.isoformat().replace("+00:00", "Z")
                    rebuy_row_idx = j
                    break
            if rebuy and rebuy_row_idx is not None:
                for k in range(rebuy_row_idx + 1, len(events)):
                    ts3, r3 = events[k]
                    if not is_sl_sell(r3):
                        continue
                    # next SL after rebuy = second SL on recycle path
                    second_sl = True
                    second_sl_h = (ts3 - parse_ts(rebuy_ts)).total_seconds() / 3600.0  # type: ignore[arg-type]
                    second_sl_pnl = pnl_usd(r3)
                    break
            episodes.append(
                Episode(
                    pair=pair,
                    sl_ts=ts.isoformat().replace("+00:00", "Z"),
                    sl_pnl_usd=pnl_usd(r),
                    sl_notional_usd=notion,
                    sl_order_id=str(r.get("order_id") or "") or None,
                    rebuy=rebuy,
                    rebuy_hours=round(rebuy_hours, 3) if rebuy_hours is not None else None,
                    rebuy_ts=rebuy_ts,
                    rebuy_within_24h=bool(rebuy and rebuy_hours is not None and rebuy_hours <= 24),
                    rebuy_within_48h=bool(rebuy and rebuy_hours is not None and rebuy_hours <= 48),
                    rebuy_within_72h=bool(rebuy and rebuy_hours is not None and rebuy_hours <= 72),
                    second_sl=second_sl,
                    second_sl_hours_after_rebuy=round(second_sl_h, 3) if second_sl_h is not None else None,
                    second_sl_pnl_usd=second_sl_pnl,
                    dust_sl=dust,
                )
            )
    return episodes


def summarize(episodes: list[Episode], *, min_n: int = 15, block_hours: float = 72.0) -> dict[str, Any]:
    # Primary analysis set: non-dust SL episodes (product path)
    core = [e for e in episodes if not e.dust_sl]
    re_eps = [e for e in core if e.rebuy]
    n_sl = len(core)
    n_re = len(re_eps)
    def rate(pred) -> float | None:
        if n_sl == 0:
            return None
        return round(sum(1 for e in core if pred(e)) / n_sl, 4)

    rebuy_24 = rate(lambda e: e.rebuy_within_24h)
    rebuy_48 = rate(lambda e: e.rebuy_within_48h)
    rebuy_72 = rate(lambda e: e.rebuy_within_72h)
    rebuy_any = rate(lambda e: e.rebuy)

    second_among_rebuy = None
    if n_re:
        second_among_rebuy = round(sum(1 for e in re_eps if e.second_sl) / n_re, 4)

    sl_pnl = [e.sl_pnl_usd for e in core if e.sl_pnl_usd is not None]
    re_sl_pnl = [e.sl_pnl_usd for e in re_eps if e.sl_pnl_usd is not None]
    second_pnl = [e.second_sl_pnl_usd for e in re_eps if e.second_sl and e.second_sl_pnl_usd is not None]

    sum_sl = round(sum(sl_pnl), 4) if sl_pnl else None
    sum_sl_rebuy_path = round(sum(re_sl_pnl), 4) if re_sl_pnl else None
    sum_second = round(sum(second_pnl), 4) if second_pnl else None
    recycle_stack = None
    if sum_sl_rebuy_path is not None:
        recycle_stack = round(sum_sl_rebuy_path + (sum_second or 0.0), 4)

    early_rebuy = [e for e in re_eps if e.rebuy_hours is not None and e.rebuy_hours < block_hours]
    early_frac = round(len(early_rebuy) / n_re, 4) if n_re else None

    # Decision logic (honest, offline only)
    enum = "inconclusive"
    reasons: list[str] = []
    if n_re < min_n and n_sl < min_n:
        enum = "inconclusive"
        reasons.append(f"n_reentry={n_re} n_sl_core={n_sl} < min_n={min_n}")
    elif n_re < min_n:
        enum = "inconclusive"
        reasons.append(f"re-entry episodes n={n_re} < min_n={min_n} (core SL n={n_sl})")
    else:
        # Enough re-entry episodes
        high_second = (second_among_rebuy or 0) >= 0.35
        high_early = (early_frac or 0) >= 0.50
        # Policy enforce=72h hold: many rebuys inside window while config says hold → gap or tighten evidence
        if high_early and high_second:
            enum = "tighten"
            reasons.append(
                f"early_rebuy_frac<{block_hours}h={early_frac} and second_sl_rate={second_among_rebuy} — recycle wound active"
            )
        elif high_early and (second_among_rebuy or 0) >= 0.20:
            enum = "tighten"
            reasons.append(
                f"majority/high early rebuy ({early_frac}) with material second-SL ({second_among_rebuy})"
            )
        elif high_early and (second_among_rebuy or 0) < 0.20:
            # Early rebuy but low second SL — hold may be overkill OR luck; don't claim hold_ok
            enum = "inconclusive"
            reasons.append(
                f"early_rebuy_frac={early_frac} but second_sl_rate={second_among_rebuy} low — less-loss not proven either way"
            )
        elif not high_early and not high_second:
            enum = "hold_ok"
            reasons.append(
                f"rebuy mostly after {block_hours}h window and second_sl_rate={second_among_rebuy} modest — hold discipline not creating obvious recycle wound"
            )
        else:
            enum = "inconclusive"
            reasons.append("mixed early/second-SL pattern without clear less-loss proof")

        # Stacked loss on recycle path
        if recycle_stack is not None and recycle_stack < -15 and high_second:
            if enum == "hold_ok":
                enum = "tighten"
            reasons.append(f"recycle_stack_pnl_usd={recycle_stack} with elevated second SL")

    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "ledger": str(DEFAULT_LEDGER),
        "config_note": {
            "stop_loss_exchange_hold_cash": True,
            "stop_loss_exchange_block_rebuy_hours": block_hours,
            "source": "config/trading_config_phase6.json (read-only note)",
        },
        "filters": {
            "dust_usd_lt": 5.0,
            "max_rebuy_look_hours": 14 * 24,
            "min_n": min_n,
        },
        "counts": {
            "sl_episodes_all": len(episodes),
            "sl_episodes_core_non_dust": n_sl,
            "sl_dust": sum(1 for e in episodes if e.dust_sl),
            "reentry_episodes": n_re,
            "no_rebuy_in_lookback": n_sl - n_re,
            "second_sl_after_rebuy": sum(1 for e in re_eps if e.second_sl),
            "early_rebuy_lt_block_h": len(early_rebuy),
        },
        "rates_of_core_sl": {
            "rebuy_any": rebuy_any,
            "rebuy_within_24h": rebuy_24,
            "rebuy_within_48h": rebuy_48,
            "rebuy_within_72h": rebuy_72,
        },
        "rates_of_reentry": {
            "second_sl_rate": second_among_rebuy,
            "early_rebuy_frac_lt_block_h": early_frac,
        },
        "pnl_usd": {
            "sum_sl_exit_core": sum_sl,
            "sum_sl_exit_on_rebuy_path": sum_sl_rebuy_path,
            "sum_second_sl": sum_second,
            "recycle_stack_first_sl_plus_second_sl": recycle_stack,
            "note": "Ledger pnl fields only; not mark-to-market hold-cash CF",
        },
        "enum": enum,
        "enum_reasons": reasons,
        "live_promote_allowed": False,
        "episodes_sample": [asdict(e) for e in re_eps[:25]],
        "episodes_all_reentry": [asdict(e) for e in re_eps],
    }


def render_md(rep: dict[str, Any]) -> str:
    c = rep["counts"]
    r = rep["rates_of_core_sl"]
    rr = rep["rates_of_reentry"]
    p = rep["pnl_usd"]
    lines = [
        "# Post-SL re-entry effectiveness (GAP-05)",
        "",
        f"**as_of:** {rep['as_of']}",
        f"**enum:** `{rep['enum']}`",
        f"**live_promote:** {rep['live_promote_allowed']}",
        "",
        "## Counts (non-dust SL core)",
        f"- SL episodes (core): **{c['sl_episodes_core_non_dust']}** (dust excluded: {c['sl_dust']})",
        f"- Re-entry episodes: **{c['reentry_episodes']}**",
        f"- No rebuy in lookback: {c['no_rebuy_in_lookback']}",
        f"- Second SL after rebuy: **{c['second_sl_after_rebuy']}**",
        f"- Early rebuy (<{rep['config_note']['stop_loss_exchange_block_rebuy_hours']}h): **{c['early_rebuy_lt_block_h']}**",
        "",
        "## Rates (of core SL)",
        f"- rebuy any: {r['rebuy_any']}",
        f"- rebuy@24h: {r['rebuy_within_24h']}",
        f"- rebuy@48h: {r['rebuy_within_48h']}",
        f"- rebuy@72h: {r['rebuy_within_72h']}",
        "",
        "## Rates (of re-entry episodes)",
        f"- second_sl_rate: **{rr['second_sl_rate']}**",
        f"- early_rebuy_frac: **{rr['early_rebuy_frac_lt_block_h']}**",
        "",
        "## $ PnL (ledger fields)",
        f"- sum SL exit (core): {p['sum_sl_exit_core']}",
        f"- sum SL on rebuy path: {p['sum_sl_exit_on_rebuy_path']}",
        f"- sum second SL: {p['sum_second_sl']}",
        f"- recycle stack (1st+2nd SL): **{p['recycle_stack_first_sl_plus_second_sl']}**",
        f"- _{p['note']}_",
        "",
        "## Enum reasons",
    ]
    for x in rep.get("enum_reasons") or []:
        lines.append(f"- {x}")
    lines += [
        "",
        "## Policy note",
        f"- Config (read-only): hold_cash={rep['config_note']['stop_loss_exchange_hold_cash']} "
        f"block_rebuy_hours={rep['config_note']['stop_loss_exchange_block_rebuy_hours']}",
        "- This report does **not** shorten cooldown or touch live config.",
        "",
    ]
    return "\n".join(lines) + "\n"


def render_decide(rep: dict[str, Any]) -> str:
    return f"""# Decide packet — P6-SCALE-GAP-05-POST-SL-REENTRY-EFF-20260816

**Date:** 2026-08-18  
**Outcome enum:** **`{rep['enum']}`**  
**Live promote:** false (hard)  
**Live book / config:** unchanged

## Hypothesis
72h hold-cash ISO ≠ proven less-loss. Need second-SL rate and $ recycle under enforce hold on real ledger.

## Evidence (real ledger)

| Gate | Result |
|------|--------|
| min_n re-entry ≥15 | **{'PASS' if rep['counts']['reentry_episodes'] >= 15 else 'FAIL'}** (n={rep['counts']['reentry_episodes']}) |
| rebuy@24/48/72h | {rep['rates_of_core_sl']['rebuy_within_24h']} / {rep['rates_of_core_sl']['rebuy_within_48h']} / {rep['rates_of_core_sl']['rebuy_within_72h']} (of core SL) |
| second SL rate (of rebuys) | **{rep['rates_of_reentry']['second_sl_rate']}** |
| early rebuy &lt;72h frac | **{rep['rates_of_reentry']['early_rebuy_frac_lt_block_h']}** |
| recycle stack $ | {rep['pnl_usd']['recycle_stack_first_sl_plus_second_sl']} |

Artifacts:
- `data/state/post_sl_reentry_eff_latest.json`
- `reports/POST_SL_REENTRY_EFF_LATEST.md`
- `scripts/phase6/run_post_sl_reentry_eff.py`
- `scripts/phase6/test_isolation_post_sl_reentry_eff.py`

## Decision
- **CR:** `{rep['enum']}`
- **Reasons:** {'; '.join(rep.get('enum_reasons') or [])}
- **Must not:** shorten cooldown to catch bounce; live promote; capital rewrite

## Follow-on
- If `tighten`: offline design only for stronger post-SL block / pair cooldown — **Brad gate** before any config write
- If `hold_ok`: keep 72h; monitor weekly re-run of this script
- If `inconclusive`: collect more episodes; do not flip policy
- Staged next fleet lever: GAP-03 cap scope matrix (from BoN runner-up)
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    ap.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    ap.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    ap.add_argument("--out-decide", type=Path, default=DEFAULT_DECIDE)
    ap.add_argument("--min-n", type=int, default=15)
    ap.add_argument("--block-hours", type=float, default=72.0)
    args = ap.parse_args(argv)

    rows = load_rows(args.ledger)
    episodes = build_episodes(rows)
    rep = summarize(episodes, min_n=args.min_n, block_hours=args.block_hours)
    rep["ledger"] = str(args.ledger.resolve())

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    # Full episodes in JSON; MD is summary
    args.out_json.write_text(json.dumps(rep, indent=2) + "\n")
    args.out_md.write_text(render_md(rep))
    args.out_decide.write_text(render_decide(rep))

    print(json.dumps({
        "enum": rep["enum"],
        "counts": rep["counts"],
        "rates_of_core_sl": rep["rates_of_core_sl"],
        "rates_of_reentry": rep["rates_of_reentry"],
        "pnl_usd": rep["pnl_usd"],
        "enum_reasons": rep["enum_reasons"],
        "out_json": str(args.out_json),
        "out_md": str(args.out_md),
        "out_decide": str(args.out_decide),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
