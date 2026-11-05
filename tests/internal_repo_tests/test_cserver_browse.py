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
import yaml

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
    # its footer says "Powered by cMeta v<version>" (and hides the same line of the engine's cserver, 2026-11-03)
    assert 'Powered by <a href="https://cTuning.ai/project/cmeta"' in html and '>cMeta v' + cm.__version__ + '</a>' in html


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
    # the other spellings of a reference (2026-11-03): a pattern, the UID after ::, a cName, a {{{cRef}}} with a path
    uid = search(cm, q='log::gpu-costs')['rows'][0]['uid']
    assert aliases(search(cm, q='log::gpu*')) == ['gpu-costs']
    assert aliases(search(cm, q='log::gpu-costs,' + uid)) == ['gpu-costs']
    assert aliases(search(cm, q='gpu-costs,' + uid)) == ['gpu-costs']
    assert search(cm, q='sla-report,' + uid)['total'] == 0               # a cName: the alias and the UID must both hold
    assert aliases(search(cm, q='{{{log::gpu-costs}}}')) == ['gpu-costs']
    assert aliases(search(cm, q='{{{log::gpu-costs}}}/README.md')) == ['gpu-costs']


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


def test_editing_from_the_page(cm):
    """A text file, a _cmeta and a _desc saved from the page (2026-11-03): who may, the fingerprint, the checks."""
    uid, path = make(cm, 'editable', tags=['one'])
    with open(os.path.join(path, 'README.md'), 'wb') as f:
        f.write(b'# hello\r\nline\r\n')

    def save(misc, rel, text, stamp):
        return web(cm, misc, native_action='save', uid=uid, rel=rel, text=text, stamp=stamp)['json']

    def dump(rel, data):
        return json.dumps(data, indent=1) if rel.endswith('.json') else yaml.safe_dump(data, sort_keys=False)

    # a browser elsewhere may not save; a page of another site neither; the local page may
    assert 'error' in save(None, 'README.md', 'x', '')
    assert 'page of this server' in save(LOCAL, 'README.md', 'x', '')['error']
    j = web(cm, BOTH, native_action='file', uid=uid, rel='README.md')['json']
    assert j['editable'] and j['stamp']
    assert 'changed since' in save(BOTH, 'README.md', '# hi\n', 'stale')['error']
    out = save(BOTH, 'README.md', '# hi\nmore\n', j['stamp'])
    assert out['saved'] == 'README.md' and out['stamp'] != j['stamp'] and not out['warnings'], out
    with open(os.path.join(path, 'README.md'), 'rb') as f:
        assert f.read() == b'# hi\r\nmore\r\n'                       # the file's own line endings kept
    readme_stamp = out['stamp']

    # the meta: a new tag is in the index at once; the identity stays; the text must parse
    files = web(cm, BOTH, native_action='files', uid=uid)['json']
    assert files['edit'] and files['can_add'] == ['_desc.yaml']       # README.md exists, no _desc yet
    meta_rel = [f['rel'] for f in files['files'] if f['rel'].lower().startswith('_cmeta.')][0]
    j = web(cm, BOTH, native_action='file', uid=uid, rel=meta_rel)['json']
    meta = json.loads(j['text']) if meta_rel.endswith('.json') else yaml.safe_load(j['text'])
    changed = dict(meta, tags=['two'])
    out = save(BOTH, meta_rel, dump(meta_rel, changed), j['stamp'])
    assert out['saved'] == meta_rel and out['reindexed'] and not out['warnings'], out
    assert aliases(search(cm, q='tag:two')) == ['editable'] and search(cm, q='tag:one')['total'] == 0
    stamp = out['stamp']
    for bad, why in ((dict(changed, artifact='ffffffffffffffff'), 'UID'), (dict(changed, category='other'), 'category'),
                     (dict(changed, tags='two'), 'tags')):
        assert why in save(BOTH, meta_rel, dump(meta_rel, bad), stamp)['error'], why
    assert 'not valid' in save(BOTH, meta_rel, '{ or: [', stamp)['error']

    # a _desc.yaml made from the page: its connection shows in the detail; a second one is refused; bad YAML says the line
    out = save(BOTH, '_desc.yaml', 'connections:\n  - log::sla-report\n', '')
    assert out['created'] and not out['warnings'], out
    d = web(cm, BOTH, native_action='artifact', uid=uid)['json']
    assert [x['alias'] for x in d['connections']] == ['sla-report'] and d['connections'][0]['found']
    assert d['edit'] and d['meta_file'] == meta_rel and d['desc_file'] == '_desc.yaml'   # the edit buttons of the detail
    assert web(cm, native_action='artifact', uid=uid)['json']['edit'] is False             # not for a browser elsewhere
    assert 'already' in save(BOTH, '_desc.yaml', 'x: 1\n', '')['error']
    err = save(BOTH, '_desc.yaml', 'a: 1\nb: [\n', out['stamp'])['error']
    assert 'not valid YAML' in err and 'at line' in err, err              # the parser names the line
    out = save(BOTH, '_desc.yaml', 'connections:\n  - log::no-such-one\n', out['stamp'])
    assert out['warnings'] and 'no-such-one' in out['warnings'][0]

    # never a key-like file, a dot-file, a path outside, a binary name, a second _cmeta
    for rel in ('id_ed25519', '.env', '../x.txt', 'data.bin', 'files/.git/x.txt', '_cmeta.yaml', '_cmeta.json'):
        assert 'error' in save(BOTH, rel, 'x', ''), rel

    # new files with a text name anywhere inside (the folders on the way), a folder, a deletion with its guards
    def act(action, rel, misc=BOTH):
        return web(cm, misc, native_action=action, uid=uid, rel=rel)['json']
    assert save(BOTH, 'notes/plan.md', '# plan\n', '')['created'] and os.path.isfile(os.path.join(path, 'notes', 'plan.md'))
    assert save(BOTH, 'LICENSE', 'text without an extension\n', '')['created']
    assert act('mkdir', 'data')['made'] == 'data' and os.path.isdir(os.path.join(path, 'data'))
    assert 'exists already' in act('mkdir', 'data')['error']
    assert 'error' in act('mkdir', 'data', LOCAL) and 'error' in act('mkdir', '.hidden') and 'error' in act('mkdir', 'secrets')
    listing = web(cm, BOTH, native_action='files', uid=uid)['json']
    assert 'data' in listing['dirs'] and 'notes' in listing['dirs'] and 'notes/plan.md' in [f['rel'] for f in listing['files']]
    assert save(BOTH, 'data/a.txt', 'a\n', '')['created']
    assert 'not empty' in act('delete', 'data')['error']
    assert act('delete', 'data/a.txt') == {'deleted': 'data/a.txt', 'kind': 'file'}
    assert act('delete', 'data') == {'deleted': 'data', 'kind': 'folder'} and not os.path.exists(os.path.join(path, 'data'))
    for rel in (meta_rel, '_desc.yaml'):
        assert 'not deleted here' in act('delete', rel)['error'], rel
    assert 'error' in act('delete', 'LICENSE', LOCAL)                    # a page of another site
    assert 'no such' in act('delete', 'nope.txt')['error']
    assert 'error' in act('delete', 'id_ed25519')                        # a name the page never shows
    assert act('delete', 'LICENSE')['kind'] == 'file' and act('delete', 'notes/plan.md')['kind'] == 'file'
    assert act('delete', 'notes')['kind'] == 'folder'

    # browse_edit: no turns it off for the local browser too
    r = cm.access({'category': 'config', 'command': 'set', 'arg1': 'cserver', 'meta': {'browse_edit': 'no'}, 'con': False})
    assert r['return'] == 0, r
    assert 'off here' in save(BOTH, 'README.md', 'x\n', readme_stamp)['error']
    r = cm.access({'category': 'config', 'command': 'set', 'arg1': 'cserver', 'meta': {'browse_edit': ''}, 'con': False})
    assert r['return'] == 0, r

    # a signed-in reader elsewhere writes only in the repositories of the grant the host passes - or anywhere as an admin
    def grant(repos):
        return {'same_origin': True, 'browse_edit': repos}
    assert 'may not write' in save(grant(['other*']), 'README.md', 'y\n', readme_stamp)['error']
    out = save(grant(['loc*']), 'README.md', 'y\n', readme_stamp)
    assert out['saved'] == 'README.md', out
    assert save(grant(True), 'README.md', 'z\n', out['stamp'])['saved'] == 'README.md'
    assert 'error' in save({'same_origin': True}, 'README.md', 'w\n', '')      # no grant, not local: refused


def test_creating_from_the_page(cm):
    """A new artifact from the page (2026-11-03): who may, the checks, the category's own naming, the index."""
    def create(misc, **q):
        return web(cm, misc, native_action='create', **q)['json']

    assert 'error' in create(None, cat='log', repo='local', alias='made-here')             # a browser elsewhere
    assert 'page of this server' in create(LOCAL, cat='log', repo='local', alias='made-here')['error']
    for bad in ('', 'a/b', 'a:b', '.hidden', 'x,y'):
        assert 'error' in create(BOTH, cat='log', repo='local', alias=bad), bad
    assert 'no category' in create(BOTH, cat='no-such-category', repo='local', alias='x')['error']
    assert 'error' in create(BOTH, cat='log', repo='no-such-repo', alias='x')
    assert page_config(web(cm, BOTH))['edit'] is True and page_config(web(cm))['edit'] is False

    out = create(BOTH, cat='log', repo='local', alias='made-here', tags='one, two')
    assert out['created'] == 'made-here' and out['cat'] == 'log' and out['repo'] == 'local' and len(out['uid']) == 16, out
    assert out['cref'] == 'log,%s::made-here,%s' % (out['cat_uid'], out['uid'])
    assert aliases(search(cm, q='tag:two')) == ['made-here']                       # in the index at once
    assert 'error' in create(BOTH, cat='log', repo='local', alias='made-here')       # not twice
    assert web(cm, BOTH, native_action='artifact', uid=out['uid'])['json']['can_create'] is True

    # a dated category (dated_aliases: true): the day in front only when asked (dt - the form's tick, on by default
    # for such a category); without it the name is kept and the answer carries the engine's warning (2026-11-05)
    out = create(BOTH, cat='work', repo='local', alias='my task')
    assert out['created'] == 'my task' and len(out['warnings']) == 1 and 'cMeta warning' in out['warnings'][0], out
    out = create(BOTH, cat='work', repo='local', alias='my task', dt=1)
    assert out['created'].endswith('.my task') and out['created'][:8].isdigit() and out['warnings'] == [], out
    out = create(BOTH, cat='log', repo='local', alias='dated log', dt=1)             # any category
    assert out['created'][:8].isdigit() and out['created'].endswith('.dated log') and out['warnings'] == [], out
    cats = {c['alias']: c for c in web(cm, BOTH, native_action='options')['json']['categories']}
    assert cats['work']['dated'] is True and cats['log']['dated'] is False               # what ticks the form's box

    # a signed-in reader writes only in the repositories of the grant; browse_edit: no turns it off for everyone
    assert 'may not write' in create({'same_origin': True, 'browse_edit': ['other*']}, cat='log', repo='local', alias='x')['error']
    assert create({'same_origin': True, 'browse_edit': ['loc*']}, cat='log', repo='local', alias='granted')['created'] == 'granted'
    r = cm.access({'category': 'config', 'command': 'set', 'arg1': 'cserver', 'meta': {'browse_edit': 'no'}, 'con': False})
    assert r['return'] == 0, r
    assert 'off here' in create(BOTH, cat='log', repo='local', alias='y')['error']
    assert web(cm, BOTH, native_action='artifact', uid=out['uid'])['json']['can_create'] is False


def test_a_new_artifact_shows_without_a_restart(cm):
    assert search(cm, q='brand-new')['total'] == 0
    make(cm, 'brand-new')
    assert aliases(search(cm, q='brand-new')) == ['brand-new']


def test_secret_categories_are_hidden_unless_the_config_says_none(cm):
    r = cm.access({'category': 'category', 'command': 'add', 'arg1': 'local:my.crypt', 'con': False})
    assert r['return'] == 0, r
    make(cm, 'a-key-bundle', category='my.crypt')
    out = search(cm, q='a-key-bundle')
    assert out['total'] == 0
    # the result says that this server hides some categories, without naming them (2026-11-03) ...
    assert len(out['notices']) == 1 and 'hides the categories of keys and secrets' in out['notices'][0]
    assert 'my.crypt' not in out['notices'][0]
    # ... and names the one the query itself names
    for q in ('cat:my.crypt a-key-bundle', 'my.crypt::a-key-bundle', 'my.cr*::*'):
        out = search(cm, q=q)
        assert out['total'] == 0 and out['notices'] == ['my.crypt: a category this server hides (browse_hide_categories) - '
                                                         'its artifacts are not listed and their files never shown.'], q
    assert 'notices' not in search(cm, q='sla', cats='log')           # a result with rows gets no general word

    r = cm.access({'category': 'config', 'command': 'set', 'arg1': 'cserver',
                   'meta': {'browse_hide_categories': 'none'}, 'con': False})
    assert r['return'] == 0, r
    out = search(cm, q='a-key-bundle')
    assert aliases(out) == ['a-key-bundle'] and 'notices' not in out
    assert 'notices' not in search(cm, q='no-such-artifact')         # nothing hidden: nothing to say


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


def test_catalog_on_an_engine_core_without_scope(cm, monkeypatch):
    """A server started before an engine upgrade keeps the Repos it loaded while its pages reload: an older
    find_in_index has no `scope` - the catalog still builds (the lookup without it) and the answer says the engine
    is stale, so the page can ask for a restart (2026-10-27: TypeError on /browse of a cserver started the night
    before the upgrade)."""
    import cmeta.repos
    original = cmeta.repos.Repos.find_in_index

    def older(self, *args, **kwargs):
        if 'scope' in kwargs:
            raise TypeError("Repos.find_in_index() got an unexpected keyword argument 'scope'")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(cmeta.repos.Repos, 'find_in_index', older)
    out = web(cm, native_action='search', q='sla')['json']
    assert out['total'] >= 2 and out['catalog']['stale_engine'] is True
    assert any(r['alias'] == 'sla-report' for r in out['rows'])
    monkeypatch.undo()
    # the next build on the real core is clean again (the stamp changes with the index)
    make(cm, 'sla-extra', tags=['sla'], created='2026-10-02T10:00:00+00:00')
    out = web(cm, native_action='search', q='sla')['json']
    assert out['catalog']['stale_engine'] is False and out['total'] >= 3


def test_an_artifact_is_named_by_its_cref_never_by_a_bare_uid(cm):
    """An artifact's UID is unique only with its category's: the pages name an artifact in their addresses as
    cref=<category UID>::<artifact UID> (and focus= the same), never ?uid= (the user's rule, 2026-10-30); the ?uid=
    and focus=<UID> of older links still open."""
    uid, path = make(cm, 'cref-a')
    with open(os.path.join(path, 'notes.md'), 'w', encoding='utf-8') as f:
        f.write('# notes\n')
    connect(path, 'log::sla-notes')
    web(cm, native_action='reload')
    cat_uid = web(cm, native_action='artifact', uid=uid)['json']['row']['cat_uid'].lower()
    node = '%s::%s' % (cat_uid, uid)
    other = '0123456789abcdef'

    def resolve(cref):
        out = web(cm, native_action='resolve', cref=cref)['json']
        return out['uid'], out['rel']

    # the two UIDs alone, with a path, the long forms; a category UID that is not the artifact's names nothing
    assert resolve(node) == (uid, '')
    assert resolve(node + '/notes.md') == (uid, 'notes.md')
    assert resolve('log,%s::cref-a,%s' % (cat_uid, uid)) == (uid, '')
    assert resolve('log::cref-a') == (uid, '')
    assert resolve('%s::%s' % (other, uid))[0] == ''
    assert resolve('log,%s::cref-a,%s' % (other, uid))[0] == ''

    # the page opens what its address names: the cRef and a file beside it, or an older link's UID
    s = page_config(web(cm, cref=node, file='notes.md'))['state']
    assert (s['uid'], s['file']) == (uid, 'notes.md')
    assert page_config(web(cm, cref=node + '/notes.md'))['state']['file'] == 'notes.md'
    assert page_config(web(cm, uid=uid))['state']['uid'] == uid

    # the graph: a focus by cRef, a node that carries its category's UID (what the page focuses with)
    g = graph(cm, focus=node, depth='1')
    assert g['focus']['uid'] == uid and 'sla-notes' in arts(g)
    assert all(n['cat_uid'] == cat_uid for n in g['nodes'] if n['kind'] == 'artifact')
    assert graph(cm, focus='%s::%s' % (other, uid))['focus'] is None
    assert graph(cm, focus=uid)['focus']['uid'] == uid

    # the page of the artifact links to the browser and the graph by the same cRef
    r = cm.access({'category': 'cserver.cref', 'command': 'web', 'con': False, 'urls': dict(URLS),
                   'query': {'cref': 'log::cref-a,' + uid}, 'misc': {}})
    assert r['return'] == 0, r
    html = r['html_meta']['html']
    assert 'browse?cref=%s"' % node in html and 'focus=%s"' % node in html
    assert 'uid=' + uid not in html and 'focus=' + uid not in html


def test_the_pickers_tick_all_but_what_they_leave_out(cm):
    """What a picker holds (2026-11-03): names (none or "*" = all), "-name" left out, "-*" none at all."""
    assert search(cm, cats='log', repos='*')['total'] == 4
    assert search(cm, cats='log', repos='local')['total'] == 4
    assert search(cm, cats='log', repos='-local')['total'] == 0
    assert search(cm, cats='log', repos='-other')['total'] == 4
    assert search(cm, cats='log', repos='-*')['total'] == 0
    assert all(r['cat'] != 'log' for r in search(cm, q='sla', cats='-log')['rows'])
    assert arts(graph(cm, cats='log', repos='-local')) == []


def set_config(cm, **meta):
    r = cm.access({'category': 'config', 'command': 'set', 'arg1': 'cserver', 'con': False, 'meta': meta})
    assert r['return'] == 0, r


def test_unticked_repositories_apply_whenever_the_address_names_none(cm):
    set_config(cm, browse_untick_repos='fgg-arc,old-*')
    for query in ({}, {'cats': 'log', 'sort': 'created'}, {'view': 'graph'}):
        c = page_config(web(cm, **query))
        assert c['state']['repos'] == '-fgg-arc,-old-*' and c['untick'] == {'repos': ['fgg-arc', 'old-*']}, query
    assert page_config(web(cm, repos='*'))['state']['repos'] == '*'                # the address asks for all
    assert page_config(web(cm, repos='local'))['state']['repos'] == 'local'
    # a bare page with the server's own repositories: those, then the ones left out
    set_config(cm, browse_default_repos='local')
    assert page_config(web(cm))['state']['repos'] == 'local,-fgg-arc,-old-*'


def test_a_category_declares_its_order_and_the_server_may_change_it(cm):
    r = cm.access({'category': 'category', 'command': 'add', 'arg1': 'local:my.items', 'con': False,
                   'meta': {'browse_sort': 'created,updated'}})
    assert r['return'] == 0, r
    for alias, created in (('b-mid', '2026-05-01T10:00:00+00:00'), ('a-new', '2026-10-01T10:00:00+00:00'),
                           ('c-old', '2025-01-01T10:00:00+00:00')):
        make(cm, alias, created=created, category='my.items')
    out = search(cm, cats='my.items')
    assert aliases(out) == ['a-new', 'b-mid', 'c-old'] and out['sort'] == 'created' and out['sort_keys'] == ['created', 'updated']
    assert aliases(search(cm, cats='my.items', sort='alias', dir='asc')) == ['a-new', 'b-mid', 'c-old']
    assert aliases(search(cm, cats='my.items', sort='created', dir='asc')) == ['c-old', 'b-mid', 'a-new']
    assert search(cm, cats='log')['sort'] == 'alias'                              # a category without one: by name
    assert search(cm, cats='my.items,log')['sort'] == 'alias'                     # two that differ: the default
    set_config(cm, browse_category_sort='my.items: alias; fgg.task, work: created,updated')
    out = search(cm, cats='my.items')
    assert out['sort'] == 'alias' and aliases(out) == ['a-new', 'b-mid', 'c-old']
    # dated names (work items: 20261103.something): "-alias" lists them from the end, the latest date first
    r = cm.access({'category': 'category', 'command': 'add', 'arg1': 'local:my.dated', 'con': False,
                   'meta': {'browse_sort': '-alias'}})
    assert r['return'] == 0, r
    for alias in ('20261020.b', '20261103.a', '20250101.c'):
        make(cm, alias, category='my.dated')
    out = search(cm, cats='my.dated')
    assert aliases(out) == ['20261103.a', '20261020.b', '20250101.c'] and (out['sort'], out['dir']) == ('alias', 'desc')
    assert aliases(search(cm, cats='my.dated', sort='alias', dir='asc')) == ['20250101.c', '20261020.b', '20261103.a']


def test_dated_order_lists_the_routines_first_then_the_newest(cm):
    """sort=dated (2026-11-04): the names without a date first, A to Z, then the dated ones newest first; dir=desc
    gives the same list from its end; a category may declare it as its own order. A date is what the engine's
    rule reads (names.date_in_alias, 2026-11-05): the unknown part written with x, a range by its first date."""
    for alias in ('Answer Emails', 'Update links', '20010101.change-word', '20261007.qr-codes', '2017xxxx.fp_p',
                  '202604xx.tax', '2020-2022.old photos', '2026beta.not a date'):
        make(cm, alias, category='log')
    names = ['2026beta.not a date', 'Answer Emails', 'Update links', '20261007.qr-codes', '202604xx.tax',
             '2020-2022.old photos', '2017xxxx.fp_p', '20010101.change-word']
    out = search(cm, cats='log', sort='dated', limit=50)
    got = [a for a in aliases(out) if a in names]
    assert got == names, got
    assert out['sort'] == 'dated' and out['dir'] == 'asc'
    got = [a for a in aliases(search(cm, cats='log', sort='dated', dir='desc', limit=50)) if a in names]
    assert got == list(reversed(names)), got


def test_category_sorts_of_the_config():
    import importlib.util
    import cmeta as cmeta_module
    spec = importlib.util.spec_from_file_location('browse_v1_sorts', os.path.join(
        os.path.dirname(os.path.abspath(cmeta_module.__file__)), 'internal-repo', 'category', 'cserver.browse', 'api', 'v1.py'))
    v1 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v1)
    assert v1._category_sorts('work,note,fgg.task: created,updated; log: alias') == {
        'work': ['created', 'updated'], 'note': ['created', 'updated'], 'fgg.task': ['created', 'updated'], 'log': ['alias']}
    # set from the command line, a dotted category comes as nested dicts
    assert v1._category_sorts({'work': 'created', 'fgg': {'task': 'created,updated'}, 'x': 'nonsense'}) == {
        'work': ['created'], 'fgg.task': ['created', 'updated']}
    assert v1._picked('fgg-arc', 'u1', ['-fgg-arc']) is False and v1._picked('local', 'u2', ['-fgg-arc']) is True
    assert v1._picked('local', 'u2', ['-*']) is False and v1._picked('local', 'u2', ['*']) is True


def live_browse():
    """The cserver.browse module as this process runs it (its catalog and connection index are per process)."""
    for m in list(sys.modules.values()):
        f = str(getattr(m, '__file__', '') or '').replace(os.sep, '/')
        if f.endswith('cserver.browse/api/v1.py'):
            return m
    raise AssertionError('cserver.browse is not loaded')


def index_status(cm):
    return web(cm, native_action='index')['json']


def wait_index(cm, seconds=30):
    """The background build of the connection index over (it goes on with every file after a partial one)."""
    import time
    for _ in range(int(seconds * 20)):
        st = index_status(cm)
        if st['ready'] and not st['building']:
            return st
        time.sleep(0.05)
    raise AssertionError('the connection index is still building: %s' % st)


def test_an_index_change_reads_only_the_categories_that_changed(cm):
    """2026-11-04: a worker process read the whole index again after any change of it (a priority set, an artifact
    moved, any cx write): now only the categories whose index file changed - the others keep their items."""
    r = cm.access({'category': 'category', 'command': 'add', 'arg1': 'local:other', 'con': False})
    assert r['return'] == 0, r
    make(cm, 'an-other', category='other')
    search(cm, q='sla', cats='log')                  # a first search with words makes the cache artifact (an index change)
    web(cm, native_action='reload')
    out = search(cm, cats='log')
    assert out['catalog']['reread'] == -1            # a reload reads everything
    v1 = live_browse()
    log_items = v1._catalog['by_cat']['log']
    other_items = v1._catalog['by_cat']['other']

    make(cm, 'second-other', category='other')
    out = search(cm, cats='log')
    assert out['catalog']['reread'] == 1              # other alone
    assert v1._catalog['by_cat']['log'] is log_items  # the same list, not read again
    assert v1._catalog['by_cat']['other'] is not other_items
    assert sorted(aliases(search(cm, cats='other'))) == ['an-other', 'second-other']
    assert out['total'] == 4                          # log as it was

    make(cm, 'fifth', category='log')
    out = search(cm, cats='log')
    assert out['catalog']['reread'] == 1 and out['total'] == 5
    assert v1._catalog['by_cat']['other'] is not other_items and v1._catalog['by_cat']['log'] is not log_items

    # a reload reads everything again
    web(cm, native_action='reload')
    assert search(cm, cats='log')['catalog']['reread'] == -1


def test_after_an_index_change_a_word_search_looks_only_at_the_changed_categories_first(cm, monkeypatch):
    """The _desc files of the categories read again are looked at before the answer; the rest are trusted as of
    the last build, then every file is looked at in the background - so a _desc edited elsewhere is found as
    before, a moment later. A reference an old _desc makes to an artifact that appears only now resolves at once."""
    r = cm.access({'category': 'category', 'command': 'add', 'arg1': 'local:other', 'con': False})
    assert r['return'] == 0, r
    a, pa = make(cm, 'zoo-plan')
    describe(pa, {'notes': 'a unicorn enclosure', 'connections': ['other::late-comer']})
    assert aliases(search(cm, q='unicorn')) == ['zoo-plan']
    st = wait_index(cm)
    assert st['trusted'] == 0

    # every build from now on: how many files it trusted (None: it looked at every one)
    v1 = live_browse()
    builds = []
    compute = v1._conn_compute

    def counting(items, by_uid, by_key, trusted=None):
        builds.append(None if trusted is None else len(trusted))
        return compute(items, by_uid, by_key, trusted)

    monkeypatch.setattr(v1, '_conn_compute', counting)

    # a new artifact in another category: its text is found at once, the log files were trusted; then the
    # build goes on with every file in the background
    b, pb = make(cm, 'late-comer', category='other')
    describe(pb, {'notes': 'a late giraffe'})
    assert aliases(search(cm, q='giraffe')) == ['late-comer']
    wait_index(cm)
    assert builds[0] >= 5 and builds[-1] is None, builds          # the four of the fixture + zoo-plan trusted
    # the old _desc's reference to it resolved
    d = web(cm, native_action='artifact', uid=a)['json']
    assert any(c.get('uid') == b for c in d.get('connections', [])), d.get('connections')

    # an edit elsewhere, then an index change in the other category: found once the background pass is over
    describe(pa, {'notes': 'a unicorn enclosure with a Fence', 'connections': ['other::late-comer']})
    make(cm, 'third', category='other')
    search(cm, q='fence')                             # the answer may come before the edit is seen
    wait_index(cm)
    assert aliases(search(cm, q='fence')) == ['zoo-plan']
    assert index_status(cm)['trusted'] == 0           # the last build looked at every file
