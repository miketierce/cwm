#!/usr/bin/env python3
"""
Convert WCFOMA markdown papers to rich PDF via HTML + Chromium.

Usage:
    python md2pdf.py paper/v11.md              # → paper/v11.pdf
    python md2pdf.py paper/v11.md -o out.pdf   # → out.pdf
    python md2pdf.py paper/v11.md --html-only  # → paper/v11.html (for debugging)
"""

import argparse
import re
import sys
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright

# ── CSS ──────────────────────────────────────────────────────────────────────

CSS = r"""
@page {
    size: letter;
    margin: 1in 1in 1in 1in;
}

:root {
    --text: #1a1a1a;
    --muted: #555;
    --accent: #2563eb;
    --border: #d1d5db;
    --bg-code: #f5f5f5;
    --bg-table-head: #f0f4f8;
}

* { box-sizing: border-box; }

body {
    font-family: "Palatino", "Palatino Linotype", "Georgia", serif;
    font-size: 11pt;
    line-height: 1.55;
    color: var(--text);
    max-width: 100%;
    margin: 0;
    padding: 0;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
}

/* ── Title & Author ─────────────────────────────────────── */
h1 {
    font-size: 18pt;
    font-weight: 700;
    text-align: center;
    margin: 0 0 6pt 0;
    line-height: 1.25;
    color: var(--text);
}

/* Author line right after title */
h1 + p {
    text-align: center;
    margin: 0 0 2pt 0;
}
h1 + p + p {
    text-align: center;
    font-style: italic;
    color: var(--muted);
    margin: 0 0 12pt 0;
}

/* ── Headings ────────────────────────────────────────────── */
h2 {
    font-size: 14pt;
    font-weight: 700;
    margin: 20pt 0 8pt 0;
    padding-bottom: 3pt;
    border-bottom: 1.5pt solid var(--accent);
    color: var(--text);
    page-break-after: avoid;
}

h3 {
    font-size: 12pt;
    font-weight: 700;
    margin: 14pt 0 6pt 0;
    color: var(--text);
    page-break-after: avoid;
}

h4 {
    font-size: 11pt;
    font-weight: 700;
    margin: 10pt 0 4pt 0;
    color: var(--muted);
}

/* ── Paragraphs ──────────────────────────────────────────── */
p {
    margin: 0 0 8pt 0;
    text-align: justify;
    hyphens: auto;
    orphans: 3;
    widows: 3;
}

/* ── Lists ───────────────────────────────────────────────── */
ul, ol {
    margin: 4pt 0 8pt 0;
    padding-left: 20pt;
}
li {
    margin-bottom: 3pt;
}
li > p { margin-bottom: 3pt; }

/* ── Tables ──────────────────────────────────────────────── */
table {
    border-collapse: collapse;
    width: 100%;
    margin: 10pt 0;
    font-size: 9.5pt;
    line-height: 1.35;
    page-break-inside: avoid;
}

thead th {
    background: var(--bg-table-head);
    border: 1pt solid var(--border);
    padding: 5pt 8pt;
    font-weight: 700;
    text-align: left;
    white-space: nowrap;
}

tbody td {
    border: 1pt solid var(--border);
    padding: 4pt 8pt;
    vertical-align: top;
}

tbody tr:nth-child(even) {
    background: #fafafa;
}

/* Bold cells in tables (for highlight rows) */
tbody td strong {
    color: var(--accent);
}

/* ── Horizontal Rules ────────────────────────────────────── */
hr {
    border: none;
    border-top: 1pt solid var(--border);
    margin: 16pt 0;
}

/* ── Code ────────────────────────────────────────────────── */
code {
    font-family: "SF Mono", "Menlo", "Monaco", "Consolas", monospace;
    font-size: 9pt;
    background: var(--bg-code);
    padding: 1pt 3pt;
    border-radius: 2pt;
}

pre {
    background: var(--bg-code);
    padding: 10pt 12pt;
    border-radius: 4pt;
    border: 1pt solid var(--border);
    overflow-x: auto;
    font-size: 8.5pt;
    line-height: 1.4;
    margin: 8pt 0;
    page-break-inside: avoid;
}

pre code {
    background: none;
    padding: 0;
}

/* ── Block quotes ────────────────────────────────────────── */
blockquote {
    margin: 8pt 0;
    padding: 6pt 12pt;
    border-left: 3pt solid var(--accent);
    background: #f8fafc;
    color: var(--muted);
}

/* ── Links / references ──────────────────────────────────── */
a {
    color: var(--accent);
    text-decoration: none;
}

/* ── Math (KaTeX) ────────────────────────────────────────── */
.katex-display {
    margin: 10pt 0;
    overflow-x: auto;
}

.katex {
    font-size: 1.05em;
}

/* ── Display math: prevent orphaned equations ────────────── */
.katex-display {
    page-break-inside: avoid;
    break-inside: avoid;
}

/* ── Inline thumbnail figures ─────────────────────────────── */
div.sem-thumb {
    text-align: center;
    margin: 12pt auto;
    page-break-inside: avoid;
}

div.sem-thumb img {
    max-width: 70%;
    height: auto;
    display: block;
    margin: 0 auto;
}

div.sem-thumb p {
    font-size: 8.5pt;
    color: var(--muted);
    text-align: center;
    max-width: 85%;
    margin: 6pt auto 0 auto;
    line-height: 1.35;
}

/* ── Landscape plate pages (end-of-doc gallery) ──────────── */
@page plate {
    size: letter landscape;
    margin: 0.5in;
}

div.plate-page {
    page: plate;
    page-break-before: always;
    page-break-after: always;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 100%;
    padding: 0;
}

div.plate-page img {
    max-width: 100%;
    max-height: 6.5in;
    width: auto;
    height: auto;
}

div.plate-page p {
    text-align: center;
    max-width: 90%;
    margin-top: 10pt;
    font-size: 9.5pt;
    line-height: 1.4;
}

/* ── Blank verso for duplex printing ─────────────────────── */
div.blank-verso {
    page-break-before: always;
    page-break-after: always;
    min-height: 1px;
    visibility: hidden;
}

/* ── Abstract special styling ────────────────────────────── */
h2#abstract + p,
h2:first-of-type + p {
    font-size: 10pt;
    line-height: 1.45;
    color: var(--muted);
}

/* ── Footnotes / References ──────────────────────────────── */
h2#references ~ p,
h2:last-of-type ~ p {
    font-size: 9pt;
    line-height: 1.35;
    hanging-punctuation: first;
    padding-left: 24pt;
    text-indent: -24pt;
}

/* ── Print tweaks ────────────────────────────────────────── */
h2, h3 {
    page-break-after: avoid;
}
table, pre, blockquote {
    page-break-inside: avoid;
}
"""


# ── HTML template ────────────────────────────────────────────────────────────

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<link rel="stylesheet"
      href="https://cdn.jsdelivr.net/npm/katex@0.16.21/dist/katex.min.css"
      crossorigin="anonymous">
<script defer
        src="https://cdn.jsdelivr.net/npm/katex@0.16.21/dist/katex.min.js"
        crossorigin="anonymous"></script>
<script defer
        src="https://cdn.jsdelivr.net/npm/katex@0.16.21/dist/contrib/auto-render.min.js"
        crossorigin="anonymous"></script>
<style>
{css}
</style>
</head>
<body>
{body}
<script>
document.addEventListener("DOMContentLoaded", function() {{
    renderMathInElement(document.body, {{
        delimiters: [
            {{left: "$$", right: "$$", display: true}},
            {{left: "$", right: "$", display: false}}
        ],
        throwOnError: false
    }});
}});
</script>
</body>
</html>
"""


def _protect_math(md_text: str):
    """Extract LaTeX math from markdown so the parser cannot mangle it.

    The markdown parser turns ``_x`` into ``<em>x</em>`` even inside
    ``$...$`` blocks, destroying LaTeX subscripts.  We swap every math
    span for an opaque placeholder, run markdown, then restore.
    """
    store = []

    def _stash(m):
        store.append(m.group(0))
        return f"\x00MATH{len(store) - 1}\x00"

    # Display math first (greedy across lines), then inline
    text = re.sub(r"\$\$(.+?)\$\$", _stash, md_text, flags=re.DOTALL)
    text = re.sub(r"(?<!\\)\$(?!\$)(.+?)(?<!\\)\$", _stash, text)
    return text, store


def _restore_math(html: str, store: list) -> str:
    """Put the real LaTeX back into the HTML."""
    for i, original in enumerate(store):
        html = html.replace(f"\x00MATH{i}\x00", original)
    return html


def convert_md_to_html(md_text: str) -> str:
    """Convert markdown text to HTML body string."""
    # Protect LaTeX from the markdown parser
    protected, math_store = _protect_math(md_text)

    # pymdown-extensions for better table, formatting support
    extensions = [
        "tables",
        "fenced_code",
        "codehilite",
        "toc",
        "smarty",
        "pymdownx.betterem",
        "pymdownx.superfences",
    ]
    extension_configs = {
        "codehilite": {"css_class": "highlight", "guess_lang": False},
        "toc": {"permalink": False},
    }

    md = markdown.Markdown(extensions=extensions, extension_configs=extension_configs)
    html = md.convert(protected)

    # Restore LaTeX
    html = _restore_math(html, math_store)
    return html


def extract_title(md_text: str) -> str:
    """Pull the first H1 as the document title."""
    m = re.search(r"^#\s+(.+)$", md_text, re.MULTILINE)
    return m.group(1) if m else "WCFOMA Paper"


def build_html(md_path: Path) -> str:
    """Read markdown file, return complete HTML string."""
    md_text = md_path.read_text(encoding="utf-8")
    title = extract_title(md_text)
    body = convert_md_to_html(md_text)
    html = HTML_TEMPLATE.format(title=title, css=CSS, body=body)
    # Convert relative image paths to absolute file:// URIs for Chromium
    base_dir = md_path.resolve().parent
    import urllib.parse
    def resolve_img(match):
        src = match.group(1)
        if src.startswith(("http://", "https://", "data:", "file://")):
            return match.group(0)
        abs_path = (base_dir / src).resolve()
        return match.group(0).replace(src, abs_path.as_uri())
    html = re.sub(r'<img[^>]+src="([^"]+)"', resolve_img, html)
    return html


def html_to_pdf(html: str, pdf_path: Path, md_path=None) -> None:
    """Render HTML to PDF using headless Chromium.

    Writes html to a temp file next to the markdown source so that
    file:// image references resolve correctly via page.goto().
    """
    import tempfile

    # Write HTML to a temp file in the same directory as the source
    # so relative file:// paths resolve correctly.
    base_dir = md_path.resolve().parent if md_path else Path.cwd()
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".html", dir=str(base_dir))
    try:
        with open(tmp_fd, "w", encoding="utf-8") as f:
            f.write(html)
        file_url = Path(tmp_path).as_uri()

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(file_url, wait_until="networkidle")
            # Give KaTeX a moment to render
            page.wait_for_timeout(2000)
            page.pdf(
                path=str(pdf_path),
                format="Letter",
                margin={"top": "0.75in", "right": "1in", "bottom": "0.75in", "left": "1in"},
                print_background=True,
                display_header_footer=True,
                header_template='<span style="font-size:1px;"></span>',
                footer_template=(
                    '<div style="font-size:9pt; color:#999; width:100%; text-align:center; margin:0; padding:0;">'
                    '<span class="pageNumber"></span>'
                    "</div>"
                ),
            )
            browser.close()
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Convert WCFOMA markdown to rich PDF")
    parser.add_argument("input", help="Path to .md file")
    parser.add_argument("-o", "--output", help="Output PDF path (default: same name as input)")
    parser.add_argument("--html-only", action="store_true", help="Write HTML file only (for debugging)")
    args = parser.parse_args()

    md_path = Path(args.input)
    if not md_path.exists():
        print(f"Error: {md_path} not found", file=sys.stderr)
        sys.exit(1)

    html = build_html(md_path)

    if args.html_only:
        html_path = md_path.with_suffix(".html")
        html_path.write_text(html, encoding="utf-8")
        print(f"HTML written to {html_path}")
        return

    pdf_path = Path(args.output) if args.output else md_path.with_suffix(".pdf")

    # Also save the HTML for reference
    html_path = md_path.with_suffix(".html")
    html_path.write_text(html, encoding="utf-8")
    print(f"HTML written to {html_path}")

    print(f"Rendering PDF (this takes a few seconds)...")
    html_to_pdf(html, pdf_path, md_path=md_path)
    print(f"PDF written to {pdf_path}")


if __name__ == "__main__":
    main()
