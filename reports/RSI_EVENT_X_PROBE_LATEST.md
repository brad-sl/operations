# RSI-event X probe

- as_of: `2026-09-18T21:49:14.872123+00:00`
- dry_run: **False** · spend_executed: **False**
- live_gate: **OFF** · place_orders: **false**
- budget: `{"allowed": false, "reason": "empty_pairs", "day": "2026-09-18", "would_add": 0, "remaining_day": 6, "remaining_lane": 2, "blocked_pairs": [], "allowed_pairs": []}`
- fetched: `[]`
- x_scores: `{}`

## Plain English

No RSI-wash+stale doors in top-K (universe=7, trigger=0). Probe idle — no X spend.

## Honesty

- Probe validates sensor clock with real X — not a live buy path.
- place_orders always False; runner buy still needs normal gates + seat.
- Budget is pair-query hard cap (rsi lane ≤2/day default).
- dry_run default — --go required to spend.

