"""Public API and linking checks for the pybind11 extension."""

import math
import subprocess
import sys
from array import array
from concurrent.futures import ThreadPoolExecutor

import pytest

import mgrs


def test_import_does_not_load_foreign_function_or_array_dependencies():
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, mgrs; "
            "assert 'ctypes' not in sys.modules; "
            "assert 'packaging' not in sys.modules; "
            "m = mgrs.MGRS(); "
            "assert m.toMGRS(42, -93) == '15TWG0000049776'",
        ],
        check=True,
    )


def test_native_module_and_exception_identity():
    from mgrs import _native

    assert isinstance(mgrs.MGRS(), _native.MGRS)
    assert mgrs.core.MGRSError is _native.MGRSError
    with pytest.warns(DeprecationWarning):
        assert isinstance(mgrs.core.RTreeError("error"), mgrs.core.MGRSError)


def test_scalar_keywords_bytes_and_units():
    m = mgrs.MGRS()
    code = m.toMGRS(latitude=42, longitude=-93, MGRSPrecision=5)
    assert m.toLatLon(MGRS=code) == m.toLatLon(code.encode("ascii"))
    assert code == m.toMGRS(math.radians(42), math.radians(-93), False)
    radians = m.toLatLon(code, inDegrees=False)
    degrees = m.toLatLon(code)
    assert tuple(v * 180 / math.pi for v in radians) == degrees
    assert m.MGRSToUTM(code, encoding="ascii") == m.MGRSToUTM(code.encode())
    zone, hemisphere, easting, northing = m.MGRSToUTM(code)
    assert m.UTMToMGRS(zone, hemisphere, easting, northing) == code
    assert m.UTMToMGRS(zone, hemisphere.encode(), easting, northing) == code


@pytest.mark.parametrize("code", ["", "nonsense", b"\xff", "é"])
def test_scalar_invalid_codes(code):
    with pytest.raises(mgrs.core.MGRSError, match="String Error"):
        mgrs.MGRS().toLatLon(code)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 91])
def test_scalar_invalid_coordinates(value):
    with pytest.raises(mgrs.core.MGRSError, match="Latitude Error"):
        mgrs.MGRS().toMGRS(value, 0)


def test_scalar_invalid_utm_and_precision():
    m = mgrs.MGRS()
    for precision in (-1, 6, 2**100):
        with pytest.raises(mgrs.core.MGRSError, match="Precision Error"):
            m.toMGRS(42, -93, MGRSPrecision=precision)
    with pytest.raises(mgrs.core.MGRSError, match="Easting Error"):
        m.UTMToMGRS(15, "N", float("nan"), 4000000)
    with pytest.raises(mgrs.core.MGRSError, match="Hemisphere Error"):
        m.UTMToMGRS(15, "X", 500000, 4000000)
    with pytest.raises(TypeError, match="one character"):
        m.UTMToMGRS(15, "North", 500000, 4000000)


def test_all_native_entry_points_share_projection_state_safely():
    m = mgrs.MGRS()
    locations = [(42, -93), (-42, 93), (60, 6), (78, 20)]
    codes = [m.toMGRS(*p) for p in locations]
    coordinates = [m.toLatLon(c) for c in codes]
    utm = [m.MGRSToUTM(c) for c in codes]
    packed = bytearray().join(c.encode().ljust(15, b"\0") for c in codes)

    def work(index):
        i = index % len(locations)
        assert m.toMGRS(*locations[i]) == codes[i]
        assert m.toLatLon(codes[i]) == coordinates[i]
        assert m.MGRSToUTM(codes[i]) == utm[i]
        assert m.UTMToMGRS(*utm[i]) == codes[i]
        start, end = i * 15, (i + 1) * 15
        assert m.toMGRSArray(array("d", locations[i])) == packed[start:end]
        assert m.toLatLonArray(packed) == array(
            "d", (v for p in coordinates for v in p)
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(work, range(200)))
