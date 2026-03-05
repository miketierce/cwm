"""
Data Export Utilities

Export simulation and experiment results to standard formats
for external analysis, reproducibility, and sharing.
"""

import json
import csv
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Dict, Any


def ensure_dir(path: str) -> Path:
    """Create directory if it doesn't exist."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def export_to_csv(
    data: Dict[str, np.ndarray],
    filename: str,
    output_dir: str = "data/results",
    metadata: Dict[str, Any] = None,
):
    """
    Export array data to CSV with optional metadata header.

    Parameters
    ----------
    data : dict
        Column name -> array mapping.
    filename : str
        Output filename (without extension).
    output_dir : str
        Output directory.
    metadata : dict, optional
        Key-value pairs written as comments at top of CSV.
    """
    out = ensure_dir(output_dir)
    filepath = out / f"{filename}.csv"

    with open(filepath, 'w', newline='') as f:
        if metadata:
            for key, val in metadata.items():
                f.write(f"# {key}: {val}\n")
            f.write(f"# exported: {datetime.now().isoformat()}\n")

        writer = csv.writer(f)
        headers = list(data.keys())
        writer.writerow(headers)

        # Transpose arrays to rows
        arrays = [np.atleast_1d(data[h]) for h in headers]
        max_len = max(len(a) for a in arrays)
        for i in range(max_len):
            row = []
            for a in arrays:
                row.append(float(a[i]) if i < len(a) else '')
            writer.writerow(row)

    print(f"Exported CSV: {filepath}")
    return filepath


def export_to_json(
    data: Dict[str, Any],
    filename: str,
    output_dir: str = "data/results",
):
    """
    Export results to JSON.
    Handles numpy arrays by converting to lists.
    """
    out = ensure_dir(output_dir)
    filepath = out / f"{filename}.json"

    def convert(obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, complex):
            return {'real': obj.real, 'imag': obj.imag}
        raise TypeError(f"Cannot serialize {type(obj)}")

    payload = {
        'metadata': {
            'exported': datetime.now().isoformat(),
            'project': 'WCFOMA',
        },
        'data': data,
    }

    with open(filepath, 'w') as f:
        json.dump(payload, f, indent=2, default=convert)

    print(f"Exported JSON: {filepath}")
    return filepath
