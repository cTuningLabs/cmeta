"""
Integration tests for the full reindex (`cx --reindex`): the new index is built completely in a
temporary sibling folder and replaces the previous index only when it is complete, so an aborted
reindex leaves the previous index intact; a category UID found in two repositories is a warning
that keeps the first copy instead of an error that aborts the reindex.

Each test runs against a fresh <CMETA_HOME> in tmp_path so it does not touch the user's real
cMeta state.

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
import sys

import pytest

from cmeta import CMeta

CATEGORY_UID = 'fedcba9876543210'

API_V1 = '''from cmeta.category import InitCategory

class Category(InitCategory):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, module_file_path = __file__, **kwargs)
'''


@pytest.fixture()
def cm(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX',
                'CMETA_DEBUG', 'CMETA_VERBOSE'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    return CMeta(home=str(tmp_path))


def access(cm, **params):
    params.setdefault('con', False)
    return cm.access(params)


def make_repo(tmp_path, name, repo_uid, artifact_uid):
    """A repository with its own copy of the category `dupcat,CATEGORY_UID` and one artifact in it."""
    repo = tmp_path / 'extra' / name
    category = repo / 'category' / 'dupcat'
    (category / 'api').mkdir(parents=True)
    (repo / '_cmr.yaml').write_text(f'artifact: {name},{repo_uid}\ncategory: repo,f4f792ab40c7498f\n', encoding='utf-8')
    (category / '_cmeta.yaml').write_text(f'artifact: dupcat,{CATEGORY_UID}\ncategory: category,dd9ea50e7f76467f\n'
                                          'last_api_version: 1\nbase_category_default_api_versions:\n  "1": 1\n',
                                          encoding='utf-8')
    (category / 'api' / 'v1.py').write_text(API_V1, encoding='utf-8')
    artifact = repo / 'dupcat' / f'art-{name}'
    artifact.mkdir(parents=True)
    (artifact / '_cmeta.yaml').write_text(f'artifact: art-{name},{artifact_uid}\ncategory: dupcat,{CATEGORY_UID}\n',
                                          encoding='utf-8')
    return repo


def plug(cm, repo):
    return access(cm, category='repo', command='plug', arg1=str(repo))


def same(path):
    return os.path.normcase(os.path.normpath(str(path)))


def paths(r):
    return [same(a['path']) for a in r.get('artifacts', [])]


def index_files(tmp_path):
    """The index files with their modification times and contents."""
    return {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in (tmp_path / 'index').glob('*.pkl')}


def index_folders(tmp_path):
    """The `index*` folders of CMETA_HOME: only `index` once a reindex is over."""
    return sorted(p.name for p in tmp_path.iterdir() if p.is_dir() and p.name.startswith('index'))


def test_a_duplicate_category_uid_is_a_warning_that_keeps_the_first_copy(cm, tmp_path, capsys):
    access(cm, category='repo', command='list')          # the layout and the first index
    repo_a = make_repo(tmp_path, 'dup-a', '1111111111111111', 'aaaaaaaaaaaaaaaa')
    repo_b = make_repo(tmp_path, 'dup-b', '2222222222222222', 'bbbbbbbbbbbbbbbb')
    kept, skipped = repo_a / 'category' / 'dupcat', repo_b / 'category' / 'dupcat'

    assert plug(cm, repo_a)['return'] == 0
    capsys.readouterr()

    # Plugging the second repository indexes it incrementally: the same warning, no error
    r = plug(cm, repo_b)
    assert r['return'] == 0, r.get('error')
    out = capsys.readouterr().out
    assert 'Warning' in out and 'same UID' in out and str(kept) in out and str(skipped) in out

    # The full reindex: no abort, a warning naming the kept and the skipped path, nothing left behind
    r = access(cm, reindex=True)
    assert r['return'] == 0, r.get('error')
    out = capsys.readouterr().out
    assert 'Warning' in out and 'same UID' in out and str(kept) in out and str(skipped) in out
    assert index_folders(tmp_path) == ['index']

    # The category resolves once, to the first repository: by alias, alias,UID and UID
    for ref in ('dupcat', f'dupcat,{CATEGORY_UID}', CATEGORY_UID):
        r = access(cm, category='category', command='find', arg1=ref)
        assert r['return'] == 0, (ref, r.get('error'))
        assert paths(r) == [same(kept)], ref

    # The artifacts of both repositories are reached through the kept copy
    r = access(cm, category='dupcat', command='find')
    assert r['return'] == 0, r.get('error')
    assert sorted(a['cmeta_ref_parts']['artifact_alias'] for a in r['artifacts']) == ['art-dup-a', 'art-dup-b']

    r = access(cm, category=f'dupcat,{CATEGORY_UID}', command='find', arg1='art-dup-b')
    assert r['return'] == 0, r.get('error')
    assert paths(r) == [same(repo_b / 'dupcat' / 'art-dup-b')]


def test_a_failed_reindex_keeps_the_previous_index(cm, tmp_path, monkeypatch):
    r = access(cm, category='asset', command='create', arg1='kept-asset', yaml=True)
    assert r['return'] == 0, r.get('error')
    before = index_files(tmp_path)
    assert {'repo.pkl', 'category.pkl', 'asset.pkl'} <= set(before)

    original = cm.repos._find_artifacts
    state = {'fail': True, 'tmp': [], 'tmp_files': []}

    def find_artifacts(*args, **kwargs):
        # Called once per category while the artifacts are indexed, after repo.pkl and category.pkl were recorded
        if not state['fail']:
            return original(*args, **kwargs)
        state['tmp'] = [p for p in tmp_path.iterdir() if p.name.startswith('index.tmp-')]
        state['tmp_files'] = sorted(q.name for p in state['tmp'] for q in p.glob('*.pkl'))
        return {'return': 1, 'error': 'injected failure'}

    monkeypatch.setattr(cm.repos, '_find_artifacts', find_artifacts)

    r = access(cm, reindex=True)
    assert r['return'] > 0 and 'injected failure' in r['error']

    # The new index was being built in a temporary folder next to the index ...
    assert [p.name for p in state['tmp']] == [f'index.tmp-{os.getpid()}']
    assert state['tmp_files'] == ['category.pkl', 'repo.pkl']
    # ... the previous index is untouched and usable, and the temporary folder is gone
    assert index_files(tmp_path) == before
    assert index_folders(tmp_path) == ['index']
    r = access(cm, category='asset', command='find', arg1='kept-asset')
    assert r['return'] == 0 and len(r['artifacts']) == 1

    # The next reindex succeeds and replaces the index
    state['fail'] = False
    r = access(cm, reindex=True)
    assert r['return'] == 0, r.get('error')
    assert set(index_files(tmp_path)) == set(before)
    assert index_folders(tmp_path) == ['index']
    r = access(cm, category='asset', command='find', arg1='kept-asset')
    assert r['return'] == 0 and len(r['artifacts']) == 1


def test_an_exception_during_the_reindex_keeps_the_previous_index(cm, tmp_path, monkeypatch):
    access(cm, category='repo', command='list')
    assert index_folders(tmp_path) == ['index']        # the first index leaves nothing behind either
    before = index_files(tmp_path)
    assert before

    def boom(*args, **kwargs):
        raise RuntimeError('injected failure')

    monkeypatch.setattr(cm.repos, '_find_artifacts', boom)
    with pytest.raises(RuntimeError, match='injected failure'):
        cm.repos.reindex()

    assert index_files(tmp_path) == before
    assert index_folders(tmp_path) == ['index']


@pytest.mark.skipif(sys.platform != 'win32', reason='only Windows refuses to rename a folder with an open file')
def test_a_swap_that_is_refused_keeps_the_previous_index(cm, tmp_path):
    r = access(cm, category='asset', command='create', arg1='kept-asset', yaml=True)
    assert r['return'] == 0, r.get('error')
    before = index_files(tmp_path)

    # Another process still reads a file of the index when the new one is complete: the old one cannot be moved away
    with open(tmp_path / 'index' / 'repo.pkl', 'rb'):
        r = access(cm, reindex=True)
    assert r['return'] > 0 and 'previous index is kept' in r['error']
    assert index_files(tmp_path) == before
    assert index_folders(tmp_path) == ['index']

    # Once the file is closed, the reindex goes through
    r = access(cm, reindex=True)
    assert r['return'] == 0, r.get('error')
    assert set(index_files(tmp_path)) == set(before)
    assert index_folders(tmp_path) == ['index']
