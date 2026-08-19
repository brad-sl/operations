# External FAQ — Trading Clients

**Audience:** onboarded traders and product/help surfaces.  
**Not for:** pipeline internals, vendors, cron schedules, API costs, or implementation detail.  
**Staff / ops:** [`Internal_Trading_Platform_FAQ.md`](Internal_Trading_Platform_FAQ.md)

---

## Performance & risk

### Why can my 7-day return be worse than the stop-loss percentage?

Stop-losses apply **per position** from that position’s entry. They are **not** a guarantee that the whole portfolio can only lose that percentage over a week.

Your **7-day return** reflects the full account (cash, open positions, and closed trades). It can move more than a single position’s stop because several positions can lose at once, prices can gap, and open holdings still mark to market.

### What is Exit win rate?

Of recent **closed** trades that realized a profit or loss, the share that were profitable. It is **not** the same as your account’s 1-day or 7-day return.

### What is Utilization?

The share of your account currently in crypto holdings versus held as cash. Higher utilization means more of the account is invested; it does not by itself mean higher or lower risk.

### Why might longer history (e.g. 30-day) show as unavailable?

There may not yet be enough account history to calculate that window reliably. We show unavailable rather than an invented zero.

### What does stop-loss coverage mean?

It indicates whether open positions have protective stop orders in place. It is **not** a maximum loss limit on the whole portfolio.

---

## Reading marketplace / competitor bot stats

### Why do some bots advertise very high returns or win rates?

Those figures are often **marketing highlights**, not a prediction of what you will earn. Short sample periods, small numbers of trades, and unclear starting capital are common. Treat them as illustrations, not guarantees.

For a fuller plain-language guide: ask support for the marketplace stats explainer, or see the product education article used by our team (`HOW_TO_READ_BOT_MARKETPLACE_STATS` in internal docs — staff can share a client-safe extract).

---

## After a large sell

### If the platform sells a position, does it always buy something else right away?

**Not always.** After a large sell, the account may **hold cash** for a period while risk controls and market filters apply. A “buy” label on a market snapshot is **context**, not a promise that cash will move into that pair immediately.

When a controlled redeploy is used, it is a **limited portion** of proceeds under product rules — not an automatic full swap into the strongest-looking name. That design exists because rapid full redeploys can add fees and repeat losses when markets are choppy.

### Why might cash sit after a sale?

- Protective cooldowns (for example, not immediately rebuying the same asset)  
- Regime and entry filters (only deploy when rules say the setup is acceptable)  
- Preference for **smaller, gated** risk after a big exit until the book is stable  

Exact knobs depend on your account settings; support can explain your mode without pipeline detail.

---

## How the platform uses market context

### Does the platform use social media or news?

The platform uses **automated market context** (including public market and social signals where configured) as one input among others when rebalancing on its schedule. You do not need to manage those sources. Exact vendors and mix can change as we improve reliability; your experience is the product settings and risk controls you choose, not a DIY data pipeline.

---

*Last updated: 2026-08-16 — after large sell / cash hold expectations*
