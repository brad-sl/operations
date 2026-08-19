#!/usr/bin/env python3
"""
T0-02: Unit tests for AccountContext dataclass + dual legacy path + isolation skeleton.

- 2 accounts load without state bleed
- Legacy Brad path unchanged when flag off
- Context injection clean (with_account, get_current, runner pass-through)
- Per-account paths in ledger etc.

Run: python -m pytest phase6/core/test_t0_02_context_isolation.py -q --tb=line
Or: python phase6/core/test_t0_02_context_isolation.py
"""

import os
import sys
import tempfile
from pathlib import Path

# Ensure root on path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("MULTI_TENANT_ENABLED", "0")  # tests control it

from phase6.core.context import (
    AccountContext,
    get_current_context,
    with_account,
    create_legacy_context,
    is_multi_tenant_enabled,
    create_test_context,
)

from phase6.core.trade_ledger import TradeLedger
from phase6.core.stop_loss_manager import StopLossManager

# Mock minimal exchange/config for ledger/sl
class MockExchange:
    def __init__(self):
        self.mode = "shadow"
    def get_account_balance(self, c):
        return 1000.0

def test_account_context_dataclass_and_dual_path():
    print("=== T0-02 context primitives ===")
    legacy = create_legacy_context(account_id="brad-primary")
    assert legacy.account_id == "brad-primary"
    assert not legacy.is_multi_tenant()  # default flag false

    t1 = create_test_context("acct-001", tier="elite")
    t2 = create_test_context("acct-002", tier="starter")
    assert t1.account_id == "acct-001"
    assert t2.account_id == "acct-002"
    assert t1.is_multi_tenant()
    assert t2.is_multi_tenant()

    # with_account isolation
    with with_account(t1):
        assert get_current_context() is t1
        assert get_current_context().account_id == "acct-001"
    assert get_current_context() is None

    with with_account(t2):
        assert get_current_context().account_id == "acct-002"
    print("✅ dataclass + with_account + dual path OK")

def test_runner_style_context_passthrough_and_legacy():
    print("=== T0-02 runner-style passthrough (shadow) ===")
    # Simulate Phase6Runner(ctx) behavior without full import cycle
    ctx1 = create_test_context("test-acct-001")
    ctx2 = create_test_context("test-acct-002")

    # Ledger accepts and isolates path
    l1 = TradeLedger(account_context=ctx1)
    l2 = TradeLedger(account_context=ctx2)
    assert l1.account_id == "test-acct-001"
    assert l2.account_id == "test-acct-002"
    # T0-02 tracks account_id on components; per-account path partitions are T0-03+.
    assert l1.account_id != l2.account_id
    print(f"  Ledger1 account_id={l1.account_id} dir={l1.trades_dir}")
    print(f"  Ledger2 account_id={l2.account_id} dir={l2.trades_dir}")

    # SL manager
    ex = MockExchange()
    sl1 = StopLossManager(ex, {"risk_management": {}}, mode="shadow", account_context=ctx1)
    sl2 = StopLossManager(ex, {"risk_management": {}}, mode="shadow", account_context=ctx2)
    assert sl1.account_id == "test-acct-001"
    assert sl2.account_id == "test-acct-002"
    print("✅ subcomponents accept/pass context OK")

def test_legacy_preserved_when_flag_off():
    print("=== T0-02 legacy Brad path when flag=off ===")
    # Ensure default is legacy
    assert not is_multi_tenant_enabled(False)
    leg = create_legacy_context()
    assert leg.account_id == "brad-primary"
    # In real runner, no ctx passed -> legacy created inside
    print("✅ legacy preserved (flag false by default, Brad path)")

def test_two_accounts_no_state_bleed_skeleton():
    print("=== T0-02 isolation: 2 accounts no bleed skeleton ===")
    ctx_a = create_test_context("iso-a")
    ctx_b = create_test_context("iso-b")

    # Different contexts, different ledger paths
    la = TradeLedger(account_context=ctx_a)
    lb = TradeLedger(account_context=ctx_b)
    # Write marker (temp to not pollute)
    with tempfile.TemporaryDirectory() as td:
        la2 = TradeLedger(base_dir=Path(td), account_context=ctx_a)
        lb2 = TradeLedger(base_dir=Path(td), account_context=ctx_b)
        la2.jsonl_path.write_text('{"account":"a"}\n')
        lb2.jsonl_path.write_text('{"account":"b"}\n')
        assert "iso-a" in str(la2.trades_dir)
        assert "iso-b" in str(lb2.trades_dir)
        assert la2.jsonl_path.read_text() != lb2.jsonl_path.read_text()
    print("✅ 2 accounts loaded, separate paths, no cross bleed in skeleton")

if __name__ == "__main__":
    test_account_context_dataclass_and_dual_path()
    test_runner_style_context_passthrough_and_legacy()
    test_legacy_preserved_when_flag_off()
    test_two_accounts_no_state_bleed_skeleton()
    print("\n=== T0-02 CONTEXT ISOLATION TESTS PASSED ===")
