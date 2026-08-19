# ARCH Automation — Brand Kit (draft)

**Status:** Draft pending Brad logo sign-off (PHASE-A-01)  
**Assets:** `docs/marketing/brand/assets/`  
**Date:** 2026-07-16  

---

## 1. Name system

| Form | Usage |
|------|--------|
| **ARCH Automation** | Primary product name (first mention, legal-ish footers) |
| **ARCH** | Short UI / nav after first full mention |
| **ARCH Starter / Pro / Elite** | Tier labels |
| Never | “Brad’s bot,” personal Telegram handle as product name |

Tagline (default):  
**Your Coinbase. Your capital. Rules-based automation.**

Category line:  
**Coinbase Advanced portfolio automation software**

---

## 2. Color tokens

| Token | Hex | Use |
|-------|-----|-----|
| `navy` | `#0B1F2A` | Primary brand field, dark UI chrome, mark background |
| `teal` | `#14B8A6` | Accent, CTAs, mark stroke on navy |
| `teal-dark` | `#0F766E` | Wordmark secondary on light backgrounds |
| `offwhite` | `#F4F7F9` | Light backgrounds, light mark fill |
| `slate` | `#1E293B` | Body text on light |
| `muted` | `#94A3B8` | Secondary text on dark |
| `success` | `#22C55E` | Runner healthy (UI only; not logo) |
| `warning` | `#F59E0B` | Needs attention |
| `danger` | `#EF4444` | Errors / pause |

**Do not** use neon purple crypto-meme palettes or gold “get rich” gradients in product brand.

---

## 3. Typography

| Role | Stack |
|------|--------|
| Display / logo | Inter, Segoe UI, Helvetica, Arial, sans-serif |
| UI / body | Same; system UI stack acceptable in product |
| Weight | ARCH = 700; Automation = 500; body 400–500 |

Avoid decorative script fonts and comic crypto fonts.

---

## 4. Logo system

Mark concept: **gateway arch + center pillar** (structure, discipline, entry to automation) — not a coin or chart.

| File | Use |
|------|-----|
| `logo-mark-primary.svg` | Default app icon / avatar (navy + teal) |
| `logo-mark-light.svg` | Light surfaces |
| `logo-mark-teal.svg` | High-energy accent tile |
| `logo-mark-mono-black.svg` | Print / single-color dark |
| `logo-mark-mono-white.svg` | On photography / dark photo |
| `logo-wordmark-dark.svg` | Light website headers |
| `logo-wordmark-light.svg` | Dark website headers |
| `logo-favicon.svg` | Browser favicon source |
| `logo-app-icon.svg` | Connect app / PWA-style icon |
| `social-avatar.svg` | Social profile |
| `social-banner.svg` | Cover / OG-style banner |

**Clear space:** ≥ 1/8 mark width padding.  
**Min size:** mark ≥ 24px digital; wordmark ≥ 120px wide.  
**Don’t:** stretch, recolor off-palette, add drop shadows, put mark on busy P&L screenshots.

---

## 5. Voice (brand, not full copy guide)

- Calm operator, not hype trader.  
- Prefer concrete process (“OAuth connect”, “pause on billing failure”) over vague “AI-powered alpha.”  
- Compliance-safe claims only (MKT plan §1.4).  

---

## 6. Export notes

- SVG is **source of truth**.  
- PNG: export 512 / 1024 / 2048 from SVG via `rsvg-convert` or design tool before GHL upload if SVG unsupported.  
- Example: `rsvg-convert -w 512 logo-mark-primary.svg -o logo-mark-primary.png`

---

## 7. Version

| Version | Date | Notes |
|---------|------|-------|
| 0.1 | 2026-07-16 | Initial draft kit for PHASE-A-01 |
