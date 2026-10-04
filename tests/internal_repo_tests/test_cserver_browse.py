"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

Integration tests for cserver.browse: search, browse and graph the artifacts of every plugged repository.
Each test runs against a fresh <CMETA_HOME> in tmp_path with a few artifacts of its own.
"""

import json
import os

import pytest

from cmeta import CMeta

URLS = {'url': 'http://127.0.0.1:8004/browse?', 'url_files': 'http://127.0.0.1:8004/browse/',
        'url_server': 'http://127.0.0.1:8004/'}
REMOTE = {'url': 'https://example.org/browse?', 'url_files': 'https://example.org/browse/',
          'url_server': 'https://example.org/'}


@pytest.fixture()
def cm(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX',
                'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    cm = CMeta(home=str(tmp_path))
    make(cm, 'sla-report', tags=['report', 'sla'], created='2026-09-14T10:00:00+00:00',
         generator={'method': 'task'}, title='The SLA brief')
    make(cm, 'sla-notes', tags=['sla', 'draft'], created='2026-10-01T10:00:00+00:00')
    make(cm, 'gpu-costs', tags=['cost'], created='2025-12-31T23:00:00+00:00', owner='Olivier Caudron')
    make(cm, 'plain', created='2024-05-01T08:00:00+00:00')
    return cm


def make(cm, alias, tags=None, created=None, category='log', **meta):
    m = dict(meta)
    if tags:
        m['tags'] = tags
    if created:
        m['creation_timestamp'] = created
    r = cm.access({'category': category, 'command': 'create', 'arg1': 'local:' + alias, 'meta': m, 'con': False})
    assert r['return'] == 0, r
    return r['meta']['artifact'], r['path']


def web(cm, urls=URLS, **query):
    r = cm.access({'category': 'cserver.browse', 'command': 'web', 'con': False,
                   'urls': dict(urls), 'query': query, 'misc': {}})
    assert r['return'] == 0, r
    return r


def search(cm, **query):
    out = web(cm, native_action='search', **query)['json']
    assert 'error' not in out, out
    return out


def aliases(out):
    return [r['alias'] for r in out['rows']]


def test_the_page_renders(cm):
    r = web(cm)
    html = r['html_meta']['html']
    assert 'var CONFIG = ' in html and 'cbr-view-graph' in html
    assert 'css/browse.css?v=' in r['html_meta']['page_extra_style']


def test_words_tags_and_negation(cm):
    assert sorted(aliases(search(cm, q='sla', cats='log'))) == ['sla-notes', 'sla-report']
    assert aliases(search(cm, q='tag:report')) == ['sla-report']
    assert aliases(search(cm, q='tag:sla -tag:draft')) == ['sla-report']
    assert aliases(search(cm, q='sla -report', cats='log')) == ['sla-notes']
    assert aliases(search(cm, q='"olivier caudron"')) == ['gpu-costs']


def test_meta_keys_has_and_crefs(cm):
    assert aliases(search(cm, q='generator.method:task')) == ['sla-report']
    assert aliases(search(cm, q='owner:olivier*')) == ['gpu-costs']
    assert aliases(search(cm, q='has:owner')) == ['gpu-costs']
    assert 'gpu-costs' not in aliases(search(cm, q='-has:owner cat:log', limit=50))
    assert aliases(search(cm, q='log::gpu-costs')) == ['gpu-costs']


def test_dates_from_the_query_and_from_the_pickers(cm):
    assert sorted(aliases(search(cm, q='after:2026-09 cat:log'))) == ['sla-notes', 'sla-report']
    assert sorted(aliases(search(cm, q='before:2026 cat:log'))) == ['gpu-costs', 'plain']
    assert aliases(search(cm, cats='log', after='2026-10-01')) == ['sla-notes']


def test_pickers_repositories_and_categories(cm):
    assert search(cm, repos='local', cats='log')['total'] == 4
    assert search(cm, repos='nothing-like-this')['total'] == 0
    assert search(cm, cats='log,category', q='sla')['total'] >= 2


def test_sorting_paging_and_facets(cm):
    out = search(cm, cats='log', sort='alias', dir='asc', limit=2)
    assert aliases(out) == ['gpu-costs', 'plain'] and out['total'] == 4
    out = search(cm, cats='log', sort='alias', dir='asc', limit=2, offset=2)
    assert aliases(out) == ['sla-notes', 'sla-report']
    f = search(cm, cats='log')['facets']
    assert dict(f['cat'])['log'] == 4
    assert dict(f['tag'])['sla'] == 2
    assert dict(f['year'])['2026'] == 2


def test_relevance_puts_the_alias_first(cm):
    out = search(cm, q='sla brief')
    assert aliases(out)[0] == 'sla-report'
    assert out['rows'][0]['snippet'].startswith('title:')


def test_detail_resolves_connections_and_hides_the_path_on_a_remote_host(cm):
    target_uid, _ = make(cm, 'target')
    uid, path = make(cm, 'source')
    with open(os.path.join(path, '_desc.json'), 'w', encoding='utf-8') as f:
        json.dump({'connections': ['log::target,%s' % target_uid, 'log::missing,0123456789abcdef']}, f)

    d = web(cm, native_action='artifact', uid=uid)['json']
    assert d['row']['alias'] == 'source' and d['path'] == path
    assert [(c['alias'], c['found']) for c in d['connections']] == [('target', True), ('missing', False)]
    assert d['commands'][0] == 'cx log find source,%s' % uid

    d = web(cm, REMOTE, native_action='artifact', uid=uid)['json']
    assert 'path' not in d


def test_graph_joins_the_results_by_their_connections(cm):
    a, _ = make(cm, 'g-a')
    b, pb = make(cm, 'g-b')
    with open(os.path.join(pb, '_desc.json'), 'w', encoding='utf-8') as f:
        json.dump({'connections': ['log::g-a,%s' % a]}, f)

    g = web(cm, native_action='graph', q='g-', max_nodes=10)['json']
    assert sorted(n['alias'] for n in g['nodes']) == ['g-a', 'g-b']
    assert g['links'] == [{'source': b, 'target': a}]

    g = web(cm, native_action='graph', q='g-b', max_nodes=10, neighbors='1')['json']
    assert sorted((n['alias'], n['neighbor']) for n in g['nodes']) == [('g-a', True), ('g-b', False)]


def test_a_new_artifact_shows_without_a_restart(cm):
    assert search(cm, q='brand-new')['total'] == 0
    make(cm, 'brand-new')
    assert aliases(search(cm, q='brand-new')) == ['brand-new']


def test_secret_categories_are_hidden_unless_the_config_says_none(cm):
    r = cm.access({'category': 'category', 'command': 'add', 'arg1': 'local:my.crypt', 'con': False})
    assert r['return'] == 0, r
    make(cm, 'a-key-bundle', category='my.crypt')
    assert search(cm, q='a-key-bundle')['total'] == 0

    r = cm.access({'category': 'config', 'command': 'set', 'arg1': 'cserver',
                   'meta': {'browse_hide_categories': 'none'}, 'con': False})
    assert r['return'] == 0, r
    assert aliases(search(cm, q='a-key-bundle')) == ['a-key-bundle']


def test_hide_repos_applies(cm):
    r = cm.access({'category': 'config', 'command': 'set', 'arg1': 'cserver',
                   'meta': {'hide_repos': 'loc*'}, 'con': False})
    assert r['return'] == 0, r
    assert search(cm, cats='log')['total'] == 0


def test_the_terminal_query(cm, capsys):
    r = cm.access({'category': 'cserver.browse', 'command': 'query', 'arg1': 'tag:report', 'con': True})
    assert r['return'] == 0, r
    assert r['total'] == 1 and r['rows'][0]['alias'] == 'sla-report'
    assert '1 of' in capsys.readouterr().out
