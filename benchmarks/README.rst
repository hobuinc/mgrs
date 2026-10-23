Performance tests
=================

Run these commands from the repository root, with the local extension built::

    uv venv
    . .venv/bin/activate
    uv pip install -e .
    python -m benchmarks generate
    python -m benchmarks run --output benchmarks/results/baseline.json
    # After making a change, using the same interpreter and machine:
    python -m benchmarks run --baseline benchmarks/results/baseline.json \
        --output benchmarks/results/current.json --max-regression 10

The generator creates ``benchmarks/data/global.csv`` and its JSON manifest.
The default dataset has exactly **1,000,000 points** with seed ``20261021``.
It divides longitude and sin(latitude) into a 1,000 by 1,000 grid, chooses
one random point inside each cell, then shuffles the points. Each cell has
equal surface area on a sphere, so the sample does not cluster at the poles
as a uniform latitude sample would. Both hemispheres, all longitudes, and
the north and south UPS polar regions are included. This is spherical
equal-area sampling, not exact ellipsoidal equal-area sampling.

CSV coordinates are decimal degrees in latitude,longitude order. The manifest
records the seed, sampling version, grid dimensions, count, and SHA-256 of
the CSV. Keep both files together and reuse them across revisions. Generated
data and result files are ignored by Git; the generator is the reproducible
source of the workload. Existing datasets are never overwritten. To create
a different workload, use ``generate --output other.csv --points 2000000
--seed 42``. Non-square counts use the closest rectangular factorization.
Smaller counts are supported for smoke tests; use at least a million for
performance comparisons.

The GEOTRANS 3.10 forward optimization uses a separate fixed million-point
dataset with seed ``20261022``. Its checksum is recorded in
``geotrans310-forward-dataset.json``; see ``geotrans310-forward.rst`` for
generation commands and results.

Each run measures the public Python APIs serially, including their binding,
allocation, and encoding costs:

* Forward: ``MGRS.toMGRS(latitude, longitude, MGRSPrecision=5)``.
* Inverse: ``MGRS.toLatLon(mgrs_string)``.

Before timing, the harness loads and checks the CSV, prepares all inverse
strings, validates every round trip, and warms up each direction with 10,000
queries. Round-trip validation allows three cell widths (3 m at precision 5)
because MGRS truncates to a grid cell. Failed conversions or excessive errors
fail the run; points are never silently skipped. The result records the
maximum round-trip error and UTM/UPS coverage counts.

Five measured passes per direction each process the entire dataset. The
direction measured first alternates between passes. Generation, disk I/O,
inverse input preparation, validation, warmup, and report writing are excluded
from timings. Results are consumed by Python and discarded within each pass;
there is no growing output collection in the timed loops. Garbage collection
uses Python's normal settings. ``--repeats``, ``--warmup``, and ``--precision``
can be changed explicitly.

JSON reports contain every pass duration, median/min/max elapsed time,
queries/second, average microseconds/query derived from the median pass,
library version and binary checksum, Git revision and tracked dirty status,
Python/platform/host details, and the dataset identity. These are whole-pass
throughput measurements, not individual-query tail latency measurements.

Baseline comparisons use median elapsed time independently for each
direction. A slowdown strictly above ``--max-regression`` percent returns
exit code 1; a successful run returns 0; invalid data, failed validation, or
incompatible baselines return 2. Reports are saved even if baseline comparison
fails. Dataset identity, inverse strings, timing settings, host, OS, and Python
must match; the MGRS revision and binary may differ. Use an idle machine with
consistent power and build settings. Re-run a noisy comparison before treating
it as a regression. No background polling or scheduled monitoring is installed.

The inexpensive harness tests run with the normal suite::

    python -m pytest tests --doctest-glob='*.txt'

Locally, the full million-point performance test is opt-in via ``python -m
benchmarks run`` so ordinary tests do not enforce wall-clock thresholds. With
no ``--output``, reports use unique UTC timestamps under ``benchmarks/results/``.

GitHub Actions performance gate
-------------------------------

``.github/workflows/performance.yml`` runs the **Performance regression** job
on every pull request, merge queue group, push to main/master, and manual
dispatch. The comparison uses:

* Pull requests: the proposed merge commit versus the PR target's base SHA.
* Merge queues: the queue's head SHA versus its base SHA.
* Main/master pushes: the pushed SHA versus the branch's pre-push SHA.
* Manual runs: the selected workflow ref versus ``baseline_ref`` (branch,
  tag, or SHA), defaulting to the repository's default branch.

Both revisions are built from source on one ``ubuntu-24.04`` runner, with
Python 3.13, identical compiler flags, and the pinned dependencies in
``requirements-ci.txt``. The workflow builds both before timing and does not
reuse cached native binaries or historical timings. Both revisions are built
with ``uv build`` through their PEP 517 wheel backends, then only the native
binaries are placed in their respective source trees. This supports historical
setuptools/ctypes builds and scikit-build-core/pybind11 builds without competing
editable installs.
Each child process disables site initialization with ``python -S`` so installed
editable import hooks cannot redirect it to another checkout. Site-package
directories remain available as ordinary import paths for baseline dependencies,
after the requested source tree. The report verifies that import location.
The candidate's harness measures both revisions, so older baselines do not
need to contain benchmark code. Review changes to the harness and workflow
alongside changes to the library.

One shared million-point dataset is generated. Four independent benchmark
processes run in **base, candidate, candidate, base** order. Each performs
validation, warmup, and five measured passes per direction. All ten samples
per revision/direction are pooled and their median elapsed times compared.
A slowdown greater than **10% in either direction fails the job**. A build,
correctness, import, or comparison failure also fails it. There is no automatic
retry-until-pass behavior. Reversed ordering reduces systematic timing drift;
it does not eliminate shared-runner noise or provide a statistical confidence
guarantee. Inspect the raw sample spread when investigating a marginal failure.

Every completed comparison produces a job summary table and 30-day artifacts:
four raw reports, two aggregated reports, a comparison JSON, the dataset
manifest, the summary, benchmark logs, and compiler/dependency/CPU details.
Partial reports remain available when a run fails. The 36 MB CSV is regenerated
from its seed and excluded from artifacts. Jobs time out after 15 minutes;
superseded runs for the same PR/ref are cancelled. There are no scheduled jobs,
model calls, or external reporting services.

After the workflow has run once, configure the repository's branch protection
or ruleset to require **Performance regression** before merging, and require
branches to be up to date (or use the merge queue). Adding the workflow file
alone does not make its check mandatory. The workflow intentionally has no
PR path filter, since filtered-out required workflows can remain pending.
It uses ``pull_request`` with read-only repository permissions, no secrets,
and GitHub-hosted runners to accommodate fork contributions. It publishes
through job summaries and artifacts without posting PR comments.

Local reproduction with two checkouts::

    uv venv
    . .venv/bin/activate
    uv pip install -r benchmarks/requirements-ci.txt
    python -m benchmarks.build --source /path/to/base
    python -m benchmarks.build --source /path/to/candidate

    python -m benchmarks.ci --base /path/to/base --candidate /path/to/candidate \
        --output /tmp/mgrs-comparison --points 1000000 --repeats 5

Run from the checkout containing this harness. Output must be a new directory.
For a smoke test, lower ``--points``; the GitHub workflow explicitly uses one
million. Exit codes match the standalone harness: 0 pass, 1 slowdown, 2 error.

Keeping performance stable over time
------------------------------------

The initial 10% limit is an engineering threshold, not a measured noise floor.
Use several unchanged-revision manual comparisons to characterize runner
variance before tightening it. For reliable detection of smaller changes,
use consistent, isolated hardware; keep untrusted fork execution off persistent
self-hosted machines. A single Linux/Python combination is a practical first
gate; add Windows/macOS or other Python versions when platform-specific
performance is important, always comparing both revisions within each job.

Small regressions below the per-PR threshold can accumulate. Use manual runs
against a fixed release tag to measure cumulative drift with a freshly built
baseline on the same runner. Push artifacts provide a short-term history;
long-term trends require retaining/exporting those reports beyond 30 days.
Add separate polar, UTM, zone-boundary, and precision-specific workloads if
changes could disproportionately affect those paths: the global aggregate is
dominated by UTM points and can conceal a polar-only regression. Require review
of changes to benchmark settings, thresholds, and build flags so a performance
failure is resolved or deliberately accepted rather than obscured.

Array scenario
---------------

Measure scalar and array APIs on the same dataset using only standard-library
arrays and byte buffers::

    python -m benchmarks run --scenario array \
        --output benchmarks/results/array.json

This prepares interleaved ``array('d')`` coordinates and 15-byte, NUL-padded
``bytearray`` records outside timing, then checks **every** forward code and
inverse coordinate for exact equality with the scalar API. Timed batch passes
include input validation, output allocation, the native loop, and output disposal.
Input preparation, CSV I/O,
and conversion of byte arrays into Python strings/lists are excluded. The
reported improvement applies to callers consuming array outputs directly.

Reports include ``array_operations`` (the same sample/median/throughput fields
as scalar operations), ``array_config`` (buffer types, record width, and
validation method), and ``array_speedup`` (scalar median time divided by array
median time). The optional minimum-speedup gate returns 1 if either direction falls below the
requested ratio, and records the requirement and outcome in the JSON report.

CI runs the scenario automatically for revisions that expose both array APIs.
When both revisions expose the API, batch timings also participate in the
existing **10% regression gate**. CI compares all four absolute operation
timings against the baseline. Batch/scalar ratios remain informational: a faster
scalar binding can reduce that ratio even when batch throughput improves. The
optional ``--min-array-speedup`` flag remains available for explicit experiments.
A baseline predating the array API still runs
the scalar comparison; the summary explicitly identifies that the batch
baseline is unavailable. Removing an existing array API fails comparison.
The paired run pools ten batch samples per revision/direction, alongside the
scalar samples, and publishes both comparisons and the speedup in its summary.
The ordinary tests verify correctness and gate logic without wall-clock limits.
Reports from a different buffer layout or timing protocol are rejected as
incompatible; regenerate both reports with this harness when comparing revisions.
