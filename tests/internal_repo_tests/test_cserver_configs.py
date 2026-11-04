"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

Tests for cserver.cmeta.configs, the page of every key the plugged artifacts read from the config artifacts: what
their code, their docs and the "configs" block of their _desc say, joined with what is set on this machine, as each
viewer may see it.

Each test runs against a fresh <CMETA_HOME> in tmp_path, with one reader category made in its local repository.
"""

import importlib.util
import json
import os

import pytest

import cmeta
from cmeta import CMeta

URLS = {'url': 'http://127.0.0.1:8004/cmeta.configs?', 'url_files': 'http://127.0.0.1:8004/cmeta.configs/',
        'url_server': 'http://127.0.0.1:8004/'}

PAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(cmeta.__file__)), 'internal-repo', 'category',
                        'cserver.cmeta.configs')

# A category that reads its settings in every way the page follows
READER = '''from cmeta.category import InitCategory
from _lib import conf

CONFIG_ALIAS = 'mycfg'
TOKEN_KEY = 'api_token'                 # the token of the service


class Category(InitCategory):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, module_file_path=__file__, **kwargs)

    def _cfg(self):
        r = self.cm.access({'category': 'config', 'command': 'read', 'arg1': CONFIG_ALIAS, 'con': False})
        return (r.get('config_cmeta') or {}) if r.get('return', 1) == 0 else {}

    def _value(self, key, default=None):
        return self._cfg().get(key, default)

    def run_(self, ctx):
        cfg = self._cfg()
        limit = cfg.get('alpha', 5)
        beta = cfg.get('sub', {}).get('beta')
        token = cfg.get(TOKEN_KEY)
        gamma = self._value('gamma', 'g')       # the gamma of a run
        for k in ('delta', 'epsilon'):
            cfg.get(k)
        mode = cfg.get('mode_' + ctx.get('harness', 'x'))
        zeta = conf.setting(self.cm, 'othercfg', 'zeta')
        return {'return': 0}
'''

# A helper module next to the category folders (from _lib import conf), as some repositories keep them
HELPER = '''def setting(cm, name, key, default=''):
    r = cm.access({'category': 'config', 'command': 'read', 'arg1': name, 'con': False})
    return ((r.get('artifact') or {}).get('cmeta') or {}).get(key, default)
'''

DESC = '''configs:
  mycfg:
    desc: the settings of the test reader
    keys:
      alpha:
        desc: how many items at most
        type: number
        default: '5'
      api_token:
        desc: the token of the service
        secret: true
'''

README = '''# mycat

    cx config set mycfg --meta.alpha=7          # the most items it takes

| Key | Meaning |
|---|---|
| `sub.beta` | the beta of it |
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
    folder = r['path']
    with open(os.path.join(folder, 'api', 'v1.py'), 'w', encoding='utf-8') as f:
        f.write(READER)
    with open(os.path.join(folder, '_desc.yaml'), 'w', encoding='utf-8') as f:
        f.write(DESC)
    with open(os.path.join(folder, 'README.md'), 'w', encoding='utf-8') as f:
        f.write(README)
    os.makedirs(os.path.join(os.path.dirname(folder), '_lib'), exist_ok=True)
    with open(os.path.join(os.path.dirname(folder), '_lib', 'conf.py'), 'w', encoding='utf-8') as f:
        f.write(HELPER)

    r = cm.access({'category': 'config', 'command': 'set', 'arg1': 'mycfg', 'con': False,
                   'meta': {'alpha': '7', 'api_token': 's3cr3t-value-of-the-test', 'stale': '1', 'mode_codex': 'fast',
                            'sub': {'beta': 'b'}}})
    assert r['return'] == 0, r
    cm.folder = folder
    return cm


def _configs(cm, misc=None, **access):
    q = {'category': 'cserver.cmeta.configs', 'command': 'web', 'con': False, 'urls': dict(URLS),
         'query': {'native_action': 'configs', 'refresh': '1'}, 'misc': {'client_local': True} if misc is None else misc}
    q.update(access)
    r = cm.access(q)
    assert r['return'] == 0, r
    j = r['json']
    assert 'error' not in j, j
    return j


def _config(j, name):
    return next((c for c in j['configs'] if c['name'] == name), None)


def _keys(c):
    return {k['key']: k for k in c['keys']}


# ---------------------------------------------------------------------------
# What the artifacts say
# ---------------------------------------------------------------------------

def test_the_keys_come_from_the_desc_the_code_and_the_docs(cm):
    j = _configs(cm)
    c = _config(j, 'mycfg')
    assert c and c['desc'] == 'the settings of the test reader'
    k = _keys(c)

    # declared, read by the code, shown in the README: what the _desc says goes first
    assert k['alpha']['sources'] == ['declared', 'code', 'docs']
    assert k['alpha']['desc'] == 'how many items at most' and k['alpha']['type'] == 'number'
    assert '5' in k['alpha']['defaults']

    # a chain of gets, a table of the README for what it does
    assert k['sub.beta']['sources'] == ['code', 'docs'] and k['sub.beta']['desc'] == 'the beta of it'
    assert 'sub' not in k                                  # taken on the way to its part: no row of its own

    # a helper of the file with the key as a parameter: the key and the comment of the call
    assert k['gamma']['sources'] == ['code'] and k['gamma']['desc'] == 'the gamma of a run'

    # a loop over keys the code spells out; a key built at run time
    assert 'delta' in k and 'epsilon' in k
    assert 'mode_<harness>' in k

    # the comment of the constant that names a key
    assert k['api_token']['secret'] is True

    # a helper module imported from next to the category folder, the config and the key given by the call
    other = _config(j, 'othercfg')
    assert other and 'zeta' in _keys(other)
    readers = [j['artifacts'][x['aid']]['alias'] for x in _keys(other)['zeta']['readers']]
    assert readers == ['mycat']


def test_each_artifact_and_the_configs_it_uses(cm, capsys):
    """The other way round (the map of the page): an artifact, the configs it uses, what it does with each."""
    j = _configs(cm)
    mycat = next(aid for aid, a in j['artifacts'].items() if a['cat'] == 'category' and a['alias'] == 'mycat')
    uses = j['uses'][mycat]
    assert set(uses) == {'mycfg', 'othercfg'}
    assert uses['mycfg']['reads'] == 7 and uses['mycfg']['declares'] == 2 and uses['mycfg']['docs'] == 2
    assert {'alpha', 'api_token', 'delta', 'epsilon', 'gamma', 'mode_<harness>', 'sub.beta'} == set(uses['mycfg']['keys'])
    assert uses['othercfg']['keys'] == ['zeta'] and 'reads' in uses['othercfg']['how']

    # the search of the page: the keys of one artifact
    r = cm.access({'category': 'cserver.cmeta.configs', 'command': 'list', 'arg1': 'art:mycat', 'con': True})
    out = capsys.readouterr().out
    assert r['return'] == 0 and r['rows'] == 8
    assert 'config::mycfg' in out and 'config::othercfg' in out and 'config::cserver' not in out

    # each artifact and its configs in a terminal
    r = cm.access({'category': 'cserver.cmeta.configs', 'command': 'artifacts', 'arg1': 'art:mycat', 'con': True})
    out = capsys.readouterr().out
    assert r['return'] == 0 and r['artifacts'] == 1
    assert 'category::mycat' in out and 'reads 7, declares 2, shows 2' in out and 'zeta' in out


def test_the_engine_declares_its_own_keys(cm):
    j = _configs(cm)
    cs = _keys(_config(j, 'cserver'))
    assert cs['browse_files']['sources'][:2] == ['declared', 'code']           # cserver.browse
    assert cs['password']['secret'] is True and cs['param.port']['defaults'] == ['8004']
    assert _keys(_config(j, 'default'))['default_git']['defaults'] == ['https://github.com/']
    assert 'url' in _keys(_config(j, 'ctuning_server'))


# ---------------------------------------------------------------------------
# What is set here, and who sees it
# ---------------------------------------------------------------------------

def test_the_values_here_secrets_never(cm):
    j = _configs(cm)
    assert j['values'] is True
    k = _keys(_config(j, 'mycfg'))
    assert k['alpha']['set'] and k['alpha']['value'] == '7'
    assert k['api_token']['set'] and k['api_token']['value'] is None
    assert 's3cr3t-value-of-the-test' not in json.dumps(j)

    # a key set under a key the code names at run time; a key nothing reads
    assert k['mode_<harness>']['children'] == [{'key': 'mode_codex', 'value': 'fast', 'secret': False}]
    unread = _config(j, 'mycfg')['unread']
    assert [u['key'] for u in unread] == ['stale']
    assert j['stats']['unread'] == 1


def test_values_only_for_this_machine_unless_the_config_says_so(cm):
    r = cm.access({'category': 'config', 'command': 'set', 'arg1': 'lonely', 'meta': {'x': '1'}, 'con': False})
    assert r['return'] == 0
    assert _config(_configs(cm), 'lonely')['unread'] == [{'key': 'x', 'value': '1', 'secret': False, 'every': False}]

    j = _configs(cm, misc={})
    assert j['values'] is False
    c = _config(j, 'mycfg')
    assert not any(k['set'] or k['value'] or k.get('children') for k in c['keys']) and c['unread'] == []
    assert 'fast' not in json.dumps(c) and 'data_file' not in c                  # nothing of what is set here,
    assert c['artifacts'] == [] and _config(j, 'lonely') is None                 # not even which configs it holds

    r = cm.access({'category': 'config', 'command': 'set', 'arg1': 'cserver', 'meta': {'configs_values': 'yes'},
                   'con': False})
    assert r['return'] == 0
    assert _configs(cm, misc={})['values'] is True
    assert _configs(cm, misc={'ctuning_server': True})['values'] is False        # never through the cPlatform


def test_hidden_repositories_hide_their_readers_and_configs(cm):
    j = _configs(cm, hide_repos='local')
    assert _config(j, 'mycfg') is None and _config(j, 'othercfg') is None
    assert _config(j, 'cserver') is not None                                     # the engine's own stay

    # a host's own list of the repositories shown (the cPlatform's project pointer passes it in the call): the others
    # are out, their artifacts and their configs alike
    j = _configs(cm, misc={'ctuning_server': True}, only_repos='internal')
    assert _config(j, 'mycfg') is None and _config(j, 'othercfg') is None and _config(j, 'cserver') is not None
    assert {a['repo'] for a in j['artifacts'].values()} == {'internal'} and j['values'] is False
    assert all(a.split('::')[0] in {x['cat_uid'] for x in j['artifacts'].values()} for a in j['uses'])

    r = cm.access({'category': 'config', 'command': 'set', 'arg1': 'cserver', 'meta': {'hide_repos': 'loc*'},
                   'con': False})
    assert r['return'] == 0
    assert _config(_configs(cm), 'mycfg') is None


# ---------------------------------------------------------------------------
# The scan and the page
# ---------------------------------------------------------------------------

def test_the_scan_reads_again_only_what_changed(cm):
    r = cm.access({'category': 'cserver.cmeta.configs', 'command': 'scan', 'con': False})
    assert r['return'] == 0 and r['stats']['files'] > 0
    r = cm.access({'category': 'cserver.cmeta.configs', 'command': 'scan', 'con': False})
    assert r['stats']['read'] == 0

    with open(os.path.join(cm.folder, 'README.md'), 'a', encoding='utf-8') as f:
        f.write('\n    cx config set mycfg --meta.omega=1   # the last one\n')
    os.utime(os.path.join(cm.folder, 'README.md'), (1, 2_000_000_000))
    r = cm.access({'category': 'cserver.cmeta.configs', 'command': 'scan', 'con': False})
    assert r['stats']['read'] == 1
    assert _keys(_config(_configs(cm), 'mycfg'))['omega']['desc'] == 'the last one'

    # the scan is kept in the cache artifact of the local repository
    r = cm.access({'category': 'cache', 'command': 'find', 'arg1': 'cserver--cmeta-configs', 'con': False})
    assert r['return'] == 0 and len(r['artifacts']) == 1
    assert os.path.isfile(os.path.join(r['artifacts'][0]['path'], 'scan.json'))


def test_the_terminal_lists_the_keys(cm, capsys):
    r = cm.access({'category': 'cserver.cmeta.configs', 'command': 'list', 'arg1': 'config:mycfg', 'con': True})
    assert r['return'] == 0 and r['rows'] >= 7
    out = capsys.readouterr().out
    assert 'config::mycfg - the settings of the test reader' in out
    assert 'how many items at most' in out and 's3cr3t' not in out
    assert 'set here, read by no plugged artifact' in out


def test_the_page(cm):
    r = cm.access({'category': 'cserver.cmeta.configs', 'command': 'web', 'con': False, 'urls': dict(URLS),
                   'query': {}, 'misc': {}})
    assert r['return'] == 0
    meta = r['html_meta']
    assert 'id="ccf"' in meta['html'] and '%%' not in meta['html']
    assert 'css/configs.css?v=' in meta['page_extra_style'] and 'js/configs.js?v=' in meta['page_extra_style']


# ---------------------------------------------------------------------------
# The scanner alone
# ---------------------------------------------------------------------------

def _module():
    spec = importlib.util.spec_from_file_location('cserver_cmeta_configs_under_test', os.path.join(PAGE_DIR, 'api', 'v1.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_routes_and_commands_in_texts():
    m = _module()
    stats = {'parsed': 0, 'errors': 0}
    code = '''
def run(ctx):
    floor = ctx['tasks'].get('global', {}).get('init', {}).get('min_free_gb')
    cache = ctx['tasks']['global']['init'].get('hf', {}).get('cache')
'''
    facts = m._scan_text(code, 'py', stats, {'global.init': 'task'})['facts']
    assert {(f['c'], f['k']) for f in facts if f['a'] == 'read'} >= {('task', 'min_free_gb'), ('task', 'hf.cache')}

    desc = 'install: "winget install x {{global.init.winget_install_flags|}}"\n'
    facts = m._scan_text(desc, 'desc', stats, {'global.init': 'task'})['facts']
    assert [(f['c'], f['k']) for f in facts] == [('task', 'winget_install_flags')]

    text = ('cx config set default --meta.default_git=git@github.com:   # the server\n'
            'cx config set task-run-ai "--meta.local_ai_uses.<repository alias,UID>=<cref>" `\n'
            'cx config unset cserver --meta.password                      # off again\n'
            'cx config set {config} --meta.{key}=x\n')
    facts = m._doc_lines(text)
    assert [(f['c'], f['k'], f.get('x'), f.get('n')) for f in facts] == [
        ('default', 'default_git', 'git@github.com:', 'the server'),
        ('task-run-ai', 'local_ai_uses.<repository_alias,UID>', '<cref>', None),
        ('cserver', 'password', None, None)]
