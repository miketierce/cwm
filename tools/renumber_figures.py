#!/usr/bin/env python3
"""Renumber figures in cwm_core.md to sequential order of first appearance."""

import re
import sys

# Map: old figure number → new figure number
# Derived from order of first appearance in the paper
RENUM = {
    3: 1,    # eigenmode encoding (§2.1)
    1: 2,    # architecture (§2.3)
    10: 3,   # CW readout (§2.3)
    11: 4,   # two-phase readout (§2.3)
    7: 5,    # prototype spectrum (§4.4)
    8: 6,    # ringdown (§4.5)
    9: 7,    # recall discrimination (§4.6)
    5: 8,    # scaling (§6.4)
    4: 9,    # Q budget (§7.6)
    6: 10,   # fabrication (§9.1)
    2: 11,   # MEMS cross-section (§9.3)
}

def renumber(text):
    """Two-pass renumbering using placeholders to avoid cascading."""
    # Pass 1: Replace all "Figure N" with "Figure __FIGPH_N__"
    def to_placeholder(m):
        prefix = m.group(1)  # "Figure " or "Figure"
        num = int(m.group(2))
        suffix = m.group(3)  # could be ".", "(b)", etc.
        if num in RENUM:
            return f"{prefix}__FIGPH_{num}__{suffix}"
        return m.group(0)

    # Match "Figure N" in captions, body text, alt text
    # Handles: Figure 3, Figure 3., Figure 9(b), Figure 10
    text = re.sub(r'(Figure\s?)(\d+)(\b)', to_placeholder, text)

    # Pass 2: Replace all placeholders with final numbers
    def from_placeholder(m):
        old_num = int(m.group(1))
        return f"Figure {RENUM[old_num]}"

    text = re.sub(r'Figure\s?__FIGPH_(\d+)__', from_placeholder, text)

    return text


if __name__ == "__main__":
    path = "paper/cwm_core.md"
    with open(path, "r") as f:
        content = f.read()

    new_content = renumber(content)

    # Verify: check figure caption order
    captions = re.findall(r'<strong>Figure (\d+)', new_content)
    print(f"Figure caption order after renumbering: {captions}")
    expected = [str(i) for i in range(1, 12)]
    if captions == expected:
        print("✓ Sequential 1-11 in order of appearance")
    else:
        print(f"✗ Expected {expected}, got {captions}")
        sys.exit(1)

    # Verify: check in-text references are valid
    refs = set(int(x) for x in re.findall(r'Figure (\d+)', new_content))
    print(f"All figure numbers referenced: {sorted(refs)}")
    if refs == set(range(1, 12)):
        print("✓ All figures 1-11 referenced, no orphans")
    else:
        extra = refs - set(range(1, 12))
        if extra:
            print(f"✗ Unexpected figure numbers: {extra}")
            sys.exit(1)

    with open(path, "w") as f:
        f.write(new_content)
    print(f"\n✓ Wrote {path}")
