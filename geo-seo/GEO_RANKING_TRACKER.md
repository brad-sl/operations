# GEO Ranking Tracker — Uncorked Canvas

**Purpose:** Track uncorkedcanvas.com visibility in AI-powered search engines (ChatGPT, Perplexity, Gemini, Claude) using Brave Search API as baseline proxy.

**Location:** `/projects/orchestrator/geo_rankings.json`

## How It Works

### Daily Workflow
1. **Run search queries** via `web_search` tool with Brave Search API
2. **Extract ranking position** for uncorkedcanvas.com
3. **Record result** with timestamp, query, position, top results
4. **Track trends** month-over-month

### Key Metrics
- **Position:** Where uncorkedcanvas ranks in AI-powered search results (1-10, or not ranked)
- **Visibility:** Is the domain showing up at all?
- **Trend:** Improving, declining, or stable?
- **Competitors:** Who ranks above/below (competitive positioning)

### Search Queries to Track
```
Primary queries (GEO focus):
1. "uncorkedcanvas generative engine optimization"
2. "uncorkedcanvas AI search visibility"
3. "generative engine optimization services"
4. "GEO SEO uncorkedcanvas"

Secondary (brand):
5. "uncorkedcanvas"
6. "uncorkedcanvas.com"
```

## Data Schema (geo_rankings.json)

```json
{
  "domain": "uncorkedcanvas.com",
  "trackingStartDate": "2026-03-20",
  "lastUpdated": "2026-03-20T16:54:50Z",
  "rankings": [
    {
      "date": "2026-03-20",
      "time": "09:58:00",
      "query": "uncorkedcanvas generative engine optimization",
      "ranked": true,
      "position": null,
      "topResult": {
        "title": "Generative Engine Optimization: How to Dominate AI Search",
        "url": "https://arxiv.org/abs/2509.08919",
        "domain": "arxiv.org"
      },
      "domainInResults": false,
      "resultsCount": 5,
      "tookMs": 745,
      "notes": "First baseline measurement. Uncorkedcanvas not yet in top 5."
    }
  ],
  "trends": {
    "lastWeek": {
      "avgPosition": null,
      "rankedDays": 0,
      "query": "uncorkedcanvas generative engine optimization"
    },
    "lastMonth": {
      "avgPosition": null,
      "rankedDays": 0
    }
  },
  "competitiveContext": {
    "topCompetitors": [
      {
        "domain": "foundationinc.co",
        "keyword": "generative engine optimization",
        "position": 2
      },
      {
        "domain": "reddit.com",
        "keyword": "generative engine optimization",
        "position": 3
      },
      {
        "domain": "github.com",
        "keyword": "generative engine optimization",
        "position": 4
      }
    ]
  }
}
```

## Automation Path

### Manual (For Now)
```bash
# Run daily search snapshot
openclaw web_search "uncorkedcanvas generative engine optimization"

# Update geo_rankings.json with results
# Track month-over-month in HEARTBEAT digest
```

### Future: Cron Job
```bash
# Daily 9 AM PT
0 9 * * * /home/brad/.openclaw/bin/track-geo-rankings.sh
```

## Interpretation Guide

| Position | Status | Action |
|----------|--------|--------|
| 1-3 | 🟢 Excellent | Maintain; track for drop-offs |
| 4-6 | 🟡 Good | Optimize; see "Next Steps for GEO" |
| 7-10 | 🟠 Visible | Low visibility; needs improvement |
| None | 🔴 Not ranked | Build visibility; coordinate with Creative Agent copy |
| Appearing but no position | ⚪ Uncertain | May be in "cited but not featured" |

## Next Steps for GEO

1. **Week 1:** Establish baseline (done ✅)
2. **Week 2:** Generate GEO audit (via `/geo audit uncorkedcanvas.com`)
3. **Week 3:** Implement recommendations (schema markup, E-E-A-T signals, platform citations)
4. **Week 4:** Re-measure and compare

## Platform Tracking (Future)

Track uncorkedcanvas visibility in these AI search engines:
- ChatGPT (via web search)
- Perplexity Sonar (via web search)
- Google Gemini (via web search)
- Claude Web (via web search)
- DeepSeek (via web search)

**Note:** These require browser automation or platform APIs. For now, Brave Search serves as proxy.

---

**Owner:** Brad Slusher  
**Status:** ✅ Baseline established 2026-03-20  
**Next check:** 2026-03-27 (1 week)
