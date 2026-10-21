"""Check revision isolation, aggregation, and failure propagation in CI."""

import copy
import json
import os
import subprocess
import venv
from pathlib import Path

import pytest

from benchmarks import ci
from benchmarks import performance as perf


def report(source, samples=(1.0, 1.0)):
    return {
        "schema_version": perf.SCHEMA_VERSION,
        "created_at": "2026-10-21T00:00:00Z",
        "dataset": {"count": 4, "sha256": "dataset"},
        "config": {"repeats": len(samples), "timing": "test"},
        "validation": {"inverse_inputs_sha256": "codes"},
        "environment": {
            "source_root": str(source),
            "git_commit": source.name,
            "git_dirty": False,
            "python": "3.13.0",
            "implementation": "CPython",
            "platform": "test-platform",
            "machine": "x86_64",
            "hostname": "runner",
        },
        "native_library_sha256": source.name,
        "operations": {
            name: perf.summarize(list(samples), 4) for name in perf.OPERATIONS
        },
    }


def test_all_samples_are_pooled_without_mutating_runs(tmp_path):
    first = report(tmp_path, (1.0, 2.0))
    second = report(tmp_path, (3.0, 10.0))
    before = copy.deepcopy([first, second])
    combined = ci.combine_runs([first, second])
    assert combined["config"]["repeats"] == 4
    assert combined["operations"]["forward"]["seconds"] == [1, 2, 3, 10]
    assert combined["operations"]["forward"]["median_seconds"] == 2.5
    assert [first, second] == before


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("environment", "source_root", "wrong-tree"),
        ("environment", "git_commit", "different"),
        ("dataset", "sha256", "different"),
        ("validation", "inverse_inputs_sha256", "different"),
    ],
)
def test_inconsistent_runs_rejected(tmp_path, section, key, value):
    first = report(tmp_path)
    second = copy.deepcopy(first)
    second[section][key] = value
    with pytest.raises(ValueError):
        ci.combine_runs([first, second])


@pytest.mark.parametrize("samples", [[1], [1, 0], [1, float("nan")]])
def test_missing_or_invalid_samples_rejected(tmp_path, samples):
    first = report(tmp_path)
    first["operations"]["forward"]["seconds"] = samples
    with pytest.raises(ValueError, match="samples"):
        ci.combine_runs([first])


@pytest.fixture
def old_source(tmp_path):
    source = tmp_path / "old source tree"
    package = source / "mgrs"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        "from types import SimpleNamespace\n"
        "__version__ = 'old-tree-under-test'\n"
        "core = SimpleNamespace(rt=SimpleNamespace(_name=__file__))\n"
        "class MGRS:\n"
        "    def toMGRS(self, lat, lon, MGRSPrecision):\n"
        "        return f'0:{lat}:{lon}'\n"
        "    def toLatLon(self, code):\n"
        "        return tuple(map(float, code.split(':')[1:]))\n"
    )
    return source


def test_requested_tree_imported_without_its_own_harness(tmp_path, old_source):
    dataset = tmp_path / "global.csv"
    perf.generate_dataset(dataset, 4)
    result = ci.run_revision(old_source, dataset, tmp_path / "result.json", 1)
    assert result["mgrs_version"] == "old-tree-under-test"
    assert result["environment"]["source_root"] == str(old_source)
    assert not (old_source / "benchmarks").exists()


def test_editable_hook_cannot_override_revision(tmp_path, old_source):
    # A disposable environment reproduces scikit-build-core's .pth-installed
    # meta-path finder even when the test suite itself uses a regular wheel.
    env_path = tmp_path / "editable environment"
    venv.create(env_path, with_pip=False, symlinks=os.name != "nt")
    binary = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    executable = env_path / binary
    # Use the venv's installation directory: on Debian/Ubuntu, site also
    # lists dist-packages paths that need not exist in a new environment.
    site_packages = Path(
        subprocess.check_output(
            [
                str(executable),
                "-c",
                "import sysconfig; print(sysconfig.get_path('purelib'))",
            ],
            text=True,
        ).strip()
    )
    (site_packages / "test_editable_hook.py").write_text(
        "import sys\n"
        "class Finder:\n"
        "    def find_spec(self, fullname, path=None, target=None):\n"
        "        if fullname == 'mgrs' or fullname.startswith('mgrs.'):\n"
        "            raise RuntimeError('editable hook intercepted mgrs')\n"
        "sys.meta_path.insert(0, Finder())\n"
    )
    hook = site_packages / "test_editable_hook.pth"
    hook.write_text("import test_editable_hook\n")
    intercepted = subprocess.run(
        [str(executable), "-c", "import mgrs"],
        capture_output=True,
        text=True,
    )
    assert intercepted.returncode != 0
    assert "editable hook intercepted mgrs" in intercepted.stderr

    # Runtime dependencies in site-packages must remain importable, as the
    # historical ctypes implementation needs packaging.tags.
    (site_packages / "test_dependency.py").write_text("value = 42\n")
    with (old_source / "mgrs" / "__init__.py").open("a") as stream:
        stream.write("from test_dependency import value\nassert value == 42\n")
    dataset = tmp_path / "global.csv"
    output = tmp_path / "result.json"
    perf.generate_dataset(dataset, 4)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(ci.__file__).resolve().parents[1])
    subprocess.run(
        [
            str(executable),
            "-c",
            "import sys; from pathlib import Path; from benchmarks import ci; "
            "ci.run_revision(*(Path(p) for p in sys.argv[1:]), repeats=1)",
            str(old_source),
            str(dataset),
            str(output),
        ],
        env=env,
        check=True,
        timeout=30,
    )
    result = json.loads(output.read_text())
    assert result["mgrs_version"] == "old-tree-under-test"
    assert result["environment"]["source_root"] == str(old_source)


@pytest.fixture
def sources(tmp_path):
    paths = [tmp_path / "base", tmp_path / "candidate"]
    for path in paths:
        (path / "mgrs").mkdir(parents=True)
        (path / "mgrs" / "__init__.py").touch()
    return paths


@pytest.mark.parametrize("direction", [None, "forward", "inverse"])
def test_ci_order_reports_and_regression_exit(
    tmp_path, monkeypatch, sources, direction
):
    base, candidate = sources
    calls = []

    def run(source, dataset, output, repeats):
        calls.append(source.name)
        value = report(source)
        if source == candidate and direction:
            value["operations"][direction] = perf.summarize([2.0, 2.0], 4)
        return value

    monkeypatch.setattr(ci, "run_revision", run)
    output = tmp_path / "results"
    code = ci.main(
        [
            "--base",
            str(base),
            "--candidate",
            str(candidate),
            "--output",
            str(output),
            "--points",
            "4",
            "--repeats",
            "2",
        ]
    )
    assert code == (1 if direction else 0)
    assert calls == ["base", "candidate", "candidate", "base"]
    comparison = json.loads((output / "comparison.json").read_text())
    assert comparison["operations"][direction or "forward"]["regression"] == (
        direction is not None
    )
    assert (output / "base.json").exists()
    assert (output / "candidate.json").exists()
    expected = "FAIL" if direction else "PASS"
    assert expected in (output / "summary.md").read_text()


def test_child_failure_stops_comparison(tmp_path, monkeypatch, sources):
    base, candidate = sources
    calls = []

    def fail(*args):
        calls.append(args)
        raise subprocess.CalledProcessError(2, ["benchmark"])

    monkeypatch.setattr(ci, "run_revision", fail)
    output = tmp_path / "results"
    args = [
        "--base",
        str(base),
        "--candidate",
        str(candidate),
        "--output",
        str(output),
        "--points",
        "4",
    ]
    assert ci.main(args) == 2
    assert len(calls) == 1
    assert not (output / "comparison.json").exists()
    assert "failed" in (output / "summary.md").read_text()
    # A second invocation cannot accidentally consume partial/stale reports.
    assert ci.main(args) == 2
    assert len(calls) == 1


def test_git_metadata_comes_from_loaded_tree(tmp_path, monkeypatch):
    seen = []
    check_output = perf.subprocess.check_output

    def git(command, **kwargs):
        if command[0] != "git":
            return check_output(command, **kwargs)
        seen.append(kwargs["cwd"])
        return "revision" if command[-1] == "HEAD" else ""

    monkeypatch.setattr(perf.subprocess, "check_output", git)
    metadata = perf.environment(tmp_path)
    assert seen == [tmp_path, tmp_path]
    assert metadata["git_commit"] == "revision"
    assert metadata["source_root"] == str(tmp_path)


def with_arrays(value, seconds=0.25):
    value["array_config"] = {"points_storage": "array('d')", "timing": "array"}
    value["array_operations"] = {
        name: perf.summarize([seconds, seconds], 4) for name in perf.OPERATIONS
    }
    return value


def test_array_regression_and_missing_support(tmp_path):
    base = with_arrays(report(tmp_path))
    candidate = copy.deepcopy(base)
    candidate["array_operations"]["inverse"] = perf.summarize([0.5, 0.5], 4)
    changes = perf.compare_results(candidate, base, 10)
    assert changes["array_inverse"]["regression"]
    assert not changes["array_forward"]["regression"]
    assert not changes["inverse"]["regression"]
    with pytest.raises(ValueError, match="no longer supports"):
        perf.compare_results(report(tmp_path), base, 10)
    # A base that predates the API still participates in the scalar gate.
    assert set(perf.compare_results(candidate, report(tmp_path), 10)) == {
        "forward",
        "inverse",
    }


def test_array_aggregation_recomputes_speedup(tmp_path):
    first = with_arrays(report(tmp_path), 0.25)
    second = with_arrays(report(tmp_path), 0.5)
    result = ci.combine_runs([first, second])
    samples = result["array_operations"]["forward"]["seconds"]
    assert samples == [0.25, 0.25, 0.5, 0.5]
    assert result["array_speedup"]["forward"] == 1 / 0.375


@pytest.mark.parametrize(
    "seconds,exit_code",
    [(0.25, 0), (0.75, 1), (None, 2)],
)
def test_ci_array_speedup_gate(
    tmp_path,
    monkeypatch,
    sources,
    seconds,
    exit_code,
):
    base, candidate = sources

    def run(source, dataset, output, repeats):
        value = report(source)
        if source == candidate and seconds is not None:
            with_arrays(value, seconds)
        return value

    monkeypatch.setattr(ci, "run_revision", run)
    output = tmp_path / "results"
    args = [
        "--base",
        str(base),
        "--candidate",
        str(candidate),
        "--output",
        str(output),
        "--points",
        "4",
        "--repeats",
        "2",
        "--min-array-speedup",
        "2",
    ]
    assert ci.main(args) == exit_code
    if seconds is not None:
        result = json.loads((output / "comparison.json").read_text())
        assert result["array_speedup"]["forward"] == 1 / seconds
        assert result["min_array_speedup"] == 2
