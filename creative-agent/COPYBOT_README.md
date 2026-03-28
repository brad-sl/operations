# CopyBot MVP — Ad Copy Generation Agent

## Overview

CopyBot is a simple, powerful agent that generates **25-30 ad headline + description variations** grouped by marketing theme. Perfect for bootstrap campaigns across Google Ads, Meta, LinkedIn, and TikTok.

**Input:** Campaign brief (product, audience, tone, benefits, CTA)  
**Output:** JSON with themed headlines and descriptions, validated against platform constraints

## Features

✅ **5 Marketing Themes** (Speed, Cost, Quality, Integration, Social Proof)  
✅ **30 Headlines** (6 per theme, ≤30 characters each)  
✅ **30 Descriptions** (6 per theme, ≤90 characters each)  
✅ **Validation Built-in** (character counts, hyphens, exclamation marks)  
✅ **Easy to Swap Briefs** (just modify the brief dict)  
✅ **Works Today** (no API key required for MVP demo mode)  
✅ **Ready for Claude/GPT-4** (plug in your API key for real LLM generation)

## Quick Start

### 1. Run the MVP Demo (No API Key Needed)

```bash
cd /home/brad/.openclaw/workspace
python3 copybot.py
```

**Output:**
- Console summary with validation results
- Full JSON output → `copybot_output.json`

### 2. Use with Claude API (Recommended)

```bash
# Set your API key
export ANTHROPIC_API_KEY="sk-ant-..."

# Run
python3 copybot.py
```

The script automatically detects the API key and uses Claude for generation instead of templates.

### 3. Integrate into Your Workflow

```python
from copybot import generate_copy_from_templates, generate_ad_copy_via_api, validate_copy

# Your campaign brief
brief = {
    "product_description": "Social media scheduling tool for small businesses",
    "target_audience": "Small business owners with 1-10 employees",
    "tone": "casual",
    "platform": "meta",
    "key_benefits": ["saves time", "better engagement", "team collaboration"],
    "cta": "Start Free 14 Days"
}

# Generate (uses API if key set, otherwise templates)
copy_obj = generate_ad_copy_via_api(brief) if os.getenv("ANTHROPIC_API_KEY") else generate_copy_from_templates(brief)

# Validate
errors = validate_copy(copy_obj)
if not errors:
    print("✅ Copy ready to upload!")
```

## Output Format

```json
{
  "headlines": [
    {
      "id": "h_speed_001",
      "text": "Onboard 80% Faster",
      "theme": "speed",
      "char_count": 18
    },
    {
      "id": "h_cost_007",
      "text": "Cut Onboarding Costs 50%",
      "theme": "cost",
      "char_count": 24
    }
  ],
  "descriptions": [
    {
      "id": "d_speed_001",
      "text": "Cut onboarding time from weeks to days. New hires productive immediately.",
      "theme": "speed",
      "char_count": 73
    }
  ]
}
```

Each headline/description includes:
- **id:** Unique identifier (theme_number)
- **text:** The actual copy
- **theme:** Which marketing theme (speed, cost, quality, integration, socialproof)
- **char_count:** Validated character count

## Prompt Engineering (The Secret Sauce)

The magic is in the system prompt. It includes:

1. **Theme Definitions** — What makes "Speed" different from "Cost"?
2. **Concrete Examples** — Good headlines vs. bad (similar) headlines
3. **Hard Constraints** — Max 30 chars, no hyphens, no trailing exclamation marks
4. **Unique Copy Requirement** — Forces variation, not just word swaps
5. **Benefit-First Framing** — "Why should I care?" before "What is it?"

This prompt works equally well with Claude, GPT-4, or other capable LLMs.

## Platform-Specific Notes

### Google Ads Search (RSA)
- Headlines: Max 30 characters, 3 per ad
- Descriptions: Max 90 characters, 2 per ad
- No hyphens in headlines (Google's preference)
- CopyBot provides all variations; you pick the best

### Meta Ads
- Headlines: 30-125 characters (CopyBot gives you 30-char versions)
- Descriptions: 20-300 characters (CopyBot gives you 90-char versions)
- Copy is more informal; use "casual" tone for best results

### LinkedIn Ads
- Headlines: 25-255 characters (CopyBot provides 30-char versions)
- Descriptions: 50-1200 characters (CopyBot provides 90-char versions)
- Professional tone recommended for B2B audiences

### TikTok Ads
- Hashtags and emojis work well (not included in CopyBot MVP)
- Casual, playful tone performs best
- Video should be the star; copy is supporting

## Customization

### Change the Brief

Edit the `sample_brief` dict in `main()`:

```python
sample_brief = {
    "product_description": "YOUR PRODUCT HERE",
    "target_audience": "YOUR AUDIENCE HERE",
    "tone": "professional|casual|playful",
    "platform": "google_ads|meta|linkedin|tiktok",
    "key_benefits": ["benefit1", "benefit2", "benefit3"],
    "cta": "YOUR CALL TO ACTION"
}
```

### Add Custom Themes

Edit the `COPY_TEMPLATES` dict to add new themes or override existing ones:

```python
COPY_TEMPLATES["custom_theme"] = {
    "headlines": [
        "Your headline here",
        "Another headline",
    ],
    "descriptions": [
        "Your description here",
        "Another description",
    ]
}
```

### Use with GPT-4 (via OpenAI)

```python
# Install: pip install openai

import openai

openai.api_key = os.getenv("OPENAI_API_KEY")

def generate_ad_copy_via_openai(brief):
    # Similar to generate_ad_copy_via_api but using openai.ChatCompletion.create()
    # ... (would need implementation)
```

## Validation Rules

CopyBot validates:
- ✅ Headline length ≤ 30 characters
- ✅ Description length ≤ 90 characters
- ✅ No hyphens in headlines
- ✅ No trailing exclamation marks
- ✅ Minimum 25 headlines (3+ warnings at <25)
- ✅ Minimum 25 descriptions (3+ warnings at <25)

All validations must pass before copy is considered "ready to upload."

## Limitations & Future Work

**MVP Limitations:**
- Template-based generation (when API key not set) is good but not creative
- Only 5 pre-defined themes
- No dynamic CTA insertion (users must manually add CTAs to descriptions)
- No A/B testing variants (all copies are variations, not A/B pairs)

**Future Enhancements:**
- Support for GPT-4, Gemini, Llama via pluggable LLM interface
- 10+ custom themes (per industry)
- Dynamic CTA injection
- A/B test pairing (suggest which headlines pair best with which descriptions)
- Tone variation within themes (e.g., "Speed + Playful" vs "Speed + Professional")
- Bulk generation (upload CSV of briefs, get 100+ copy variations)
- Integration with Google Ads API for direct upload (skip manual paste)

## Sample Output (HR SaaS Example)

**Speed Theme Headlines:**
- Onboard 80% Faster (18 chars)
- Speed Up Hiring Process (23 chars)
- Complete Setup in Days (22 chars)
- Instant New Hire Launch (23 chars)
- Cut Admin Time in Half (22 chars)
- Faster Employee Onboarding (26 chars)

**Cost Theme Descriptions:**
- Eliminate manual data entry. Reduce onboarding spend per hire by 50%.
- Automate time consuming tasks. Cut HR administration costs significantly.
- One platform replaces multiple tools. Reduce tech spending on onboarding.
- Less manual work means lower costs. Save thousands with automation.
- Reduce HR resource requirements. Better ROI on each new hire.
- Cut recruiting and onboarding expenses. Improve profitability.

## Architecture

```
copybot.py
├── SYSTEM_PROMPT          # The master prompt (works with any LLM)
├── COPY_TEMPLATES         # Fallback templates (MVP mode)
├── generate_ad_copy_via_api()     # Claude API integration
├── generate_copy_from_templates() # Template-based fallback
├── validate_copy()        # Constraint validation
└── main()                 # Entry point
```

**~500 lines of clean, modular Python.** No dependencies beyond `anthropic` (optional).

## Testing

Run once more with the sample brief:

```bash
python3 copybot.py
```

Expected output:
- 30 headlines, all ≤30 chars, all unique
- 30 descriptions, all ≤90 chars, all unique
- 5 themes: speed, cost, quality, integration, socialproof
- All validations pass

## FAQ

**Q: Do I need an API key to use CopyBot?**  
A: No. The MVP works with template-based generation. For AI-generated copy, set `ANTHROPIC_API_KEY` to use Claude (recommended) or modify the script to use another LLM.

**Q: Can I use this with GPT-4?**  
A: Yes. Modify `generate_ad_copy_via_api()` to call OpenAI's API instead. The prompt is model-agnostic.

**Q: How unique are the templates?**  
A: Good enough for MVP testing. They follow the prompt guidelines (no word swaps, benefit-first framing). For production, use Claude or GPT-4.

**Q: Can I add more than 5 themes?**  
A: Yes. Add to `COPY_TEMPLATES` dict and update `theme_order` in `generate_copy_from_templates()`.

**Q: Can I upload these headlines directly to Google Ads?**  
A: Yes. The JSON format is ready for manual upload to ad groups. Future version will integrate with Google Ads API for direct upload.

## Support

For questions or improvements, check the prompt in `SYSTEM_PROMPT` — it's designed to be clear and self-documenting. To improve copy quality, refine the prompt (it's the only magic).

---

**Built with prompt engineering principles that work with Claude, GPT-4, Llama, and other capable LLMs.**
