"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

Integration tests for cserver.projects, the home page of cserver: every cserver.* page plugged into this
machine as cards, then the version of the server and where cMeta lives.

Each test runs against a fresh <CMETA_HOME> in tmp_path so it does not touch the user's real cMeta state. A
fresh home has no page of its own: the internal repository ships cserver.projects only, and the page leaves
itself out of its cards.
"""

import os

import pytest

from cmeta import CMeta
from cmeta.version import __version__

URLS = {'url': 'http://127.0.0.1:8004/projects?', 'url_files': 'http://127.0.0.1:8004/projects/',
        'url_server': 'http://127.0.0.1:8004/'}

PAGE_API = '''from cmeta.category import InitCategory


class Category(InitCategory):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, module_file_path=__file__, **kwargs)

    def web_(self, ctx, urls, query={}, misc={}):
        return {'return': 0, 'html_meta': {'html': '<p>hello</p>'}}
'''


@pytest.fixture()
def cm(tmp_path, monkeypatch):
    """A fresh CMeta bound to a temp CMETA_HOME."""
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX',
                'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    return CMeta(home=str(tmp_path))


def _web(cm, **query):
    r = cm.access({'category': 'cserver.projects', 'command': 'web', 'con': False,
                   'urls': dict(URLS), 'query': query, 'misc': {}})
    assert r['return'] == 0, r
    return r


def _add_category(cm, alias, page=True):
    """A cserver.* category in the local repo; with page=True its api defines web_, so it is a page."""
    r = cm.access({'category': 'category', 'command': 'add', 'arg1': 'local:' + alias, 'con': False})
    assert r['return'] == 0, r
    if page:
        with open(os.path.join(r['path'], 'api', 'v1.py'), 'w', encoding='utf-8') as f:
            f.write(PAGE_API)
    return r['path']


# ---------------------------------------------------------------------------
# A fresh home
# ---------------------------------------------------------------------------

def test_the_terminal_lists_the_page_itself(cm):
    r = cm.access({'category': 'cserver.projects', 'command': 'pages', 'con': False})
    assert r['return'] == 0
    pages = [(p['alias'], p['page'], p['repo']) for p in r['pages']]
    assert ('cserver.projects', 'projects', 'internal') in pages
    assert ('cserver.browse', 'browse', 'internal') in pages      # the other page the engine ships


def test_a_fresh_home_has_the_browse_card(cm):
    j = _web(cm, native_action='projects')['json']
    assert 'error' not in j
    # The page leaves itself out; the engine's other page, cserver.browse, is the one card of a fresh home
    assert [(p['alias'], p['href']) for p in j['pages']] == [('cserver.browse', URLS['url_server'] + 'browse')]
    assert j['count'] == 1
    assert j['version'] == __version__
    assert j['url_server'] == URLS['url_server']


def test_the_page_shows_the_version_and_where_cmeta_lives(cm):
    meta = _web(cm)['html_meta']
    html = meta['html']
    assert '%%' not in html                          # every placeholder filled
    assert 'v' + __version__ in html
    for link in ('https://github.com/cTuningLabs/cmeta"', 'https://github.com/cTuningLabs/cmeta-aops"',
                 'https://cTuning.ai/project/cmeta"'):
        assert link in html
    assert 'id="cpj-empty"' in html                  # what a page is, shown while there is none
    assert meta['page_title'] == 'cMeta server'
    assert 'css/projects.css?v=' in meta['page_extra_style']


# ---------------------------------------------------------------------------
# Pages of plugged repositories
# ---------------------------------------------------------------------------

def test_a_page_becomes_a_card_and_a_helper_a_footnote(cm):
    _add_category(cm, 'cserver.hello')
    _add_category(cm, 'cserver.helper', page=False)

    j = _web(cm, native_action='projects')['json']
    assert [(p['alias'], p['repo'], p['href']) for p in j['pages'] if p['repo'] == 'local'] == \
        [('cserver.hello', 'local', URLS['url_server'] + 'hello')]
    assert [p['alias'] for p in j['others']] == ['cserver.helper']
    assert 'local' in j['repos'] and j['count'] == 2              # with the engine's cserver.browse
    assert all('path' not in p for p in j['pages'] + j['others'])   # no local paths on the page


def test_repo_filter(cm):
    _add_category(cm, 'cserver.hello')
    assert _web(cm, native_action='projects', repo='LOC')['json']['count'] == 1    # substring, any case
    assert _web(cm, native_action='projects', repo='nowhere')['json']['count'] == 0


def test_repositories_hidden_by_the_cserver_config(cm):
    _add_category(cm, 'cserver.hello')
    r = cm.access({'category': 'config', 'command': 'set', 'arg1': 'cserver',
                   'meta': {'hide_repos': 'other, loc*'}, 'con': False})
    assert r['return'] == 0, r

    assert [p for p in _web(cm, native_action='projects')['json']['pages'] if p['repo'] == 'local'] == []
    # Hidden from the page, not from the terminal or from its own URL.
    r = cm.access({'category': 'cserver.projects', 'command': 'pages', 'con': False})
    assert 'cserver.hello' in [p['alias'] for p in r['pages']]
