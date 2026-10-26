"""
CMetaAsync.access_sync() runs the command on a plain CMeta of the calling process (KI-001).

A command whose api/v1.py re-enters cMeta through self.cm.access() - the config category's `get`, most commands -
gets a result dict from access_sync(), as it does in a worker process of `await cm.access()`. Until KI-001 was fixed
the command ran on the async object itself, the nested call landed on the async access() and an un-awaited coroutine
came back in place of the result. The async path is checked unchanged, and the plain engine of access_sync() is made
once with the constructor arguments of the async object.

Every home is under tmp_path: nothing of the user's cMeta is touched. The async test starts one worker process.
"""

import asyncio
import os

import pytest

from cmeta import CMeta
from cmeta.core_async import CMetaAsync

HOME_VARS = ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX')

# the config's get re-enters cMeta (it reads the artifact through cm.access); category find does not
NESTED = {'category': 'config', 'command': 'get', 'arg1': 'cserver', 'con': False}
SIMPLE = {'category': 'category', 'command': 'find', 'arg1': 'config', 'con': False}


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """A cMeta home of the test, chosen by CMETA_HOME; the user's folder is a folder of the test too."""
    for var in HOME_VARS + ('CMETA_DEBUG', 'CMETA_VERBOSE', 'CMETA_LOG', 'CMETA_LOG_FILE'):
        monkeypatch.delenv(var, raising=False)

    user = tmp_path / 'user'
    user.mkdir()
    monkeypatch.setenv('HOME', str(user))
    monkeypatch.setenv('USERPROFILE', str(user))

    folder = tmp_path / 'home'
    monkeypatch.setenv('CMETA_HOME', str(folder))
    return folder


@pytest.fixture()
def cm(home):
    cm = CMetaAsync(max_workers=1)
    yield cm
    cm.shutdown()


def under(folder, path):
    return os.path.normcase(os.path.abspath(str(path))).startswith(os.path.normcase(os.path.abspath(str(folder))))


def test_access_sync_serves_a_command_that_re_enters(cm, home):
    """The failing case of KI-001: a result dict, not a coroutine, with the config read and its artifact under the home."""
    r = cm.access_sync(dict(NESTED))

    assert isinstance(r, dict) and not asyncio.iscoroutine(r)
    assert r['return'] == 0, r.get('error')
    assert isinstance(r.get('config_cmeta'), dict)
    assert under(home, (r.get('artifact') or {}).get('path', ''))


def test_access_sync_simple_command_as_a_plain_cmeta_would(cm, home):
    """A command without a nested call answers as before: the same artifacts a plain CMeta finds."""
    r = cm.access_sync(dict(SIMPLE))
    assert r['return'] == 0, r.get('error')

    plain = CMeta().access(dict(SIMPLE))
    assert plain['return'] == 0, plain.get('error')

    def uids(result):
        return sorted(str(a.get('uid') or a.get('artifact') or a.get('path')) for a in result.get('artifacts') or [])

    assert uids(r) == uids(plain) and uids(r)


def test_access_sync_makes_one_plain_engine_and_reuses_it(cm):
    """The engine of access_sync() is a plain CMeta, not the async object, made at the first call and kept."""
    assert cm._sync_cmeta is None

    cm.access_sync(dict(SIMPLE))
    first = cm._sync_cmeta
    cm.access_sync(dict(NESTED))

    assert first is not None and first is cm._sync_cmeta
    assert type(first) is CMeta and first is not cm


def test_access_sync_takes_the_constructor_arguments(tmp_path, home):
    """The plain engine is made with what the async object was made with: another home named at construction."""
    other = tmp_path / 'other-home'
    cm = CMetaAsync(max_workers=1, home=str(other))
    try:
        r = cm.access_sync(dict(NESTED))
        assert r['return'] == 0, r.get('error')
        assert under(other, (r.get('artifact') or {}).get('path', ''))
    finally:
        cm.shutdown()


def test_access_sync_error_is_a_dict(cm):
    """An error comes back as cMeta's dict, as from a plain CMeta."""
    r = cm.access_sync({'category': 'no-such-category-of-this-test', 'command': 'find', 'con': False})
    assert isinstance(r, dict) and r['return'] > 0 and r.get('error')


def test_async_access_unchanged(cm, home):
    """`await cm.access()` still runs in a worker process and serves the re-entering command as before."""
    async def both():
        return await cm.access(dict(NESTED)), await cm.access(dict(SIMPLE))

    nested, simple = asyncio.run(both())
    assert nested['return'] == 0, nested.get('error')
    assert isinstance(nested.get('config_cmeta'), dict)
    assert under(home, (nested.get('artifact') or {}).get('path', ''))
    assert simple['return'] == 0 and simple.get('artifacts')
    assert cm._sync_cmeta is None          # the async path never makes the plain engine of access_sync()
