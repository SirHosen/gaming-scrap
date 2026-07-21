@echo off
REM ---------------------------------------------------------------------------
REM  Windows helper that mirrors the Unix Makefile targets so `make check`
REM  (and friends) work without installing GNU Make.
REM
REM    cmd.exe     :  make check
REM    PowerShell  :  .\make.bat check
REM ---------------------------------------------------------------------------
setlocal
set "TARGET=%~1"
if "%TARGET%"=="" set "TARGET=help"

if /I "%TARGET%"=="help"        goto help
if /I "%TARGET%"=="install"     goto install
if /I "%TARGET%"=="install-dev" goto installdev
if /I "%TARGET%"=="test"        goto test
if /I "%TARGET%"=="lint"        goto lint
if /I "%TARGET%"=="type"        goto type
if /I "%TARGET%"=="health"      goto health
if /I "%TARGET%"=="check"       goto check
if /I "%TARGET%"=="run"         goto run
if /I "%TARGET%"=="clean"       goto clean
echo Unknown target: %TARGET%
echo Run "make.bat help" to list available targets.
exit /b 1

:help
echo NESTfetch - available commands:
echo    make install       Install the package (runtime only)
echo    make install-dev   Install package + dev/CI tooling
echo    make test          Run the offline test suite
echo    make lint          Lint with ruff
echo    make type          Type-check with mypy
echo    make health        Re-parse samples/ to detect config drift
echo    make check         Run every quality gate (lint + type + health + test)
echo    make run           Launch the interactive scraper
echo    make clean         Remove caches and build artifacts
exit /b 0

:install
pip install -e .
exit /b %ERRORLEVEL%

:installdev
pip install -e ".[async,config,dev]"
if errorlevel 1 exit /b 1
pip install -r requirements-dev.txt
exit /b %ERRORLEVEL%

:test
pytest
exit /b %ERRORLEVEL%

:lint
ruff check .
exit /b %ERRORLEVEL%

:type
mypy
exit /b %ERRORLEVEL%

:health
python -m nestfetch.healthcheck
exit /b %ERRORLEVEL%

:check
ruff check .
if errorlevel 1 exit /b 1
mypy
if errorlevel 1 exit /b 1
python -m nestfetch.healthcheck
if errorlevel 1 exit /b 1
pytest
exit /b %ERRORLEVEL%

:run
python -m nestfetch
exit /b %ERRORLEVEL%

:clean
for /d /r %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
if exist .pytest_cache rd /s /q .pytest_cache
if exist .mypy_cache rd /s /q .mypy_cache
if exist .ruff_cache rd /s /q .ruff_cache
exit /b 0
