#!/usr/bin/env python3
"""Isolation: structure BOS exit (LINK-shaped path + gates)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.structure_bos_exit import (
    normalize_candles,
    walk_long_structure_bos,
    evaluate_position_bos,
    load_bos_config,
)


def _bar(t, o, h, l, c):
    return {"t": float(t), "o": o, "h": h, "l": l, "c": c, "v": 1.0}


def link_shaped_path():
    """
    Synthetic 1h-ish path:
    rise with HL → small pullback holds → new high → hard break of HL → continue down.
    entry at 10.
    """
    rows = []
    t0 = 1_700_000_000.0
    # climb 10 → 12 with higher lows
    px = 10.0
    for i in range(20):
        o = px
        h = px + 0.15
        l = px - 0.05
        c = px + 0.12
        rows.append(_bar(t0 + i * 3600, o, h, l, c))
        px = c
    # small pullback (holds structure) ~ to 11.6
    for i in range(20, 26):
        o = px
        h = px + 0.05
        l = px - 0.12
        c = px - 0.08
        rows.append(_bar(t0 + i * 3600, o, h, l, c))
        px = c
    pullback_low = min(r["l"] for r in rows[20:26])
    # continue rise to new high ~13
    for i in range(26, 40):
        o = px
        h = px + 0.18
        l = px - 0.04
        c = px + 0.14
        rows.append(_bar(t0 + i * 3600, o, h, l, c))
        px = c
    peak = max(r["h"] for r in rows)
    # hard turn down — break last HL and keep going
    for i in range(40, 55):
        o = px
        h = px + 0.02
        l = px - 0.25
        c = px - 0.20
        rows.append(_bar(t0 + i * 3600, o, h, l, c))
        px = c
    return rows, pullback_low, peak


def main() -> int:
    fails = []
    rows, pb_low, peak = link_shaped_path()
    entry = 10.0
    res = walk_long_structure_bos(
        rows,
        entry_price=entry,
        entry_idx=0,
        pair="LINK-USD",
        swing_left=2,
        swing_right=2,
        arm_mfe_pct=0.04,
        confirm_closes=1,
    )
    if not res.armed:
        fails.append("expected armed after run")
    if not res.fired:
        fails.append(f"expected BOS fire on hard turn, got {res}")
    else:
        if res.exit_price >= res.structure_low:
            fails.append(f"exit should be below structure_low {res.structure_low} got {res.exit_price}")
        if res.ret_vs_entry_pct <= 0 and res.mfe_pct > 0.1:
            # may still be green or small red depending path — just log
            pass
        print(
            f"BOS OK exit={res.exit_price:.3f} struct_low={res.structure_low:.3f} "
            f"mfe={res.mfe_pct:.3f} ret={res.ret_vs_entry_pct:.3f} giveback={res.giveback_from_peak_pct:.3f}"
        )

    # No fire if only mild pullback (truncate before hard dump)
    mild = rows[:40]
    res2 = walk_long_structure_bos(
        mild,
        entry_price=entry,
        entry_idx=0,
        arm_mfe_pct=0.04,
        confirm_closes=1,
    )
    if res2.fired:
        fails.append(f"should not BOS on healthy pullback-only path: {res2}")
    else:
        print("no_bos_on_healthy_pullback OK", "armed=", res2.armed)

    # Never arm → no fire on dump from entry
    dump = [_bar(1_700_000_000 + i * 3600, 10, 10.05, 9.5 - i * 0.05, 9.6 - i * 0.05) for i in range(30)]
    res3 = walk_long_structure_bos(dump, entry_price=10.0, entry_idx=0, arm_mfe_pct=0.04)
    if res3.fired:
        fails.append("unarmed dump must not BOS (SL owns this)")
    else:
        print("unarmed_no_bos OK")

    # normalize coinbase shape
    raw = [[1000, 9.0, 11.0, 10.0, 10.5, 1.0], [1001, 10.0, 12.0, 10.5, 11.5, 1.0]]
    n = normalize_candles(raw)
    if n[0]["c"] != 10.5 or n[0]["l"] != 9.0:
        fails.append(f"normalize bad {n}")
    else:
        print("normalize OK")

    cfg = load_bos_config()
    if cfg.get("mode") != "shadow":
        fails.append("default mode must be shadow")
    else:
        print("config_shadow OK")

    # evaluate_position_bos wrapper
    r4 = evaluate_position_bos(pair="X", candles=rows, entry_price=10.0, cfg=cfg)
    if not r4.fired:
        fails.append("evaluate_position_bos should fire on full path")
    else:
        print("evaluate wrapper OK")

    if fails:
        print("FAIL")
        for f in fails:
            print(" -", f)
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
