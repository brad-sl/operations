#!/usr/bin/env python3
"""CLI: marketdata D1–D4 — init, thin 1d ingest, status, regime smoke.

  PYTHONPATH=. python3 scripts/phase6/run_marketdata_btc_1d.py thin
  PYTHONPATH=. python3 scripts/phase6/run_marketdata_btc_1d.py universe
  PYTHONPATH=. python3 scripts/phase6/run_marketdata_btc_1d.py all --mirror-json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description="Marketdata thin 1d (D1–D4)")
    ap.add_argument(
        "cmd",
        choices=("init", "ingest", "thin", "universe", "status", "regime", "all"),
        help="init | ingest BTC | thin multi-pair | universe | status | regime | all",
    )
    ap.add_argument("--db", default="", help="override marketdata.db path")
    ap.add_argument("--lookback-days", type=int, default=400)
    ap.add_argument("--no-api", action="store_true", help="local JSON only (BTC)")
    ap.add_argument("--mirror-json", action="store_true", help="rewrite data/ohlcv BTC JSON from DB")
    ap.add_argument("--json", action="store_true", help="machine JSON stdout")
    args = ap.parse_args()

    db = Path(args.db) if args.db else None

    from phase6.core.marketdata_store import db_stats, init_schema, seed_core_pairs
    from phase6.core.marketdata_ingest import (
        ingest_btc_1d,
        ingest_thin_1d,
        resolve_thin_universe,
        write_local_btc_mirror,
    )

    out: dict = {}
    if args.cmd in ("init", "all"):
        path = init_schema(db)
        pairs = seed_core_pairs(db)
        out["init"] = {"db": str(path), "seeded_pairs": pairs}

    if args.cmd == "universe":
        out["universe"] = resolve_thin_universe()

    if args.cmd == "ingest":
        rep = ingest_btc_1d(
            db_path=db,
            lookback_days=args.lookback_days,
            prefer_api=not args.no_api,
            also_local_file=True,
        )
        out["ingest"] = rep

    if args.cmd in ("thin", "all"):
        rep = ingest_thin_1d(
            db_path=db,
            lookback_days=args.lookback_days,
            prefer_api=not args.no_api,
        )
        out["thin"] = rep
        # keep BTC-only job healthy too
        out["ingest"] = {
            "job": "btc_via_thin",
            "ok": any(
                p.get("symbol") == "BTC-USD" and p.get("ok") for p in (rep.get("pairs") or [])
            ),
            "bar_count": next(
                (p.get("bar_count") for p in (rep.get("pairs") or []) if p.get("symbol") == "BTC-USD"),
                None,
            ),
            "freshness": {"status": next(
                (p.get("status") for p in (rep.get("pairs") or []) if p.get("symbol") == "BTC-USD"),
                None,
            )},
            "api_rows": next(
                (p.get("api_rows") for p in (rep.get("pairs") or []) if p.get("symbol") == "BTC-USD"),
                None,
            ),
            "local_rows": 0,
        }
        if args.mirror_json or args.cmd == "all":
            try:
                p = write_local_btc_mirror(db_path=db)
                out["mirror"] = str(p)
            except Exception as e:
                out["mirror_error"] = str(e)

    if args.cmd == "ingest" and (args.mirror_json):
        try:
            out["mirror"] = str(write_local_btc_mirror(db_path=db))
        except Exception as e:
            out["mirror_error"] = str(e)

    if args.cmd in ("status", "all"):
        out["status"] = db_stats(db)

    if args.cmd in ("regime", "all"):
        from phase6.research.regime_detector import detect_regime

        d = detect_regime(use_live_price=True)
        out["regime"] = {
            "regime": d.get("regime"),
            "regime_layer": d.get("regime_layer"),
            "btc_return_pct": d.get("btc_return_pct"),
            "window_start": d.get("window_start"),
            "window_end": d.get("window_end"),
            "confidence": d.get("confidence"),
            "data_source": d.get("data_source"),
            "fresh_ok": d.get("fresh_ok"),
            "reason": d.get("reason"),
            "shadow_stance": d.get("shadow_stance"),
        }

    print(json.dumps(out, indent=2, default=str))

    if "regime" in out:
        r = out["regime"]
        print(
            f"\nREGIME · {r.get('regime')}/{r.get('regime_layer')} · "
            f"btc_30d={r.get('btc_return_pct')} · "
            f"src={r.get('data_source')} · fresh={r.get('fresh_ok')} · "
            f"win={r.get('window_start')}→{r.get('window_end')}"
        )
    if "thin" in out:
        t = out["thin"]
        print(
            f"THIN · n={t.get('n_pairs')} ok={t.get('n_ok')}/{t.get('n_pairs')} "
            f"btc_ok={t.get('btc_ok')} job_ok={t.get('ok')}"
        )
        for p in (t.get("pairs") or [])[:20]:
            print(
                f"  {p.get('symbol'):12} bars={p.get('bar_count')} "
                f"status={p.get('status')} ok={p.get('ok')}"
            )
    elif "ingest" in out and args.cmd == "ingest":
        ing = out["ingest"]
        fr = ing.get("freshness") or {}
        print(
            f"INGEST · bars={ing.get('bar_count')} api={ing.get('api_rows')} "
            f"local={ing.get('local_rows')} status={fr.get('status')} "
            f"gap={fr.get('gap_days_tail')} ok={ing.get('ok')}"
        )
    if "universe" in out:
        u = out["universe"]
        print(f"UNIVERSE · n={u.get('n')} pairs={u.get('pairs')}")

    # exit
    if args.cmd in ("thin", "all"):
        return 0 if out.get("thin", {}).get("ok") else 1
    if args.cmd == "ingest":
        return 0 if out.get("ingest", {}).get("ok") else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
