NGA GEOTRANS 3.10 source subset
==============================

These 45 source/header files were originally copied byte-for-byte from the user's
NGA ``geotrans-download.tgz`` archive, whose top-level directory is
``geotrans3.10``. Only MGRS and its projection, coordinate, parameter and
exception dependencies are included. The original directory layout beneath
``CCS/src/dtcc`` and all source notices are preserved.

``SOURCE.json`` records the archive SHA-256 and each original archive member
name and original file SHA-256. These hashes describe the upstream sources;
local modifications are documented below rather than replacing those hashes.
The separate ``../mgrs.cpp`` adapter implements the existing C-facing MGRS
API, translates upstream exceptions/warnings, and manages returned objects.
``../batch.c`` continues to implement the batch API using those entry points.

Inverse conversions retain GEOTRANS 3.10's cell-center behavior and updated
projection algorithms. The adapter does not subtract offsets or otherwise
adjust results to match the older test expectations.

Local modifications
-------------------

``CoordinateSystems/mgrs/MGRS.cpp`` writes the validated zone and numeric
fields directly into the output string instead of calling ``snprintf``.
This preserves zero padding, precision-zero strings, and the absence of a
zone prefix for UPS. The existing projection, truncation, epsilon, and
cell-center calculations are unchanged. See ``../../benchmarks/geotrans310-forward.rst``
for the fixed dataset, equivalence checks, and performance measurements.
