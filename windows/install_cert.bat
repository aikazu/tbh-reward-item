@echo off
REM install_cert.bat — install mitmproxy CA cert into Windows Trusted Root store.
REM Idempotent (certutil -f overwrites). Requires admin; auto-relaunches elevated.
REM
REM Usage:
REM   windows\install_cert.bat
REM
REM Env:
REM   MITMPROXY_CA_CERT  Override cert path (default: %USERPROFILE%\.mitmproxy\mitmproxy-ca-cert.cer)
setlocal enabledelayedexpansion
if defined MITMPROXY_CA_CERT (
    set "CERT=%MITMPROXY_CA_CERT%"
) else (
    set "CERT=%USERPROFILE%\.mitmproxy\mitmproxy-ca-cert.cer"
)
REM ── 1. Cert must exist ──────────────────────────────────────────────────────
if not exist "!CERT!" (
    echo [FAIL] cert not found: !CERT!
    echo   Run mitmdump once first to generate CA at %%USERPROFILE%%\.mitmproxy\
    exit /b 1
)
REM ── 2. Admin check (net session returns nonzero when not elevated) ──────────
net session >nul 2>&1
if !errorlevel! neq 0 (
    where powershell >nul 2>&1
    if !errorlevel! equ 0 (
        echo Not elevated. Relaunching as administrator...
        powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs -ArgumentList %*"
        exit /b 0
    ) else (
        echo [FAIL] this script requires administrator privileges.
        echo   Right-click install_cert.bat and choose "Run as administrator".
        exit /b 1
    )
)
REM ── 3. Install to Trusted Root Certification Authorities ────────────────────
echo Installing: !CERT!
certutil -addstore -f "Root" "!CERT!"
if !errorlevel! neq 0 (
    echo [FAIL] certutil failed.
    exit /b 1
)
echo.
echo [OK] mitmproxy CA installed to Trusted Root
echo.
echo Verify:
echo   certutil -store Root ^| findstr /i mitmproxy
echo.
echo NOTE: Firefox uses its own store. Import manually via about:preferences#privacy ^-^> Certificates ^-^> View Certificates ^-^> Import.
echo Remove later: windows\remove_cert.bat