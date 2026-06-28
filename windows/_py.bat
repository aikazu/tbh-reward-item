@echo off
REM windows\_py.bat — resolve a Python interpreter.
REM
REM Priority (anchored at this script's directory, not cwd):
REM   1. <repo>\.venv\Scripts\python.exe (if user created a venv there)
REM   2. py on PATH (Windows Python Launcher)
REM   3. python on PATH
REM
REM Exits non-zero with a helpful message if nothing is found.
REM
REM Usage 1 — run Python with forwarded args:
REM   windows\_py.bat -c "import sys; print(sys.executable)"
REM   windows\_py.bat -m tbh_desktop.main
REM
REM Usage 2 — print the resolved interpreter path (for caller scripts):
REM   for /f "delims=" %%I in ('call windows\_py.bat --which') do set "PY=%%I"

setlocal enabledelayedexpansion

REM %~dp0 = directory of this script, with trailing backslash.
REM Repo root = parent of windows\, so strip trailing \windows\ from %~dp0.
set "_PY_REPO_ROOT=%~dp0.."
pushd "%_PY_REPO_ROOT%" >nul 2>&1
if !errorlevel! neq 0 (
    echo [ERR] cannot cd to !_PY_REPO_ROOT!
    exit /b 1
)
set "_PY_REPO_ROOT=%CD%"
popd >nul

set "_PY_INTERP="
set "_PY_MODE=%~1"
if /i "!_PY_MODE!"=="--which" shift /1

REM 1. Honor .venv\ at the repo root if user already created one.
REM    Anchored to script location, NOT cwd — otherwise running from
REM    outside the repo could pick up a stale .venv in %CD%.
if exist "!_PY_REPO_ROOT!\.venv\Scripts\python.exe" (
    set "_PY_INTERP=!_PY_REPO_ROOT!\.venv\Scripts\python.exe"
    goto :_py_dispatch
)

REM 2. Windows Python Launcher (`py`)
where py >nul 2>&1
if !errorlevel! equ 0 (
    set "_PY_INTERP=py"
    goto :_py_dispatch
)

REM 3. python on PATH
where python >nul 2>&1
if !errorlevel! equ 0 (
    set "_PY_INTERP=python"
    goto :_py_dispatch
)

echo [ERR] no Python found. Install Python or create !_PY_REPO_ROOT!\.venv\
exit /b 127

:_py_dispatch
if /i "!_PY_MODE!"=="--which" (
    echo !_PY_INTERP!
    exit /b 0
)

%_PY_INTERP% %*