# UTM + KPI Template — ARCH Automation Phase A

**Purpose:** Instrument invite/unlisted funnel before paid media.  
**Sheet:** Copy this markdown into Google Sheets tabs or keep as MD log.  
**Date:** 2026-07-30

---

## 1. UTM conventions

Base (when domain live): `https://arch-automation.com/...`  
Pilot: GHL funnel host + path.

| Param | Allowed values (pilot) | Example |
|-------|------------------------|---------|
| `utm_source` | `invite`, `founder`, `manual`, `email`, `sms`, `linkedin`, `x`, `google` | `invite` |
| `utm_medium` | `dm`, `email`, `cpc`, `organic`, `referral`, `qr` | `dm` |
| `utm_campaign` | `pilot_t0`, `pilot_t1`, `waitlist`, `w2_connect` | `pilot_t0` |
| `utm_content` | creative or messenger slug | `brad_dm_01` |
| `utm_term` | optional keyword (ads later) | — |

**Rules**
- Lowercase, snake_case, no PII in UTMs  
- One primary CTA link per message carrying full UTM  
- Internal lifecycle emails may omit UTM or use `utm_source=lifecycle&utm_medium=email&utm_campaign=w1_welcome`

**Example invite link**
```
https://{GHL_FUNNEL_HOST}/arch-pilot-landing?utm_source=invite&utm_medium=dm&utm_campaign=pilot_t0&utm_content=cohort_a
```

---

## 2. Event definitions

| Event | Definition | Owner system |
|-------|------------|--------------|
| `landing_view` | Unique page view landing | GHL / analytics |
| `pricing_view` | Pricing step view | GHL |
| `checkout_start` | Checkout loaded | GHL |
| `checkout_complete` / `paid_at` | Payment success timestamp | GHL SaaS |
| `w1_sent_at` | Welcome email sent | GHL |
| `connect_link_click` | Click connect CTA | GHL + platform |
| `oauth_start` | User hits Coinbase authorize | Platform |
| `connected_at` | `coinbase_status=connected` | Platform → GHL |
| `live_green_at` | `runner_health=green` first time | Platform |
| `past_due_at` | Payment failed | GHL |
| `canceled_at` | Sub canceled | GHL |

---

## 3. Core KPIs (Phase A / T1)

| KPI | Formula | Pilot target |
|-----|---------|--------------|
| Invite → Landing CTR | clicks / invites sent | Log only |
| Landing → Pricing | pricing_view / landing_view | Log only |
| Pricing → Checkout start | checkout_start / pricing_view | Log only |
| Checkout conversion | paid / checkout_start | Log only |
| **Pay → Connect median (human min)** | median(connected_at − paid_at) | **T1 < 15 min**; stretch T3 < 5 min |
| Pay → Connect P90 | p90(connected_at − paid_at) | Log |
| Connect rate 24h | connected within 24h / paid | Maximize |
| Connect rate 72h | connected within 72h / paid | Maximize |
| W2 needed rate | received W2a / paid | Lower is better |
| Go-live rate | live_green / paid | T1 gate related |
| W1 open rate | opens / delivered | Log |
| Dunning recover rate | recovered / past_due | Log |
| Compliance incidents | count critical claim violations | **0** |

---

## 4. Cohort log table (sheet tab: `cohort_log`)

| invite_id | email_hash_or_contact_id | utm_source | utm_medium | utm_campaign | utm_content | invited_at | paid_at | connected_at | live_green_at | pay_to_connect_min | tier | notes |
|-----------|--------------------------|------------|------------|--------------|-------------|------------|---------|--------------|---------------|--------------------|------|-------|
| | | | | | | | | | | | | |

Use contact id from GHL; avoid storing full email in shared marketing sheets if possible (hash or GHL id).

---

## 5. Weekly scorecard (sheet tab: `weekly_kpi`)

| week_start | invites | paid | connected | median_pay_connect_min | p90_pay_connect_min | go_live | past_due | cancels | compliance_flags | notes |
|------------|---------|------|-----------|------------------------|---------------------|---------|----------|---------|------------------|-------|
| | | | | | | | | | | |

---

## 6. Instrumentation checklist

- [ ] GHL checkout success writes `paid_at` (or reliable proxy)  
- [ ] Platform writes `connected_at` to GHL custom field or tag time  
- [ ] Spreadsheet or BI joins paid_at + connected_at  
- [ ] W1–W3 workflows use templates from `sequences/`  
- [ ] UTM preserved through funnel (GHL attribution)  
- [ ] No performance ROI fields in marketing dashboards presented as guarantees  

---

## 7. When ads go live (later — not Phase A)

Add: CAC proxy = spend / paid; CPC; CTR; quality negatives list from MKT plan §4.3.  
Still **$0 spend** until legal + tracking + product ad account ready.
