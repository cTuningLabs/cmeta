"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

Integration tests for cserver.browse: search, browse and graph the artifacts of every plugged repository.
Each test runs against a fresh <CMETA_HOME> in tmp_path with a few artifacts of its own.
"""

import json
import os
import sys

import pytest

from cmeta import CMeta

URLS = {'url': 'http://127.0.0.1:8004/browse?', 'url_files': 'http://127.0.0.1:8004/browse/',
        'url_server': 'http://127.0.0.1:8004/'}
LOCAL = {'client_local': True}       # what the engine cserver passes for a browser on its own machine
BOTH = {'client_local': True, 'same_origin': True}      # ... and for a request a page of this server sent


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
    make(cm, 'gpu-costs', tags=['cost'], created='2025-12-31T23:00:00+00:00', owner='Ada Lovelace')
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


def web(cm, misc=None, **query):
    r = cm.access({'category': 'cserver.browse', 'command': 'web', 'con': False,
                   'urls': dict(URLS), 'query': query, 'misc': dict(misc or {})})
    assert r['return'] == 0, r
    return r


def graph(cm, **query):
    out = web(cm, native_action='graph', **query)['json']
    assert 'error' not in out, out
    return out


def connect(path, *crefs, uses=None):
    """Write the _desc of an artifact folder: its connections, and the uses list of a task."""
    desc = {'connections': list(crefs)}
    if uses:
        desc['uses'] = uses
    with open(os.path.join(path, '_desc.json'), 'w', encoding='utf-8') as f:
        json.dump(desc, f)


def describe(path, desc):
    """Write any _desc of an artifact folder."""
    with open(os.path.join(path, '_desc.json'), 'w', encoding='utf-8') as f:
        json.dump(desc, f)


def page_config(r):
    """The CONFIG the page carries."""
    return json.loads(r['html_meta']['html'].split('var CONFIG = ', 1)[1].split(';</script>', 1)[0])


def arts(g):
    return sorted(n['label'] for n in g['nodes'] if n['kind'] == 'artifact')


def edges(g, kind):
    names = {n['id']: n['label'] for n in g['nodes']}
    return sorted((names[x['s']], names[x['t']]) for x in g['links'] if x['k'] == kind)


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
    assert 'js/graph.js?v=' in r['html_meta']['page_extra_style']
    assert '"files": false' in html                      # not a browser on the server's machine
    assert '"files": true' in web(cm, misc=LOCAL)['html_meta']['html']


def test_words_tags_and_negation(cm):
    assert sorted(aliases(search(cm, q='sla', cats='log'))) == ['sla-notes', 'sla-report']
    assert aliases(search(cm, q='tag:report')) == ['sla-report']
    assert aliases(search(cm, q='tag:sla -tag:draft')) == ['sla-report']
    assert aliases(search(cm, q='sla -report', cats='log')) == ['sla-notes']
    assert aliases(search(cm, q='"ada lovelace"')) == ['gpu-costs']


def test_meta_keys_has_and_crefs(cm):
    assert aliases(search(cm, q='generator.method:task')) == ['sla-report']
    assert aliases(search(cm, q='owner:ada*')) == ['gpu-costs']
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


def test_detail_resolves_connections_both_ways_and_shows_the_path_only_locally(cm):
    target_uid, _ = make(cm, 'target')
    uid, path = make(cm, 'source')
    task_uid, task_path = make(cm, 'runner')
    connect(path, 'log::target,%s' % target_uid, 'log::missing,0123456789abcdef', 'log::plain')
    connect(task_path, uses=[{'log': 'target,%s' % target_uid, 'name': 'python'}])
    web(cm, native_action='reload')

    d = web(cm, LOCAL, native_action='artifact', uid=uid)['json']
    assert d['row']['alias'] == 'source' and d['path'] == path
    assert [(c['alias'], c['found']) for c in d['connections']] == [('target', True), ('missing', False),
                                                                     ('plain', True)]   # cat::alias resolves too
    assert d['commands'][0] == 'cx log find source,%s' % uid
    assert d['files'] is True

    d = web(cm, native_action='artifact', uid=uid)['json']
    assert 'path' not in d and d['files'] is False

    graph(cm, q='target')                                # waits for the connection index
    d = web(cm, native_action='artifact', uid=target_uid)['json']
    assert [(c['alias'], c['uses']) for c in d['incoming']] == [('runner', True), ('source', False)]
    d = web(cm, native_action='artifact', uid=task_uid)['json']
    assert [(c['alias'], c['found']) for c in d['uses']] == [('target', True)]


def test_graph_joins_the_results_by_their_connections(cm):
    a, _ = make(cm, 'g-a')
    b, pb = make(cm, 'g-b')
    connect(pb, 'log::g-a,%s' % a)
    web(cm, native_action='reload')

    g = graph(cm, q='g-', cats='log', categories='0')
    assert arts(g) == ['g-a', 'g-b'] and edges(g, 'link') == [('g-b', 'g-a')]
    assert [n['kind'] for n in g['nodes']] == ['artifact', 'artifact']
    assert set(g['timing']) >= {'catalog', 'index', 'select', 'graph', 'server'} and g['index']['ready']

    g = graph(cm, q='g-', cats='log', core='1')          # the layout: artifacts hang off their category node
    assert [n['label'] for n in g['nodes'] if n['kind'] != 'artifact'] == ['cMeta', 'log']
    assert edges(g, 'member') == [('log', 'g-a'), ('log', 'g-b')] and edges(g, 'core') == [('cMeta', 'log')]
    assert g['cats'][0][:2] == ['log', 2]

    for q in ('g-a', 'g-b'):                             # + connected works both ways
        g = graph(cm, q=q, cats='log', neighbors='1', categories='0')
        assert arts(g) == ['g-a', 'g-b'] and g['stats']['grown'] == 1


def test_graph_hides_isolated_artifacts_only_without_categories(cm):
    a, _ = make(cm, 'iso-a')
    b, pb = make(cm, 'iso-b')
    make(cm, 'iso-alone')
    connect(pb, 'log::iso-a,%s' % a)
    web(cm, native_action='reload')

    assert arts(graph(cm, q='iso-', cats='log')) == ['iso-a', 'iso-alone', 'iso-b']
    g = graph(cm, q='iso-', cats='log', categories='0')
    assert arts(g) == ['iso-a', 'iso-b'] and g['stats']['isolated_hidden'] == 1
    assert any('isolated' in n for n in g['notices'])
    assert arts(graph(cm, q='iso-', cats='log', categories='0', isolated='1')) == ['iso-a', 'iso-alone', 'iso-b']


def test_graph_focus_follows_connections_to_a_depth(cm):
    uids = {}
    for name in ('f-1', 'f-2', 'f-3', 'f-4'):
        uids[name] = make(cm, name)
    for x, y in (('f-1', 'f-2'), ('f-2', 'f-3'), ('f-3', 'f-4')):    # a chain f-1 - f-2 - f-3 - f-4
        connect(uids[x][1], 'log::%s,%s' % (y, uids[y][0]))
    web(cm, native_action='reload')

    g = graph(cm, focus=uids['f-2'][0], depth='1', q='words are not applied while focused')
    assert arts(g) == ['f-1', 'f-2', 'f-3']
    assert g['focus']['alias'] == 'f-2' and g['focus']['next'] == 1
    assert {n['label']: n['hop'] for n in g['nodes'] if n['kind'] == 'artifact'} == {'f-1': 1, 'f-2': 0, 'f-3': 1}
    assert arts(graph(cm, focus='log::f-2', depth='2')) == ['f-1', 'f-2', 'f-3', 'f-4']
    assert graph(cm, focus='f-2', depth='2', cats='nothing-like-this')['focus'] is None
    assert 'Nothing to focus on' in graph(cm, focus='no-such-artifact')['notices'][0]


def test_graph_draws_uses_as_directed_edges(cm):
    a, _ = make(cm, 'uses-setup')
    b, pb = make(cm, 'uses-task')
    connect(pb, 'log::uses-setup,%s' % a, uses=[{'log': 'uses-setup,%s' % a, 'version': '1.2'}])
    web(cm, native_action='reload')

    g = graph(cm, q='uses-', cats='log')
    assert edges(g, 'uses') == [('uses-task', 'uses-setup')]   # drawn once, as a uses edge with its arrow
    assert edges(g, 'link') == [] and g['stats']['uses'] == 1


def test_graph_draws_ai_uses_as_directed_edges_and_the_detail_lists_them(cm):
    a, pa = make(cm, 'ai-engine')
    b, pb = make(cm, 'ai-plugin')
    # the plugin's AI sessions read the engine's memory: a one-way `ai_uses` next to the two-way connection
    with open(os.path.join(pb, '_desc.json'), 'w', encoding='utf-8') as f:
        json.dump({'connections': ['log::ai-engine,%s' % a], 'ai_uses': ['log,::ai-engine,%s' % a]}, f)
    connect(pa, 'log::ai-plugin,%s' % b)
    web(cm, native_action='reload')

    g = graph(cm, q='ai-', cats='log')
    assert edges(g, 'ai') == [('ai-plugin', 'ai-engine')]        # drawn once, with its arrow
    assert edges(g, 'link') == [] and g['stats']['ai_uses'] == 1 and g['stats']['links'] == 0

    d = web(cm, native_action='artifact', uid=b)['json']
    assert [x['alias'] for x in d['ai_uses']] == ['ai-engine'] and d['ai_uses'][0]['found']
    e = web(cm, native_action='artifact', uid=a)['json']
    assert [(x['alias'], x['ai']) for x in e['incoming']] == [('ai-plugin', True)]


def test_graph_samples_fairly_across_categories(cm):
    r = cm.access({'category': 'category', 'command': 'add', 'arg1': 'local:my.notes', 'con': False})
    assert r['return'] == 0, r
    for i in range(14):
        make(cm, 'many-%02d' % i)
    for i in range(3):
        make(cm, 'note-%d' % i, category='my.notes')

    g = graph(cm, cats='log,my.notes', max_nodes='10')
    drawn = [n['cat'] for n in g['nodes'] if n['kind'] == 'artifact']
    assert len(drawn) == 10 and drawn.count('my.notes') == 3            # the small category is not crowded out
    assert g['stats']['capped'] == 18 + 3 - 10 and any('Showing 10 of 21' in n for n in g['notices'])


def test_file_browser_is_local_and_guarded(cm, tmp_path):
    uid, path = make(cm, 'with-files')
    os.makedirs(os.path.join(path, 'files', '.git'))
    for rel, text in (('README.md', '# hello'), ('files/data.csv', 'a,b'), ('id_ed25519', 'KEY'),
                      ('api_token.txt', 'T'), ('.env', 'X=1'), ('files/.git/config', 'c')):
        with open(os.path.join(path, *rel.split('/')), 'w', encoding='utf-8') as f:
            f.write(text)
    with open(os.path.join(str(tmp_path), 'outside.txt'), 'w', encoding='utf-8') as f:
        f.write('outside')

    assert 'error' in web(cm, native_action='files', uid=uid)['json']        # not a browser on this machine
    out = web(cm, LOCAL, native_action='files', uid=uid)['json']
    rels = [f['rel'] for f in out['files']]
    assert rels[0].startswith('_cmeta') and rels[1:] == ['README.md', 'files/data.csv']

    assert web(cm, LOCAL, native_action='file', uid=uid, rel='README.md')['json']['text'] == '# hello'
    for rel in ('id_ed25519', 'api_token.txt', '.env', 'files/.git/config', '../outside.txt',
                '../../outside.txt', 'C:/Windows/win.ini', '/etc/passwd'):
        assert 'error' in web(cm, LOCAL, native_action='file', uid=uid, rel=rel)['json'], rel

    r = cm.access({'category': 'config', 'command': 'set', 'arg1': 'cserver',
                   'meta': {'browse_files': 'yes'}, 'con': False})
    assert r['return'] == 0, r
    assert web(cm, native_action='file', uid=uid, rel='files/data.csv')['json']['text'] == 'a,b'


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


def test_words_find_the_text_of_the_desc_but_not_its_links(cm):
    a, pa = make(cm, 'zoo-plan')
    b, pb = make(cm, 'zoo-links')
    describe(pa, {'notes': 'The Unicorn enclosure needs a Fence', 'owner': {'team': 'keepers'}})
    describe(pb, {'connections': ['log::zoo-plan,%s' % a], 'summary': 'links only'})

    out = search(cm, q='unicorn', cats='log')
    assert aliases(out) == ['zoo-plan'] and out['descs']['searched'] and out['descs']['asked']
    assert out['rows'][0]['snippet'] == '_desc.notes: The Unicorn enclosure needs a Fence'
    assert aliases(search(cm, q='"unicorn enclosure" fence', cats='log')) == ['zoo-plan']
    assert aliases(search(cm, q='zoo -unicorn', cats='log')) == ['zoo-links']
    assert aliases(search(cm, q='zoo-plan', cats='log')) == ['zoo-plan']       # words skip the link lists
    assert aliases(search(cm, q='_desc:zoo-plan', cats='log')) == ['zoo-links']  # _desc: reads them
    assert aliases(search(cm, q='_desc.owner.team:keep', cats='log')) == ['zoo-plan']
    assert aliases(search(cm, q='_desc.owner:keep*', cats='log')) == ['zoo-plan']  # a pattern: a whole value
    assert search(cm, q='_desc.notes:keepers', cats='log')['total'] == 0
    assert aliases(search(cm, q='zoo -_desc:unicorn', cats='log')) == ['zoo-links']
    assert sorted(aliases(search(cm, q='has:_desc', cats='log'))) == ['zoo-links', 'zoo-plan']
    assert aliases(search(cm, q='has:_desc.connections', cats='log')) == ['zoo-links']
    assert sorted(aliases(search(cm, q='-has:_desc', cats='log'))) == ['gpu-costs', 'plain', 'sla-notes',
                                                                       'sla-report']
    assert search(cm, cats='log')['descs'] == {'asked': False, 'searched': False, 'count': 0}   # no words: no wait


def test_the_desc_files_are_kept_in_the_cache_artifact(cm, tmp_path):
    uid, path = make(cm, 'cached-one')
    describe(path, {'notes': 'a zebra crossing'})
    assert aliases(search(cm, q='zebra', cats='log')) == ['cached-one']
    r = cm.access({'category': 'cache', 'command': 'find', 'arg1': 'cserver--browse', 'con': False})
    assert r['return'] == 0 and len(r['artifacts']) == 1, r
    assert r['artifacts'][0]['cmeta']['generator']['method'] == 'script'     # made by the page, not by a person
    cache_dir = r['artifacts'][0]['path']
    assert os.path.isfile(os.path.join(cache_dir, 'desc_index.pickle'))

    cm2 = CMeta(home=str(tmp_path))                  # another server process: the _desc files come from the cache
    assert aliases(search(cm2, q='zebra', cats='log')) == ['cached-one']
    idx = web(cm2, native_action='index')['json']
    assert idx['ready'] and idx['reread'] == 0 and idx['cache']['artifact'] == 'cache::cserver--browse'

    describe(path, {'notes': 'a giraffe crossing now'})    # an edit is read again, nothing else is
    web(cm2, native_action='reload')
    assert aliases(search(cm2, q='giraffe', cats='log')) == ['cached-one']
    assert web(cm2, native_action='index')['json']['reread'] == 1

    r = cm.access({'category': 'cache', 'command': 'rm', 'arg1': 'cserver--browse', 'force': True, 'con': False})
    assert r['return'] == 0 and not os.path.isdir(cache_dir), r
    cm3 = CMeta(home=str(tmp_path))                  # removed: the next process reads everything and makes it again
    assert aliases(search(cm3, q='giraffe', cats='log')) == ['cached-one']
    assert os.path.isfile(os.path.join(cache_dir, 'desc_index.pickle'))


def test_open_a_folder_only_from_this_machine_and_from_a_page_of_this_server(cm):
    uid, path = make(cm, 'to-open')
    assert 'error' in web(cm, native_action='open', uid=uid, dry='1')['json']      # a browser elsewhere
    assert 'did not come from a page of this server' in \
        web(cm, LOCAL, native_action='open', uid=uid, dry='1')['json']['error']   # another site's page
    for what in ('folder', 'shell'):
        out = web(cm, BOTH, native_action='open', uid=uid, what=what, dry='1')['json']
        if 'error' in out:                           # a Linux server with no desktop, or no terminal
            assert sys.platform.startswith('linux') and ('desktop' in out['error'] or 'found' in out['error'])
        else:
            assert out['path'] == os.path.realpath(path) and out['dry'] and out['opened'] == what and out['cmd']
    assert 'error' in web(cm, BOTH, native_action='open', uid=uid, what='rm -rf', dry='1')['json']
    assert 'error' in web(cm, BOTH, native_action='open', uid='0123456789abcdef', dry='1')['json']

    assert sorted(page_config(web(cm, BOTH))['open']) == ['far', 'folder', 'shell']
    assert page_config(web(cm))['open'] == {}
    r = cm.access({'category': 'config', 'command': 'set', 'arg1': 'cserver', 'meta': {'browse_open': 'no'},
                   'con': False})
    assert r['return'] == 0, r
    assert page_config(web(cm, BOTH))['open'] == {}
    assert 'error' in web(cm, BOTH, native_action='open', uid=uid, dry='1')['json']


def test_a_bare_page_opens_with_the_presets_of_the_server(cm):
    r = cm.access({'category': 'config', 'command': 'set', 'arg1': 'cserver', 'con': False, 'meta': {
        'browse_title': 'Acme <knowledge>', 'browse_default_query': 'tag:sla', 'browse_default_repos': 'local',
        'browse_default_cats': ['log', 'note'], 'browse_default_view': 'graph'}})
    assert r['return'] == 0, r
    r = web(cm)
    assert r['html_meta']['page_title'] == 'Acme <knowledge>'
    assert '<h1>Acme &lt;knowledge&gt;</h1>' in r['html_meta']['html']
    s = page_config(r)['state']
    assert (s['q'], s['repos'], s['cats'], s['view']) == ('tag:sla', 'local', 'log,note', 'graph')
    s = page_config(web(cm, q='gpu'))['state']                 # a URL with a query keeps its own state
    assert (s['q'], s['repos'], s['cats'], s['view']) == ('gpu', '', '', '')
