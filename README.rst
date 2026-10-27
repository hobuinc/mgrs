.. _home:

mgrs: Converting to and from MGRS and Decimal Degrees
------------------------------------------------------------------------------

This package exposes scalar and batch GeoTrans_ conversions through
a pybind11_ extension. The Rust translation of GEOTRANS 3.10 is linked
statically into that extension; no separate libmgrs shared library or runtime
Python dependencies are needed. The C++ binding preserves the Python API;
all coordinate conversion runs in Rust.

The MGRS, UTM, UPS, Transverse Mercator and Polar Stereographic sources are
vendored from NGA's GEOTRANS 3.10 distribution. Source provenance and hashes
are recorded in ``libmgrs/geotrans3.10/SOURCE.json``. These C++ sources remain
as reference material and are not compiled into the Python extension.

Inverse conversion returns the center of the MGRS grid cell. See the 1.6.0
release notes below for the change from the previous southwest-corner convention.
The Rust backend retains that convention. Forward strings match the C++
backend on the fixed million-point dataset at all six precisions; inverse
coordinates can differ in their last floating-point digits. See the
`Python backend comparison <benchmarks/python-rust.rst>`_ for measurements.

.. _`GeoTrans`: http://earth-info.nga.mil/GandG/geotrans/
.. _`pybind11`: https://pybind11.readthedocs.io/

Rust and TypeScript
------------------------------------------------------------------------------

This repository also contains a native Rust translation of the WGS84 GEOTRANS
3.10 algorithms and a TypeScript/JavaScript package using that engine through
WebAssembly in Node.js and browsers. Both follow the Python scalar and batch
API, including cell-center inverse coordinates and ASCII whitespace handling.
Rust uses borrowed slices and owned vectors; TypeScript uses ``Float64Array``
and ``Uint8Array``. Neither requires Python or C++ at runtime.

See the `Rust guide <rust/README.md>`_, `TypeScript guide <typescript/README.md>`_,
`test coverage <rust/tests/fixtures/README.md>`_, and
`performance guide <benchmarks/rust-typescript.md>`_ for build instructions,
language-specific error/warning handling, and fixed-workload comparisons.
The release workflow attaches a Rust ``.crate`` and a TypeScript ``.tgz``
with Node/browser WebAssembly builds to each published GitHub release,
alongside the Python source distribution and all Python wheels. The workflow
publishes the Python packages to PyPI; Rust and TypeScript packages are
distributed as release downloads without publishing to crates.io or npm.

Run native tests from the repository root::

    cargo test --workspace --all-features --locked

After installing the WebAssembly toolchain described in the TypeScript guide::

    cd typescript
    npm ci
    npm test
    npx playwright install chromium
    npm run test:browser



ChangeLog
------------------------------------------------------------------------------

1.6.0

Changes since `1.5.4 <https://github.com/hobuinc/mgrs/releases/tag/1.5.4>`_.

**Inverse conversions now return the cell center.** GEOTRANS 3.10 replaces 2.4.2 and decodes MGRS coordinates to the center of the represented cell instead of its southwest corner. This applies to ``toLatLon``, ``toLatLonArray``, and ``MGRSToUTM``. `#57 <https://github.com/hobuinc/mgrs/pull/57>`_

The shift is half the cell width on each projected grid axis: **+0.5 m easting and northing at precision 5** (about 0.707 m diagonally), increasing to **+50 km per axis at precision 0**. Applications that compare exact decoded coordinates or use them as cell corners must account for this change.

* Accept leading, trailing, and internal ASCII whitespace in MGRS inputs; reject trailing junk and embedded NULs, preserving batch NUL padding. `#59 <https://github.com/hobuinc/mgrs/pull/59>`_
* Add ``toMGRSArray`` and ``toLatLonArray`` batch conversions. `#51 <https://github.com/hobuinc/mgrs/pull/51>`_
* Replace ctypes with pybind11, modernize builds, and require Python 3.11 or later. `#49 <https://github.com/hobuinc/mgrs/pull/49>`_, `#52 <https://github.com/hobuinc/mgrs/pull/52>`_
* Optimize GEOTRANS 3.10 formatting, recovering the forward-conversion slowdown on the benchmark workload without changing results. `#58 <https://github.com/hobuinc/mgrs/pull/58>`_
* Add reproducible performance benchmarks and CI regression checks; update wheel and artifact tooling. `#50 <https://github.com/hobuinc/mgrs/pull/50>`_, `#53 <https://github.com/hobuinc/mgrs/pull/53>`_, `#54 <https://github.com/hobuinc/mgrs/pull/54>`_, `#55 <https://github.com/hobuinc/mgrs/pull/55>`_, `#56 <https://github.com/hobuinc/mgrs/pull/56>`_

`Full changes since 1.5.4 <https://github.com/hobuinc/mgrs/compare/1.5.4...d3370da69879118723a054f2681e5842fcb6821b>`_

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

    >>> lat, lon = m.toLatLon(c)
    >>> '%.5f, %.5f' % (lat, lon)
    '42.00000, -92.99999'

    >>> y = '321942.29N'
    >>> yd = m.dmstodd(y)
    >>> '%.5f' % yd
    '32.32841'

    >>> d, m, s = m.ddtodms(32.328414)
    >>> (d, m, '%.2f' % s)
    (32.0, 19.0, '42.29')

You can also control the precision of the MGRS grid with the MGRSPrecision
arguments in .toMGRS().  Other than that, there isn't too much to it.

MGRS input accepts ASCII whitespace (spaces, tabs, and line breaks) before,
after, or between coordinate groups. ``toLatLon``, ``toWKT`` and ``MGRSToUTM`` remove
this whitespace before validating the complete coordinate and passing it
to GEOTRANS. Both ``str`` and ``bytes`` inputs are supported::

    >>> m = mgrs.MGRS()
    >>> lat, lon = m.toLatLon("  04QEJ 97987 90670  ")
    >>> '%.5f, %.5f' % (lat, lon)
    '21.61643, -158.05326'

Invalid characters, trailing text, and NUL bytes in scalar inputs raise
``mgrs.core.MGRSError`` rather than converting a partial coordinate.

Cell polygons
------------------------------------------------------------------------------

``toWKT(MGRS)`` returns the cell footprint as a WKT ``POLYGON``::

    >>> m = mgrs.MGRS()
    >>> polygon = m.toWKT("15TWG0000049776")
    >>> polygon.startswith("POLYGON ((")
    True

Coordinates are WGS84 **longitude latitude in degrees**, with no embedded SRID.
The ID determines the cell size: 100 km at precision 0 through 1 m at precision
5. The polygon covers the full UTM or UPS grid square, including portions beyond
zone and latitude-band boundaries. Its corners are derived from the projected
grid bounds, accounting for the half-cell offset used by ``toLatLon``.

The exterior ring is closed and counterclockwise. Curved projected edges are
sampled adaptively, targeting a 0.1 m midpoint error, so coarse cells generally
have more than four vertices. Coordinates are written to 12 decimal places;
the footprint is an approximation, not an exact representation of curved edges.

To preserve a single polygon across the antimeridian, longitudes are continuous
and may extend beyond -180 or +180 degrees. Do not wrap individual vertices:
split the geometry at the antimeridian if a consumer requires that longitude
range. Cells touching a pole include two vertices at latitude +90 or -90 with
different longitudes to represent the cell's wedge.

The method accepts ``str`` or ``bytes`` with the same whitespace, validation and
latitude-band warnings as ``toLatLon``. Rust exposes ``to_wkt(code)`` and
TypeScript exposes ``toWKT(code)`` with the same geometry conventions.

Building from source
------------------------------------------------------------------------------

Python 3.11 or later is required.

The build uses scikit-build-core and CMake. You must provide a C++17 compiler
and Rust/Cargo 1.85 or later on ``PATH`` before building (CI uses Rust 1.90.0).
The package does not install Rust automatically. Prebuilt wheels do not
require a Rust installation.

Install Rust with `rustup <https://rustup.rs/>`_. On macOS or Linux::

    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
    . "$HOME/.cargo/env"
    rustc --version
    cargo --version

On Windows, use the rustup installer from https://rustup.rs/, install the
Visual Studio C++ Build Tools when prompted, and open a new terminal so
``rustc`` and ``cargo`` are on ``PATH``.

Install uv using https://docs.astral.sh/uv/getting-started/installation/.
Then, from this repository's root, install the Python package with uv::

    uv venv
    . .venv/bin/activate
    uv pip install .

On Windows PowerShell, activate with ``.venv\Scripts\Activate.ps1`` instead.
uv installs Python build dependencies and the build backend obtains
CMake/Ninja when needed; Rust is supplied by your existing toolchain.
Standard PEP 517 frontends such as pip can also build and install the package.

For development, install in editable mode and run the tests. Repeat the
install command after changing Rust or C++ sources to rebuild the extension::

    uv pip install --reinstall-package mgrs -e . pytest
    python -m pytest tests --doctest-glob='*.txt'

To produce both source and wheel distributions::

    uv build

CI pins uv and cibuildwheel in ``ci/requirements.txt``. Dependabot checks
GitHub Actions daily and Python dependencies weekly, including the build
requirements in ``pyproject.toml`` and the pins in ``ci/requirements.txt``
and ``benchmarks/requirements-ci.txt``.

``CMakeLists.txt`` builds the ``mgrs-python`` Cargo crate as a static library
and links it into the ``mgrs._native`` pybind11 extension. Only the extension
and Python package are installed. Cargo uses the locked dependencies and
release profile; CMake's compiler flags apply to the C++ binding. Cross builds
require the matching Rust target installed with ``rustup target add``; set
``MGRS_RUST_TARGET`` for other CMake toolchains. macOS wheels target arm64 or
x86_64 separately. No ``setup.py`` build is required. The scalar and batch
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
See `benchmarks/geotrans310-forward.rst <benchmarks/geotrans310-forward.rst>`_
for the fixed million-point dataset and GEOTRANS 3.10 forward optimization.

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

ASCII whitespace within each record is removed before conversion; records
must still fit the selected width. NUL bytes are allowed only as trailing
padding, and any non-NUL data after the first NUL raises an error.

Inputs must be C-contiguous, and numeric inputs must be aligned for doubles.
They are read without copying and may be read-only. Use ``memoryview`` for
views and slices of existing buffers; materialize strided numeric data with
``array('d', values)`` before conversion. Lists, Unicode strings, and buffers
with the wrong element type or layout are rejected. Empty inputs work. Buffer
exports retain the input storage throughout conversion and are released on
success or failure. The binding copies input storage while holding the GIL,
then Rust reads that snapshot. As with other Python buffers, external native
code must not write concurrently while the snapshot is being taken.

Invalid values raise ``mgrs.core.MGRSError`` with the first failing zero-based
row. No partial output is returned. NaN and infinite coordinates are rejected.
Latitude warnings are emitted once per batch, identifying the first affected
row. Rust projection state is immutable and shared safely across calls. The
extension releases the GIL during conversion, so independent calls from Python
threads can run concurrently without a global projection mutex. Output is
written directly into the returned Python buffer. Snapshot storage adds
16 bytes per input point for forward batches or ``width`` bytes per inverse
record, released when the call finishes.
The batch adapter needs no additional dependencies or third-party array ABI.
