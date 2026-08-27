#!/usr/bin/env python3
"""
Isolation tests: run lifecycle P1 (ignition+structure) + P2 (dual-peak).

Run:
  cd /home/brad/projects/crypto-trading-bot && PYTHONPATH=. python3 scripts/phase6/test_isolation_run_lifecycle_p12.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.run_lifecycle import (
    classify_structure,
    evaluate_dual_peak_exits,
    load_lifecycle_config,
    rsi_structure_entry_score,
    score_pair_ignition,
)
from phase6.core.run_phase_deploy import (
    PHASE_EXTENSION,
    PHASE_IGNITION,
    classify_run_phase,
    fetch_daily_candles_public,
)


def main() -> int:
    fails = []
    cfg = json.loads((ROOT / "config/trading_config_phase6.json").read_text())
    life = load_lifecycle_config(cfg)
    assert life["ignition_scout"]["enabled"]
    assert life["dual_peak_exit"]["enabled"]

    # --- Real LINK: Aug 11 should score; Aug 24 should not ---
    link = fetch_daily_candles_public("LINK-USD", limit=50)
    from datetime import datetime, timezone

    def idx_on(d):
        for i, r in enumerate(link):
            if datetime.fromtimestamp(r["t"], tz=timezone.utc).strftime("%Y-%m-%d") == d:
                return i
        return None

    i11 = idx_on("2026-08-11")
    i24 = idx_on("2026-08-24")
    if i11 is None or i24 is None:
        fails.append("missing LINK dates")
    else:
        c11 = score_pair_ignition("LINK-USD", link[: i11 + 1], sentiment=0.2, cfg_all=life)
        c24 = score_pair_ignition("LINK-USD", link[: i24 + 1], sentiment=0.89, cfg_all=life)
        print("LINK Aug11", c11.score, c11.phase_name, c11.structure_ok, c11.reason)
        print("LINK Aug24", c24.score, c24.phase_name, c24.structure_ok, c24.reason)
        if c11.phase > 2:
            fails.append(f"Aug11 phase should be early, got {c11.phase_name}")
        # Aug11 may or may not clear min_score depending on structure — but must beat Aug24
        if c24.score >= 0.55:
            fails.append(f"Aug24 must not be ignition candidate, score={c24.score}")
        if c24.proposal_usd > 0:
            fails.append("Aug24 proposal_usd must be 0")
        if c11.score <= c24.score:
            fails.append(f"Aug11 score should exceed Aug24 ({c11.score} vs {c24.score})")

    # --- Structure: RSI alone high without structure fails ---
    # Build mild uptrend with price above SMA
    closes = [10 + i * 0.02 for i in range(60)]
    candles = []
    t0 = 1_700_000_000
    for i, c in enumerate(closes):
        candles.append([t0 + i * 86400, c * 0.99, c * 1.01, c, c, 1000])
    st = classify_structure(candles, pair="T-USD", cfg=life["structure"])
    print("structure mild trend", st.structure_ok_for_entry, st.above_sma_fast, st.fib_pos)
    snap = classify_run_phase(candles, pair="T-USD")
    sc, reason = rsi_structure_entry_score(
        daily_rsi=snap.daily_rsi or 58.0,
        structure=st,
        run_phase=PHASE_IGNITION if snap.phase <= 2 else snap.phase,
        sentiment=0.1,
        cfg_structure=life["structure"],
        cfg_scout=life["ignition_scout"],
    )
    print("rsi+structure score", sc, reason, "phase", snap.phase_name)

    # RSI high + late structure → 0
    st_late = classify_structure(candles, pair="T-USD", cfg=life["structure"])
    # force late by synthetic: mark fib extension
    st_late.structure_late = True
    st_late.at_or_past_extension = True
    st_late.structure_ok_for_entry = False
    sc_bad, r_bad = rsi_structure_entry_score(
        daily_rsi=72.0,
        structure=st_late,
        run_phase=PHASE_EXTENSION,
        sentiment=0.9,
        cfg_structure=life["structure"],
        cfg_scout=life["ignition_scout"],
    )
    if sc_bad != 0:
        fails.append(f"late+high RSI must score 0, got {sc_bad} {r_bad}")

    # --- Dual peak pure ---
    lots = [
        {
            "pair": "LINK-USD",
            "open": True,
            "entry_price": 11.60,
            "entry_sentiment": 0.89,
            "entry_sent_peak": 0.89,
            "peak_price": 12.50,
            "usd": 1000,
        }
    ]
    # price stall off peak + sent fade — mark still GREEN vs entry (P0 no-red)
    events = evaluate_dual_peak_exits(
        lots=lots,
        current_sentiment={"LINK-USD": 0.50},
        current_prices={"LINK-USD": 11.90},
        positions_usd={"LINK-USD": 1000},
        candles_by_pair={"LINK-USD": link},
        cfg_p2=life["dual_peak_exit"],
    )
    kinds = {e.kind for e in events}
    print("dual peak events", [(e.kind, e.would_trim_usd, e.reasons) for e in events])
    if not events:
        # may still get extension_partial from live phase
        fails.append("expected at least one dual-peak or extension_partial event for faded LINK")
    else:
        # sent faded 0.39 >= 0.30 and off peak from 12 → dual or extension
        if "dual_peak" not in kinds and "extension_partial" not in kinds:
            fails.append(f"unexpected kinds {kinds}")

    # No event if sent still hot and price at highs (unless extension phase)
    events2 = evaluate_dual_peak_exits(
        lots=[
            {
                "pair": "X-USD",
                "open": True,
                "entry_price": 10.0,
                "entry_sentiment": 0.5,
                "peak_price": 10.1,
                "usd": 500,
            }
        ],
        current_sentiment={"X-USD": 0.55},
        current_prices={"X-USD": 10.1},
        positions_usd={"X-USD": 500},
        candles_by_pair={
            "X-USD": [[t0 + i * 86400, 10, 10.1, 10, 10.05, 100] for i in range(30)]
        },
        cfg_p2=life["dual_peak_exit"],
    )
    dual2 = [e for e in events2 if e.kind == "dual_peak"]
    if dual2:
        fails.append(f"should not dual-peak on flat healthy hold: {dual2}")

    # EXIT-H1: SL reattach after lifecycle partial
    try:
        from unittest.mock import MagicMock, patch
        from phase6.core.run_lifecycle import reattach_sl_after_lifecycle_trim

        r = reattach_sl_after_lifecycle_trim(
            None, "LINK-USD", entry_price=11.6, remaining_qty_hint=50
        )
        if not (r.get("ok") is False and r.get("error") == "no_exchange_or_pair"):
            fails.append(f"sl_reattach no_exchange expected fail got {r}")
        ex = MagicMock()
        with patch(
            "phase6.core.sl_preflight.cancel_open_stops_for_pair", return_value=1
        ), patch(
            "phase6.core.sl_preflight.poll_available_after_cancel", return_value=True
        ), patch(
            "phase6.core.sl_preflight.resolve_sl_attach_size",
            return_value=(40.0, {"source": "t"}),
        ), patch(
            "phase6.core.stop_loss_manager.StopLossManager"
        ) as SLM:
            inst = SLM.return_value
            inst.attach_stop_loss.return_value = True
            r2 = reattach_sl_after_lifecycle_trim(
                ex,
                "LINK-USD",
                entry_price=11.6,
                remaining_qty_hint=50.0,
                config_dict={},
            )
            if not (r2.get("ok") is True and r2.get("size") == 40.0):
                fails.append(f"sl_reattach happy path failed: {r2}")
            elif inst.attach_stop_loss.call_args.kwargs.get("fresh_buy") is not False:
                fails.append("sl_reattach must use fresh_buy=False")
            else:
                print("sl_reattach_after_lifecycle_trim OK")
    except Exception as e:
        fails.append(f"sl_reattach exception: {e}")

    # EXIT-H1b: live trim must cancel stops BEFORE sell (stop-lock → INSUFFICIENT_FUND)
    try:
        from unittest.mock import MagicMock, patch, call
        from phase6.core.run_lifecycle import apply_lifecycle_exits_live, DualPeakEvent

        cancel_calls = []
        sell_calls = []

        def _cancel(ex, pair):
            cancel_calls.append(pair)
            return 1

        def _sell(pair, qty):
            sell_calls.append((pair, qty, list(cancel_calls)))
            return {"success": True, "order_id": "oid-test"}

        ex = MagicMock()
        ex.place_market_sell.side_effect = _sell
        ex.quantize_size.side_effect = lambda p, q: float(q)
        ex.get_crypto_available.return_value = 0.01
        ex.get_order_fill_details.return_value = {
            "average_filled_price": 80000.0,
            "filled_size": 0.005,
        }

        fake_ev = DualPeakEvent(
            pair="BTC-USD",
            kind="dual_peak",
            would_trim_frac=0.5,
            would_trim_usd=400.0,
            current_price=80000.0,
            entry_price=78600.0,
            peak_return=0.05,
            off_peak_pct=0.03,
            entry_sentiment=0.8,
            current_sentiment=0.4,
            sent_fade=0.4,
            phase_name="extension",
            reasons=["stall"],
            mode="live",
            shadow=False,
        )

        with patch(
            "phase6.core.sl_preflight.cancel_open_stops_for_pair", side_effect=_cancel
        ), patch(
            "phase6.core.sl_preflight.poll_available_after_cancel", return_value=True
        ), patch(
            "phase6.core.run_lifecycle.evaluate_dual_peak_exits", return_value=[fake_ev]
        ), patch(
            "phase6.core.run_lifecycle.run_dual_peak_exit_shadow", return_value=[]
        ), patch(
            "phase6.core.run_lifecycle._load_lots",
            return_value=[
                {
                    "pair": "BTC-USD",
                    "open": True,
                    "entry_price": 78600.0,
                    "usd": 800,
                }
            ],
        ), patch(
            "phase6.core.protected_market_exit.reattach_stop_after_exit",
            return_value={"ok": True, "size": 0.005, "action": "reattach"},
        ), patch(
            "phase6.core.trade_ledger.TradeLedger"
        ) as TL, patch(
            "phase6.core.run_lifecycle._notify_dual_peak"
        ), patch(
            "pathlib.Path.exists", return_value=False
        ), patch(
            "pathlib.Path.write_text"
        ), patch(
            "pathlib.Path.open", create=True
        ):
            TL.return_value.log_trade = MagicMock()
            out = apply_lifecycle_exits_live(
                config_dict={
                    "run_lifecycle": {
                        "dual_peak_exit": {
                            "mode": "live",
                            "enabled": True,
                            "live_min_trim_usd": 40,
                            "live_max_trims_per_tick": 2,
                            "notify_telegram": False,
                        }
                    }
                },
                exchange=ex,
                dry_run=False,
                notify=False,
            )
            if not cancel_calls:
                fails.append("live trim did not cancel stops before sell")
            elif not sell_calls:
                fails.append(f"live trim did not sell; out={out}")
            elif not sell_calls[0][2]:
                fails.append("sell happened before cancel stops")
            elif not out.get("executed"):
                fails.append(f"expected executed row, got {out}")
            else:
                row = out["executed"][0]
                if not row.get("cancelled_stops_pre_sell"):
                    fails.append(f"missing cancelled_stops_pre_sell: {row}")
                else:
                    print("pre_sell_cancel_stops OK")
    except Exception as e:
        fails.append(f"pre_sell_cancel exception: {e}")

    print("\n==== RESULTS ====")
    if fails:
        for f in fails:
            print("FAIL:", f)
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
