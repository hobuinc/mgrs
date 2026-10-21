.. _home:

mgrs: Converting to and from MGRS and Decimal Degrees
------------------------------------------------------------------------------

GeoTrans_ provides C code for converting to and from MGRS, but well, it's
C code :). This package exposes scalar and batch GeoTrans_ conversions through
a pybind11_ extension. The C kernels are linked statically into that extension;
no separate libmgrs shared library or runtime Python dependencies are needed.

This library has an internal copy of some of the files from GeoTrans_ 2.4.2.

.. _`GeoTrans`: http://earth-info.nga.mil/GandG/geotrans/
.. _`pybind11`: https://pybind11.readthedocs.io/



ChangeLog
------------------------------------------------------------------------------

1.5.3

* Fix busted auto-release

1.5.2

* Use ABI name for finding DLL

1.5.1

* Wheels
* fix broken test with fixed precision comparison

1.5.0

* Wheels
* pyproject.toml-based metadata

1.4.3

* Wheels
* black, flake8, and isort linters

1.4.2

* GitHub Action builders needed to be changed to push release

1.4.1

* Fix install requirements #34

1.4.0

* Alias and deprecate RTreeError #33

1.3.9

* MGRS now requires packaging library #31
* Fix wheel imports of shared libs

1.3.8

* UTF-8 encoding for all strings.
* Fix #29 implicit tuple on return of UTMToMGRS

1.3.7

* automated building of osx, linux and win64 wheels
* Migrate from TravisCI => GitHub Actions
* Warnings cleanup
* flake8 validation

1.3.6

* required positional argument for wheel.425tags.get_platform()
  https://github.com/hobu/mgrs/pull/24

1.3.4

* Truncate, don't round results https://github.com/hobu/mgrs/pull/15
* Apply license

1.3.3

* SOABI support #10 https://github.com/hobu/mgrs/pull/10
* Clean up some compilation warnings
* Travis builds https://travis-ci.org/hobu/mgrs

1.3.2

* Better Windows support
* Bug fix for 3 digit longitudes

1.3.1

* Python 3.x support
* Allow user to override precision in UTMToMGRS


Usage
------------------------------------------------------------------------------

In a nutshell::

    >>> import mgrs

    >>> latitude = 42.0
    >>> longitude = -93.0

    >>> m = mgrs.MGRS()
    >>> c = m.toMGRS(latitude, longitude)
    >>> c
    '15TWG0000049776'

    >>> d = m.toLatLon(c)
    >>> d
    (41.999997975127997, -93.000000000000014)

    >>> y = '321942.29N'
    >>> yd = m.dmstodd(y)
    32.328414

    >>> d, m, s = m.ddtodms(32.328414)
    >>> d, m, s
    (32.0, 19.0, 42.290400)

You can also control the precision of the MGRS grid with the MGRSPrecision
arguments in .toMGRS().  Other than that, there isn't too much to it.

Building from source
------------------------------------------------------------------------------

Python 3.11 or later is required.

The build uses scikit-build-core and CMake with a C compiler and a C++17
compiler. GitHub Actions and the commands below use uv to install Python build
dependencies and obtain CMake/Ninja when needed::

    uv venv
    . .venv/bin/activate
    uv pip install .
    # Development install:
    uv pip install -e . pytest
    python -m pytest tests --doctest-glob='*.txt'

To produce both source and wheel distributions::

    uv build

Install uv using https://docs.astral.sh/uv/getting-started/installation/.
On Windows, activate with ``.venv\Scripts\activate`` instead. Standard PEP 517
frontends such as pip can also build and install the package.

``CMakeLists.txt`` defines a position-independent static ``mgrs_core`` library
and the ``mgrs._native`` pybind11 extension. Only the extension and Python
package are installed. CMake's normal compiler selection, toolchain files,
and build flags apply; no ``setup.py`` build is required. The scalar and batch
``MGRS`` methods and ``mgrs.core.MGRSError`` remain available. The internal
``mgrs.core.rt`` foreign-function handle has been removed.

Performance testing
------------------------------------------------------------------------------

The opt-in benchmark harness measures forward and inverse conversions over
a reproducible, randomized dataset of one million points distributed uniformly
over the globe's spherical surface. From a source checkout::

    python -m benchmarks generate
    python -m benchmarks run --output benchmarks/results/baseline.json
    python -m benchmarks run --baseline benchmarks/results/baseline.json

See `benchmarks/README.rst <benchmarks/README.rst>`_ for dataset generation,
timing methodology, JSON reports, and regression thresholds.
See `benchmarks/pybind11.rst <benchmarks/pybind11.rst>`_ for the measured
comparison with the previous ctypes binding.

Array conversion
------------------------------------------------------------------------------

The batch methods use Python's standard-library ``array.array`` and byte
buffers. They perform the entire conversion loop in C with one extension call::

    from array import array
    import mgrs

    converter = mgrs.MGRS()
    points = array("d", [42.0, -93.0, 89.0, 45.0])
    codes = converter.toMGRSArray(points)       # bytearray, 2 records of 15 bytes
    decoded = converter.toLatLonArray(codes)   # array('d'), 4 interleaved values

    # Read individual results when Python strings/tuples are needed:
    first_code = codes[:15].rstrip(b"\0").decode("ascii")
    first_latlon = tuple(decoded[:2])

``toMGRSArray(points, inDegrees=True, MGRSPrecision=5)`` accepts an
``array('d')`` containing interleaved latitude,longitude pairs. Compatible
buffers with native-endian 8-byte doubles and shape ``(2*N,)`` or ``(N, 2)``
are also supported. It returns a new ``bytearray`` containing one 15-byte
ASCII record per point, padded with NUL bytes for shorter codes. Full-length
records do not have a trailing terminator.

``toLatLonArray(codes, inDegrees=True, *, width=15)`` accepts a flat ``bytes``,
``bytearray``, or compatible byte buffer. Its length must be divisible by the
record width. The optional ``width`` accepts 1 through 15 bytes for externally
packed records; outputs from ``toMGRSArray`` always use 15. It returns a new
``array('d')`` of interleaved latitude,longitude pairs::

    decoded = converter.toLatLonArray(b"15TWG31NEA", width=5)

Inputs must be C-contiguous, and numeric inputs must be aligned for doubles.
They are read without copying and may be read-only. Use ``memoryview`` for
views and slices of existing buffers; materialize strided numeric data with
``array('d', values)`` before conversion. Lists, Unicode strings, and buffers
with the wrong element type or layout are rejected. Empty inputs work. Buffer
exports retain the input storage throughout conversion and are released on
success or failure. Do not mutate input values while conversion is in progress.

Invalid values raise ``mgrs.core.MGRSError`` with the first failing zero-based
row. No partial output is returned. NaN and infinite coordinates are rejected.
Latitude warnings are emitted once per batch, identifying the first affected
row. All scalar and batch conversion methods serialize access to GeoTrans's
shared projection state through a native mutex. The extension releases the GIL
during conversion, but calls
from multiple Python threads do not execute the projection code in parallel.
The batch adapter needs no additional dependencies or third-party array ABI.
