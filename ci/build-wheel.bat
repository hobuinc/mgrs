@echo off
call conda activate test
if errorlevel 1 exit /b %errorlevel%
python -m pip install build
if errorlevel 1 exit /b %errorlevel%
python -m build --wheel
