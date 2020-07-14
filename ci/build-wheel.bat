
call conda activate test
cd ..

where python

pushd "%~dp0"

python setup.py bdist_wheel
popd
