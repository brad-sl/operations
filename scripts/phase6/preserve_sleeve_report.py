#!/usr/bin/env python3
"""Summarize Preserve sleeve JSONL log → plain-English returns snapshot."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / "data/state/preserve_sleeve_log.jsonl"
STATE = ROOT / "data/state/preserve_hold_state.json"


def main() -> int:
    rows = []
    if LOG.exists():
        for line in LOG.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    st = {}
    if STATE.exists():
        try:
            st = json.loads(STATE.read_text())
        except Exception:
            pass

    print("=== Preserve sleeve monitor ===")
    print(f"state_armed: {st.get('armed')}  micro: {st.get('soak_micro')}  e1: {st.get('e1_order_id')}")
    print(f"arm_vwap: {st.get('arm_vwap')}  arm_qty: {st.get('arm_qty')}  e1_stop: {st.get('e1_stop_price')}")
    if not rows:
        print("No log rows yet:", LOG)
        return 0
    first, last = rows[0], rows[-1]
    print(f"log_rows: {len(rows)}")
    print(f"first_ts: {first.get('ts')}  last_ts: {last.get('ts')}")
    print(
        f"last: usd={last.get('preserve_usd')} ret_vs_arm={last.get('ret_vs_arm')} "
        f"pnl_usd={last.get('pnl_usd')} e1_open={last.get('e1_open')} badge={last.get('badge')}"
    )
    # simple path stats on ret_vs_arm
    rets = [r.get("ret_vs_arm") for r in rows if r.get("ret_vs_arm") is not None]
    if rets:
        print(f"ret_vs_arm min={min(rets):.6f} max={max(rets):.6f} last={rets[-1]:.6f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
