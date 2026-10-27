# Legacy GEOTRANS C/C++ backend

This directory is no longer used by the Python package build. Its C/C++ conversion code is not compiled or linked into `mgrs._native`. Python now uses the [Rust GEOTRANS 3.10 implementation](../rust/README.md), linked through the existing pybind11 interface.

The GEOTRANS sources and legacy adapters remain in the repository for provenance, reference, and numerical and performance comparisons with the Rust implementation. They are intentionally retained and should not be removed merely because the current build no longer uses them.

The [GEOTRANS source notes](geotrans3.10/README.rst) describe the bundled source subset and local modifications. [SOURCE.json](geotrans3.10/SOURCE.json) records the original NGA archive and source-file hashes. Existing source notices are preserved.
