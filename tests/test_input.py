"""Normalize MGRS whitespace without silently accepting partial coordinates."""

from array import array

import pytest

import mgrs


def test_issue_40_coordinate():
    converter = mgrs.MGRS()
    coordinate = converter.toLatLon("04QEJ 97987 90670")
    assert coordinate == converter.toLatLon("04QEJ9798790670")
    # The ticket's location, within one metre; 3.10 returns the cell center.
    assert coordinate == pytest.approx((21.61643, -158.05325), abs=1e-5, rel=0)
    assert converter.toMGRS(*coordinate) == "04QEJ9798790670"


@pytest.mark.parametrize("as_bytes", [False, True])
@pytest.mark.parametrize(
    "code",
    [
        "04QEJ 97987 90670",
        " 04QEJ9798790670",
        "04QEJ9798790670 ",
        "  04QEJ  97987  90670  ",
        "\t04QEJ\t97987\r\n90670\v\f",
        " " * 100 + "04qej 97987 90670" + " " * 100,
    ],
)
def test_scalar_whitespace(code, as_bytes):
    converter = mgrs.MGRS()
    if as_bytes:
        code = code.encode("ascii")
    compact = "04QEJ9798790670"
    assert converter.toLatLon(code) == converter.toLatLon(compact)
    assert converter.toLatLon(code, inDegrees=False) == converter.toLatLon(
        compact, inDegrees=False
    )
    expected_utm = converter.MGRSToUTM(compact)
    assert converter.MGRSToUTM(code, encoding="ascii") == expected_utm


@pytest.mark.parametrize("as_bytes", [False, True])
@pytest.mark.parametrize(
    "code",
    [
        " ",
        "\t\r\n\v\f",
        "17SMB8287460719 is an Odd place",
        "Bad company, I can't deny\nBad, bad company, 'til the day I die",
        "04QEJ12garbage",
        "04QEJ12 garbage",
        "04QEJ 12 A 34",
        "04QEJ 97987 90670!",
        "04QEJ 97987 90670 00",
        "04QEJ 97987 9067",
        "04QEJ9798790670\0junk",
        "04QEJ9798790670\0",
        "04QEJ\0 97987 90670",
    ],
)
def test_scalar_rejects_incomplete_or_trailing_input(code, as_bytes):
    if as_bytes:
        code = code.encode("ascii")
    converter = mgrs.MGRS()
    for convert in (converter.toLatLon, converter.MGRSToUTM):
        with pytest.raises(mgrs.core.MGRSError, match="String Error"):
            convert(code)


@pytest.mark.parametrize("precision", range(6))
@pytest.mark.parametrize("point", [(21.61643, -158.05325), (90, 0), (-90, 0)])
def test_whitespace_at_all_precisions_and_poles(precision, point):
    converter = mgrs.MGRS()
    compact = converter.toMGRS(*point, MGRSPrecision=precision)
    assert converter.toLatLon(" " + " ".join(compact) + " ") == (
        converter.toLatLon(compact)
    )


@pytest.mark.parametrize(
    "code, compact",
    [
        (b" 04QEJ ", "04QEJ"),
        (b"04QEJ 97 90", "04QEJ9790"),
        (b"\t04QEJ\t97\n90\r", "04QEJ9790"),
        (b" ZAH 00 00 ", "ZAH0000"),
    ],
)
@pytest.mark.parametrize("degrees", [False, True])
def test_batch_whitespace(code, compact, degrees):
    converter = mgrs.MGRS()
    expected = array("d", converter.toLatLon(compact, inDegrees=degrees))
    # Both unterminated records and the default NUL-padded layout work.
    assert converter.toLatLonArray(code, degrees, width=len(code)) == expected
    padded = bytearray(code.ljust(15, b"\0"))
    assert converter.toLatLonArray(padded, degrees) == expected
    assert padded == code.ljust(15, b"\0")
    padded.append(0)  # No buffer export remains after conversion.


@pytest.mark.parametrize(
    "code",
    [
        b" \t\n ",
        b"04QEJ12garbage",
        b"04QEJ12 garbage",
        b"04QEJ12\0junk",
        b"04QEJ12\0 34",
        b"04QEJ12\0\xff",
    ],
)
def test_batch_rejects_trailing_input_with_row(code):
    values = bytearray(b"04QEJ9798790670") + code.ljust(15, b"\0")
    with pytest.raises(mgrs.core.MGRSError, match="row 1: String Error"):
        mgrs.MGRS().toLatLonArray(values)
    values.append(0)  # Failed conversions also release their exports.
