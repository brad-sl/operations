# Agent quality gates (Hermes + Phase 6)

**MASTER:** `HERMES-QUALITY-LOOP-20260909`  
**Brad GO:** 2026-09-09  
**Code:** `scripts/hermes/pre_ship_quality.sh` → `scripts/hermes/pre_ship_quality.py`

## Why this exists

Painful bugs were class failures, not missing features: swallowed `TypeError`, config≠path, unlimited waivers, stale Hermes script copies. Chat review is optional; **this gate is not**.

## Before you bounce the live runner

```bash
cd /home/brad/projects/crypto-trading-bot
bash scripts/hermes/pre_ship_quality.sh
# expect: PRE-SHIP QUALITY PASS
```

Exit **2** = do not restart runner, do not claim shipped.

`commit-safe-code.sh` (manual, no `SAFE_CODE_SKIP_QUALITY`) also runs this before commit.

## What it checks (P0)

1. `TradeLedger.get_recent_trades` accepts **`hours=`** (72h cooldown hole)
2. `evaluate_buy_entry` wires `pair_process_tax_lockout_reasons` + `collect_buy_block_pairs`
3. Money files: no `except Exception: return []` **without a log** (`phase6_runner`, ledger, capital_events)
4. `data/state/buy_block_waivers.json`: no unlimited `expires_ts=null` + `scope=all`
5. Isolation scripts listed in `pre_ship_quality.py` (`ISOLATION`)

Nightly cron (`pre-ship-quality-nightly`): `PRE_SHIP_QUIET=1` — **Telegram only on FAIL** (empty stdout on pass).

## Code-reviewer packet (SL / ledger / config diffs)

Use `docs/templates/CODE_REVIEWER_PACKET_SL_LEDGER_CONFIG.md` with profile `code-reviewer`. Do not skip because isolation already passed — grep **live call sites**.

## Must not

- Skip the gate “because tests passed in chat”
- `SAFE_CODE_SKIP_QUALITY=1` on a money-path ship (daily backup only)
- Restore LINK-class waivers with `scope=all` / `expires_ts=null`
- Edit `~/.hermes/scripts/*.py` copies — thin `exec` wrappers only
- Pin tryout scars into permanent `buy_block_pairs` just to silence a gate (use funnel + expiring locks)

## Funnel-first / rare perma-block (product law)

| Layer | Role | Permanent? |
|-------|------|------------|
| Qualify / thaw / tier / novelty | Who may *compete* | Time-bounded / reversible |
| Missfire / first-fill / 72h post-SL / same-day seat | Process tax | Auto-expires or packet-clear |
| Regime park / bear | No new alt risk | Regime-bound |
| **`buy_block_pairs`** | Nuclear “never buy this name” | **Exceptional operator pin only** |

**Live hard list SSOT today:** `RAVE-USD`, `UNI-USD` (operator scars).  
**Not** every wounded tryout (e.g. LINK after a bug-class SL → ledger correction + time-bounded waiver).

**When perma-block is justified:** toxic beyond the funnel (repeated wounds after gates, broken venue product, explicit never-again). Prefer **named + dated + review/unpin** (novelty `hard_pin_block` is closer than stuffing names into config forever).

**Isolation that encodes this:** `scripts/phase6/test_isolation_process_tax_lockout.py`  
(`test_live_hard_block_ssot_scar_pairs_only` — RAVE/UNI in, LINK out of hard list).  
Also: `phase6/core/test_isolation_buy_block_pairs.py`, missfire / novelty / recovery tryout isolations.
