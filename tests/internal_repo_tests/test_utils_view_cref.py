"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

cx utils view_cref (2026-11-10): the page of an artifact on this machine's cMeta server, opened in a browser - the
address from the config (cserver_url of "default", else the cserver's port), "." for the artifact of the current
directory, a {{{cRef}}}/file, the browser (the system's, a name webbrowser knows, a command with %s) started
detached, the refusals. The browser is never started here: webbrowser and Popen are replaced.
"""

import os
import subprocess
import webbrowser

import pytest

from cmeta import CMeta


@pytest.fixture()
def cm(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    cm = CMeta(home=str(tmp_path))
    r = cm.access({'category': 'log', 'command': 'add', 'arg1': 'local:my log', 'con': False})
    assert r['return'] == 0, r
    f = cm.access({'category': 'log', 'command': 'find', 'arg1': 'my log', 'con': False})
    cm.made = {'path': r['path'], 'uid': f['artifacts'][0]['cmeta_ref_parts']['artifact_uid']}
    return cm


def view(cm, **p):
    return cm.access(dict({'category': 'utils', 'command': 'view_cref', 'con': False, 'print_only': True}, **p))


def test_the_address_from_the_config_and_the_default(cm):
    uid = cm.made['uid']
    r = view(cm, arg1='log::my log')
    assert r['return'] == 0 and r['url'] == 'http://127.0.0.1:8004/cref/log::my%20log,' + uid and r['opened'] is False
    # the port of the cserver config, then cserver_url of the default config (a trailing / or /cref taken off)
    assert cm.access({'category': 'config', 'command': 'set', 'arg1': 'cserver', 'meta': {'param': {'port': 8010}}, 'con': False})['return'] == 0
    assert view(cm, arg1='log::my log')['url'].startswith('http://127.0.0.1:8010/cref/')
    assert cm.access({'category': 'config', 'command': 'set', 'arg1': 'default', 'meta': {'cserver_url': 'http://my-laptop:8004/cref/'}, 'con': False})['return'] == 0
    assert view(cm, arg1='log::my log')['url'] == 'http://my-laptop:8004/cref/log::my%20log,' + uid
    assert view(cm, arg1='log::my log', url='other:1234')['url'] == 'http://other:1234/cref/log::my%20log,' + uid
    # the braces of a text, a file after them; an artifact that is not here is opened as named (the page says so)
    r = view(cm, arg1='{{{log::my log,%s}}}/README.md' % uid)
    assert r['url'].endswith('/cref/log::my%20log,' + uid + '/README.md') and r['cref'] == 'log::my log,' + uid
    assert view(cm, arg1='log::no such thing')['url'].endswith('/cref/log::no%20such%20thing')
    assert view(cm, arg1='nonsense')['return'] > 0 and 'not a cRef' in view(cm, arg1='nonsense')['error']


def test_a_dot_is_the_artifact_of_the_current_directory(cm, monkeypatch):
    uid = cm.made['uid']
    monkeypatch.chdir(cm.made['path'])
    assert view(cm, arg1='.')['url'].endswith('/cref/log::my%20log,' + uid)
    sub = os.path.join(cm.made['path'], 'deeper')
    os.makedirs(sub)
    monkeypatch.chdir(sub)
    assert view(cm)['url'].endswith('/cref/log::my%20log,' + uid)             # a folder inside it too
    monkeypatch.chdir(os.path.dirname(os.path.dirname(cm.made['path'])))       # the repository's root: no artifact
    assert view(cm, arg1='.')['return'] > 0


def test_the_browser_detached(cm, monkeypatch):
    calls = []
    monkeypatch.setattr(webbrowser, 'open', lambda url, new=0, autoraise=True: calls.append(('default', url, new)) or True)
    r = cm.access({'category': 'utils', 'command': 'view_cref', 'arg1': 'log::my log', 'con': False})
    assert r['return'] == 0 and r['opened'] is True and calls[-1] == ('default', r['url'], 2)
    # a command of one's own, from the config: started with Popen, detached, nothing waited for; %s = the address
    popen = []

    class Fake:
        def __init__(self, argv, **kw):
            popen.append((argv, kw))

    monkeypatch.setattr(subprocess, 'Popen', Fake)
    assert cm.access({'category': 'config', 'command': 'set', 'arg1': 'default', 'meta': {'browser': '"C:/my browser/b.exe" --new-window %s'}, 'con': False})['return'] == 0
    r = cm.access({'category': 'utils', 'command': 'view_cref', 'arg1': 'log::my log', 'con': False})
    assert r['return'] == 0 and r['opened'] is True
    argv, kw = popen[-1]
    assert argv[-1] == r['url'] and argv[-2] == '--new-window' and 'my browser' in argv[0]
    assert kw.get('start_new_session') or kw.get('creationflags')
    assert kw['stdin'] is subprocess.DEVNULL and kw['stdout'] is subprocess.DEVNULL and kw['close_fds'] is True
    # --browser wins over the config; a command without %s gets the address last
    r = cm.access({'category': 'utils', 'command': 'view_cref', 'arg1': 'log::my log', 'browser': 'mybrowser', 'con': False})
    assert r['return'] == 0 and popen[-1][0] == ['mybrowser', r['url']]
