
call conda activate test

where python


python -m pip install . -t .
python setup.py bdist_wheel
