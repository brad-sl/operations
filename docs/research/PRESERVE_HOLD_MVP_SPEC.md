# Preserve Hold MVP Spec (G3) — gated

**Status:** CODE SHIPPED · **LIVE MICRO** (`micro_live` ~$75; full 20% still off)  
**Date:** 2026-08-02 · **Posture check:** 2026-08-07  
**MASTER:** `PRESERVE-HOLD-MVP-20260802` · gate `PRESERVE-FUNDAMENTALS-GATE-20260802`  
**PRD:** `docs/research/PRESERVE_MODE_PRD.md`  
**Gates passed:** G1 **A**, G2a **PASS**, G2b **DeRisk stays OFF**  
**Code:** `phase6/core/preserve_hold.py` · CLI `scripts/phase6/arm_preserve_hold.py`

### 2026-08-07 posture (honest)

| Piece | State |
|-------|--------|
| MICRO ~$75 PAXG + E1 path | **Where we left it** — learning sleeve / kill-bot path; **not** full ballast |
| Full 20% Hold | Still **manual scale only** — not auto |
| DeRisk ladder | **OFF** |
| **Full park package: USDC carry (~3.5% APY *research class*, venue-quoted live) + PAXG Hold** | **Not implemented** as one product scenario — USDC park executor exists but primary account `enabled=false`; no unified A+B onboarding package |
| Personalized prefs for park/hold | Spec’d under `docs/features/TRADER_PERSONALIZED_SETTINGS_SPEC.md` §4–5 |

Do **not** treat current MICRO as completion of the USDC+gold park vision.

---

## Plain English

We only want **Hold** for v1: put about **20%** of the *cash+gold* sleeve into PAXG while crypto is parked, leave it alone through normal gold crashes, and keep **one deep emergency stop on Coinbase at −32%** from buy price.  

We will **not** auto-sell gold at −12/−18 as the default (that’s DeRisk; economics say it often underperforms hold over long samples and sells into holes).

---

## Gate evidence

| Gate | Result | Artifact |
|------|--------|----------|
| G1 Venue | **A** — 3 concurrent stop-limits on `PAXG-USD` placed, listed path OK, cancelled, residual sold | `reports/PRESERVE_VENUE_PROBE_2026-08-02.md` |
| G2a Hold | **PASS** — E1 −32% does **not** fire on arm-at-peak 2026 −28.1% path; book ~−5.4% | `reports/PRESERVE_HOLD_DERISK_ECONOMICS_2026-08-02.md` |
| G2b DeRisk | **KEEP_DISABLED_DEFAULT** — ladder fires S1/S2 into stress; full-sample ladder ≪ static hold | same |

Probe cleanup verified: **0 open PAXG stops**, **0 PAXG inventory** after run.

---

## In scope (Hold MVP only)

1. Config `preserve_mode.profile = "hold"`, `enabled=false` until operator arm  
2. Arm only if crypto sleeve **parked** (`allow_preserve_with_crypto_util=false`)  
3. Build PAXG to `target_pct=0.20` of `cash_plus_preserve_mtm`  
4. Place **one** resting protective sell **E1 @ −32%** from `arm_vwap` (~98% size, dust after)  
   - Prefer stop-market if we add support later; stop-limit proven on venue today  
5. At −12% from arm (bot MTM): `adds_blocked=true` persisted — **no buys**  
6. Deploy/bull: cancel E1 → sell PAXG → clear state  
7. Sleeve tags on orders/fills; crypto cancel/suspend **must not** strip Preserve E1  
8. Kill-bot test: E1 still open after runner stop  
9. Min ballast notional **$500** (below → still single E1, watch min size)  
10. Dashboard: profile Hold · % · E1 status · adds_blocked · never “risk-free”

## Out of scope

- DeRisk S1/S2/S3 multi-leg product  
- HWM trail  
- Auto-arm  
- Timed BTC→gold  
- USDC yield productization  
- Multi-tenant packs  

---

## Config freeze (do not apply live until implement plan + Brad arm)

```json
"preserve_mode": {
  "enabled": false,
  "armed": false,
  "profile": "hold",
  "target_pct": 0.20,
  "asset": "PAXG-USD",
  "preserve_equity_base": "cash_plus_preserve_mtm",
  "allow_preserve_with_crypto_util": false,
  "hold": { "e1_dd_pct": -0.32, "soft_adds_block_dd_pct": -0.12 },
  "derisk": { "enabled": false },
  "venue_probe_result": "A",
  "venue_probe_date": "2026-08-02"
}
```

---

## Implementation blast-radius checklist (when coding)

- [x] `stop_loss_manager` / suspend protective — filter preserve sleeve  
- [x] dust orphan skip when preserve armed  
- [x] registry `sleeve=preserve` / reason `preserve_e1`  
- [x] isolation: no auto-arm, naked-arm forbidden, suspend skip, adds_block latch  
- [ ] capital_event cancel paths (basket usually excludes PAXG; suspend already filters)  
- [ ] dashboard badges (optional follow-up)  
- [ ] kill-bot live soak with tiny arm (operator)  

---

## Operator arm (live still gated)

```bash
# preview only
PYTHONPATH=. .venv/bin/python scripts/phase6/arm_preserve_hold.py arm --dry-run

# live (crypto must be parked; flips enabled if you pass --set-enabled)
PYTHONPATH=. .venv/bin/python scripts/phase6/arm_preserve_hold.py arm --set-enabled --i-understand

PYTHONPATH=. .venv/bin/python scripts/phase6/arm_preserve_hold.py status
PYTHONPATH=. .venv/bin/python scripts/phase6/arm_preserve_hold.py disarm --i-understand
```

Until then live safety = **REGIME-CASH USDC park** only.
