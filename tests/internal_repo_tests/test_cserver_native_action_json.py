"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

A page's request for JSON gets JSON when the engine's call fails (2026-11-23): the home page on a tablet showed
"Unexpected token '<'" - its ?native_action=projects had been answered with the HTML error page. A request that
wants JSON (native_action, force_json, out=json, an Accept of JSON) gets {"return": ..., "error": ...}; a page asked
for in a browser still gets the error page. The app runs in-process with FastAPI's TestClient against a fresh
<CMETA_HOME>, the category answered by a stand-in for the engine's access. Skipped without fastapi or httpx.
"""

import asyncio
import importlib.util
import os

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('httpx')

from fastapi.testclient import TestClient  # noqa: E402

import cmeta  # noqa: E402

APP_DIR = os.path.join(os.path.dirname(os.path.abspath(cmeta.__file__)), 'internal-repo', 'app', 'cserver')


@pytest.fixture()
def app(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path / 'home'))
    monkeypatch.chdir(APP_DIR)
    spec = importlib.util.spec_from_file_location('cserver_app_json_under_test', os.path.join(APP_DIR, 'src', 'app.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        with TestClient(module.app) as client:
            module.cfg.clear()
            real = module.cm.access

            async def access(params):
                if params.get('category') == 'cserver.broken':
                    return {'return': 1, 'error': 'the category could not be loaded'}
                r = real(params)
                return (await r) if asyncio.iscoroutine(r) else r

            module.cm.access = access
            yield module, client
    finally:
        module.cm.shutdown()


def test_a_failed_call_answers_a_request_for_json_with_json(app):
    module, client = app
    for how in ({'url': '/broken/?native_action=data'}, {'url': '/broken/?native_action=data', 'post': True},
                {'url': '/broken/?force_json=1'}, {'url': '/broken/?out=json'},
                {'url': '/broken/', 'headers': {'Accept': 'application/json'}}):
        r = client.post(how['url'], json={}) if how.get('post') else client.get(how['url'], headers=how.get('headers') or {})
        assert r.status_code == 200, how
        assert r.headers['content-type'].startswith('application/json'), how
        assert r.json() == {'return': 1, 'error': 'the category could not be loaded'}, how


def test_a_failed_page_in_a_browser_is_still_the_error_page(app):
    module, client = app
    r = client.get('/broken/', headers={'Accept': 'text/html,application/xhtml+xml'})
    assert r.status_code == 200 and r.headers['content-type'].startswith('text/html')
    assert 'cMeta error:' in r.text and 'the category could not be loaded' in r.text


def test_an_api_key_refused_is_json_for_a_request_for_json(app):
    module, client = app
    module.cfg['api_keys'] = ['a-key-of-the-test']
    r = client.get('/broken/?native_action=data')
    assert r.headers['content-type'].startswith('application/json') and r.json()['error'] == 'api_key must be present in the query'
    r = client.get('/broken/', headers={'Accept': 'text/html'})
    assert r.headers['content-type'].startswith('text/html') and 'api_key must be present' in r.text
