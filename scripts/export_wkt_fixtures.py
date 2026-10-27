"""Freeze cell corners using PROJ, independently of the Rust geometry code.

Run with pyproj installed. IDs come from the frozen C++ oracle; this script
never imports mgrs. Review regenerated coordinates before committing.
"""

import json
import math
import re
from pathlib import Path

import pyproj

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "rust/tests/fixtures"


def main():
    upstream = json.loads((DIRECTORY / "geotrans310.json").read_text())
    # Equator, all precisions, Norway/Svalbard, both poles, antimeridian,
    # the northern UTM cutoff and a southern-hemisphere UTM cell.
    inputs = upstream["forward"][:11] + [
        upstream["forward"][123],
        upstream["forward"][154],
    ]
    cases = []
    for row in inputs:
        lat, lon = row["point"]
        for precision, code in enumerate(row["codes"]):
            match = re.match(r"(\d+)", code)
            epsg = (
                (32600 if lat >= 0 else 32700) + int(match[1])
                if match
                else (32661 if lat >= 0 else 32761)
            )
            forward = pyproj.Transformer.from_crs(4326, epsg, always_xy=True)
            inverse = pyproj.Transformer.from_crs(epsg, 4326, always_xy=True)
            x, y = forward.transform(lon, lat)
            size = 10 ** (5 - precision)
            # Remove sub-micrometre noise at exact projected grid lines.
            x = math.floor((x + 1e-7) / size) * size
            y = math.floor((y + 1e-7) / size) * size
            grid = [(x, y), (x + size, y), (x + size, y + size), (x, y + size)]
            corners = [inverse.transform(e, n) for e, n in grid]
            cases.append(
                {
                    "code": code,
                    "epsg": epsg,
                    "bounds": [x, y, x + size, y + size],
                    "corners": corners,
                }
            )
    fixture = {
        "source": (
            f"pyproj {pyproj.__version__}, PROJ {pyproj.proj_version_str}; "
            "scripts/export_wkt_fixtures.py"
        ),
        "cases": cases,
    }
    (DIRECTORY / "wkt.json").write_text(json.dumps(fixture, indent=2) + "\n")


if __name__ == "__main__":
    main()
