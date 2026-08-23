"""Isolation: park package coordinator (USDC + PAXG) — no orders."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core import park_package as pp


def test_normalize_and_profiles():
    assert pp._normalize_profile("A_PLUS_B_MICRO") == "a_plus_b_micro"
    assert pp._normalize_profile("nope") == "off"
    assert "a_only" in pp.PROFILES_WANT_A
    assert "a_plus_b_micro" in pp.PROFILES_WANT_B
    assert "off" not in pp.PROFILES_WANT_B


def test_sequence_enter_park_order_a_before_b_offer():
    book = {
        "enabled": True,
        "profile": "a_plus_b_micro",
        "buckets": {
            "A": {"target_usdc_pct": 0.92, "min_usd_reserve_usd": 50.0},
            "B": {
                "micro_usd": 75.0,
                "require_explicit_arm": True,
                "require_crypto_parked_before_arm": True,
                "allow_preserve_with_crypto_util": False,
                "derisk_enabled": False,
            },
        },
        "execution": {
            "allow_coordinate_toggles": False,
            "auto_arm_b": False,
            "auto_trim_b_on_deploy": False,
        },
    }
    full_config = {
        "global_settings": {
            "strategy_mode": "usdc_park",
            "rebalance_cap_usd": 0,
            "risk_free_preference": "USDC",
        }
    }

    with patch.object(pp, "load_park_package_config", return_value={**book, "account_id": "iso"}):
        with patch.object(
            pp,
            "live_usdc_park_settings",
            return_value={"enabled": True, "target_usdc_pct": 0.92, "min_usd_reserve_usd": 50.0},
        ):
            with patch.object(
                pp,
                "_preserve_snapshot",
                return_value={
                    "enabled": True,
                    "armed": False,
                    "micro": True,
                    "micro_usd": 75.0,
                    "derisk_enabled": False,
                    "allow_preserve_with_crypto_util": False,
                },
            ):
                with patch.object(pp, "_crypto_util_est", return_value=0.1):
                    with patch.object(pp, "_shadow_b_recommendation", return_value={}):
                        plan = pp.evaluate_park_package(
                            account_id="iso", full_config=full_config
                        )

    assert plan["orders"] is False
    assert plan["profile"] == "a_plus_b_micro"
    assert plan["cash_plan"]["cash_earmarked_b_usd"] == 75.0
    assert plan["cash_plan"]["double_spend_ok"] is True
    ids = [s["id"] for s in plan["sequence"]]
    # A park step before B offer
    assert "run_A_usdc_park_if_eligible" in ids
    assert "offer_B_only_if_profile_and_operator" in ids
    assert ids.index("run_A_usdc_park_if_eligible") < ids.index(
        "offer_B_only_if_profile_and_operator"
    )
    b_step = next(s for s in plan["sequence"] if s["id"] == "offer_B_only_if_profile_and_operator")
    assert b_step["auto"] is False
    assert b_step.get("arm_allowed") is False


def test_no_auto_arm_even_if_flag_true():
    book = {
        "enabled": True,
        "profile": "a_plus_b_micro",
        "buckets": {"A": {}, "B": {"micro_usd": 75.0, "require_explicit_arm": True}},
        "execution": {"auto_arm_b": True, "auto_trim_b_on_deploy": False},
    }
    with patch.object(pp, "load_park_package_config", return_value={**book, "account_id": "x"}):
        with patch.object(pp, "live_usdc_park_settings", return_value={"enabled": True}):
            with patch.object(
                pp,
                "_preserve_snapshot",
                return_value={"armed": False, "micro": True, "micro_usd": 75.0, "derisk_enabled": False},
            ):
                with patch.object(pp, "_regime_snapshot", return_value={
                    "park_signal": True, "deploy_open": False, "rebalance_cap_usd": 0, "regime": "flat"
                }):
                    with patch.object(pp, "_crypto_util_est", return_value=0.05):
                        with patch.object(pp, "_shadow_b_recommendation", return_value={}):
                            plan = pp.evaluate_park_package(account_id="x", full_config={})
    assert plan["execution_flags"]["auto_arm_b"] is False
    assert any("auto_arm_b" in w for w in plan["consistency_warnings"])


def test_profile_off_usd_path():
    book = {
        "enabled": False,
        "profile": "off",
        "buckets": {"A": {}, "B": {"micro_usd": 75.0}},
        "execution": {},
    }
    with patch.object(pp, "load_park_package_config", return_value={**book, "account_id": "x"}):
        with patch.object(pp, "live_usdc_park_settings", return_value={"enabled": False}):
            with patch.object(
                pp,
                "_preserve_snapshot",
                return_value={"armed": False, "micro": False, "derisk_enabled": False},
            ):
                with patch.object(
                    pp,
                    "_regime_snapshot",
                    return_value={
                        "park_signal": True,
                        "deploy_open": False,
                        "rebalance_cap_usd": 0,
                        "regime": "flat",
                    },
                ):
                    with patch.object(pp, "_crypto_util_est", return_value=0.5):
                        with patch.object(pp, "_shadow_b_recommendation", return_value={}):
                            plan = pp.evaluate_park_package(account_id="x", full_config={})
    assert plan["profile"] == "off"
    assert plan["bucket_a"]["recommended_a_action"] == "none"
    assert any(s["id"] == "A_regime_cash_usd" for s in plan["sequence"])


def test_warning_when_profile_wants_a_toggle_off():
    book = {
        "enabled": True,
        "profile": "a_only",
        "buckets": {"A": {}, "B": {}},
        "execution": {},
    }
    with patch.object(pp, "load_park_package_config", return_value={**book, "account_id": "x"}):
        with patch.object(pp, "live_usdc_park_settings", return_value={"enabled": False}):
            with patch.object(
                pp,
                "_preserve_snapshot",
                return_value={"armed": False, "derisk_enabled": False},
            ):
                with patch.object(
                    pp,
                    "_regime_snapshot",
                    return_value={"park_signal": True, "deploy_open": False, "rebalance_cap_usd": 0},
                ):
                    with patch.object(pp, "_crypto_util_est", return_value=None):
                        with patch.object(pp, "_shadow_b_recommendation", return_value={}):
                            plan = pp.evaluate_park_package(account_id="x", full_config={})
    assert plan["bucket_a"]["recommended_a_action"] == "enable_live_usdc_park_toggle"
    assert any("live_usdc_park.enabled=false" in w for w in plan["consistency_warnings"])


def test_write_status_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "park_package_status.json"
        plan = {"schema_version": 1, "orders": False, "profile": "off", "package_enabled": False}
        out = pp.write_park_package_status(plan, path=path)
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["profile"] == "off"
        assert data["orders"] is False


def test_deploy_sequence_mentions_trim_before_implied_c():
    book = {
        "enabled": True,
        "profile": "a_plus_b_micro",
        "buckets": {"A": {}, "B": {"micro_usd": 75.0}},
        "execution": {"auto_trim_b_on_deploy": False},
    }
    with patch.object(pp, "load_park_package_config", return_value={**book, "account_id": "x"}):
        with patch.object(pp, "live_usdc_park_settings", return_value={"enabled": True}):
            with patch.object(
                pp,
                "_preserve_snapshot",
                return_value={"armed": True, "micro": True, "derisk_enabled": False},
            ):
                with patch.object(
                    pp,
                    "_regime_snapshot",
                    return_value={
                        "park_signal": False,
                        "deploy_open": True,
                        "rebalance_cap_usd": 75,
                        "regime": "flat",
                    },
                ):
                    with patch.object(pp, "_crypto_util_est", return_value=0.4):
                        with patch.object(
                            pp,
                            "_shadow_b_recommendation",
                            return_value={"recommended_action": "TRIM_DEFAULT_TO_A"},
                        ):
                            plan = pp.evaluate_park_package(account_id="x", full_config={})
    ids = [s["id"] for s in plan["sequence"]]
    assert "shadow_or_manual_trim_B_to_A" in ids
    assert "run_A_usdc_redeploy_unwind" in ids
    # trim step is not auto
    trim = next(s for s in plan["sequence"] if s["id"] == "shadow_or_manual_trim_B_to_A")
    assert trim["auto"] is False


def test_auto_trim_sequence_when_flag_on():
    book = {
        "enabled": True,
        "profile": "a_plus_b_micro",
        "buckets": {"A": {}, "B": {"micro_usd": 75.0}},
        "execution": {"auto_trim_b_on_deploy": True},
    }
    with patch.object(pp, "load_park_package_config", return_value={**book, "account_id": "x"}):
        with patch.object(pp, "live_usdc_park_settings", return_value={"enabled": True}):
            with patch.object(
                pp,
                "_preserve_snapshot",
                return_value={"armed": True, "micro": True, "derisk_enabled": False},
            ):
                with patch.object(
                    pp,
                    "_regime_snapshot",
                    return_value={
                        "park_signal": False,
                        "deploy_open": True,
                        "rebalance_cap_usd": 75,
                        "regime": "bull",
                    },
                ):
                    with patch.object(pp, "_crypto_util_est", return_value=0.4):
                        with patch.object(
                            pp,
                            "_shadow_b_recommendation",
                            return_value={"recommended_action": "TRIM_DEFAULT_TO_A"},
                        ):
                            plan = pp.evaluate_park_package(account_id="x", full_config={})
    trim = next(s for s in plan["sequence"] if s["id"] == "auto_trim_B_to_A")
    assert trim["auto"] is True
    assert plan["execution_flags"]["auto_trim_b_on_deploy"] is True


def test_should_execute_edge_triggered_only(tmp_path, monkeypatch):
    state_path = tmp_path / "park_auto_trim_state.json"
    monkeypatch.setattr(pp, "AUTO_TRIM_STATE_PATH", state_path)

    plan = {
        "package_enabled": True,
        "bucket_b": {
            "preserve": {"armed": True},
            "shadow": {"recommended_action": "TRIM_DEFAULT_TO_A"},
        },
        "bucket_c": {"regime": {"park_signal": False, "deploy_open": True}},
    }
    pkg = {"execution": {"auto_trim_b_on_deploy": True}}

    # cold start already in deploy — no edge
    g = pp.should_execute_auto_trim_b(plan, pkg)
    assert g["execute"] is False
    assert "no_park_to_deploy_edge" in g["reason"]

    # seed prior park
    state_path.write_text(json.dumps({"last_posture": "park", "last_park_seen_at": "t0"}))
    g2 = pp.should_execute_auto_trim_b(plan, pkg)
    assert g2["execute"] is True
    assert g2["reason"] == "park_to_deploy_edge"

    # keep-hold blocks
    plan_kh = json.loads(json.dumps(plan))
    plan_kh["bucket_b"]["shadow"]["recommended_action"] = "KEEP_HOLD_MICRO"
    g3 = pp.should_execute_auto_trim_b(plan_kh, pkg)
    assert g3["execute"] is False
    assert g3["reason"] == "keep_hold"


def test_maybe_execute_dry_run_on_edge(tmp_path, monkeypatch):
    state_path = tmp_path / "park_auto_trim_state.json"
    monkeypatch.setattr(pp, "AUTO_TRIM_STATE_PATH", state_path)
    state_path.write_text(json.dumps({"last_posture": "park", "last_park_seen_at": "t0"}))
    plan = {
        "package_enabled": True,
        "bucket_b": {
            "preserve": {"armed": True},
            "shadow": {"recommended_action": "TRIM_DEFAULT_TO_A"},
        },
        "bucket_c": {"regime": {"park_signal": False, "deploy_open": True}},
    }
    pkg = {"execution": {"auto_trim_b_on_deploy": True}}
    runner = MagicMock()
    runner.exchange = MagicMock(shadow_mode=False)
    out = pp.maybe_execute_auto_trim_b(runner, plan, pkg, dry_run=True)
    assert out["attempted"] is True
    assert out["ok"] is True
    assert out["orders"] is False
    assert out["reason"] == "dry_run_would_disarm_sell"


def test_maybe_cycle_no_orders():
    runner = MagicMock()
    runner.account_id = "iso-cycle"
    runner.config_dict = {"global_settings": {"strategy_mode": "usdc_park", "rebalance_cap_usd": 0}}
    with patch.object(pp, "evaluate_and_write_status", return_value={
        "orders": False,
        "profile": "off",
        "package_enabled": False,
        "bucket_b": {"preserve": {"armed": False}, "shadow": {}},
        "bucket_c": {"regime": {"park_signal": True, "deploy_open": False}},
    }):
        with patch.object(pp, "load_park_package_config", return_value={
            "enabled": False,
            "execution": {"write_status_each_cycle": True, "auto_trim_b_on_deploy": False},
        }):
            with patch.object(pp, "write_park_package_status"):
                out = pp.maybe_park_package_cycle(runner)
    assert out.get("error") is None
    assert (out.get("auto_trim_execution") or {}).get("attempted") is False


if __name__ == "__main__":
    test_normalize_and_profiles()
    test_sequence_enter_park_order_a_before_b_offer()
    test_no_auto_arm_even_if_flag_true()
    test_profile_off_usd_path()
    test_warning_when_profile_wants_a_toggle_off()
    test_write_status_roundtrip()
    test_deploy_sequence_mentions_trim_before_implied_c()
    test_auto_trim_sequence_when_flag_on()
    # manual tmp for edge tests without pytest
    import tempfile
    from pathlib import Path as P

    class _MP:
        def __init__(self):
            self._attrs = []

        def setattr(self, obj, name, val):
            self._attrs.append((obj, name, getattr(obj, name, None)))
            setattr(obj, name, val)

        def undo(self):
            for obj, name, old in reversed(self._attrs):
                if old is None and not hasattr(obj, name):
                    continue
                setattr(obj, name, old)

    with tempfile.TemporaryDirectory() as td:
        mp = _MP()
        try:
            sp = P(td) / "park_auto_trim_state.json"
            mp.setattr(pp, "AUTO_TRIM_STATE_PATH", sp)
            plan = {
                "package_enabled": True,
                "bucket_b": {
                    "preserve": {"armed": True},
                    "shadow": {"recommended_action": "TRIM_DEFAULT_TO_A"},
                },
                "bucket_c": {"regime": {"park_signal": False, "deploy_open": True}},
            }
            pkg = {"execution": {"auto_trim_b_on_deploy": True}}
            g = pp.should_execute_auto_trim_b(plan, pkg)
            assert g["execute"] is False
            sp.write_text(json.dumps({"last_posture": "park", "last_park_seen_at": "t0"}))
            g2 = pp.should_execute_auto_trim_b(plan, pkg)
            assert g2["execute"] is True
            runner = MagicMock()
            runner.exchange = MagicMock(shadow_mode=False)
            out = pp.maybe_execute_auto_trim_b(runner, plan, pkg, dry_run=True)
            assert out["attempted"] and out["ok"]
        finally:
            mp.undo()
    test_maybe_cycle_no_orders()
    print("park_package isolation PASS")
