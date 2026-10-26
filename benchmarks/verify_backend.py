"""Compare the installed Python backend with a frozen C++ million-point oracle.

Create the oracle with scripts.export_large_oracle using a C++ checkout first.
This command only reads the oracle and never updates its expected results.
"""

import argparse
import json
import math
import sys
import warnings
from array import array
from pathlib import Path

import mgrs

from .performance import load_dataset, native_library, sha256_file, write_json


def verify(dataset, oracle):
    points, metadata = load_dataset(dataset)
    manifest = json.loads((oracle / "manifest.json").read_text())
    identity = ("sha256", "count", "seed")
    if any(manifest[key] != metadata[key] for key in identity):
        raise ValueError("oracle dataset identity does not match")
    coordinates = array("d", (v for point in points for v in point))
    m = mgrs.MGRS()
    maximum = 0.0
    different = 0

    def reference(name):
        path = oracle / name
        if sha256_file(path) != manifest["files"][name]:
            raise ValueError(f"oracle hash mismatch: {name}")
        return path.read_bytes()

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        for precision in range(6):
            expected = reference(f"upstream-precision-{precision}.bin")
            actual = m.toMGRSArray(coordinates, MGRSPrecision=precision)
            if len(expected) != len(points) * 15 or actual != expected:
                raise ValueError(f"batch mismatch at precision {precision}")
            for i, point in enumerate(points):
                code = m.toMGRS(*point, MGRSPrecision=precision)
                start, end = i * 15, (i + 1) * 15
                if code.encode().ljust(15, b"\0") != expected[start:end]:
                    raise ValueError(f"mismatch: p={precision}, row={i}")
        baseline = array("d")
        baseline.frombytes(reference("upstream-inverse-precision-5.bin"))
        if sys.byteorder != "little":
            baseline.byteswap()
        decoded = m.toLatLonArray(expected)
        if len(decoded) != len(baseline) or len(baseline) != len(points) * 2:
            raise ValueError("inverse output length mismatch")
        for i in range(len(points)):
            start, end = i * 15, (i + 1) * 15
            code = expected[start:end].rstrip(b"\0")
            scalar = m.toLatLon(code)
            for j, value in enumerate(scalar):
                batch = decoded[i * 2 + j]
                error = abs(value - baseline[i * 2 + j])
                if not math.isfinite(value) or value != batch or error > 1e-9:
                    raise ValueError(f"inverse mismatch at row {i}")
                maximum = max(maximum, error)
                different += value != baseline[i * 2 + j]
    return {
        "dataset": metadata,
        "oracle_files": manifest["files"],
        "native_library_sha256": sha256_file(native_library(mgrs)),
        "backend": getattr(mgrs._native, "backend", "cpp"),
        "exact_scalar_forward_records": len(points) * 6,
        "exact_batch_forward_records": len(points) * 6,
        "inverse_points": len(points),
        "inverse_scalar_equals_batch": True,
        "inverse_components_differing_from_cpp": different,
        "maximum_inverse_difference_degrees": maximum,
        "inverse_tolerance_degrees": 1e-9,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(args.oracle.resolve()) or output in (
        args.dataset.resolve(),
        args.dataset.with_suffix(".json").resolve(),
    ):
        parser.error("output must not overwrite the dataset or oracle")
    result = verify(args.dataset, args.oracle)
    write_json(output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
