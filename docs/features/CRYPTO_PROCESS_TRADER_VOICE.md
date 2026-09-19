# How we manage your crypto (trader voice)

| Field | Value |
|-------|--------|
| **ID** | `FEAT-CRYPTO-PROCESS-TRADER-VOICE-2026-09` |
| **Status** | `DRAFT` · product copy source |
| **Audience** | Traders / clients (plain English) |
| **Parent** | [`CRYPTO_PROCESS_LIFECYCLE.md`](./CRYPTO_PROCESS_LIFECYCLE.md) |
| **Updated** | 2026-09-19 |
| **Not for** | Live knobs, engineering SSOT, or performance guarantees |

---

## In one sentence

We connect to your Coinbase account, put **rules and stop-losses** around risk, and run a **repeatable process** for when to try a name, when to protect it, when to take profit, and when to step back to cash — instead of chasing every headline.

---

## Two ways to start

### Fresh start (cash-first) — our preferred path

You fund with **cash / USDC** (or we treat the book as cash-dominant).  
We **build the book from scratch** under small, controlled sizes.

**Why we prefer it:** cleaner history, every position starts with our stop and process tags, fewer “mystery bags” from the past. Lab comparisons favored this path over messy inherited books — that is **research direction**, not a promise of future returns.

**What you should expect early on:** small tryout sizes, empty days when gates say “no,” and more learning than fireworks.

### Takeover (you already hold crypto)

You already have **coins on Coinbase**.  
We **do not force-sell everything on day one**. We take the wheel carefully:

1. See what you hold  
2. Put **protections** on what stays  
3. Sort names into keep / review / not-in-process  
4. Only **add new risk** under the same rules as Fresh  
5. Slowly **normalize** toward a process book (with your OK on big moves)

**Honest tradeoff:** Takeover is more work and usually messier than Fresh. Stabilizing first is the product; matching a clean Fresh backtest on day one is not.

---

## What happens after you’re on

### We watch doors, not vibes

A name has to clear **several checks** before new money goes in — eligibility, market wash, real sentiment when we decide, seat limits, and risk caps.  
If the door is closed, we wait. That is the system working.

### We open small when we open

New names often start as **tryouts** (small tickets), not full bets.  
The goal is to **prove the path** (entry → protect → exit) before sizing up.

### We care for open positions

- **Stops** to limit damage  
- **Take-profit / trail** rules to bank progress when price cooperates  
- **No naked bags** — unprotected size is a bug, not a style  
- After a stop-out, we often **cool off** before buying the same name again  

### We can grow winners — carefully

Adding to a position that is already working is a **separate decision** from buying something new.  
It is not automatic “double down.” On the operator path it may need an explicit approval step.

### We change the roster slowly

Adding or removing **which names are allowed** is deliberate.  
We do not silently rotate your whole book because a paper model had a good week.

### We learn in public (to you)

You should see plain status: what we tried, what blocked a buy, what exited, and whether that was stop tax or banked progress.  
We would rather show **process tax** clearly than hide it behind “the AI is working.”

### You can always step toward cash

Park idle cash, preserve a ballast name (when enabled), or wind down trading risk.  
**Cash / park is a valid state**, not failure.

---

## What we will not do

- Promise returns or “set and forget riches”  
- Auto-promote paper experiments into full size without a clear decision  
- Dump your whole Takeover book without asking (unless you choose full wind-down)  
- Treat every social post as a buy signal  
- Pretend Takeover starts with the same edge profile as Fresh  

---

## Simple picture

```text
START
  Fresh: cash → we allocate under rules
  Takeover: your coins → protect → sort → normalize

MANAGE
  Check doors → small opens → protect & trail
  Grow only on purpose · change roster slowly · keep learning

STOP OR PAUSE
  Flatten trading risk · move to cash / park · keep what you want held outside process
```

---

## Questions we expect

**“Why didn’t it buy today?”**  
Gates closed (sentiment, wash, seats, cooloff, risk armor, etc.). Status should say which.

**“Why so small?”**  
Tryout / trust path. Size is earned, not assumed.

**“Can you just trade what I already own harder?”**  
We can manage and protect it. Aggressively scaling inherited bags without a clean process history is how trust dies.

**“Is Fresh better?”**  
For **process control and historical init comparisons**, yes we steer people there when they can choose. Your situation may still need Takeover — we’ll say so plainly.

---

## Related (operators)

- Full lifecycle + coverage: [`CRYPTO_PROCESS_LIFECYCLE.md`](./CRYPTO_PROCESS_LIFECYCLE.md)  
- Takeover normalize steps: [`TAKEOVER_NORMALIZE_PLAYBOOK.md`](./TAKEOVER_NORMALIZE_PLAYBOOK.md)  
- Capital events (deposit / manual sell): [`../CAPITAL_AND_PORTFOLIO_EVENTS.md`](../CAPITAL_AND_PORTFOLIO_EVENTS.md)  
- Glossary / happy path: [`../faq/Internal_Trading_Platform_FAQ.md`](../faq/Internal_Trading_Platform_FAQ.md)  
