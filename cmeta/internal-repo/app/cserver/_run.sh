#!/bin/sh
# POSIX sh, not bash: the `app` category sources this with ". ./_run.sh", which
# on Debian/Ubuntu means /bin/sh -> dash. Keep bashisms out ([[ ]], arrays).

# Which interpreter to run cserver with.
#
# CMETA_PYTHON is exported by the `app` category and is the interpreter cMeta
# itself is running under. That matters because a bare "python" is not safe to
# assume:
#
#   - a `uv tool` install keeps its interpreter out of PATH by design (only the
#     cx / cmeta / cserver shims go there), so "python" is simply not found even
#     though cx works;
#   - modern Linux ships python3 with no "python" alias at all.
#
# It is also the only interpreter guaranteed to have cmeta importable, and -
# with the "server" extra - uvicorn too. The fallbacks below are for running
# this script by hand, outside cMeta.
CSERVER_PYTHON="${CMETA_PYTHON:-}"

if [ -z "${CSERVER_PYTHON}" ]; then
    if command -v python3 >/dev/null 2>&1; then
        CSERVER_PYTHON=python3
    else
        CSERVER_PYTHON=python
    fi
fi

if ! ${PYTHON_PREFIX} "${CSERVER_PYTHON}" -c "import sys" >/dev/null 2>&1; then
    echo "cserver: cannot run '${CSERVER_PYTHON}' - set CMETA_PYTHON to a Python interpreter." >&2
    exit 1
fi

# Install the web stack, but only when it is actually missing AND pip is there
# to do it. A `uv tool` environment ships no pip at all, so the old
# unconditional "python -m pip install -r requirements.txt" could only ever
# fail there - and failing is the wrong answer anyway, because the way to get
# these packages into such an install is the cmeta "server" extra.
if ! ${PYTHON_PREFIX} "${CSERVER_PYTHON}" -c "import uvicorn, fastapi" >/dev/null 2>&1; then
    if ${PYTHON_PREFIX} "${CSERVER_PYTHON}" -m pip --version >/dev/null 2>&1; then
        ${PYTHON_PREFIX} "${CSERVER_PYTHON}" -m pip install -r requirements.txt
    else
        echo "cserver: uvicorn/fastapi are missing and this environment has no pip." >&2
        echo "cserver: reinstall cMeta with the 'server' extra, for example:" >&2
        echo "cserver:   uv tool install --force \"cmeta[server]\"" >&2
        echo "cserver:   pip install \"cmeta[server]\"" >&2
        exit 1
    fi
fi

# CSERVER_FLAGS comes from default_env in _cmeta.yaml, so the flags stay
# configurable rather than baked in - the way _run.bat has always done it.
# This script used to hardcode "--reload", so the two halves of the same app
# disagreed about its own defaults.
${PYTHON_PREFIX} "${CSERVER_PYTHON}" -m uvicorn src.app:app \
    --host "${CSERVER_HOST}" --port "${CSERVER_PORT}" ${CSERVER_FLAGS}
