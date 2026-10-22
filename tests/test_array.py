"""Batch API compatibility, buffer ownership, errors, and serialization."""

import ctypes
import math
import sys
from array import array
from concurrent.futures import ThreadPoolExecutor

import pytest

import mgrs
from benchmarks.performance import global_points


def pack(codes, width=15):
    records = (code.encode("ascii").ljust(width, b"\0") for code in codes)
    return bytearray().join(records)


def pairs(points):
    return zip(points[::2], points[1::2])


@pytest.fixture
def points():
    boundaries = [
        (90, 0),
        (-90, 0),
        (84, 6),
        (-80, -180),
        (0, 180),
        (60, 6),
        (78, 20),
        (0, 360),
        (42, -93),
    ]
    return array(
        "d",
        (value for p in boundaries + global_points(1000) for value in p),
    )


@pytest.mark.parametrize("precision", range(6))
@pytest.mark.parametrize("degrees", [True, False])
def test_batch_matches_scalar(points, precision, degrees):
    converter = mgrs.MGRS()
    if not degrees:
        points = array("d", map(math.radians, points))
    convert = converter.toMGRS
    codes_list = [convert(*p, degrees, precision) for p in pairs(points)]
    codes = converter.toMGRSArray(points, degrees, precision)
    assert isinstance(codes, bytearray)
    assert codes == pack(codes_list)
    decoded = converter.toLatLonArray(codes, degrees)
    assert isinstance(decoded, array) and decoded.typecode == "d"
    expected = array(
        "d",
        (v for code in codes_list for v in converter.toLatLon(code, degrees)),
    )
    assert decoded == expected


def test_readonly_numeric_view(points):
    converter = mgrs.MGRS()
    with memoryview(points)[2:].toreadonly() as view:
        codes = converter.toMGRSArray(view)
    assert codes == pack(converter.toMGRS(*p) for p in pairs(points[2:]))
    points.append(0)  # No export survives the conversion.


def test_readonly_byte_view():
    owner = b"x15TWG0000049776y"
    result = mgrs.MGRS().toLatLonArray(memoryview(owner)[1:-1])
    assert result == array("d", mgrs.MGRS().toLatLon("15TWG0000049776"))


@pytest.mark.skipif(
    sys.version_info < (3, 12),
    reason="Python buffer exporters",
)
def test_buffer_protocol_acquires_and_releases_input(points):
    events = []

    class Provider:
        def __buffer__(self, flags):
            events.append("acquired")
            return memoryview(points).toreadonly()

        def __release_buffer__(self, view):
            # The native request keeps this export alive until conversion ends.
            with pytest.raises(BufferError):
                points.append(0)
            events.append("released")

    converter = mgrs.MGRS()
    assert converter.toMGRSArray(Provider()) == converter.toMGRSArray(points)
    assert events == ["acquired", "released"]
    points.append(0)


def test_shaped_and_native_ctypes_buffers(points):
    converter = mgrs.MGRS()
    view = memoryview(points).cast("B").cast("d", shape=[len(points) // 2, 2])
    assert converter.toMGRSArray(view) == converter.toMGRSArray(points)
    native = (ctypes.c_double * 2)(42, -93)
    assert converter.toMGRSArray(native) == pack(["15TWG0000049776"])


@pytest.mark.parametrize("typecode", ["f", "q", "B"])
def test_wrong_point_type(typecode):
    with pytest.raises(TypeError, match="native-endian doubles"):
        mgrs.MGRS().toMGRSArray(array(typecode, [0, 0]))


def test_foreign_byte_order():
    foreign = (
        ctypes.c_double.__ctype_be__
        if sys.byteorder == "little"
        else ctypes.c_double.__ctype_le__
    )
    with pytest.raises(TypeError, match="native-endian doubles"):
        mgrs.MGRS().toMGRSArray((foreign * 2)(42, -93))


@pytest.mark.parametrize("shape", [[2, 3], [2, 1, 2]])
def test_wrong_shape(shape):
    values = array("d", [0] * math.prod(shape))
    view = memoryview(values).cast("B").cast("d", shape=shape)
    with pytest.raises(ValueError, match="shape"):
        mgrs.MGRS().toMGRSArray(view)


def test_odd_and_scalar_shapes():
    for value in (array("d", [42]), ctypes.c_double(42)):
        with pytest.raises(ValueError, match="shape"):
            mgrs.MGRS().toMGRSArray(value)


def test_noncontiguous_unaligned_and_plain_inputs(points):
    converter = mgrs.MGRS()
    for view in (memoryview(points)[::2], memoryview(points)[::-1]):
        with pytest.raises(ValueError, match="C-contiguous"):
            converter.toMGRSArray(view)
    unaligned = memoryview(bytearray(33))[1:].cast("d")
    with pytest.raises(ValueError, match="aligned"):
        converter.toMGRSArray(unaligned)
    with pytest.raises(TypeError):
        converter.toMGRSArray([[42, -93]])


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -91, 91])
def test_invalid_latitude_has_row(bad):
    points = array("d", [42, -93, bad, 0, 0, 0])
    with pytest.raises(mgrs.core.MGRSError, match="row 1: Latitude Error"):
        mgrs.MGRS().toMGRSArray(points)
    points.append(0)  # Failed conversions release their exports too.


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -181, 361])
def test_invalid_longitude_has_row(bad):
    points = array("d", [42, -93, 0, bad])
    with pytest.raises(mgrs.core.MGRSError, match="row 1: Longitude Error"):
        mgrs.MGRS().toMGRSArray(points)


def test_empty_and_precision():
    converter = mgrs.MGRS()
    assert converter.toMGRSArray(array("d")) == bytearray()
    assert converter.toLatLonArray(b"") == array("d")
    for precision in (-1, 6, 2**100):
        with pytest.raises(mgrs.core.MGRSError, match="Precision Error"):
            converter.toMGRSArray(array("d"), MGRSPrecision=precision)
    with pytest.raises(TypeError):
        converter.toMGRSArray(array("d"), MGRSPrecision=1.5)


@pytest.mark.parametrize("code", [b"", b"nonsense", b"\xffABC"])
def test_invalid_code_has_row(code):
    values = pack(["15TWG0000049776"]) + code.ljust(15, b"\0")
    with pytest.raises(mgrs.core.MGRSError, match="row 1: String Error"):
        mgrs.MGRS().toLatLonArray(values)
    values.append(0)


@pytest.mark.parametrize("factory", [bytes, bytearray, memoryview])
def test_inverse_buffers_and_width(factory):
    converter = mgrs.MGRS()
    # Full records have no terminator; the C adapter adds one before parsing.
    for code in (b"15TWG", b"15TWG0000049776", b"31NEA0000000000"):
        result = converter.toLatLonArray(factory(code), width=len(code))
        assert result == array("d", converter.toLatLon(code))
    with pytest.raises(ValueError, match="multiple of width"):
        converter.toLatLonArray(factory(b"15TWG"))


def test_inverse_layout():
    converter = mgrs.MGRS()
    with pytest.raises(TypeError, match="byte buffer"):
        converter.toLatLonArray(array("d", [0, 0]))
    with pytest.raises(TypeError):
        converter.toLatLonArray("15TWG")
    with pytest.raises(ValueError, match="one-dimensional"):
        converter.toLatLonArray(
            memoryview(bytearray(30)).cast("B", shape=[2, 15]),
        )
    with pytest.raises(ValueError, match="C-contiguous"):
        converter.toLatLonArray(memoryview(bytearray(30))[::2])
    for width in (0, 16, 2**100):
        with pytest.raises(ValueError, match="width"):
            converter.toLatLonArray(b"", width=width)
    with pytest.raises(TypeError):
        converter.toLatLonArray(b"", width=1.5)


def test_warning_preserves_coordinates():
    converter = mgrs.MGRS()
    codes = ["15TWG0000049776", "50TMK5045027900"]
    with pytest.warns(RuntimeWarning, match="first affected row 1") as caught:
        decoded = converter.toLatLonArray(pack(codes))
    assert len(caught) == 1
    with pytest.warns(RuntimeWarning):
        expected = array(
            "d",
            (v for code in codes for v in converter.toLatLon(code)),
        )
    assert decoded == expected


def test_scalar_and_batch_calls_share_projection_lock(points):
    converter = mgrs.MGRS()
    expected = converter.toMGRSArray(points)

    def work(index):
        if index % 2:
            return converter.toMGRSArray(points)
        return pack(converter.toMGRS(*point) for point in pairs(points))

    with ThreadPoolExecutor(max_workers=4) as executor:
        for codes in executor.map(work, range(8)):
            assert codes == expected


def test_buffers_release_when_warning_becomes_error():
    codes = pack(["50TMK5045027900"])
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        with pytest.raises(RuntimeWarning, match="Latitude Warning"):
            mgrs.MGRS().toLatLonArray(codes)
    codes.append(0)


def test_buffer_owners_are_not_leaked():
    points = array("d", [42, -93])
    converter = mgrs.MGRS()
    codes = converter.toMGRSArray(points)
    before = sys.getrefcount(points), sys.getrefcount(codes)
    for _ in range(10):
        converter.toMGRSArray(points)
        converter.toLatLonArray(codes)
    assert before == (sys.getrefcount(points), sys.getrefcount(codes))
    points.append(0)
    codes.append(0)
