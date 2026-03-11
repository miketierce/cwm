#!/usr/bin/env python3
"""
Convert WCFOMA markdown papers to a traditional 2-column academic PDF.

This is the "Version B" converter — it produces a compact, journal-style
layout modelled on IEEE / APS / Nature conventions:

  - Letter-size pages with narrow margins
  - 2-column body text (CSS columns)
  - Single-column title block with centred author info
  - Single-column abstract with "Abstract—" bold prefix
  - Section headings span the full width or sit inside columns
  - Figures and wide tables can span both columns
  - Compact typography: 9 pt body, 8 pt references
  - No Part divider pages, no illustration plates, no blank versos
  - Continuous page numbering (no recto enforcement)

The existing md2pdf.py (Version A — book layout) is unmodified.

Usage:
    python md2pdf_2col.py paper/v15.md                   # -> paper/v15_2col.pdf
    python md2pdf_2col.py paper/v15.md -o journal.pdf    # -> journal.pdf
    python md2pdf_2col.py paper/v15.md --html-only       # -> paper/v15_2col.html
"""

import argparse
import re
import sys
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# CSS — 2-column academic journal layout
# ---------------------------------------------------------------------------

CSS_2COL = r"""
/* ===== Page geometry ===== */
@page {
    size: letter;
    margin: 0.65in 0.6in 0.75in 0.6in;
}

:root {
    --text: #1a1a1a;
    --muted: #444;
    --accent: #1a3c7a;
    --border: #bbb;
    --bg-code: #f4f4f4;
    --bg-table-head: #e8ecf1;
    --col-gap: 0.28in;
}

* { box-sizing: border-box; }

body {
    font-family: "Times New Roman", "Times", "Nimbus Roman", serif;
    font-size: 9pt;
    line-height: 1.38;
    color: var(--text);
    margin: 0;
    padding: 0;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
}

/* ===== Title block — full width, single column ===== */
.paper-header {
    text-align: center;
    margin-bottom: 14pt;
    padding-bottom: 8pt;
    border-bottom: 0.5pt solid var(--border);
}

.paper-header .paper-title {
    font-size: 17pt;
    font-weight: 700;
    line-height: 1.2;
    margin: 0 0 8pt 0;
    color: var(--text);
    display: block !important;
}

.paper-header .author-name {
    font-size: 11pt;
    font-weight: 400;
    margin: 0 0 2pt 0;
}

.paper-header .author-affil {
    font-size: 9pt;
    font-style: italic;
    color: var(--muted);
    margin: 0 0 2pt 0;
}

.paper-header .author-ids {
    font-size: 8pt;
    color: var(--muted);
    margin: 0;
}

.paper-header .author-ids a {
    color: var(--accent);
    text-decoration: none;
}

/* ===== Abstract — full width, indented, italic prefix ===== */
.abstract-block {
    margin: 0 0.3in 12pt 0.3in;
    font-size: 8.5pt;
    line-height: 1.35;
    text-align: justify;
}

.abstract-block .abstract-label {
    font-weight: 700;
    font-style: italic;
}

/* ===== Two-column body ===== */
.two-col {
    column-count: 2;
    column-gap: var(--col-gap);
    column-rule: 0.25pt solid #ddd;
}

/* ===== Section headings ===== */
/* h1 is hidden (title is in the header) */
h1 { display: none; }

/* Major sections (## N. Title) — span both columns */
h2 {
    column-span: all;
    font-size: 10pt;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.3pt;
    margin: 14pt 0 6pt 0;
    padding-bottom: 2pt;
    border-bottom: 0.5pt solid var(--accent);
    color: var(--text);
    page-break-after: avoid;
}

/* Subsections (### N.N Title) — inside column */
h3 {
    font-size: 9.5pt;
    font-weight: 700;
    font-style: italic;
    margin: 10pt 0 4pt 0;
    color: var(--text);
    page-break-after: avoid;
}

h4 {
    font-size: 9pt;
    font-weight: 700;
    margin: 8pt 0 3pt 0;
    color: var(--muted);
    page-break-after: avoid;
}

/* ===== Body text ===== */
p {
    margin: 0 0 6pt 0;
    text-align: justify;
    hyphens: auto;
    orphans: 2;
    widows: 2;
}

ul, ol {
    margin: 3pt 0 6pt 0;
    padding-left: 14pt;
}
li { margin-bottom: 2pt; }
li > p { margin-bottom: 2pt; }

/* ===== Tables ===== */
table {
    border-collapse: collapse;
    width: 100%;
    margin: 8pt 0;
    font-size: 8pt;
    line-height: 1.25;
    break-inside: avoid;
}

thead th {
    background: var(--bg-table-head);
    border-top: 1pt solid var(--text);
    border-bottom: 1pt solid var(--text);
    padding: 3pt 4pt;
    font-weight: 700;
    text-align: left;
    font-size: 7.5pt;
}

tbody td {
    border-bottom: 0.25pt solid #ddd;
    padding: 2.5pt 4pt;
    vertical-align: top;
}

/* Bottom rule on last row */
tbody tr:last-child td {
    border-bottom: 1pt solid var(--text);
}

tbody td strong {
    color: var(--accent);
}

/* Wide tables that must span both columns */
.wide-table {
    column-span: all;
}

/* ===== Horizontal rules ===== */
hr {
    border: none;
    border-top: 0.25pt solid #ccc;
    margin: 8pt 0;
}

/* ===== Code ===== */
code {
    font-family: "SF Mono", "Menlo", "Consolas", monospace;
    font-size: 7.5pt;
    background: var(--bg-code);
    padding: 0.5pt 2pt;
    border-radius: 1.5pt;
}

pre {
    background: var(--bg-code);
    padding: 6pt 8pt;
    border-radius: 2pt;
    border: 0.25pt solid var(--border);
    overflow-x: auto;
    font-size: 7pt;
    line-height: 1.3;
    margin: 6pt 0;
    break-inside: avoid;
}

pre code {
    background: none;
    padding: 0;
}

/* ===== Block quotes ===== */
blockquote {
    margin: 6pt 0;
    padding: 4pt 8pt;
    border-left: 2pt solid var(--accent);
    background: #f5f7fa;
    color: var(--muted);
    font-size: 8.5pt;
}

blockquote p {
    font-size: 8.5pt;
}

/* ===== Links ===== */
a {
    color: var(--accent);
    text-decoration: none;
}

/* ===== Math (KaTeX) ===== */
.katex-display {
    margin: 8pt 0;
    overflow-x: auto;
    break-inside: avoid;
}

.katex {
    font-size: 1.0em;
}

/* ===== Figures — full width when inside plate-page, else in-column ===== */
div.sem-thumb {
    text-align: center;
    margin: 8pt auto;
    break-inside: avoid;
}

div.sem-thumb img {
    max-width: 100%;
    height: auto;
    display: block;
    margin: 0 auto;
}

div.sem-thumb p {
    font-size: 7.5pt;
    color: var(--muted);
    text-align: justify;
    margin: 4pt 0 0 0;
    line-height: 1.25;
}

/* Plate-page images: span full width, portrait orientation */
div.plate-page {
    column-span: all;
    text-align: center;
    margin: 10pt 0;
    break-inside: avoid;
    page-break-inside: avoid;
}

div.plate-page img {
    max-width: 100%;
    max-height: 4.5in;
    width: auto;
    height: auto;
}

div.plate-page p {
    font-size: 7.5pt;
    color: var(--muted);
    text-align: justify;
    max-width: 100%;
    margin: 4pt auto 0 auto;
    line-height: 1.25;
}

/* Hide blank-verso pages entirely in 2-col layout */
.blank-verso {
    display: none;
}

/* ===== Worksheet plates — span both columns ===== */
div.worksheet-plate {
    column-span: all;
    page-break-before: always;
    padding-top: 0.15in;
}

div.worksheet-plate h4 {
    text-align: center;
    font-size: 10pt;
    font-weight: 700;
    margin-bottom: 8pt;
    padding-bottom: 3pt;
    border-bottom: 0.5pt solid var(--border);
    text-transform: none;
    font-style: normal;
}

div.worksheet-plate p.ws-inst {
    font-size: 8pt;
    color: var(--muted);
    text-align: center;
    margin-bottom: 6pt;
    font-style: italic;
}

div.worksheet-plate table {
    font-size: 8.5pt;
}

/* ===== Handwritten example entries (blue pen) ===== */
.ex {
    font-family: "Caveat", "Bradley Hand", "Marker Felt", cursive;
    color: #1a5fb4;
    font-size: 9.5pt;
    font-weight: 600;
    font-style: normal;
}

/* ===== References ===== */
h2#references ~ p,
h2:last-of-type ~ p {
    font-size: 7.5pt;
    line-height: 1.25;
    padding-left: 16pt;
    text-indent: -16pt;
}

/* ===== Print tweaks ===== */
h2, h3, h4 {
    page-break-after: avoid;
}
table, pre, blockquote {
    break-inside: avoid;
}

/* ===== Colophon ===== */
.colophon-2col {
    column-span: all;
    text-align: center;
    color: var(--muted);
    font-size: 7.5pt;
    line-height: 1.5;
    margin-top: 16pt;
    padding-top: 8pt;
    border-top: 0.5pt solid var(--border);
}

.colophon-2col p {
    text-align: center;
    font-size: 7.5pt;
}

/* ===== Part headings — converted to in-flow banners ===== */
.part-banner {
    column-span: all;
    text-align: center;
    padding: 10pt 0 6pt 0;
    margin: 14pt 0 4pt 0;
    border-top: 1.5pt solid var(--accent);
    border-bottom: 0.5pt solid var(--border);
}

.part-banner .part-label {
    font-size: 8pt;
    font-weight: 700;
    letter-spacing: 1pt;
    text-transform: uppercase;
    color: var(--accent);
    margin: 0 0 2pt 0;
}

.part-banner .part-title {
    font-size: 11pt;
    font-weight: 700;
    color: var(--text);
    margin: 0;
}
"""

# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

HTML_TEMPLATE_2COL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Caveat:wght@400;600;700&display=swap"
      rel="stylesheet">
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

# ---------------------------------------------------------------------------
# Metadata extraction  (identical to md2pdf.py)
# ---------------------------------------------------------------------------

def extract_front_matter(md_text):
    """Pull title, author, affiliation, ORCID, repo, version."""
    info = {}
    m = re.search(r"^#\s+(.+)$", md_text, re.MULTILINE)
    info["title"] = m.group(1).strip() if m else "WCFOMA Paper"

    m = re.search(r"^\*\*(.+?)\*\*\s*$", md_text, re.MULTILINE)
    info["author"] = m.group(1).strip() if m else ""

    m = re.search(r"^_(.+?)_\s*$", md_text, re.MULTILINE)
    info["affiliation"] = m.group(1).strip() if m else ""

    m = re.search(r"ORCID:\s*\[([^\]]+)\]\(([^)]+)\)", md_text)
    if m:
        info["orcid_id"] = m.group(1).strip()
        info["orcid_url"] = m.group(2).strip()
    else:
        info["orcid_id"] = info["orcid_url"] = ""

    m = re.search(r"Repository:\s*\[([^\]]+)\]\(([^)]+)\)", md_text)
    if m:
        info["repo_text"] = m.group(1).strip()
        info["repo_url"] = m.group(2).strip()
    else:
        info["repo_text"] = info["repo_url"] = ""

    m = re.search(r"^\*\*Version\s+(.+?)\*\*\s*$", md_text, re.MULTILINE)
    info["version"] = m.group(1).strip() if m else ""

    return info


# ---------------------------------------------------------------------------
# Title block — single-column header (IEEE / APS style)
# ---------------------------------------------------------------------------

def build_header(info):
    """Build the single-column paper header with title + author block."""
    orcid = ""
    if info.get("orcid_id"):
        orcid = ('ORCID: <a href="' + info["orcid_url"] + '">'
                 + info["orcid_id"] + "</a>")
    repo = ""
    if info.get("repo_text"):
        url = info["repo_url"]
        if not url.startswith("http"):
            url = "https://" + url
        repo = '<a href="' + url + '">' + info["repo_text"] + "</a>"

    ids_parts = [x for x in [orcid, repo] if x]
    ids_line = " &nbsp;|&nbsp; ".join(ids_parts)

    return (
        '<div class="paper-header">\n'
        '  <h1 class="paper-title" style="display:block">'
        + info["title"] + "</h1>\n"
        '  <p class="author-name">' + info["author"] + "</p>\n"
        '  <p class="author-affil">' + info["affiliation"] + "</p>\n"
        '  <p class="author-ids">' + ids_line
        + " &nbsp;|&nbsp; Version " + info["version"] + "</p>\n"
        "</div>\n"
    )


# ---------------------------------------------------------------------------
# Abstract — full-width, italic prefix
# ---------------------------------------------------------------------------

def extract_abstract_md(md_text):
    """Pull the raw abstract paragraph(s) from the markdown source."""
    m = re.search(
        r"^## Abstract\s*\n(.*?)(?=\n##\s)",
        md_text, re.MULTILINE | re.DOTALL,
    )
    if m:
        return m.group(1).strip()
    return ""


# ---------------------------------------------------------------------------
# Markdown → HTML conversion  (shared logic with md2pdf.py)
# ---------------------------------------------------------------------------

def _protect_math(md_text):
    store = []
    def _stash(m):
        store.append(m.group(0))
        return "\x00MATH" + str(len(store) - 1) + "\x00"

    text = re.sub(r"\$\$(.+?)\$\$", _stash, md_text, flags=re.DOTALL)
    text = re.sub(r"(?<!\\)\$(?!\$)(.+?)(?<!\\)\$", _stash, text)
    text = text.replace("\\$", "&#36;")
    return text, store


def _restore_math(html, store):
    for i, original in enumerate(store):
        html = html.replace("\x00MATH" + str(i) + "\x00", original)
    return html


def strip_front_matter(md_text):
    """Remove everything before the first ## heading (Abstract)."""
    m = re.search(r"^(## Abstract)", md_text, re.MULTILINE)
    if m:
        return md_text[m.start():]
    m = re.search(r"^(## )", md_text, re.MULTILINE)
    if m:
        return md_text[m.start():]
    return md_text


def strip_toc_block(md_text):
    """Remove the ## Table of Contents block (we skip it in journal mode)."""
    return re.sub(
        r"^## Table of Contents\s*\n.*?(?=\n## )",
        "",
        md_text,
        count=1,
        flags=re.MULTILINE | re.DOTALL,
    )


def strip_illustration_plates_section(md_text):
    """Remove the Illustration Plates + Printable Worksheets back-matter."""
    # Everything from "## Illustration Plates" to end-of-string is plates
    m = re.search(r"^## Illustration Plates", md_text, re.MULTILINE)
    if m:
        return md_text[:m.start()].rstrip() + "\n"
    return md_text


def strip_printable_worksheets_section(md_text):
    """Remove the Printable Worksheets section (blank worksheet plates)."""
    m = re.search(r"^## Printable Worksheets", md_text, re.MULTILINE)
    if m:
        return md_text[:m.start()].rstrip() + "\n"
    return md_text


def convert_md_to_html(md_text):
    protected, math_store = _protect_math(md_text)

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

    md = markdown.Markdown(
        extensions=extensions, extension_configs=extension_configs
    )
    html = md.convert(protected)
    html = _restore_math(html, math_store)
    return html


# ---------------------------------------------------------------------------
# Part definitions — converted to inline banners (no page breaks)
# ---------------------------------------------------------------------------

PARTS = [
    {"label": "Part I",   "title": "Theory and Architecture",   "before_section": 1},
    {"label": "Part II",  "title": "Substrate and Prototype",   "before_section": 3},
    {"label": "Part III", "title": "Finite Element Validation",  "before_section": 5},
    {"label": "Part IV",  "title": "MEMS Design and Scaling",   "before_section": 6},
    {"label": "Part V",   "title": "Advanced Techniques",       "before_section": 10},
    {"label": "Part VI",  "title": "Outlook",                   "before_section": 13},
]


def _build_part_banner(part):
    return (
        '<div class="part-banner">\n'
        '  <p class="part-label">' + part["label"] + "</p>\n"
        '  <p class="part-title">' + part["title"] + "</p>\n"
        "</div>\n"
    )


def inject_part_banners(html):
    """Insert compact Part banners before the appropriate section headings."""
    for part in reversed(PARTS):
        sec_num = part["before_section"]
        pattern = re.compile(
            r'(<h2\s[^>]*>)\s*' + str(sec_num) + r'\.\s',
            re.IGNORECASE,
        )
        m = pattern.search(html)
        if m:
            banner = _build_part_banner(part)
            html = html[:m.start()] + banner + html[m.start():]
    return html


# ---------------------------------------------------------------------------
# Post-processing
# ---------------------------------------------------------------------------

def wrap_abstract_2col(html):
    """Replace the rendered Abstract <h2> + <p> with a styled block."""
    # Find the Abstract heading and capture the already-rendered HTML body
    pattern = re.compile(
        r'<h2[^>]*id="abstract"[^>]*>Abstract</h2>\s*(.*?)(?=<h2|<div class="part-banner")',
        re.DOTALL | re.IGNORECASE,
    )
    m = pattern.search(html)
    if not m:
        return html

    # Use the already-converted HTML content (bold, italic, math all intact)
    rendered_body = m.group(1).strip()

    # Build the replacement abstract block
    abstract_html = (
        '<div class="abstract-block">\n'
        '  <span class="abstract-label">Abstract&mdash;</span> '
        + rendered_body + "\n"
        "</div>\n"
    )

    # Replace the matched region with our styled block
    html = html[:m.start()] + abstract_html + html[m.end():]
    return html


def build_colophon_2col(info):
    return (
        '<div class="colophon-2col">\n'
        "  <p><em>Spectral Eigenmode Memory</em> &mdash; Version "
        + info["version"]
        + " &mdash; &copy; "
        + info["author"]
        + "<br>\n"
        "  Typeset from Markdown source. Mathematics by KaTeX. "
        "All claims from first-principles simulation (30 modules, "
        "749 tests).</p>\n"
        "</div>\n"
    )


# ---------------------------------------------------------------------------
# Master assembly
# ---------------------------------------------------------------------------

def build_html(md_path):
    md_text = md_path.read_text(encoding="utf-8")

    # 1. Extract metadata
    info = extract_front_matter(md_text)

    # 2. Build header
    header_html = build_header(info)

    # 4. Prepare body markdown: strip front matter, ToC, plates, worksheets
    body_md = strip_front_matter(md_text)
    body_md = strip_toc_block(body_md)
    body_md = strip_printable_worksheets_section(body_md)
    body_md = strip_illustration_plates_section(body_md)

    # 5. Convert to HTML
    body_html = convert_md_to_html(body_md)

    # 6. Inject Part banners (compact, no page breaks)
    body_html = inject_part_banners(body_html)

    # 7. Style the abstract
    body_html = wrap_abstract_2col(body_html)

    # 8. Colophon
    colophon = build_colophon_2col(info)

    # 9. Wrap body in 2-column container
    full_body = (
        header_html
        + '<div class="two-col">\n'
        + body_html
        + colophon
        + "</div>\n"
    )

    # 10. Assemble HTML document
    html = HTML_TEMPLATE_2COL.format(
        title=info["title"],
        css=CSS_2COL,
        body=full_body,
    )

    # 11. Resolve image paths
    base_dir = md_path.resolve().parent

    def resolve_img(match):
        src = match.group(1)
        if src.startswith(("http://", "https://", "data:", "file://")):
            return match.group(0)
        abs_path = (base_dir / src).resolve()
        return match.group(0).replace(src, abs_path.as_uri())

    html = re.sub(r'<img[^>]+src="([^"]+)"', resolve_img, html)

    return html


# ---------------------------------------------------------------------------
# PDF rendering
# ---------------------------------------------------------------------------

def html_to_pdf(html, pdf_path, md_path=None):
    """Render HTML to PDF using headless Chromium."""
    import tempfile

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
            page.wait_for_timeout(2500)
            page.pdf(
                path=str(pdf_path),
                format="Letter",
                margin={
                    "top": "0.65in",
                    "right": "0.6in",
                    "bottom": "0.75in",
                    "left": "0.6in",
                },
                print_background=True,
                display_header_footer=True,
                header_template=(
                    '<span style="font-size:1px;color:transparent;">.</span>'
                ),
                footer_template=(
                    '<div style="font-size: 7.5pt; color: #999; width: 100%;'
                    " padding: 0 0.6in;"
                    ' display: flex; justify-content: space-between;">'
                    "<span>SEM — Tierce 2026</span>"
                    '<span class="pageNumber"></span>'
                    "</div>"
                ),
            )
            browser.close()
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Convert WCFOMA markdown to 2-column academic PDF (Version B)"
    )
    parser.add_argument("input", help="Path to .md file")
    parser.add_argument(
        "-o", "--output",
        help="Output PDF path (default: <input>_2col.pdf)",
    )
    parser.add_argument(
        "--html-only",
        action="store_true",
        help="Write HTML file only (for debugging)",
    )
    args = parser.parse_args()

    md_path = Path(args.input)
    if not md_path.exists():
        print(f"Error: {md_path} not found", file=sys.stderr)
        sys.exit(1)

    print("Building 2-column HTML...")
    html = build_html(md_path)

    stem = md_path.stem + "_2col"

    if args.html_only:
        html_path = md_path.with_stem(stem).with_suffix(".html")
        html_path.write_text(html, encoding="utf-8")
        print(f"HTML written to {html_path}")
        return

    pdf_path = Path(args.output) if args.output else md_path.with_stem(stem).with_suffix(".pdf")

    # Also save the HTML for debugging
    html_path = md_path.with_stem(stem).with_suffix(".html")
    html_path.write_text(html, encoding="utf-8")
    print(f"HTML written to {html_path}")

    print("Rendering PDF (this takes a few seconds)...")
    html_to_pdf(html, pdf_path, md_path=md_path)
    print(f"PDF written to {pdf_path}")

    # Report page count (macOS)
    try:
        import subprocess
        result = subprocess.run(
            ["mdls", "-name", "kMDItemNumberOfPages", str(pdf_path)],
            capture_output=True, text=True,
        )
        for line in result.stdout.strip().split("\n"):
            if "kMDItemNumberOfPages" in line:
                pages = line.split("=")[1].strip()
                print(f"Pages: {pages}")
    except Exception:
        pass


if __name__ == "__main__":
    main()
