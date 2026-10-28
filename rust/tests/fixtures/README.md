# Conversion and geometry oracles

`wkt.json` freezes 78 independent PROJ cell-corner cases across all six precisions: ordinary UTM, southern UTM, Norway/Svalbard, the antimeridian, the UTM latitude cutoff and UPS cells including both poles. The IDs come from the existing C++ oracle; the projected grid bounds and geographic corners are calculated by PROJ, without importing the Rust engine. Rust, Python and the shared Node/browser suite consume these same expected corners. Additional tests cover adaptive sampling, full cells beyond projection cutoffs, pole wedges, input validation, warnings and Python output-buffer ownership. To regenerate explicitly with `pyproj` installed, run `python scripts/export_wkt_fixtures.py` and review the numerical changes.

## Python conformance oracle

The GeoJSON tests reuse `wkt.json` to verify corners, ring orientation, coordinate order, precision and preservation of the WKT footprint. They also check antimeridian splitting, pole cells, JSON serialization, independent output storage, error/warning propagation and Python's `__geo_interface__` mapping structure. Rust checks GeoJSON against every valid inverse input in `geotrans310.json`; Node and browser conformance use the same geometry scenarios. No geospatial package is needed to run these tests.

`geotrans310.json` freezes the current Python GEOTRANS 3.10 results at main commit `1b12e14`. Tests consume this checked-in file; they never derive expected coordinates from the Rust implementation. It is included in the Rust crate so packaged tests can run without the repository's Python files.

It contains 6,876 forward strings (1,146 points at six precisions), five UTM boundary sets, and 6,595 inverse inputs with coordinates, radians, UTM results, errors and warnings. Points include the original forward regression cases, Norway/Svalbard, antimeridian, latitude-band/UTM/UPS boundaries, the issue 40 example, issue 46's latitude, doctest cities, and all 1,000 seeded global points used by Python's array tests.

Explicit regeneration requires a Python checkout with the C++ backend (for example `b0634d7`). The exporter rejects Rust-backed Python so the reference cannot be replaced by results from the implementation under test:

```sh
python -m scripts.export_python_fixtures
```

Review any oracle change as a numerical compatibility change. Large optional comparisons use a separately frozen, checksum-verified million-point oracle; see [the performance guide](../../../benchmarks/rust-typescript.md).

| Python source | Rust coverage | TypeScript / browser coverage |
| --- | --- | --- |
| `tests/test.txt`, README examples | `tests/api.rs`, crate doctest | `test/conformance.mjs`: doctests, DMS, warnings |
| `tests/test_geotrans_forward.py` | `tests/parity.rs`: all six precisions and UTM truncation boundaries | shared conformance: all fixture strings and UTM boundaries |
| `tests/test_input.py` | fixture invalid strings, whitespace/bytes and numerical hardening in `api.rs` | shared conformance: whitespace, bytes, invalid types, nonfinite values, large integers, malformed strings |
| `tests/test_array.py` | `parity.rs` and `api.rs`: scalar/batch identity, degrees/radians, precision, views, empty arrays, layout/row errors, warnings, ownership | shared conformance: typed views/offsets, copies, widths/padding, errors/warnings; Node workers |
| `tests/test_native.py` | immutable independent/shared instances across native threads, error recovery | independent Wasm instances, warning-handler error recovery, explicit disposal and Node workers |
| `tests/test_performance.py`, `test_performance_array.py`, `test_performance_ci.py` | benchmark helper tests: seeded inputs, medians, round trips and per-operation regression gates | `test/benchmark.test.mjs`: same contracts; Node/browser benchmark smoke paths |
| `tests/test_benchmark_build.py`, Python-specific native/wheel tests | Cargo package build and packaged test verification | `scripts/test-package.mjs`: isolated npm install, both Wasm engines and consumer TypeScript declarations |

Python-specific behavior is adapted rather than copied literally: Rust's borrowed typed slices prevent invalid dtype/shape/alignment and enforce lifetimes; JS typed arrays replace Python's buffer protocol, with copies across the Wasm boundary. Python refcount, GIL, ctypes ABI, warning filters, bytecode and wheel-build checks remain in the Python suite; Rust threading/ownership, JS typed-array copies, worker isolation, warning callbacks, disposal, Cargo and npm packaging test the corresponding language behavior. The existing Python benchmark/build/CI orchestration remains intact, and the new runners exercise the same four conversion operations without depending on Python builds.

Forward MGRS strings must match exactly. Inverse geographic comparisons allow 1e-9 degrees and UTM comparisons 1e-6 m for platform math differences; doctest displays remain at five decimal places. Scalar and batch results within each implementation must be identical. Warnings/errors must retain their Python category and first affected row.
