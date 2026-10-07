# Post-Proof Dwell — LIVE apply armed

**Date:** 2026-10-06  
**Brad GO:** live_apply true  
**Config:** `config/post_proof_dwell.json`  
**Edge class:** `ATTENTION_ONLY_less_loss_path` (unchanged — hygiene, not alpha claim)

## What flipped

| Knob | Before | After |
|------|--------|-------|
| `live_apply` | `false` (shadow only) | **`true`** |
| Kill file | absent | still honored if created |
| Shadow crumbs | on | still on (audit trail) |

## Money paths now enforced

1. **Composer** (`rsi_event_tryout_seat_composer` → `apply_to_composer_candidate`):  
   `skip_seat` when graduated / post-TP tryout ban — **blocks new $25 reincarnation**.
2. **Scale-window board** (`tryout_scale_window.evaluate_pair`):  
   when `apply_skip`, clears `would_eject` → status `dwell_hold` — **no auto-eject on graduated**.
3. **Ledger** still stamps TP/trail proof → graduate / SL demote (unchanged).

Unproven shells (HYPE-class, SUI-class) **still eject**.

## Live proof (2026-10-06 post-flip)

```
CONFIG live_apply True
active graduated: SOL-USD, TIA-USD

TIA-USD  APPLY_BLOCK True  APPLY_SKIP True  (graduated_hold + post_tp ban)
SOL-USD  APPLY_BLOCK True  APPLY_SKIP True  (graduated_hold)
SUI-USD  APPLY_BLOCK False APPLY_SKIP False (unproven — kill OK)
HYPE-USD APPLY_BLOCK False APPLY_SKIP False
LINK-USD APPLY_BLOCK False (dwell expired)

TIA evaluate_pair → would_eject=False status=dwell_hold
HYPE evaluate_pair → would_eject=True  status=window_closed
```

## Tests

- `test_isolation_post_proof_dwell.py` — **8/8**
- `test_isolation_tryout_scale_window.py` — **13/13** (iso mock + new live_apply eject-clear case)

## Ops

- Kill OFF: `touch data/state/post_proof_dwell_KILL` (or set `live_apply: false`)
- Next scale-window board will **hold graduated** names instead of auto-selling them
- SOL already flat from earlier shadow-era eject — dwell cannot un-eject past fills
- TIA trail TP already banked; re-seat blocked ~48h / while graduated

## Product one-liner

Prove → dwell under SL/trail → no tryout reincarnation → unproven still die.
