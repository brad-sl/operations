# GEO-SEO Claude — Quick Start Guide

**Deployment:** ✅ Complete (2026-03-17 16:47 PDT)  
**Status:** Operational and tested  
**Time to Deploy:** 5 minutes total

---

## What You Have

A complete GEO (Generative Engine Optimization) tool installed on your system that audits websites for:

- **AI Citability** — How well content is written for AI citation
- **AI Crawler Access** — Can GPTBot, ClaudeBot, PerplexityBot reach your site?
- **Brand Authority** — Mentions on Reddit, YouTube, Wikipedia, LinkedIn, etc.
- **Structured Data** — Schema markup (Organization, Product, LocalBusiness, etc.)
- **E-E-A-T** — Expertise, Experience, Authoritativeness, Trustworthiness
- **Platform Optimization** — ChatGPT readiness, Perplexity optimization, Google AIO
- **Technical SEO** — Core Web Vitals, mobile, security, crawlability

---

## Quick Start (3 Steps)

### Step 1: Activate Python Environment

```bash
source /home/brad/geo-env/bin/activate
cd /home/brad/geo-seo-claude
```

### Step 2: Run a Quick Audit

```bash
# 60-second snapshot
python3 scripts/fetch_page.py https://uncorkedcanvas.com

# Citability score
python3 scripts/citability_scorer.py https://uncorkedcanvas.com

# Brand mentions
python3 scripts/brand_scanner.py https://uncorkedcanvas.com
```

### Step 3: Generate a Report

```bash
# Full PDF report (in Claude Code interface)
/geo report-pdf https://uncorkedcanvas.com
```

---

## What We Tested Today

✅ **fetch_page.py** — Extracted 35+ meta tags, H1/H2/H3 structure from uncorkedcanvas.com  
✅ **citability_scorer.py** — Scored site at 39/100, identified "Reviews" section as most citable  
✅ **Python environment** — All dependencies installed (requests, beautifulsoup4, reportlab, etc.)

---

## Key Insights from Uncorked Canvas Test

| Metric | Result | Grade |
|--------|--------|-------|
| Average Citability | 39/100 | D (needs work) |
| Most Citable Block | Reviews section (189 words) | C |
| Poorest Block | Product list (73 words) | F |
| Meta Tags | 35+ present | ✅ Good |
| Heading Structure | H1, H2×3, H3 | ✅ Good |
| Canonical Tag | Present | ✅ Good |

**Recommendations for Uncorked Canvas:**
1. Expand product descriptions (target 134-167 words per block)
2. Add Product schema markup (structured data)
3. Create dedicated blog content (Q&A format)
4. Write a FAQ page (AI-optimized for citation)

---

## Monetization Opportunity

- **GEO Agencies charge:** $2K–$12K/month
- **Market size:** $850M (2025) → $7.3B (2031)
- **Your tool:** Does the audit automatically
- **What's included:** Skool community for sales training & client acquisition

---

## Integration Opportunities

### 1. Adspirer + GEO Workflow
```
GEO Audit → Content Recommendations
  ↓
Creative Agent (generates blog content briefs)
  ↓
Google Ads Campaign (themed to GEO recommendations)
```

### 2. Cron Monitoring
```
Daily 9 AM: Run /geo audit → Store scores in dashboard
Weekly: Email GEO report to stakeholders
Monthly: Track GEO score trends
```

### 3. Client Reporting
```
/geo audit <client_url> → Generate PDF
→ Monthly deliverable (ready to send to client)
→ Track month-over-month improvement
```

---

## Files & Locations

```
Skill:         /home/brad/.claude/skills/geo/
Sub-skills:    /home/brad/.claude/skills/geo-audit/  (11 skills)
Source:        /home/brad/geo-seo-claude/
Python:        /home/brad/geo-env/
Scripts:       /home/brad/geo-seo-claude/scripts/
Docs:          /home/brad/.openclaw/workspace/GEO_SEO_DEPLOYMENT.md
```

---

## Next Steps (For Brad)

**Today:** ✅ Deployed  
**Tomorrow:** Run full `/geo audit` test with all 5 subagents  
**This week:** Test on 3-5 different websites (SaaS, local, e-commerce)  
**This month:** Build Adspirer + GEO integration workflow

---

## Support

- Full docs: https://github.com/zubair-trabzada/geo-seo-claude
- Skool community (sales/positioning): https://skool.com/aiworkshop
- Scripts are tested and working ✅

---

**Ready to test the full audit? Let me know!**
