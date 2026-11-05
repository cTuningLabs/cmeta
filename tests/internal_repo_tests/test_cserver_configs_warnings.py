"""
The scan of cserver.cmeta.configs reads the Python files of the plugged artifacts with ast.parse: a file whose text
holds a bad escape (a Windows path in a string, "D:\\!FGG...") makes Python warn (SyntaxWarning) at the parse, and the
warning went to the server's output on the first scan of such a file (2026-11-05). The scan must take such a file
quietly: the warning is the file's author's, not the page's.

Each test runs against a fresh <CMETA_HOME> in tmp_path.

Licensed under the Apache License, Version 2.0.
See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
import warnings

import pytest

from cmeta import CMeta

URLS = {'url': 'http://127.0.0.1:8004/cmeta.configs?', 'url_files': 'http://127.0.0.1:8004/cmeta.configs/',
        'url_server': 'http://127.0.0.1:8004/'}

# A reader whose text carries the bad escape a Windows path brings ("\!"): Python warns when it parses it
READER = '''from cmeta.category import InitCategory

ROOT = "D:\\!Work\\repos"


class Category(InitCategory):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, module_file_path=__file__, **kwargs)

    def run_(self, ctx):
        r = self.cm.access({'category': 'config', 'command': 'read', 'arg1': 'warncfg', 'con': False})
        return {'return': 0, 'root': (r.get('config_cmeta') or {}).get('root', ROOT)}
'''


@pytest.fixture()
def cm(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    cm = CMeta(home=str(tmp_path))

    r = cm.access({'category': 'category', 'command': 'add', 'arg1': 'local:warncat', 'con': False})
    assert r['return'] == 0, r
    with open(os.path.join(r['path'], 'api', 'v1.py'), 'w', encoding='utf-8') as f:
        f.write(READER)
    return cm


def test_a_file_with_a_bad_escape_is_scanned_without_a_warning(cm):
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter('always')
        r = cm.access({'category': 'cserver.cmeta.configs', 'command': 'web', 'con': False, 'urls': dict(URLS),
                       'query': {'native_action': 'configs', 'refresh': '1'}, 'misc': {'client_local': True}})
    assert r['return'] == 0, r
    j = r['json']
    assert 'error' not in j, j

    # the reader was read (its config is listed), and Python's warning about its text stayed inside the scan
    assert any(c['name'] == 'warncfg' for c in j['configs']), [c['name'] for c in j['configs']]
    assert not [w for w in seen if issubclass(w.category, SyntaxWarning)], [str(w.message) for w in seen]
