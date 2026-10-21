"""Fast harness checks without wall-clock performance assertions."""

import copy
import json
import math
from collections import Counter

import pytest

import mgrs
from benchmarks import performance as perf


def test_global_distribution_and_reproducibility():
    points = perf.global_points(10_000, seed=17)
    assert points == perf.global_points(10_000, seed=17)
    assert points != perf.global_points(10_000, seed=18)
    assert len(set(points)) == 10_000
    cells = Counter()
    for latitude, longitude in points:
        assert -90 <= latitude <= 90
        assert -180 <= longitude < 180
        row = int((math.sin(math.radians(latitude)) + 1) * 50)
        column = int((longitude + 180) / 3.6)
        cells[row, column] += 1
    assert len(cells) == 10_000
    assert set(cells.values()) == {1}
    assert sum(lat < 0 for lat, lon in points) == 5000
    assert any(lat > 84 for lat, lon in points)
    assert any(lat < -80 for lat, lon in points)
    assert points != sorted(points)
    assert perf.DEFAULT_POINTS >= 1_000_000
    assert perf.grid_shape(perf.DEFAULT_POINTS) == (1000, 1000)


@pytest.mark.parametrize("count", [1, 7, 12, 101])
def test_arbitrary_point_counts(count):
    assert len(perf.global_points(count)) == count
    rows, columns = perf.grid_shape(count)
    assert rows * columns == count


def test_dataset_reuse_and_integrity(tmp_path):
    first, second = tmp_path / "a.csv", tmp_path / "b.csv"
    metadata = perf.generate_dataset(first, 100, seed=9)
    assert metadata == perf.generate_dataset(second, 100, seed=9)
    assert first.read_bytes() == second.read_bytes()
    points, loaded_metadata = perf.load_dataset(first)
    assert points == perf.global_points(100, seed=9)
    assert loaded_metadata == metadata
    with pytest.raises(ValueError, match="already exists"):
        perf.generate_dataset(first, 100)
    first.write_text(first.read_text() + "0,0\n")
    with pytest.raises(ValueError, match="checksum"):
        perf.load_dataset(first)


@pytest.mark.parametrize(
    "coordinate",
    ["nan,0", "0,inf", "91,0", "0,-181", "0"],
)
def test_invalid_dataset_coordinates(tmp_path, coordinate):
    path = tmp_path / "points.csv"
    metadata = perf.generate_dataset(path, 1)
    path.write_text("latitude,longitude\n" + coordinate + "\n")
    metadata["sha256"] = perf.sha256_file(path)
    perf.write_json(path.with_suffix(".json"), metadata)
    with pytest.raises(ValueError, match="invalid coordinate"):
        perf.load_dataset(path)


def test_dataset_count_mismatch(tmp_path):
    path = tmp_path / "points.csv"
    metadata = perf.generate_dataset(path, 10)
    metadata["count"] += 1
    perf.write_json(path.with_suffix(".json"), metadata)
    with pytest.raises(ValueError, match="count mismatch"):
        perf.load_dataset(path)


def test_real_conversion_coverage_and_round_trips():
    points = [(42, -93), (-42, 93), (89, 45), (-89, -45), (0, 179.99999)]
    codes, validation = perf.prepare_workload(mgrs.MGRS(), points, 5)
    assert len(codes) == len(points)
    assert validation["coverage"] == {"utm": 3, "ups_north": 1, "ups_south": 1}
    assert validation["max_round_trip_error_metres"] < 3
    assert len(validation["inverse_inputs_sha256"]) == 64
    assert perf.distance_metres((0, 179.999999), (0, -179.999999)) < 1


def test_bad_round_trip_is_not_silently_timed():
    class BrokenConverter:
        def toMGRS(self, *args, **kwargs):
            return "15TWG0000049776"

        def toLatLon(self, code):
            return (0, 0)

    with pytest.raises(ValueError, match="round-trip error at point 0"):
        perf.prepare_workload(BrokenConverter(), [(42, -93)], 5)


def test_timing_excludes_warmup_and_alternates_directions(monkeypatch):
    events = []

    class Converter:
        def toMGRS(self, lat, lon, MGRSPrecision):
            events.append("forward")

        def toLatLon(self, code):
            events.append("inverse")

    timestamps = iter([10, 12, 20, 24, 30, 36, 40, 48])

    def clock():
        events.append("clock")
        return next(timestamps)

    monkeypatch.setattr(perf.time, "perf_counter", clock)
    result = perf.measure(Converter(), [(0, 0)] * 3, ["x"] * 3, 5, 2, 1)
    assert events[:2] == ["forward", "inverse"]
    assert events[2:] == sum(
        (
            ["clock"] + [direction] * 3 + ["clock"]
            for direction in ["forward", "inverse", "inverse", "forward"]
        ),
        [],
    )
    assert result["forward"]["seconds"] == [2, 8]
    assert result["inverse"]["seconds"] == [4, 6]
    assert result["forward"]["median_seconds"] == 5
    assert result["forward"]["queries_per_second"] == 0.6
    assert result["forward"]["microseconds_per_query"] == 5e6 / 3


@pytest.fixture
def report():
    return {
        "schema_version": perf.SCHEMA_VERSION,
        "dataset": {"sha256": "dataset"},
        "config": {"repeats": 5, "precision": 5},
        "validation": {"inverse_inputs_sha256": "codes"},
        "environment": {
            "python": "3.12.0",
            "implementation": "CPython",
            "platform": "test-platform",
            "machine": "arm64",
            "hostname": "test-host",
        },
        "operations": {
            "forward": {"median_seconds": 4},
            "inverse": {"median_seconds": 8},
        },
    }


@pytest.mark.parametrize("direction", perf.OPERATIONS)
def test_regression_detected_independently(report, direction):
    current = copy.deepcopy(report)
    current["operations"][direction]["median_seconds"] *= 1.25
    changes = perf.compare_results(current, report, 10)
    assert changes[direction] == {"change_percent": 25, "regression": True}
    other = "inverse" if direction == "forward" else "forward"
    assert not changes[other]["regression"]
    changes = perf.compare_results(current, report, 25)
    assert not changes[direction]["regression"]
    current["operations"][direction]["median_seconds"] *= 0.5
    changes = perf.compare_results(current, report, 0)
    assert not changes[direction]["regression"]


def test_threshold_equality_is_not_a_regression(report):
    current = copy.deepcopy(report)
    current["operations"]["forward"]["median_seconds"] *= 1.1
    changes = perf.compare_results(current, report, 10)
    assert not changes["forward"]["regression"]


@pytest.mark.parametrize(
    "section,key",
    [
        ("dataset", "sha256"),
        ("config", "precision"),
        ("environment", "python"),
        ("environment", "hostname"),
        ("validation", "inverse_inputs_sha256"),
    ],
)
def test_incompatible_baselines_rejected(report, section, key):
    baseline = copy.deepcopy(report)
    baseline[section][key] = "different"
    with pytest.raises(ValueError, match="does not match|do not match"):
        perf.compare_results(report, baseline, 10)


@pytest.mark.parametrize("timing", [0, -1, float("nan"), float("inf"), "fast"])
def test_invalid_baseline_timing(report, timing):
    baseline = copy.deepcopy(report)
    baseline["operations"]["forward"]["median_seconds"] = timing
    with pytest.raises(ValueError, match="invalid forward baseline timing"):
        perf.compare_results(report, baseline, 10)


def test_cli_reports_and_regression_exit_codes(tmp_path):
    dataset = tmp_path / "points.csv"
    baseline = tmp_path / "baseline.json"
    current = tmp_path / "current.json"
    generate = ["generate", "--output", str(dataset), "--points", "100"]
    assert perf.main(generate) == 0
    args = [
        "run",
        "--dataset",
        str(dataset),
        "--repeats",
        "1",
        "--warmup",
        "5",
    ]
    assert perf.main(args + ["--output", str(baseline)]) == 0
    saved = json.loads(baseline.read_text())
    assert saved["dataset"]["count"] == 100
    assert saved["operations"]["forward"]["queries_per_second"] > 0
    assert saved["operations"]["inverse"]["queries_per_second"] > 0
    for operation in perf.OPERATIONS:
        saved["operations"][operation]["median_seconds"] = 1e-12
    perf.write_json(baseline, saved)
    compare = args + ["--baseline", str(baseline)]
    assert perf.main(compare + ["--output", str(current)]) == 1
    comparison = json.loads(current.read_text())["comparison"]
    assert all(c["regression"] for c in comparison["operations"].values())
    before = baseline.read_bytes()
    assert perf.main(compare + ["--output", str(baseline)]) == 2
    assert baseline.read_bytes() == before


@pytest.mark.parametrize(
    "args",
    [
        ["generate", "--points", "0"],
        ["run", "--repeats", "0"],
        ["run", "--warmup", "-1"],
        ["run", "--precision", "6"],
        ["run", "--max-regression", "nan"],
    ],
)
def test_invalid_cli_options(args):
    with pytest.raises(SystemExit) as error:
        perf.main(args)
    assert error.value.code == 2
