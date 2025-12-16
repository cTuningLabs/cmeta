#!/bin/bash

${PYTHON_PREFIX} python -m pip install -r requirements.txt
${PYTHON_PREFIX} python -m uvicorn src.app:app --host ${CSERVER_HOST} --port ${CSERVER_PORT} --reload
