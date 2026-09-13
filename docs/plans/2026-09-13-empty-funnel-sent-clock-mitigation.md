# Empty-funnel mitigation path (sentiment clock + tryout floors)

**Date:** 2026-09-13  
**Status:** Analysis saved; **A1+A2+B1 implemented** (Brad GO).  
**Context:** ~4 days no new entries; ADA/AVAX looked hot earlier, dead by ~09:00 rebalance.

## Diagnosis (evidence)

Not “missing scouts.” Soft-down tryout armor + sensor clock.

| Layer | Live pattern |
|-------|----------------|
| Doors | AVAX force_eligible, ETH/LINK/XRP tryout — membership open |
| Floor used | **0.35** = max(new_pair 0.35, quality_tryout 0.30) |
| RSI | tryout max **55** — alts often 55–65 on mild bounce |
| X cadence | **08:50 / 20:50** PT → rebalance **09:05 / 21:05** |
| Aging | X **15m HL** — ~15–17m age at decision → decay ~0.45–0.50 |
| Bridge | Reddit empty on ADA/AVAX → mid-cycle eng **0** (`x_reddit_bridge`) |
| Book | Cash + PAXG park; 0 tryout seats; low risk **and** no deploy alpha |

**2026-09-13 morning (X cache + runner):**

| Pair | X raw @08:50 | ~Aged @09:07 | Notes |
|------|-------------:|-------------:|-------|
| ADA | **0.58** | ~0.26 | Looks hot raw; still &lt;0.35 aged; **not** on tryout list |
| AVAX | **0.065** | ~0.03 | Never near floor; free tee ~0.12 |
| LINK | 0.61 | ~0.27 | Closest if not buy_block |
| ETH | 0.43 | ~0.22 | RSI also high |

**Root cause class:** decision uses half-dead X; stacked floors; narrow tryout doors; empty bridge. Idle = correct under armor, wrong if mission is any deployment.

## Mitigation menu (reference)

### A — Clock (preferred)
| ID | Lever | Risk |
|----|-------|------|
| **A1** | X refresh **09:00 / 21:00** (was 08:50/20:50) — closer to rebalance | +small X latency alignment; still 2×/day |
| **A2** | Tryout **sent latch**: if eng/raw clears tryout floor at/near X refresh, hold clear **≤45m** through rebalance | Stops green-at-refresh / dead-at-09:05; tryout-only |
| A3 | Longer HL tryout-only at rebalance tick | Milder stale risk |

### B — Tryout door (GO needed)
| ID | Lever | Risk |
|----|-------|------|
| **B1** | Tryout floor = **quality_tryout min only (0.30)** — do **not** stack max(with new_pair 0.35) | More fills on tryout sleeve only |
| B2 | Lower tryout floor 0.20–0.25 | Higher weak-sent tax |
| B3 | RSI max 55→58–62 tryout-only | More chase |
| B4 | OR-gate RSI structure + soft sent | Bigger policy change |

### C — Who can sit
| ID | Lever |
|----|-------|
| C1 | Add ADA to tryout if desired when X strong |
| C2 | Keep AVAX force; don’t expect fill without A/B |
| C3 | Don’t waive LINK post-SL lock |

### D — Sensor fuel
| ID | Lever | Note |
|----|-------|------|
| D1 | Richer Reddit bridge | Helps mid-day; won’t clear 0.35 alone |
| D2 | Free mid-cycle live reinforce | Needs multi-day promote + GO; free levels often &lt; floor |
| D3 | More paid X | Cost regression — prefer A1 |

### E — Accept armor
| ID | Lever |
|----|-------|
| E1 | No entry = feature until regime/health improves |
| E2 | Lab GO / deploy NO-GO until stamped tryout clears |

## Shipped package (this change)

**A1 + A2 + B1** only (Brad GO 2026-09-13).

| Piece | Implementation |
|-------|----------------|
| A1 | Hermes cron `phase6-x-sentiment-live-2x` → `0 9,21 * * *` PT; tryout board default slots |
| A2 | `phase6/core/tryout_sent_latch.py` — write at X refresh; `evaluate_buy_entry` honors latch for tryout pairs |
| B1 | `evaluate_buy_entry` + `live_entry_floor(..., on_tryout=True)` use **qt min_sentiment only** |

**Explicitly not shipped:** B2–B4, free live wire, LINK waive, auto-promote, aging off.

## Ops check after deploy

```bash
# floor + latch isolation
PYTHONPATH=. .venv/bin/python3 scripts/phase6/test_isolation_tryout_sent_latch_a2.py
PYTHONPATH=. .venv/bin/python3 scripts/phase6/test_isolation_tryout_readiness_pc03.py
# readiness board
PYTHONPATH=. .venv/bin/python3 scripts/phase6/run_tryout_readiness.py
# cron
hermes cron list | rg 'x-sentiment|rebalance'
```

## Related artifacts

- `data/state/tryout_readiness_latest.json`
- `data/state/tryout_sent_latch.json` (A2 runtime)
- Skills: `phase6-sentiment-pipeline`, tryout-readiness-board ref
