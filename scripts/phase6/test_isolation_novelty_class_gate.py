#!/usr/bin/env python3
"""Isolation tests for novelty_class_gate (no live writes outside tmp)."""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core import novelty_class_gate as ncg


def _now() -> datetime:
    return datetime(2026, 9, 12, 18, 0, 0, tzinfo=timezone.utc)


def test_core_and_seed_and_hard_pin() -> None:
    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        reg_path = tdir / "reg.json"
        led = tdir / "ledger.jsonl"
        led.write_text("")
        reg = ncg.empty_registry()
        reg["hard_pin_block"] = ["JUNK-USD"]
        ncg.save_registry(reg, reg_path)

        btc = ncg.evaluate_pair_novelty("BTC-USD", registry_path=reg_path, ledger_path=led, now=_now())
        assert btc.class_ == "sticky_core" and not btc.blocked, btc

        link = ncg.evaluate_pair_novelty("LINK-USD", registry_path=reg_path, ledger_path=led, now=_now())
        assert link.class_ == "liquid_core" and not link.blocked, link

        pump = ncg.evaluate_pair_novelty("PUMP-USD", registry_path=reg_path, ledger_path=led, now=_now())
        assert pump.class_ == "novelty_restricted" and pump.blocked, pump

        junk = ncg.evaluate_pair_novelty("JUNK-USD", registry_path=reg_path, ledger_path=led, now=_now())
        assert junk.class_ == "novelty_blocked" and junk.blocked, junk

        unknown = ncg.evaluate_pair_novelty("BRANDNEW-USD", registry_path=reg_path, ledger_path=led, now=_now())
        assert unknown.class_ == "novelty_restricted" and unknown.blocked, unknown


def test_meme_can_graduate_later() -> None:
    """Restricted today → graduate after packet → contender; demote again if toxic."""
    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        reg_path = tdir / "reg.json"
        led = tdir / "ledger.jsonl"
        now = _now()
        first = (now - timedelta(days=60)).isoformat()

        # Clean ledger RTs for PUMP
        rows = []
        for i, reason in enumerate(["tp", "rotation", "tp", "sl"]):
            rows.append(
                {
                    "pair": "PUMP-USD",
                    "side": "sell",
                    "reason": reason,
                    "realized_pnl": 2.0 if reason != "sl" else -1.0,
                    "timestamp": (now - timedelta(days=30 - i)).isoformat(),
                }
            )
        # first seen older
        rows.append(
            {
                "pair": "PUMP-USD",
                "side": "buy",
                "timestamp": first,
            }
        )
        led.write_text("\n".join(json.dumps(r) for r in rows) + "\n")

        reg = ncg.empty_registry()
        reg["first_seen"] = {"PUMP-USD": first}
        reg["clean_contacts"] = {"PUMP-USD": 3}
        ncg.save_registry(reg, reg_path)

        before = ncg.evaluate_pair_novelty(
            "PUMP-USD",
            registry_path=reg_path,
            ledger_path=led,
            quote_vol_24h=8_000_000.0,
            ret_24h=0.02,
            ret_7d=0.05,
            now=now,
            auto_graduate=False,
            missfire_blocked=False,
        )
        assert before.class_ == "novelty_restricted"
        assert before.can_graduate is True, before.graduation_reasons

        after = ncg.evaluate_pair_novelty(
            "PUMP-USD",
            registry_path=reg_path,
            ledger_path=led,
            quote_vol_24h=8_000_000.0,
            ret_24h=0.02,
            ret_7d=0.05,
            now=now,
            auto_graduate=True,
            missfire_blocked=False,
        )
        assert after.class_ == "graduated" and not after.blocked, after
        reg2 = ncg.load_registry(reg_path)
        assert "PUMP-USD" in (reg2.get("graduated") or {})

        # Brad promote path also works for a cold name
        ncg.promote_pair("COLD-USD", reason="brad_go", registry_path=reg_path, as_force=True)
        cold = ncg.evaluate_pair_novelty("COLD-USD", registry_path=reg_path, ledger_path=led, now=now)
        assert cold.class_ == "graduated" and not cold.blocked, cold

        # Demote
        ncg.demote_pair("PUMP-USD", reason="toxic_again", registry_path=reg_path)
        dem = ncg.evaluate_pair_novelty("PUMP-USD", registry_path=reg_path, ledger_path=led, now=now)
        assert dem.class_ == "novelty_restricted" and dem.blocked, dem


def test_annotate_suppresses_membership_ok() -> None:
    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        reg_path = tdir / "reg.json"
        ncg.save_registry(ncg.empty_registry(), reg_path)
        swap = {
            "add": "PUMP-USD",
            "remove": "LINK-USD",
            "membership_ok": True,
            "quote_vol_24h": 1_000_000.0,
            "ret_24h": 0.2,
        }
        out = ncg.annotate_swap(swap, enforce=True, registry_path=reg_path)
        assert out["novelty_class"] == "novelty_restricted"
        assert out["novelty_blocked"] is True
        assert out["membership_ok"] is False
        assert out.get("membership_ok_suppressed_by") == "novelty_class_gate"

        # liquid core not suppressed
        swap2 = {"add": "SOL-USD", "membership_ok": True, "quote_vol_24h": 50_000_000.0}
        out2 = ncg.annotate_swap(swap2, enforce=True, registry_path=reg_path)
        assert out2["novelty_class"] == "liquid_core"
        assert out2["novelty_blocked"] is False
        assert out2["membership_ok"] is True


def test_graduation_rejects_chase_and_thin() -> None:
    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        reg_path = tdir / "reg.json"
        led = tdir / "ledger.jsonl"
        led.write_text("")
        reg = ncg.empty_registry()
        reg["first_seen"] = {"HYPE-USD": (_now() - timedelta(days=60)).isoformat()}
        ncg.save_registry(reg, reg_path)

        # hot chase
        v = ncg.evaluate_pair_novelty(
            "HYPE-USD",
            registry_path=reg_path,
            ledger_path=led,
            quote_vol_24h=20_000_000.0,
            ret_24h=0.40,
            now=_now(),
        )
        assert v.blocked and not v.can_graduate
        assert any("extended_24h" in r for r in v.graduation_reasons), v.graduation_reasons

        # young
        reg["first_seen"] = {"HYPE-USD": (_now() - timedelta(days=5)).isoformat()}
        ncg.save_registry(reg, reg_path)
        v2 = ncg.evaluate_pair_novelty(
            "HYPE-USD",
            registry_path=reg_path,
            ledger_path=led,
            quote_vol_24h=20_000_000.0,
            ret_24h=0.01,
            now=_now(),
        )
        assert not v2.can_graduate
        assert any("age_too_young" in r for r in v2.graduation_reasons), v2.graduation_reasons


def test_build_board_tmp() -> None:
    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        reg_path = tdir / "reg.json"
        led = tdir / "ledger.jsonl"
        led.write_text("")
        ncg.save_registry(ncg.empty_registry(), reg_path)
        # monkeypatch latest path via writing only through build with custom — use registry only
        board = ncg.build_board(
            ["BTC-USD", "PUMP-USD", "SOL-USD"],
            registry_path=reg_path,
            ledger_path=led,
            write=False,
        )
        assert board["counts"]["sticky_core"] >= 1
        assert board["counts"]["novelty_restricted"] >= 1
        assert board["blocked_for_auto_rotation"] >= 1


def main() -> int:
    tests = [
        test_core_and_seed_and_hard_pin,
        test_meme_can_graduate_later,
        test_annotate_suppresses_membership_ok,
        test_graduation_rejects_chase_and_thin,
        test_build_board_tmp,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"OK  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {fn.__name__}: {type(e).__name__}: {e}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
