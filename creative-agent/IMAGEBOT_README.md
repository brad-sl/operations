# ImageBot MVP - DALL-E Image Generation Agent

A Python-based image generation agent that creates multiple ad creatives for campaigns using OpenAI's DALL-E 3, automatically resizes them to platform-specific dimensions, and uploads them to Google Cloud Storage with public HTTPS URLs.

## Features

✨ **Core Capabilities:**
- Generate 3-5 image variations per theme (Speed, Cost, Quality, Integration, Social Proof)
- Support multiple ad platforms with platform-specific aspect ratios
- Automatic image resizing using PIL/Pillow
- Google Cloud Storage integration with public URL generation
- JSON manifest and CSV export for easy review
- Retry logic for robust API calls
- Two operational modes: TEST (1 image) and FULL (15-20 images)

🎨 **Supported Platforms:**
- **Google Ads**: 300x250, 728x90 (banner sizes)
- **Meta**: 1200x628 (feed), 1080x1080 (square)
- **LinkedIn**: 1200x628, 1080x1080
- **TikTok**: 1080x1080 (square vertical)

📊 **Output Formats:**
- JSON manifest with all image metadata
- CSV spreadsheet for review and tracking
- Public HTTPS URLs for immediate use in ad platforms

## Installation

### Prerequisites
- Python 3.9+
- OpenAI API key
- Google Cloud Storage bucket with credentials

### Setup

```bash
# Create virtual environment
python3 -m venv imagebot_env
source imagebot_env/bin/activate

# Install dependencies
pip install openai google-cloud-storage pillow requests

# Set API credentials
export OPENAI_API_KEY="your-openai-key"
export GOOGLE_APPLICATION_CREDENTIALS="path/to/service-account.json"
```

## Usage

### Quick Start

```bash
# TEST MODE: Generate 1 sample image
python imagebot.py --input brief.json --mode test

# FULL MODE: Generate 15-20 images per campaign
python imagebot.py --input brief.json --mode full --bucket gs://brad-creative-assets
```

### Campaign Brief Format

Create a `brief.json` file with your campaign details:

```json
{
  "id": "campaign-001",
  "product_description": "HR SaaS platform for employee onboarding automation",
  "target_audience": "HR managers at 10-500 person companies",
  "key_benefits": [
    "faster onboarding",
    "fewer errors",
    "integrates with existing tools"
  ],
  "visual_style": "professional",
  "platform": "meta",
  "theme": "speed"
}
```

### Command-Line Options

```bash
python imagebot.py \
  --input brief.json              # Required: Path to campaign brief
  --mode test|full                # Optional: Generation mode (default: test)
  --bucket gs://your-bucket       # Optional: GCS bucket (default: gs://brad-creative-assets)
  --credentials path/to/sa.json   # Optional: Service account JSON path
  --output-dir ./output           # Optional: Output directory (default: ./imagebot_output)
```

## Configuration

### Campaign Brief Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `id` | string | Unique campaign identifier | `"hr-saas-001"` |
| `product_description` | string | Short product name | `"HR SaaS platform"` |
| `target_audience` | string | Target customer profile | `"HR managers"` |
| `key_benefits` | array | Primary value propositions | `["faster onboarding", ...]` |
| `visual_style` | string | Design tone (professional/casual/playful) | `"professional"` |
| `platform` | string | Target ad platform | `"meta"` |
| `theme` | string | Primary theme (optional) | `"speed"` |

### Visual Styles
- **professional**: Clean, corporate, business-focused
- **casual**: Friendly, approachable, conversational
- **playful**: Fun, energetic, creative

### Themes (Generated Variations)

ImageBot generates 5 distinct themes for each campaign:

1. **Speed**: Fast, efficient, quick implementation
2. **Cost**: Budget-conscious, ROI-focused, savings
3. **Quality**: Premium, excellence, high-standard
4. **Integration**: Seamless, compatible, connected
5. **Social Proof**: Testimonials, success stories, trust

## Output Specification

### Manifest JSON

```json
{
  "brief_id": "hr-saas-001",
  "campaign_name": "HR SaaS platform for employee onboarding automation",
  "platform": "meta",
  "mode": "full",
  "generated_at": "2025-03-10T15:30:45.123456",
  "images": [
    {
      "id": "img_speed_000_000",
      "theme": "speed",
      "platform": "meta",
      "dimensions": "1200x628",
      "url": "https://storage.googleapis.com/brad-creative-assets/creatives/hr-saas-001/images/img_speed_000_000_1200x628.png",
      "alt_text": "HR SaaS - Fast and speedy onboarding process",
      "file_size_kb": 245.5,
      "prompt_used": "A vibrant, modern illustration showing rapid faster onboarding..."
    }
  ],
  "upload_status": "success",
  "storage_location": "gs://brad-creative-assets/creatives/hr-saas-001/images/",
  "summary": {
    "total_images": 10,
    "themes": ["speed", "cost", "quality", "integration", "social_proof"],
    "total_size_mb": 2.45
  }
}
```

### CSV Export

```csv
id,theme,platform,dimensions,url,alt_text,file_size_kb
img_speed_000_000,speed,meta,1200x628,https://storage.googleapis.com/.../img_speed_000_000_1200x628.png,HR SaaS - Fast and speedy onboarding process,245.5
img_cost_001_000,cost,meta,1200x628,https://storage.googleapis.com/.../img_cost_001_000_1200x628.png,HR SaaS - Cost-effective solution saving money,232.1
...
```

## How It Works

### 1. Image Generation (DALL-E 3)
- Takes campaign brief + theme
- Generates custom prompts for each theme
- Calls OpenAI DALL-E 3 API (1024x1024 base size)
- Includes retry logic for reliability

### 2. Image Resizing (PIL/Pillow)
- Crops image to target aspect ratio
- Resizes to exact platform dimensions
- Preserves quality with LANCZOS resampling
- Converts RGBA to RGB as needed

### 3. Cloud Upload (Google Cloud Storage)
- Uploads to specified GCS bucket
- Sets public read ACL
- Generates public HTTPS URL
- Records file metadata

### 4. Manifest Generation
- Compiles all image metadata
- Exports JSON manifest
- Exports CSV for spreadsheet review
- Includes campaign summary stats

## Environment Variables

```bash
# Required
OPENAI_API_KEY="sk-..."                 # OpenAI API key

# Optional
GOOGLE_APPLICATION_CREDENTIALS="..."    # Path to GCS service account JSON
```

If `GOOGLE_APPLICATION_CREDENTIALS` is not set, ImageBot will use your default Google Cloud credentials (gcloud CLI authentication).

## Image Specifications

### Quality Standards
- **Format**: PNG with 95% quality
- **Max File Size**: 5MB per image
- **Dimensions**: Platform-specific (see table below)
- **Color Space**: RGB (converted from RGBA)

### Dimension Support

| Platform | Dimensions | Use Case |
|----------|-----------|----------|
| Google Ads | 300x250 | Standard banner |
| Google Ads | 728x90 | Leaderboard |
| Meta | 1200x628 | Feed post |
| Meta | 1080x1080 | Square/story |
| LinkedIn | 1200x628 | Feed post |
| LinkedIn | 1080x1080 | Square |
| TikTok | 1080x1080 | Square (vertical crops available) |

## Examples

### Example 1: HR SaaS Campaign (TEST MODE)

```bash
cat > hr_saas_brief.json << 'EOF'
{
  "id": "hr-saas-001",
  "product_description": "HR SaaS platform for employee onboarding automation",
  "target_audience": "HR managers at 10-500 person companies",
  "key_benefits": ["faster onboarding", "fewer errors", "integrates with existing tools"],
  "visual_style": "professional",
  "platform": "meta"
}
EOF

python imagebot.py --input hr_saas_brief.json --mode test
```

### Example 2: Ecommerce Campaign (FULL MODE)

```bash
cat > ecommerce_brief.json << 'EOF'
{
  "id": "ecommerce-001",
  "product_description": "AI-powered inventory management for online retailers",
  "target_audience": "ecommerce store owners",
  "key_benefits": ["reduce stockouts", "lower holding costs", "automated forecasting"],
  "visual_style": "professional",
  "platform": "linkedin"
}
EOF

python imagebot.py --input ecommerce_brief.json --mode full --bucket gs://my-bucket
```

### Example 3: Programmatic Usage

```python
from imagebot import ImageBot

# Create brief
brief = {
    "id": "campaign-001",
    "product_description": "My SaaS Product",
    "target_audience": "Enterprise CTOs",
    "key_benefits": ["save time", "reduce costs"],
    "visual_style": "professional",
    "platform": "meta"
}

# Initialize and generate
bot = ImageBot()
manifest = bot.generate_campaign_images(
    brief=brief,
    bucket_name="gs://my-bucket",
    mode="full"
)

# Export results
bot.export_manifest(manifest, "manifest.json")
bot.export_csv(manifest, "images.csv")
```

## Troubleshooting

### Issue: "No module named 'openai'"
```bash
source imagebot_env/bin/activate
pip install openai
```

### Issue: "Google API error"
```bash
# Set credentials
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"

# Or use gcloud CLI auth
gcloud auth application-default login
```

### Issue: "DALL-E quota exceeded"
- Check OpenAI usage at https://platform.openai.com/account/usage
- Upgrade account or wait for quota reset

### Issue: "Image upload failed"
- Verify bucket exists: `gsutil ls gs://your-bucket`
- Check GCS permissions: `gsutil acl ch -u AllUsers:R gs://your-bucket/file.png`
- Verify public access is enabled on bucket

## Performance & Costs

### Execution Time
- **TEST MODE**: ~2-3 minutes (1 image)
- **FULL MODE**: ~15-20 minutes (15-20 images)

### API Costs (Approximate)
- DALL-E 3 generation: $0.08 per image
- GCS storage: $0.023 per GB/month
- GCS transfer: Free (same region)

### Examples
- TEST MODE (1 image): ~$0.08
- FULL MODE (20 images): ~$1.60
- Monthly storage (100 campaigns): ~$5-10

## Architecture

```
Brief JSON
    ↓
ImageBot Init (OpenAI + GCS)
    ↓
For each theme:
    ├─ Build prompt
    ├─ Call DALL-E 3 API
    ├─ Download image
    └─ For each platform dimension:
        ├─ Resize image (PIL)
        ├─ Upload to GCS
        └─ Record metadata
    ↓
Export Manifest (JSON)
Export CSV (Spreadsheet)
```

## API Reference

### ImageBot Class

```python
class ImageBot:
    def __init__(self, openai_api_key=None, gcs_credentials=None)
    def generate_image(prompt, size="1024x1024", retries=3) -> bytes
    def resize_image(image_bytes, target_width, target_height) -> bytes
    def upload_to_gcs(image_bytes, bucket_name, destination_path) -> str
    def generate_campaign_images(brief, bucket_name, mode="test", themes=None) -> dict
    def export_manifest(manifest, output_path) -> str
    def export_csv(manifest, output_path) -> str
```

## License

MIT License - Use freely in your projects

## Support

For issues, questions, or feature requests, reach out to the development team.

---

**Version**: 1.0 MVP
**Last Updated**: 2025-03-10
**Status**: Production Ready
