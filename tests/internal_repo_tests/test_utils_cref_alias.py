"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

`cx utils cref` is `find_by_cid` under the name of what it takes (a command alias declared in the utils category's
_cmeta.yaml, 2026-11-10): the same artifacts for a cRef with wildcards, every option passed through, a {{{cRef}}} as
`cx info` prints it accepted on the command line, and the help of the category naming the alias. Each test runs in
a fresh CMETA_HOME.
"""

import os
import subprocess
import sys

import pytest

from cmeta import CMeta


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """A fresh CMETA_HOME with two config artifacts; -> (CMeta, the UID of the first)."""
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    cm = CMeta(home=str(tmp_path))
    for alias in ('cref-alias-one', 'cref-alias-two'):
        r = cm.access({'category': 'config', 'command': 'add', 'arg1': 'local:' + alias, 'con': False, 'tags': 'cref-test'})
        assert r['return'] == 0, r
    found = cm.access({'category': 'config', 'command': 'find', 'arg1': 'cref-alias-one', 'con': False})['artifacts']
    return cm, found[0]['cmeta']['artifact']


def paths(r):
    return sorted(a['path'] for a in r['artifacts'])


def test_cref_finds_what_find_by_cid_finds(home):
    cm, uid = home
    for arg in ('config::cref-alias-*', 'cref-alias-one', 'config::cref-alias-one,' + uid, 'config::,' + uid):
        a = cm.access({'category': 'utils', 'command': 'cref', 'arg1': arg, 'con': False})
        b = cm.access({'category': 'utils', 'command': 'find_by_cid', 'arg1': arg, 'con': False})
        assert a['return'] == 0 and b['return'] == 0, (arg, a, b)
        assert paths(a) == paths(b) and len(paths(a)) >= 1, arg
    # an option of find_by_cid goes through the alias too
    r = cm.access({'category': 'utils', 'command': 'cref', 'arg1': 'config::cref-alias-*', 'tags': 'no-such-tag', 'con': False})
    assert r['return'] == 16 and not r.get('artifacts')          # find_by_cid answers 16 (not found) when nothing matches


def test_the_command_line_takes_a_braced_cref_and_the_help_names_the_alias(home, tmp_path):
    cm, uid = home
    env = {k: v for k, v in os.environ.items() if not k.startswith('CMETA_')}
    env['CMETA_HOME'] = str(tmp_path)

    def cx(*args):
        return subprocess.run([sys.executable, '-m', 'cmeta'] + list(args), capture_output=True, text=True, env=env,
                              stdin=subprocess.DEVNULL, timeout=120)
    out = cx('utils', 'cref', '{{{config::cref-alias-one,%s}}}' % uid)
    assert out.returncode == 0 and 'cref-alias-one' in out.stdout, out.stdout[-600:] + out.stderr[-400:]
    out = cx('utils', '--help')
    assert 'find_by_cid (cref)' in out.stdout, out.stdout[-800:] + out.stderr[-400:]
