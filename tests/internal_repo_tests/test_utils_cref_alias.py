"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

`cx utils cref` is `find_by_cid` under the name of what it takes (a command alias declared in the utils category's
_cmeta.yaml, 2026-11-10): the same artifacts for a cRef with wildcards, every option passed through, a {{{cRef}}} as
`cx info` prints it accepted on the command line, and the help of the category naming the alias. Each test runs in
a fresh CMETA_HOME.

2026-11-16: `cx utils cref` reads the path inside the artifact written after the cRef - <cRef>/<path> and
{{{<cRef>}}}/<path>, "/" or "\" - exactly: the path must exist as written, text around the cRef and a path leaving
the artifact are refused, a cRef alone answers as before. `cx utils smart_cref` is smart_find_by_cid under the same
kind of name (the cRef found inside other text, a path guessed from its longest existing part).
"""

import os
import subprocess
import sys
from urllib.parse import quote

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


# ------------------------------------------------------------------ a path after the cRef (2026-11-16)

MESSAGE = 'EMails/20261115.message.md'


@pytest.fixture()
def tree(home):
    """The two config artifacts with files in them: a message, a name with a space, !AI/memory, and shared.md in
    both. -> (CMeta, UID of the first, {alias: folder})."""
    cm, uid = home
    found = cm.access({'category': 'config', 'command': 'find', 'arg1': 'cref-alias-*', 'con': False})['artifacts']
    folders = {a['cmeta_ref_parts']['artifact_alias']: a['path'] for a in found}
    one = folders['cref-alias-one']
    for rel in (MESSAGE, 'notes/a b.md', '!AI/memory/MEMORY.md'):
        os.makedirs(os.path.dirname(os.path.join(one, rel)), exist_ok=True)
        with open(os.path.join(one, rel), 'w', encoding='utf-8') as f:
            f.write(rel)
    for folder in folders.values():
        with open(os.path.join(folder, 'shared.md'), 'w', encoding='utf-8') as f:
            f.write('shared')
    return cm, uid, folders


def cref(cm, arg, **flags):
    return cm.access(dict(flags, category='utils', command='cref', arg1=arg, con=False))


def braced(ref):
    return '{{{' + ref + '}}}'


def test_a_path_after_the_cref_is_the_answer(tree):
    cm, uid, folders = tree
    one = folders['cref-alias-one']
    expected = os.path.join(one, 'EMails', '20261115.message.md')
    full = 'config::cref-alias-one,' + uid
    for arg in (full + '/' + MESSAGE,                                  # cRef/path
                braced(full) + '/' + MESSAGE,                          # {{{cRef}}}/path, as memories write a place
                full + '\\EMails\\20261115.message.md',                # a backslash separates names too
                braced(full) + '\\' + MESSAGE,
                'cref-alias-one/' + MESSAGE,                           # a bare name, any category
                'config::,' + uid + '/' + MESSAGE,                     # the UID alone
                'config::cref-alias-one/./EMails//20261115.message.md',  # "." and empty names are no names
                '  ' + full + '/' + MESSAGE + '  '):                   # spaces around the whole argument
        r = cref(cm, arg)
        assert r['return'] == 0, (arg, r)
        assert r['path'] == expected and r['paths'] == [expected], (arg, r.get('paths'))
        assert [a['path'] for a in r['artifacts']] == [one] and r['sub_path'] == MESSAGE, arg

    # a folder, a name with a space, a name with "!", and "/" alone: the artifact's own folder
    for rel, place in (('EMails', os.path.join(one, 'EMails')), ('notes/a b.md', os.path.join(one, 'notes', 'a b.md')),
                       ('!AI/memory/MEMORY.md', os.path.join(one, '!AI', 'memory', 'MEMORY.md')), ('', one)):
        r = cref(cm, full + '/' + rel)
        assert r['return'] == 0 and r['path'] == place and r['sub_path'] == rel, (rel, r)

    # the web form of the command (cmeta:///?<encoded cRef>) takes a path too
    r = cref(cm, 'cmeta:///?' + quote(full + '/' + MESSAGE), web=True)
    assert r['return'] == 0 and r['path'] == expected, r


def test_a_cref_without_a_path_answers_as_before(tree):
    cm, uid, folders = tree
    for arg in ('config::cref-alias-one,' + uid, braced('config::cref-alias-one,' + uid), 'cref-alias-one', 'config::cref-alias-*'):
        a = cref(cm, arg)
        b = cm.access({'category': 'utils', 'command': 'find_by_cid', 'arg1': arg, 'con': False})
        assert a['return'] == 0 and paths(a) == paths(b), arg
        assert 'path' not in a and 'paths' not in a and 'sub_path' not in a, arg


def test_the_path_must_exist_exactly(tree):
    cm, uid, folders = tree
    one, full = folders['cref-alias-one'], 'config::cref-alias-one,' + uid
    for rel in ('EMails/no-such.md',                       # not there
                'EMails/20261115.message',                 # no extension guessed
                MESSAGE + ' and more words',               # no prose dropped from the end
                MESSAGE + '/more'):                        # nothing below a file
        r = cref(cm, full + '/' + rel)
        assert r['return'] == 16 and 'not found in ' + one in r['error'], (rel, r)
        assert not r.get('artifacts') and not r.get('path'), rel


@pytest.mark.parametrize('arg, says', [
    (braced('config::cref-alias-one') + ' and more words', 'only "/<path>" may follow'),
    (braced('config::cref-alias-one') + 'x', 'only "/<path>" may follow'),
    (braced('config::cref-alias-one/EMails'), 'after the braces'),
    ('{{{}}}', 'no cRef inside'),
    ('{{{config::cref-alias-one', 'without closing'),
    ('config::cref-alias-one/../cref-alias-two/shared.md', 'may not leave its artifact'),
    ('config::cref-alias-one/EMails/../../x', 'may not leave its artifact'),
    (braced('config::cref-alias-one') + '/..', 'may not leave its artifact'),
    ('/etc/hosts', 'a path of the file system'),
    ('~/x', 'a path of the file system'),
    ('\\\\server\\share\\x', 'a path of the file system'),
    ('C:\\Windows', 'a path of the file system'),
    ('D:/data/x.md', 'a path of the file system'),
])
def test_what_is_not_exact_is_refused(tree, arg, says):
    cm, uid, folders = tree
    r = cref(cm, arg)
    assert r['return'] == 1 and says in r['error'], (arg, r)
    assert not r.get('artifacts'), arg


def test_a_name_with_a_drive_never_leads_elsewhere(tree):
    cm, uid, folders = tree
    for rel in ('C:/Windows', 'C:', 'shared.md:stream'):
        r = cref(cm, 'config::cref-alias-one/' + rel)
        if os.name == 'nt':
            assert r['return'] == 1 and 'not a file or folder on Windows' in r['error'], (rel, r)
        else:
            assert r['return'] == 16, (rel, r)                  # a valid name elsewhere, and not there


def test_a_path_and_a_file_search_do_not_go_together(tree):
    cm, uid, folders = tree
    for flag in ('search_text', 'search_file_names'):
        r = cref(cm, 'config::cref-alias-one/EMails', **{flag: 'message'})
        assert r['return'] == 1 and '--' + flag in r['error'], (flag, r)
    # without a path the file search works as before
    r = cref(cm, 'config::cref-alias-one', search_text='EMails/20261115', search_files='**/*.md')
    assert r['return'] == 0 and r['files'] == [os.path.join(folders['cref-alias-one'], 'EMails', '20261115.message.md')], r


def test_a_wildcard_with_a_path_answers_with_the_artifacts_having_it(tree):
    cm, uid, folders = tree
    r = cref(cm, 'config::cref-alias-*/shared.md')
    assert r['return'] == 0 and len(r['paths']) == 2 and len(r['artifacts']) == 2, r
    for place, artifact in zip(r['paths'], r['artifacts']):          # the same order: a path per artifact
        assert place == os.path.join(artifact['path'], 'shared.md')
    r = cref(cm, 'config::cref-alias-*/' + MESSAGE)                   # only one of them has it
    assert r['return'] == 0 and [a['path'] for a in r['artifacts']] == [folders['cref-alias-one']], r
    r = cref(cm, 'config::cref-alias-*/nothing-here.md')
    assert r['return'] == 16 and 'any of the 2 artifacts found' in r['error'], r


def test_the_options_still_apply_with_a_path(tree):
    cm, uid, folders = tree
    assert len(cref(cm, 'config::cref-alias-*/shared.md', tags='cref-test')['paths']) == 2
    assert cref(cm, 'config::cref-alias-*/shared.md', tags='no-such-tag')['return'] == 16
    r = cref(cm, 'config::cref-alias-one/' + MESSAGE, skip_non_indexed=True)
    assert r['return'] == 0 and r['path'].endswith('20261115.message.md'), r


def test_smart_cref_is_smart_find_by_cid(tree):
    cm, uid, folders = tree
    full = 'config::cref-alias-one,' + uid
    for arg in ('see ' + full + ' please',                              # a cRef inside prose
                braced(full) + ' and more words',
                braced(full) + '/' + MESSAGE + ' and more words',      # the longest existing part of the path
                full + '/' + MESSAGE,
                'cref-alias-one'):                                      # smart cannot read a bare name: both refuse
        a = cm.access({'category': 'utils', 'command': 'smart_cref', 'arg1': arg, 'con': False})
        b = cm.access({'category': 'utils', 'command': 'smart_find_by_cid', 'arg1': arg, 'con': False})
        assert a['return'] == b['return'], (arg, a, b)
        assert a.get('path') == b.get('path'), arg
        assert [x['path'] for x in a.get('artifacts') or []] == [x['path'] for x in b.get('artifacts') or []], arg
    # where the smart command guesses, the exact one refuses
    assert cm.access({'category': 'utils', 'command': 'smart_cref', 'arg1': braced(full) + ' and more words', 'con': False})['return'] == 0
    assert cref(cm, braced(full) + ' and more words')['return'] == 1


def test_the_command_line_takes_a_path_after_the_cref(tree, tmp_path):
    cm, uid, folders = tree
    env = {k: v for k, v in os.environ.items() if not k.startswith('CMETA_')}
    env['CMETA_HOME'] = str(tmp_path)
    expected = os.path.join(folders['cref-alias-one'], 'EMails', '20261115.message.md')

    def cx(*args):
        return subprocess.run([sys.executable, '-m', 'cmeta'] + list(args), capture_output=True, text=True, env=env,
                              stdin=subprocess.DEVNULL, timeout=120)

    for arg in (braced('config::cref-alias-one,' + uid) + '/' + MESSAGE, 'config::cref-alias-one,' + uid + '\\EMails\\20261115.message.md'):
        out = cx('utils', 'cref', arg)
        assert out.returncode == 0 and out.stdout.strip().splitlines()[-1] == expected, out.stdout[-600:] + out.stderr[-400:]
    out = cx('utils', 'cref', braced('config::cref-alias-one') + ' and more words')
    assert out.returncode != 0 and 'smart_cref' in out.stdout + out.stderr, out.stdout[-600:] + out.stderr[-400:]
    out = cx('utils', 'smart_cref', 'see ' + braced('config::cref-alias-one,' + uid) + ' please')
    assert out.returncode == 0 and out.stdout.strip().splitlines()[-1] == folders['cref-alias-one'], out.stdout[-600:] + out.stderr[-400:]
    out = cx('utils', '--help')
    assert 'find_by_cid (cref)' in out.stdout and 'smart_find_by_cid (smart_cref)' in out.stdout, out.stdout[-800:]
