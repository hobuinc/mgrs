"""Validate the array benchmark without machine-dependent timing limits."""

import json
from array import array

import pytest

import mgrs
from benchmarks import performance as perf


@pytest.mark.parametrize("operation", ["forward", "inverse"])
def test_array_output_mismatch_fails_validation(operation):
    class BrokenConverter(mgrs.MGRS):
        def toMGRSArray(self, *args, **kwargs):
            result = super().toMGRSArray(*args, **kwargs)
            if operation == "forward":
                result[:3] = b"bad"
            return result

        def toLatLonArray(self, *args, **kwargs):
            result = super().toLatLonArray(*args, **kwargs)
            if operation == "inverse":
                result[0] += 1
            return result

    with pytest.raises(ValueError, match=f"array {operation} results differ"):
        perf.prepare_arrays(
            BrokenConverter(),
            [(42, -93)],
            ["15TWG0000049776"],
            5,
        )


def test_array_timing_uses_one_call_per_pass(monkeypatch):
    events = []

    class Converter:
        def toMGRSArray(self, points, MGRSPrecision):
            events.append(("forward", len(points) // 2))

        def toLatLonArray(self, codes):
            events.append(("inverse", len(codes) // 15))

    times = iter([0, 1, 2, 4, 5, 9, 10, 13])
    monkeypatch.setattr(perf.time, "perf_counter", lambda: next(times))
    result = perf.measure_arrays(
        Converter(), array("d", [0] * 20), bytearray(150), 5, 2, 3
    )
    assert events == [
        ("forward", 3),
        ("inverse", 3),
        ("forward", 10),
        ("inverse", 10),
        ("inverse", 10),
        ("forward", 10),
    ]
    assert result["forward"]["median_seconds"] == 2
    assert result["inverse"]["median_seconds"] == 3
    assert result["forward"]["queries_per_second"] == 5


def test_array_cli_report_and_speedup_failure(tmp_path):
    dataset = tmp_path / "global.csv"
    perf.generate_dataset(dataset, 100)
    output = tmp_path / "result.json"
    assert (
        perf.main(
            [
                "run",
                "--dataset",
                str(dataset),
                "--output",
                str(output),
                "--scenario",
                "array",
                "--repeats",
                "1",
                "--warmup",
                "5",
                "--min-array-speedup",
                "1000000000",
            ]
        )
        == 1
    )
    result = json.loads(output.read_text())
    assert not result["array_speedup_pass"]
    validation = result["array_config"]["validation"]
    assert validation == "all-rows-exact-scalar-equivalence"
    assert set(result["array_operations"]) == {"forward", "inverse"}
