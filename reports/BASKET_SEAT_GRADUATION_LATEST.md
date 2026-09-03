# Basket seat graduation funnel

_Generated 2026-09-03T19:30:24.624650+00:00 · window 30d post-promote_

## Plain English

Seats=3 → signaled=3 (1.0) → filled=2 (0.667|sig) → wins=0 (win|seat=0.0; blocked_no_fill=1)

## Rates (optimize these, not vibes)

| Step | Rate | Count |
|------|------|-------|
| Signal \| seat | 1.0 | 3/3 |
| Fill \| signal | 0.667 | 2/3 |
| Win \| closed fill | 0.0 | 0/2 |
| **Win \| seat (full funnel)** | **0.0** | 0/3 |

Prior guestimate ~**0.25** win|seat — replace with `rate_win_given_seat` when N≥12 closed episodes.

## Per pick

| Pick | Add | Stage | Sig | Fill | PnL$ | Block | Age d | Paper 7d% |
|------|-----|-------|-----|------|------|-------|-------|-----------|
| 8b47ff6a-9c6 | RAVE-USD | filled_loss | Y | Y | -15.6977 | 0 | 25.58 | -23.569 |
| 42c73fff-502 | ICP-USD | filled_loss | Y | Y | -15.6852 | 0 | 23.54 | -6.11 |
| 2e9d79a7-cca | PENGU-USD | blocked_no_fill | Y | n | None | 4 | 9.03 | -16.846 |

## Stage meanings

- `seated` — promoted; no buy signal yet
- `signaled` — ROTATE_IN/BUY plan seen; not filled (gates may still run)
- `blocked_no_fill` — signal + run-phase (or similar) drop; no live buy
- `filled_open` — bought; episode not fully realized
- `filled_win` / `filled_loss` — sells booked with net pnl
- `stale_no_signal` — past window, never signaled

## Honesty

Guestimate prior ~0.25 win|seat is a planning bar only. rate_win_given_seat needs closed fills; n small ⇒ noise.

Paper MTM (marks) ≠ trade success. Optimize **fill|signal** vs **win|fill** separately.

