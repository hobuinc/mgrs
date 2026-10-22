NGA GEOTRANS 3.10 source subset
==============================

These 45 source/header files were copied byte-for-byte from the user's
NGA ``geotrans-download.tgz`` archive, whose top-level directory is
``geotrans3.10``. Only MGRS and its projection, coordinate, parameter and
exception dependencies are included. The original directory layout beneath
``CCS/src/dtcc`` and all source notices are preserved.

``SOURCE.json`` records the archive SHA-256 and each original archive member
name and file SHA-256. The vendored sources have no local modifications.
The separate ``../mgrs.cpp`` adapter implements the existing C-facing MGRS
API, translates upstream exceptions/warnings, and manages returned objects.
``../batch.c`` continues to implement the batch API using those entry points.

Inverse conversions retain GEOTRANS 3.10's cell-center behavior and updated
projection algorithms. The adapter does not subtract offsets or otherwise
adjust results to match the older test expectations.
