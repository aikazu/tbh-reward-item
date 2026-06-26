@echo off
REM launch_desktop.bat — check readiness then launch TBH desktop app (Windows).
REM
REM Checks (stops at first failure):
REM   1. Python venv exists (.venv\)
REM   2. Desktop deps installed (PySide6, requests, bs4, playwright, cloakbrowser)
REM   3. mitmproxy installed (system or venv — needed for Start/Stop)
REM   4. src\config.json exists and is valid JSON
REM   5. CloakBrowser binary downloaded (optional — auto-downloads on first scrape)
REM
REM If any required check fails, it prints what's missing and how to fix it,
REM then exits 1. If all pass, launches the desktop app.
REM
REM Usage:
REM   windows\launch_desktop.bat          : checks + launch
REM   windows\launch_desktop.bat --check : checks only, no launch

setlocal enabledelayedexpansion

set "REPO_ROOT=%~dp0.."
cd /d "%REPO_ROOT%"

set "CHECK_ONLY=0"
if /i "%~1"=="--check" set "CHECK_ONLY=1"

set "ERRORS=0"

REM ── 1. Python venv ─────────────────────────────────────────────────────────
if not exist ".venv\Scripts\python.exe" (
    echo [FAIL] Python venv not found at .venv\
    echo   Fix: python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements-desktop.txt
    set /a ERRORS+=1
) else (
    echo [OK]  Python venv found
)

REM ── 2. Desktop deps ─────────────────────────────────────────────────────────
if exist ".venv\Scripts\python.exe" (
    for %%M in (PySide6 requests bs4 playwright cloakbrowser) do (
        .venv\Scripts\python -c "import %%M" >nul 2>&1
        if !errorlevel! equ 0 (
            echo [OK]  %%M installed
        ) else (
            echo [FAIL] %%M not installed
            echo   Fix: .venv\Scripts\pip install -r requirements-desktop.txt
            set /a ERRORS+=1
        )
    )
)

REM ── 3. mitmproxy ─────────────────────────────────────────────────────────────
where mitmdump >nul 2>&1
if !errorlevel! equ 0 (
    echo [OK]  mitmproxy found in PATH
) else (
    .venv\Scripts\python -c "import mitmproxy" >nul 2>&1
    if !errorlevel! equ 0 (
        echo [OK]  mitmproxy found in venv
    ) else (
        echo [WARN] mitmproxy not found — Start/Stop proxy won't work
        echo   Fix: .venv\Scripts\pip install mitmproxy
        REM Not fatal — app can still launch, just can't run proxy
    )
)

REM ── 4. config.json ──────────────────────────────────────────────────────────
REM Auto-generate config.json from config.default.json if missing (mirrors
REM the Linux launch_desktop.sh logic).
if not exist "src\config.json" if exist "src\config.default.json" (
    .venv\Scripts\python -c "import sys; sys.path.insert(0, r'%CD%\src'); from config_setup import ensure_config, CONFIG_PATH; ensure_config(CONFIG_PATH)" >nul 2>&1
    if exist "src\config.json" echo [OK]  src\config.json (auto-generated from config.default.json)
)

if not exist "src\config.json" (
    echo [FAIL] src\config.json not found
    echo   The proxy addon needs this file. Create one with the example format from README.
    set /a ERRORS+=1
) else (
    .venv\Scripts\python -c "import json; json.loads(open('src/config.json', encoding='utf-8-sig').read())" >nul 2>&1
    if !errorlevel! neq 0 (
        echo [FAIL] src\config.json is invalid JSON
        echo   Fix the file — the addon keeps last good config on invalid reload.
        set /a ERRORS+=1
    ) else (
        echo [OK]  src\config.json: valid
    )
)

REM ── 5. CloakBrowser binary (optional) ────────────────────────────────────────
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python -c "import cloakbrowser" >nul 2>&1
    if !errorlevel! equ 0 (
        .venv\Scripts\python -c "import cloakbrowser, os; p = cloakbrowser.ensure_binary(); exit(0 if (p and os.path.exists(p)) else 1)" >nul 2>&1
        if !errorlevel! equ 0 (
            echo [OK]  CloakBrowser binary downloaded
        ) else (
            echo [WARN] CloakBrowser binary not downloaded yet — will auto-download (~200MB) on first scrape
        )
    )
)

REM ── Summary ─────────────────────────────────────────────────────────────────
echo.
if !ERRORS! gtr 0 (
    echo [FAIL] !ERRORS! check(s) failed. Fix the issues above before launching.
    exit /b 1
)

echo [OK]  All checks passed. Ready to launch.
echo.

if "!CHECK_ONLY!"=="1" exit /b 0

echo Launching TBH desktop app...
.venv\Scripts\python -m tbh_desktop.main
