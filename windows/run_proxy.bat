@echo off
setlocal
cd /d "%~dp0.."

REM Auto-generate config.json from config.default.json if missing.
if not exist "src\config.json" if exist "src\config.default.json" (
    where py >nul 2>nul
    if %errorlevel%==0 (
        py -c "import sys; sys.path.insert(0, r'%~dp0..\src'); from config_setup import ensure_config, CONFIG_PATH; ensure_config(CONFIG_PATH)" >nul 2>&1
    ) else (
        python -c "import sys; sys.path.insert(0, r'%~dp0..\src'); from config_setup import ensure_config, CONFIG_PATH; ensure_config(CONFIG_PATH)" >nul 2>&1
    )
    if exist "src\config.json" echo Generated src\config.json from config.default.json.
)

where py >nul 2>nul
if %errorlevel%==0 (
    py "%~dp0..\src\run_proxy.py"
) else (
    python "%~dp0..\src\run_proxy.py"
)

echo.
echo Proxy stopped.
pause
