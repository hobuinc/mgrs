"""Read the Python release version and synchronize Cargo/npm metadata.

Uses only Python 3.11+ standard-library modules. Python builds call this as
a dynamic-metadata provider; run it directly before Cargo/npm packaging, or
use --check to detect drift and --artifacts DIR to verify release packages.
"""

import argparse
import ast
import json
import re
import tarfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = {
    "rust/Cargo.toml": "mgrs-geotrans",
    "rust/python/Cargo.toml": "mgrs-python",
}


def python_version(root):
    tree = ast.parse((root / "mgrs/__init__.py").read_text())
    values = [
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(getattr(t, "id", None) == "__version__" for t in node.targets)
    ]
    if len(values) != 1 or not isinstance(values[0], str):
        raise ValueError("Expected one literal __version__ assignment")
    return values[0]


def release_version(root, tag=None):
    version = python_version(root)
    number = r"(?:0|[1-9][0-9]*)"
    match = re.fullmatch(
        rf"({number}\.{number}\.{number})(?:(a|b|rc)({number}))?", version
    )
    if not match:
        raise ValueError("Version must be X.Y.Z, X.Y.ZaN, X.Y.ZbN or X.Y.ZrcN")
    if tag and tag.removeprefix("v") != version:
        raise ValueError(f"Tag {tag!r} does not match Python {version!r}")
    # Cargo and npm use SemVer prereleases; Python uses PEP 440 spellings.
    base, phase, serial = match.groups()
    suffix = {"a": "alpha", "b": "beta", "rc": "rc"}
    return f"{base}-{suffix[phase]}.{serial}" if phase else base


def cargo_version(text, name, version):
    pattern = rf'(^name = "{re.escape(name)}"\r?\nversion = ")[^"]+("$)'
    updated, count = re.subn(
        pattern, lambda m: m[1] + version + m[2], text, flags=re.MULTILINE
    )
    if count != 1:
        raise ValueError(f"Expected one Cargo version entry for {name}")
    return updated


def synchronize(root, version, check=False, *, include_npm=True):
    updates = {}
    for filename, name in PACKAGES.items():
        path = root / filename
        text = path.read_text()
        if tomllib.loads(text)["package"]["name"] != name:
            raise ValueError(f"Unexpected package name in {filename}")
        updates[path] = cargo_version(text, name, version)
    path = root / "Cargo.lock"
    text = path.read_text()
    for name in PACKAGES.values():
        text = cargo_version(text, name, version)
    updates[path] = text
    npm_files = ["package.json", "package-lock.json"] if include_npm else []
    for filename in npm_files:
        path = root / "typescript" / filename
        data = json.loads(path.read_text())
        if data["name"] != "mgrs-geotrans":
            raise ValueError(f"Unexpected package name in {filename}")
        data["version"] = version
        if filename == "package-lock.json":
            data["packages"][""]["version"] = version
        updates[path] = json.dumps(data, indent=2) + "\n"
    changed = [p for p, text in updates.items() if p.read_text() != text]
    if check and changed:
        names = ", ".join(str(p.relative_to(root)) for p in changed)
        raise ValueError(f"Package versions need synchronization: {names}")
    for path in changed:
        path.write_text(updates[path])
    return changed


def dynamic_metadata(settings, project):
    """Synchronize before scikit-build-core packages or builds Python."""
    if settings:
        raise ValueError("The version provider does not accept settings")
    # Python source distributions contain Rust but omit TypeScript sources.
    synchronize(
        ROOT,
        release_version(ROOT),
        include_npm=(ROOT / "typescript").is_dir(),
    )
    return {"version": python_version(ROOT)}


def verify_artifacts(directory, version):
    for extension, member, parser in [
        ("crate", f"mgrs-geotrans-{version}/Cargo.toml", tomllib.loads),
        ("tgz", "package/package.json", json.loads),
    ]:
        expected = directory / f"mgrs-geotrans-{version}.{extension}"
        archives = sorted(directory.glob(f"*.{extension}"))
        if archives != [expected]:
            raise ValueError(f"Expected only {expected.name}; got {archives}")
        with tarfile.open(expected, "r:gz") as archive:
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError(f"Missing {member} in {expected.name}")
            metadata = parser(stream.read().decode("utf-8"))
        if extension == "crate":
            metadata = metadata["package"]
        expected_metadata = ("mgrs-geotrans", version)
        if (metadata["name"], metadata["version"]) != expected_metadata:
            raise ValueError(f"Incorrect metadata inside {expected.name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--artifacts", type=Path)
    parser.add_argument("--tag", help="Require release tag to match Python")
    args = parser.parse_args()
    try:
        version = release_version(ROOT, args.tag)
        if args.artifacts is not None:
            verify_artifacts(args.artifacts, version)
        else:
            synchronize(ROOT, version, args.check)
    except (ValueError, KeyError, OSError, tarfile.TarError) as error:
        parser.error(str(error))
    print(f"Release package version: {version}")


if __name__ == "__main__":
    main()
