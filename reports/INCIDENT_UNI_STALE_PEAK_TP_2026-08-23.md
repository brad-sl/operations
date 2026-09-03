# Incident — UNI stale peak_r live trail dump (2026-08-23)

**Status:** FIXED (code + live state sanitize)  
**Severity:** high (core exit path sold a fresh lot at a small loss)  
**Money impact:** ~−$1.1 on UNI (~−0.3%); not catastrophic but **must never recur**

## Plain English

We bought UNI on a rebalance, then the live take-profit trail sold it ~1–2 minutes later thinking it had already run +11% and pulled back. It hadn’t. The trail was using an **old peak** from a previous bag/promote seed. Fresh lots must start their own peak at the current return.

## Timeline (America/Los_Angeles)

| Local PT | UTC | Event |
|----------|-----|--------|
| 9:00:35 AM | 16:00:35Z | Rebal **BUY** 73.5625 UNI @ ~$4.570 |
| 9:01:45 AM | 16:01:45Z | Live TP **SELL** 1.4713 UNI `take_profit_trail` (leg 1 / residual) |
| 9:02:58 AM | 16:02:58Z | Live TP **SELL** 72.0913 UNI `take_profit_trail` (bulk) |

Exit ~$4.555–4.556 → ~−0.3% vs entry.

Dashboard showed **04:01 PM** because the UI printed UTC wall-clock via browser host TZ (often UTC on the host), not trader local time.

## Root cause

1. **`peak_r` not bound to lot identity.** State kept `UNI-USD: 0.1123` after prior bag/promote. New lot inherited it.
2. **Weak gap gate** only reset when `peak − mark_r > 0.15` and `mark_r < 0.08`. UNI gap was ~0.115 → **missed**.
3. Trail: arm +4%, trail 2% → stop at `0.1123 − 0.02 = 0.0923`. Mark at −0.3% ≤ stop → **immediate market sell**.
4. **Timestamps:** ledger mixed naive/Z UTC; UI used `toLocaleTimeString()` without `timeZone` → host-local, not trader-local.

## Fix shipped

### A. Lot-bound peaks (`phase6/core/shadow_tp.py`)

- New `sanitize_peak_r_for_lots()`:
  - Drop peaks for pairs not held
  - If no `peak_lot` meta + leftover peak → reset to current `r` (**unbound_peak_new_lot**)
  - If `entry_px` moved >0.5% vs bound lot → reset (**entry_changed**)
  - Same lot keeps peak so **real** trail pullbacks still fire
- Persist `peak_lot` in `shadow_tp_status.json`
- Clear peak/lot after **real** live TP exits (not dry_run)
- Promote re-seed also binds lot meta

### B. Isolation tests (`test_isolation_live_tp_exit.py`)

- UNI incident reproduction (must not trail-fire)
- Same-lot trail still fires after real pullback
- Entry change with lot meta resets peak  
**PASS**

### C. Display timezone (per trader)

- `config/trader_accounts.json` → `ui.display_timezone` / `locale` (default `America/Los_Angeles`)
- `trader_account_config.ui_display_settings()`
- `/api/trades` + `/api/ui-prefs` return `display_timezone`
- Dashboard formats with `timeZone: DASH_TZ` (never browser host alone)
- Ledger always stores UTC with `Z` (`trade_ledger._normalize_trade_timestamp`)

### D. Live state

- Cleared UNI peak + emptied `peak_lot` so next cycle rebinds honestly  
- Backup: `data/state/shadow_tp_status.json.bak_pre_lot_bind_20260823`

## Verification

```bash
PYTHONPATH=. .venv/bin/python phase6/core/test_isolation_live_tp_exit.py  # PASS
PYTHONPATH=. .venv/bin/python phase6/core/test_isolation_shadow_tp.py     # PASS
```

## Follow-ups

- Runner picks up code on next import/restart (Python process reload if long-lived)
- Dashboard hard-refresh for TZ JS
- Optional: surface `display_timezone` in trader settings UI later
- Watch next rebal buy: peak_lot must bind; no same-minute trail unless real arm walk-up

## Related

- LINK fixed_tp earlier same day was **healthy** (~+6.3%)
- Post-TP 24h rebuy block correctly on UNI after sells
