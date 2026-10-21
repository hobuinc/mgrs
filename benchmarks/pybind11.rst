pybind11 versus ctypes
======================

The pybind11 branch ports the public scalar and batch methods to a C++ extension
and statically links the existing C projection kernels. Numeric results remain
``array('d')`` and string results remain fixed-width byte buffers. There are no
runtime Python package dependencies.

Local comparison
----------------

Measured against the merged ctypes baseline ``c53dcf9`` using the pybind11
working tree, CPython 3.12.15, macOS 26.5.2, and Apple M4 ARM64. Both builds used
Apple Clang, ``-O3 -DNDEBUG``, and a macOS 11.0 deployment target. The C++ binding
uses C++17; optional pybind11 LTO is disabled. Build tooling: scikit-build-core
1.1.1, pybind11 3.1.0, CMake 4.4.4, Ninja 1.13.2; baseline setuptools 84.2.1.

The same seeded one-million-point equal-area global dataset was used for both
builds. Four independent processes ran in base/candidate/candidate/base order,
each with five measured passes per direction after validation and warmup. The
table gives median seconds for the full million-point pass, pooling all ten
samples per operation. Input preparation is excluded; public API overhead and
output allocation/disposal are included.

.. list-table:: Median time per million points
   :header-rows: 1

   * - Operation
     - ctypes (seconds)
     - pybind11 (seconds)
     - Throughput ratio
   * - Scalar forward
     - 1.011144
     - 0.592773
     - 1.71x
   * - Scalar inverse
     - 2.028672
     - 1.172850
     - 1.73x
   * - Batch forward
     - 0.334934
     - 0.332108
     - 1.01x
   * - Batch inverse
     - 1.074997
     - 1.061669
     - 1.01x

Scalar elapsed time decreased by about 41% forward and 42% inverse. Batch
throughput was effectively unchanged: the 1% differences are small enough to
be runner noise. All four operations passed the 10% regression limit. These
are results from one machine, not a guarantee for other platforms.

Every batch output matched its scalar equivalent across all million points.
An additional 12,108 coordinate cases across precisions 0 through 5 and both
degrees/radians, plus UTM conversions, matched the previous binding exactly
(including existing conversion errors at coarse precisions). The canonical
result digest was:
``bc34c8e39df534f94e37306b3342b2a2687d6d97a0a572bb7641b78b620b074a``.

The measured native binary SHA-256 values were:

* ctypes: ``f802a81230bc778b2a73be4019e4053202ce874dca3f115f3e50a335edf23e3e``
* pybind11: ``8cf6015ed6e847f9d62de30c8936427b5d6bb516aefdc461a887099d7754eaf8``

Reproducing the comparison
-------------------------

Use two separate checkouts and the same interpreter/compiler for both::

    python -m pip install -r benchmarks/requirements-ci.txt
    python -m benchmarks.build --source /path/to/ctypes-checkout
    python -m benchmarks.build --source /path/to/pybind11-checkout
    python -m benchmarks.ci --base /path/to/ctypes-checkout \
        --candidate /path/to/pybind11-checkout --output /tmp/mgrs-comparison \
        --points 1000000 --repeats 5 --max-regression 10

The builder uses each revision's wheel backend and copies only the compiled
native binaries into its own checkout. Neither package is installed as an
editable dependency in the shared benchmark environment. Reports verify the
loaded source tree and native binary checksum.

CI retains independent regression gates for scalar forward/inverse and batch
forward/inverse. The old 1.5x batch-over-scalar requirement is removed because
faster scalar bindings reduce that ratio without slowing batch conversion.
The ratio is still reported (1.78x forward, 1.10x inverse in this run), and an
explicit ``--min-array-speedup`` remains available for controlled experiments.
