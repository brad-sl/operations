# Adspirer Logging & Reporting System

Automated system for capturing all Adspirer tool outputs, maintaining campaign documents, and generating client reports.

---

## How It Works

### 1. Automatic Logging

Every Adspirer tool call is logged automatically to:
```
campaigns/[client]/[campaign-name]-logs/[YYYY-MM-DD]_[tool-name].md
```

**Logged data includes:**
- Timestamp
- Tool name & parameters
- Full API response
- User approvals/decisions
- Any errors

### 2. Campaign Document Updates

Campaign master document updated after each major step:
```
campaigns/[client]/[campaign-name].md
```

**Sections updated:**
- Keyword Research
- Ad Assets
- Campaign Configuration
- Performance metrics
- Revision history

### 3. Report Generation

On-demand or scheduled reports written to:
```
reports/[type]/[client]_[date]_[type].md
```

**Report types:**
- `performance_report.md` — Campaign metrics & analysis
- `keyword_analysis.md` — Keyword performance breakdown
- `wasted_spend_analysis.md` — Budget optimization findings

### 4. Git Commit & Version Control

After each major action:
```bash
git add campaigns/
git add reports/
git commit -m "adspirer: [client] [action] - [brief description]"
```

**Commit messages follow pattern:**
```
adspirer: [client] [action] - [details]

Examples:
- adspirer: uncorked-canvas keyword-research - kits campaign keywords finalized
- adspirer: uncorked-canvas campaign-creation - kits and events campaigns created (paused)
- adspirer: uncorked-canvas performance-update - 7-day metrics captured
```

---

## Logging Workflow

### Step 1: Tool Execution
```
User requests: "Research keywords for Uncorked Canvas kits campaign"
↓
I call: research_keywords(business="art kits", location="US")
↓
API returns: Full keyword results
```

### Step 2: Auto-Log Creation
```
File created: campaigns/uncorked-canvas/kits-campaign-logs/2026-03-09_research_keywords.md

Contents:
- Timestamp: 2026-03-09 14:30:00
- Tool: research_keywords
- Parameters: { business: "art kits", location: "US" }
- Results: [Full table of keywords, search volume, CPC, competition]
- Status: Complete
- User Decision: Awaiting approval
```

### Step 3: Campaign Document Update
```
File: campaigns/uncorked-canvas/kits-campaign.md

Updated sections:
- Keyword Research (populated with results)
- Revision History (added entry)
```

### Step 4: Git Commit
```bash
git add campaigns/uncorked-canvas/
git commit -m "adspirer: uncorked-canvas keyword-research - kits campaign high/medium/low intent keywords"
```

### Step 5: Client Report (if requested)
```
File: reports/keyword-research/uncorked-canvas_2026-03-09_keyword_research.md

Contains:
- Executive summary
- Keyword tables by intent
- CPC analysis
- Competitive landscape
- Recommendations
```

---

## Directory Structure

```
/home/brad/.openclaw/workspace/
├── CAMPAIGNS_INDEX.md                    # Navigation hub
├── ADSPIRER_LOGGING_SYSTEM.md           # This file
├── campaigns/
│   ├── uncorked-canvas/
│   │   ├── kits-campaign.md             # Master campaign doc
│   │   ├── events-campaign.md           # Master campaign doc
│   │   ├── kits-campaign-logs/
│   │   │   ├── 2026-03-09_research_keywords.md
│   │   │   ├── 2026-03-09_discover_existing_assets.md
│   │   │   ├── 2026-03-09_suggest_ad_content.md
│   │   │   └── 2026-03-10_performance_check.md
│   │   └── events-campaign-logs/
│   │       └── ...
│   └── [other-client]/
├── reports/
│   ├── keyword-research/
│   │   ├── uncorked-canvas_2026-03-09_keyword_research.md
│   │   └── ...
│   ├── performance-analysis/
│   │   ├── uncorked-canvas_2026-03-09_performance_report.md
│   │   └── ...
│   └── optimization/
│       ├── uncorked-canvas_2026-03-09_wasted_spend_analysis.md
│       └── ...
└── [other-workspace-files]
```

---

## PDF Generation

### Method 1: Using `nano-pdf` (if available)

Install nano-pdf skill:
```bash
clawhub search nano-pdf
clawhub install nano-pdf
```

Generate PDF from markdown:
```bash
nano-pdf convert reports/keyword-research/uncorked-canvas_2026-03-09_keyword_research.md -o uncorked-canvas_keyword_research.pdf
```

### Method 2: Using Pandoc (recommended for bulk exports)

Install pandoc:
```bash
apt-get install pandoc wkhtmltopdf
```

Convert single file:
```bash
pandoc reports/keyword-research/uncorked-canvas_2026-03-09_keyword_research.md \
  -o uncorked-canvas_keyword_research.pdf \
  --pdf-engine=wkhtmltopdf
```

Convert multiple reports with styling:
```bash
pandoc reports/keyword-research/uncorked-canvas_2026-03-09_keyword_research.md \
  reports/performance-analysis/uncorked-canvas_2026-03-09_performance_report.md \
  -o uncorked-canvas_full_analysis.pdf \
  --from=markdown \
  --pdf-engine=wkhtmltopdf \
  --template=path/to/template.html
```

### Method 3: Using Python + weasyprint

```bash
pip install weasyprint
```

```python
from weasyprint import HTML

HTML('reports/keyword-research/uncorked-canvas_2026-03-09.md').write_pdf(
    'uncorked-canvas_keyword_research.pdf'
)
```

### Method 4: Browser Print-to-PDF (Quick & Easy)

1. Open markdown file in VS Code
2. Install "Markdown Preview GitHub Styling" extension
3. Right-click → Open Preview
4. Ctrl+P → Print → Save as PDF

---

## Client Delivery Workflow

### 1. Generate Report
```bash
# Inside OpenClaw session
# After running performance analysis, I output to:
reports/performance-analysis/uncorked-canvas_2026-03-09_performance_report.md
```

### 2. Convert to PDF
```bash
pandoc reports/performance-analysis/uncorked-canvas_2026-03-09_performance_report.md \
  -o reports/performance-analysis/uncorked-canvas_2026-03-09_performance_report.pdf \
  --pdf-engine=wkhtmltopdf
```

### 3. Share with Client
```bash
# Email or Slack the PDF
# File saved at: ~/downloads/uncorked-canvas_2026-03-09_performance_report.pdf
```

### 4. Archive
Move to dated archive folder after delivery:
```bash
mv reports/performance-analysis/uncorked-canvas_2026-03-09_performance_report.pdf \
   reports/archive/2026-03/
```

---

## Usage Examples

### Example 1: Creating a New Campaign

```
User: "Let's build a Google Ads search campaign for Uncorked Canvas kits"

1. I copy _TEMPLATE_campaign.md → campaigns/uncorked-canvas/kits-campaign.md
2. Fill in basic info (client, objective, budget, landing page)
3. Run: research_keywords()
   → Auto-logged to kits-campaign-logs/[date]_research_keywords.md
   → Data populated into kits-campaign.md § Keyword Research
4. Run: discover_existing_assets()
   → Auto-logged to kits-campaign-logs/[date]_discover_existing_assets.md
   → Data populated into kits-campaign.md § Ad Assets
5. Run: suggest_ad_content()
   → Auto-logged to kits-campaign-logs/[date]_suggest_ad_content.md
   → Headlines + descriptions populated into kits-campaign.md
6. Git commit: "adspirer: uncorked-canvas keyword-research - kits campaign"
7. User reviews and approves
8. Run: create_search_campaign()
   → Auto-logged to kits-campaign-logs/[date]_create_search_campaign.md
   → Campaign ID + status populated into kits-campaign.md
9. Git commit: "adspirer: uncorked-canvas campaign-creation - kits campaign (paused for review)"
10. Campaign ready for user to launch
```

### Example 2: Generating a Client Report

```
User: "Pull a performance report for uncorked-canvas, last 30 days"

1. I call: get_campaign_performance(lookback_days=30)
2. Results auto-logged to [campaign]-logs/[date]_performance_check.md
3. I populate _TEMPLATE_performance_report.md with results
   → Save as: reports/performance-analysis/uncorked-canvas_2026-03-09_performance_report.md
4. I call: analyze_wasted_spend()
   → Auto-logged
   → Data added to report § Wasted Spend Analysis
5. Add recommendations section
6. Git commit: "adspirer: uncorked-canvas performance-analysis - 30-day report"
7. Convert to PDF: `pandoc ... -o uncorked-canvas_performance_report.pdf`
8. Ready to email to client
```

---

## Maintenance

### Weekly
- Review git log for accuracy
- Verify all logs have corresponding campaign doc entries
- Check for any missing approval markers

### Monthly
- Archive old logs (>90 days)
- Generate summary report across all clients
- Update CAMPAIGNS_INDEX.md with latest status

### Quarterly
- Clean up archived reports
- Review template formats for improvements
- Update version numbers if templates change

---

## Tips

1. **Always confirm before major actions** — Logging system captures decisions, so user approval is explicitly recorded
2. **Use descriptive commit messages** — Makes it easy to find what changed and when
3. **Tag reports with campaign version** — e.g., `uncorked-canvas_2026-03-09_v2_performance_report.pdf` if campaign changed
4. **Keep logs even after campaigns end** — Valuable for historical analysis and client references
5. **PDF generation is last step** — All markdown finalized → reviewed → converted to PDF for delivery

---

_Last updated: 2026-03-09_
