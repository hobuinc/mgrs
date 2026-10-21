"""Compare two built source trees on one machine, in A/B/B/A order."""

import argparse
import copy
import json
import math
import os
import site
import subprocess
import sys
from pathlib import Path

from . import performance as perf

ORDER = ("base", "candidate", "candidate", "base")


def run_revision(source, dataset, output, repeats):
    """Use this harness for both revisions, even if the base predates it."""
    source = Path(source).resolve()
    env = os.environ.copy()
    # Skip site initialization so editable-install .pth hooks cannot redirect
    # mgrs to another checkout. Add site-package directories as ordinary paths
    # for historical runtime dependencies (such as packaging), without running
    # their .pth files. The requested source tree always comes first.
    env["PYTHONPATH"] = os.pathsep.join([str(source), *site.getsitepackages()])
    env["PYTHONNOUSERSITE"] = "1"
    subprocess.run(
        [
            sys.executable,
            "-S",
            str(Path(perf.__file__).resolve()),
            "run",
            "--dataset",
            str(dataset),
            "--output",
            str(output),
            "--repeats",
            str(repeats),
            "--scenario",
            "auto",
        ],
        cwd=source,
        env=env,
        check=True,
        timeout=300,
    )
    report = json.loads(output.read_text())
    if report["environment"]["source_root"] != str(source):
        raise ValueError("benchmark imported the wrong source tree")
    return report


def combine_runs(runs):
    """Pool all timed passes; never select only the fastest invocation."""
    first = runs[0]
    for report in runs:
        perf.compare_results(report, first, 0)
        for key in ("git_commit", "git_dirty", "source_root"):
            if report["environment"][key] != first["environment"][key]:
                raise ValueError(f"revision changed between runs: {key}")
        if report["native_library_sha256"] != first["native_library_sha256"]:
            raise ValueError("native library changed between runs")
        for group in ("operations", "array_operations"):
            if (group in report) != (group in first):
                raise ValueError("array support changed between runs")
            if group not in report:
                continue
            for operation in perf.OPERATIONS:
                samples = report[group][operation]["seconds"]
                if len(samples) != report["config"]["repeats"] or not all(
                    math.isfinite(value) and value > 0 for value in samples
                ):
                    raise ValueError(f"invalid {operation} samples")
    combined = copy.deepcopy(first)
    combined["config"]["repeats"] *= len(runs)
    combined["config"]["timing"] += "-abba-pooled-v1"
    combined["run_started_at"] = [report["created_at"] for report in runs]
    for group in ("operations", "array_operations"):
        if group not in first:
            continue
        for operation in perf.OPERATIONS:
            samples = [
                value
                for report in runs
                for value in report[group][operation]["seconds"]
            ]
            combined[group][operation] = perf.summarize(
                samples, first["dataset"]["count"]
            )
    if "array_operations" in combined:
        combined["array_speedup"] = perf.array_speedups(combined)
    return combined


def summary(base, candidate, comparison, threshold, min_speedup=None):
    def revision(report):
        value = report["environment"]["git_commit"]
        suffix = ""
        if report["environment"].get("git_dirty"):
            suffix = " (working tree changes)"
        return f"`{value}`{suffix}"

    lines = [
        "## MGRS performance comparison",
        "",
        f"Base: {revision(base)}  ",
        f"Candidate: {revision(candidate)}",
        "",
        f"{base['dataset']['count']:,} points; "
        f"{base['config']['repeats']} timed passes per revision/direction. "
        "Order: base, candidate, candidate, base.",
        "",
        f"Allowed slowdown: **{threshold:g}%** in each direction. "
        "Positive change means slower. Medians use all passes.",
        "",
        "| Operation | Base queries/s | Candidate queries/s | "
        "Time change | Result |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for name, change in comparison.items():
        group = "operations"
        if name.startswith("array_"):
            group = "array_operations"
        operation = name.removeprefix("array_")
        before = base[group][operation]["queries_per_second"]
        after = candidate[group][operation]["queries_per_second"]
        delta = change["change_percent"]
        status = "FAIL" if change["regression"] else "PASS"
        row = f"| {name} | {before:,.0f} | {after:,.0f} | "
        lines.append(row + f"{delta:+.2f}% | {status} |")
    speedups = perf.array_speedups(candidate)
    if speedups:
        lines += ["", "### Candidate array speedup over scalar", ""]
        if "array_operations" not in base:
            lines += [
                "Base revision has no array API; new scenario validated "
                "against candidate scalar results.",
                "",
            ]
        for operation, speedup in speedups.items():
            status = "informational" if min_speedup is None else "PASS"
            if min_speedup is not None and speedup < min_speedup:
                status = "FAIL"
            lines.append(f"* {operation}: **{speedup:.2f}x** ({status})")
        if min_speedup is not None:
            lines += ["", f"Required minimum: {min_speedup:g}x."]
    lines += [
        "",
        "Both revisions passed full round-trip validation. "
        "Raw samples, source revisions, dataset identity, and toolchain "
        "details are available in the workflow artifact.",
        "",
        "For a suspected noisy failure, inspect all samples and repeat the "
        "entire paired comparison. Do not retry only the candidate.",
        "",
    ]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--points", type=perf.positive_int, default=1_000_000)
    parser.add_argument("--repeats", type=perf.positive_int, default=5)
    parser.add_argument("--max-regression", type=perf.percentage, default=10)
    parser.add_argument("--min-array-speedup", type=perf.positive_float)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    try:
        # Refuse stale results instead of mixing two independent comparisons.
        output.mkdir(parents=True, exist_ok=False)
    except OSError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    try:
        sources = {
            "base": args.base.resolve(),
            "candidate": args.candidate.resolve(),
        }
        for source in sources.values():
            if not (source / "mgrs" / "__init__.py").is_file():
                raise ValueError(f"missing mgrs source tree: {source}")
        dataset = output / "global.csv"
        perf.generate_dataset(dataset, args.points)
        runs = {"base": [], "candidate": []}
        for index, revision in enumerate(ORDER, 1):
            print(f"\nRun {index}/4: {revision}", flush=True)
            report = run_revision(
                sources[revision],
                dataset,
                output / f"{index}-{revision}.json",
                args.repeats,
            )
            runs[revision].append(report)
        base = combine_runs(runs["base"])
        candidate = combine_runs(runs["candidate"])
        perf.write_json(output / "base.json", base)
        perf.write_json(output / "candidate.json", candidate)
        comparison = perf.compare_results(candidate, base, args.max_regression)
        speedups = perf.array_speedups(candidate)
        if args.min_array_speedup is not None and not speedups:
            raise ValueError("candidate must support the array scenario")
        perf.write_json(
            output / "comparison.json",
            {
                "schema_version": 1,
                "order": ORDER,
                "max_regression_percent": args.max_regression,
                "operations": comparison,
                "array_speedup": speedups,
                "min_array_speedup": args.min_array_speedup,
            },
        )
        rendered = summary(
            base,
            candidate,
            comparison,
            args.max_regression,
            args.min_array_speedup,
        )
        (output / "summary.md").write_text(rendered)
        print(rendered)
        regressed = any(item["regression"] for item in comparison.values())
        if args.min_array_speedup is not None:
            minimum = args.min_array_speedup
            regressed |= any(s < minimum for s in speedups.values())
        return int(regressed)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        (output / "summary.md").write_text(
            "## MGRS performance comparison failed\n\n"
            "No passing performance decision was produced. Inspect the "
            "workflow log and any partial reports in the artifact.\n"
        )
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
