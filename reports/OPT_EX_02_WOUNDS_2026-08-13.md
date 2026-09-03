# OPT_EX_02 — 3d same-session SL post-gate (read-only)

**Task:** `P6-OPT-EX-02-WOUNDS-20260813` · Kanban `t_9b3ab866`  
**As of:** 2026-08-15  
**Race-fix deploy cut:** 2026-08-13

## Call

**`watch`**

## Headline

**3-day post-fix count = 0. Crisis? no.**

Ops finding should fire only if 3d count > 0 — it does not.

## Numbers (real ledger)

```text
summarize(lookback_days=3.0) → count_2h=0, count_5m=0, pairs=[]
post 2026-08-13 examples in latest state → 0
```

30d historical (context only — **not** a new crisis):

| Pair | BUY→SL Δ | When |
|------|----------|------|
| RAVE-USD | ~28s | 2026-08-12 (pre cut) |
| LINK-USD | ~29s | 2026-08-04 |
| OP-USD | ~44s | 2026-07-20 |
| ARB-USD | ~2s | 2026-07-17 |

All four 30d examples are **before** the armed-stop race fix cut. Alts cluster historically; no BTC/PAXG same-session in the examples list.

## Dust

Dust after SL ≠ armed PAXG — no new PAXG arm implied by this metric. Not pursued here.

## Call enum

`watch` — keep 3d watchdog; do not treat 30d pre-fix brief counts as a fresh P0.
