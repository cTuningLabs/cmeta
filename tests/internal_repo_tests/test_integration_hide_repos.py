"""
Integration tests for the scope of one call: `hide_repos` in CMeta.access hides the artifacts of some
repositories from that call and from every call it makes (a server applies it per request, for what a
signed-in person may not see). The repositories stay registered; only their contents are hidden.

Each test runs against a fresh <CMETA_HOME> in tmp_path with two local repositories of its own.

Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.
"""

import os

import pytest

from cmeta import CMeta

URLS = {'url': 'http://127.0.0.1:8004/browse?', 'url_files': 'http://127.0.0.1:8004/browse/',
        'url_server': 'http://127.0.0.1:8004/'}


@pytest.fixture()
def cm(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    cm = CMeta(home=str(tmp_path))

    # a second local repository, "private": the artifacts a scope hides
    r = cm.access({'category': 'repo', 'command': 'create', 'arg1': 'private', 'con': False})
    assert r['return'] == 0, r

    for repo, alias in (('local', 'public-note'), ('private', 'secret-note'), ('private', 'secret-note-2')):
        r = cm.access({'category': 'log', 'command': 'create', 'arg1': '%s:%s' % (repo, alias),
                       'meta': {'tags': ['note']}, 'con': False})
        assert r['return'] == 0, r
    return cm


def names(r):
    assert r['return'] in (0, 16), r
    return sorted(a['cmeta_ref_parts']['artifact_alias'] for a in r.get('artifacts', []))


def test_find_and_list_leave_the_hidden_repository_out(cm):
    assert names(cm.access({'category': 'log', 'command': 'find', 'arg1': '*', 'con': False})) == \
        ['public-note', 'secret-note', 'secret-note-2']

    scoped = cm.access({'category': 'log', 'command': 'find', 'arg1': '*', 'con': False, 'hide_repos': 'private'})
    assert names(scoped) == ['public-note']

    # by alias: not found at all; by UID neither
    r = cm.access({'category': 'log', 'command': 'find', 'arg1': 'secret-note', 'con': False})
    uid = r['artifacts'][0]['cmeta_ref_parts']['artifact_uid']
    r = cm.access({'category': 'log', 'command': 'find', 'arg1': 'secret-note', 'con': False, 'hide_repos': 'private'})
    assert r['return'] == 16, r
    r = cm.access({'category': 'log', 'command': 'find', 'arg1': uid, 'con': False, 'hide_repos': ['private']})
    assert r['return'] == 16, r
    r = cm.access({'category': 'log', 'command': 'read', 'arg1': uid, 'con': False, 'hide_repos': 'private'})
    assert r['return'] > 0, r

    # ls as well
    r = cm.access({'category': 'log', 'command': 'ls', 'con': False, 'hide_repos': 'private'})
    assert r['return'] == 0, r
    assert 'secret-note' not in str(r)


def test_the_scope_takes_uids_and_patterns_and_ends_with_the_call(cm):
    r = cm.access({'category': 'repo', 'command': 'find', 'arg1': 'private', 'con': False})
    uid = r['artifacts'][0]['cmeta_ref_parts']['artifact_uid']

    assert names(cm.access({'category': 'log', 'command': 'find', 'arg1': '*', 'con': False, 'hide_repos': uid})) == ['public-note']
    assert names(cm.access({'category': 'log', 'command': 'find', 'arg1': '*', 'con': False, 'hide_repos': 'priv*'})) == ['public-note']
    assert names(cm.access({'category': 'log', 'command': 'find', 'arg1': '*', 'con': False, 'hide_repos': 'local,private'})) == []

    # the scope is gone once the call returned, whatever the call did
    assert cm.repos.hidden_repos == ()
    assert names(cm.access({'category': 'log', 'command': 'find', 'arg1': '*', 'con': False})) == \
        ['public-note', 'secret-note', 'secret-note-2']
    r = cm.access({'category': 'log', 'command': 'find', 'arg1': 'no-such-artifact', 'con': False, 'hide_repos': 'private'})
    assert r['return'] == 16
    assert cm.repos.hidden_repos == ()


def test_the_repository_stays_registered_only_its_contents_hide(cm):
    r = cm.access({'category': 'repo', 'command': 'find', 'arg1': 'private', 'con': False, 'hide_repos': 'private'})
    assert r['return'] == 0 and len(r['artifacts']) == 1, r
    r = cm.access({'category': 'repo', 'command': 'ls', 'con': False, 'hide_repos': 'private'})
    assert r['return'] == 0, r


def test_a_category_defined_in_a_hidden_repository_is_not_found(cm):
    r = cm.access({'category': 'category', 'command': 'create', 'arg1': 'private:secret.kind', 'con': False})
    assert r['return'] == 0, r
    r = cm.access({'category': 'secret.kind', 'command': 'create', 'arg1': 'private:thing', 'con': False})
    assert r['return'] == 0, r

    r = cm.access({'category': 'secret.kind', 'command': 'find', 'arg1': '*', 'con': False})
    assert r['return'] == 0 and len(r['artifacts']) == 1
    r = cm.access({'category': 'secret.kind', 'command': 'find', 'arg1': '*', 'con': False, 'hide_repos': 'private'})
    assert r['return'] > 0 and 'not found' in r.get('error', ''), r


def test_nested_calls_inherit_the_scope_the_browse_page_included(cm):
    def search(**query):
        r = cm.access({'category': 'cserver.browse', 'command': 'web', 'con': False, 'urls': dict(URLS),
                       'query': dict(query, native_action='search', cats='log'), 'misc': {}, **({'hide_repos': 'private'} if query.pop('scoped', False) else {})})
        assert r['return'] == 0, r
        assert 'error' not in r['json'], r['json']
        return sorted(x['alias'] for x in r['json']['rows'])

    assert search() == ['public-note', 'secret-note', 'secret-note-2']
    assert search(scoped=True) == ['public-note']
    # a hidden artifact asked for by its UID: not shown either, nor resolved by cRef
    r = cm.access({'category': 'log', 'command': 'find', 'arg1': 'secret-note', 'con': False})
    uid = r['artifacts'][0]['cmeta_ref_parts']['artifact_uid']
    r = cm.access({'category': 'cserver.browse', 'command': 'web', 'con': False, 'urls': dict(URLS),
                   'query': {'native_action': 'artifact', 'uid': uid}, 'misc': {}, 'hide_repos': 'private'})
    assert 'error' in r['json'], r['json']
    r = cm.access({'category': 'cserver.browse', 'command': 'web', 'con': False, 'urls': dict(URLS),
                   'query': {'native_action': 'resolve', 'cref': 'log::secret-note'}, 'misc': {}, 'hide_repos': 'private'})
    assert r['json']['uid'] == '' and r['json']['notice'], r['json']
    # and the catalog kept per process was not narrowed by the scoped request before
    assert search() == ['public-note', 'secret-note', 'secret-note-2']


def test_the_terminal_takes_the_scope_as_a_flag(cm, tmp_path):
    import subprocess
    import sys
    env = dict(os.environ, CMETA_HOME=str(tmp_path))
    for var in ('CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX'):
        env.pop(var, None)
    out = subprocess.run([sys.executable, '-m', 'cmeta', 'log', 'ls', '--hide_repos=private'], env=env,
                         capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert out.returncode == 0, out.stderr
    assert 'public-note' in out.stdout and 'secret-note' not in out.stdout
