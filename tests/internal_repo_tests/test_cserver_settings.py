"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

Tests for cserver.settings (2026-11-10), the settings page: every config key the plugged artifacts read, as
/cmeta.configs knows them, in groups a search prunes, each set or taken out in place - the value typed as the key is
(the kind of the value it replaces, else the declared type), a dotted key nested, a secret never shown, the refusals
(a browser elsewhere, another site, the cTuning platform, a word for a number, a key nothing reads).

Each test runs against a fresh <CMETA_HOME> in tmp_path, with one reader category made in its local repository.
"""

import os

import pytest

from cmeta import CMeta

URLS = {'url': 'http://127.0.0.1:8004/settings?', 'url_files': 'http://127.0.0.1:8004/settings/',
        'url_server': 'http://127.0.0.1:8004/'}
LOCAL = {'client_local': True, 'same_origin': True}

READER = '''from cmeta.category import InitCategory


class Category(InitCategory):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, module_file_path=__file__, **kwargs)

    def run_(self, ctx):
        r = self.cm.access({'category': 'config', 'command': 'read', 'arg1': 'mycfg', 'con': False})
        cfg = (r.get('config_cmeta') or {}) if r.get('return', 1) == 0 else {}
        return {'return': 0, 'alpha': cfg.get('alpha', 5), 'beta': cfg.get('sub', {}).get('beta'), 'token': cfg.get('api_token'),
                'on': cfg.get('switch'), 'names': cfg.get('names'), 'note': cfg.get('note')}
'''

DESC = '''configs:
  mycfg:
    desc: the settings of the test reader
    keys:
      alpha:
        desc: how many items at most
        type: number
        default: '5'
      sub.beta:
        desc: the beta of it
      api_token:
        desc: the token of the service
        secret: true
      switch:
        desc: on or off
        type: yes/no
      names:
        desc: the names it takes
        type: list
      note:
        desc: a line of text
'''


@pytest.fixture()
def cm(tmp_path, monkeypatch):
    """A fresh CMeta bound to a temp CMETA_HOME, with the reader category and a config artifact set."""
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    cm = CMeta(home=str(tmp_path))
    r = cm.access({'category': 'category', 'command': 'add', 'arg1': 'local:mycat', 'con': False})
    assert r['return'] == 0, r
    with open(os.path.join(r['path'], 'api', 'v1.py'), 'w', encoding='utf-8') as f:
        f.write(READER)
    with open(os.path.join(r['path'], '_desc.yaml'), 'w', encoding='utf-8') as f:
        f.write(DESC)
    r = cm.access({'category': 'config', 'command': 'set', 'arg1': 'mycfg', 'con': False,
                   'meta': {'alpha': 7, 'api_token': 's3cr3t-value-of-the-test', 'sub': {'beta': 'b'}, 'names': ['x', 'y'],
                            'stale': 'old'}})
    assert r['return'] == 0, r
    return cm


def act(cm, na, misc=None, **query):
    r = cm.access({'category': 'cserver.settings', 'command': 'web', 'con': False, 'urls': dict(URLS),
                   'misc': dict(LOCAL if misc is None else misc), 'query': dict(query, native_action=na)})
    assert r['return'] == 0, r
    return r['json']


def group(cm, name='mycfg', misc=None):
    j = act(cm, 'settings', misc)
    assert 'error' not in j, j
    return next((g for g in j['groups'] if g['name'] == name), None), j


def key(g, name):
    return next((k for k in g['keys'] if k['key'] == name), None)


def stored(cm):
    r = cm.access({'category': 'config', 'command': 'read', 'arg1': 'mycfg', 'con': False})
    assert r['return'] == 0, r
    return r.get('config_cmeta') or {}


def test_the_groups_and_their_keys(cm):
    g, j = group(cm)
    assert g and g['here'] is True and g['desc'] == 'the settings of the test reader' and 'mycat' in ' '.join(g['readers'])
    assert j['values'] is True and j['edit'] is True
    k = {x['key']: x for x in g['keys']}
    assert k['alpha']['set'] is True and k['alpha']['value'] == 7 and k['alpha']['type'] == 'number' and k['alpha']['default'] == '5'
    assert k['sub.beta']['set'] is True and k['sub.beta']['value'] == 'b'
    assert k['api_token']['secret'] is True and k['api_token']['set'] is True and k['api_token']['value'] is None
    assert k['switch']['set'] is False and k['switch']['value'] is None and k['switch']['type'] == 'yes/no'
    assert k['names']['value'] == ['x', 'y'] and k['names']['list'] is True
    # set here, read by nothing: listed as such
    assert k['stale']['unread'] is True and k['stale']['value'] == 'old'
    assert g['set_count'] == 5
    # a pattern of keys (<x>_create_repo) and the patterns of dynamic config names are no rows
    assert not any('<' in x['key'] for gg in j['groups'] for x in gg['keys']) and not any('<' in gg['name'] for gg in j['groups'])
    # the page itself renders, titled Settings
    r = cm.access({'category': 'cserver.settings', 'command': 'web', 'con': False, 'urls': dict(URLS), 'misc': dict(LOCAL), 'query': {}})
    assert r['return'] == 0 and r['html_meta']['page_title'] == 'Settings' and 'id="cst"' in r['html_meta']['html']


def test_set_as_the_key_is_and_unset(cm):
    # a number stays a number; a word is refused
    r = act(cm, 'set', config='mycfg', key='alpha', value='12')
    assert r['changed'] is True and r['value'] == 12 and r['old'] == 7 and r['was_set'] is True and stored(cm)['alpha'] == 12
    assert 'number' in act(cm, 'set', config='mycfg', key='alpha', value='many')['error'] and stored(cm)['alpha'] == 12
    assert act(cm, 'set', config='mycfg', key='alpha', value='12')['changed'] is False
    # a dotted key nested; a list from commas
    r = act(cm, 'set', config='mycfg', key='sub.beta', value='c')
    assert r['changed'] and stored(cm)['sub'] == {'beta': 'c'}
    r = act(cm, 'set', config='mycfg', key='names', value='a, b ,c')
    assert r['value'] == ['a', 'b', 'c'] and stored(cm)['names'] == ['a', 'b', 'c']
    # a key not set yet: the declared type - yes/no as the word, a text as typed
    r = act(cm, 'set', config='mycfg', key='switch', value='Yes')
    assert r['was_set'] is False and r['value'] == 'yes' and stored(cm)['switch'] == 'yes'
    assert 'yes or no' in act(cm, 'set', config='mycfg', key='switch', value='maybe')['error']
    r = act(cm, 'set', config='mycfg', key='note', value='  a line  ')
    assert r['value'] == '  a line  ' and stored(cm)['note'] == '  a line  '
    # unset: the key leaves the file; again: nothing
    r = act(cm, 'unset', config='mycfg', key='sub.beta')
    assert r['changed'] is True and r['old'] == 'c' and 'beta' not in stored(cm).get('sub', {})
    assert act(cm, 'unset', config='mycfg', key='sub.beta')['changed'] is False
    r = act(cm, 'unset', config='mycfg', key='stale')
    assert r['changed'] is True and 'stale' not in stored(cm)
    # the page reads it all back
    g, _ = group(cm)
    assert key(g, 'alpha')['value'] == 12 and key(g, 'switch')['value'] == 'yes' and key(g, 'sub.beta')['set'] is False
    assert key(g, 'stale') is None


def test_a_secret_is_set_but_never_shown(cm):
    r = act(cm, 'set', config='mycfg', key='api_token', value='new-secret')
    assert r['changed'] is True and r['value'] is None and r['old'] is None and stored(cm)['api_token'] == 'new-secret'
    g, _ = group(cm)
    assert key(g, 'api_token')['value'] is None and key(g, 'api_token')['set'] is True
    r = act(cm, 'unset', config='mycfg', key='api_token')
    assert r['changed'] is True and r['old'] is None and 'api_token' not in stored(cm)


def test_refusals(cm):
    # a key nothing reads, a config nothing knows, a bad key
    assert 'no plugged artifact reads' in act(cm, 'set', config='mycfg', key='nosuch', value='1')['error']
    assert 'no config' in act(cm, 'set', config='nowhere', key='alpha', value='1')['error']
    assert 'key' in act(cm, 'set', config='mycfg', key='a..b', value='1')['error']
    # who may: a browser elsewhere (no values, no edit), another site, the cTuning platform
    g, j = group(cm, misc={})
    assert j['edit'] is False and j['values'] is False and g is not None and key(g, 'alpha')['value'] is None
    assert 'browser' in act(cm, 'set', misc={}, config='mycfg', key='alpha', value='1')['error']
    assert 'did not come' in act(cm, 'set', misc={'client_local': True}, config='mycfg', key='alpha', value='1')['error']
    assert 'not here' in act(cm, 'set', misc={'ctuning_server': True, 'same_origin': True}, config='mycfg', key='alpha', value='1')['error']
    assert stored(cm)['alpha'] == 7


def test_the_terminal_list(cm, capsys):
    r = cm.access({'category': 'cserver.settings', 'command': 'list', 'arg1': 'alpha', 'con': True})
    assert r['return'] == 0 and [g['name'] for g in r['groups']] == ['mycfg'] and [k['key'] for k in r['groups'][0]['keys']] == ['alpha']
    out = capsys.readouterr().out
    assert 'mycfg' in out and 'alpha' in out and '7' in out and 's3cr3t' not in out
    r = cm.access({'category': 'cserver.settings', 'command': 'list', 'show': 'set', 'con': False})
    assert all(k['set'] for g in r['groups'] for k in g['keys'])
    assert cm.access({'category': 'cserver.settings', 'command': 'list', 'show': 'odd', 'con': False})['return'] > 0
