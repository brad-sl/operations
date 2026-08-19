# Handoff: P6-DASH-KPI-TRUTH — Dashboard KPI accuracy cleanup

**Date:** 2026-07-16  
**Owner implementer:** `crypto-engineer`  
**Reviewer:** `crypto-orchestrator` / default  
**Board:** `crypto-bot-project`  
**MASTER id:** `P6-DASH-KPI-TRUTH-20260716`  
**Priority:** High  

## Objective

Make Phase 6 dashboard KPIs **honest and hard to misread**: no fake 0% periods, Util matches cash vs risk, SL OK reflects real protection, ops tiles use correct labels, and operators understand **portfolio 7D % ≠ per-position 3% SL**.

## Context (evidence 2026-07-16 evening)

Screenshot + live API review:

| Issue | Evidence |
|-------|----------|
| **30D = 0.00%** | `account_balances` min ts ~2026-06-28; 30d window has no real baseline → code returns **0.0** (looks flat) |
| **Util 98%** with ~$1.7k cash of ~$2.58k | Tooltip says non-cash share / ARCH-4 exposure; **cash-heavy book cannot be 98% deployed** |
| **SL 0%** | `/api/metrics` `sl_success_rate: 0.0` while positions show `sl_stop_price_est`; rebalance BUYs often `sl_attached: false` in ledger |
| **Health 2.2 / Active 22 / Capital 100%** | Map to **churn / rebalance_count / replay_match** — not portfolio health, open pairs, or capital deploy |
| **Exit WR 0%** | Correct for last-100 nonzero PnL (0 wins / ~28–29 losses) — keep definition, improve labeling |
| **7D ~−15–16% deposit-adj** | Not a “3% SL failed globally” bug — see § SL vs 7D below |

Files:

- `phase6_dashboard.html` (tiles, tooltips)
- `serve_dashboard.py` (`/api/performance`, `/api/metrics`)
- `phase6/core/dashboard_serve_helpers.py` (`compute_period_performance`, `fast_observability_metrics`)
- SL truth: `phase6/core/ledger_sl_truth.py`, exchange protective orders, `scripts/phase6/audit_rebalance_sl_gaps.py`
- Isolation: `scripts/phase6/test_isolation_*.py` under phase6 dashboard/KPI tests

## Scope

### Must Do

1. **30D (and any period) insufficient history**  
   - If no snapshot at/before cutoff, return **null** / omit numeric 0.  
   - UI: show **—** or **N/A**, never **0.00%** for missing window.

2. **Util (actual)**  
   - Primary display: `holdings_value / total_usd` from live positions.  
   - Optional secondary: ARCH-4 target exposure — separate label if shown.

3. **SL OK truth**  
   - Do not publish permanent **0%** from empty DB metric.  
   - Prefer: fraction of **open trading positions** with exchange protective stop (or verified ledger attach after rebalance).  
   - Hover: “not portfolio max loss.”

4. **Ops tile labels** (match current HTML intent; fix any remaining wrong labels in UI/JS)  
   - Util, Accept, SL OK, Churn, Rebal, Recov, Replay — **not** Health / Active / Capital unless those mean something real.  
   - Ensure JS binds metrics to the correct DOM ids.

5. **Exit WR**  
   - Keep `ledger_nonzero_pnl` definition.  
   - Always show **wins/total** subline; tooltip: not equal to 1D/7D.

6. **1D/7D vs SL education**  
   - Tooltip on 1D/7D: deposit-adjusted **wallet** return; **3% SL is per-position from entry**, not portfolio DD cap.  
   - Short note in `docs/CAPITAL_AND_PORTFOLIO_EVENTS.md` or `docs/Trading_Bot_FAQ.md` if present.

7. **Isolation tests** for period N/A, util formula, SL OK source. 
8. Restart dashboard live (`bash scripts/phase6/restart_dashboard_live.sh`) and curl verify. 
9. Update MASTER status + checklist JSON if used.

### Must Not Do

- Change live risk parameters / stop %. 
- Fake historical snapshots to force non-zero 30D. 
- Use placeholder prices. 
- Touch marketing / non-dashboard paths.

## SL vs 7D −16% (for implementer + FAQ)

**User is partly wrong to expect 7D ≈ −3%.** Reasons (document in tooltip/FAQ):

1. **Per-position stop ≠ portfolio stop.** Each bag can lose ~3% from *its* entry; the **wallet** can lose much more over a week via many positions and many cycles. 
2. **Re-entry / rebalance:** Stop out ~−3%, redeploy, stop again → cumulative 7D can be −10% to −20%+ with repeated rounds. 
3. **Unrealized MTM:** Open book can sit at −1% to −2% without hitting stop; large DOGE size dominates $ PnL. 
4. **Stops are not always exact −3%:** stop-limit gaps, fees; recent ledger sells show `pnl_pct` from ~−1.6% to **−6%**. 
5. **Attach gaps:** rebalance BUYs with `sl_attached: false` mean **some legs may be unprotected** until recovery — separate bug (see existing P6-OPS SL attach tickets). 
6. **Deposit-adjusted 7D** strips external cash; it is still **whole-account** return, not max single-trade loss.

**What would be a real SL violation:** open position with **live price through stop** for long without fill, or missing exchange stop on size. That needs exchange order audit — optional follow-up card if attach audit fails.

## Deliverables

1. Code patches + isolation tests green  
2. Dashboard restart + `curl` evidence for `/api/performance` and `/api/metrics` 
3. MASTER append with pass/fail 
4. Short FAQ blurb: 7D vs 3% SL 

## Success criteria

- [ ] Missing period windows never show `0.00%` as a real return 
- [ ] Util matches holdings/total within ~1% of live positions API 
- [ ] SL OK is either real attach rate or **—** if unknown (never stale 0% from empty view) 
- [ ] Ops labels match metric meaning 
- [ ] Exit WR shows wins/total 
- [ ] Isolation tests pass 
- [ ] No live trading config change 

## Validation

```bash
cd /home/brad/projects/crypto-trading-bot
bash scripts/phase6/restart_dashboard_live.sh
curl -s http://127.0.0.1:8502/api/performance | python3 -m json.tool
curl -s http://127.0.0.1:8502/api/metrics | python3 -m json.tool
# Util: compare to positions total_holdings_value / total_usd
# 30d: null/N/A if history < 30d
PYTHONPATH=. .venv/bin/python3 scripts/phase6/test_isolation_*.py  # relevant new/updated tests
```

## Related open ops

- P6-OPS-20260713-001 — rebalance BUY `sl_attached: false`  
- Ledger SL truth work 2026-07-15 (`ledger_sl_truth.py`) — ensure dashboard consumes it  

---

*Handoff for Kanban standard process — implementer owns end-to-end; reviewer re-runs curls + tests.*

## Reviewer Sign-off Addendum (2026-07-17)
Fresh re-run post-implement (this session):
- restart + curls + test_isolation_kpi_truth.py : PASS (d30=None, util holdings/total ~0.8475 match, sl=1.0 from live pos)
- Positions audit: 5/5 with SL est; util calc exact
- HTML/FAQ: 7D/portfolio vs per-position 3% SL documented in tooltips + Trading_Bot_FAQ.md
- MASTER + triage updated with full evidence + sign-off
- All Must Do / success criteria met. t_08a89c44 complete.
