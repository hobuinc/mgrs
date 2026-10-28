"""GeoJSON mappings need only built-in types and preserve the full cell."""

import json
import math
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import mgrs

FIXTURE = Path(__file__).resolve().parents[1] / "rust/tests/fixtures/wkt.json"
CASES = json.loads(FIXTURE.read_text())["cases"]


def area(ring):
    ox, oy = ring[0]
    return (
        sum(
            (a[0] - ox) * (b[1] - oy) - (b[0] - ox) * (a[1] - oy)
            for a, b in zip(ring, ring[1:])
        )
        / 2
    )


def rings(geometry):
    assert type(geometry) is dict
    assert set(geometry) == {"type", "coordinates"}
    assert geometry["type"] in ("Polygon", "MultiPolygon")
    assert json.loads(json.dumps(geometry, allow_nan=False)) == geometry
    polygons = geometry["coordinates"]
    if geometry["type"] == "Polygon":
        polygons = [polygons]
    assert polygons
    for polygon in polygons:
        assert type(polygon) is list and len(polygon) == 1
        ring = polygon[0]
        assert type(ring) is list and len(ring) >= 4
        assert ring[0] == ring[-1] and area(ring) > 0
        for point in ring:
            assert type(point) is list and len(point) == 2
            assert all(type(n) is float and math.isfinite(n) for n in point)
            assert -180 <= point[0] <= 180 and -90 <= point[1] <= 90
        assert all(abs(a[0] - b[0]) <= 180 for a, b in zip(ring, ring[1:]))
    return [polygon[0] for polygon in polygons]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["code"])
def test_geometry_matches_wkt_and_independent_corners(case):
    m = mgrs.MGRS()
    geometry = m.toGeoJSON(case["code"])
    parts = rings(geometry)
    text = m.toWKT(case["code"])[10:-2]
    wkt = [list(map(float, p.split())) for p in text.split(", ")]
    if all(-180 <= x <= 180 for x, y in wkt):
        assert geometry == {"type": "Polygon", "coordinates": [wkt]}
    assert sum(area(part) for part in parts) == pytest.approx(
        area(wkt), rel=1e-6, abs=1e-15
    )
    for lon, lat in case["corners"]:
        assert any(
            abs(y - lat) < 1e-9
            and (abs(lat) == 90 or abs((x - lon + 180) % 360 - 180) < 1e-9)
            for part in parts
            for x, y in part
        )


def test_antimeridian_and_pole_topology():
    m = mgrs.MGRS()
    for code in ["01NAA", "60NZF", "01NAA6602100000"]:
        geometry = m.toGeoJSON(code)
        assert geometry["type"] == "MultiPolygon"
        parts = rings(geometry)
        assert len(parts) == 2
        west = {y for part in parts for x, y in part if x == -180}
        east = {y for part in parts for x, y in part if x == 180}
        assert west == east and len(west) >= 2
    for code in ["ZAH", "ZAG", "YZH", "YZG", "BAN", "BAM", "AZN", "AZM"]:
        geometry = m.toGeoJSON(code)
        assert geometry["type"] == "Polygon"
        pole = {x for x, y in rings(geometry)[0] if abs(y) == 90}
        assert len(pole) == 2 and max(pole) - min(pole) == 90


def test_geo_interface_mapping_and_independent_storage():
    m = mgrs.MGRS()
    geometry = m.toGeoJSON(MGRS="15TWG0000049776")

    class Cell:
        @property
        def __geo_interface__(self):
            return m.toGeoJSON("15TWG0000049776")

    assert Cell().__geo_interface__ == geometry
    geometry["coordinates"][0][0][0] = 0.0
    assert Cell().__geo_interface__["coordinates"][0][0][0] == -93.0
    codes = ["15TWG0000049776", "ZAH", "BAN", "15TWG", "01NAA"] * 5
    expected = [m.toGeoJSON(code) for code in codes]
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(m.toGeoJSON, codes)) == expected


def test_validation_and_warnings():
    m = mgrs.MGRS()
    expected = m.toGeoJSON("04QEJ9798790670")
    assert m.toGeoJSON(b" \t04qej 97987\n90670\r ") == expected
    for code in ["", "invalid", "15TWG1", "32XJA", "15TWG\0", b"\xff"]:
        with pytest.raises(mgrs.core.MGRSError):
            m.toGeoJSON(code)
    with pytest.raises(TypeError):
        m.toGeoJSON(123)
    with pytest.warns(RuntimeWarning, match="Latitude Warning") as caught:
        rings(m.toGeoJSON("50TMK5045027900"))
    assert len(caught) == 1
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with pytest.raises(RuntimeWarning):
            m.toGeoJSON("50TMK5045027900")
    rings(m.toGeoJSON("15TWG"))
