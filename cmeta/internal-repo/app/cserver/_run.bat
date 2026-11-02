@echo off
rem ---------------------------------------------------------------------------
rem  Which interpreter to run cserver with.
rem
rem  CMETA_PYTHON is exported by the `app` category and is the interpreter cMeta
rem  itself is running under. A bare "python" is not safe to assume: a
rem  `uv tool` install keeps its interpreter out of PATH by design (only the
rem  cx / cmeta / cserver shims go there), so "python" is not found even though
rem  cx works. It is also the only interpreter guaranteed to have cmeta
rem  importable, and - with the "server" extra - uvicorn too.
rem
rem  The fallback is for running this script by hand, outside cMeta.
rem ---------------------------------------------------------------------------

set "CSERVER_PYTHON=%CMETA_PYTHON%"
if not defined CSERVER_PYTHON set "CSERVER_PYTHON=python"

%PYTHON_PREFIX% "%CSERVER_PYTHON%" -c "import sys" >nul 2>&1
if errorlevel 1 (
  echo cserver: cannot run "%CSERVER_PYTHON%" - set CMETA_PYTHON to a Python interpreter. 1>&2
  exit /b 1
)

rem Install the web stack only when it is actually missing AND pip is there to
rem do it. A uv tool environment ships no pip, so the old unconditional
rem "python -m pip install -r requirements.txt" could only fail there - and the
rem right way to get these packages into such an install is the cmeta "server"
rem extra.
%PYTHON_PREFIX% "%CSERVER_PYTHON%" -c "import uvicorn, fastapi" >nul 2>&1
if errorlevel 1 (
  %PYTHON_PREFIX% "%CSERVER_PYTHON%" -m pip --version >nul 2>&1
  if errorlevel 1 (
    echo cserver: uvicorn/fastapi are missing and this environment has no pip. 1>&2
    echo cserver: reinstall cMeta with the "server" extra, for example: 1>&2
    echo cserver:   uv tool install --force "cmeta[server]" 1>&2
    echo cserver:   pip install "cmeta[server]" 1>&2
    exit /b 1
  )
  %PYTHON_PREFIX% "%CSERVER_PYTHON%" -m pip install -r requirements.txt
)

rem --param.host=tailscale: listen on this machine's Tailscale address alone, asked of Tailscale at each start (no
rem address in a script). Tailscale missing or stopped stops the start with its reason - never another address.
rem One-line ifs and no labels: this file has LF line endings, with which cmd can miss a label. -W: the package
rem imports the module that -m runs, and Python's RuntimeWarning about it says nothing here.
set "CSERVER_ON_TAILSCALE="
if /i "%CSERVER_HOST%"=="tailscale" set "CSERVER_ON_TAILSCALE=1"
if defined CSERVER_ON_TAILSCALE set "CSERVER_HOST="
if defined CSERVER_ON_TAILSCALE for /f "usebackq delims=" %%a in (`%PYTHON_PREFIX% "%CSERVER_PYTHON%" -W ignore::RuntimeWarning -m cmeta.utils.net tailscale_ipv4`) do set "CSERVER_HOST=%%a"
if defined CSERVER_ON_TAILSCALE if not defined CSERVER_HOST exit /b 1
if defined CSERVER_ON_TAILSCALE echo cMeta info: cserver listens on the Tailscale address %CSERVER_HOST%

%PYTHON_PREFIX% "%CSERVER_PYTHON%" -m uvicorn src.app:app --host %CSERVER_HOST% --port %CSERVER_PORT% %CSERVER_FLAGS%
