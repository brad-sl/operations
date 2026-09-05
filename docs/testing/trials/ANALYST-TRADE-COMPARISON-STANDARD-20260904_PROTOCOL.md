# Protocol — ANALYST-TRADE-COMPARISON-STANDARD-20260904

**Master task:** `ANALYST-TRADE-COMPARISON-STANDARD-20260904`  
**Kind:** `offline_analysis`  
**Family:** `trade_comparison_standard`  
**Regimen:** `docs/testing/TEST_REGIMEN_E2E.md`

## 1. Hypothesis
Process leak classes (post-SL reentry, post-TP rebuy, pile-on, elevated-RSI large ticket, same-day churn) explain a material share of pair-level SELL PnL tax on the live ledger; a shared scoreboard can rank pairs and paper rules without pair-anecdote knobs.

## 2. Non-goals
- No live trading config / regime policy / evaluate_buy_entry writes without Brad + promotion gates
- Real ledger + public OHLCV only
- Single-pair LINK dig is **seed case**, not promote authority
- Short windows are context only

## 3. Design
| Item | Value |
|------|--------|
| Control / baseline | raw process (no cooldown/cap) matched book |
| Arms | paper rules A–F from scoreboard (would-block CF) |
| Data | `trades/phase6_trades.jsonl` + optional Coinbase hourly |
| Primary window | full live ledger since 2026-06-20 (or go-live) |
| Context | per-pair LINK deep dig 2026-09-04 |
| Fees | label ~1.6% RT taker-taker when marking CF |
| Runner | `phase6/research/run_trade_comparison_dig.py` |
| Core | `phase6/research/trade_comparison_standard.py` |

## 4. Success criteria (frozen before multipair CF claim)

| Gate | Value |
|------|--------|
| primary_window | full_ledger_live |
| sensor_preflight_ok | true (`sensor_ok`) |
| min_pairs_with_sells | ≥ 5 |
| generalize_rule | leak on ≥2 pairs **or** explicit multipair CF |
| must_show_edge_class | required on every pair board |
| sparse_is | inconclusive_not_promote |
| live_promote_allowed | false |
| shadow_ok | would-block logger only |

**CR accept for shadow wire only if** multipair dig shows repeated leak class and isolation PASS.  
**CR accept for live gate** only on separate Brad GO.

## 5. Outcome recording
`outcome.class` ∈  
`HIT_CRITERIA` | `EDGE_VS_BAGS_ONLY` | `ATTENTION_ONLY_less_loss_path` | `inconclusive_sparse_N` | `unstable_or_no_edge` | `process_incomplete` | `sensor_*` | `method_invalid`

Default expectation after seed: `ATTENTION_ONLY_less_loss_path`.

## 6. Decision path
1. Isolation + multipair dig artifacts  
2. `trial_cycle.py finalize-report` when trial registered  
3. `review-request` → Brad `decide`  
4. Follow-on: `scoped_shadow` (would-block) | `none` | `drop`

## 7. Follow-on policy
| If | Then |
|----|------|
| multipair leak confirmed | shadow would-block logger (LINK-first optional) |
| single-pair only | keep pair note; do not platform-wire |
| sensor fail | fix meter; no score |
| no_edge | drop; no cooldown cron |

## 8. Notify
Decision packet under `docs/testing/decisions/` + inbox when trial closes.
