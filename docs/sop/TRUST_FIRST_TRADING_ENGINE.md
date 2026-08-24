# SOP — Trust-first trading engine (both ends)

**Status:** standing product standard  
**Audience:** ops, agent, anyone changing live entry/exit paths  
**Last updated:** 2026-08-23  

## One-line standard

Trust is the product. Customer service means the book does what the rules say, **both ends** of the trade are honest, and failures are loud and rare — not silent and expensive.

Excitement follows a week of boring, correct in/out cycles. Until then the win is: *it behaved*.

## What “both ends” means

| End | Job | Trust signal |
|-----|-----|----------------|
| **Get in** | Size + timing only when gates say go; cash/blocks real | No phantom BUY with no fill; no blocked pair sneaking in |
| **Protect** | SL on **this** lot, under **this** entry, soon after fill | Never naked bag; never stale anchor |
| **Get out** | TP only after real progress; SL when wrong | No flip-flop trail dump; no “profit take” at −0.3% |
| **After exit** | Short, correct cool-off (24h TP / longer SL); free capital when policy says free | No stacked 48h “manual” on a real TP |

## How we build trust (not hype)

1. **Predictable mechanics** over clever stories — lot-bound peaks, ledger-true blocks, local timestamps that match the fill.
2. **Proof after every change** — isolation tests + live monitor that only speaks when wrong.
3. **Honest UI** — blocked is blocked; cooldown lists real pairs; times in trader TZ; no soft “cap $N” that isn’t hard on every path.
4. **Operator clarity** — go/no-go first; when money moved, say fill, SL, peak, and whether it matched policy.

## Minimum checklist after any live BUY (rebal or mid-cycle)

Pass all before calling the entry “good”:

1. Ledger BUY row exists (qty/price/order_id).
2. Exchange SL present; stop **below** this lot’s entry (~adaptive 1.5–5% band for crypto sleeve; preserve E1 is separate).
3. `peak_lot` bound for the pair; `peak_r ≈ mark_r` right after buy (near 0 if flat) — **not** a leftover peak from a prior bag.
4. No LIVE-TP / trail fire within ~10 minutes unless mark actually cleared arm (~+4%) then trailed.
5. Blocks/cash-hold match policy (e.g. LINK post-TP = 24h ledger only; no surprise cash park on TP).

## Minimum checklist after any live SELL

1. Ledger reason is true (`take_profit_*`, `stop_loss_exchange`, dust, rotation — not mis-tagged manual).
2. Disposition: TP → **no** cash hold + **no** 48h capital cooldown (24h post-TP only). SL → SL policy. Manual → manual policy.
3. Peak cleared for fully exited pair (not dry-run).
4. Residual dust swept when under dust caps (crypto sleeve).

## Known incident anchors (do not regress)

| Date | Issue | Lesson | Report / code |
|------|--------|--------|----------------|
| 2026-08-23 | UNI trail dump ~90s after rebal buy (stale `peak_r`) | Peaks are **lot-bound** | `reports/INCIDENT_UNI_STALE_PEAK_TP_2026-08-23.md`, `phase6/core/shadow_tp.py` `sanitize_peak_r_for_lots` |
| 2026-08-23 | TP exits stamped 48h manual + cash hold | Classify TP in disposition; post-TP = 24h ledger only | `runner_capital_events.split_disposition_pairs_by_ledger` |
| 2026-08-23 | Dashboard times looked like “4pm” for 9am PT fills | Display = trader `ui.display_timezone`; store UTC Z | `config/trader_accounts.json`, `phase6_dashboard.html` |
| 2026-08-23 | Recovery “Cooldown Pairs: None” while UNI/LINK blocked | Recovery SSOT = `load_buy_block_status` | `/api/recovery` in `serve_dashboard.py` |

## Live monitor (alerts only when wrong)

- Script: `scripts/phase6/monitor_reentry_sl_tp.py`
- Latest artifact: `data/state/reentry_sl_tp_monitor_latest.json`
- Cron: Hermes job **`phase6-reentry-sl-tp-monitor`** every 10m → Telegram on alert, silent when clean
- Wrapper: `~/.hermes/scripts/phase6_reentry_sl_tp_monitor.sh`

## Force rebalance (ops)

```bash
cd /home/brad/projects/crypto-trading-bot
touch data/state/force_rebalance.flag
# runner consumes flag on next cycle (~1 min); watch logs for [FORCE] + FILL-RECON + SL reattach
```

## Related skills & docs

- Exit layers plain English: skill `phase6-exit-automation` (+ `references/exit-layers-plain-english.md`)
- SL / dust / near-stop: skill `phase6-sl-exits-and-dust`
- SL vs live TP economic floor (no ATR adapters): `docs/research/SL_TP_SYMMETRY_FLOOR.md`
- UI honesty: skill `ui-expectation-honesty`
- Exit automation config: `config/exit_automation.json`, `docs/EXIT_AUTOMATION.md`
- This SOP path (canonical): **`docs/sop/TRUST_FIRST_TRADING_ENGINE.md`**

## Communication default (Brad)

- Plain English go/no-go first.
- Then fill / SL / peak / block facts.
- Never frame a bug-path sell as a clever profit take.
