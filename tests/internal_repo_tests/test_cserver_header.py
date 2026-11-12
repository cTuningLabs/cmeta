"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

Tests for the bar above every page of the cserver app (2026-11-12, page_header of the cserver config): on by
default - the menu of all pages (the home page's own list), the neuron to the home page, where the page is (the
parts of its name, then its title), the shared theme, Settings - also above an error page; none with
page_header: no; its stylesheet, script and image served from /static.

The app runs in-process with FastAPI's TestClient against a fresh <CMETA_HOME> in tmp_path. Skipped without the
server extra (fastapi) or httpx, which the TestClient needs.
"""

import importlib.util
import os
import re

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('httpx')

from fastapi.testclient import TestClient  # noqa: E402

import cmeta  # noqa: E402

APP_DIR = os.path.join(os.path.dirname(os.path.abspath(cmeta.__file__)), 'internal-repo', 'app', 'cserver')


@pytest.fixture()
def server(tmp_path, monkeypatch):
    """The cserver app module and a client, on a fresh home with an empty cserver config."""
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    monkeypatch.chdir(APP_DIR)                    # the app finds src/templates and src/static from its folder

    spec = importlib.util.spec_from_file_location('cserver_app_header_under_test', os.path.join(APP_DIR, 'src', 'app.py'))
    app_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app_module)
    try:
        with TestClient(app_module.app) as client:   # runs the startup event: reads the cserver config
            app_module.cfg.clear()                    # no password, no api_keys, page_header unset (= on)
            yield app_module, client
    finally:
        app_module.cm.shutdown()


def bar(html):
    m = re.search(r'<header class="cmh" id="cmh".*?</header>', html, re.S)
    return m.group(0) if m else ''


def test_the_bar_is_above_every_page_by_default(server):
    _, client = server
    r = client.get('/settings')
    assert r.status_code == 200
    b = bar(r.text)
    assert b, 'no bar above /settings'
    assert 'id="cmh-menu"' in b and 'id="cmh-theme"' in b
    assert re.search(r'class="cmh-btn cmh-settings" href="[^"]*/settings"', b)
    assert re.search(r'class="cmh-brand" href="http://testserver/"', b)                  # the neuron: home
    assert 'data-projects="http://testserver/projects/?native_action=projects"' in b       # the menu's list
    assert re.search(r'<span class="cmh-now"[^>]*>Settings</span>', b)                     # the page's own title
    assert 'class="cmh-crumb"' not in b                                                   # no part before it
    assert re.search(r'href="http://testserver/static/css/cmeta_header\.css\?v=\d+"', r.text)
    assert re.search(r'src="http://testserver/static/js/cmeta_header\.js\?v=\d+"', r.text)
    assert 'id="cmh-drawer"' in r.text and 'id="cmh-filter"' in r.text
    # the hook that lets the bar follow a page's own theme switch, before any script of the page
    head = r.text.split('</head>')[0]
    assert "key === 'cmeta.theme'" in head


def test_the_place_of_a_page_is_the_parts_of_its_name(server):
    _, client = server
    b = bar(client.get('/cmeta.configs').text)
    assert re.search(r'<span class="cmh-crumb" data-prefix="cmeta\."[^>]*>cmeta</span>', b)
    assert b.count('class="cmh-crumb"') == 1


def test_the_home_page_says_home(server):
    """The neuron says Home on every page (2026-11-12, the user: "use Home close to the neuron instead of cMeta"); on
    the home page itself nothing follows it."""
    _, client = server
    b = bar(client.get('/').text)
    assert 'data-is-home="1"' in b and re.search(r'class="cmh-brand"[^>]*>\s*<img[^>]*><span>Home</span>', b)
    assert 'class="cmh-now"' not in b and 'class="cmh-crumb"' not in b
    assert re.search(r'<span>Home</span>', bar(client.get('/settings').text))


def test_an_error_page_keeps_the_bar(server):
    _, client = server
    r = client.get('/no-such-page-of-this-server')
    assert 'cMeta error' in r.text
    assert bar(r.text), 'no way back from an error page'


def test_page_header_no_keeps_the_pages_as_they_were(server):
    app_module, client = server
    app_module.cfg['page_header'] = 'no'
    r = client.get('/settings')
    assert r.status_code == 200
    assert not bar(r.text) and 'cmeta_header.css' not in r.text and 'cmeta_header.js' not in r.text
    assert "key === 'cmeta.theme'" not in r.text.split('</head>')[0]
    app_module.cfg['page_header'] = 'yes'
    assert bar(client.get('/settings').text)


def test_the_assets_of_the_bar_are_served(server):
    _, client = server
    for path, kind in (('/static/css/cmeta_header.css', 'css'), ('/static/js/cmeta_header.js', 'javascript'),
                       ('/static/images/neuron.png', 'png')):
        r = client.get(path)
        assert r.status_code == 200 and kind in r.headers.get('content-type', ''), (path, r.headers.get('content-type'))
