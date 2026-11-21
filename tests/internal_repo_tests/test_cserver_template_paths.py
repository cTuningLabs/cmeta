"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

The cserver app finds its templates and static files from its own file, not from the current folder (2026-11-21): a
server whose current folder is elsewhere - started from another folder, or left in a folder that an upgrade in place
deleted under it - answered every templated page with 500 (TemplateNotFound: 'src/templates', favicon.ico missing).

The app runs in-process with FastAPI's TestClient against a fresh <CMETA_HOME> in tmp_path, from a folder that is not
its own. Skipped without the server extra (fastapi) or httpx, which the TestClient needs.
"""

import importlib.util
import os

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('httpx')

from fastapi.testclient import TestClient  # noqa: E402

import cmeta  # noqa: E402

APP_DIR = os.path.join(os.path.dirname(os.path.abspath(cmeta.__file__)), 'internal-repo', 'app', 'cserver')


def test_pages_render_when_the_server_stands_in_another_folder(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path / 'home'))
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)                      # not the app's folder: no src/ here

    spec = importlib.util.spec_from_file_location('cserver_app_paths_under_test', os.path.join(APP_DIR, 'src', 'app.py'))
    app_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app_module)
    try:
        with TestClient(app_module.app) as client:
            app_module.cfg.clear()                    # no password: the pages answer
            assert os.path.isabs(app_module.home_dir_templates) and os.path.isabs(app_module.home_dir_static)
            r = client.get('/favicon.ico')
            assert r.status_code == 200 and r.content
            r = client.get('/settings')
            assert r.status_code == 200 and '<html' in r.text.lower()
            r = client.get('/a-page-that-is-not-there')  # the error page is a template too
            assert r.status_code == 200 and 'a-page-that-is-not-there' in r.text
            r = client.get('/static/images/favicon.ico')
            assert r.status_code == 200
    finally:
        app_module.cm.shutdown()
