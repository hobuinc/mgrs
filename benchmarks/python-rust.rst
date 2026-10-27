Python with the Rust backend
============================

The Python extension now links the native Rust translation of GEOTRANS 3.10.
The existing pybind11 interface remains in place, including keyword arguments,
return types, exceptions, warnings, input normalization and buffer validation.
The original C++ conversion sources remain in the repository for reference;
they are not built into the Python extension.

Measured performance
--------------------

On macOS 26.5.2 ARM64 with CPython 3.12.15, the Rust backend reduced elapsed
time in all four public-API scenarios. Each value is the median of ten timed
passes over the same one million points at precision 5. The comparison ran
C++, Rust, Rust, C++, with five passes per invocation and alternating forward
and inverse directions. Dataset loading, validation and warmup were untimed.
Output allocation and the Rust binding's input snapshots were included.

.. list-table:: Seconds per million conversions
   :header-rows: 1
   :widths: 30 18 18 17 17

   * - Python operation
     - C++ backend
     - Rust backend
     - Time reduction
     - Throughput gain
   * - Scalar forward
     - 0.5776
     - 0.4120
     - 28.7%
     - 1.40x
   * - Scalar inverse
     - 0.9528
     - 0.4995
     - 47.6%
     - 1.91x
   * - Batch forward
     - 0.2952
     - 0.1518
     - 48.6%
     - 1.94x
   * - Batch inverse
     - 0.8214
     - 0.3852
     - 53.1%
     - 2.13x

The baseline is the optimized GEOTRANS 3.10 C++ backend at
``b0634d792179879ef0d18667f165fc18fc7208cf``. Both builds use pybind11 3.1.0,
scikit-build-core 1.1.1, CMake 4.4.4 and AppleClang 21.0.0. The Rust engine
uses Rust 1.90.0 and the workspace release profile (thin LTO, one codegen unit).
Neither build uses CPU-specific tuning. These measurements describe this host
and workload; no cross-platform or multithreaded speedup is implied.

Raw samples, environment, binary hashes and numerical verification results
are in `python-rust-results.json <python-rust-results.json>`_. The dataset
uses seed ``20261022`` and SHA-256
``9e1729c9da6db1a56589702aa22ab16296aacd45534a9b4506dd256c61aeedc1``.

Compatibility and consequences
------------------------------

* All 207 pre-existing Python tests and doctests pass without expectation
  changes. Additional Python tests exercise the frozen C++ reference: 6,876
  forward cases and 6,595 inverse inputs, including radians, UTM, errors and
  latitude warnings. The complete Python suite passes on CPython 3.12 and
  3.15 (211 tests); CPython 3.11 passes 210 with its existing buffer-exporter
  test skipped. An isolated install from the source distribution passes all
  211 tests. Rust tests, the standalone Cargo package, the minimum Rust 1.85
  check, and all 14 TypeScript/Node tests also pass. Windows and Linux builds
  are configured in CI but were not run on this macOS host.
* On the fixed million-point dataset, all 6,000,000 forward records match C++
  exactly at precisions 0 through 5, through both scalar and batch Python APIs.
  Scalar and batch inverse coordinates match each other exactly. Against C++,
  348,585 of the two million inverse coordinate components differ in their
  final floating-point digits; the largest absolute difference is
  ``3.339550858072471e-13`` degrees. Inverse values are numerically equivalent,
  but are not guaranteed bit-for-bit identical to C++ values. Cell centers
  and the one-metre default precision are unchanged.
* Python threads can convert concurrently: the GIL is released and the Rust
  engine's immutable state needs no global projection mutex. Batches snapshot
  their input first, costing an additional 16 bytes per forward point or
  ``width`` bytes per inverse record until the call finishes. Output is written
  directly into the returned ``bytearray`` or ``array('d')``.
* Source builds additionally require Rust/Cargo 1.85 or newer. Wheels include
  the Rust code and need no Rust installation. The C++17 compiler requirement
  remains for pybind11. The macOS ARM64 extension grew from about 279 KiB to
  491 KiB in this comparison; no extra shared backend library is loaded.

Reproducing the comparison
-------------------------

Build the C++ baseline in its own checkout and the candidate in this checkout
using the same Python interpreter and build tools. The build helper extracts
the wheel's native extension into each checkout, and the benchmark disables
editable-install hooks so it imports the requested backend. For example::

    git worktree add --detach /tmp/mgrs-cpp b0634d7
    python -m benchmarks.build --source /tmp/mgrs-cpp
    python -m benchmarks.build --source .
    python -m benchmarks.performance generate \
        --output benchmarks/data/geotrans310-forward.csv \
        --points 1000000 --seed 20261022
    python -m benchmarks.ci --base /tmp/mgrs-cpp --candidate . \
        --dataset benchmarks/data/geotrans310-forward.csv \
        --output benchmarks/results/python-rust --repeats 5

Skip generation when the fixed dataset already exists. The harness verifies
its manifest and refuses to reuse a results directory. To freeze C++ output,
run ``scripts.export_large_oracle`` with the C++ checkout's Python package;
the exporter rejects the Rust backend to protect the reference. Then run::

    python -m benchmarks.verify_backend \
        --dataset benchmarks/data/geotrans310-forward.csv \
        --oracle benchmarks/results/rust-oracle \
        --output benchmarks/results/python-rust-parity.json

The verifier checks oracle hashes, all scalar and batch forward records, and
every scalar and batch inverse coordinate. It fails on inverse differences
above ``1e-9`` degrees or any change in scalar/batch results; it never rewrites
the oracle. CI also compares each operation against the PR base, and builds
and tests wheels and an isolated source distribution with the Rust toolchain.
