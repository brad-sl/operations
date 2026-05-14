# PHASE6.md — Project Codex (Fast Reference)

**Purpose:** Single source of truth for the Phase 6 live trading system. Every agent must read this file before exploring code or answering Phase 6 questions.

**Last Updated:** 2026-05-13 08:05 PT  
**Current Status:** LIVE (minimal runner) — full production runner in development

---

## Quick Facts

| Item                        | Value / Location                                                                 | Notes |
|----------------------------|----------------------------------------------------------------------------------|-------|
| **Live Runner Script**     | `operations/crypto-bot/run_phase6_live_final.py`                                 | Minimal loop only — one Fresh Start + idle |
| **Live PID**               | 433244                                                                           | Started 2026-05-12 16:08 PT |
| **Production Runner**      | `phase6.py` → `Phase6DirectTrader` + new `phase6_runner.py` (in progress)        | Target for feature/phase6-prod-runner |
| **Config File**            | `config/trading_config_phase6.json`                                              | Daily rebalance time is here |
| **Daily Rebalance Time**   | Configurable (`scheduler.daily_rebalance_time`, default `"09:00"`)               | America/Los_Angeles timezone |
| **Trading Mode**           | LIVE                                                                             | $1,000 real capital |
| **Active Pairs (Basket)**  | BTC-USD, ETH-USD, SOL-USD, XRP-USD, DOGE-USD                                     | Dynamic basket planned |
| **Risk Params**            | RSI<40 entry, +10% TP, -5% SL, daily rebalance, 0.72 deploy pct                  | From backtests |
| **State / Checkpoint**     | `phase6_state.json`, `portfolio_state.json`                                      | Maintained by LivePortfolioManager |
| **Signal Source**          | `~/.trading-bot/reports.db` (Phase 5 unified signals)                            | UnifiedSignalConsumer reads this |
| **Key Components**         | `risk_engine.py`, `live_portfolio_manager.py`, `exchange_client.py`, `multi_pair_analyzer.py` | All present and mostly implemented |

---

## Current Gaps (What the Minimal Runner Is Missing)

1. **No daily rebalance scheduler** — only runs once on start
2. **No dynamic basket logic** — hard-coded basket
3. **No signal-driven decisions** — ignores `UnifiedSignalConsumer`
4. **No native SL/TP attachment** on new positions
5. **No reporting / Telegram digests** on each cycle
6. **No proactive scanner** (RSI + sentiment + volatility)

See `memory/projects/PHASE6_SEQUENCE_DIAGRAM_AND_STATUS.md` for the full status matrix.

---

## Intended Final Architecture (High-Level)

- `phase6_runner.py` (new orchestrator) loads config → instantiates `Phase6DirectTrader`
- `Phase6DirectTrader` owns:
  - `LivePortfolioManager` (reconciliation + P&L)
  - `MultiPairAnalyzer` (proactive scanner + pair decisions)
  - `RiskEngine` (position sizing + circuit breaker)
- Daily rebalance at configured time + event-driven (correlation drift)
- Fresh Start on cold start only
- Shadow mode toggle for safe testing
- ReportingAgent + Telegram alerts every cycle

---

## How to Work on Phase 6

**Mandatory first reads (do not skip):**
1. `PHASE6.md` (this file)
2. `memory/projects/PHASE6_SEQUENCE_DIAGRAM_AND_STATUS.md`
3. `memory/decisions/PHASE6_LIVE_DEPLOY_2026-05-12.md`
4. Latest `memory/projects/phase6-live-status.md`

**To update this codex:** After any meaningful change (new runner, config field, new component), append a one-line “Updated: [date] — [what changed]” at the top and refresh the Quick Facts table.

---

## Maintenance Schedule

- **After every sub-agent or major PR** — the responsible agent updates this file (mandatory).
- **Weekly review** (every Sunday 09:00 PT via heartbeat) — verify facts against live system and prune stale entries.
- **On status change** (LIVE → PAPER, new PID, config change) — immediate update required.
- **Owner:** Primary Phase 6 agent + any human-triggered review.

**Last maintenance:** 2026-05-13 — Initial codex creation + AGENTS.md directive added.## Migration Note (2026-05-14)

This project was migrated to a clean structure on 2026-05-14.

**New Location**: `/home/brad/projects/crypto-trading-bot/`

**Git Repository**: `brad-sl/operations`

**Key Changes**:
- All Phase 4, 5, and 6 code consolidated into one place
- Core modules moved to `src/core/`
- Runners organized under `scripts/phase6/`
- Documentation centralized in `docs/`
- Fresh git history created

The original scattered locations inside `.openclaw/workspace/` can now be cleaned up if desired.
