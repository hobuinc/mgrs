"""Freeze Python results for optional million-point Rust/Wasm comparisons."""

import argparse
import json
import sys
import warnings
from array import array
from pathlib import Path

import mgrs
from benchmarks.performance import load_dataset, sha256_file


def main():
    if getattr(mgrs._native, "backend", None) == "rust":
        raise RuntimeError(
            "Generate C++ reference fixtures from a C++ backend checkout"
        )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    points, metadata = load_dataset(args.dataset)
    args.output.mkdir(parents=True, exist_ok=False)
    coordinates = array("d", (v for p in points for v in p))
    converter = mgrs.MGRS()
    files = {}
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        for precision in range(6):
            codes = converter.toMGRSArray(coordinates, MGRSPrecision=precision)
            target = args.output / f"upstream-precision-{precision}.bin"
            target.write_bytes(codes)
            files[target.name] = sha256_file(target)
        inverse = converter.toLatLonArray(codes)
        if sys.byteorder != "little":
            inverse.byteswap()
        target = args.output / "upstream-inverse-precision-5.bin"
        target.write_bytes(inverse.tobytes())
        files[target.name] = sha256_file(target)
    metadata["files"] = files
    manifest_text = json.dumps(metadata, indent=2) + "\n"
    (args.output / "manifest.json").write_text(manifest_text)
    print(f"Saved {len(points)} points at six precisions to {args.output}")


if __name__ == "__main__":
    main()
