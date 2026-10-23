GEOTRANS 3.10 forward optimization
=================================

The optimization replaces three ``snprintf`` calls in ``makeMGRSString`` with
direct writes of the validated zone and zero-padded numeric fields. The
projection arithmetic, grid truncation, epsilon handling, and inverse
cell-center behavior remain unchanged. Only ``CoordinateSystems/mgrs/MGRS.cpp``
differs from the original NGA source hashes in ``libmgrs/geotrans3.10/SOURCE.json``.

Fixed dataset
-------------

``benchmarks/data/geotrans310-forward.csv`` contains exactly 1,000,000 random
points, generated with seed ``20261022``. There is one jittered point per cell
in a 1,000 by 1,000 longitude/sin(latitude) grid, shuffled into random order.
This gives equal-area coverage on a sphere: 989,685 UTM points, 2,736 north UPS
points, and 7,579 south UPS points. Coordinates are decimal degrees.

The CSV and its adjacent JSON manifest are held fixed between revisions. The
generator refuses to overwrite them, and every benchmark checks their hash.
The reference metadata is saved in ``geotrans310-forward-dataset.json``.
The CSV SHA-256 is::

    9e1729c9da6db1a56589702aa22ab16296aacd45534a9b4506dd256c61aeedc1

When the CSV is absent, generate it once from the repository root::

    python -m benchmarks generate --output benchmarks/data/geotrans310-forward.csv \
        --points 1000000 --seed 20261022
    python -c "import json; from pathlib import Path; assert json.loads(Path('benchmarks/data/geotrans310-forward.json').read_text()) == json.loads(Path('benchmarks/geotrans310-forward-dataset.json').read_text())"

Keep the same files for subsequent experiments. The 38 MB CSV is excluded
from Git and source distributions; its seed, generator, and reference checksum
are included so a fresh checkout can reproduce and verify it.

Measurements
------------

Measured on October 22, 2026, with an Apple M4 Max, macOS 26.5.2 ARM64, CPython
3.12.15, Apple Clang 21.0.0, pybind11 3.1.0, and scikit-build-core 1.1.1.
All three backends were freshly built with the same ``-O3 -DNDEBUG`` release
flags and no LTO. Their pybind11 bindings, Python wrappers, and batch adapter
were identical.

The backends were GEOTRANS 2.4.2-derived code at ``c8d6e57``, unmodified
GEOTRANS 3.10 at ``e614372``, and the optimized 3.10 working tree based on
``e614372``. Six independent processes ran serially in legacy/base/candidate/
candidate/base/legacy order. Each measured five passes per operation after
10,000 warmup points. Each median below pools all ten samples per backend
and operation; precision is 5. Input preparation and validation are excluded.
Python API overhead and output allocation/disposal are included.

.. list-table:: Median seconds per million forward conversions
   :header-rows: 1

   * - API
     - GEOTRANS 2.4.2
     - GEOTRANS 3.10
     - Optimized 3.10
     - Time versus 3.10
     - Time versus 2.4.2
   * - Scalar
     - 0.587154
     - 0.658236
     - 0.567969
     - -13.71%
     - -3.27%
   * - Batch
     - 0.329643
     - 0.381302
     - 0.287377
     - -24.63%
     - -12.82%

This recovers the forward performance regression from the GEOTRANS upgrade
on this workload. Optimized throughput was 1.76 million scalar conversions
per second and 3.48 million batch conversions per second. Inverse timings
were effectively unchanged versus unmodified 3.10: scalar time changed by
-0.48% and batch time by -0.04%. These sub-percent differences should be
treated as measurement variation. All four operations passed the existing
10% regression gate. Results on other machines and input distributions may
differ; the scalar improvement over 2.4.2 is relatively small.

All forward comparisons use the identical input coordinates. The two 3.10
backends also use identical inverse strings. Legacy inverse timings are not
compared because the older backend can generate different forward strings.
Raw timing samples, toolchain information, source identities, native binary
hashes, and validation hashes are retained in ``geotrans310-forward-results.json``.

Correctness
-----------

At every precision from 0 through 5, all 1,000,000 optimized forward results
matched unmodified GEOTRANS 3.10 byte for byte through both scalar and batch
APIs: six million exact comparisons per API. The one million precision-5
inverse coordinate pairs also matched byte for byte. Every timed run checked
all round trips and exact scalar/batch equivalence before timing. The maximum
3.10 round-trip error was 0.707465 metres, within the existing 3-metre bound.

``tests/test_geotrans_forward.py`` preserves upstream output examples for
every precision, including zero numeric fields, zero padding, single- and
double-digit zones, Norway/Svalbard, both poles, UPS without zone prefixes,
longitude wrapping, and grid-square boundaries near the truncation epsilon.
The optimization adds no new numerical behavior relative to GEOTRANS 3.10.

Reproducing measurements
-----------------------

Build isolated source trees using the same interpreter and compiler. The
existing ``benchmarks.build`` helper puts each extension into its own tree
without installing competing editable packages::

    CC=/usr/bin/clang CXX=/usr/bin/clang++ CFLAGS='-O3 -DNDEBUG' CXXFLAGS='-O3 -DNDEBUG' \
        python -m benchmarks.build --source /path/to/unmodified-checkout
    CC=/usr/bin/clang CXX=/usr/bin/clang++ CFLAGS='-O3 -DNDEBUG' CXXFLAGS='-O3 -DNDEBUG' \
        python -m benchmarks.build --source /path/to/optimized-checkout

Use ``benchmarks.ci.run_revision(source, dataset, output, repeats=5)`` with
the absolute path to the fixed CSV for each tree, serially in base/candidate/
candidate/base order. This helper isolates imports, verifies the loaded
source tree, and runs the scalar and batch scenarios. Pool the two reports
per backend with ``benchmarks.ci.combine_runs`` and compare them with
``benchmarks.performance.compare_results(candidate, base, 10)``. To repeat the
three-backend experiment, bracket those four runs with two legacy runs.
Use a fresh result directory and preserve every sample.

For a single installed-backend measurement, reuse the same CSV explicitly::

    python -m benchmarks run --dataset benchmarks/data/geotrans310-forward.csv \
        --scenario array --precision 5 --repeats 5 --output /tmp/mgrs-forward-run.json
