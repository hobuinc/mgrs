#!/bin/bash


PYPREFIX=$(python -c "import sys; print(sys.prefix)")
python -c "import sys; print(sys.version)"
echo "PYPREFIX: " $PYPREFIX
python -m pip install delocate

PREFIX=$(pwd)

cd /src
pwd
python -m pip install . -t .
python setup.py bdist_wheel

delocate-wheel -w wheels -v dist/*.whl
