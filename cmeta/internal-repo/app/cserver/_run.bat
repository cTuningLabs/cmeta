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

%PYTHON_PREFIX% "%CSERVER_PYTHON%" -m uvicorn src.app:app --host %CSERVER_HOST% --port %CSERVER_PORT% %CSERVER_FLAGS%
