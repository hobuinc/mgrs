"""Compare two built source trees on one machine, in A/B/B/A order."""

import argparse
import copy
import json
import math
import os
import subprocess
import sys
from pathlib import Path

from . import performance as perf

ORDER = ("base", "candidate", "candidate", "base")


def run_revision(source, dataset, output, repeats):
    """Use this harness for both revisions, even if the base predates it."""
    source = Path(source).resolve()
    env = os.environ.copy()
    # Run the script directly: its sys.path[0] is benchmarks/, not the
    # candidate checkout. The requested source tree supplies the mgrs import.
    env["PYTHONPATH"] = str(source)
    env["PYTHONNOUSERSITE"] = "1"
    subprocess.run(
        [
            sys.executable,
            str(Path(perf.__file__).resolve()),
            "run",
            "--dataset",
            str(dataset),
            "--output",
            str(output),
            "--repeats",
            str(repeats),
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
        for operation in perf.OPERATIONS:
            samples = report["operations"][operation]["seconds"]
            if len(samples) != report["config"]["repeats"] or not all(
                math.isfinite(value) and value > 0 for value in samples
            ):
                raise ValueError(f"invalid {operation} samples")
    combined = copy.deepcopy(first)
    combined["config"]["repeats"] *= len(runs)
    combined["config"]["timing"] += "-abba-pooled-v1"
    combined["run_started_at"] = [report["created_at"] for report in runs]
    for operation in perf.OPERATIONS:
        samples = [
            value
            for report in runs
            for value in report["operations"][operation]["seconds"]
        ]
        combined["operations"][operation] = perf.summarize(
            samples, first["dataset"]["count"]
        )
    return combined


def summary(base, candidate, comparison, threshold):
    lines = [
        "## MGRS performance comparison",
        "",
        f"Base: `{base['environment']['git_commit']}`  ",
        f"Candidate: `{candidate['environment']['git_commit']}`",
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
    for operation in perf.OPERATIONS:
        before = base["operations"][operation]["queries_per_second"]
        after = candidate["operations"][operation]["queries_per_second"]
        delta = comparison[operation]["change_percent"]
        status = "FAIL" if comparison[operation]["regression"] else "PASS"
        lines.append(
            f"| {operation} | {before:,.0f} | {after:,.0f} | "
            f"{delta:+.2f}% | {status} |"
        )
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
        perf.write_json(
            output / "comparison.json",
            {
                "schema_version": 1,
                "order": ORDER,
                "max_regression_percent": args.max_regression,
                "operations": comparison,
            },
        )
        rendered = summary(base, candidate, comparison, args.max_regression)
        (output / "summary.md").write_text(rendered)
        print(rendered)
        return int(any(item["regression"] for item in comparison.values()))
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
