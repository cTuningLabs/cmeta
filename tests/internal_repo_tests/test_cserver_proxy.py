"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

Tests for the cserver's proxy route (2026-11-19): a page whose category declares `cserver_proxy: {sub: ui}` in its
_desc.yaml has the sub-paths of its page under "ui" passed to the address its api answers to the command "upstream" -
every method, the query and the body, the headers but this server's own session cookie; the answer's status, headers
(Set-Cookie more than once) and body passed back, a redirect to the upstream made relative; 502 when nothing answers.
The page's other sub-paths and every other page are served as before (a POST there: 405).

The app runs in-process with FastAPI's TestClient against a fresh <CMETA_HOME>; a stub web server stands for the
upstream, and the category is answered by a stand-in for the engine's access. Skipped without fastapi or httpx.
"""

import asyncio
import http.server
import importlib.util
import json
import os
import threading

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('httpx')

from fastapi.testclient import TestClient  # noqa: E402

import cmeta  # noqa: E402

APP_DIR = os.path.join(os.path.dirname(os.path.abspath(cmeta.__file__)), 'internal-repo', 'app', 'cserver')


class Upstream(http.server.BaseHTTPRequestHandler):
    """Answers what it was asked (method, path, body, the headers it got); /base/redir redirects to itself."""
    seen = []

    def _answer(self):
        body = self.rfile.read(int(self.headers.get('Content-Length') or 0))
        Upstream.seen.append({'method': self.command, 'path': self.path, 'body': body.decode('utf-8', 'replace'),
                              'headers': {k.lower(): v for k, v in self.headers.items()}})
        if self.path.startswith('/base/redir'):
            self.send_response(302)
            self.send_header('Location', 'http://%s:%d/base/elsewhere' % self.server.server_address)
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        out = json.dumps({'method': self.command, 'path': self.path}).encode()
        self.send_response(201 if self.command == 'POST' else 200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Set-Cookie', 'a=1; Path=/')
        self.send_header('Set-Cookie', 'b=2; Path=/')
        self.send_header('Content-Length', str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    do_GET = do_POST = do_PUT = do_DELETE = _answer

    def log_message(self, *args):
        pass


@pytest.fixture()
def proxied(tmp_path, monkeypatch):
    """The app, a client, a page category 'cserver.testproxy' declaring the route, and a stub upstream."""
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path / 'home'))
    monkeypatch.chdir(APP_DIR)
    cat = tmp_path / 'cserver.testproxy'
    (cat / 'files').mkdir(parents=True)
    (cat / '_desc.yaml').write_text('cserver_proxy:\n  sub: ui\n', encoding='utf-8')
    plain = tmp_path / 'cserver.plain'
    (plain / 'files').mkdir(parents=True)
    (plain / 'files' / 'a.txt').write_text('a file', encoding='utf-8')

    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    upstream = {'url': 'http://127.0.0.1:%d/base' % srv.server_address[1]}
    Upstream.seen.clear()

    spec = importlib.util.spec_from_file_location('cserver_app_proxy_under_test', os.path.join(APP_DIR, 'src', 'app.py'))
    app_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app_module)
    try:
        with TestClient(app_module.app) as client:
            app_module.cfg.clear()
            real = app_module.cm.access

            async def access(params):
                if params.get('category') == 'category' and params.get('command') == 'find':
                    found = {'cserver.testproxy': cat, 'cserver.plain': plain}.get(params.get('arg1'))
                    if found:
                        return {'return': 0, 'artifacts': [{'path': str(found)}]}
                if params.get('category') == 'cserver.testproxy' and params.get('command') == 'upstream':
                    return {'return': 0, 'url': upstream['url']}
                r = real(params)
                return (await r) if asyncio.iscoroutine(r) else r

            app_module.cm.access = access
            app_module._PROXY_UPSTREAMS.clear()
            yield app_module, client, upstream
    finally:
        srv.shutdown()
        app_module.cm.shutdown()


def test_a_get_goes_to_the_upstream_with_its_query(proxied):
    _, client, upstream = proxied
    r = client.get('/testproxy/ui/hello/there?x=1&y=2')
    assert r.status_code == 200 and r.json() == {'method': 'GET', 'path': '/base/hello/there?x=1&y=2'}
    seen = Upstream.seen[-1]
    assert seen['headers']['host'] == upstream['url'].split('/')[2]


def test_every_method_and_the_body_go_through(proxied):
    _, client, _ = proxied
    r = client.post('/testproxy/ui/api/query', content=b'{"q": 1}', headers={'Content-Type': 'application/json'})
    assert r.status_code == 201 and Upstream.seen[-1]['body'] == '{"q": 1}' and Upstream.seen[-1]['method'] == 'POST'
    assert client.put('/testproxy/ui/x', content=b'p').status_code == 200 and Upstream.seen[-1]['method'] == 'PUT'
    assert client.delete('/testproxy/ui/x').status_code == 200 and Upstream.seen[-1]['method'] == 'DELETE'
    assert client.get('/testproxy/ui').status_code == 200 and Upstream.seen[-1]['path'] == '/base/'


def test_this_servers_session_stays_here_other_cookies_go(proxied):
    _, client, _ = proxied
    client.get('/testproxy/ui/c', headers={'Cookie': 'cserver_session=SECRET; grafana_session=g1; other=o'})
    cookie = Upstream.seen[-1]['headers'].get('cookie', '')
    assert 'SECRET' not in cookie and 'cserver_session' not in cookie and 'grafana_session=g1' in cookie and 'other=o' in cookie


def test_the_answer_comes_back_whole_and_a_redirect_stays_here(proxied):
    _, client, _ = proxied
    r = client.get('/testproxy/ui/hello')
    assert sorted(v.split(';')[0] for v in r.headers.get_list('set-cookie')) == ['a=1', 'b=2']
    r = client.get('/testproxy/ui/redir', follow_redirects=False)
    assert r.status_code == 302 and r.headers['location'] == '/base/elsewhere'


def test_nothing_answering_is_a_502_with_the_page_named(proxied):
    app_module, client, upstream = proxied
    upstream['url'] = ''
    app_module._PROXY_UPSTREAMS.clear()
    r = client.get('/testproxy/ui/hello')
    assert r.status_code == 502 and '/testproxy' in r.text
    upstream['url'] = 'http://127.0.0.1:9/base'           # nothing listens on port 9
    app_module._PROXY_UPSTREAMS.clear()
    assert client.get('/testproxy/ui/hello').status_code == 502


def test_everything_else_is_served_as_before(proxied):
    _, client, _ = proxied
    n = len(Upstream.seen)
    assert client.get('/plain/a.txt').text == 'a file'
    assert client.post('/plain/a.txt', content=b'x').status_code == 405        # no declaration: as before
    assert client.post('/testproxy/other', content=b'x').status_code == 405    # outside "ui": as before
    assert client.get('/testproxy/uiother').status_code == 404                 # "ui" is a whole word
    assert len(Upstream.seen) == n                                              # nothing went to the upstream
