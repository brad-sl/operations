# ImageBot MVP - Deployment Guide

## Overview

ImageBot MVP is a production-ready DALL-E image generation agent for creating ad campaign creatives at scale. This guide walks through setup, configuration, and deployment.

## Quick Start (Real APIs)

### Step 1: Prerequisites

```bash
# Ensure you have Python 3.9+
python3 --version

# Create and activate virtual environment
python3 -m venv imagebot_env
source imagebot_env/bin/activate

# Install dependencies
pip install openai google-cloud-storage pillow requests
```

### Step 2: Configure API Keys

#### OpenAI API Key

1. Get key from https://platform.openai.com/api-keys
2. Set environment variable:

```bash
export OPENAI_API_KEY="sk-your-api-key-here"
```

Or pass to the script:

```bash
python imagebot.py --input brief.json --openai-key "sk-your-api-key"
```

#### Google Cloud Storage

Option A: Use default credentials (gcloud CLI):

```bash
gcloud auth application-default login
```

Option B: Use service account JSON:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"
```

Or pass to script:

```bash
python imagebot.py --input brief.json --credentials /path/to/sa.json
```

### Step 3: Create GCS Bucket

```bash
# Create bucket if not exists
gsutil mb gs://brad-creative-assets

# Verify bucket
gsutil ls gs://brad-creative-assets

# Enable public read (for images)
gsutil acl ch -u AllUsers:R gs://brad-creative-assets
```

### Step 4: Run ImageBot

```bash
# Test mode (1 image)
python imagebot.py --input sample_brief_hr_saas.json --mode test

# Full mode (all themes + dimensions)
python imagebot.py --input sample_brief_hr_saas.json --mode full

# Custom bucket
python imagebot.py --input brief.json --mode full --bucket gs://my-bucket
```

## Production Deployment

### Option 1: Local Machine (Development)

```bash
# Activate venv
source imagebot_env/bin/activate

# Run with logging
python imagebot.py --input brief.json --mode full 2>&1 | tee logs/campaign.log
```

### Option 2: Cloud Function (Serverless)

Deploy as Google Cloud Function for automated triggers:

```bash
# Create Cloud Function
gcloud functions create imagebot-generate \
  --runtime python312 \
  --trigger-http \
  --entry-point generate_campaign \
  --allow-unauthenticated

# Deploy function code
gcloud functions deploy imagebot-generate \
  --source . \
  --runtime python312
```

Cloud Function code (`main.py`):

```python
from imagebot import ImageBot
import json
from flask import Request, jsonify

def generate_campaign(request: Request):
    """HTTP endpoint for ImageBot"""
    request_json = request.get_json()
    
    brief = request_json.get("brief")
    bucket = request_json.get("bucket", "gs://brad-creative-assets")
    mode = request_json.get("mode", "test")
    
    bot = ImageBot()
    manifest = bot.generate_campaign_images(
        brief=brief,
        bucket_name=bucket,
        mode=mode
    )
    
    return jsonify(manifest)
```

Call the function:

```bash
curl -X POST https://region-project.cloudfunctions.net/imagebot-generate \
  -H "Content-Type: application/json" \
  -d '{
    "brief": {
      "id": "campaign-001",
      "product_description": "My Product",
      "target_audience": "Users",
      "key_benefits": ["benefit1"],
      "visual_style": "professional",
      "platform": "meta"
    },
    "mode": "full"
  }'
```

### Option 3: Docker Container

Deploy with Docker for portability:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -q -r requirements.txt

COPY imagebot.py .

ENTRYPOINT ["python", "imagebot.py"]
```

Build and push:

```bash
docker build -t imagebot:latest .
docker tag imagebot:latest gcr.io/YOUR_PROJECT/imagebot:latest
docker push gcr.io/YOUR_PROJECT/imagebot:latest
```

Run container:

```bash
docker run -e OPENAI_API_KEY=sk-... \
  -e GOOGLE_APPLICATION_CREDENTIALS=/secrets/sa.json \
  -v /path/to/sa.json:/secrets/sa.json \
  imagebot:latest \
  --input brief.json --mode full
```

### Option 4: Cloud Run (Containerized HTTP Service)

```bash
# Deploy to Cloud Run
gcloud run deploy imagebot \
  --image gcr.io/YOUR_PROJECT/imagebot:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars OPENAI_API_KEY=sk-... \
  --service-account imagebot-sa@YOUR_PROJECT.iam.gserviceaccount.com
```

## Integration Examples

### Adspirer Integration

Use ImageBot to generate creatives for Adspirer campaigns:

```python
from imagebot import ImageBot
from adspirer_client import AdspireClient

# Generate images
bot = ImageBot()
manifest = bot.generate_campaign_images(
    brief={
        "product_description": "My SaaS",
        "target_audience": "Businesses",
        "key_benefits": ["save time"],
        "visual_style": "professional",
        "platform": "meta"
    },
    bucket_name="gs://brad-creative-assets",
    mode="full"
)

# Get image URLs
image_urls = [img["url"] for img in manifest["images"]]

# Create Meta Ads campaign with generated images
client = AdspireClient()
campaign = client.create_meta_image_campaign(
    name="Generated Campaign",
    target_audience="All Users",
    image_urls=image_urls,
    budget=1000
)
```

### Scheduled Automation (Cloud Scheduler)

Schedule ImageBot to run on a cron job:

```bash
# Create Cloud Scheduler job
gcloud scheduler jobs create http imagebot-daily \
  --schedule="0 9 * * MON" \
  --uri="https://region-project.cloudfunctions.net/imagebot-generate" \
  --http-method=POST \
  --message-body='{
    "brief": {
      "id": "weekly-campaign",
      "product_description": "My Product",
      "target_audience": "Users",
      "key_benefits": ["benefit"],
      "visual_style": "professional",
      "platform": "meta"
    },
    "mode": "full"
  }'
```

## Monitoring & Troubleshooting

### Check API Usage

```bash
# OpenAI API usage
curl https://api.openai.com/v1/usage/usage_records \
  -H "Authorization: Bearer $OPENAI_API_KEY"

# GCS bucket size
gsutil du -s gs://brad-creative-assets
```

### Common Issues

| Issue | Solution |
|-------|----------|
| `OPENAI_API_KEY not set` | `export OPENAI_API_KEY="sk-..."` |
| `GCS bucket not found` | `gsutil mb gs://bucket-name` |
| `Permission denied` | Check GCS IAM permissions |
| `Rate limit exceeded` | Add retry delays, upgrade API plan |
| `Out of memory` | Use smaller batch sizes |

### Logs

View execution logs:

```bash
# Cloud Function logs
gcloud functions logs read imagebot-generate --limit=100

# Cloud Run logs
gcloud run logs read imagebot --limit=100

# Local logs
python imagebot.py ... 2>&1 | tee campaign.log
```

## Performance Optimization

### Batch Processing

Process multiple briefs in parallel:

```python
from concurrent.futures import ThreadPoolExecutor
from imagebot import ImageBot

briefs = [
    {"id": "campaign-1", ...},
    {"id": "campaign-2", ...},
    {"id": "campaign-3", ...},
]

def generate(brief):
    bot = ImageBot()
    return bot.generate_campaign_images(brief, bucket_name="gs://brad-creative-assets")

with ThreadPoolExecutor(max_workers=3) as executor:
    results = list(executor.map(generate, briefs))
```

### Cost Optimization

- Use TEST mode for validation ($0.08 per campaign)
- Batch FULL mode generation ($1.60 per campaign)
- Cache image variations between runs
- Use scheduled jobs instead of continuous generation

## Security Best Practices

✅ **DO:**
- Store API keys in environment variables
- Use service accounts with minimal IAM permissions
- Enable GCS versioning for image history
- Audit API usage regularly
- Rotate API keys quarterly

❌ **DON'T:**
- Commit API keys to version control
- Share service account JSON files
- Make buckets public (use signed URLs)
- Grant Editor/Admin permissions broadly
- Disable audit logging

## Monitoring Dashboard

Create a monitoring dashboard for production:

```bash
# Create Cloud Monitoring dashboard
gcloud monitoring dashboards create --config-from-file=dashboard.yaml
```

Dashboard config (`dashboard.yaml`):

```yaml
displayName: "ImageBot Monitoring"
gridLayout:
  widgets:
  - title: "Daily Campaigns Generated"
    xyChart:
      dataSets:
      - timeSeriesQuery:
          timeSeriesFilter:
            filter: 'resource.type="cloud_function" resource.label.function_name="imagebot-generate"'
  - title: "API Costs"
    xyChart:
      dataSets:
      - timeSeriesQuery:
          timeSeriesFilter:
            filter: 'metric.type="serviceruntime.googleapis.com/api/consumer/quota_used_count"'
```

## Scaling Checklist

- [ ] API quota increased for DALL-E
- [ ] GCS bucket with versioning enabled
- [ ] Service account with Cloud Storage permissions
- [ ] Cloud Logging configured
- [ ] Error notifications (Slack/Email)
- [ ] Monthly cost budget alert ($100-500)
- [ ] Backup strategy for generated images
- [ ] Documentation updated

## Support & Next Steps

- **Questions?** Check IMAGEBOT_README.md for detailed documentation
- **Issues?** Run in test mode first to validate configuration
- **Scaling?** Use Cloud Function or Cloud Run for automated execution
- **Integration?** Connect with Adspirer for campaign automation

---

**Version**: 1.0 MVP  
**Last Updated**: 2025-03-10  
**Status**: Production Ready
