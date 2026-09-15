@echo off
rem ---------------------------------------------------------------------------
rem  cMeta installer for Windows - installs cMeta FROM THIS DIRECTORY, not from
rem  PyPI and not from git.
rem
rem    install.bat
rem    install.bat -WithDeps
rem    install.bat -CmetaHome D:\CMETA -Aops
rem    install.bat -NoExtras
rem    install.bat -Help
rem
rem  This is only a launcher: all the work is in install.ps1 next to it, and
rem  every argument is passed straight through, so install.ps1 -Help is the
rem  authoritative list of options. "%~dp0" is this .bat file's own directory
rem  (with a trailing backslash), so the correct install.ps1 is found no matter
rem  which directory you run this from.
rem
rem  Why keep it when install.ps1 can be run directly:
rem    - a .bat can be double-clicked from Explorer; a .ps1 cannot;
rem    - -ExecutionPolicy Bypass applies to this one invocation only - it does
rem      not change the machine's policy - and is what lets a freshly copied
rem      script run on a default Windows install, where the policy is
rem      Restricted and "powershell -File install.ps1" would simply refuse;
rem    - -NoProfile keeps a user's PowerShell profile from altering PATH or the
rem      environment mid-install;
rem    - pwsh (PowerShell 7) is preferred when present, powershell 5.1 otherwise.
rem
rem  Copyright (C) 2025-2026 Grigori Fursin and cTuning Labs.
rem  Licensed under Apache-2.0 - see https://github.com/cTuningLabs/cmeta
rem ---------------------------------------------------------------------------

setlocal

set "_PS=powershell"
where pwsh >nul 2>&1 && set "_PS=pwsh"

"%_PS%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*

endlocal & exit /b %ERRORLEVEL%
