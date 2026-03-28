# PDF Export Guide — Quick Reference

Fast conversion of markdown reports to PDFs for client delivery.

---

## Quickest Method: Pandoc

### Install (One-time)
```bash
apt-get update && apt-get install -y pandoc wkhtmltopdf
```

### Convert Single File
```bash
cd ~/reports/performance-analysis
pandoc uncorked-canvas_2026-03-09_performance_report.md \
  -o uncorked-canvas_2026-03-09_performance_report.pdf \
  --pdf-engine=wkhtmltopdf
```

### Convert All Reports (Bulk)
```bash
cd ~
for file in reports/*/*.md; do
  pandoc "$file" -o "${file%.md}.pdf" --pdf-engine=wkhtmltopdf
done
```

### With Custom Styling
```bash
pandoc uncorked-canvas_performance_report.md \
  -o uncorked-canvas_performance_report.pdf \
  --pdf-engine=wkhtmltopdf \
  -V geometry:margin=1in \
  -V colorlinks=true \
  -V fontsize=11pt
```

---

## Alternative: VS Code + Extension (Easiest GUI)

1. **Install Extension:**
   - Open VS Code
   - Extensions → Search "Markdown Preview GitHub Styling"
   - Install

2. **Generate PDF:**
   - Open `.md` file
   - Right-click → "Open Preview"
   - Ctrl+P (or Cmd+P on Mac) → "Print"
   - Select "Save as PDF"
   - Choose location & save

---

## Alternative: Python + Weasyprint

### Install (One-time)
```bash
pip install weasyprint
```

### Quick Script
```python
from weasyprint import HTML
import sys

input_file = sys.argv[1]
output_file = input_file.replace('.md', '.pdf')

HTML(input_file).write_pdf(output_file)
print(f"✓ Converted: {output_file}")
```

### Save as `~/bin/md2pdf` and run:
```bash
chmod +x ~/bin/md2pdf
md2pdf reports/performance-analysis/uncorked-canvas_2026-03-09_performance_report.md
```

---

## One-Liner: Convert & Email Ready

```bash
pandoc reports/performance-analysis/uncorked-canvas_2026-03-09_performance_report.md \
  -o /tmp/uncorked-canvas_performance_report.pdf \
  --pdf-engine=wkhtmltopdf && \
echo "PDF ready: /tmp/uncorked-canvas_performance_report.pdf"
```

---

## Formatting Tips

### Markdown Best Practices for PDF

**Use consistent headers:**
```markdown
# Main Title (H1)
## Section (H2)
### Subsection (H3)
```

**Tables render cleanly:**
```markdown
| Column 1 | Column 2 |
|----------|----------|
| Data | Data |
```

**Code blocks stay readable:**
```markdown
\`\`\`json
{
  "key": "value"
}
\`\`\`
```

**Lists format properly:**
```markdown
- Item 1
- Item 2
  - Sub-item 2a
  - Sub-item 2b
```

**Avoid:**
- Emojis (may not render)
- Complex HTML (use markdown syntax instead)
- Inline CSS (use pandoc flags instead)

---

## Batch Conversion Commands

### Convert All Reports & Organize by Client

```bash
#!/bin/bash

for client in uncorked-canvas client-2 client-3; do
  echo "Processing $client..."
  for report in reports/*/${client}_*.md; do
    if [ -f "$report" ]; then
      pdf="${report%.md}.pdf"
      pandoc "$report" -o "$pdf" --pdf-engine=wkhtmltopdf
      echo "✓ $pdf"
    fi
  done
done
```

### Generate Monthly Bundle

```bash
MONTH=$(date +"%Y-%m")
BUNDLE="reports/archive/${MONTH}_all_reports.pdf"

pandoc reports/*/*.md \
  -o "$BUNDLE" \
  --pdf-engine=wkhtmltopdf \
  --toc \
  --number-sections

echo "Bundle created: $BUNDLE"
```

---

## Troubleshooting

### "wkhtmltopdf not found"
```bash
apt-get install wkhtmltopdf
# Or on Mac:
brew install --cask wkhtmltopdf
```

### "pandoc command not found"
```bash
apt-get install pandoc
# Or on Mac:
brew install pandoc
```

### PDF is blank or missing content
- Check markdown syntax (headers, tables)
- Try without custom flags first: `pandoc file.md -o file.pdf`
- Ensure the markdown file has actual content

### Tables look broken
- Use pipes `|` to separate columns
- Ensure header row has `---` separators
- Avoid merged cells (pandoc doesn't support)

---

## Recommended Workflow

```
1. Generate markdown report
   ↓
2. Review & finalize in markdown
   ↓
3. Convert to PDF: pandoc file.md -o file.pdf
   ↓
4. Check PDF formatting (open & review)
   ↓
5. Email to client
   ↓
6. Archive: mv file.pdf reports/archive/2026-03/
```

---

## File Size Tips

**Reduce PDF size:**
```bash
# Compress with ghostscript (if installed)
gs -sDEVICE=pdfwrite -dCompatibilityLevel=1.4 -dPDFSETTINGS=/ebook \
  -dNOPAUSE -dQUIET -dBATCH -sOutputFile=output_compressed.pdf input.pdf
```

---

## Quick Commands Reference

| Task | Command |
|------|---------|
| Single file | `pandoc file.md -o file.pdf --pdf-engine=wkhtmltopdf` |
| All MD files | `for f in *.md; do pandoc "$f" -o "${f%.md}.pdf"; done` |
| With TOC | `pandoc file.md -o file.pdf --toc` |
| Portrait + margins | `pandoc file.md -o file.pdf -V geometry:margin=1in` |
| Wide format | `pandoc file.md -o file.pdf -V geometry:paperwidth=11in` |
| Custom footer | Add `--include-before-body footer.html` |

---

_Updated: 2026-03-09_
