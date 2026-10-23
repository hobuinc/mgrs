"""Generate a reproducible global workload and benchmark both conversions."""

import argparse
import csv
import hashlib
import json
import math
import platform
import random
import statistics
import subprocess
import sys
import time
from array import array
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_POINTS = 1_000_000
DEFAULT_SEED = 20261021
DEFAULT_DATASET = Path("benchmarks/data/global.csv")
SCHEMA_VERSION = 1
SAMPLING = "jittered-equal-area-sphere-v1"
OPERATIONS = ("forward", "inverse")


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def grid_shape(count):
    """Find rectangular factors, closest to square, for exactly count cells."""
    if count < 1:
        raise ValueError("point count must be positive")
    rows = math.isqrt(count)
    while count % rows:
        rows -= 1
    return rows, count // rows


def global_points(count=DEFAULT_POINTS, seed=DEFAULT_SEED):
    """One random point per equal-area cell, in seeded random order.

    Sphere surface area is proportional to d(longitude) * d(sin(latitude)).
    Sampling latitude directly would overrepresent the poles.
    """
    rows, columns = grid_shape(count)
    rng = random.Random(seed)
    points = []
    for row in range(rows):
        for column in range(columns):
            sin_latitude = -1 + 2 * (row + rng.random()) / rows
            latitude = math.degrees(math.asin(sin_latitude))
            longitude = -180 + 360 * (column + rng.random()) / columns
            points.append((latitude, longitude))
    rng.shuffle(points)
    return points


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def generate_dataset(path, count=DEFAULT_POINTS, seed=DEFAULT_SEED):
    path = Path(path)
    metadata_path = path.with_suffix(".json")
    if path.suffix != ".csv":
        raise ValueError("dataset path must end in .csv")
    if path.exists() or metadata_path.exists():
        raise ValueError("dataset already exists; use a new output path")
    points = global_points(count, seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="ascii") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("latitude", "longitude"))
        writer.writerows(points)
    rows, columns = grid_shape(count)
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "sampling": SAMPLING,
        "count": count,
        "seed": seed,
        "latitude_bands": rows,
        "longitude_cells": columns,
        "sha256": sha256_file(path),
    }
    write_json(metadata_path, metadata)
    return metadata


def load_dataset(path):
    path = Path(path)
    metadata = json.loads(path.with_suffix(".json").read_text())
    if metadata.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported dataset schema")
    if metadata.get("sampling") != SAMPLING:
        raise ValueError("unsupported dataset sampling method")
    if sha256_file(path) != metadata.get("sha256"):
        raise ValueError("dataset checksum mismatch")
    points = []
    with path.open(newline="", encoding="ascii") as stream:
        reader = csv.reader(stream)
        if next(reader, None) != ["latitude", "longitude"]:
            raise ValueError("expected latitude,longitude CSV header")
        for row_number, row in enumerate(reader, 2):
            if len(row) != 2:
                raise ValueError(f"invalid coordinate at CSV row {row_number}")
            lat, lon = map(float, row)
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError(f"invalid coordinate at CSV row {row_number}")
            points.append((lat, lon))
    if not points or len(points) != metadata.get("count"):
        raise ValueError("dataset point count mismatch")
    return points, metadata


def distance_metres(first, second):
    """Spherical distance for validation, including across the antimeridian."""
    lat1, lon1 = map(math.radians, first)
    lat2, lon2 = map(math.radians, second)
    haversine = math.sin((lat2 - lat1) / 2) ** 2 + (
        math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 6_371_008.8 * math.asin(math.sqrt(min(1, haversine)))


def prepare_workload(converter, points, precision):
    """Prepare inverse inputs and validate every round trip outside timing."""
    codes = []
    digest = hashlib.sha256()
    coverage = {"utm": 0, "ups_north": 0, "ups_south": 0}
    max_error = 0.0
    # MGRS identifies a cell, not the original location. GEOTRANS 3.10 returns
    # its center; older backends return its corner. Allow three cell widths
    # for the diagonal and projection scale distortion with either backend.
    tolerance = 3 * 10 ** (5 - precision)
    for index, point in enumerate(points):
        try:
            code = converter.toMGRS(*point, MGRSPrecision=precision)
            decoded = converter.toLatLon(code)
        except Exception as error:
            message = f"conversion failed at point {index}: {point}"
            raise ValueError(message) from error
        if not (-90 <= decoded[0] <= 90 and -180 <= decoded[1] <= 180):
            message = f"invalid inverse result at point {index}: {decoded}"
            raise ValueError(message)
        error = distance_metres(point, decoded)
        if error > tolerance:
            message = f"round-trip error at point {index}: {error:.3f} m"
            raise ValueError(message)
        max_error = max(max_error, error)
        region = "utm"
        if not code[0].isdigit():
            region = "ups_north" if point[0] >= 0 else "ups_south"
        coverage[region] += 1
        codes.append(code)
        digest.update(code.encode("ascii") + b"\n")
    return codes, {
        "inverse_inputs_sha256": digest.hexdigest(),
        "coverage": coverage,
        "max_round_trip_error_metres": max_error,
        "round_trip_tolerance_metres": tolerance,
    }


def forward_pass(convert, points, precision):
    for lat, lon in points:
        convert(lat, lon, MGRSPrecision=precision)


def inverse_pass(convert, codes):
    for code in codes:
        convert(code)


def summarize(samples, count):
    median = statistics.median(samples)
    return {
        "seconds": samples,
        "median_seconds": median,
        "min_seconds": min(samples),
        "max_seconds": max(samples),
        "queries_per_second": count / median,
        "microseconds_per_query": median * 1_000_000 / count,
    }


def prepare_arrays(converter, points, codes, precision):
    """Validate every batch output against the scalar API before timing."""
    coordinates = array("d", (value for point in points for value in point))
    records = (code.encode("ascii").ljust(15, b"\0") for code in codes)
    strings = bytearray().join(records)
    actual_codes = converter.toMGRSArray(coordinates, MGRSPrecision=precision)
    if actual_codes != strings:
        raise ValueError("array forward results differ from scalar results")
    expected = array(
        "d", (value for code in codes for value in converter.toLatLon(code))
    )
    actual_points = converter.toLatLonArray(strings)
    if actual_points != expected:
        raise ValueError("array inverse results differ from scalar results")
    return (
        coordinates,
        strings,
        {
            "points_storage": "array('d')",
            "codes_storage": "bytearray",
            "code_width": 15,
            "validation": "all-rows-exact-scalar-equivalence",
            "timing": "whole-buffer-including-output-allocation-v1",
        },
    )


def measure_arrays(converter, points, codes, precision, repeats, warmup):
    converter.toMGRSArray(
        memoryview(points)[: warmup * 2],
        MGRSPrecision=precision,
    )
    converter.toLatLonArray(memoryview(codes)[: warmup * 15])
    samples = {operation: [] for operation in OPERATIONS}
    for repeat in range(repeats):
        order = OPERATIONS if repeat % 2 == 0 else OPERATIONS[::-1]
        for operation in order:
            start = time.perf_counter()
            if operation == "forward":
                converter.toMGRSArray(points, MGRSPrecision=precision)
            else:
                converter.toLatLonArray(codes)
            elapsed = time.perf_counter() - start
            samples[operation].append(elapsed)
            print(
                f"array {operation} {repeat + 1}/{repeats}: {elapsed:.3f} s",
                file=sys.stderr,
                flush=True,
            )
    count = len(points) // 2
    return {name: summarize(values, count) for name, values in samples.items()}


def array_speedups(report):
    if "array_operations" not in report:
        return {}
    return {
        name: report["operations"][name]["median_seconds"]
        / report["array_operations"][name]["median_seconds"]
        for name in OPERATIONS
    }


def measure(converter, points, codes, precision, repeats, warmup):
    forward = converter.toMGRS
    inverse = converter.toLatLon
    forward_pass(forward, points[:warmup], precision)
    inverse_pass(inverse, codes[:warmup])
    samples = {operation: [] for operation in OPERATIONS}
    for repeat in range(repeats):
        # Alternate order to reduce systematic bias from warming/drift.
        order = OPERATIONS if repeat % 2 == 0 else OPERATIONS[::-1]
        for operation in order:
            start = time.perf_counter()
            if operation == "forward":
                forward_pass(forward, points, precision)
            else:
                inverse_pass(inverse, codes)
            elapsed = time.perf_counter() - start
            samples[operation].append(elapsed)
            print(
                f"{operation:7} {repeat + 1}/{repeats}: {elapsed:.3f} s, "
                f"{len(points) / elapsed:,.0f} queries/s",
                file=sys.stderr,
                flush=True,
            )
    count = len(points)
    return {name: summarize(values, count) for name, values in samples.items()}


def environment(source_root=None):
    source_root = Path(source_root or Path(__file__).resolve().parents[1])

    def git(*args):
        try:
            return subprocess.check_output(
                ["git", *args],
                cwd=source_root,
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            return None

    status = git("status", "--porcelain", "--untracked-files=no")
    return {
        "source_root": str(source_root.resolve()),
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "hostname": platform.node(),
        "git_commit": git("rev-parse", "HEAD"),
        "git_dirty": status != "" if status is not None else None,
    }


def native_library(module):
    """Locate either the extension or a historical ctypes library."""
    native = getattr(module, "_native", None)
    if native is not None:
        return native.__file__
    return module.core.rt._name


def compare_results(current, baseline, max_regression):
    if baseline.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported baseline schema")
    for key in ("dataset", "config"):
        if current[key] != baseline.get(key):
            raise ValueError(f"baseline {key} does not match this run")
    if current["validation"]["inverse_inputs_sha256"] != baseline.get(
        "validation", {}
    ).get("inverse_inputs_sha256"):
        raise ValueError("baseline inverse inputs do not match this run")
    # A different library revision/version is expected. A different host or
    # interpreter makes an automated speed regression decision misleading.
    previous_environment = baseline.get("environment", {})
    for key in ("python", "implementation", "platform", "machine", "hostname"):
        if current["environment"][key] != previous_environment.get(key):
            raise ValueError(f"baseline environment does not match: {key}")
    groups = [("", "operations")]
    if "array_operations" in baseline:
        if "array_operations" not in current:
            raise ValueError("candidate no longer supports array conversions")
        if current.get("array_config") != baseline.get("array_config"):
            raise ValueError("baseline array configuration does not match")
        groups.append(("array_", "array_operations"))
    comparisons = {}
    for prefix, group in groups:
        for operation in OPERATIONS:
            name = prefix + operation
            previous_operation = baseline.get(group, {}).get(operation, {})
            previous = previous_operation.get("median_seconds")
            if not isinstance(previous, (int, float)) or not (
                math.isfinite(previous) and previous > 0
            ):
                raise ValueError(f"invalid {name} baseline timing")
            elapsed = current[group][operation]["median_seconds"]
            change = (elapsed / previous - 1) * 100
            comparisons[name] = {
                "change_percent": change,
                "regression": elapsed > previous * (1 + max_regression / 100),
            }
    return comparisons


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def nonnegative_int(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return number


def percentage(value):
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("must be finite and nonnegative")
    return number


def positive_float(value):
    number = percentage(value)
    if number == 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser(
        "generate",
        help="create a reusable global dataset",
    )
    generate.add_argument("--output", type=Path, default=DEFAULT_DATASET)
    generate.add_argument(
        "--points",
        type=positive_int,
        default=DEFAULT_POINTS,
    )
    generate.add_argument("--seed", type=int, default=DEFAULT_SEED)
    run = commands.add_parser(
        "run",
        help="benchmark forward and inverse conversions",
    )
    run.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    run.add_argument("--output", type=Path)
    run.add_argument("--precision", type=int, choices=range(6), default=5)
    run.add_argument("--repeats", type=positive_int, default=5)
    run.add_argument("--warmup", type=nonnegative_int, default=10_000)
    run.add_argument("--baseline", type=Path)
    run.add_argument("--max-regression", type=percentage, default=10.0)
    run.add_argument(
        "--scenario", choices=("scalar", "array", "auto"), default="scalar"
    )
    run.add_argument("--min-array-speedup", type=positive_float)
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            metadata = generate_dataset(args.output, args.points, args.seed)
            print(f"Created {metadata['count']:,} points: {args.output}")
            print(f"SHA-256: {metadata['sha256']}")
            return 0

        import mgrs

        timestamp = datetime.now(timezone.utc)
        output = args.output or Path("benchmarks/results") / (
            timestamp.strftime("%Y%m%dT%H%M%S.%fZ") + ".json"
        )
        protected = [args.dataset, args.dataset.with_suffix(".json")]
        if args.baseline:
            protected.append(args.baseline)
        if output.resolve() in [path.resolve() for path in protected]:
            raise ValueError("output must not overwrite dataset or baseline")
        baseline = None
        if args.baseline:
            baseline = json.loads(args.baseline.read_text())
        points, metadata = load_dataset(args.dataset)
        print(
            f"Preparing and validating {len(points):,} points...",
            file=sys.stderr,
        )
        converter = mgrs.MGRS()
        available = hasattr(converter, "toMGRSArray") and hasattr(
            converter, "toLatLonArray"
        )
        use_arrays = args.scenario != "scalar" and available
        if args.scenario == "array" and not available:
            raise ValueError("this revision has no array conversion API")
        if args.min_array_speedup is not None and not use_arrays:
            raise ValueError("minimum speedup requires the array scenario")
        codes, validation = prepare_workload(converter, points, args.precision)
        if use_arrays:
            array_points, array_codes, array_config = prepare_arrays(
                converter, points, codes, args.precision
            )
        source_root = Path(mgrs.__file__).resolve().parents[1]
        result = {
            "schema_version": SCHEMA_VERSION,
            "created_at": timestamp.isoformat(),
            "dataset": metadata,
            "config": {
                "precision": args.precision,
                "repeats": args.repeats,
                "warmup": min(args.warmup, len(points)),
                "timing": "serial-public-api-alternating-v1",
            },
            "environment": environment(source_root),
            "mgrs_version": mgrs.__version__,
            "native_library_sha256": sha256_file(native_library(mgrs)),
            "validation": validation,
        }
        result["operations"] = measure(
            converter,
            points,
            codes,
            args.precision,
            args.repeats,
            result["config"]["warmup"],
        )
        if use_arrays:
            result["array_config"] = array_config
            result["array_operations"] = measure_arrays(
                converter,
                array_points,
                array_codes,
                args.precision,
                args.repeats,
                result["config"]["warmup"],
            )
            result["array_speedup"] = array_speedups(result)
            if args.min_array_speedup is not None:
                result["array_min_speedup"] = args.min_array_speedup
                result["array_speedup_pass"] = all(
                    s >= args.min_array_speedup
                    for s in result["array_speedup"].values()
                )
        # Retain the measurement even if the chosen baseline is incompatible.
        write_json(output, result)
        print(f"Results: {output}")
        regressed = False
        if baseline is not None:
            comparison = compare_results(result, baseline, args.max_regression)
            result["comparison"] = {
                "baseline": str(args.baseline),
                "max_regression_percent": args.max_regression,
                "operations": comparison,
            }
            for operation, change in comparison.items():
                label = "REGRESSION" if change["regression"] else "PASS"
                delta = change["change_percent"]
                print(f"{operation}: {delta:+.2f}% time ({label})")
            regressed = any(item["regression"] for item in comparison.values())
            write_json(output, result)
        for operation, speedup in array_speedups(result).items():
            print(f"array {operation}: {speedup:.2f}x scalar throughput")
            if args.min_array_speedup is not None:
                regressed |= speedup < args.min_array_speedup
        return 1 if regressed else 0
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
