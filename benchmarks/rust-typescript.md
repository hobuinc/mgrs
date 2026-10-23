# Rust and TypeScript performance paths

The Rust and TypeScript runners measure scalar forward, scalar inverse, batch forward and batch inverse conversions independently. Both Node.js and browsers run the Rust engine compiled to WebAssembly. Native Rust needs no binding layer.

## Fixed inputs and correctness

Reuse the GEOTRANS upgrade's fixed CSV and its JSON manifest. If absent, generate them using the existing Python harness, from the repository root:

```sh
python -m benchmarks generate --output benchmarks/data/geotrans310-forward.csv --points 1000000 --seed 20261022
```

This is the existing jittered equal-area spherical dataset, SHA-256 `9e1729c9da6db1a56589702aa22ab16296aacd45534a9b4506dd256c61aeedc1`. Generation refuses to overwrite existing data. Keep the manifest alongside the CSV: each new runner checks its checksum and point count when present.

For a fresh independent numerical oracle, build/install the current Python extension, then run:

```sh
python -m scripts.export_large_oracle benchmarks/data/geotrans310-forward.csv benchmarks/results/python-oracle
cargo run --release --locked --example verify -- benchmarks/data/geotrans310-forward.csv benchmarks/results/python-oracle
node typescript/verify.mjs benchmarks/data/geotrans310-forward.csv benchmarks/results/python-oracle
```

The exporter requires a new output directory and saves 106 MB of results: six precision-specific fixed-width byte files and little-endian inverse doubles, with checksums. Both verification programs validate the input identity and oracle hashes, compare every scalar and batch forward result exactly at precisions 0–5, and compare every inverse coordinate within 1e-9 degrees. Ordinary tests use the much smaller checked-in Python fixture and need no Python installation.

## Native Rust and Node.js

Build TypeScript first, following [its guide](../typescript/README.md). From the repository root:

```sh
cargo run --release --locked --example benchmark -- --dataset benchmarks/data/geotrans310-forward.csv --repeats 5 --output benchmarks/results/rust-baseline.json
node typescript/benchmark.mjs --dataset benchmarks/data/geotrans310-forward.csv --repeats 5 --output benchmarks/results/node-baseline.json

# After a change, with the same dataset, runtime, build settings and machine:
cargo run --release --locked --example benchmark -- --dataset benchmarks/data/geotrans310-forward.csv --repeats 5 --baseline benchmarks/results/rust-baseline.json --output benchmarks/results/rust-current.json --max-regression 10
node typescript/benchmark.mjs --dataset benchmarks/data/geotrans310-forward.csv --repeats 5 --baseline benchmarks/results/node-baseline.json --output benchmarks/results/node-current.json --max-regression 10
```

Without `--dataset`, both runners generate a repeatable spherical workload with a xorshift32 generator (`--points 1000000 --seed 20261022` by default). This is **not** the original stratified Python dataset. Use a shared CSV for comparisons between languages: native and Wasm math may round generated coordinates differently. CSV input takes precedence over the generated point count and seed options.

Before timing, each runner validates finite coordinates, prepares inverse strings, checks every scalar/batch result for identity, and verifies a maximum 3 m round-trip error at precision 5. It warms up to 10,000 scalar conversions in both directions; batch calls are exercised during validation. Five timed passes process the complete input; operation order reverses on alternating passes. Loading, generation, validation, string preparation, warmup and report writing are excluded. Allocation, bindings, encoding, returned-result handling and normal runtime garbage collection are included. Outputs are consumed and discarded without accumulating timed results. Batch measurements include one complete returned array per pass.

JSON records all samples, median seconds, points/second, runtime, OS/architecture/host, dataset SHA-256, point count and maximum round-trip error. Each operation has its own regression gate. Any median slowdown strictly greater than `--max-regression` (default 10%) returns status 1; success returns 0; invalid inputs/baselines return 2. Baselines must match backend, runtime, platform/host, dataset, point count, precision and repeats. Build flags and power settings are the operator's responsibility. Do not compare a native baseline with a Wasm report or use historical timings from another machine as a gate.

## Browser

```sh
cd typescript
npx playwright install chromium
npm run bench:browser -- --points 1000000 --seed 20261022 --repeats 5
```

This launches a local HTTP server and headless Chromium, runs the conformance and worker tests, then measures the same four operations inside the browser. Output includes the browser user agent, input hash and samples. It uses the generated xorshift workload; the browser runner currently has no CSV-input or baseline-gating option. It closes the browser and server on completion. Browser performance is sensitive to JIT warmup and garbage collection; compare repeated runs with the same browser version and workload.

## Initial measurements

Measured October 23, 2026, on macOS 26.5.2 ARM64, release Rust 1.90.0 and Node.js 24.19.0. Each value is the median seconds for **1,000,000 points**, five passes, precision 5, using the fixed CSV above. These are local observations, not portable speed guarantees.

| Operation | Native Rust | Node.js / Wasm |
| --- | ---: | ---: |
| Scalar forward | 0.172 | 0.319 |
| Scalar inverse | 0.379 | 0.923 |
| Batch forward | 0.149 | 0.189 |
| Batch inverse | 0.393 | 0.669 |

On that dataset, both implementations matched all six million scalar forward strings and all six million batch forward records exactly. The maximum inverse difference from Python was **3.34 × 10⁻¹³ degrees**; maximum distance from the original coordinate to its precision-5 cell center was **0.707465 m**. GEOTRANS 3.10 cell-center semantics are preserved.

A separate Chromium 156 run on the generated million-point workload measured 0.548 s scalar forward, 1.472 s scalar inverse, 0.192 s batch forward and 0.647 s batch inverse. Its different input hash is recorded explicitly; these browser values are not a controlled comparison with the fixed-CSV table.

Raw samples and verification metadata are in [rust-typescript-results.json](rust-typescript-results.json). CI runs correctness, packaging and 1,000-point benchmark smoke tests on each change. The existing Python performance gate remains unchanged; no noisy cross-platform wall-clock threshold is imposed by the new CI workflow.
