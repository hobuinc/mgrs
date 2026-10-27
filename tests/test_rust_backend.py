"""Exercise the Python binding against the frozen C++ GEOTRANS oracle."""

import json
import warnings
from array import array
from pathlib import Path

import pytest

import mgrs
from mgrs import _native

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "rust/tests/fixtures/geotrans310.json"


@pytest.fixture(scope="module")
def oracle():
    return json.loads(FIXTURE.read_text())


def test_rust_backend_is_linked():
    assert _native.backend == "rust"


def test_frozen_cpp_forward_and_utm(oracle):
    m = mgrs.MGRS()
    points = array("d", (v for row in oracle["forward"] for v in row["point"]))
    for precision in range(6):
        expected = [row["codes"][precision] for row in oracle["forward"]]
        assert [
            m.toMGRS(*row["point"], MGRSPrecision=precision)
            for row in oracle["forward"]
        ] == expected
        packed = b"".join(code.encode().ljust(15, b"\0") for code in expected)
        assert m.toMGRSArray(points, MGRSPrecision=precision) == packed
        for row in oracle["utm"]:
            assert (
                m.UTMToMGRS(*row["point"], MGRSPrecision=precision)
                == row["codes"][precision]
            )


def test_frozen_cpp_inverse_errors_and_warnings(oracle):
    m = mgrs.MGRS()
    for row in oracle["inverse"]:
        calls = [
            ("latlon", lambda: m.toLatLon(row["code"]), 1e-9),
            ("radians", lambda: m.toLatLon(row["code"], False), 1e-11),
            ("utm", lambda: m.MGRSToUTM(row["code"]), 1e-6),
        ]
        for key, call, tolerance in calls:
            expected = row[key]
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                if "error" in expected:
                    with pytest.raises(mgrs.core.MGRSError) as error:
                        call()
                    names = [
                        name
                        for name in mgrs.core.errors.values()
                        if name in str(error.value)
                    ]
                    assert " & ".join(names) == expected["error"]
                    continue
                actual = call()
            assert bool(caught) == expected["warning"], row["code"]
            values = expected["value"]
            if key == "utm":
                assert actual[:2] == tuple(values[:2])
                actual, values = actual[2:], values[2:]
            assert actual == pytest.approx(values, abs=tolerance, rel=0)
