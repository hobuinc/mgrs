"""Forward strings captured from unmodified GEOTRANS 3.10 (e614372).

Protect fixed-width formatting at every precision, including empty numeric
fields, leading zeros, UTM zone prefixes, UPS, and grid-square boundaries.
"""

from array import array

import pytest

import mgrs


@pytest.mark.parametrize(
    "point, expected",
    [
        (
            (0, -177),
            (
                "01NEA",
                "01NEA00",
                "01NEA0000",
                "01NEA000000",
                "01NEA00000000",
                "01NEA0000000000",
            ),
        ),
        (
            (0, -129),
            (
                "09NWA",
                "09NWA00",
                "09NWA0000",
                "09NWA000000",
                "09NWA00000000",
                "09NWA0000000000",
            ),
        ),
        (
            (0, 177),
            (
                "60NWF",
                "60NWF00",
                "60NWF0000",
                "60NWF000000",
                "60NWF00000000",
                "60NWF0000000000",
            ),
        ),
        (
            (42, -93),
            (
                "15TWG",
                "15TWG04",
                "15TWG0049",
                "15TWG000497",
                "15TWG00004977",
                "15TWG0000049776",
            ),
        ),
        (
            (60, 6),
            (
                "32VLM",
                "32VLM35",
                "32VLM3255",
                "32VLM327552",
                "32VLM32705520",
                "32VLM3270555205",
            ),
        ),
        (
            (78, 20),
            (
                "33XXG",
                "33XXG16",
                "33XXG1563",
                "33XXG159633",
                "33XXG15916332",
                "33XXG1591463320",
            ),
        ),
        (
            (90, 0),
            (
                "ZAH",
                "ZAH00",
                "ZAH0000",
                "ZAH000000",
                "ZAH00000000",
                "ZAH0000000000",
            ),
        ),
        (
            (-90, 0),
            (
                "BAN",
                "BAN00",
                "BAN0000",
                "BAN000000",
                "BAN00000000",
                "BAN0000000000",
            ),
        ),
        (
            (89, -45),
            (
                "YZG",
                "YZG22",
                "YZG2121",
                "YZG214214",
                "YZG21492149",
                "YZG2149221492",
            ),
        ),
        (
            (-89, 45),
            (
                "BAN",
                "BAN77",
                "BAN7878",
                "BAN785785",
                "BAN78507850",
                "BAN7850778507",
            ),
        ),
        (
            (0, 180),
            (
                "01NAA",
                "01NAA60",
                "01NAA6600",
                "01NAA660000",
                "01NAA66020000",
                "01NAA6602100000",
            ),
        ),
        (
            (0, 360),
            (
                "31NAA",
                "31NAA60",
                "31NAA6600",
                "31NAA660000",
                "31NAA66020000",
                "31NAA6602100000",
            ),
        ),
    ],
)
def test_forward_strings_match_upstream(point, expected):
    converter = mgrs.MGRS()
    for precision, code in enumerate(expected):
        assert converter.toMGRS(*point, MGRSPrecision=precision) == code
        assert converter.toMGRSArray(
            array("d", point), MGRSPrecision=precision
        ) == code.encode("ascii").ljust(15, b"\0")


@pytest.mark.parametrize(
    "easting, northing, expected",
    [
        (
            599999.49,
            4999999.49,
            (
                "15TWK",
                "15TWK99",
                "15TWK9999",
                "15TWK999999",
                "15TWK99999999",
                "15TWK9999999999",
            ),
        ),
        (
            599999.5,
            4999999.5,
            (
                "15TWK",
                "15TWK99",
                "15TWK9999",
                "15TWK999999",
                "15TWK99999999",
                "15TWK9999999999",
            ),
        ),
        (
            599999.99999999,
            4999999.99999999,
            (
                "15TXL",
                "15TXL00",
                "15TXL0000",
                "15TXL000000",
                "15TXL00000000",
                "15TXL0000000000",
            ),
        ),
        (
            600000,
            5000000,
            (
                "15TXL",
                "15TXL00",
                "15TXL0000",
                "15TXL000000",
                "15TXL00000000",
                "15TXL0000000000",
            ),
        ),
        (
            500001,
            4000009,
            (
                "15SWA",
                "15SWA00",
                "15SWA0000",
                "15SWA000000",
                "15SWA00000000",
                "15SWA0000100009",
            ),
        ),
    ],
)
def test_utm_grid_boundaries_match_upstream(easting, northing, expected):
    convert = mgrs.MGRS().UTMToMGRS
    for precision, code in enumerate(expected):
        assert convert(15, "N", easting, northing, precision) == code
