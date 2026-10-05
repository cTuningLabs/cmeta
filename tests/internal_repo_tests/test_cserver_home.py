"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

Tests for "/" of the cserver app: the page named by `default_page` (by default /projects), the plain welcome
page when that is none or cannot be shown, and ?out=json.

The app runs in-process with FastAPI's TestClient against a fresh <CMETA_HOME> in tmp_path. Skipped without
the server extra (fastapi) or httpx, which the TestClient needs.
"""

import importlib.util
import inspect
import os
from types import SimpleNamespace

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
    assert j['count'] == 1 and j['version'] == __version__      # the engine's cserver.browse


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


def _req(**headers):
    return SimpleNamespace(headers={k.replace('_', '-'): v for k, v in headers.items()})


def test_the_host_must_name_this_machine_and_the_page_must_be_ours(server):
    app_module, _ = server
    for host in ('localhost:8004', '127.0.0.1:8004', '[::1]:8004', 'app.localhost', 'localhost'):
        assert app_module._host_local(_req(host=host)), host
    for host in ('rebound.example:8004', '192.168.1.5:8004', 'localhost.example.com', ''):
        assert not app_module._host_local(_req(host=host)), host        # DNS rebinding comes with its own name

    assert app_module._same_origin(_req(host='localhost:8004'))                     # no browser: the CLI, curl
    assert app_module._same_origin(_req(host='localhost:8004', sec_fetch_site='same-origin'))
    assert app_module._same_origin(_req(host='localhost:8004', sec_fetch_site='none'))  # a typed address
    for site in ('cross-site', 'same-site'):                                       # another port is another app
        assert not app_module._same_origin(_req(host='localhost:8004', sec_fetch_site=site))
    assert app_module._same_origin(_req(host='localhost:8004', origin='http://localhost:8004'))
    assert not app_module._same_origin(_req(host='localhost:8004', origin='http://other.example'))


def test_open_a_folder_through_the_app(server):
    app_module, _ = server
    if 'client' not in inspect.signature(TestClient.__init__).parameters:
        pytest.skip('this Starlette TestClient cannot pose as a loopback client')
    # The category cserver.browse itself: an artifact of every home. (Not one made here: on Linux, Python 3.14
    # starts the app's worker processes from a forkserver made by an earlier test, with that test's CMETA_HOME.)
    body = {'uid': '14b2334988864507', 'what': 'folder', 'dry': '1'}
    with TestClient(app_module.app, base_url='http://localhost:8004', client=('127.0.0.1', 50000)) as local:
        app_module.cfg.clear()
        j = local.post('/browse?native_action=open', json=body, headers={'Sec-Fetch-Site': 'same-origin'}).json()
        assert j.get('dry') or 'desktop' in j.get('error', '') or 'found' in j.get('error', ''), j
        j = local.post('/browse?native_action=open', json=body, headers={'Sec-Fetch-Site': 'cross-site'}).json()
        assert 'did not come from a page of this server' in j['error']
        j = local.post('/browse?native_action=open', json=body, headers={'Host': 'rebound.example:8004'}).json()
        assert 'server\'s own machine' in j['error']                      # a loopback peer under another name
    with TestClient(app_module.app) as remote:                             # 'testclient': not this machine
        app_module.cfg.clear()
        j = remote.post('/browse?native_action=open', json=body, headers={'Sec-Fetch-Site': 'same-origin'}).json()
        assert 'server\'s own machine' in j['error']
