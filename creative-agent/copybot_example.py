#!/usr/bin/env python3
"""
CopyBot Usage Examples — Integration patterns and output formats.
"""

import json
import os
from copybot import (
    generate_copy_from_templates,
    generate_ad_copy_via_api,
    validate_copy,
    SYSTEM_PROMPT
)


# ============================================================================
# Example 1: Generate copy for a SaaS product
# ============================================================================

def example_saas_product():
    """Generate copy for a project management tool."""
    print("\n" + "="*70)
    print("Example 1: SaaS Product (Project Management Tool)")
    print("="*70)

    brief = {
        "product_description": "Cloud based project management platform for remote teams",
        "target_audience": "Tech managers and project leads at startups",
        "tone": "professional",
        "platform": "google_ads",
        "key_benefits": ["real time collaboration", "transparent timelines", "fewer meetings"],
        "cta": "Try Free for 14 Days"
    }

    # Generate
    copy_obj = generate_copy_from_templates(brief)

    # Validate
    errors = validate_copy(copy_obj)
    print(f"\n✅ Generated {len(copy_obj['headlines'])} headlines, {len(copy_obj['descriptions'])} descriptions")
    print(f"   Status: {'✅ All valid' if not errors else f'⚠️  {len(errors)} errors'}")

    # Show themes
    themes = sorted(set(h["theme"] for h in copy_obj["headlines"]))
    print(f"\n📊 Themes: {', '.join(themes)}")

    # Show sample copy
    print("\n📝 Sample Speed Headlines:")
    for h in [h for h in copy_obj["headlines"] if h["theme"] == "speed"][:2]:
        print(f"   • {h['text']} ({h['char_count']} chars)")

    return copy_obj


# ============================================================================
# Example 2: Generate copy for an e-commerce product
# ============================================================================

def example_ecommerce_product():
    """Generate copy for an online store builder."""
    print("\n" + "="*70)
    print("Example 2: E-Commerce (Online Store Builder)")
    print("="*70)

    brief = {
        "product_description": "DIY online store builder for handmade crafts and products",
        "target_audience": "Etsy sellers and crafters looking to build their own store",
        "tone": "casual",
        "platform": "meta",
        "key_benefits": ["no coding required", "beautiful templates", "built in payments"],
        "cta": "Start Selling Today"
    }

    copy_obj = generate_copy_from_templates(brief)
    errors = validate_copy(copy_obj)

    print(f"\n✅ Generated {len(copy_obj['headlines'])} headlines, {len(copy_obj['descriptions'])} descriptions")
    print(f"   Status: {'✅ All valid' if not errors else f'⚠️  {len(errors)} errors'}")

    # Show all quality headlines
    quality_headlines = [h for h in copy_obj["headlines"] if h["theme"] == "quality"]
    print(f"\n📝 Quality Theme Headlines:")
    for h in quality_headlines:
        print(f"   • {h['text']} ({h['char_count']} chars)")

    return copy_obj


# ============================================================================
# Example 3: Export to CSV (for manual upload to ad platforms)
# ============================================================================

def export_to_csv(copy_obj, filename="copybot_export.csv"):
    """Export headlines and descriptions to CSV format."""
    import csv

    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)

        # Headers
        writer.writerow(["Type", "ID", "Theme", "Copy", "Char Count"])

        # Headlines
        for h in copy_obj["headlines"]:
            writer.writerow(["Headline", h["id"], h["theme"], h["text"], h["char_count"]])

        # Descriptions
        for d in copy_obj["descriptions"]:
            writer.writerow(["Description", d["id"], d["theme"], d["text"], d["char_count"]])

    print(f"✅ Exported to {filename}")


# ============================================================================
# Example 4: Group by theme for review
# ============================================================================

def group_by_theme(copy_obj):
    """Organize copy by theme for easy review."""
    print("\n" + "="*70)
    print("Copy Organized by Theme")
    print("="*70)

    themes = sorted(set(h["theme"] for h in copy_obj["headlines"]))

    for theme in themes:
        headlines = [h for h in copy_obj["headlines"] if h["theme"] == theme]
        descriptions = [d for d in copy_obj["descriptions"] if d["theme"] == theme]

        print(f"\n📌 {theme.upper()}")
        print(f"   Headlines ({len(headlines)}):")
        for h in headlines:
            print(f"     • {h['text']} ({h['char_count']} chars)")

        print(f"\n   Descriptions ({len(descriptions)}):")
        for d in descriptions[:2]:  # Show first 2
            print(f"     • {d['text'][:60]}... ({d['char_count']} chars)")


# ============================================================================
# Example 5: Filter by character count for specific platform
# ============================================================================

def filter_by_platform_limits(copy_obj, platform="google_ads"):
    """Filter copy to platform-specific character limits."""
    limits = {
        "google_ads": {"headline": 30, "description": 90},
        "meta": {"headline": 125, "description": 300},
        "linkedin": {"headline": 255, "description": 1200},
        "tiktok": {"headline": 150, "description": 500},
    }

    limits_for_platform = limits.get(platform, limits["google_ads"])

    valid_headlines = [
        h for h in copy_obj["headlines"]
        if h["char_count"] <= limits_for_platform["headline"]
    ]
    valid_descriptions = [
        d for d in copy_obj["descriptions"]
        if d["char_count"] <= limits_for_platform["description"]
    ]

    print(f"\n{platform.upper()}")
    print(f"  Headline limit: {limits_for_platform['headline']} chars")
    print(f"  Description limit: {limits_for_platform['description']} chars")
    print(f"  Valid headlines: {len(valid_headlines)}/{len(copy_obj['headlines'])}")
    print(f"  Valid descriptions: {len(valid_descriptions)}/{len(copy_obj['descriptions'])}")

    return {
        "headlines": valid_headlines,
        "descriptions": valid_descriptions
    }


# ============================================================================
# Example 6: Show the prompt engineering
# ============================================================================

def show_prompt():
    """Print the system prompt used for generation."""
    print("\n" + "="*70)
    print("CopyBot System Prompt (Works with Claude, GPT-4, Llama)")
    print("="*70)
    print(SYSTEM_PROMPT[:500] + "...\n[truncated]\n")


# ============================================================================
# Main: Run all examples
# ============================================================================

def main():
    print("\n🤖 CopyBot Integration Examples\n")

    # Example 1: SaaS
    copy1 = example_saas_product()

    # Example 2: E-commerce
    copy2 = example_ecommerce_product()

    # Example 3: Export to CSV
    print("\n" + "="*70)
    print("Example 3: Export to CSV")
    print("="*70)
    export_to_csv(copy1, "/home/brad/.openclaw/workspace/copybot_saas_export.csv")

    # Example 4: Group by theme
    group_by_theme(copy2)

    # Example 5: Filter by platform
    print("\n" + "="*70)
    print("Example 5: Platform Compatibility Check")
    print("="*70)
    for platform in ["google_ads", "meta", "linkedin", "tiktok"]:
        filter_by_platform_limits(copy1, platform)

    # Example 6: Show the magic
    show_prompt()

    print("\n✅ All examples complete!")
    print("\nNext steps:")
    print("  1. Review copybot_saas_export.csv")
    print("  2. Pick your favorite headlines and descriptions")
    print("  3. Upload to your ad platform")
    print("  4. Test and iterate based on performance")


if __name__ == "__main__":
    main()
