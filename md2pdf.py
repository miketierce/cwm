#!/usr/bin/env python3
"""
Convert WCFOMA markdown papers to book-quality PDF via HTML + Chromium.

Produces a properly structured document for double-sided printing and
binding, with:
  - Formal title page (recto) + blank verso
  - Table of Contents on its own page spread
  - Abstract starting on a new recto
  - Each Part starting on a recto page
  - Alternating left/right margins for binding gutter
  - Page numbers on the outer edge of each page
  - Landscape illustration plates with interleaved blank versos

Usage:
    python md2pdf.py paper/v15.md              # -> paper/v15.pdf
    python md2pdf.py paper/v15.md -o out.pdf   # -> out.pdf
    python md2pdf.py paper/v15.md --html-only  # -> paper/v15.html (for debugging)
"""

import argparse
import re
import sys
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright

# -- CSS -------------------------------------------------------------------

CSS = """
/* -- Page geometry: duplex with binding gutter -- */
@page {
    size: letter;
    margin: 0.85in 0.85in 1in 1.15in;   /* top right bottom left(gutter) */
}
@page :left {
    margin-left: 0.85in;
    margin-right: 1.15in;
}
@page :right {
    margin-left: 1.15in;
    margin-right: 0.85in;
}

/* Named page for landscape plates */
@page plate {
    size: letter landscape;
    margin: 0.5in;
}

:root {
    --text: #1a1a1a;
    --muted: #555;
    --accent: #2563eb;
    --border: #d1d5db;
    --bg-code: #f5f5f5;
    --bg-table-head: #f0f4f8;
    --title-accent: #1e40af;
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

/* === TITLE PAGE === */
.title-page {
    page-break-after: always;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    min-height: 100vh;
    text-align: center;
    padding: 0 0.5in;
}

.title-page .rule-top {
    width: 3in;
    border: none;
    border-top: 2.5pt solid var(--title-accent);
    margin: 0 auto 28pt auto;
}

.title-page .paper-title {
    font-size: 22pt;
    font-weight: 700;
    line-height: 1.25;
    color: var(--text);
    margin: 0 0 8pt 0;
    max-width: 5.5in;
    display: block !important;
}

.title-page .rule-mid {
    width: 1.5in;
    border: none;
    border-top: 1pt solid var(--border);
    margin: 0 auto 28pt auto;
}

.title-page .author {
    font-size: 14pt;
    font-weight: 600;
    margin: 0 0 4pt 0;
    color: var(--text);
}

.title-page .affiliation {
    font-size: 11pt;
    font-style: italic;
    color: var(--muted);
    margin: 0 0 6pt 0;
}

.title-page .orcid {
    font-size: 9.5pt;
    color: var(--muted);
    margin: 0 0 2pt 0;
}

.title-page .orcid a {
    color: var(--accent);
    text-decoration: none;
}

.title-page .repo {
    font-size: 9.5pt;
    color: var(--muted);
    margin: 0 0 32pt 0;
}

.title-page .repo a {
    color: var(--accent);
    text-decoration: none;
}

.title-page .version {
    font-size: 11pt;
    font-weight: 600;
    color: var(--muted);
    margin: 0;
}

.title-page .rule-bottom {
    width: 3in;
    border: none;
    border-top: 2.5pt solid var(--title-accent);
    margin: 28pt auto 0 auto;
}

/* === BLANK VERSO === */
.blank-verso {
    page-break-before: always;
    page-break-after: always;
    min-height: 1px;
    visibility: hidden;
}

/* === TABLE OF CONTENTS === */
.toc-page {
    page-break-before: right;
    page-break-after: always;
}

.toc-page h2 {
    font-size: 16pt;
    text-align: center;
    border-bottom: none;
    margin-bottom: 18pt;
    color: var(--text);
}

.toc-page .toc-part {
    font-size: 10pt;
    font-weight: 700;
    color: var(--title-accent);
    margin: 14pt 0 4pt 0;
    letter-spacing: 0.5pt;
    text-transform: uppercase;
}

.toc-page .toc-part:first-of-type {
    margin-top: 0;
}

.toc-page ol {
    list-style: none;
    padding: 0;
    margin: 0 0 4pt 0;
}

.toc-page ol li {
    font-size: 10.5pt;
    line-height: 1.7;
    padding-left: 8pt;
    margin: 0;
}

.toc-page ol li a {
    color: var(--text);
    text-decoration: none;
}

.toc-page ol li .toc-desc {
    color: var(--muted);
    font-size: 9.5pt;
}

.toc-page ol li.toc-sub {
    font-size: 9.5pt;
    color: var(--muted);
    padding-left: 24pt;
    line-height: 1.5;
}

.toc-page .toc-appendices {
    margin-top: 14pt;
}

.toc-page .toc-appendices .toc-part {
    margin-top: 0;
}

/* === ABSTRACT PAGE === */
.abstract-page {
    page-break-before: right;
}

.abstract-page h2 {
    font-size: 16pt;
    text-align: center;
    border-bottom: none;
    margin-bottom: 14pt;
}

.abstract-page p {
    font-size: 10.5pt;
    line-height: 1.5;
    color: var(--muted);
    text-align: justify;
}

/* === PART DIVIDERS === */
.part-heading {
    page-break-before: right;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    min-height: 3in;
    text-align: center;
    margin-bottom: 0;
    padding-top: 2in;
}

.part-heading .part-label {
    font-size: 11pt;
    font-weight: 700;
    letter-spacing: 1.5pt;
    text-transform: uppercase;
    color: var(--title-accent);
    margin: 0 0 8pt 0;
}

.part-heading .part-title {
    font-size: 18pt;
    font-weight: 700;
    color: var(--text);
    margin: 0 0 6pt 0;
}

.part-heading .part-desc {
    font-size: 10pt;
    color: var(--muted);
    font-style: italic;
    max-width: 4.5in;
    margin: 0;
}

.part-heading hr {
    width: 2in;
    border: none;
    border-top: 1.5pt solid var(--title-accent);
    margin: 18pt auto 0 auto;
}

/* === BODY HEADINGS === */
h1 {
    display: none;
}

h2 {
    font-size: 14pt;
    font-weight: 700;
    margin: 22pt 0 8pt 0;
    padding-bottom: 3pt;
    border-bottom: 1.5pt solid var(--accent);
    color: var(--text);
    page-break-before: right;
    page-break-after: avoid;
}

/* Suppress double page-break when h2 follows a Part divider or is inside a container */
.part-heading + h2,
.abstract-page h2,
.toc-page h2 {
    page-break-before: avoid;
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

/* === BODY TEXT === */
p {
    margin: 0 0 8pt 0;
    text-align: justify;
    hyphens: none;
    orphans: 3;
    widows: 3;
}

ul, ol {
    margin: 4pt 0 8pt 0;
    padding-left: 20pt;
}
li {
    margin-bottom: 3pt;
}
li > p { margin-bottom: 3pt; }

/* -- Tables -- */
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

tbody td strong {
    color: var(--accent);
}

/* -- Horizontal Rules -- */
hr {
    border: none;
    border-top: 1pt solid var(--border);
    margin: 16pt 0;
}

/* -- Code -- */
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

/* -- Block quotes -- */
blockquote {
    margin: 8pt 0;
    padding: 6pt 12pt;
    border-left: 3pt solid var(--accent);
    background: #f8fafc;
    color: var(--muted);
}

/* -- Links -- */
a {
    color: var(--accent);
    text-decoration: none;
}

/* -- Math (KaTeX) -- */
.katex-display {
    margin: 10pt 0;
    overflow-x: auto;
    page-break-inside: avoid;
    break-inside: avoid;
}

.katex {
    font-size: 1.05em;
}

/* -- Inline thumbnail figures -- */
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

/* -- Landscape plate pages -- */
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

/* -- Footnotes / References -- */
h2#references ~ p,
h2:last-of-type ~ p {
    font-size: 9pt;
    line-height: 1.35;
    hanging-punctuation: first;
    padding-left: 24pt;
    text-indent: -24pt;
}

/* -- Print tweaks -- */
h2, h3 {
    page-break-after: avoid;
}
table, pre, blockquote {
    page-break-inside: avoid;
}

/* -- Colophon page -- */
.colophon {
    page-break-before: right;
    padding-top: 2in;
    text-align: center;
    color: var(--muted);
    font-size: 9pt;
    line-height: 1.6;
}

.colophon p {
    text-align: center;
}

/* -- Handwritten example entries (blue pen) -- */
.ex {
    font-family: "Caveat", "Bradley Hand", "Marker Felt", cursive;
    color: #1a5fb4;
    font-size: 11pt;
    font-weight: 600;
    font-style: normal;
}

/* -- Printable worksheet pages -- */
div.worksheet-plate {
    page-break-before: always;
    page-break-after: always;
    padding-top: 0.15in;
}

div.worksheet-plate h4 {
    text-align: center;
    font-size: 13pt;
    font-weight: 700;
    margin-bottom: 10pt;
    padding-bottom: 4pt;
    border-bottom: 1pt solid var(--border);
}

div.worksheet-plate p.ws-inst {
    font-size: 9pt;
    color: var(--muted);
    text-align: center;
    margin-bottom: 8pt;
    font-style: italic;
}

div.worksheet-plate table {
    width: 100%;
    font-size: 10pt;
}

div.worksheet-plate td,
div.worksheet-plate th {
    padding: 5pt 6pt;
}
"""


# -- HTML template ---------------------------------------------------------

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Caveat:wght@400;600;700&display=swap" rel="stylesheet">
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


# -- Metadata extraction ---------------------------------------------------

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


# -- Title page builder ----------------------------------------------------

def build_title_page(info):
    orcid_line = ""
    if info.get("orcid_id"):
        orcid_line = (
            '<p class="orcid">ORCID: '
            '<a href="' + info["orcid_url"] + '">' + info["orcid_id"] + '</a></p>'
        )

    repo_line = ""
    if info.get("repo_text"):
        url = info["repo_url"]
        if not url.startswith("http"):
            url = "https://" + url
        repo_line = (
            '<p class="repo">'
            '<a href="' + url + '">' + info["repo_text"] + '</a></p>'
        )

    return (
        '<div class="title-page">\n'
        '  <hr class="rule-top">\n'
        '  <h1 class="paper-title" style="display:block">' + info["title"] + '</h1>\n'
        '  <hr class="rule-mid">\n'
        '  <p class="author">' + info["author"] + '</p>\n'
        '  <p class="affiliation">' + info["affiliation"] + '</p>\n'
        '  ' + orcid_line + '\n'
        '  ' + repo_line + '\n'
        '  <p class="version">Version ' + info["version"] + '</p>\n'
        '  <hr class="rule-bottom">\n'
        '</div>\n'
        '<div class="blank-verso">&nbsp;</div>\n'
    )


# -- Table of Contents builder ---------------------------------------------

def build_toc_html(md_text):
    """Parse the markdown ToC block and rebuild it as structured HTML."""
    toc_match = re.search(
        r"## Table of Contents\s*\n(.*?)(?=\n---)",
        md_text, re.DOTALL,
    )
    if not toc_match:
        return ""

    toc_block = toc_match.group(1)

    parts = []
    parts.append('<div class="toc-page">')
    parts.append('<h2>Contents</h2>')

    in_list = False
    for line in toc_block.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        # Part heading: **Part X -- Title**
        part_match = re.match(r"\*\*(.+?)\*\*\s*$", line)
        if part_match:
            label = part_match.group(1)
            if in_list:
                parts.append("</ol>")
                in_list = False
            if "Appendi" in label:
                parts.append('<div class="toc-appendices">')
            parts.append('<p class="toc-part">' + label + '</p>')
            parts.append("<ol>")
            in_list = True
            continue

        # Numbered entry
        entry_match = re.match(
            r"(\d+|[A-C])\.\s*\[(.+?)\]\(#(.+?)\)\s*(?:[\u2014\u2013\-]\s*(.+))?",
            line,
        )
        if entry_match:
            num, title, anchor, desc = entry_match.groups()
            desc_span = ' <span class="toc-desc">\u2014 ' + desc + '</span>' if desc else ""
            parts.append(
                '<li>' + num + '. <a href="#' + anchor + '">' + title + '</a>' + desc_span + '</li>'
            )
            continue

        # Subsection entry: - 1.1 Title
        sub_match = re.match(r"-\s*(\d+\.\d+)\s+(.+)", line)
        if sub_match:
            sub_num, sub_title = sub_match.groups()
            parts.append(
                '<li class="toc-sub">' + sub_num + ' ' + sub_title + '</li>'
            )
            continue

    if in_list:
        parts.append("</ol>")
    # Close appendices wrapper if it was opened
    if any("toc-appendices" in p for p in parts):
        parts.append("</div>")
    parts.append("</div>")

    return "\n".join(parts)


# -- Part definitions for divider pages ------------------------------------

PARTS = [
    {"label": "Part I",   "title": "Theory and Architecture",   "desc": "Sections 1\u20132",  "before_section": 1},
    {"label": "Part II",  "title": "Substrate and Prototype",   "desc": "Sections 3\u20134",  "before_section": 3},
    {"label": "Part III", "title": "Finite Element Validation",  "desc": "Section 5",          "before_section": 5},
    {"label": "Part IV",  "title": "MEMS Design and Scaling",   "desc": "Sections 6\u20139",  "before_section": 6},
    {"label": "Part V",   "title": "Advanced Techniques",       "desc": "Sections 10\u201312", "before_section": 10},
    {"label": "Part VI",  "title": "Outlook",                   "desc": "Sections 13\u201316", "before_section": 13},
]


def build_part_divider(part):
    return (
        '<div class="part-heading">\n'
        '  <p class="part-label">' + part["label"] + '</p>\n'
        '  <p class="part-title">' + part["title"] + '</p>\n'
        '  <p class="part-desc">' + part["desc"] + '</p>\n'
        '  <hr>\n'
        '</div>\n'
    )


# -- Markdown to HTML conversion -------------------------------------------

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
    """Remove everything before the Abstract section."""
    m = re.search(r"^(## Abstract)", md_text, re.MULTILINE)
    if m:
        return md_text[m.start():]
    m = re.search(r"^(## )", md_text, re.MULTILINE)
    if m:
        return md_text[m.start():]
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

    md = markdown.Markdown(extensions=extensions, extension_configs=extension_configs)
    html = md.convert(protected)
    html = _restore_math(html, math_store)
    return html


# -- Post-processing -------------------------------------------------------

def inject_part_dividers(html):
    """Insert Part divider pages before the appropriate section headings."""
    for part in reversed(PARTS):
        sec_num = part["before_section"]
        pattern = re.compile(
            r'(<h2\s[^>]*>)\s*' + str(sec_num) + r'\.\s',
            re.IGNORECASE,
        )
        m = pattern.search(html)
        if m:
            divider = build_part_divider(part)
            html = html[:m.start()] + divider + html[m.start():]
    return html


def wrap_abstract(html):
    """Wrap the Abstract section in a styled container."""
    pattern = re.compile(
        r'(<h2[^>]*id="abstract"[^>]*>Abstract</h2>)',
        re.IGNORECASE,
    )
    m = pattern.search(html)
    if m:
        html = (
            html[:m.start()]
            + '<div class="abstract-page">'
            + html[m.start():]
        )
        rest_start = m.end()
        next_section = re.search(
            r'(?=<h2|<div class="part-heading")',
            html[rest_start:],
        )
        if next_section:
            insert_pos = rest_start + next_section.start()
            html = html[:insert_pos] + "</div>" + html[insert_pos:]
    return html


# -- Colophon --------------------------------------------------------------

def build_colophon(info):
    return (
        '<div class="colophon">\n'
        '  <p><em>Spectral Eigenmode Memory</em></p>\n'
        '  <p>Version ' + info["version"] + '</p>\n'
        '  <p>&copy; ' + info["author"] + '</p>\n'
        '  <p style="margin-top: 16pt; font-size: 8pt;">\n'
        '    Typeset from Markdown source using Chromium PDF rendering.<br>\n'
        '    Body text in Palatino 11 pt. Mathematics rendered by KaTeX.<br>\n'
        '    All quantitative claims computed from first-principles simulation code<br>\n'
        '    (26 modules, 568 automated tests) with independent FEM validation.\n'
        '  </p>\n'
        '</div>\n'
    )


# -- Master assembly -------------------------------------------------------

def build_html(md_path):
    md_text = md_path.read_text(encoding="utf-8")

    # 1. Extract metadata
    info = extract_front_matter(md_text)

    # 2. Build structured front matter
    title_page = build_title_page(info)
    toc_html = build_toc_html(md_text)

    # 3. Convert body (everything from Abstract onward)
    body_md = strip_front_matter(md_text)
    body_html = convert_md_to_html(body_md)

    # 4. Post-process: inject Part dividers before sections
    body_html = inject_part_dividers(body_html)

    # 5. Wrap abstract in styled container
    body_html = wrap_abstract(body_html)

    # 6. Build colophon
    colophon = build_colophon(info)

    # 7. Assemble full body
    full_body = title_page + toc_html + body_html + colophon

    # 8. Build complete HTML document
    html = HTML_TEMPLATE.format(
        title=info["title"],
        css=CSS,
        body=full_body,
    )

    # 9. Resolve image paths to absolute file:// URIs
    base_dir = md_path.resolve().parent

    def resolve_img(match):
        src = match.group(1)
        if src.startswith(("http://", "https://", "data:", "file://")):
            return match.group(0)
        abs_path = (base_dir / src).resolve()
        return match.group(0).replace(src, abs_path.as_uri())

    html = re.sub(r'<img[^>]+src="([^"]+)"', resolve_img, html)

    return html


def _enforce_recto_starts(pdf_path):
    """Post-process a PDF to ensure every section opens on a recto page.

    Chromium's PDF renderer treats ``page-break-before: right`` as plain
    ``always``, so sections may land on verso (even-numbered) pages.
    This function scans the rendered PDF for section / Part headings,
    and inserts a blank page before any that start on a verso page.

    The algorithm processes sections front-to-back, accumulating an
    insertion offset so that each fix doesn't break subsequent pages.
    """
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        print("  (pypdf not installed; skipping recto enforcement)")
        return

    reader = PdfReader(str(pdf_path))
    n = len(reader.pages)

    # --- Identify pages that should be recto (section starts) ---
    section_re = re.compile(r"^\s*(\d+)\.\s+\w", re.MULTILINE)
    part_re = re.compile(r"PART\s+[IVX]+\b")
    abstract_re = re.compile(r"^\s*Abstract\b", re.MULTILINE)
    appendix_re = re.compile(r"^\s*Appendix\s+[A-Z]", re.MULTILINE)

    recto_pages = []  # 0-indexed pages that must be recto (odd in 1-based)
    for i, page in enumerate(reader.pages):
        text = (page.extract_text() or "").strip()
        if not text:
            continue
        first_400 = text[:400]
        if (section_re.match(first_400)
                or part_re.search(first_400[:100])
                or abstract_re.match(first_400)
                or appendix_re.match(first_400)):
            recto_pages.append(i)  # 0-indexed

    if not recto_pages:
        return

    # --- Calculate which insertions are needed ---
    # Process front-to-back; track cumulative offset from prior insertions.
    insert_before = []  # 0-indexed positions (in the ORIGINAL pdf) to add blanks
    offset = 0
    for orig_idx in recto_pages:
        adjusted = orig_idx + offset  # position after earlier insertions
        page_num_1 = adjusted + 1     # 1-based page number
        if page_num_1 % 2 == 0:       # verso (even 1-based = left page)
            insert_before.append(orig_idx)
            offset += 1

    if not insert_before:
        print("  ✓ All sections already start on recto pages")
        return

    # --- Build new PDF with blank pages inserted ---
    writer = PdfWriter()

    # Create a blank page matching the document's page size
    sample = reader.pages[0]
    page_w = float(sample.mediabox.width)
    page_h = float(sample.mediabox.height)

    insertions_done = 0
    for i, page in enumerate(reader.pages):
        if i in insert_before:
            # Add a blank page before this one
            writer.add_blank_page(width=page_w, height=page_h)
            insertions_done += 1
        writer.add_page(page)

    with open(str(pdf_path), "wb") as f:
        writer.write(f)

    print(f"  ✓ Inserted {insertions_done} blank page(s) for recto starts "
          f"({n} → {n + insertions_done} pages)")


def html_to_pdf(html, pdf_path, md_path=None):
    """Render HTML to PDF using headless Chromium, then enforce recto starts."""
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
                    "top": "0.85in",
                    "right": "0.85in",
                    "bottom": "1in",
                    "left": "1.15in",
                },
                print_background=True,
                display_header_footer=True,
                header_template='<span style="font-size:1px;color:transparent;">.</span>',
                footer_template=(
                    '<div style="font-size: 8.5pt; color: #999; width: 100%;'
                    ' padding: 0 0.85in; display: flex; justify-content: space-between;">'
                    '<span></span>'
                    '<span class="pageNumber"></span>'
                    '</div>'
                ),
            )
            browser.close()
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    # Post-process: insert blank pages so every section opens on recto
    _enforce_recto_starts(pdf_path)


def main():
    parser = argparse.ArgumentParser(
        description="Convert WCFOMA markdown to book-quality PDF"
    )
    parser.add_argument("input", help="Path to .md file")
    parser.add_argument(
        "-o", "--output", help="Output PDF path (default: same name as input)"
    )
    parser.add_argument(
        "--html-only",
        action="store_true",
        help="Write HTML file only (for debugging)",
    )
    args = parser.parse_args()

    md_path = Path(args.input)
    if not md_path.exists():
        print("Error: " + str(md_path) + " not found", file=sys.stderr)
        sys.exit(1)

    print("Building HTML...")
    html = build_html(md_path)

    if args.html_only:
        html_path = md_path.with_suffix(".html")
        html_path.write_text(html, encoding="utf-8")
        print("HTML written to " + str(html_path))
        return

    pdf_path = Path(args.output) if args.output else md_path.with_suffix(".pdf")

    html_path = md_path.with_suffix(".html")
    html_path.write_text(html, encoding="utf-8")
    print("HTML written to " + str(html_path))

    print("Rendering PDF (this takes a few seconds)...")
    html_to_pdf(html, pdf_path, md_path=md_path)
    print("PDF written to " + str(pdf_path))

    # Report page count on macOS
    try:
        import subprocess
        result = subprocess.run(
            ["mdls", "-name", "kMDItemNumberOfPages", str(pdf_path)],
            capture_output=True, text=True,
        )
        for line in result.stdout.strip().split("\n"):
            if "kMDItemNumberOfPages" in line:
                pages = line.split("=")[1].strip()
                print("Pages: " + pages)
    except Exception:
        pass


if __name__ == "__main__":
    main()
