"""
cMeta core tests - utils.net.download: with and without a Content-Length header, a transfer cut by the
network (an error, never a short file reported as downloaded) and the continuation of a partly
downloaded file (resume=True: an HTTP range request under If-Range, the record next to the partial file)

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import http.server
import json
import os
import re
import socket
import threading

import pytest

import cmeta.utils.net as net

BODY = b'cMeta download test\n' * 1000
OTHER = b'another file, of the same size as the first one..\n' * 400
assert len(OTHER) == len(BODY)
SHORTER = b'a shorter file\n' * 100


class Site:
    """What the test server serves and how; every test starts from reset()."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.body = BODY
        self.bodies = {}                # path -> body, for the paths that serve something else
        self.etag = '"v1"'
        self.last_modified = 'Wed, 01 Oct 2025 10:00:00 GMT'
        self.length = True              # send Content-Length
        self.chunked = False            # Transfer-Encoding: chunked
        self.ranges = True              # answer range requests with 206
        self.honour_if_range = True     # False: a 206 whatever If-Range says (a broken server)
        self.range_offset = 0           # added to the first byte named in Content-Range (a broken server)
        self.range_status = None        # an HTTP error for every range request
        self.status = None              # an HTTP error for every request
        self.cut = []                   # per request: stop after this many bytes of the body (None: all of it)
        self.requests = []              # what arrived: {'path': ..., <header in lower case>: ...}


SITE = Site()


class Handler(http.server.BaseHTTPRequestHandler):

    def do_GET(self):
        site = SITE
        seen = {k.lower(): v for k, v in self.headers.items()}
        seen['path'] = self.path
        site.requests.append(seen)

        if self.path.startswith('/redirect'):
            self.send_response(302)
            self.send_header('Location', '/file')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return

        requested = self.headers.get('Range')

        if site.status or (requested and site.range_status):
            self.send_response(site.status or site.range_status)
            self.send_header('Content-Length', '0')
            self.end_headers()
            return

        body = site.bodies.get(self.path, site.body)
        status = 200
        first = 0
        last = len(body) - 1

        if requested and site.ranges:
            m = re.match(r'bytes=(\d+)-(\d*)$', requested)
            condition = self.headers.get('If-Range')
            same = condition is None or condition in (site.etag, site.last_modified)
            if m and (same or not site.honour_if_range):
                first = int(m.group(1))
                if m.group(2):
                    last = min(int(m.group(2)), last)
                if first >= len(body):
                    self.send_response(416)
                    self.send_header('Content-Range', f'bytes */{len(body)}')
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
                status = 206

        payload = body[first:last + 1]

        self.send_response(status)
        self.send_header('Content-Type', 'application/octet-stream')
        if site.etag:
            self.send_header('ETag', site.etag)
        if site.last_modified:
            self.send_header('Last-Modified', site.last_modified)
        if status == 206:
            self.send_header('Content-Range', f'bytes {first + site.range_offset}-{last}/{len(body)}')
        if site.chunked:
            self.send_header('Transfer-Encoding', 'chunked')
        elif site.length:
            self.send_header('Content-Length', str(len(payload)))
        self.end_headers()

        cut = site.cut.pop(0) if site.cut else None
        if cut is not None:
            payload = payload[:cut]

        if site.chunked:
            self.wfile.write(b'%x\r\n' % len(payload) + payload + b'\r\n')
            if cut is None:
                self.wfile.write(b'0\r\n\r\n')
        else:
            self.wfile.write(payload)
        self.wfile.flush()

        if cut is not None:
            # The connection ends here, cleanly (FIN): what a proxy or a dropped link does mid-transfer
            self.connection.shutdown(socket.SHUT_WR)
        self.close_connection = True

    def log_message(self, *args):
        pass


@pytest.fixture(scope='module')
def httpd():
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_address[1]}'
    server.shutdown()
    server.server_close()


@pytest.fixture
def server(httpd):
    SITE.reset()
    return httpd


def get(server, tmp_path, resume=True, path='/file', **kw):
    return net.download(server + path, filename='file.bin', path=str(tmp_path), resume=resume, **kw)


def part(tmp_path):
    return tmp_path / 'file.bin'


def record(tmp_path):
    return tmp_path / ('file.bin' + net.RESUME_RECORD_SUFFIX)


def leave(server, tmp_path, data, path='/file', **fields):
    """A partial file and its record, as an interrupted download(resume=True) leaves them."""
    part(tmp_path).write_bytes(data)
    rec = {'url': server + path, 'etag': '"v1"', 'last_modified': SITE.last_modified, 'total': len(BODY)}
    rec.update(fields)
    record(tmp_path).write_text(json.dumps(rec), encoding='utf-8')


###################################################################################################
# A complete download

@pytest.mark.parametrize('length', [True, False])
@pytest.mark.parametrize('show_progress', [False, True])
@pytest.mark.parametrize('resume', [False, True])
def test_download(server, tmp_path, length, show_progress, resume):
    if show_progress:
        pytest.importorskip('tqdm')
    SITE.length = length
    r = get(server, tmp_path, resume=resume, show_progress=show_progress)
    assert r['return'] == 0, r.get('error')
    assert part(tmp_path).read_bytes() == BODY
    assert r['size'] == len(BODY) and r['resumed_from'] == 0
    assert not record(tmp_path).exists()
    assert 'range' not in SITE.requests[-1]


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


def test_download_file_url_resume(tmp_path):
    """resume=True on a file:// URL: no ranges there, so a partial copy is replaced by the whole file."""
    src = tmp_path / 'src.bin'
    src.write_bytes(BODY)
    url = src.resolve().as_uri()
    out = tmp_path / 'out'
    out.mkdir()
    (out / 'copy.bin').write_bytes(BODY[:500])
    (out / ('copy.bin' + net.RESUME_RECORD_SUFFIX)).write_text(
        json.dumps({'url': url, 'etag': None, 'last_modified': 'Wed, 01 Oct 2025 10:00:00 GMT', 'total': len(BODY)}))
    r = net.download(url, filename='copy.bin', path=str(out), resume=True)
    assert r['return'] == 0, r.get('error')
    assert (out / 'copy.bin').read_bytes() == BODY and r['resumed_from'] == 0
    assert not (out / ('copy.bin' + net.RESUME_RECORD_SUFFIX)).exists()


def test_empty_file(server, tmp_path):
    SITE.body = b''
    r = get(server, tmp_path)
    assert r['return'] == 0, r.get('error')
    assert part(tmp_path).read_bytes() == b'' and r['size'] == 0
    assert not record(tmp_path).exists()


def test_http_error(server, tmp_path):
    SITE.status = 404
    r = get(server, tmp_path, resume=False)
    assert r['return'] == 1 and '404' in r['error']
    assert not part(tmp_path).exists()          # nothing is created for a request that was refused


###################################################################################################
# A transfer cut by the network

@pytest.mark.parametrize('resume', [False, True])
def test_cut_transfer_is_an_error(server, tmp_path, resume):
    """The server announces the whole file, sends 100 bytes and the connection ends: not a download."""
    SITE.cut = [100]
    r = get(server, tmp_path, resume=resume)
    assert r['return'] == 1
    assert r['incomplete'] is True and r['size'] == 100 and r['total_size'] == len(BODY)
    assert '100 of %d bytes' % len(BODY) in r['error']
    assert part(tmp_path).read_bytes() == BODY[:100]      # what arrived stays
    assert record(tmp_path).exists() == resume


def test_cut_transfer_raises_with_fail_on_error(server, tmp_path):
    SITE.cut = [100]
    with pytest.raises(RuntimeError, match='100 of'):
        get(server, tmp_path, resume=False, fail_on_error=True)


def test_cut_at_zero_bytes(server, tmp_path):
    SITE.cut = [0]
    r = get(server, tmp_path)
    assert r['return'] == 1 and r['incomplete'] is True and r['size'] == 0


def test_cut_chunked_transfer_is_an_error(server, tmp_path):
    """A chunked body that ends before its last chunk: http.client reports it itself."""
    SITE.chunked = True
    SITE.cut = [100]
    r = get(server, tmp_path, resume=False)
    assert r['return'] == 1


def test_cut_without_any_length_cannot_be_seen(server, tmp_path):
    """
    The limit of the check: a body with neither Content-Length nor chunks ends when the connection
    closes, so an early end looks like the end (HTTP/1.0 style; a file of a known size has a length).
    """
    SITE.length = False
    SITE.cut = [100]
    r = get(server, tmp_path, resume=False)
    assert r['return'] == 0 and r['size'] == 100


###################################################################################################
# The continuation of a partial file

def test_resume_continues_where_the_file_ends(server, tmp_path):
    SITE.cut = [1000]
    r = get(server, tmp_path)
    assert r['return'] == 1 and r['incomplete'] is True
    rec = json.loads(record(tmp_path).read_text(encoding='utf-8'))
    assert rec == {'url': server + '/file', 'etag': '"v1"', 'last_modified': SITE.last_modified, 'total': len(BODY)}

    r = get(server, tmp_path)
    assert r['return'] == 0, r.get('error')
    assert r['resumed_from'] == 1000 and r['size'] == len(BODY)
    assert part(tmp_path).read_bytes() == BODY
    assert not record(tmp_path).exists()
    assert SITE.requests[-1]['range'] == 'bytes=1000-' and SITE.requests[-1]['if-range'] == '"v1"'
    assert len(SITE.requests) == 2


def test_resume_over_several_cuts(server, tmp_path):
    SITE.cut = [1000, 500, 0, 7]
    for done in (1000, 1500, 1500, 1507):
        r = get(server, tmp_path)
        assert r['return'] == 1 and r['size'] == done and r['total_size'] == len(BODY)
        assert part(tmp_path).read_bytes() == BODY[:done]
        assert record(tmp_path).exists()
    r = get(server, tmp_path)
    assert r['return'] == 0 and r['resumed_from'] == 1507
    assert part(tmp_path).read_bytes() == BODY
    assert [q.get('range') for q in SITE.requests] == [None, 'bytes=1000-', 'bytes=1500-', 'bytes=1500-', 'bytes=1507-']


def test_resume_with_progress(server, tmp_path):
    pytest.importorskip('tqdm')
    SITE.cut = [1000]
    assert get(server, tmp_path, show_progress=True)['return'] == 1
    r = get(server, tmp_path, show_progress=True)
    assert r['return'] == 0 and r['resumed_from'] == 1000
    assert part(tmp_path).read_bytes() == BODY


def test_resume_through_a_redirect(server, tmp_path):
    SITE.cut = [1000]
    assert get(server, tmp_path, path='/redirect')['return'] == 1
    r = get(server, tmp_path, path='/redirect')
    assert r['return'] == 0 and r['resumed_from'] == 1000
    assert part(tmp_path).read_bytes() == BODY
    assert SITE.requests[-1]['path'] == '/file' and SITE.requests[-1]['range'] == 'bytes=1000-'


def test_resume_with_the_date_when_there_is_no_etag(server, tmp_path):
    SITE.etag = None
    SITE.cut = [1000]
    assert get(server, tmp_path)['return'] == 1
    r = get(server, tmp_path)
    assert r['return'] == 0 and r['resumed_from'] == 1000
    assert part(tmp_path).read_bytes() == BODY
    assert SITE.requests[-1]['if-range'] == SITE.last_modified


def test_resume_is_off_by_default(server, tmp_path):
    """Without resume=True a partial file and its record are not looked at: the file starts over."""
    leave(server, tmp_path, BODY[:1000])
    r = net.download(server + '/file', filename='file.bin', path=str(tmp_path))
    assert r['return'] == 0 and r['resumed_from'] == 0
    assert part(tmp_path).read_bytes() == BODY
    assert 'range' not in SITE.requests[-1]


###################################################################################################
# Everything that makes the download start over instead

def started_over(tmp_path, body=BODY):
    return part(tmp_path).read_bytes() == body and not record(tmp_path).exists()


def test_server_without_ranges(server, tmp_path):
    """A server that ignores the range sends the whole file: it replaces the partial one, never follows it."""
    SITE.ranges = False
    SITE.cut = [1000]
    assert get(server, tmp_path)['return'] == 1
    r = get(server, tmp_path)
    assert r['return'] == 0 and r['resumed_from'] == 0
    assert started_over(tmp_path)
    assert SITE.requests[-1]['range'] == 'bytes=1000-'      # it was asked for


def test_file_changed_on_the_server(server, tmp_path):
    """If-Range: the file is another one now, so the server sends all of it."""
    SITE.cut = [1000]
    assert get(server, tmp_path)['return'] == 1
    SITE.body, SITE.etag = OTHER, '"v2"'
    r = get(server, tmp_path)
    assert r['return'] == 0 and r['resumed_from'] == 0
    assert started_over(tmp_path, OTHER)
    assert len(SITE.requests) == 2


def test_file_changed_and_shorter_than_the_part(server, tmp_path):
    SITE.cut = [5000]
    assert get(server, tmp_path)['return'] == 1
    SITE.body, SITE.etag = SHORTER, '"v2"'
    r = get(server, tmp_path)
    assert r['return'] == 0 and started_over(tmp_path, SHORTER)


def test_file_changed_on_a_server_that_ignores_if_range(server, tmp_path):
    """A broken server answers 206 for the new file: its ETag is not the recorded one - the whole file is asked for."""
    SITE.cut = [1000]
    assert get(server, tmp_path)['return'] == 1
    SITE.body, SITE.etag, SITE.honour_if_range = OTHER, '"v2"', False
    r = get(server, tmp_path)
    assert r['return'] == 0 and r['resumed_from'] == 0
    assert started_over(tmp_path, OTHER)
    assert [q.get('range') for q in SITE.requests] == [None, 'bytes=1000-', None]


def test_file_changed_size_on_a_server_that_ignores_if_range(server, tmp_path):
    """The same without validators in the answer: the total of Content-Range is not the recorded one."""
    SITE.cut = [1000]
    assert get(server, tmp_path)['return'] == 1
    SITE.body, SITE.honour_if_range = SHORTER * 3, False       # ETag unchanged: only the size tells
    r = get(server, tmp_path)
    assert r['return'] == 0 and started_over(tmp_path, SHORTER * 3)


def test_range_that_does_not_start_where_asked(server, tmp_path):
    SITE.cut = [1000]
    assert get(server, tmp_path)['return'] == 1
    SITE.range_offset = 5
    r = get(server, tmp_path)
    assert r['return'] == 0 and r['resumed_from'] == 0
    assert [q.get('range') for q in SITE.requests] == [None, 'bytes=1000-', None]
    assert started_over(tmp_path)


def test_no_validator_no_record(server, tmp_path):
    """A server that names neither an ETag nor a date: nothing could prove the rest is the same file."""
    SITE.etag = SITE.last_modified = None
    SITE.cut = [1000]
    assert get(server, tmp_path)['return'] == 1
    assert not record(tmp_path).exists()
    r = get(server, tmp_path)
    assert r['return'] == 0 and r['resumed_from'] == 0 and started_over(tmp_path)
    assert 'range' not in SITE.requests[-1]


def test_weak_etag_is_no_validator(server, tmp_path):
    SITE.etag = 'W/"v1"'
    SITE.cut = [1000]
    assert get(server, tmp_path)['return'] == 1
    assert not record(tmp_path).exists()
    r = get(server, tmp_path)
    assert r['return'] == 0 and r['resumed_from'] == 0 and started_over(tmp_path)


def test_another_url_for_the_same_file_name(server, tmp_path):
    """A mirror: the partial file of one URL is never continued from another."""
    SITE.cut = [1000]
    assert get(server, tmp_path)['return'] == 1
    SITE.bodies['/mirror/file'] = OTHER
    r = get(server, tmp_path, path='/mirror/file')
    assert r['return'] == 0 and r['resumed_from'] == 0 and started_over(tmp_path, OTHER)
    assert 'range' not in SITE.requests[-1]


def test_part_without_a_record(server, tmp_path):
    """A partial file left by an engine without resume (or by anything else): unknown origin."""
    part(tmp_path).write_bytes(OTHER[:1000])
    r = get(server, tmp_path)
    assert r['return'] == 0 and r['resumed_from'] == 0 and started_over(tmp_path)
    assert 'range' not in SITE.requests[-1]


@pytest.mark.parametrize('text', ['', '{"url": ', 'not json', '[]', '{"etag": "x"}', '{"url": 5}'])
def test_unreadable_record(server, tmp_path, text):
    part(tmp_path).write_bytes(BODY[:1000])
    record(tmp_path).write_text(text, encoding='utf-8')
    r = get(server, tmp_path)
    assert r['return'] == 0 and r['resumed_from'] == 0 and started_over(tmp_path)
    assert 'range' not in SITE.requests[-1]


@pytest.mark.parametrize('total', ['20000', -1, True, 1.5])
def test_record_with_a_wrong_total(server, tmp_path, total):
    leave(server, tmp_path, BODY[:1000], total=total)
    r = get(server, tmp_path)
    assert r['return'] == 0 and r['resumed_from'] == 0 and started_over(tmp_path)


def test_part_larger_than_the_recorded_file(server, tmp_path):
    leave(server, tmp_path, BODY + b'more')
    r = get(server, tmp_path)
    assert r['return'] == 0 and r['resumed_from'] == 0 and started_over(tmp_path)
    assert 'range' not in SITE.requests[-1]


def test_empty_part(server, tmp_path):
    leave(server, tmp_path, b'')
    r = get(server, tmp_path)
    assert r['return'] == 0 and r['resumed_from'] == 0 and started_over(tmp_path)
    assert 'range' not in SITE.requests[-1]


###################################################################################################
# A partial file that is complete already

def test_complete_part_needs_no_request(server, tmp_path):
    """Stopped after the last byte and before the caller renamed the file: nothing is asked again."""
    leave(server, tmp_path, BODY)
    r = get(server, tmp_path)
    assert r['return'] == 0 and r['resumed_from'] == len(BODY) and r['size'] == len(BODY)
    assert started_over(tmp_path) and SITE.requests == []


def test_complete_part_of_unknown_total(server, tmp_path):
    """The first answer named no size: the server says that the range starts at the end of the file (416)."""
    leave(server, tmp_path, BODY, total=None)
    r = get(server, tmp_path)
    assert r['return'] == 0 and r['resumed_from'] == len(BODY)
    assert started_over(tmp_path) and len(SITE.requests) == 1


def test_part_beyond_the_file_of_unknown_total(server, tmp_path):
    """416 for another size than the one on disk: not the same file - the whole file is asked for."""
    leave(server, tmp_path, BODY + b'more', total=None)
    r = get(server, tmp_path)
    assert r['return'] == 0 and r['resumed_from'] == 0 and started_over(tmp_path)
    assert [q.get('range') for q in SITE.requests] == ['bytes=%d-' % (len(BODY) + 4), None]


###################################################################################################
# Errors while continuing

def test_range_request_refused_then_the_whole_file(server, tmp_path):
    """A server that fails on range requests must not make the same download fail for ever."""
    SITE.cut = [1000]
    assert get(server, tmp_path)['return'] == 1
    SITE.range_status = 500
    r = get(server, tmp_path)
    assert r['return'] == 0 and r['resumed_from'] == 0 and started_over(tmp_path)
    assert [q.get('range') for q in SITE.requests] == [None, 'bytes=1000-', None]


def test_server_down_keeps_the_part(server, tmp_path):
    """Both requests fail: the partial file and its record are untouched and continue when the server is back."""
    SITE.cut = [1000]
    assert get(server, tmp_path)['return'] == 1
    before = record(tmp_path).read_text(encoding='utf-8')
    SITE.status = 503
    r = get(server, tmp_path)
    assert r['return'] == 1 and '503' in r['error'] and 'incomplete' not in r
    assert part(tmp_path).read_bytes() == BODY[:1000]
    assert record(tmp_path).read_text(encoding='utf-8') == before
    SITE.status = None
    r = get(server, tmp_path)
    assert r['return'] == 0 and r['resumed_from'] == 1000 and started_over(tmp_path)


def test_unreachable_server_keeps_the_part(tmp_path):
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    part(tmp_path).write_bytes(BODY[:1000])
    record(tmp_path).write_text(json.dumps({'url': url + '/file', 'etag': '"v1"', 'last_modified': None, 'total': len(BODY)}))
    r = net.download(url + '/file', filename='file.bin', path=str(tmp_path), resume=True)
    assert r['return'] == 1
    assert part(tmp_path).read_bytes() == BODY[:1000] and record(tmp_path).exists()


def test_cut_while_continuing_then_file_changes(server, tmp_path):
    """Two cuts, then the file on the server is replaced: the two parts are dropped, not completed."""
    SITE.cut = [1000, 500]
    assert get(server, tmp_path)['return'] == 1
    assert get(server, tmp_path)['return'] == 1
    assert os.path.getsize(part(tmp_path)) == 1500
    SITE.body, SITE.etag = OTHER, '"v2"'
    SITE.cut = [300]
    r = get(server, tmp_path)
    assert r['return'] == 1 and r['size'] == 300
    assert part(tmp_path).read_bytes() == OTHER[:300]
    assert json.loads(record(tmp_path).read_text(encoding='utf-8'))['etag'] == '"v2"'
    r = get(server, tmp_path)
    assert r['return'] == 0 and r['resumed_from'] == 300 and started_over(tmp_path, OTHER)


def test_a_range_of_the_caller_is_left_alone(server, tmp_path):
    """resume=True with a Range header of the caller: that range is what is asked, nothing is continued."""
    leave(server, tmp_path, BODY[:1000])
    r = get(server, tmp_path, headers={'Range': 'bytes=0-9'})
    assert r['return'] == 0 and r['size'] == 10 and r['resumed_from'] == 0
    assert part(tmp_path).read_bytes() == BODY[:10]
    assert record(tmp_path).exists()            # not this call's business


###################################################################################################
# The helpers

@pytest.mark.parametrize('value, expected', [
    ('bytes 100-999/1000', (100, 999, 1000)),
    ('bytes 100-999/*', (100, 999, None)),
    ('bytes */1000', (None, None, 1000)),
    ('Bytes  0-0/1', (0, 0, 1)),
    ('items 0-9/10', None),
    ('bytes 100-999', None),
    ('', None),
    (None, None),
])
def test_content_range(value, expected):
    assert net._content_range(value) == expected


@pytest.mark.parametrize('rec, expected', [
    ({'etag': '"a"', 'last_modified': 'date'}, '"a"'),
    ({'etag': None, 'last_modified': 'date'}, 'date'),
    ({'etag': 'W/"a"', 'last_modified': 'date'}, None),
    ({'etag': '', 'last_modified': ''}, None),
    ({}, None),
])
def test_resume_validator(rec, expected):
    assert net._resume_validator(rec) == expected
