# Handoff: SL-INSUFFICIENT-FUND-02

**Status:** Done (2026-07-06)

## Root cause (recurring)
Coinbase Advanced Trade stop orders use `order_configuration` keys like **`stop_limit_stop_limit_gtc`**, not bare `stop_limit`. Suspend/CR-03 and `get_open_stop_orders()` **never matched** those keys, so:

1. Existing stops were **not canceled** on re-attach.
2. **100% of base balance stayed on hold** (`available=0`, `total>0`).
3. New `place_stop_limit_sell` → **`PREVIEW_INSUFFICIENT_FUND`** (mislabeled as “size mismatch”; it was **double-placement on locked balance**).

## Fix
| Layer | Change |
|-------|--------|
| `sl_preflight.py` | `order_configuration_is_stop`, `cancel_open_stops_for_pair`, `poll_available_after_cancel`, `resolve_sl_attach_size` |
| `exchange_client.py` | Normalize/detect stops via new helpers |
| `stop_loss_coordinator.py` | Cancel + poll before each re-attach; suspend uses same detection |
| `stop_loss_manager.py` | Cap size to **available** (98%); auto-release holds if needed; INSUFFICIENT_FUND retry |

## Verification
- Isolation: `phase6/tests/test_isolation_sl_insufficient_fund.py`
- Live `reattach_sl_once.py`: **UNI, LINK, OP, ADA, SOL, BTC** all `attached` (was failing on UNI/LINK/OP/ADA)

## Ops
Re-attach path always **cancel → poll avail → size to avail → place**. CR-03 suspend now actually cancels Coinbase GTC stop-limit orders.