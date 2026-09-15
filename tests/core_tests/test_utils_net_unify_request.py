"""
cMeta core tests - utils.net.unify_request (the request normaliser of the cserver app)

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import asyncio

import cmeta.utils.net as net


class FakeRequest:
    """The three things unify_request reads: method, query_params, and the body."""

    def __init__(self, method='GET', query=None, body=b'', fail_body=None):
        self.method = method
        self.query_params = query or {}
        self.headers = {}
        self._body = body
        self._fail_body = fail_body

    async def body(self):
        if self._fail_body is not None:
            raise self._fail_body
        return self._body


def unify(req):
    return asyncio.run(net.unify_request(req))


def test_get_uses_query_params_only():
    r = unify(FakeRequest('GET', {'a': '1', 'native_action': 'x'}))
    assert r['return'] == 0
    assert r['query'] == {'a': '1', 'native_action': 'x'}


def test_post_merges_json_body_over_query():
    r = unify(FakeRequest('POST', {'a': '1', 'b': 'q'}, b'{"b": "body", "c": 3}'))
    assert r['return'] == 0
    assert r['query'] == {'a': '1', 'b': 'body', 'c': 3}


def test_post_empty_body_means_no_extra_params():
    for body in (b'', b'   \n'):
        r = unify(FakeRequest('POST', {'a': '1'}, body))
        assert r['return'] == 0
        assert r['query'] == {'a': '1'}


def test_post_invalid_json_is_reported_not_raised():
    r = unify(FakeRequest('POST', {'a': '1'}, b'{"as_at": "2026'))
    assert r['return'] == 99
    assert 'not valid JSON' in r['error']


def test_post_form_body_is_reported():
    r = unify(FakeRequest('POST', {}, b'a=1&b=2'))
    assert r['return'] == 99
    assert 'not valid JSON' in r['error']


def test_post_json_that_is_not_an_object_is_reported():
    r = unify(FakeRequest('POST', {}, b'[1, 2, 3]'))
    assert r['return'] == 99
    assert 'JSON object' in r['error']


def test_post_body_read_failure_is_reported():
    """The client disconnected while sending (a page reload mid-request): no exception escapes."""
    r = unify(FakeRequest('POST', {}, fail_body=RuntimeError('client disconnected')))
    assert r['return'] == 99
    assert 'could not be read' in r['error']
