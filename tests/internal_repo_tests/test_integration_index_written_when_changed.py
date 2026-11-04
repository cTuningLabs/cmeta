"""
Integration tests for the index files an incremental index writes (2026-11-04): a repository indexed again,
plugged or unplugged rewrites only the category files whose records or aliases changed, and the index of the
repositories and of the categories only when one of them changed - until then every file of the index was
written at every run (200 files for an empty repository on the author's home), and every reader (each worker
process of a server) loaded them all again. The content written is the same as before: what changes is only
that an unchanged file keeps its time.

Each test runs against a fresh <CMETA_HOME> in tmp_path so it does not touch the user's real cMeta state.

Licensed under the Apache License, Version 2.0.
See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
import pickle
import shutil

import pytest

from cmeta import CMeta


@pytest.fixture()
def cm(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX',
                'CMETA_DEBUG', 'CMETA_VERBOSE', 'CMETA_FAIL_ON_ERROR'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path))
    return CMeta(home=str(tmp_path))


def access(cm, **params):
    params.setdefault('con', False)
    return cm.access(params)


def make_repo(tmp_path, name, repo_uid):
    repo = tmp_path / 'extra' / name
    repo.mkdir(parents=True)
    (repo / '_cmr.yaml').write_text(f'artifact: {name},{repo_uid}\ncategory: repo,f4f792ab40c7498f\n', encoding='utf-8')
    return repo


def plug(cm, repo):
    r = access(cm, category='repo', command='plug', arg1=str(repo))
    assert r['return'] == 0, r.get('error')


def make(cm, alias, repo, category='log', **meta):
    r = access(cm, category=category, command='create', arg1=f'{repo}:{alias}', meta=meta, yaml=True)
    assert r['return'] == 0, r.get('error')
    return r['meta']['artifact']


def hand_made(repo, alias, uid, category='log', category_ref='log,487a7639093a4685'):
    folder = repo / category / alias
    folder.mkdir(parents=True)
    (folder / '_cmeta.yaml').write_text(f'artifact: {alias},{uid}\ncategory: {category_ref}\n', encoding='utf-8')
    return folder


def reindex(cm, repo):
    r = access(cm, category='repo', command='reindex', arg1=repo)
    assert r['return'] == 0, r.get('error')


def stamps(tmp_path):
    """Every index file with its time and size (what a reader's cache and a page's catalog look at)."""
    index = tmp_path / 'index'
    return {e.name: (e.stat().st_mtime_ns, e.stat().st_size) for e in os.scandir(index) if e.is_file()}


def rewritten(before, after):
    return sorted(n for n in set(before) | set(after) if before.get(n) != after.get(n))


def index_data(tmp_path, category):
    with open(tmp_path / 'index' / f'{category}.pkl', 'rb') as f:
        return pickle.load(f)


def find(cm, ref, category='log'):
    return access(cm, category=category, command='find', arg1=ref)


def test_a_reindex_that_changes_nothing_writes_nothing(cm, tmp_path):
    repo = make_repo(tmp_path, 'mine', '1111111111111111')
    plug(cm, repo)
    make(cm, 'kept', 'mine')
    make(cm, 'in-local', 'local')
    before = stamps(tmp_path)
    assert len(before) > 3                      # log, repo, category and the engine's own categories

    reindex(cm, 'mine')
    assert rewritten(before, stamps(tmp_path)) == []

    # the records are there, as they were
    assert find(cm, 'kept')['return'] == 0 and find(cm, 'in-local')['return'] == 0


def test_only_the_category_files_that_changed_are_written(cm, tmp_path):
    repo = make_repo(tmp_path, 'mine', '1111111111111111')
    plug(cm, repo)
    make(cm, 'kept', 'mine')
    make(cm, 'in-local', 'local')
    log_before = index_data(tmp_path, 'log')

    # a folder added by hand: the file of its category alone
    hand_made(repo, 'added', 'aaaaaaaaaaaaaaaa')
    before = stamps(tmp_path)
    reindex(cm, 'mine')
    assert rewritten(before, stamps(tmp_path)) == ['log.pkl']
    assert find(cm, 'added')['return'] == 0
    # what the file holds is what it held, plus the record (the same writer as before)
    log_after = index_data(tmp_path, 'log')
    assert set(log_after['uids']) == set(log_before['uids']) | {'aaaaaaaaaaaaaaaa'}
    for uid, record in log_before['uids'].items():
        assert log_after['uids'][uid] == record

    # a folder removed: the file of its category alone
    shutil.rmtree(repo / 'log' / 'added')
    before = stamps(tmp_path)
    reindex(cm, 'mine')
    assert rewritten(before, stamps(tmp_path)) == ['log.pkl']
    assert find(cm, 'added')['return'] == 16
    assert index_data(tmp_path, 'log')['uids'] == log_before['uids']

    # the descriptor of the repository changed: the index of the repositories alone
    f = repo / '_cmr.yaml'
    f.write_text(f.read_text(encoding='utf-8') + 'owner: me\n', encoding='utf-8')
    before = stamps(tmp_path)
    reindex(cm, 'mine')
    assert rewritten(before, stamps(tmp_path)) == ['repo.pkl']
    r = access(cm, category='repo', command='find', arg1='mine')
    assert r['return'] == 0 and r['artifacts'][0]['cmeta']['owner'] == 'me'


def test_an_artifact_in_another_category_touches_that_file_alone(cm, tmp_path):
    repo = make_repo(tmp_path, 'mine', '1111111111111111')
    plug(cm, repo)
    make(cm, 'a-log', 'mine')
    r = access(cm, category='category', command='add', arg1='local:other', con=False)
    assert r['return'] == 0, r.get('error')
    make(cm, 'an-other', 'mine', category='other')
    before = stamps(tmp_path)

    hand_made(repo, 'two', '2222222222222222', category='other',
              category_ref='other,' + r['meta']['artifact'].split(',')[-1])
    reindex(cm, 'mine')
    assert rewritten(before, stamps(tmp_path)) == ['other.pkl']
    assert find(cm, 'two', category='other')['return'] == 0


def test_unplug_and_plug_write_the_files_the_repository_has_records_in(cm, tmp_path):
    repo = make_repo(tmp_path, 'mine', '1111111111111111')
    plug(cm, repo)
    make(cm, 'a-log', 'mine')
    make(cm, 'in-local', 'local')
    before = stamps(tmp_path)

    r = access(cm, category='repo', command='unplug', arg1='mine')
    assert r['return'] == 0, r.get('error')
    # its records leave log.pkl, it leaves repo.pkl; every other category file is as it was (an unplug makes an
    # empty index file for a category that had none - as it always did; those are new, not rewritten)
    after = stamps(tmp_path)
    assert sorted(n for n in before if before[n] != after.get(n)) == ['log.pkl', 'repo.pkl']   # sorted: the folder's order differs per file system
    for name in set(after) - set(before):
        assert index_data(tmp_path, name[:-4])['uids'] == {}, name
    assert find(cm, 'a-log')['return'] == 16 and find(cm, 'in-local')['return'] == 0

    before = stamps(tmp_path)
    plug(cm, repo)
    assert rewritten(before, stamps(tmp_path)) == ['log.pkl', 'repo.pkl']
    assert find(cm, 'a-log')['return'] == 0


def test_a_new_category_declared_by_the_repository_writes_the_index_of_categories(cm, tmp_path):
    repo = make_repo(tmp_path, 'mine', '1111111111111111')
    plug(cm, repo)
    make(cm, 'a-log', 'mine')
    before = stamps(tmp_path)

    # a category made by hand in the repository: the index of categories, and the new category's own file
    folder = repo / 'category' / 'fresh'
    folder.mkdir(parents=True)
    (folder / '_cmeta.yaml').write_text('artifact: fresh,ffffffffffffffff\ncategory: category,dd9ea50e7f76467f\n',
                                        encoding='utf-8')
    reindex(cm, 'mine')
    changed = rewritten(before, stamps(tmp_path))
    assert 'category.pkl' in changed and 'log.pkl' not in changed and 'repo.pkl' not in changed, changed
    r = access(cm, category='category', command='find', arg1='fresh')
    assert r['return'] == 0 and len(r['artifacts']) == 1

    # ... and once more with nothing new: nothing
    before = stamps(tmp_path)
    reindex(cm, 'mine')
    assert rewritten(before, stamps(tmp_path)) == []


def test_a_full_reindex_writes_every_file_as_before(cm, tmp_path):
    repo = make_repo(tmp_path, 'mine', '1111111111111111')
    plug(cm, repo)
    make(cm, 'a-log', 'mine')
    before = stamps(tmp_path)

    r = cm.repos.index(clean=True, con=False)
    assert r['return'] == 0, r.get('error')
    after = stamps(tmp_path)
    assert set(rewritten(before, after)) == set(before) | set(after)
    assert find(cm, 'a-log')['return'] == 0
