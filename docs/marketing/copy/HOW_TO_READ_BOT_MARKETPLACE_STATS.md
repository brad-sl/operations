# How to Read Bot Marketplace Stats

**Audience:** prospects evaluating crypto trading bots (including Coinbase-connected tools)  
**Purpose:** teach pattern-matching so ROI billboards don’t substitute for risk literacy  
**Claims rule:** this article **does not** claim our (or anyone’s) future returns. No invented competitor P&L.  
**Related:** `docs/marketing/CLAIMS_SCREENSHOT_POLICY.md`, `docs/Trading_Bot_FAQ.md`, `docs/marketing/RISK_DISCLOSURES.md`

---

## 1. The billboard you’ll see

A typical marketplace or “strategy showcase” card looks like this:

| Label | Example (illustrative) |
|-------|-------------------------|
| Strategy name | “Trend Following Strategy” |
| Exchange badge | Coinbase |
| **ROI** | 92.4% |
| **PnL** | $5,247 |
| **Win rate** | 100% |
| **Trades closed** | 13 |
| **Max floating drawdown** | −1.51% |
| **Fees** | $51 |

It *sounds* excellent. That is the job of the card. Your job is to ask what the card **doesn’t** say.

---

## 2. Decode each metric

### ROI (or “return”)

| Ask | Why it matters |
|-----|----------------|
| **Over what dates?** | A calm 3-week window ≠ a full cycle. |
| **On what capital?** | 92% on $500 paper and 92% on $50k live are not the same operational story. |
| **Deposit-adjusted?** | Deposits inflate “wallet up” narratives. Serious reporting separates **cash flows** from **trading P&L**. |
| **Gross or net of fees?** | Fees line may exist while ROI is still shown pre-fee. |
| **One bot / one account / one cherry-picked run?** | Marketplaces often highlight **best** public or demo runs, not the median user. |

**Rule of thumb:** If ROI has no **window**, **method**, and **capital base**, treat it as **advertising**, not evidence.

### PnL ($)

Dollar PnL without starting equity is incomplete.  
$5,247 on $5,000 is very different from $5,247 on $200,000.

Also ask: **realized only**, or mark-to-market including open bags?

### Win rate

| Red flag | Why |
|----------|-----|
| **100% win rate** | Extremely rare over meaningful samples; often means **tiny N**, soft definition of “win,” or selection bias. |
| **Win rate with N &lt; 30** | Coin-flip noise. 13 trades proves almost nothing about the next 130. |
| **No definition of win** | Full take-profit only? Partial closes? Ignoring stopped-out legs? |

**Prefer:** profit factor, expectancy, and **full trade list** over win rate alone.

### Trades closed (sample size)

Small **N** is the quiet killer of marketplace credibility.

| Closed trades | How to treat the card |
|---------------|------------------------|
| &lt; 20 | Anecdote |
| 20–100 | Early signal, high variance |
| 100+ across regimes | Starting to be interesting — still need DD and live vs backtest clarity |

### Max floating drawdown

“Floating” often means **peak unrealized** pain **during the showcased window**, not:

- worst historical month,  
- a true bear regime,  
- what happens when correlation goes to 1,  
- or **your** portfolio if you add capital mid-drawdown.

Per-position stop-losses also **do not** cap portfolio drawdown (many names can stop or bleed together). See `docs/Trading_Bot_FAQ.md`.

### Fees

A fees line is good hygiene. It still doesn’t tell you:

- funding / spread / slippage,  
- failed orders,  
- or whether the strategy only “works” in high-fee-tolerant trends.

### Exchange logo (e.g. Coinbase)

Usually means: **this strategy can connect to that exchange** — not:

- Coinbase endorses the bot,  
- your account will match the card,  
- or funds are safer because of the logo alone.

**Safety** is about **custody model**, **how you authorize trading**, and **who holds keys** — not the badge art.

---

## 3. Questions that separate theater from substance

Copy/paste checklist for any bot page:

1. **Is this live money or backtest/demo/paper?**  
2. **Exact start and end dates?**  
3. **Starting equity and net deposits/withdrawals?**  
4. **How many **independent** accounts show similar results?**  
5. **What was the worst day / worst week / worst month?**  
6. **What happens when the API dies, OAuth expires, or billing fails?**  
7. **Can I revoke access without emailing support?**  
8. **Do they show losing strategies as publicly as winners?**  
9. **Are returns deposit-adjusted and methodology-documented?**  
10. **Is the product a fund, a signal group, or software on *my* exchange account?**

If the page can’t answer most of these, the ROI card is doing the heavy lifting for a reason.

---

## 4. Common presentation tricks (not always malicious — still distorting)

| Trick | What you’ll see | Healthier framing |
|-------|-----------------|-------------------|
| **Highlight bias** | Only top strategies on the homepage | Ask for median / distribution |
| **Short window** | Huge % in a bull burst | Demand multi-regime span |
| **Tiny N** | 100% WR on 10–20 trades | Ignore WR until N is large |
| **Unclear capital** | Big $ PnL, no base | Require % **and** base |
| **Deposit confusion** | “Account grew” after you added cash | Deposit-adjusted return |
| **Demo mode glow** | Perfect fills, no emotion, no ops failure | Live track record only |
| **Strategy zoo** | Hundreds of bots; one winner shown | Ask what *default* users get |
| **Copy-trading social proof** | Leaderboard heroes | Survivorship: losers leave |

---

## 5. What *is* worth comparing (process over fireworks)

When ROI cards are untrustworthy, compare **systems**:

| Dimension | Better questions |
|-----------|------------------|
| **Custody** | Do funds stay on *my* exchange? |
| **Authorization** | API keys in a random dashboard vs **OAuth** (scoped, revocable)? |
| **Failure modes** | Pause on billing fail? Status digests? Kill-switch? |
| **Reporting honesty** | N/A when unknown? Deposit-adjusted? Per-position SL ≠ portfolio floor? |
| **Ops** | Who gets paged when the runner is red? |
| **Incentives** | Do they win if *you* lose (deposit-only hype) or if software keeps working? |

A boring, accurate status page beats a 92% billboard you can’t audit.

---

## 6. Worked example (how to read the card above)

Using the illustrative billboard:

| Claim | Skeptical read |
|-------|----------------|
| ROI 92.4% | No window, no method, no capital base → **unverified ad metric**. |
| PnL $5,247 | Meaningless without starting equity and flows. |
| Win rate 100% | With **13** closes → **anecdote**, not edge proof. |
| Max floating DD −1.51% | Showcase-window path; not a promise for the next crash. |
| Fees $51 | Nice detail; still not a full cost or risk picture. |
| Coinbase logo | Connectivity / marketing adjacency — **not** a performance guarantee. |

**Sane conclusion:** “Interesting as a *story*. Useless as a *forecast*. I need live methodology or I walk.”

---

## 7. How we choose to show performance (ARCH Automation)

We aim for the opposite of marketplace billboard culture:

- **Software access** on **your** Coinbase Advanced account — not a pooled fund.  
- Prefer **deposit-adjusted** reporting and explicit **N/A** when data isn’t there.  
- **Per-position** risk controls are **not** marketed as a max portfolio loss.  
- No “100% win rate” hero stats as a substitute for process.  
- Connect path goal: **OAuth-first** (revocable access; keys not pasted into the CRM).  

If we publish numbers, they should survive the checklist in §3. If they don’t, they shouldn’t ship.

---

## 8. One-paragraph LP blurb (optional)

> Bot marketplaces love 90% ROI cards and 100% win rates on a handful of trades. Those numbers almost never include the window, deposits, median user, or full drawdown history. Judge automation by custody, how you authorize trading, failure handling, and honest reporting — not by the loudest screenshot.

---

## Document control

| Version | Date | Notes |
|---------|------|-------|
| 1.0 | 2026-07-17 | Initial education piece for product GTM / FAQ / content calendar |

**Canonical path:** `docs/marketing/copy/HOW_TO_READ_BOT_MARKETPLACE_STATS.md`
