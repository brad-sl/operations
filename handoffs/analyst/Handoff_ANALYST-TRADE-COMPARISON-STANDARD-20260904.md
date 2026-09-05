# Handoff — ANALYST-TRADE-COMPARISON-STANDARD-20260904

**Role:** crypto-analyst  
**Goal:** Platform-standard trade comparison methodology (not LINK-only).  
**Live boundary:** paper dig + shadow would-block only until Brad GO.

## Must Do
1. Use `phase6/research/trade_comparison_standard.py` scoreboard SSOT.
2. Run isolation: `phase6/research/test_isolation_trade_comparison_standard.py`
3. Run multipair dig: `phase6/research/run_trade_comparison_dig.py`
4. Attach reports to CR / trial finalize-report.
5. Generalize a rule only if leak on ≥2 pairs or multipair CF confirms.
6. Shadow logger first — **no** `evaluate_buy_entry` / config writes without Brad GO.

## Must Not Do
- Invent entry RSI/sent stamps on old fills.
- Call process hygiene a HIT_10 printer.
- Auto-promote cooldowns from single-pair anecdote.
- FIFO-only PnL as book truth (SELL pnl sums are SSOT).

## Success criteria
- Isolation PASS on fixtures + live LINK slice.
- Multipair dig JSON/MD written under `data/state/` + `reports/`.
- Skill `trade-comparison-standard` documents procedure + edge vocabulary.
- Backlog proposals minted (methodology + LINK shadow cooldown).
- MASTER Type:test registered for offline multipair confirm / shadow follow-on.

## Artifacts
- Core: `phase6/research/trade_comparison_standard.py`
- Runner: `phase6/research/run_trade_comparison_dig.py`
- Isolation: `phase6/research/test_isolation_trade_comparison_standard.py`
- LINK case: `reports/LINK_TIMING_DIG_2026-09-04.md`
- Skill: Hermes `trade-comparison-standard`
