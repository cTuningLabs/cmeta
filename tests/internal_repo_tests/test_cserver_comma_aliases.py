"""
Licensed under the Apache License, Version 2.0.
See the COPYRIGHT and LICENSE files in the project root for details.

The pages of the engine with an alias that holds commas and spaces (the user, 2026-11-23: "Kim Doe, joined Example Co,
20260922"): /browse reads every cRef by the engine's rule - the part after the LAST comma is the UID only when it is one -
in its search, connections, graph, the page of an artifact (/cref), the _cmeta check and its pickers (browse.js); its
create and rename take commas and refuse only a UID after the last one; /cref, /cmeta.configs and /projects read
category, config, repository and button names the same way. Each integration test runs in a fresh <CMETA_HOME>.
"""

import importlib.util
import json
import os
import shutil
import subprocess

import pytest

from cmeta import CMeta

KIM = 'Kim Doe, joined Example Co, 20260922'
UID = '5ca1ab1e5ca1ab1e'
CAT = '487a7639093a4685'
LIKE_UID = '0123456789abcdef'

URLS = {'url': 'http://127.0.0.1:8004/browse?', 'url_files': 'http://127.0.0.1:8004/browse/',
        'url_server': 'http://127.0.0.1:8004/'}
LOCAL = {'client_local': True}
BOTH = {'client_local': True, 'same_origin': True}


def page(cat):
    """The api/v1.py of a page of the engine, loaded by its path (its module-level functions)."""
    import cmeta as cmeta_module
    path = os.path.join(os.path.dirname(os.path.abspath(cmeta_module.__file__)), 'internal-repo', 'category', cat, 'api', 'v1.py')
    spec = importlib.util.spec_from_file_location('comma_' + cat.replace('.', '_'), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def cm(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    return CMeta(home=str(tmp_path))


def make(cm, alias, tags=None):
    r = cm.access({'category': 'log', 'command': 'create', 'arg1': 'local:' + alias, 'meta': {'tags': tags or []},
                   'con': False})
    assert r['return'] == 0, r
    return r['meta']['artifact'], r['path']


def web(cm, misc=None, **query):
    r = cm.access({'category': 'cserver.browse', 'command': 'web', 'con': False,
                   'urls': dict(URLS), 'query': query, 'misc': dict(misc or {})})
    assert r['return'] == 0, r
    return r


def search(cm, **query):
    out = web(cm, native_action='search', **query)['json']
    assert 'error' not in out, out
    return {r['alias'] for r in out['rows']}


def connect(path, *crefs):
    with open(os.path.join(path, '_desc.json'), 'w', encoding='utf-8') as f:
        json.dump({'connections': list(crefs)}, f)


def found(cm, name):
    r = cm.access({'category': 'log', 'command': 'find', 'arg1': name, 'con': False})
    return set() if r['return'] == 16 else {(a['cmeta_ref_parts'].get('artifact_alias'), a['cmeta_ref_parts']['artifact_uid'])
                                            for a in r['artifacts']}


@pytest.mark.parametrize('cref, expected', [
    # the forms of before
    ('log,%s::gpu-costs,%s' % (CAT, UID), ('log', CAT, 'gpu-costs', UID)),
    ('log::gpu-costs', ('log', '', 'gpu-costs', '')),
    ('gpu-costs,' + UID, ('', '', 'gpu-costs', UID)),
    (UID, ('', '', '', UID)),
    ('', ('', '', '', '')),

    # an alias with commas, with and without its UID; UIDs in capitals
    ('log,%s::%s,%s' % (CAT, KIM, UID), ('log', CAT, KIM, UID)),
    ('log::' + KIM, ('log', '', KIM, '')),
    ('LOG,%s::%s , %s' % (CAT.upper(), KIM, UID.upper()), ('LOG', CAT, KIM, UID)),
    (KIM, ('', '', KIM, '')),
    ('my, category::a, b', ('my, category', '', 'a, b', '')),

    # the two UIDs alone (what the pages write in their own addresses)
    ('%s::%s' % (CAT, UID), ('', CAT, '', UID)),
])
def test_parse_cref(cref, expected):
    assert page('cserver.browse')._parse_cref(cref) == expected


def test_parse_query_reads_crefs_with_commas_spaces_and_quotes():
    pq = page('cserver.browse').parse_query

    q = pq('{{{log::%s,%s}}}/EMails/20261119.Notes.eml' % (KIM, UID))
    assert (q['cats'], q['uids'], q['aliases'], q['words']) == (['log'], [UID], [], [])
    q = pq('{{{log::%s}}}' % KIM)
    assert (q['cats'], q['uids'], q['aliases'], q['words']) == (['log'], [], [KIM.lower()], [])
    q = pq('log::"%s" tag:example' % KIM)
    assert (q['aliases'], q['tags'], q['words']) == ([KIM.lower()], ['example'], [])
    q = pq('log::' + UID.upper())
    assert (q['uids'], q['aliases']) == ([UID], [])
    q = pq('log::a,b')
    assert (q['uids'], q['aliases']) == ([], ['a,b'])

    # the forms of before
    q = pq('log::gpu-costs,' + UID)
    assert (q['cats'], q['uids'], q['aliases']) == (['log'], [UID], [])
    q = pq('gpu-costs,' + UID)
    assert (q['uids'], q['aliases']) == ([UID], ['gpu-costs'])
    q = pq('sla brief -draft')
    assert (q['words'], q['not_words']) == (['sla', 'brief'], ['draft'])


def test_search_tokens_change_only_for_spaces_inside_braces():
    import re
    old = re.compile(r'-?[^\s"]*"[^"]*"|\S+')                      # the tokens of 0.45.2
    new = page('cserver.browse').TOKEN_RE
    for q in ('sla brief -draft', 'tag:x "a phrase" -tag:y', 'owner:"Ada Lovelace" cat:log', '{{{log::gpu-costs}}}/README.md',
              '-{{{log::x}}} word', 'title:"a, b" x', 'x{{{a b}}}', '"{{{a b}}}"', 'tag:{{{x}}}', '{{{unclosed a b',
              'a}}} {{{b', 'log::gpu-costs,' + UID, 'repo:demo cat:demo.person Kim'):
        assert new.findall(q) == old.findall(q), q
    assert new.findall('{{{log::%s}}}/a.md tag:x' % KIM) == ['{{{log::%s}}}/a.md' % KIM, 'tag:x']
    assert new.findall('-{{{log::a b}}} w') == ['-{{{log::a b}}}', 'w']


def test_name_matches_takes_a_uid_only_after_the_last_comma():
    nm = page('cserver.browse')._name_matches
    assert nm('log', CAT, 'log') and nm('log', CAT, 'LOG') and nm('log', CAT, 'log,' + CAT) and nm('log', CAT, CAT)
    assert nm('other', CAT, 'old, name,' + CAT.upper())                # the UID decides
    assert nm('a, b', '', 'a, b') and not nm('b', '', 'a, b')          # the whole alias, not its last part
    assert not nm('log', CAT, 'log, x') and not nm('log', CAT, 'log,' + LIKE_UID)
    assert nm('ctuninglabs@cmeta-aops', '', 'cmeta-aops') and nm('demo-arc', '', 'demo*')


def test_the_pages_follow_an_alias_with_commas(cm):
    kim_uid, kim_path = make(cm, KIM, tags=['example'])
    carol_uid, carol_path = make(cm, 'Carol Roe', tags=['megacorp'])
    ms_uid, _ = make(cm, 'Megacorp, Inc.', tags=['org'])
    connect(carol_path, 'log::' + KIM, 'log::Megacorp, Inc.')               # by the alias alone, commas in it
    web(cm, native_action='reload')
    cat_uid = web(cm, native_action='artifact', uid=kim_uid)['json']['row']['cat_uid'].lower()
    connect(kim_path, 'log,%s::Carol Roe,%s' % (cat_uid, carol_uid))
    web(cm, native_action='reload')

    # the search: a pasted {{{cRef}}} (spaces in it), a quoted alias, the UID after :: (capitals too), a pattern
    with open(os.path.join(kim_path, 'README.md'), 'w', encoding='utf-8') as f:
        f.write('# Kim\n')
    for q in ('{{{log::%s}}}/README.md' % KIM, '{{{log::%s,%s}}}' % (KIM, kim_uid), 'log::"%s"' % KIM,
              'log::' + kim_uid.upper(), 'log::kim*', '{{{log,%s::%s,%s}}}/EMails/a.eml' % (cat_uid, KIM, kim_uid)):
        assert search(cm, q=q) <= {KIM} and KIM in search(cm, q=q), q
    assert search(cm, q='log::Kim') == set() and search(cm, q='log::"Kim Doe"') == set()

    # the detail of an artifact: its connections resolved, both ways
    d = web(cm, LOCAL, native_action='artifact', uid=carol_uid)['json']
    assert {(c['alias'], c['found']) for c in d['connections']} == {(KIM, True), ('Megacorp, Inc.', True)}
    web(cm, native_action='graph', q='log::kim*')                          # waits for the connection index
    d = web(cm, native_action='artifact', uid=kim_uid)['json']
    assert {c['alias'] for c in d['incoming']} == {'Carol Roe'}
    assert {(c['alias'], c['found']) for c in d['connections']} == {('Carol Roe', True)}

    # the graph joins them
    g = web(cm, native_action='graph', cats='log', categories='0')['json']
    names = {n['id']: n['label'] for n in g['nodes']}
    links = {(names[x['s']], names[x['t']]) for x in g['links'] if x['k'] == 'link'}
    assert ('Carol Roe', KIM) in links and ('Carol Roe', 'Megacorp, Inc.') in links, links

    # the page of an artifact (/cref) by every form of its cRef
    for ref in ('log::' + KIM, 'log::%s,%s' % (KIM, kim_uid), '{{{log::%s}}}/README.md' % KIM,
                '%s::%s' % (cat_uid, kim_uid), 'log,%s::%s' % (cat_uid.upper(), KIM)):
        r = cm.access({'category': 'cserver.cref', 'command': 'web', 'con': False, 'urls': dict(URLS),
                       'query': {'cref': ref}, 'misc': dict(BOTH)})
        assert r['return'] == 0, r
        html = r['html_meta']['html']
        assert '<span class="cxr-tt">%s</span>' % KIM in html, ref
    assert ms_uid


def test_the_cmeta_check_reads_alias_uid_with_commas(cm):
    uid, path = make(cm, KIM)
    web(cm, native_action='reload')
    meta_rel = [f['rel'] for f in web(cm, BOTH, native_action='files', uid=uid)['json']['files']
                if f['rel'].lower().startswith('_cmeta.')][0]
    j = web(cm, BOTH, native_action='file', uid=uid, rel=meta_rel)['json']
    meta = json.loads(j['text'])
    stamp = j['stamp']

    def save(**changes):
        text = json.dumps(dict(meta, **changes), indent=1)
        return web(cm, BOTH, native_action='save', uid=uid, rel=meta_rel, text=text, stamp=stamp)['json']

    cat_uid = web(cm, native_action='artifact', uid=uid)['json']['row']['cat_uid'].lower()

    # refused: another alias before the UID, another UID, a bare alias; a category the index would not read as its
    # own - another one, one without its UID (it dropped the artifact, 2026-11-23), its UID beside another alias
    for changes in ({'artifact': 'Other, name,' + uid}, {'artifact': KIM + ',' + LIKE_UID}, {'artifact': KIM},
                    {'category': 'other'}, {'category': 'log, x'}, {'category': 'log'}, {'category': 'other,' + cat_uid},
                    {'category': 'log,' + LIKE_UID}):
        assert 'error' in save(**changes), changes

    # kept: its own alias with commas before its UID (capitals too), the category by alias,UID or its UID alone
    for changes in ({'artifact': '%s,%s' % (KIM, uid.upper())}, {'artifact': '%s , %s' % (KIM, uid)},
                    {'category': 'log,' + cat_uid.upper()}, {'category': cat_uid}, {'artifact': uid, 'category': 'log,' + cat_uid}):
        out = save(**changes)
        assert out.get('saved') == meta_rel, (changes, out)
        stamp = out['stamp']


def test_create_and_rename_take_commas_but_not_a_uid_after_the_last(cm):
    def act(action, **q):
        return web(cm, BOTH, native_action=action, **q)['json']

    out = act('create', cat='log', repo='local', alias='Made, with commas')
    assert out['created'] == 'Made, with commas' and out['cref'].endswith('::Made, with commas,' + out['uid']), out
    assert found(cm, 'Made, with commas') == {('Made, with commas', out['uid'])}
    uid = out['uid']

    for bad in ('x,' + LIKE_UID, 'x, ' + LIKE_UID.upper(), 'a, b,' + LIKE_UID):
        r = act('create', cat='log', repo='local', alias=bad)
        assert 'alias,UID' in r.get('error', ''), (bad, r)
        r = act('rename', uid=uid, alias=bad)
        assert 'alias,UID' in r.get('error', ''), (bad, r)

    # a UID alone: an artifact without an alias, as cx add makes one (as before)
    out2 = act('create', cat='log', repo='local', alias='fedcba9876543210')
    assert out2.get('uid') == 'fedcba9876543210' and found(cm, 'fedcba9876543210') == {(None, 'fedcba9876543210')}, out2

    out = act('rename', uid=uid, alias='Renamed, with commas, too')
    assert out['to'] == 'Renamed, with commas, too' and out['cref'].endswith('::Renamed, with commas, too,' + uid), out
    assert found(cm, 'Renamed, with commas, too') == {('Renamed, with commas, too', uid)}
    assert found(cm, 'Made, with commas') == set()
    assert act('rename', uid=uid, alias='Made, with commas')['to'] == 'Made, with commas'


@pytest.mark.parametrize('cref, expected', [
    ('log,%s::%s' % (CAT, KIM), 'log'),
    ('my, cat,%s::x' % CAT, 'my, cat'),
    ('my, cat::x', 'my, cat'),
    ('%s::x' % CAT.upper(), CAT),
    ('x', ''),
])
def test_cref_page_list_category(cref, expected):
    assert page('cserver.cref')._item_cat({'cref': cref}) == expected


def test_cref_page_list_category_given():
    assert page('cserver.cref')._item_cat({'cat': 'given', 'cref': 'log::x'}) == 'given'


@pytest.mark.parametrize('text, expected', [
    ('task-run-ai', 'task-run-ai'),
    ('local:task-run-ai', 'task-run-ai'),
    ('task-run-ai,' + UID, 'task-run-ai'),
    ('my, config,' + UID.upper(), 'my, config'),
    ('my, config', 'my, config'),
    (UID, UID),
    ('', ''),
])
def test_configs_page_config_alias(text, expected):
    assert page('cserver.cmeta.configs')._config_alias(text) == expected


def test_projects_page_names_and_buttons():
    pj = page('cserver.projects')
    for good in ('a, b', 'Example Co Labs', 'x,' + LIKE_UID[:15]):
        assert pj._valid_name(good), good
    for bad in ('a,' + LIKE_UID, 'a, ' + LIKE_UID.upper(), LIKE_UID, 'a/b', ' a', 'a.'):
        assert not pj._valid_name(bad), bad
    assert pj._name_part('Example Co, Labs') == 'Example Co Labs'                  # a name made from a title: as before

    buttons = [{'uid': UID, 'alias': 'Carol', 'title': 'Hello, world'},
               {'uid': LIKE_UID, 'alias': 'b, c', 'title': 'Other'}]
    one = pj.Category._one
    for name, uid in (('Carol,' + UID, UID), ('anything,' + LIKE_UID.upper(), LIKE_UID), ('Hello, world', UID),
                      ('b, c', LIKE_UID), ('{{{cserver.projects::b, c,%s}}}' % LIKE_UID, LIKE_UID), ('world', UID)):
        hit, err = one(None, buttons, name)
        assert hit is not None and hit['uid'] == uid, (name, err)
    assert one(None, buttons, 'nothing, like it')[0] is None


def _js_function(source, name):
    """The text of a function of a script: from "function <name>(" to its closing brace."""
    i = source.index('function %s(' % name)
    depth, j = 0, source.index('{', i)
    for k in range(j, len(source)):
        depth += {'{': 1, '}': -1}.get(source[k], 0)
        if depth == 0:
            return source[i:k + 1]
    raise AssertionError('no end of ' + name)


@pytest.mark.skipif(shutil.which('node') is None, reason='node is not installed')
def test_browse_js_name_is(tmp_path):
    import cmeta as cmeta_module
    js = os.path.join(os.path.dirname(os.path.abspath(cmeta_module.__file__)), 'internal-repo', 'category',
                      'cserver.browse', 'files', 'js', 'browse.js')
    with open(js, encoding='utf-8') as f:
        source = f.read()
    cases = [['log', 'log', True], ['log', 'LOG', True], ['a, b', 'a, b', True], ['b', 'a, b', False],
             [UID, 'x, y,' + UID, True], [UID, 'x,' + UID.upper(), True], ['log', 'log,' + UID, False],
             ['ctuninglabs@cmeta-aops', 'cmeta-aops', True], ['demo-arc', 'demo*', True], ['log, x', 'log, x ', True]]
    script = tmp_path / 'name_is.js'
    script.write_text('%s\n%s\nvar cases = %s;\nconsole.log(JSON.stringify(cases.map(function (c) { return nameIs(c[0], c[1]); })));\n'
                      % (_js_function(source, 'escRe'), _js_function(source, 'nameIs'), json.dumps(cases)), encoding='utf-8')
    p = subprocess.run(['node', str(script)], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       timeout=60)
    assert p.returncode == 0, p.stderr.decode('utf-8', 'replace')
    got = json.loads(p.stdout.decode('utf-8'))
    assert {tuple(c[:2]): g for c, g in zip(cases, got)} == {tuple(c[:2]): c[2] for c in cases}
