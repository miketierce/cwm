#!/usr/bin/env python3
"""Build 2-column PDFs for both split papers."""
import os
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright

env = {**os.environ, 'PYTHONPATH': '.'}

# Step 1: Build 2-col HTML for both papers
for md in ['paper/cwm_core.md', 'paper/cwm_advanced.md']:
    print(f'Building 2-col HTML for {md}...')
    subprocess.run(['python', 'tools/md2pdf_2col.py', md, '--html-only'],
                   check=True, env=env)

# Step 2: Render PDFs
with sync_playwright() as p:
    browser = p.chromium.launch()
    for name in ['cwm_core', 'cwm_advanced']:
        html_path = Path(f'paper/{name}_2col.html')
        pdf_path = Path(f'paper/{name}_2col.pdf')
        print(f'Rendering {pdf_path}...')
        page = browser.new_page()
        page.goto(html_path.resolve().as_uri(), wait_until='networkidle')
        page.wait_for_timeout(3000)
        page.pdf(
            path=str(pdf_path),
            format='Letter',
            margin={
                'top': '0.65in',
                'right': '0.6in',
                'bottom': '0.75in',
                'left': '0.6in',
            },
            print_background=True,
        )
        page.close()
        size_kb = pdf_path.stat().st_size // 1024
        print(f'  -> {pdf_path} ({size_kb} KB)')
    browser.close()

print('Done.')
