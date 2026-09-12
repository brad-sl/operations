#!/usr/bin/env python3
"""CLI: novelty class gate board + promote/demote/unpin."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.novelty_class_gate import (
    annotate_swap,
    build_board,
    demote_pair,
    evaluate_pair_novelty,
    format_board_lines,
    load_registry,
    promote_pair,
    unpin_pair,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Novelty class gate (reversible meme→contender funnel)")
    ap.add_argument("--board", action="store_true", help="Build and print board")
    ap.add_argument("--pair", type=str, default="", help="Evaluate one pair")
    ap.add_argument("--promote", type=str, default="", help="Brad GO graduate pair")
    ap.add_argument("--demote", type=str, default="", help="Demote pair to restricted")
    ap.add_argument("--hard-pin", action="store_true", help="With --demote: hard pin block")
    ap.add_argument("--unpin", type=str, default="", help="Clear hard/force restricted pin")
    ap.add_argument("--force", action="store_true", help="With --promote: also force_graduated list")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--annotate-json", type=str, default="", help="Path to swap JSON to annotate")
    args = ap.parse_args()

    if args.promote:
        out = promote_pair(args.promote, as_force=bool(args.force))
        print(json.dumps(out, indent=2) if args.json else out)
        return 0
    if args.demote:
        out = demote_pair(args.demote, hard_pin=bool(args.hard_pin))
        print(json.dumps(out, indent=2) if args.json else out)
        return 0
    if args.unpin:
        out = unpin_pair(args.unpin)
        print(json.dumps(out, indent=2) if args.json else out)
        return 0
    if args.annotate_json:
        raw = json.loads(Path(args.annotate_json).read_text())
        if isinstance(raw, list):
            out = [annotate_swap(x, enforce=True) for x in raw]
        else:
            out = annotate_swap(raw, enforce=True)
        print(json.dumps(out, indent=2))
        return 0
    if args.pair:
        v = evaluate_pair_novelty(args.pair, enforce=True, persist_first_seen=True)
        print(json.dumps(v.to_dict(), indent=2) if args.json else v)
        return 0

    # default board
    board = build_board(write=True)
    if args.json:
        print(json.dumps(board, indent=2))
    else:
        print(format_board_lines(board))
        print(f"registry={load_registry().get('updated_at')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
