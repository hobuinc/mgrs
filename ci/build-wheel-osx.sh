#!/bin/bash
set -euo pipefail

cd /src
python -m pip install build delocate
python -m build --wheel
delocate-wheel -w wheels -v dist/*.whl
