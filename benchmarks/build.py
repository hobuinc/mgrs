"""Build a revision's wheel and put only its native binaries in its checkout.

This supports both historical setuptools builds and scikit-build-core without
installing competing editable packages into the benchmark interpreter.
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def unpack_native(wheel, source):
    source = Path(source).resolve()
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        members = [name for name in names if name.endswith((".so", ".pyd"))]
        if not members:
            raise ValueError("wheel contains no native extension")
        targets = [(name, (source / name).resolve()) for name in members]
        if any(not target.is_relative_to(source) for name, target in targets):
            raise ValueError("wheel contains an unsafe native path")
        for name, target in targets:
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(name) as data, target.open("wb") as output:
                shutil.copyfileobj(data, output)
    return [target for name, target in targets]


def build_revision(source):
    source = Path(source).resolve()
    with tempfile.TemporaryDirectory(prefix="mgrs-wheel-") as directory:
        subprocess.run(
            [
                "uv",
                "build",
                "--wheel",
                "--python",
                sys.executable,
                "--no-build-isolation",
                "--no-cache",
                "--out-dir",
                directory,
                str(source),
            ],
            check=True,
        )
        wheels = list(Path(directory).glob("*.whl"))
        if len(wheels) != 1:
            raise ValueError("expected exactly one built wheel")
        return unpack_native(wheels[0], source)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args(argv)
    for path in build_revision(args.source):
        print(path)


if __name__ == "__main__":
    main()
