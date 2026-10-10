"""
Integration tests for `cx repo reindex <repository>`: one registered repository is indexed again
(its `_cmr.yaml` re-read, its artifacts rescanned) while the records of the other repositories
stay as they are; a repository whose folder is not there is refused. Also the incremental index
that pull, plug and unzip use: the records of a category of which the repository holds no
artifact any more are dropped.

Each test runs against a fresh <CMETA_HOME> in tmp_path so it does not touch the user's real
cMeta state.

Licensed under the Apache License, Version 2.0.
See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import json
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


def find(cm, ref=None, category='log', **params):
    return access(cm, category=category, command='find', arg1=ref, **params)


def uids(r):
    return sorted(a['cmeta_ref_parts']['artifact_uid'] for a in r.get('artifacts', []))


def repo_record(cm, ref):
    r = access(cm, category='repo', command='find', arg1=ref)
    assert r['return'] == 0, r.get('error')
    assert len(r['artifacts']) == 1
    return r['artifacts'][0]


def index_data(tmp_path, category):
    with open(tmp_path / 'index' / f'{category}.pkl', 'rb') as f:
        return pickle.load(f)


def repos_json(tmp_path):
    return json.loads((tmp_path / 'repos.json').read_text(encoding='utf-8'))


def same(path):
    return os.path.normcase(os.path.normpath(str(path)))


def test_repo_reindex_rereads_the_descriptor_and_rescans_the_artifacts(cm, tmp_path):
    repo = make_repo(tmp_path, 'mine', '1111111111111111')
    plug(cm, repo)
    local_uid = make(cm, 'in-local', 'local', tags=['local'])
    kept = make(cm, 'kept', 'mine')
    removed = make(cm, 'removed', 'mine')
    local_before = index_data(tmp_path, 'log')['uids'][local_uid]

    # Changes made behind cMeta's back: the descriptor, a new folder, a folder removed
    f = repo / '_cmr.yaml'
    f.write_text(f.read_text(encoding='utf-8') + 'owner: me\n', encoding='utf-8')
    hand_made(repo, 'added', 'aaaaaaaaaaaaaaaa')
    shutil.rmtree(repo / 'log' / 'removed')

    assert 'owner' not in repo_record(cm, 'mine')['cmeta']
    assert find(cm, 'added')['return'] == 16
    assert uids(find(cm, 'removed')) == [removed]

    r = access(cm, category='repo', command='reindex', arg1='mine')
    assert r['return'] == 0, r.get('error')
    assert [a['cmeta_ref_parts']['artifact_alias'] for a in r['artifacts']] == ['mine']
    assert [same(p) for p in r['paths']] == [same(repo)]

    assert repo_record(cm, 'mine')['cmeta']['owner'] == 'me'
    assert uids(find(cm, 'added')) == ['aaaaaaaaaaaaaaaa']
    assert uids(find(cm, 'kept')) == [kept]
    assert find(cm, 'removed')['return'] == 16
    assert 'removed' not in index_data(tmp_path, 'log')['lowercase_aliases']
    # The other repository's records are as they were
    assert index_data(tmp_path, 'log')['uids'][local_uid] == local_before
    assert repos_json(tmp_path) == repos_json(tmp_path)   # still readable
    assert same(repo) in [same(p) for p in repos_json(tmp_path)]


def test_repo_reindex_by_uid_path_and_dot(cm, tmp_path, monkeypatch):
    repo = make_repo(tmp_path, 'mine', '1111111111111111')
    plug(cm, repo)
    make(cm, 'seed', 'mine')

    hand_made(repo, 'by-uid', 'aaaaaaaaaaaaaaaa')
    r = access(cm, category='repo', command='reindex', arg1='1111111111111111')
    assert r['return'] == 0, r.get('error')
    assert uids(find(cm, 'by-uid')) == ['aaaaaaaaaaaaaaaa']

    hand_made(repo, 'by-path', 'bbbbbbbbbbbbbbbb')
    r = access(cm, category='repo', command='reindex', arg1=str(repo))
    assert r['return'] == 0, r.get('error')
    assert uids(find(cm, 'by-path')) == ['bbbbbbbbbbbbbbbb']

    hand_made(repo, 'by-sub-path', 'cccccccccccccccc')
    r = access(cm, category='repo', command='reindex', arg1=str(repo / 'log'))     # a folder inside the repository
    assert r['return'] == 0, r.get('error')
    assert uids(find(cm, 'by-sub-path')) == ['cccccccccccccccc']

    hand_made(repo, 'by-dot', 'dddddddddddddddd')
    monkeypatch.chdir(repo / 'log' / 'by-dot')
    r = access(cm, category='repo', command='reindex', arg1='.')
    assert r['return'] == 0, r.get('error')
    assert uids(find(cm, 'by-dot')) == ['dddddddddddddddd']

    monkeypatch.chdir(tmp_path)
    r = access(cm, category='repo', command='reindex', arg1='.')
    assert r['return'] == 16 and 'plug' in r['error']


def test_repo_reindex_refuses_what_it_cannot_do_safely(cm, tmp_path):
    repo = make_repo(tmp_path, 'mine', '1111111111111111')
    plug(cm, repo)
    uid = make(cm, 'seed', 'mine')
    before = index_data(tmp_path, 'log')
    repos_before = repos_json(tmp_path)

    r = access(cm, category='repo', command='reindex')
    assert r['return'] == 1 and 'cx --reindex' in r['error']

    r = access(cm, category='repo', command='reindex', arg1='no-such-repo')
    assert r['return'] == 16

    # The repository's folder is not there (a detached drive): refused, nothing changed, the
    # registration and the records stay
    moved = tmp_path / 'extra' / 'mine-away'
    (tmp_path / 'extra' / 'mine').rename(moved)
    r = access(cm, category='repo', command='reindex', arg1='mine')
    assert r['return'] == 1 and 'not there' in r['error'], r
    assert index_data(tmp_path, 'log') == before
    assert repos_json(tmp_path) == repos_before
    assert uids(find(cm, 'seed')) == [uid]

    moved.rename(tmp_path / 'extra' / 'mine')
    r = access(cm, category='repo', command='reindex', arg1='mine')
    assert r['return'] == 0, r.get('error')
    assert uids(find(cm, 'seed')) == [uid]


def test_repo_reindex_after_the_descriptor_renamed_the_repository(cm, tmp_path):
    repo = make_repo(tmp_path, 'old-repo', '1111111111111111')
    plug(cm, repo)
    uid = make(cm, 'art', 'old-repo')

    (repo / '_cmr.yaml').write_text('artifact: new-repo,1111111111111111\ncategory: repo,f4f792ab40c7498f\n', encoding='utf-8')

    r = access(cm, category='repo', command='reindex', arg1='1111111111111111')
    assert r['return'] == 0, r.get('error')
    assert repo_record(cm, 'new-repo')['cmeta_ref_parts']['artifact_uid'] == '1111111111111111'
    assert access(cm, category='repo', command='find', arg1='old-repo')['return'] == 16
    assert find(cm, 'art')['artifacts'][0]['cmeta_ref_parts']['repo_alias'] == 'new-repo'
    assert uids(find(cm, 'new-repo:art')) == [uid]


def test_repo_reindex_with_a_wildcard_and_several_repositories(cm, tmp_path):
    repo_a = make_repo(tmp_path, 'mine-a', '1111111111111111')
    repo_b = make_repo(tmp_path, 'mine-b', '2222222222222222')
    other = make_repo(tmp_path, 'other', '3333333333333333')
    for repo in (repo_a, repo_b, other):
        plug(cm, repo)
    hand_made(repo_a, 'in-a', 'aaaaaaaaaaaaaaaa')
    hand_made(repo_b, 'in-b', 'bbbbbbbbbbbbbbbb')
    hand_made(other, 'in-other', 'cccccccccccccccc')

    r = access(cm, category='repo', command='reindex', arg1='mine-*')
    assert r['return'] == 0, r.get('error')
    assert sorted(a['cmeta_ref_parts']['artifact_alias'] for a in r['artifacts']) == ['mine-a', 'mine-b']
    assert uids(find(cm, 'in-a')) == ['aaaaaaaaaaaaaaaa'] and uids(find(cm, 'in-b')) == ['bbbbbbbbbbbbbbbb']
    assert find(cm, 'in-other')['return'] == 16            # not asked for, not scanned


def test_the_incremental_index_drops_the_records_of_an_emptied_category(cm, tmp_path):
    # The index that pull, plug and reindex share: a repository whose last artifact of a category
    # was removed by hand loses that record too
    repo = make_repo(tmp_path, 'mine', '1111111111111111')
    plug(cm, repo)
    local_uid = make(cm, 'in-local', 'local')
    only = make(cm, 'only-one', 'mine')
    asset = make(cm, 'an-asset', 'mine', category='asset')

    shutil.rmtree(repo / 'log' / 'only-one')
    r = access(cm, category='repo', command='reindex', arg1='mine')
    assert r['return'] == 0, r.get('error')

    assert find(cm, 'only-one')['return'] == 16
    assert only not in index_data(tmp_path, 'log')['uids']
    assert uids(find(cm, 'in-local')) == [local_uid]
    assert uids(find(cm, 'an-asset', category='asset')) == [asset]

    # The same through plug of a second copy: plugging indexes incrementally as well
    other = make_repo(tmp_path, 'other', '2222222222222222')
    hand_made(other, 'in-other', 'eeeeeeeeeeeeeeee')
    plug(cm, other)
    assert uids(find(cm, 'in-other')) == ['eeeeeeeeeeeeeeee']
    assert uids(find(cm, 'in-local')) == [local_uid]
