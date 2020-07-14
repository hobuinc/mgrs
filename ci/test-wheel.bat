
call conda activate test

pushd "%~dp0"

cd
dir dist
dir dist\mgrs*.whl

for /f "delims=" %%a in ('dir /s /b .\dist\mgrs*.whl') do set "wheel=%%a"

pip install pytest numpy
pip install %wheel%

cd mgrs\test


