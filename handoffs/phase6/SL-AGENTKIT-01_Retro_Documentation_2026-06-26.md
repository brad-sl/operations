# SL-AGENTKIT-01: Retro Documentation of Prior Undocumented Coinbase AgentKit SL Test (2026-06-25)

**Task ID**: t_ccda3ab2 (P0)  
**Date documented**: 2026-06-26  
**Assignee**: crypto-orchestrator  
**Status**: Documentation complete (no primary artifacts located)  
**Feeds**: SL-AGENTKIT-02 (separate run/implementation), SL-AGENTKIT-03 (isolation verification)

## Summary
User directive (from live triage): "The test we already did was apparently not documented so take this as a new task and track it. We must get the SL working reliably." And "Add the Agent Kit as a potential mitigation path. It should be run separately in place of the current method and verified."

A Coinbase AgentKit-based SL (stop-loss / stop-limit attach) test was performed by the user on or around 2026-06-25 ("yesterday" relative to 2026-06-26 task creation). It reportedly looked **promising** for bypassing the persistent `INSUFFICIENT_FUND` / `PREVIEW_INSUFFICIENT_FUND` errors observed in classic stop-limit placement (even when holdings >0 and positions confirmed open).

**Critical finding from exhaustive search (this session)**: **No traceable artifacts remain** from that specific test:
- No `coinbase-agentkit` or `Agentkit` package installed (runtime has only `coinbase-advanced-py 1.8.3`).
- No imports or references in any .py source (confirmed via full-repo grep; only examples in old `docs/COINBASE_AGENTKIT_ANALYSIS.md` and MASTER notes).
- No test scripts, snippets, or modified files dated 2026-06-25 mentioning AgentKit.
- No logs in /tmp/, project/logs/, .hermes/, or elsewhere containing "agentkit", "AgentKit", "coinbase_agentkit", or AgentKit-specific calls/outputs.
- Bash history and recent file scans yield zero matches for relevant commands (e.g. `pip install coinbase-agentkit`, python one-liners using it for SL, `from coinbase_agentkit`).
- Sibling kanban workspaces (t_e8e18a75, t_19585e09) empty at start.
- Old .hermes session snapshots reference Coinbase docs pages mentioning "AgentKit" section (May 2026 era, UI browsing only).

The test appears to have been **ad-hoc / one-off** (manual Python REPL, external script, or ephemeral terminal session not persisted to disk).

## Context: Why AgentKit Was Tested for SL (The Problem It Targeted)
Classic SL paths (current production, failing in live cutover proc_629acdae1493 and rebalance scenarios):
- `coinbase_wrapper_FIXED.py:place_stop_limit_sell()` (and exchange_client equivalents) → direct POST to Coinbase Advanced Trade `/api/v3/brokerage/orders` using `stop_limit_stop_limit_gtc` config.
- Used inside `src/stop_loss/stop_loss_coordinator.py` (CR-03: suspend_reattach_context) + `phase6/core/phase6_runner.py` (rebalance body + Fresh Start).
- Pre-flight / preview frequently returns: `{'error': 'INSUFFICIENT_FUND', 'preview_failure_reason': 'PREVIEW_INSUFFICIENT_FUND'}` even when:
  - Holdings confirmed positive (e.g. total value ~$717 across positions).
  - Open SL orders exist holding the sizes.
  - Cash low / reserve issues separate (PROD-03).
- Related symptoms (June 25 / June 26 logs):
  - Example from /tmp/rebalance_after_sl_cancel_1782430074.log (2026-06-25):
    ```
    Stop-limit order may have failed: ... 'error': 'INSUFFICIENT_FUND' ... 'preview_failure_reason': 'PREVIEW_INSUFFICIENT_FUND'
    ```
    (stop_limit config with base_size ~45.47 for some asset, limit/stop prices set, reduce_only=False in some cases).
  - Similar in live_cutover logs during cycles.
- Other contributing: 401s on get_open_orders/historical (fixed separately), sizing using "available" vs "total" holdings (hardened in PROD-02/03), missing reduce_only in some paths.

**Why AgentKit looked promising (per user report + inference from architecture)**:
- AgentKit (coinbase-agentkit / CDP SDK) provides **higher-level, agent-friendly action abstractions** for wallet + execution instead of raw REST order configs.
- Potential differences:
  - Different internal preview / funds validation logic (or none for certain "attach"/reduce operations).
  - Wallet-centric balance queries (may report "total" or "spendable" differently than direct holdings + SL-hold semantics).
  - Pre-built or custom actions for stops/orders that may succeed where raw stop_limit_gtc preview fails (e.g. explicit reduce-only semantics, or different order type routing).
  - Better error taxonomy and validation before hitting Coinbase preview gate.
  - From older analysis (docs/COINBASE_AGENTKIT_ANALYSIS.md): Excels at secure execution layer; abstracts complex interactions; "production-grade" for onchain/execution. (Note: primary focus was EVM/Solana onchain, but Coinbase has expanded Advanced Trade / agent support.)
- Goal for separate path: Replace or parallel the attach logic so SL can be placed reliably on existing holdings without triggering the classic preview fund rejection. Run **separately** (no mixing in same cycle) to isolate effect.
- User context emphasized "bypassing INSUFFICIENT_FUND/preview issues".

**Related older analysis**:
- `docs/COINBASE_AGENTKIT_ANALYSIS.md` (2026-03-23): Strategic positive for execution/wallet (post-Phase 2), examples of create_wallet / transfer. Explicitly NOT integrated for spot/SL at the time. Recommends phased eval.

## Evidence Collected (This Session - Real Tool Output)
- Pip / env: `coinbase-advanced-py 1.8.3` only; `pip show coinbase-agentkit` → not installed.
- Code search: Only doc examples + MASTER references to "never integrated".
- File system: No matching new files on 2026-06-25 for AgentKit terms.
- Sample failure log (classic path): See /tmp/rebalance_*_17824*.log (June 25) and live_cutover_*.log excerpts in MASTER.
- Kanban/MASTER: This task + siblings (t_e8e18a75 SL-AGENTKIT-02, t_19585e09 SL-AGENTKIT-03) + t_902e8896 (earlier eval) created during 2026-06-26 triage.
- Git: Minimal recent activity; no AgentKit commits.

## Recommendations / Next (for SL-AGENTKIT-02/03)
1. Treat as **separate mitigation path** only (config flag or dedicated shadow runner disabling classic SL/CR-03 attach).
2. Minimal pilot: 
   - `pip install coinbase-agentkit` (in isolated env or note deps).
   - Implement toggleable handler (e.g. `phase6/core/agentkit_sl.py` or `src/stop_loss/agentkit_stop_loss.py`) using relevant actions (investigate `create_order` or custom if available for stops; wallet.get_balance etc.).
   - Paper test first (mock AgentKit), then shadow with real keys.
3. Metrics to capture: attach success rate, specific errors vs classic INSUFFICIENT, latency, impact on holdings/positions.
4. Gate: Only promote if >90% reliability in controlled tests + no regression on suspend/reattach semantics.
5. Parallel to classic fixes (reduce_only, sizing, queries already landing in PROD-02 etc.).
6. Update requirements, .env.example if proceeding; preserve fallback to classic.

## Artifacts
- This file: `workspaces/t_ccda3ab2/SL-AGENTKIT-01_Retro_Documentation.md`
- Cross-ref in MASTER_TASK_TRACKING.md (appended section below).
- Related handoffs/kanban comments.
- Classic SL code refs: phase6/core/stop_loss_coordinator.py, stop_loss_manager.py, exchange_client.py, coinbase_wrapper_FIXED.py, runner.py.

**No fabricated evidence**. All statements grounded in searches, logs, MASTER, user directive, and live state inspection. Test "existed" per user report; documentation now formalizes the gap.

---
*Documented as part of P0 SL reliability hardening. Classic path issues persist in live despite partial fixes; AgentKit evaluated as independent experiment.*
