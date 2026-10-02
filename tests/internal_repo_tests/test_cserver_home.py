"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

Tests for "/" of the cserver app: the page named by `default_page` (by default /projects), the plain welcome
page when that is none or cannot be shown, and ?out=json.

The app runs in-process with FastAPI's TestClient against a fresh <CMETA_HOME> in tmp_path. Skipped without
the server extra (fastapi) or httpx, which the TestClient needs.
"""

import importlib.util
import os

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('httpx')

from fastapi.testclient import TestClient  # noqa: E402

import cmeta  # noqa: E402
from cmeta.version import __version__  # noqa: E402

APP_DIR = os.path.join(os.path.dirname(os.path.abspath(cmeta.__file__)), 'internal-repo', 'app', 'cserver')


@pytest.fixture()
def server(tmp_path, monkeypatch):
    """The cserver app module and a client, on a fresh home with an empty cserver config."""
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX',
                'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    monkeypatch.chdir(APP_DIR)                    # the app finds src/templates and src/static from its folder

    spec = importlib.util.spec_from_file_location('cserver_app_under_test', os.path.join(APP_DIR, 'src', 'app.py'))
    app_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app_module)
    try:
        with TestClient(app_module.app) as client:   # runs the startup event: reads the cserver config
            app_module.cfg.clear()                    # no password, no api_keys, default_page unset
            yield app_module, client
    finally:
        app_module.cm.shutdown()


def test_home_is_the_projects_page_with_the_welcome_under_it(server):
    _, client = server
    r = client.get('/')
    assert r.status_code == 200
    assert 'id="cpj"' in r.text                                   # the cards of cserver.projects
    assert 'Welcome to the cMeta server' in r.text and 'v' + __version__ in r.text
    assert '/projects/js/projects.js' in r.text                   # its assets and AJAX stay under /projects


def test_home_json_is_unchanged(server):
    _, client = server
    r = client.get('/?out=json')
    assert r.json() == {'return': 0, 'text': 'Welcome to the cMeta server v%s!' % __version__}


def test_projects_json(server):
    _, client = server
    j = client.post('/projects?native_action=projects', json={}).json()
    assert j['count'] == 0 and j['version'] == __version__


@pytest.mark.parametrize('value', ['none', '/no-such-page'])
def test_plain_welcome_when_there_is_no_default_page(server, value):
    app_module, client = server
    app_module.cfg['default_page'] = value
    r = client.get('/')
    assert r.status_code == 200
    assert 'class="cw"' in r.text and 'id="cpj"' not in r.text
    assert 'v' + __version__ in r.text
    for link in ('https://github.com/cTuningLabs/cmeta"', 'https://github.com/cTuningLabs/cmeta-aops"',
                 'https://cTuning.ai/project/cmeta"'):
        assert link in r.text


def test_api_keys_guard_the_list_but_not_the_welcome(server):
    app_module, client = server
    app_module.cfg['api_keys'] = ['k1']
    r = client.get('/')
    assert 'class="cw"' in r.text and 'id="cpj"' not in r.text     # no key: the welcome, as before
    r = client.get('/?api_key=k1')
    assert 'id="cpj"' in r.text
