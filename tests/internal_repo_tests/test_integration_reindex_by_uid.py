"""
Integration tests of the incremental index removing records by the UID of their repository (issue #13, its first
step). An incremental index (plug, pull, unzip, unplug, the reindex of one repository, a repository out of reach)
drops the records of the repositories it touches and scans the touched ones again. It did so by path - every record
whose path lay inside a touched folder - and needed a special case for each way a path misleads (a repository nested
in another one, the internal repository of another installation: the two fixes of 0.37.3). A record names its
repository by UID, and since 2026-10-17 that UID decides: the records of every other repository stay as they are, by
construction - also when the folder of the touched repository is gone.

Licensed under the Apache License, Version 2.0.
See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import json
import os
import pickle
import shutil

import pytest

from cmeta import CMeta

CATEGORIES = {'cat-x': 'c1b2c3d4e5f60001', 'cat-y': 'c1b2c3d4e5f60002'}


def make_repo(path, alias, uid, declare_categories=False):
    """A repository folder with its descriptor; the first one declares the two hand-made categories (a _cmeta.yaml
    each and no api folder: the base commands of the engine serve them)."""
    path.mkdir(parents=True, exist_ok=True)
    (path / '_cmr.yaml').write_text(f'artifact: {alias},{uid}\ncategory: repo,f4f792ab40c7498f\n', encoding='utf-8')

    if declare_categories:
        for name, cuid in CATEGORIES.items():
            folder = path / 'category' / name
            folder.mkdir(parents=True)
            (folder / '_cmeta.yaml').write_text(f'artifact: {name},{cuid}\ncategory: category,dd9ea50e7f76467f\n', encoding='utf-8')


def make_artifact(repo, category, alias, uid):
    folder = repo / category / alias
    folder.mkdir(parents=True)
    (folder / '_cmeta.yaml').write_text(f'artifact: {alias},{uid}\ncategory: {category},{CATEGORIES[category]}\n', encoding='utf-8')


def access(cm, **params):
    params.setdefault('con', False)
    return cm.access(params)


def paths_found(cm, category, alias):
    """The paths of the records `find` answers for the alias (none when it is not found)."""
    r = access(cm, category=category, command='find', arg1=alias)
    if r['return'] == 16:
        return []
    assert r['return'] == 0, r.get('error')
    return sorted(os.path.normcase(a['path']) for a in r['artifacts'])


def records(home, except_repo_uid=None):
    """Every record of every category file of the index (the files of the repositories and of the categories left
    out) as {uid: (file, repo uid, path)}, without those of one repository when asked."""
    found = {}
    index = os.path.join(home, 'index')

    for name in sorted(os.listdir(index)):
        if not name.endswith('.pkl') or name in ('repo.pkl', 'category.pkl'):
            continue

        with open(os.path.join(index, name), 'rb') as f:
            data = pickle.load(f)

        for uid, rec in data['uids'].items():
            if rec['cmeta_ref_parts'].get('repo_uid') != except_repo_uid:
                found[uid] = (name, rec['cmeta_ref_parts'].get('repo_uid'), rec['path'])

    return found


@pytest.fixture()
def env(tmp_path, monkeypatch):
    for var in ('CMETA_HOME', 'CMETA_HOME2', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'CMETA_DEBUG', 'CMETA_VERBOSE',
                'CMETA_INTERNAL_REPO_PATH'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CMETA_HOME', str(tmp_path / 'home'))
    return tmp_path


@pytest.fixture()
def three(env):
    """Three sibling repositories a, b and c with artifacts in both categories; a declares the categories."""
    repos = {}
    for i, alias in enumerate(('a', 'b', 'c')):
        repo = env / alias
        make_repo(repo, alias, f'a1b2c3d4e5f6020{i}', declare_categories=(alias == 'a'))
        for ci, category in enumerate(CATEGORIES):
            for k in range(2):
                make_artifact(repo, category, f'{alias}-{category}-{k}', f'b1b2c3d4e5f6{i}{k}{ci}0')
        repos[alias] = repo

    cm = CMeta(home=str(env / 'home'))
    for alias in ('a', 'b', 'c'):
        r = access(cm, category='repo', command='plug', arg1=str(repos[alias]))
        assert r['return'] == 0, r.get('error')

    for alias in ('a', 'b', 'c'):
        for category in CATEGORIES:
            assert len(paths_found(cm, category, f'{alias}-{category}-0')) == 1

    return cm, repos, str(env / 'home')


def test_the_reindex_of_one_repository_leaves_every_other_record_as_it_was(three):
    cm, repos, home = three
    others = records(home, except_repo_uid='a1b2c3d4e5f60201')             # everything but b's records

    shutil.rmtree(repos['b'] / 'cat-x' / 'b-cat-x-0')
    make_artifact(repos['b'], 'cat-y', 'b-cat-y-new', 'b1b2c3d4e5f69999')
    assert access(cm, category='repo', command='reindex', arg1='b')['return'] == 0

    assert paths_found(cm, 'cat-x', 'b-cat-x-0') == []                     # its deleted artifact left
    assert len(paths_found(cm, 'cat-y', 'b-cat-y-new')) == 1               # the new one came
    assert len(paths_found(cm, 'cat-x', 'b-cat-x-1')) == 1
    assert records(home, except_repo_uid='a1b2c3d4e5f60201') == others     # a and c: not one record changed


def test_unplug_removes_the_records_of_that_repository_alone(three):
    cm, repos, home = three
    others = records(home, except_repo_uid='a1b2c3d4e5f60202')             # everything but c's records

    assert access(cm, category='repo', command='unplug', arg1='c')['return'] == 0
    for category in CATEGORIES:
        assert paths_found(cm, category, f'c-{category}-0') == []
    assert records(home) == others                                         # nothing else left or changed

    # and the index of the repositories and of the categories, rebuilt whole at every run
    r = access(cm, category='repo', command='find', arg1='*')
    assert r['return'] == 0 and sorted(a['cmeta_ref_parts']['artifact_alias'] for a in r['artifacts']
                                       if a['cmeta_ref_parts']['artifact_alias'] in ('a', 'b', 'c')) == ['a', 'b']
    assert access(cm, category='category', command='find', arg1='cat-x')['return'] == 0

    # back again
    assert access(cm, category='repo', command='plug', arg1=str(repos['c']))['return'] == 0
    assert len(paths_found(cm, 'cat-y', 'c-cat-y-1')) == 1
    assert records(home, except_repo_uid='a1b2c3d4e5f60202') == others


def test_a_repository_out_of_reach_loses_its_records_and_no_other(three):
    cm, repos, home = three
    others = records(home, except_repo_uid='a1b2c3d4e5f60202')

    # c's descriptor cannot be read: the next incremental index (here of a) takes c's records out - its UID comes
    # from the record the index had for it, as the folder cannot be asked
    os.rename(repos['c'] / '_cmr.yaml', repos['c'] / '_cmr.yaml.away')
    assert access(cm, category='repo', command='reindex', arg1='a')['return'] == 0
    assert paths_found(cm, 'cat-x', 'c-cat-x-0') == []
    assert records(home) == others

    # reachable again: its records return with the next index run of it
    os.rename(repos['c'] / '_cmr.yaml.away', repos['c'] / '_cmr.yaml')
    assert access(cm, category='repo', command='reindex', arg1=str(repos['c']))['return'] == 0
    assert len(paths_found(cm, 'cat-x', 'c-cat-x-0')) == 1
    assert records(home, except_repo_uid='a1b2c3d4e5f60202') == others


def test_a_repository_moved_to_another_folder(three):
    cm, repos, home = three
    others = records(home, except_repo_uid='a1b2c3d4e5f60202')
    moved = repos['c'].parent / 'c-moved'
    shutil.move(str(repos['c']), str(moved))

    # the folder is gone from the registered path: the unplug of that path removes its records - the folder
    # cannot be asked for the UID, the record the index had for it gives it
    assert access(cm, category='repo', command='unplug', arg1=str(repos['c']))['return'] == 0
    assert paths_found(cm, 'cat-x', 'c-cat-x-0') == []
    assert records(home) == others

    # plugged at its new place: its records come back there, and no other record moves
    assert access(cm, category='repo', command='plug', arg1=str(moved))['return'] == 0
    assert paths_found(cm, 'cat-x', 'c-cat-x-0') == [os.path.normcase(str(moved / 'cat-x' / 'c-cat-x-0'))]
    assert records(home, except_repo_uid='a1b2c3d4e5f60202') == others

    # a registered path whose repository is in the index under another path (the move done the other way round:
    # plugged at the new place after the old registration went out of reach) drops nothing when it is forgotten
    with open(os.path.join(home, 'repos.json'), encoding='utf-8') as f:
        registered = json.load(f)
    registered[str(repos['c'])] = {'unreachable': True}
    with open(os.path.join(home, 'repos.json'), 'w', encoding='utf-8') as f:
        json.dump(registered, f)
    assert access(cm, category='repo', command='unplug', arg1=str(repos['c']))['return'] == 0
    assert paths_found(cm, 'cat-x', 'c-cat-x-0') == [os.path.normcase(str(moved / 'cat-x' / 'c-cat-x-0'))]
    assert records(home, except_repo_uid='a1b2c3d4e5f60202') == others


def test_an_alias_shared_by_two_repositories_keeps_the_record_that_stays(three):
    cm, repos, home = three
    for alias, uid in (('b', 'd1b2c3d4e5f60001'), ('c', 'd1b2c3d4e5f60002')):
        make_artifact(repos[alias], 'cat-x', 'same', uid)
        assert access(cm, category='repo', command='reindex', arg1=alias)['return'] == 0
    assert len(paths_found(cm, 'cat-x', 'same')) == 2

    # c leaves: the alias keeps b's record (the whole alias entry left before, and the alias was not found until a
    # full reindex)
    assert access(cm, category='repo', command='unplug', arg1='c')['return'] == 0
    assert paths_found(cm, 'cat-x', 'same') == [os.path.normcase(str(repos['b'] / 'cat-x' / 'same'))]


def test_a_repository_forgotten_between_two_runs_still_loses_its_records(three):
    """An unplug rewrites repos.json and then runs the index; the index run of another process can come in between
    and rebuild the index of repositories without the one that leaves - its UID is then known nowhere, and its
    records are found by their path, those of a registered repository nested in its folder excepted."""
    cm, repos, home = three
    inner = repos['c'] / 'deep' / 'inner'
    make_repo(inner, 'inner', 'a1b2c3d4e5f60299')
    make_artifact(inner, 'cat-x', 'inner-cat-x-0', 'b1b2c3d4e5f69001')
    assert access(cm, category='repo', command='plug', arg1=str(inner))['return'] == 0
    others = records(home, except_repo_uid='a1b2c3d4e5f60202')

    # the registration of c leaves repos.json (what unplug does first) ...
    with open(os.path.join(home, 'repos.json'), encoding='utf-8') as f:
        registered = json.load(f)
    key = next(k for k in registered if os.path.normcase(os.path.normpath(k)) == os.path.normcase(os.path.normpath(str(repos['c']))))
    del registered[key]
    with open(os.path.join(home, 'repos.json'), 'w', encoding='utf-8') as f:
        json.dump(registered, f)

    # ... the run of another process comes in between: the index of repositories has no c any more, its records stay
    assert cm.repos.index(add_repo_paths=[str(repos['a'])])['return'] == 0
    assert len(paths_found(cm, 'cat-x', 'c-cat-x-0')) == 1

    # ... then unplug's own run: c's records leave by their path, inner's stay (a registered repository)
    assert cm.repos.index(delete_repo_paths=[str(repos['c'])])['return'] == 0
    assert paths_found(cm, 'cat-x', 'c-cat-x-0') == []
    assert len(paths_found(cm, 'cat-x', 'inner-cat-x-0')) == 1
    assert records(home) == others


def test_an_incremental_run_says_what_it_indexes(three, capsys):
    """The reindex of one repository said "Reindexing all repos"; it names what it indexes again or removes."""
    cm, repos, home = three
    capsys.readouterr()

    assert access(cm, category='repo', command='reindex', arg1='b', con=True)['return'] == 0
    out = capsys.readouterr().out
    assert 'Reindexing all repos' not in out
    assert 'Indexing again: ' + str(repos['b']) in out

    assert access(cm, category='repo', command='unplug', arg1='c', con=True)['return'] == 0
    out = capsys.readouterr().out
    assert 'Reindexing all repos' not in out
    assert 'Removing from the index: ' in out and str(repos['c']) in out


def test_two_registered_repositories_with_one_uid_are_said(three, capsys):
    cm, repos, home = three
    twin = repos['c'].parent / 'c-twin'
    make_repo(twin, 'c-twin', 'a1b2c3d4e5f60202')                    # c's UID under another alias, no artifacts

    # plug refuses a UID that is registered; a registration written by hand gets the twin in
    r = access(cm, category='repo', command='plug', arg1=str(twin))
    assert r['return'] > 0 and 'already registered' in r['error']
    with open(os.path.join(home, 'repos.json'), encoding='utf-8') as f:
        registered = json.load(f)
    registered[str(twin)] = {}
    with open(os.path.join(home, 'repos.json'), 'w', encoding='utf-8') as f:
        json.dump(registered, f)

    r = access(cm, category='repo', command='reindex', arg1='a', con=True)
    assert r['return'] == 0, r.get('error')
    assert 'two registered repositories carry the UID a1b2c3d4e5f60202' in capsys.readouterr().out
