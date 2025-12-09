@echo off

setlocal

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

set "SCRIPT_NAME=%~n0"

set "PS_SCRIPT=%SCRIPT_DIR%\%SCRIPT_NAME%.ps1"

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%"

endlocal
