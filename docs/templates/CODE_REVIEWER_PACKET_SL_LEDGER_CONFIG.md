# Code-reviewer packet — SL / ledger / config

Use with Hermes profile **`code-reviewer`** (Kimi / OpenRouter). One-shot, no live orders.

```bash
code-reviewer chat -Q -q "$(cat docs/templates/CODE_REVIEWER_PACKET_SL_LEDGER_CONFIG.md)" -t file,terminal
```

Paste the **diff stat + named files** after the checklist. Workdir = `/home/brad/projects/crypto-trading-bot`.

---

You are an independent reviewer. Do not implement. Output: P0/P1/P2 findings with file:line. If clean, say CLEAN and list what you grepped.

## Checklist (fail closed)

1. **Call site vs signature** — every `get_recent_trades(`, `evaluate_buy_entry(`, `attach_stop_loss(` matches the live function signature (`hours=`, `fresh_buy`, etc.). `inspect.signature` or read def. TypeError swallowed as empty list = P0.
2. **except Exception: return [] / pass** on ledger, SL, cooldown, evaluate paths — must log; silent empty = P0 (72h hole class).
3. **Config ≠ path** — if JSON has `capital_event_stop_loss_exchange_block_rebuy_hours`, `buy_block_pairs`, `rebalance_cap_usd`, `market_fallback_max_usd`, grep **code** in `evaluate_buy_entry` / `runtime_knobs` / ARCH-4 filter. Config-only = theater.
4. **Waivers** — `buy_block_waivers.json` must not use `expires_ts: null` with `scope=all`. Default scope is **post_tp only**; must not wipe post-SL 72h.
5. **Isolation ≠ integration** — helper tests are not enough. Would ARCH-4 / quality_tryout / TradeExecutor still buy? Name the filter function.
6. **Ratchet / existing_stop** — fresh buy must not import a prior bag’s stop. Ghost registry `status=open` after TP/SL.
7. **Dual SSOT** — `global_settings.rebalance_cap_usd` vs `regime_cash_policy` live cap.
8. **No live flatten / no enforce:false** unless the diff explicitly says Brad GO.

## Output schema

```
P0: ...
P1: ...
P2: ...
Verified: [commands/files]
Unverified: ...
```
