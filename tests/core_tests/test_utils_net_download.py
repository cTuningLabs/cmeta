"""
cMeta core tests - utils.net.download with and without a Content-Length header

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import http.server
import threading

import pytest

import cmeta.utils.net as net

BODY = b'cMeta download test\n' * 1000


class Handler(http.server.BaseHTTPRequestHandler):
    """Serves BODY; /no-length without a Content-Length header (the body ends when the connection closes)."""

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/octet-stream')
        if self.path != '/no-length':
            self.send_header('Content-Length', str(len(BODY)))
        self.end_headers()
        self.wfile.write(BODY)

    def log_message(self, *args):
        pass


@pytest.fixture(scope='module')
def server():
    httpd = http.server.HTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{httpd.server_address[1]}'
    httpd.shutdown()
    httpd.server_close()


@pytest.mark.parametrize('path', ['/with-length', '/no-length'])
@pytest.mark.parametrize('show_progress', [False, True])
def test_download(server, tmp_path, path, show_progress):
    if show_progress:
        pytest.importorskip('tqdm')
    r = net.download(server + path, filename='file.bin', path=str(tmp_path), show_progress=show_progress)
    assert r['return'] == 0, r.get('error')
    assert (tmp_path / 'file.bin').read_bytes() == BODY


def test_download_file_url(tmp_path):
    """A file:// URL copies the local file (a response without getheader())."""
    src = tmp_path / 'src.bin'
    src.write_bytes(BODY)
    url = src.resolve().as_uri()
    r = net.download(url, filename='copy.bin', path=str(tmp_path / 'out'), show_progress=False)
    assert r['return'] == 0, r.get('error')
    assert (tmp_path / 'out' / 'copy.bin').read_bytes() == BODY
    r = net.download(url, filename='copy2.bin', path=str(tmp_path / 'out'), show_progress=True)
    assert r['return'] == 0, r.get('error')
