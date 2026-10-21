#!/bin/bash
set -euo pipefail

# Run inside a manylinux image; for example: build-wheel-linux.sh 3.13
version="${1:?Supply a Python version, for example 3.13}"
tag="${version//./}"
python_bin="/opt/python/cp${tag}-cp${tag}/bin/python"
cd /src
"$python_bin" -m pip wheel --no-deps --wheel-dir dist .
for wheel in dist/*.whl; do
    auditwheel repair "$wheel"
done
