# Hard-exit operator decision loop (TG-02)

**Status:** live — shadow + notify; **no auto-sell**  
**Config:** `config/regime_cash_policy.json` → `hard_exit`  
**CLI:** `PYTHONPATH=. python3 -m phase6.scripts.hard_exit_controls`

## You stay in the loop (exception mode)

Brad chose this while proving hard exits. **Product end-state:** thresholds are knobs; bot exits without chat. Leave the loop with **one** settings change (`operator_approve: false` + `live_apply: true`) after FP review — not endless per-trade OKs.

See also: `docs/EXIT_AUTOMATION.md` (few knobs, automated platform).

| Step | What happens |
|------|----------------|
| 1 | Runner / rebalance scans hard exits (RSI overbought **or** weak sentiment). **Never** `park_prefer_reduce`. |
| 2 | Writes `data/state/regime_hard_exit_shadow.json` |
| 3 | Upserts **pending** inbox `data/state/hard_exit_pending.json` |
| 4 | **Telegram** alert (deduped every `notify_dedupe_hours`, default 12h) with pair / $ / reasons / id |
| 5 | **You** `list` → `approve --id` or `reject --id` / `reject --all` |
| 6 | Approve **stages only** → `data/state/hard_exit_approved_execute.json` — **does not place orders** |
| 7 | Sell = your manual trade or a future explicit execute path |

`operator_approve: true` **forces** `live_apply` off in code.

## Commands

```bash
cd /home/brad/projects/crypto-trading-bot
PYTHONPATH=. python3 -m phase6.scripts.hard_exit_controls list
PYTHONPATH=. python3 -m phase6.scripts.hard_exit_controls approve --id he-...
PYTHONPATH=. python3 -m phase6.scripts.hard_exit_controls reject --id he-...
PYTHONPATH=. python3 -m phase6.scripts.hard_exit_controls reject --all
PYTHONPATH=. python3 -m phase6.scripts.hard_exit_controls notify-test   # wiring check
```

## What “later” means for TG-02 (decision triggers)

**Not a calendar auto-promote.** Bring a live_apply / execute decision to Brad when **any** of these fire:

| Trigger | Meaning |
|---------|---------|
| **T0 — every proposal** | Telegram pending → you approve/reject **that leg** (always on) |
| **T1 — promote automation?** | After **≥7 calendar days** of shadow **or** **≥5** hard-exit notifications with your decisions logged, review false-positive rate |
| **T2 — evidence** | TG-04 path study supports profit-side exits **and** hard-exit false positives acceptable |
| **T3 — explicit OK** | You say “enable live hard exit” / set `operator_approve:false` + `live_apply:true` (not recommended while you want the loop) |

Default while you want the loop: keep **`operator_approve: true`** forever for hard exits; “later” = each Telegram, not a thaw date.

## Files

- Pending: `data/state/hard_exit_pending.json`
- Decisions audit: `data/state/hard_exit_decisions.jsonl`
- Notify dedupe: `data/state/hard_exit_notify_dedupe.json`
- Staged approves: `data/state/hard_exit_approved_execute.json`
