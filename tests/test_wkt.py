"""Cell bounds checked against frozen independent PROJ corners."""

import json
import math
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import mgrs

FIXTURE = Path(__file__).resolve().parents[1] / "rust/tests/fixtures/wkt.json"
CASES = json.loads(FIXTURE.read_text())["cases"]


def ring(wkt):
    assert wkt.startswith("POLYGON ((") and wkt.endswith("))")
    points = [tuple(map(float, p.split())) for p in wkt[10:-2].split(", ")]
    assert len(points) >= 5 and points[0] == points[-1]
    assert all(math.isfinite(x) and -90 <= y <= 90 for x, y in points)
    ox, oy = points[0]
    assert (
        sum(
            (a[0] - ox) * (b[1] - oy) - (b[0] - ox) * (a[1] - oy)
            for a, b in zip(points, points[1:])
        )
        > 0
    )
    assert all(abs(a[0] - b[0]) <= 180 for a, b in zip(points, points[1:]))
    return points


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["code"])
def test_independent_proj_corners(case):
    points = ring(mgrs.MGRS().toWKT(case["code"]))
    for lon, lat in case["corners"]:
        assert any(
            abs(y - lat) < 1e-9
            and (abs(lat) == 90 or abs((x - lon + 180) % 360 - 180) < 1e-9)
            for x, y in points
        )


def test_full_cells_curves_poles_and_dateline():
    m = mgrs.MGRS()
    assert len(ring(m.toWKT("15TWG0000049776"))) == 5
    assert len(ring(m.toWKT("15TWG"))) > 5  # sampled curved edges
    assert max(y for x, y in ring(m.toWKT("31XDP"))) > 84.5
    assert max(y for x, y in ring(m.toWKT("BAZ"))) > -79.5
    for code in ["01NAA", "60NZF", "01NAA6602100000"]:
        assert any(abs(x) > 180 for x, y in ring(m.toWKT(code)))
    for code in ["ZAH", "ZAG", "YZH", "YZG", "BAN", "BAM", "AZN", "AZM"]:
        poles = {x for x, y in ring(m.toWKT(code)) if abs(y) == 90}
        assert len(poles) == 2 and max(poles) - min(poles) == 90


def test_input_validation_and_warning_propagation():
    m = mgrs.MGRS()
    expected = m.toWKT(MGRS="04QEJ9798790670")
    assert m.toWKT(b" \t04qej 97987\n90670\r ") == expected
    for code in [
        "",
        "invalid",
        "15TWG1",
        "32XJA",
        "15TWG\0",
        "15TWG\u00a0",
        b"\xff",
    ]:
        with pytest.raises(mgrs.core.MGRSError):
            m.toWKT(code)
    with pytest.raises(TypeError):
        m.toWKT(123)
    with pytest.warns(RuntimeWarning, match="Latitude Warning") as caught:
        ring(m.toWKT("50TMK5045027900"))
    assert len(caught) == 1  # no duplicate warning from buffer sizing/retry
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with pytest.raises(RuntimeWarning):
            m.toWKT("50TMK5045027900")
    assert m.toWKT("04QEJ9798790670") == expected


def test_shared_instance_and_variable_length_output():
    m = mgrs.MGRS()
    codes = ["15TWG0000049776", "ZAH", "BAN", "15TWG", "01NAA"] * 10
    expected = [m.toWKT(code) for code in codes]
    assert len(expected[0]) < 1024 < len(expected[1])
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(m.toWKT, codes)) == expected
