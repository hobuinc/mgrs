#!/bin/bash


python -m pip install pytest

for f in dist/*.whl
do

    python setup.py build
    python -m pip install $f
done;

ls
cd tests;
ls
pytest
