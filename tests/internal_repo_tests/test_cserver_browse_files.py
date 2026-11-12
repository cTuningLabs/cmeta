"""
The file search of /browse (2026-11-12): an index of the names of every file inside the artifacts and of the texts of
the readable kinds, kept in result::local:cserver-browse-files, built by the server in the background; the switches
"file names" / "file contents" make the plain words look into the files too, file:<name or glob> and text:<words> do
by themselves; a word matches inside longer words, with * and ? as wildcards; each row names the files that matched.
On a throwaway home: artifacts with files of several kinds (a pptx made with zipfile), a category of keys never
entered, a skipped folder, !AI; the index built and waited for through the command line; a change outside cMeta
followed by a sweep; an artifact deleted through cMeta followed by the page's own refresh.
"""

import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import time
import zipfile

import pytest

from cmeta import CMeta


def _fts5():
    """Whether this Python's SQLite has FTS5 (the index needs it; a Python built without it says so on the page)."""
    try:
        sqlite3.connect(':memory:').execute('create virtual table t using fts5(x)')
        return True
    except sqlite3.Error:
        return False


pytestmark = pytest.mark.skipif(not _fts5(), reason="this Python's SQLite has no FTS5")

URLS = {'url': 'http://t/browse/?', 'url_files': 'http://t/browse/', 'url_server': 'http://t/',
        'url_server_js_script': 'http://t/static/js/cmeta_server.js'}
LOCAL = {'client_local': True}
OLD = time.time() - 86400


@pytest.fixture()
def cm(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    cm = CMeta(home=str(tmp_path))
    r = cm.access({'category': 'config', 'command': 'set', 'arg1': 'cserver', 'con': False,
                   'meta': {'browse_file_search': 'yes'}})
    assert r['return'] == 0, r
    return cm


def make(cm, alias, category='memo', **meta):
    r = cm.access({'category': category, 'command': 'create', 'arg1': 'local:' + alias, 'meta': dict(meta), 'con': False})
    assert r['return'] == 0, r
    return r['meta']['artifact'], r['path']


def put(root, rel, text='x'):
    p = os.path.join(root, *rel.split('/'))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(text)
    os.utime(p, (OLD, OLD))
    return p


def web(cm, misc=None, **query):
    r = cm.access({'category': 'cserver.browse', 'command': 'web', 'con': False,
                   'urls': dict(URLS), 'query': query, 'misc': dict(misc or {})})
    assert r['return'] == 0, r
    return r


def search(cm, **query):
    """A search of the test's own category (the throwaway home holds the engine's artifacts too, whose meta names
    dashboards and the like)."""
    query.setdefault('cats', 'memo')
    out = web(cm, native_action='search', **query)['json']
    assert 'error' not in out, out
    return out


def aliases(out):
    return sorted(r['alias'] for r in out['rows'])


def files_of(out, alias):
    row = next(r for r in out['rows'] if r['alias'] == alias)
    return [(f['rel'], f['kind']) for f in row.get('files', [])]


def memo(cm):
    """(artifacts, files, texts) of the test's own category in the index (the throwaway home holds other artifacts
    of the local repository too: the categories made here, the cserver config)."""
    r = cm.access({'category': 'cserver.browse', 'command': 'files', 'stats': True, 'con': False})
    assert r['return'] == 0, r
    cats = {c['cat']: c for c in r['status']['stats'].get('categories', [])}
    assert 'my.crypt' not in cats, cats                      # the keys category never entered
    c = cats.get('memo') or {'arts': 0, 'files': 0, 'texts': 0}
    return c['arts'], c['files'], c['texts']


def build(cm, **kw):
    """The index built (or swept) and waited for, as `cx cserver.browse files --sweep --wait` does (nothing builds
    the first index by itself: the user's choice of 2026-11-12 - the Refresh button or the command line)."""
    kw.setdefault('sweep', not kw.get('rebuild'))
    r = cm.access(dict({'category': 'cserver.browse', 'command': 'files', 'wait': True, 'con': False}, **kw))
    assert r['return'] == 0, r
    return r['status']


@pytest.fixture()
def home(cm):
    """Three artifacts with files (a category of the user's, not a skipped one), one in a category of keys."""
    r = cm.access({'category': 'category', 'command': 'create', 'arg1': 'local:memo', 'con': False})
    assert r['return'] == 0, r
    _, p1 = make(cm, 'plan-2025', tags=['plan'])
    put(p1, 'README.md', 'The dashboard of events and the invoice of March.')
    put(p1, 'Notes/20250331.plan-v2_final.md', 'A plan for the cfe-2025 tax: reindex the sessions.')
    put(p1, '!AI/memory/MEMORY.md', 'memory of the session: keyboard shortcuts')
    put(p1, '.venv/lib/x.py', 'skipped')
    put(p1, 'node_modules/y.js', 'skipped')
    put(p1, 'api_token.txt', 'never')
    put(p1, 'report.pdf', 'binary \x00 stuff')
    _, p2 = make(cm, 'customer-acme')
    put(p2, 'notes.txt', 'Dashboards everywhere. Invoices too.')
    put(p2, 'data.json', '{"customer": "Acme", "amount": 42}')
    _, p3 = make(cm, 'offsite')
    with zipfile.ZipFile(os.path.join(p3, 'slides.pptx'), 'w') as z:
        z.writestr('ppt/slides/slide1.xml', '<p:sld><a:p><a:r><a:t>Quarterly offsite agenda</a:t></a:r></a:p></p:sld>')
    r = cm.access({'category': 'category', 'command': 'create', 'arg1': 'local:my.crypt', 'con': False})
    assert r['return'] == 0, r
    _, p4 = make(cm, 'keys', category='my.crypt')
    put(p4, 'private.md', 'dashboard of secrets')
    return {'plan': p1, 'acme': p2, 'offsite': p3, 'keys': p4}


def test_the_index_is_built_and_the_words_look_into_the_files(cm, home):
    st = build(cm)
    assert st['on'] and st['ready'], st
    assert memo(cm) == (3, 7, 6)
    assert 'cserver-browse-files' in st['db'] and os.path.isfile(st['db'])
    # the result artifact, permanent, in the local repository
    r = cm.access({'category': 'result', 'command': 'find', 'arg1': 'local:cserver-browse-files', 'con': False})
    assert r['return'] == 0 and len(r['artifacts']) == 1 and r['artifacts'][0]['cmeta']['permanent'] is True

    # without the switches: the meta alone
    assert aliases(search(cm, q='dash')) == []
    # a part of a word in the texts, in both artifacts; the row names the files, the text hit with its snippet
    out = search(cm, q='dash', texts='1')
    assert aliases(out) == ['customer-acme', 'plan-2025'], out
    assert files_of(out, 'plan-2025') == [('README.md', 'text')]
    snip = next(r for r in out['rows'] if r['alias'] == 'plan-2025')['files'][0]['snip']
    assert 'dashboard' in snip
    assert out['file_search']['used'] and out['file_search']['texts'] and not out['file_search']['names']
    # the names: a part of a file's name, a folder's name, a number inside a name
    assert aliases(search(cm, q='plan', names='1')) == ['plan-2025']
    assert files_of(search(cm, q='notes', names='1'), 'plan-2025') == [('Notes/20250331.plan-v2_final.md', 'name')]
    assert aliases(search(cm, q='20250331', names='1')) == ['plan-2025']
    # wildcards, a phrase, a word of the pptx, json
    assert aliases(search(cm, q='inv*ce', texts='1')) == ['customer-acme', 'plan-2025']
    assert aliases(search(cm, q='"quarterly offsite"', texts='1')) == ['offsite']
    assert aliases(search(cm, q='acme', texts='1')) == ['customer-acme']
    # -word with the switch: the artifact whose files hold it is left out
    assert aliases(search(cm, q='-dash', texts='1')) == ['offsite']
    # the keys category: never
    assert aliases(search(cm, q='secrets', texts='1', names='1')) == []
    assert aliases(search(cm, q='private', names='1')) == []


def test_the_file_that_holds_every_word_is_named_first_and_ranks_its_artifact(cm, home):
    """2026-11-12, the user's search "ChatGPT B300 Rubin Vera": the artifact was found, its row named files that held
    one of the words, never the note itself. Now a row names the files that hold every word (the words the artifact's
    own meta holds aside), those alone when there are some, 'best' - and such an artifact ranks first: a file named by
    the words, then one whose text holds them as whole words, then inside longer words."""
    # a notes artifact: one note named by the words, many that hold one of them
    _, notes = make(cm, 'notes-2024')
    for i in range(8):
        put(notes, '2025%02d01.ChatGPT-topic %d.md' % (i + 1, i), 'chatgpt about other things %d' % i)
    put(notes, '20260721.ChatGPT-B300 vs Rubin Vera.md', 'the comparison')
    # another artifact whose text holds the words inside longer ones only ("vera" in "several", b300 in gb300)
    _, other = make(cm, 'zz-other')
    put(other, 'mix.md', 'chatgpt said several things about gb300 and rubinstein')
    build(cm)
    out = search(cm, q='ChatGPT B300 Rubin Vera', names='1', texts='1')
    assert aliases(out)[:1] == ['notes-2024'] or out['rows'][0]['alias'] == 'notes-2024', [r['alias'] for r in out['rows']]
    row = out['rows'][0]
    assert row['alias'] == 'notes-2024'
    assert row['files'] == [{'rel': '20260721.ChatGPT-B300 vs Rubin Vera.md', 'kind': 'name', 'best': True}], row['files']
    # the open buttons of the page take the first file; a dry open names it
    r = web(cm, {'client_local': True, 'same_origin': True}, native_action='open', uid=row['uid'], what='far',
            rel=row['files'][0]['rel'], dry='1')['json']
    if 'error' not in r:                              # a machine without Far or without a desktop says so instead
        assert r['file'].endswith('20260721.ChatGPT-B300 vs Rubin Vera.md') and r['cmd'][-1] == r['file']
    r = web(cm, {'client_local': True, 'same_origin': True}, native_action='open', uid=row['uid'], what='folder',
            rel='../../../escape.md', dry='1')['json']
    assert 'error' in r or r['file'] == ''            # a path out of the artifact opens the artifact's folder
    # one word only: the files that hold it, no 'best' needed beyond holding it
    out = search(cm, q='rubin', names='1', texts='1')
    names = {r['alias']: [f['rel'] for f in r.get('files', [])] for r in out['rows']}
    assert names.get('notes-2024') == ['20260721.ChatGPT-B300 vs Rubin Vera.md'] and names.get('zz-other') == ['mix.md'], names


def test_the_artifact_page_opens_on_the_file(cm, home):
    """The page of an artifact named with a file (/cref/<cRef>/<file>, the link of a search's row): the Files open
    on it, its folders unfolded, the file highlighted (C.focus)."""
    build(cm)
    out = search(cm, q='file:20250331')
    row = out['rows'][0]
    rel = row['files'][0]['rel']
    r = cm.access({'category': 'cserver.cref', 'command': 'web', 'con': False, 'urls': dict(URLS),
                   'query': {'cref': '%s::%s,%s/%s' % (row['cat'], row['alias'], row['uid'], rel)}, 'misc': {'client_local': True}})
    assert r['return'] == 0, r
    html = r['html_meta']['html']
    assert '"focus": "%s"' % rel in html or "'focus': '%s'" % rel in html or ('focus' in html and rel in html)
    assert 'C.file||C.focus' in html and "classList.add('on','hit')" in html


def test_file_and_text_terms_need_no_switch(cm, home):
    build(cm)
    out = search(cm, q='file:*.pdf')
    assert aliases(out) == ['plan-2025'] and files_of(out, 'plan-2025') == [('report.pdf', 'name')]
    assert aliases(search(cm, q='file:notes')) == ['customer-acme', 'plan-2025']      # notes.txt, Notes/
    assert aliases(search(cm, q='file:slides')) == ['offsite']
    assert aliases(search(cm, q='-file:*.md')) == ['customer-acme', 'offsite']
    assert aliases(search(cm, q='text:keyboard')) == ['plan-2025']                   # !AI/memory
    assert aliases(search(cm, q='text:"test session"')) == []
    assert aliases(search(cm, q='tag:plan text:cfe')) == ['plan-2025']
    # the skipped folders and the key-like file never
    assert aliases(search(cm, q='file:x.py')) == [] and aliases(search(cm, q='file:api_token')) == []
    # a wildcard that stands for too many words is said
    assert 'notices' not in search(cm, q='text:dash')


def test_changes_outside_cmeta_are_found_by_a_sweep(cm, home):
    build(cm)
    time.sleep(0.05)
    put(home['acme'], 'Notes/new-idea.md', 'A brand new idea about keyboards')
    os.remove(os.path.join(home['plan'], 'README.md'))
    with open(os.path.join(home['acme'], 'notes.txt'), 'w', encoding='utf-8') as f:
        f.write('Edited: zebras instead.')
    # nothing of it is seen before the sweep (nothing sweeps by itself); a part of a
    # word matches inside a longer word, never the other way round ("keyboards" is not inside "keyboard")
    assert aliases(search(cm, q='keyboard', texts='1')) == ['plan-2025']
    assert aliases(search(cm, q='keyboards', texts='1')) == []
    st = build(cm, sweep=True)
    assert st['ready'] and memo(cm) == (3, 7, 6), st
    assert aliases(search(cm, q='keyboard', texts='1')) == ['customer-acme', 'plan-2025']
    assert aliases(search(cm, q='keyboards', texts='1')) == ['customer-acme']
    assert aliases(search(cm, q='file:README')) == []
    assert aliases(search(cm, q='zebra', texts='1')) == ['customer-acme']
    assert aliases(search(cm, q='invoice', texts='1')) == []                            # the old words of notes.txt gone


def test_an_artifact_deleted_through_cmeta_is_dropped_by_the_pages_own_refresh(cm, home):
    build(cm)
    assert aliases(search(cm, q='file:slides')) == ['offsite']
    r = cm.access({'category': 'memo', 'command': 'delete', 'arg1': 'local:offsite', 'force': True, 'con': False})
    assert r['return'] == 0, r
    # the page's reload notices cMeta's own change and the index follows (browse_file_search_follow); the pass it
    # started is waited for as the command line does
    out = web(cm, native_action='reload')['json']
    assert out['file_index']['on']
    cm.access({'category': 'cserver.browse', 'command': 'files', 'wait': True, 'con': False})
    assert aliases(search(cm, q='file:slides')) == []
    assert memo(cm) == (2, 6, 5)


def test_rebuild_clear_and_the_statistics(cm, home):
    build(cm)
    st = build(cm, rebuild=True)
    assert st['ready'] and memo(cm) == (3, 7, 6)
    r = cm.access({'category': 'cserver.browse', 'command': 'files', 'stats': True, 'con': False})
    x = r['status']['stats']
    assert x['ready'] and x['files'] >= 7 and x['arts'] >= 3
    assert {e['ext']: e['files'] for e in x['exts']}['md'] >= 3
    assert any(a['part'] == 'memory' and a['files'] == 1 for a in x['ai'])
    out = web(cm, LOCAL, native_action='file_stats')['json']
    assert out['ready'] and out['files'] == x['files']
    r = cm.access({'category': 'cserver.browse', 'command': 'files', 'clear': True, 'con': False})
    assert r['return'] == 0 and r['cleared'] >= 1
    assert not os.path.isfile(st['db'])
    # a search with a switch while there is no index: a notice, the meta alone answers - and nothing builds it by
    # itself (the page's open neither): the Refresh button or the command line do
    out = search(cm, q='dash', texts='1')
    assert aliases(out) == [] and any('refresh builds it' in n for n in out.get('notices', []))
    st = web(cm, native_action='options')['json']['file_index']
    assert st['on'] and not st['ready'] and not st['building'] and 'refresh builds it' in st['notice']


def test_the_page_carries_the_switches_and_the_settings_declare_the_keys(cm, home):
    r = web(cm, misc=LOCAL)
    html = r['html_meta']['html']
    cfg = json.loads(html.split('var CONFIG = ', 1)[1].split(';</script>', 1)[0])
    assert cfg['file_search'] == {'on': True, 'manage': True}
    assert 'id="cbr-names"' in html and 'id="cbr-texts"' in html and 'id="cbr-files-stats"' in html
    r = cm.access({'category': 'config', 'command': 'set', 'arg1': 'cserver', 'con': False, 'meta': {'browse_file_search': 'no'}})
    assert r['return'] == 0
    cfg = json.loads(web(cm)['html_meta']['html'].split('var CONFIG = ', 1)[1].split(';</script>', 1)[0])
    assert cfg['file_search']['on'] is False
    out = search(cm, q='dash', texts='1')
    assert any('browse_file_search' in n for n in out.get('notices', []))
    r = cm.access({'category': 'cserver.browse', 'command': 'files', 'con': False})
    assert r['return'] == 0 and r['on'] is False


def test_only_the_owners_refresh_the_index_and_read_its_statistics(cm, home):
    """On a site that signs its readers in (a hosted site), everyone searches the index within the repositories
    they may read; its refresh, rebuild, clear and statistics - which name the files of every repository - are for the
    owners a host names (misc.file_index_manage), a browser on the server's own machine, or everyone on a personal
    server whose config opens the file browser (browse_files: yes)."""
    build(cm)
    reader = {'browse_files': True}                     # what the Labs site gives every signed-in person
    out = web(cm, reader, native_action='file_index', do='sweep')['json']
    assert 'owners' in out.get('error', ''), out
    assert 'owners' in web(cm, reader, native_action='file_stats')['json'].get('error', '')
    cfg = json.loads(web(cm, reader)['html_meta']['html'].split('var CONFIG = ', 1)[1].split(';</script>', 1)[0])
    assert cfg['file_search'] == {'on': True, 'manage': False}
    # the reader still searches the files
    assert aliases(search(cm, q='dash', texts='1')) == ['customer-acme', 'plan-2025']
    # an owner of the site
    owner = {'browse_files': True, 'file_index_manage': True}
    assert web(cm, owner, native_action='file_stats')['json']['ready']
    out = web(cm, owner, native_action='file_index', do='sweep')['json']
    assert not out.get('error') and out['on'], out          # (the status carries an empty error)
    cm.access({'category': 'cserver.browse', 'command': 'files', 'wait': True, 'con': False})
    # a personal server whose config opens the file browser to everyone it lets in
    r = cm.access({'category': 'config', 'command': 'set', 'arg1': 'cserver', 'con': False, 'meta': {'browse_files': 'yes'}})
    assert r['return'] == 0
    assert web(cm, {}, native_action='file_stats')['json']['ready']


def _files_index():
    """The index module itself, loaded by its path as the category's api loads it."""
    import cmeta
    path = os.path.join(os.path.dirname(cmeta.__file__), 'internal-repo', 'category', 'cserver.browse', 'api',
                        'files_index.py')
    spec = importlib.util.spec_from_file_location('test_cserver_browse_files_index', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_build_lock_between_processes(tmp_path):
    """Two processes may want to build the same index (a server and the command line): the one that holds the lock
    keeps it as long as it touches it while it works - a first build may last longer than LOCK_STALE -, a lock not
    touched for LOCK_STALE or of a process that is gone is taken over, one still being written (no pid in it yet) is
    judged by its time alone, and the builder's progress touches its lock."""
    fx = _files_index()
    folder, lock = str(tmp_path), tmp_path / fx.LOCK_FILE

    def held(pid, age, written=True):
        # the time written in the line is old on purpose: the file's own time decides
        lock.write_text('%d %d' % (pid, int(time.time()) - 99999) if written else '', encoding='utf-8')
        t = time.time() - age
        os.utime(str(lock), (t, t))

    live = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'], stdin=subprocess.DEVNULL)
    try:
        held(live.pid, 60)                          # a builder at work, touched a minute ago: kept
        assert fx._take_lock(folder) is False
        held(live.pid, fx.LOCK_STALE + 60)          # alive but untouched for too long (stuck, or the pid reused)
        assert fx._take_lock(folder) is True
        assert lock.read_text(encoding='utf-8').split()[0] == str(os.getpid())
        fx._drop_lock(folder)
        assert not lock.exists()

        held(live.pid, 0, written=False)            # being written: fresh, kept
        assert fx._take_lock(folder) is False
        held(live.pid, fx.LOCK_STALE + 60, written=False)
        assert fx._take_lock(folder) is True
        fx._drop_lock(folder)
    finally:
        live.kill()
        live.wait()

    ended = subprocess.Popen([sys.executable, '-c', 'pass'], stdin=subprocess.DEVNULL)
    ended.wait()
    pid = ended.pid
    del ended
    held(pid, 0)                                    # a process that is gone: taken over at once
    assert fx._take_lock(folder) is True
    fx._drop_lock(folder)

    # a builder's progress touches its lock (once a LOCK_TOUCH)
    held(os.getpid(), 600)
    db = os.path.join(folder, fx.DB_FILE)
    fx._create(db, '{}')
    b = fx._Build(db, [], {'text': [], 'max_kb': 1}, 1)
    try:
        b.touched -= fx.LOCK_TOUCH + 1
        b.progress('names', 1, 2)
    finally:
        b.close()
    assert time.time() - os.path.getmtime(str(lock)) < 60


def test_an_sqlite_that_cannot_delete_word_rows(tmp_path, monkeypatch):
    """An SQLite before 3.43 (the Python 3.9 of python.org: 3.37) has no contentless_delete: the word rows of a file
    cannot be deleted. A file changed outside cMeta gets a new id - its old words no longer find it, its new ones do
    (the CI of 2026-11-12 found the old words still finding it on Windows); a file deleted is no longer found and its
    id is never given to a new file."""
    fx = _files_index()

    def plain(con, name, column):                   # what such an SQLite makes (_fts_create's fallback)
        con.execute("create virtual table %s using fts5(%s, content='', tokenize='unicode61 remove_diacritics 2')"
                    % (name, column))
        return False

    monkeypatch.setattr(fx, '_fts_create', plain)
    root = str(tmp_path / 'art')
    put(root, 'notes.txt', 'the invoice of the month')
    put(root, 'plan.md', 'a plan of the quarter')
    put(root, 'zz/last.md', 'zzlast words')
    folder = str(tmp_path / 'index')
    os.makedirs(folder)
    s = fx.settings({'browse_file_search': 'yes'})
    items = [{'uid': 'f' * 16, 'cat': 'memo', 'repo': 'local', 'path': root}]

    def found(word):
        q = fx.Query(folder)
        try:
            return sorted(rel for _, rel in q.locate(q.ids_with(word, names=False, texts=True)).values())
        finally:
            q.close()

    def touch(*paths):
        t = time.time()
        for p in paths:
            os.utime(p, (t, t))

    fx._pass(folder, items, s, set(), 'rebuild')
    q = fx.Query(folder)
    assert fx._meta(q.con)['deletable'] == '0'
    q.close()
    assert found('invoice') == ['notes.txt'] and found('quarter') == ['plan.md'] and found('zzlast') == ['zz/last.md']

    # a text changed outside cMeta, a file deleted: a sweep
    touch(put(root, 'notes.txt', 'the receipt of the year'))
    os.remove(os.path.join(root, 'zz', 'last.md'))
    touch(os.path.join(root, 'zz'))
    fx._pass(folder, items, s, set(), 'sweep')
    assert found('invoice') == [] and found('receipt') == ['notes.txt']
    assert found('zzlast') == [] and found('quarter') == ['plan.md']

    # a new file afterwards: a new id, not the deleted file's (whose words stay behind, unseen)
    put(root, 'zz/new.md', 'fresh words')
    touch(os.path.join(root, 'zz'))
    fx._pass(folder, items, s, set(), 'sweep')
    assert found('fresh') == ['zz/new.md'] and found('zzlast') == [] and found('invoice') == []
