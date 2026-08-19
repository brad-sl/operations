# Unlisted Funnel Skeleton — ARCH Automation (Phase A)

**Kanban:** t_5e21287a  
**Rule:** Unlisted / invite-only. **Do not** publish to public domain nav or run ads.  
**GHL Location:** ARCH Automation — Pilot  
**Domain (pending):** arch-automation.com (pages may live on GHL subdomain until DNS)

Agent hosts typically **cannot** create live GHL pages without Brad admin login. This MD + JSON is the build spec; ops pastes copy from `docs/marketing/copy/`.

---

## Funnel graph

```
[Invite / Waitlist landing] optional
        ↓
[Landing — value prop]  (pages/landing.md)
        ↓
[Pricing]               (pages/pricing.md)
        ↓
[Checkout + legal ack]  (pages/checkout.md)
        ↓  payment success
[Thank you → Connect]   (member Connect)
        ↓  OAuth
[Member Status]         (placeholder)
        ↓
Lifecycle email/SMS W1–W7 (sequences/*)

Legal side doors (linked, unlisted):
  Risk · Terms · Privacy · FAQ
```

---

## GHL sites / funnels to create (names)

| # | Name | Type | Indexed? | Source copy |
|---|------|------|----------|-------------|
| 1 | ARCH Pilot — Landing | Funnel step / page | no | `pages/landing.md` |
| 2 | ARCH Pilot — Pricing | Funnel step | no | `pages/pricing.md` |
| 3 | ARCH Pilot — Checkout | SaaS checkout | no | `pages/checkout.md` |
| 4 | ARCH Pilot — Thank You / Connect | Funnel step | no | checkout thank-you + member connect |
| 5 | ARCH Pilot — Risk | Website page | no | `pages/risk_disclosure_page.md` + full RISK doc |
| 6 | ARCH Pilot — Terms | Website page | no | ToS canonical |
| 7 | ARCH Pilot — Privacy | Website page | no | Privacy canonical |
| 8 | ARCH Pilot — FAQ | Website page | no | `pages/faq.md` |
| 9 | Member: Connect | Custom menu / membership | no | `pages/member_area_placeholder.md` |
| 10 | Member: Status | Custom menu / iframe later | no | member placeholder |

**Access control options (pick one for pilot):**
- Shareable funnel URL with long random slug (not linked publicly)
- Password step before landing
- Invite-only contacts + manual checkout link
- `noindex` meta on all steps

---

## SaaS products on checkout

| Product | SKU | Price | Visibility |
|---------|-----|-------|------------|
| ARCH Starter | arch_starter_mo | $39 | Invite checkout |
| ARCH Pro | arch_pro_mo | $99 | Optional unlisted |
| ARCH Elite | arch_elite_mo | $249 | Optional unlisted / request |

Product short descriptions: see `GHL_T0_FIELD_DICT.md` §4.

---

## Post-purchase path (critical KPI)

1. Payment success webhook / SaaS event → tag `paid`, set `trader_tier`, `subscription_status=active`  
2. Fire **W1** immediately with `{{connect_link}}`  
3. Stamp `paid_at` and later `connect_link_sent_at`  
4. On OAuth success platform → tag `coinbase_connected`, set `coinbase_status=connected`  
5. On green health → tag `runner_healthy`, fire **W3**  
6. Instrument **pay_at → connected_at** median (target T1: < 15 min human time)

---

## Workflows to wire (see ghl_workflows_skeleton.json)

| ID | Name | Priority Phase A |
|----|------|------------------|
| W1 | Onboarding paid | **Build** |
| W2 | Connect 24h/72h | **Build** |
| W3 | Go live | **Build** |
| W4 | Digests | Stub OK until platform events |
| W5 | Dunning | **Build** (GHL native + copy) |
| W6 | Needs attention | Stub + manual tag OK |
| W7 | Offboard | **Build** on cancel |

Do not enable workflows against production runner webhooks until host/OAuth cards ready.

---

## Tracking (unlisted still)

- UTM on invite links per `metrics/UTM_KPI_TEMPLATE.md`  
- GHL attribution fields if available  
- Manual sheet for invite cohort until ads live  

---

## Pre-go checklist (invite list testing)

- [ ] All pages noindex / unlisted  
- [ ] Checkout checkbox + disclaimer above button  
- [ ] Legal pages linked and version-dated  
- [ ] W1 sends on test purchase  
- [ ] Connect link opens (staging JWT OK)  
- [ ] No perf claims in any step (PRE_PUBLISH_APPLIED.md)  
- [ ] Support email reachable  
- [ ] Refund / cancel path documented  

---

## Out of scope this card

- Live GHL UI build by agent without credentials  
- Public DNS cutover  
- Paid media  
- Real customer data in screenshots  
