# Ad Management Rulebook

**Last Updated:** 2026-03-25 21:32 UTC  
**Scope:** All ad platforms (Google Ads, Meta, LinkedIn, TikTok)  
**Owner:** Brad Slusher  
**Status:** ACTIVE

---

## Core Principles

### Financial Authority
- ✅ **Can act:** Modify existing campaigns, ads, ad groups, keywords, bids, pause/resume (spend reduction)
- ❌ **Cannot act:** Increase budgets, activate paused campaigns, resume stopped ads
- **Approval needed:** Any action resulting in budgetary increase
- **Status updates:** Communicate all changes via regular briefings

### Performance Optimization
- Own the outcomes — optimize within constraints
- Test rigorously before wholesale adoption
- Use A/B testing for ad content, types, and targeting variations
- Follow platform-specific best practices for each phase

### Quality Assurance
1. **Verify conversion tracking** before testing — wrong metrics = wrong decisions
2. **Allow stabilization period** after campaign launch before major changes
3. **Platform-specific timing:**
   - Google Ads: 48-72 hours learning phase (MAXIMIZE_CONVERSIONS needs data)
   - Meta: 3-5 days AEO (Advantage+ optimization) learning phase
   - LinkedIn: 1-2 weeks for audience learning
   - TikTok: 2-3 weeks for algorithm stabilization

---

## Campaign Phases & Best Practices

### Phase 1: Launch (Day 0-3)
**Goal:** Collect initial data, verify tracking, establish baseline

**Actions:**
- ✅ Monitor impressions, CTR, early conversions
- ✅ Verify conversion tracking fires correctly
- ❌ DO NOT make major keyword/targeting changes
- ❌ DO NOT pause underperforming ad groups yet (too early)

**Success criteria:**
- CTR >0.5% (indicates ad relevance)
- Conversion tracking confirmed firing
- Quality Score visible (Google Ads)

**Next phase trigger:** Conversion data arriving

---

### Phase 2: Stabilization (Day 3-14)
**Goal:** Stabilize platform AI, identify clear winners/losers

**Actions:**
- ✅ Analyze search terms → add negatives (stop wasted spend)
- ✅ Pause ads with <1% CTR
- ✅ Test headline/description variations (A/B testing)
- ✅ Monitor CPA/conversion trends
- ❌ DO NOT cut budget dramatically (algorithm still learning)

**Success criteria:**
- Consistent conversion data (3+ per day minimum)
- Clear CTR patterns per ad group
- Quality Score 7+ (Google Ads)
- CPA stabilizing (not volatile week-to-week)

**Next phase trigger:** CPA stabilized, clear winners identified

---

### Phase 3: Optimization (Week 2-4)
**Goal:** Maximize ROAS, identify scaling opportunities

**Actions:**
- ✅ Pause underperforming keywords (low CTR + high CPC)
- ✅ Add high-performing keywords to other ad groups
- ✅ Increase bid on winners by 10-15%
- ✅ Test new ad variations
- ✅ **SUGGEST budget increases** (with data backing)

**Success criteria:**
- ROAS >1.5x
- CPA 30-50% lower than Phase 1
- CTR >2% on top ad groups
- Consistent daily conversions (trend line positive)

**Next phase trigger:** ROAS >2x OR plateau reached

---

### Phase 4: Scaling (Week 4+)
**Goal:** Scale winners, maintain ROAS

**Actions:**
- ✅ Increase budget 20-30% on top performers
- ✅ Pause losers (ROAS <1x)
- ✅ Add new keywords based on winner patterns
- ✅ Test creative refresh (if fatigue detected)
- ✅ Monitor for diminishing returns

**Success criteria:**
- ROAS sustained >2x during budget increases
- Cost per acquisition stable or improving
- No quality score degradation

**Next phase trigger:** New product launch OR market saturation

---

## Platform-Specific Rules

### Google Ads

**Campaign Types:**
- **Search:** High-intent keywords, immediate conversion focus
- **PMax:** All-placements automation, image/video required
- **Display:** Remarketing, brand awareness, long conversion window

**Key Rules:**
1. **Keyword matching:** Start with BROAD, convert high-performers to EXACT after 50+ conversions
2. **Quality Score targets:** ≥7 for all keywords (impacts CPC)
3. **Bid strategy progression:**
   - Phase 1-2: Manual CPC (you set bids)
   - Phase 3: MAXIMIZE_CONVERSIONS (platform optimizes)
   - Phase 4: Target CPA (after 50+ conversions)
4. **Negative keywords:** Add aggressively (cost >$5 per click with 0 conversions = block)
5. **Extensions mandatory:** Sitelinks + Callouts on all campaigns (+15% CTR)
6. **Testing window:** Minimum 14 days per variation before pausing

**Red Flags:**
- ❌ Quality Score <5 (keyword/copy mismatch)
- ❌ CTR <0.5% after 100 impressions (irrelevant traffic)
- ❌ CPA >3x target (targeting or landing page issue)

---

### Meta Ads

**Campaign Types:**
- **Conversions:** Direct sales/signups
- **Traffic:** Landing page visits (top of funnel)
- **Engagement:** Awareness, brand recall

**Key Rules:**
1. **AEO (Advantage+ Budgeting):** Use for all campaigns (Meta's AI optimizes across placements)
2. **Stabilization window:** 3-5 days required before pausing (algorithm still learning)
3. **Creative rotation:** Test 3-5 creatives per ad set, pause if <1% CTR after 48h
4. **Audience stacking:** Start with Lookalike (1% similarity), expand to 2% if scaling
5. **Budget test protocol:** Increase 20% every 3 days IF ROAS >2x
6. **Fatigue detection:** Track frequency capping (creatives die >2% frequency)

**Red Flags:**
- ❌ Frequency >3 (ad fatigue, pause and rotate)
- ❌ CPA trending upward week-over-week (audience saturation)
- ❌ CTR <0.5% after 1K impressions (wrong audience or bad creative)

---

### LinkedIn Ads

**Campaign Types:**
- **Awareness:** Brand reach, awareness
- **Lead Gen:** Lead magnets, webinars
- **Engagement:** Content engagement, follower growth

**Key Rules:**
1. **Audience learning:** 1-2 weeks minimum before optimizing (B2B decisions slower)
2. **Budget floor:** $20/day minimum (smaller budgets don't accumulate data)
3. **CPA expectations:** Higher than Google/Meta (B2B premium)
4. **Targeting precision:** Job title + industry + company size (narrow first, expand if needed)
5. **Testing window:** 3 weeks minimum per creative
6. **Lead quality over volume:** Monitor lead-to-opportunity conversion (not just lead count)

**Red Flags:**
- ❌ Leads but low quality (track SQLs, not just form fills)
- ❌ CPC >$15 without conversions (expand targeting)
- ❌ No impressions after 5 days (targeting too narrow)

---

### TikTok Ads

**Campaign Types:**
- **Traffic:** App installs, website visits
- **Conversions:** In-app or web conversions
- **Engagement:** Video views, profile visits

**Key Rules:**
1. **Algorithm stabilization:** 2-3 weeks required (young algorithm, needs data)
2. **Minimum daily budget:** $20-30 (underfunded campaigns won't scale)
3. **Creative refresh:** Change every 2 weeks (Gen Z sees repetition as boring)
4. **User-generated content (UGC):** Outperforms polished content 3-5x (prioritize)
5. **Placement:** Auto-placement (TikTok decides best placements)
6. **Budget scaling:** 50% increase every week IF performing (TikTok rewards aggressive scaling)

**Red Flags:**
- ❌ No impressions after week 1 (try UGC creative, not brand videos)
- ❌ CTR <0.5% (Gen Z finds it inauthentic, swap to UGC)
- ❌ CPA >$20 without conversions (audience too broad or creative bad fit)

---

## A/B Testing Protocol

### Element Selection
**Priority order for testing (run one at a time):**
1. Ad copy (headlines, descriptions)
2. Visual creative (image, video, colors)
3. CTA (button text, offer)
4. Audience (new segment, demographic)
5. Placement (platform/location optimization)

### Test Structure
- **Test duration:** Minimum 14 days (30 days for Meta/TikTok)
- **Sample size:** Minimum 50 conversions per variant before declaring winner
- **Traffic split:** 50/50 between control and variant
- **Success threshold:** Winner must beat control by ≥20% (statistical significance)

### Execution Rules
- ✅ Test only ONE element per experiment
- ✅ Keep all other variables constant
- ✅ Document hypothesis, results, winner in MEMORY.md
- ❌ Do NOT scale losers
- ❌ Do NOT kill winner before reaching sample size

---

## Conversion Tracking Verification

**Before launching any campaign:**

1. ✅ Test conversion pixel fires (manually visit landing page, check GA)
2. ✅ Verify conversion value captured (check order/form data)
3. ✅ Confirm tracking in ad platform dashboard (Google Ads/Meta)
4. ✅ Test with small daily budget ($5-10) for 24h before scaling

**If conversions = 0 after week 1:**
- Check tracking (likely missing, not campaign fault)
- Verify landing page loads correctly
- Test pixel manually
- Do NOT pause campaign — fix tracking first

**If conversions exist but low quality:**
- Track conversion type (lead vs sale vs signup)
- Measure post-conversion behavior (customer LTV, lead-to-SQL rate)
- Optimize for quality outcome (CPA ÷ LTV)

---

## Status Update Format (Regular Briefings)

**Include in every update:**
- Campaign name | Status | Spend | Conversions | CPA | ROAS
- Top performer this period | Key wins
- Underperformers | Paused keywords/ads
- Tests running | Expected results date
- Upcoming optimizations (if any)

---

## Budget Allocation Rules

**Within fixed monthly budget:**
1. **Winner scaling:** +20-30% every 3-5 days if ROAS >2x
2. **Loser pausing:** Pause ROAS <1x without hesitation
3. **Testing reserve:** Keep 10% budget for A/B tests
4. **Mid-campaign adjustments:** Only if clear performance trend
5. **Budget requests:** Always backed by data (ROAS, CPA trend, growth potential)

**Example:** $5K/month budget
- $4.5K to live campaigns (scale winners, pause losers)
- $500 to A/B tests (controlled learning)

---

## Landing Page Performance Link

**If CTR high but conversions low:**

**Investigation sequence:**
1. Check GA bounce rate (should be <40% for ad traffic)
2. Check form abandonment rate (last form field losing 80%?)
3. Check page load time (<2 seconds = good)
4. Check mobile responsiveness (Google Ads = 60% mobile)
5. Verify CTA button is visible above fold

**Suggestions I'll provide:**
- Reduce form fields (remove non-essential ones)
- Simplify headline (must match ad promise)
- Speed up page load (compress images, lazy load)
- Mobile-optimize (font size, button size, spacing)
- A/B test offers (free trial vs discount vs demo)

---

## Escalation Path

**I will ASK for approval when:**
- Recommending budget increase (with ROAS/CPA data)
- Pausing entire campaign (vs ad group or keyword)
- Recommending major creative overhaul
- Suggesting targeting pivot (new audience segment)

**I will ACT (then inform you) when:**
- Adding negative keywords (stops wasted spend)
- Pausing individual underperforming ads (<0.5% CTR)
- Testing new ad copy variations (A/B controlled)
- Adjusting bids within existing campaign (10-15% changes)
- Updating extensions (sitelinks, callouts)

---

## Lessons Learned & Continuous Improvement

### From Uncorked Canvas (Painted 2026-03-25)

**What Worked:**
- Specific keywords (paint & sip, online classes) > generic keywords
- Extensions (sitelinks + callouts) → +15% CTR expected
- Ad group segmentation by customer type (events vs classes vs DIY kits)

**What Didn't:**
- Generic keywords (painting, classes) attracted junk traffic
- No negative keywords → "my favorite things com" wasted $10.82
- No extensions initially → CTR lagged

**Lesson:** Specificity beats volume. Better to have 5 high-intent keywords than 50 generic ones.

---

## Last Updated
**Date:** 2026-03-25 21:32 UTC  
**Updates:** Initial rulebook created based on Uncorked Canvas optimization work  
**Next review:** After 2 weeks of campaign performance data

---

## Questions or Clarifications?
Ask Brad. This rulebook is a living document and will evolve based on results.
